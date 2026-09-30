# jev-swarm

Fish schooling under predator attack, where **every fish picks its next action with Jev** from its own local view.
It follows the design doc *Fish Schooling Under Predator Attack* (30 Sep 2026): a 2D world, no central planner,
no fish-to-fish messages, and a hard information boundary between the world and what each fish can see.

![viewer](docs/viewer.jpg)

## Quick start

```bash
python3 -m pip install numpy        # only dependency
python3 -m jevswarm                 # then open http://127.0.0.1:8777
```

The **launch screen** lets you pick a scenario and set every hyperparameter before the run starts. The groups are
Run, Policy, World, Fish vision, Timing and motion, and Predator. It also has buttons to test the Jev and chat
models, and it estimates the load and cost. The **viewer** then runs in real time. While it runs you can:

- **Pause, step** one decision interval, change **speed** (1/8x to 8x), and switch the **policy** or **sampling vs argmax** live.
- Click to **select a fish** and see three views side by side: the world, that fish's exact vision sector
  (occlusion shadows, dimmed hidden entities, slot labels), and its candidate probabilities with the exact JSON observation that was sent.
- Make what-if **interventions**: place a predator, add a rock, force a **false alarm** burst, withdraw predators, or change
  vision range or turbidity. Each one is labelled in the event log and replayed by deterministic replay.
- **Speculate** by betting play money on outcomes (survivors, captures by time T, largest group, polarization, recovery).
  Bets placed earlier pay better odds and are settled automatically.
- **Ask the analyst** (gpt-6-astra) about what the school is doing. It sees the evaluator's global metrics; the fish never do.
- Watch the inference health: latency p50/p95, decision age, achieved Hz, fallback fraction, stale drops, failures and API cost.

Each run writes `runs/<timestamp>_<scenario>_<policy>_s<seed>/` with these files:

| File | Contents |
|---|---|
| `config.json` | Full config, prompt hash and decision instruction |
| `decisions.jsonl` | Every applied decision: observation, candidates, raw and normalized distribution, applied action, source, latency, age and model version |
| `events.jsonl` | Scenario events, interventions and predictions |
| `metrics.jsonl` | Evaluator metrics at 2 Hz |
| `summary.json` | End-of-episode metrics and inference stats |

## Models and keys

| Role | Default | Key file (first one found) |
|---|---|---|
| Fish policy | Jev `typesafe/jev-1.13` through OpenRouter's System One endpoint | `/workspace/.credentials/openrouter_api_key`, then `~/.credentials/openrouter_api_key` |
| Analyst, and the optional `chat` policy | OpenAI `gpt-6-astra` | `/workspace/.credentials/llm_api_key`, then `~/.credentials/llm_api_key`, `~/.credentials/astra_api_key` or `~/.credentials/openai_key` |

Keys are read from the file at call time. They are never logged, written to `runs/` or sent to the browser, and error
messages are redacted. You can override both paths on the launch screen.

Jev receives **one choice question per fish**. The `state` is that fish's observation JSON, and the `criteria` map each
candidate id to its description. Jev returns a distribution over the candidates. By default the fish samples it with
its own RNG; argmax is also available. The response's model version is recorded (for example `typesafe/jev-1.13-20260917`).

Measured on this setup, one live 64-fish, 120 s episode made about 12,800 Jev calls. Latency was p50 0.20 s and
p95 0.28 s, with 0 failures and about **$0.57 per episode**. 96% of applied decisions came from Jev; the rest were
fallbacks after stale or invalid results.

## Architecture

```
world.py       truth: fish arrays, predators, rocks, 60 Hz physics, contact solver, swept captures, spatial grid
sensors.py     per-fish local vision: range and 240° FOV, silhouette line-of-sight occlusion, noise,
               dropout, capacity limits, motion estimated from the fish's own sensor track
candidates.py  complete actions built from one observation (no scores, no recommendation)
policies.py    jev | chat | local_rule | local_react | random | fixed_school | replay (none can see the world)
controller.py  action + local frames -> desired heading and speed; visible-only separation and avoidance
engine.py      clock, scenarios, interactive and controlled execution, fallbacks, logs, predictions
metrics.py     evaluator-only metrics: survival, polarization, fragmentation (6 BL), recovery, indirect response
server.py      stdlib HTTP + Server-Sent Events; web/ is the vanilla-JS viewer
batch.py       headless matched comparison across seeds with 95% intervals
```

**Execution modes.** *Interactive*: physics keeps running while Jev thinks. Decision phases are staggered, each fish
has at most one request in flight, and a result is dropped if it is older than 0.5 s, superseded, or targets a
neighbour that is no longer visible. When an action expires the fish uses the local fallback, and the fallback fraction
is reported. *Controlled*: at every 0.5 s barrier the engine snapshots all fish, sends independent requests, and applies
all actions together, with a wall-clock deadline and a fallback on timeout. Physics pauses during inference, so this
mode is comparable across policies and exactly replayable.

**Escape cues** (`escape_cues`, on by default). Each visible neighbour is labelled `fast` or `sharp_turn` from the
fish's own motion estimates. Fast neighbours become FOLLOW options, and a `FLEE_WITH nX` action lets a fish burst
along a fleeing neighbour's heading. Without these cues Jev almost never joined a neighbour's escape. With them it
does, but false alarms spread too. See `docs/pilot_2026-09-30.md`.

**Scenarios:** first demo (flank attack, withdrawal at 80 s), flank, blind sector, rock blocks predator, two predators,
shortened vision, false alarm, predator withdrawal, and calm.

## Checks and comparisons

```bash
python3 tests/test_checks.py
python3 -m jevswarm.batch --policies local_rule local_react random fixed_school --seeds 10
python3 -m jevswarm.batch --policies jev local_rule --seeds 5      # calls Jev: about $0.6 per episode
python3 -m jevswarm.causal --policy jev --seeds 5                  # branch at the first local escape
```

`causal.py` runs the doc's propagation intervention. It runs a live controlled source episode until the first fish
applies ESCAPE (the witness), then replays that exact prefix twice. One branch permits the witness's action and the
other replaces it with CONTINUE for one interval; both share every random stream. Over the next 3 s it compares, among
fish that have never seen a predator, how many reached fast-swim speed or applied BURST, and the evaluator's indirect
responses.

`tests/test_checks.py` covers the doc's required checks. All of them pass:

- Hidden-state invariance: moving an unseen predator or fish leaves the observation bytes, the candidates and the controller output identical.
- Blind-sector and range limits.
- Occlusion by a rock and by another fish's body.
- Rotation and translation invariance.
- Motion estimates are unknown on the first sample, and tracks are dropped when an object is lost.
- FOLLOW stops tracking a target once it is hidden.
- Candidate eligibility and caps.
- Distribution normalization.
- Independent per-fish random streams.
- Stale and superseded results are rejected.
- Deterministic replay, including a manual intervention, reproduces the recorded run exactly.
- Only whitelisted local fields ever appear in a request.

## Limits of this starter

- Replay is exact only for runs recorded in **controlled** mode. Interactive runs depend on network timing.
- The analyst is a convenience for the viewer. Its answers are not measurements.
- Parameters are the doc's starting values. They have not been tuned and frozen yet, and the indirect-response
  metric is noisy because ordinary schooling turns also count as cues.
- The causal check does not yet trace observational visibility paths (who saw whom move), which the doc suggests alongside it.
