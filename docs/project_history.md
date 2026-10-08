# jev-swarm: project history (30 Sep to 4 Oct 2026)

**Update, 8 Oct 2026:** the repo was renamed **jev-swarm-games** (GitHub `snyhlx/jev-swarm-games`, local `~/worksapce/jev-swarm-games`). Every game now launches with `python3 run.py <game>` and shares one command line (`--preset`, `--set`, `--config`, `--list-params`, `--print-config`; `common/swarmcore/cli.py`) and one hyperparameter contract (`common/swarmcore/params.py`). Keys may also come from `$OPENROUTER_API_KEY` / `$OPENAI_API_KEY`. Older paths below are kept as written.

A compacted record of the whole project, written so a fresh thread can read only this file and keep refining the work
without asking Sonny anything again. The repo copy lives at `docs/project_history.md`; a copy is at
`~/Downloads/jev_swarm_history.md`. State as of commit `6593185` on `main` (4 Oct 2026).

## 1. What the project is

**Goal (Sonny's original brief, 30 Sep):** build a Jev-based swarm-behaviour study app following the design doc
`~/Downloads/Fish_Schooling_Design.docx`. At launch a meta-user picks hyperparameters and settings; the simulator runs
in real time and lets the user "speculate" while it runs. Push as a private GitHub repo named `jev-swarm`.

The idea grew into a family of studies with one shared question: **can many cheap, local Jev decisions add up to
good group behaviour, and how does that compare with one strong model reasoning alone?**

| Item | Value |
|---|---|
| Repo | `~/worksapce/jev-swarm` on Sonny's Mac (note the folder spelling `worksapce`), private remote https://github.com/snyhlx/jev-swarm, branch `main`. `gh` CLI is logged in. Work has always been committed and pushed straight to `main` (no PRs). |
| Old clone | `~/worksapce/jev-swarm-schooling` (branch `schooling-escape`) was the fish thread's temporary clone in the 30 Sep reorganisation. Its work is merged into `main`; treat it as stale. |
| Dependency | `python3 -m pip install numpy` (the only one). Servers are stdlib HTTP + Server-Sent Events, vanilla-JS viewers. |
| Launcher | `python3 run.py <fish\|honeybee\|holmes\|circuit\|list> [--port N]` from the repo root |
| Shared code | `common/swarmcore/` (`keys.py` key lookup, `llm.py` Jev and chat clients, `web.py` server helpers) |
| Run logs | each sub-project writes `<sub>/runs/<timestamp>_.../`; `runs/` is git-ignored |

### Models and credentials (never print, log or commit key values)

| Role | Model | Key file |
|---|---|---|
| Agent decisions everywhere | Jev `typesafe/jev-1.13` (TypeSafe's "System One" model) through OpenRouter; responses report e.g. `typesafe/jev-1.13-20260917` | `~/.credentials/openrouter_api_key` (code also checks `/workspace/.credentials/openrouter_api_key` first). Sonny asked to use the OpenRouter key labelled for Jev. |
| "Genius" / Holmes / analyst | OpenAI `gpt-6-astra` (Sonny's "gpt6 astra"; confirmed to exist on the key) | `~/.credentials/llm_api_key` (also checks `/workspace/.credentials/llm_api_key`, `astra_api_key`, `openai_key`) |

- The brief named `/workspace/.credentials/`, but the keys are actually in `~/.credentials/` on the Mac; the code looks in both.
- Keys are read at call time and never logged, written to `runs/` or sent to the browser; error messages are redacted.
- OpenAI returns no cost, so gpt-6-astra is costed at list price: $10/M input, $1/M cached input, $50/M output.
- Jev answers typed questions: a `choice` over candidate ids (with `state` = the agent's observation JSON and
  `criteria` = id to plain description) returns a distribution, which the agent samples with its own RNG (argmax optional).
  About 0.2 s and $0.00002-0.0003 per call when the endpoint is not contended.
- Sonny asked on 4 Oct: "we used gpt-6-astra, right?" Yes: run records confirm `gpt-6-astra` for every genius and
  Holmes, and Jev for every boy. (Sonny once wrote "Sol" for the genius; the on-screen label stayed "gpt-6-astra".)

### Way of working Sonny has shown

- Sonny drives by short messages in project threads; Claude works on the Mac over Remote Control in `~/worksapce`.
- Push everything to `main` with a clear commit message; write results up in `<sub>/docs/*.md` with the per-case CSV.
- Benchmarks: same seeds for every setting, Wilson 95% intervals, report cost, fallbacks and both clocks
  (simulated case time and wall-clock real time). Set a spend guard (`--max-usd`) and say the expected cost first.
- Run Jev-heavy batches one at a time with a 30 s per-decision deadline; a row only counts if fallbacks stay near 0%.
  (Runs that hit a contended endpoint and fell back to the heuristic were discarded and re-run.)
- Plain, consistent, self-explanatory interface wording; Sonny cares about how a demo reads to outsiders.
- Deliverables Sonny wants to keep (videos, figures) go to `~/Downloads`.

## 2. Fish schooling (`fish/`, package `jevswarm`)

**Launch:** `python3 run.py fish` then http://127.0.0.1:8777 (or `cd fish && python3 -m jevswarm`).

**Built (30 Sep):** 2D world, 60 Hz physics, predators and rocks; each fish sees only a 240° FOV with range,
line-of-sight occlusion, noise and capacity limits, and estimates motion from its own sensor track. Each fish asks Jev
one choice question per decision (CONTINUE, SCAN, ALIGN, FOLLOW nX, COHERE, RECOVER, ESCAPE, BURST, plus later
FLEE_WITH nX, ESCAPE_GROUP, ESCAPE_SELFISH). Policies: `jev | chat | local_rule | local_react | random | fixed_school |
local_coop | local_selfish | replay`.

- **Launch screen:** scenario presets and every hyperparameter, model tests, cost estimate.
- **Execution modes:** interactive (physics runs while Jev thinks; stale results dropped) and controlled (barrier
  every 0.5 s, exactly replayable).
- **Viewer:** pause/step/speed, live policy switch, a click-to-select fish with its exact vision sector and the JSON
  sent to Jev, interventions (place predator, rock, false alarm, withdraw, vision changes), play-money **bets** on
  outcomes (this is the "speculate" feature), a gpt-6-astra analyst, and inference health.
- **Later:** a fancier viewer (60 fps interpolation, animated fish and shark), escape cues, background social steering
  (Couzin zones from visible fish), cooperative and selfish escapes, a predator confusion effect.
- **Checks:** `cd fish && python3 tests/test_checks.py`, the design doc's 11+ checks (hidden-state invariance,
  occlusion, replay, whitelist and others), all passing.
- **Tools:** `python3 -m jevswarm.batch --policies jev local_rule --seeds 5` (about $0.6 per Jev episode) and
  `python3 -m jevswarm.causal --policy jev --seeds 5` (branch at the first escape).
- **Cost:** a 64-fish, 120 s live episode makes about 12,800 Jev calls, p50 0.20 s, about $0.57.

**Results** (`fish/docs/pilot_2026-09-30.md`, 5 matched seeds, demo scenario, untuned doc parameters):
- First pilot survival: Jev 0.65, local_rule **0.75**, local_react 0.65, random 0.53, fixed_school 0.47. Jev's
  failure mode was loss of cohesion (the largest group held 0.49 of the fish, and it never regrouped).
- Causal "permit vs suppress the first escape" check: no detectable propagation at n=5.
- Sonny noticed Jev fish didn't join visible escapes. **Escape cues** (motion labels, FLEE_WITH) lifted joining
  from 4% to 40%, but caused false-alarm amplification (30% bursts before any predator; energy 0.79 to 0.20).
- Sonny said schools fell apart too easily and wanted schooling plus cooperative and selfish escape to emerge locally.
  After social steering, Jev schools hold (largest group under attack 0.92), but survival fell to 0.55. The cause is
  FLEE_WITH contagion inside dense schools. In this predator model scattering still beats schooling.

**Open:**
- Parameters are not tuned or frozen.
- The pilots use 5 seeds only.
- The indirect-response metric is noisy.
- The causal check doesn't trace visibility paths.
- Replay is exact only in controlled mode.
- The predator is faster than a bursting fish, which favours scattering.
- The FLEE_WITH contagion needs a damping or false-alarm cost.

## 3. Honeybee nest-site selection (`honeybee/`, package `beeswarm`)

**Launch:** `python3 run.py honeybee` then http://127.0.0.1:8779.

**Sonny's request (30 Sep):**
- Make it a distinct sub-project, reorganising the repo into sub-projects (done: `fish/`, `common/`, root `run.py`).
- Give each scout the listed inputs (site quality estimate, distance, bees seen, dances observed, confidence, energy,
  time since inspection).
- Let Jev choose WAIT / EXPLORE / INSPECT_X / FOLLOW_DANCE_X / ADVERTISE_X / STOP_ADVERTISING.
- Expose misinformation, noisy, biased and stubborn scouts, bandwidth, group size, quality gap and confidence calibration.

**Built:**
- 100 scouts, 5 sites, a quorum of 15 scouts present at once, then piping and lift-off. One tick is one simulated minute.
- Dance circuits scale with the estimate and fade with repeat bouts. Site letters are shuffled per seed.
- 11 scenario presets. Live interventions: drag a site's quality, add a site, misinform, fake dances, make scouts stubborn.
- Bets on the winner, a gpt-6-astra analyst, and a scout inspector.
- Policies: `jev`, `chat`, `local_rule` (Seeley-style), `random` and `replay`.
- 12 offline checks: `cd honeybee && python3 tests/test_checks.py`. Batch runs with `python3 -m beeswarm.batch`.
- A default Jev run costs about $0.016-0.02 and takes about 30 s.

**Results** (`honeybee/docs/pilot_2026-09-30.md`, 5 seeds):
- Classic: Jev picked the best site 5/5, the local rule 5/5, random 3/5.
- With 15% misinformed scouts: Jev 3/5, the local rule 2/5, and both decided faster. The intervals overlap everywhere.
- Over 40 seeds the local rule picks the best site in 32/40 classic runs.

**Open:**
- Scale the pilot to 20+ seeds per cell on `close_call`, `misinformation` and `noisy_overconfident` (about $0.40 per 20 Jev runs).
- Stop signals are not modelled.
- The swarm is scaled down.

## 4. The Irregulars: Holmes detective game (`holmes/`, package `irregulars`)

**Launch:** `python3 run.py holmes` then http://127.0.0.1:8781.

**Origin (2 Oct):** Sonny asked for a popular detective game where Jev makes small local decisions that solve a big
problem. It was inspired by the Hao AI Lab *Ace Attorney* LLM benchmark. The question: **can 100 cheap AIs out-detect
one genius AI?** The case is original and procedurally generated; only public-domain Holmes names are borrowed.

**The case:** a seeded London map of about 100 addresses in 10 districts with a street graph and cab times. The hidden
truth is a culprit (from about 10 suspects with 6 visible traits), a motive and a hideout. Each address holds one lead:
a trait sighting, an alibi, motive evidence, a hideout clue, a pointer, a red herring, nothing, or a lie. True facts
appear at `redundancy` = 2 addresses. The answer is scored as culprit, motive and hideout; "solved" means all three.

- **Holmesian difficulty** (`difficulty = holmesian`): a frame-up by the culprit's bribed servants (two false copies
  against one true copy), a planted clue, witnesses to the bribe, timed alibis, and mud-and-dust traces decoded with
  Holmes's index. Counting names the framed suspect in all 20 seeds.
- **Challenge casebook** (`irregulars/challenges.py`): 10 fixed hard cases. The Frame-Up, The Liars' Chorus, The Single
  Thread, The Sprawling City, Before the Dawn Train, Moriarty's Boys, The London Particular, The Frame-Up in the Sprawl,
  The Frame-Up at Dawn and The Perfect Crime.

**Three families (as named on the launch screen):**
- **Solo detective:** `chat` (gpt-6-astra, the "lone genius", 20 visits), `jev`, `rule` (shown as "heuristic") and `random`.
- **The Baker Street Irregulars** (`baker_street`):
  - Holmes at 221B is gpt-6-astra or a counting heuristic.
  - Wiggins splits about 12 boys across errands and collects their reports at a forward post.
  - The boys are Jev or the heuristic. They make small local choices and never accuse.
- **Swarm Detectives:**
  - 100 Irregulars with a shouting range (1 or 2 km), bandwidth, memory, and liars, misinformed or stubborn boys.
  - The case closes when a quorum of 30 holds the identical full answer.
  - Policies: `jev`, `rule`, `random` and `hybrid` (Jev acts, exact counting votes). `hybrid_genius` is still in the
    code but was removed from the menu.
  - A liar defence is on by default: each address counts once, first-hand contradictions mark a liar, and claims the
    speaker could not have walked to are rejected.
- **One 12-case-hour clock** applies to every approach (decided 3 Oct).

**Viewer and launch screen:**
- The launch screen has step 1 "The Investigator(s)" (three tracks) and step 2 "The Mystery Case", with tabs Standard,
  Holmesian and Challenge casebook. It shows the cost only.
- Sonny's decisions, all committed:
  - remove the tested-setup dropdown;
  - remove benchmark solve counts from the launch screen;
  - call the rule baselines "heuristics";
  - drop "Hybrid + genius at the Yard" from the menu;
  - use plain-English event logs and captions with names instead of ids;
  - always show a New case button and a Show result button.
- The live map is an Ordnance-Survey style with light and dark themes. Press **P** for presentation mode, **R** to
  reveal the truth and **Space** to pause; there is also a legend with matching icons and a "Speculate" lock-in.

**Batch:**
- Solo and swarm runs: `cd holmes && python3 -m irregulars.batch --mode solo|swarm --policies ... --seeds N`
  (`--set k=v`, `--vary`, `--max-usd`, `--fair-to`).
- The challenge casebook: `python3 -m irregulars.challenges`.
- Checks: `python3 tests/test_checks.py`.
- Baker Street and swarm runs save `track.jsonl` positions for replay.

### Results (all in `holmes/docs/`)

**100 standard cases** (`benchmark_100cases_2026-10-04.md`, seeds 1-100, 0 fallbacks, $107.66). This is the headline.

| Setting | Solved /100 | Culprit / motive / hideout | Sim time p50 | Real time p50 | Cost/case |
|---|---|---|---|---|---|
| Solo gpt-6-astra | 57 | 83/68/100 | 10.5 h | 82 s | $0.339 |
| Solo Jev | 25 | 46/56/95 | 11.8 h | 4.5 s | $0.005 |
| Solo heuristic | 61 | 81/79/98 | 9.0 h | 0 s | free |
| Baker Street, gpt-6-astra Holmes + Jev boys | **96** | 99/97/100 | 11.0 h | 97 s | $0.582 |
| Baker Street, counting Holmes + Jev boys | 95 | | 7.8 h | 4.9 s | $0.002 |
| Baker Street, counting Holmes + heuristic boys | 97 | | 8.8 h | 0 s | free |
| Jev swarm, 2 km | 38 (agreed in 91, **53 wrong**) | 50/72/91 | 2.2 h | 8.9 s | $0.149 |
| Heuristic swarm, 2 km | 95 | | 1.5 h | 0.1 s | free |
| Random (solo or swarm) | 0 | | | | free |

The hybrid swarm was not run at 100 cases (it would have added about $28).

**20 standard cases** on the 12 h clock (`benchmark_20seeds_12h_2026-10-03.md`):
- Baker Street solved 19/20 with any Holmes.
- The heuristic swarm solved 18/20 at 2 km and the hybrid 16/20 at 2 km.
- Solo gpt-6-astra solved 11/20; Sonny doubted this, it was re-checked twice and holds. Cases 1-6 are easy, which is
  why the 5-case pilot showed 5/5.
- The Jev swarm solved 11/20 at 2 km and 2/20 at 1 km.
- Extra time beyond 8 h changed little.

**20 Holmesian cases** (`benchmark_holmesian_20seeds_2026-10-04.md`, run 2 clean):
- gpt-6-astra Holmes + Jev boys solved 17/20 and solo gpt-6-astra 11/20 (culprit right 20/20, the motive is the miss).
- The Jev swarm solved 9/20.
- Every counting approach and the hybrid solved 0/20: they name the framed suspect.
- The ranking flips with the case type: reasoning beats counting on a planned crime.

**Challenge casebook** (`challenge_casebook_2026-10-04.md`, one run per case, $13.10):
- gpt-6-astra Holmes solved 6/10, solo gpt-6-astra 5/10, and counting Holmes + Jev boys and the heuristic swarm 4/10 each.
- Each approach owns one case and breaks on another:
  - coverage leads to Baker Street;
  - speed and scale lead to swarms;
  - bribed boys break every swarm;
  - frame-ups need gpt-6-astra.
- Nobody solved The Frame-Up at Dawn.

**Earlier docs:** `pilot_2026-10-01.md` (5-case pilot, liar defence), `benchmark_20seeds_2026-10-02.md` (first 20-case
benchmark on mixed clocks), and `the_irregulars_overview.md` (background, design, conclusions as of 2 Oct; a copy is
in `~/Downloads`).

**Caveats:**
- Jev rows on 2-3 Oct ran on a contended OpenRouter endpoint. Their real time is not comparable, and the 8 s-deadline
  attempts were discarded.
- The rule baselines read structured facts, while the models read text.
- Jev varies run to run on the same seed.
- The liar model is simple.
- Challenge cells are single runs.

**Main findings:**
1. A leader with helpers (scatter and gather) wins with any kind of leader.
2. Jev is good at single-step judgements and weak at multi-clue elimination and at knowing when it is done.
3. Swarm success is mostly plumbing: range, and telling independent evidence from repetition.
4. Vote-counting swarms are what liars capture.
5. A Jev swarm converges fast but often on the wrong answer.

### Trailer (`holmes/trailer/`)

**Current cut:** 80 s, `holmes/trailer/the_irregulars_trailer.mp4`, also at `~/Downloads/the_irregulars_trailer.mp4`.

- **Build:** `trailer.html` is a scripted canvas page; `make_data.py` builds `trailer_data.json` and `casebook_100.json`
  from the real runs; `render.py` renders frame by frame (`python3 trailer/render.py [--fps 30] [--only a,b] [--jobs 8]`);
  `sound.py` synthesises the soundtrack; ffmpeg joins them.
- **Assets** (`holmes/trailer/assets/` and `~/Downloads`): `irregulars_clip1_lone_genius.mp4`,
  `irregulars_clip2_holmes_and_the_irregulars.mp4` and `irregulars_clip3_swarm.mp4` (14.5 s each), plus
  `irregulars_results_table.png` (100 cases: Lone Genius 57 / 10.5 h / 82 s; Holmes & the Irregulars 96 / 11.0 h /
  97 s; Swarm 38 / 2.2 h / 9 s).
- **Structure:**
  - The opening is a lit Baker Street at night with rain, running boys and the gas lamp.
  - Holmes's Irregulars line (*The Sign of the Four*) is followed by Minsky's quote (*The Society of Mind*, 1986):
    "The power of intelligence stems from our vast diversity, not from any single, perfect principle."
  - Then the experiment card: "So we sent AI to Baker Street. A hundred murder mysteries. Two kinds of AI detective:
    gpt-6-astra, a large language model that reasons; and Jev, a small, fast model for quick, simple choices."
    It ends on "Which one cracks the most cases?"
  - Three chapters replay **case 9** from the 100-case benchmark with the models' own notes, clue cards and both clocks:
    - the Lone Genius ends UNSOLVED at 11h 23m with the wrong culprit;
    - Holmes & the Irregulars ends SOLVED at 7h 45m;
    - the Swarm converges at 1h 30m on the wrong man and ends UNSOLVED. The Swarm chapter switches from a "The streets"
      tab to a "The votes" tab, an animated agreement chart against the 30-vote line.
  - The close is an animated casebook with bars counting up to 57 / 96 / 38 out of 100.
- **Sonny's trailer decisions, in order:**
  - Holmes styling.
  - The three-way comparison.
  - A case clock counting up from 0h 00m against the 12 h limit.
  - Show the swarm converging.
  - No frame-up content in the trailer (standard cases only).
  - Tie the opening to swarm intelligence, with a famous AI quote (Minsky).
  - Label the models on screen (gpt-6-astra genius, Jev boys) and use real model footage, not heuristic footage.
  - Hold the SOLVED verdicts longer.
  - Show both simulated and wall-clock time.
  - Scale to 100 cases, with an example where gpt-6-astra fails and the swarm converges wrong.
  - Make the case-cracking more vivid.
  - "Just keep the correct counts", with no extra on-screen line about wrong agreements.
  - Aim for 80 s with less text, slower pacing, only "SOLVED"/"UNSOLVED", swarm convergence on another tab, and
    animated key-number plots.

**Results artifacts** (claude.ai, private): "The Irregulars Results" https://claude.ai/code/artifact/c6e1d960-8730-40ca-ac8b-4a38ef0beeca
and "The Irregulars trailer plot" https://claude.ai/code/artifact/3df08ccb-5d1e-4012-ac02-fe044fbdd41d.

**Open (Holmes):**
- Sonny has not yet given feedback on the 80 s trailer and clips.
- Ideas offered but not done:
  - The hybrid swarm on 100 cases (about $28).
  - Fixes for wrong swarm agreement: a quorum of 50, votes only from boys holding their own evidence, or dedicated
    double-checkers.
  - Swarm convergence colouring in the app's own view (it is only in the trailer).
  - A decomposed culprit question for Jev (one yes/no per suspect).
  - Telling gpt-6-astra Holmes to commit earlier.
  - Smarter, plausible liars.
  - Fairness runs with `--fair-to`.
  - Holmesian cases at 100 seeds.

## 5. Circuit debugging (`circuit/`, package `cpudebug`)

**Launch:** `python3 run.py circuit` then http://127.0.0.1:8783. Batch commands need `PYTHONPATH=.:../common` from `circuit/`.

**Origin (2 Oct):** Sonny asked for architecture and circuit design with scatter-and-gather debugging. It mirrors the
Holmes families.

- **The CPU:** a pure-Python netlist of a 96-block, 5-stage pipelined CPU with 8-bit data, 16-bit instructions,
  8 registers, 64 bytes of memory, forwarding, a load-use stall and branches resolved in EX.
- **ISA and tests:** an assembler, a golden interpreter and 9 test programs.
- **Bugs:** one bug is injected into a combinational block per seed: stuck-at, swapped mux, wrong forwarding or
  hazard path, or off-by-one.
- **Probes:** `check(block, cycle)`, `drive(block, kind)`, and `read(net)` (solo genius only, now charged).
- **Hardened defaults** (one button restores the easy original):
  - failure info is final state only, and investigators get the longest failing waveform;
  - a check window of 2 cycles and 5% glitch noise;
  - 40% of bugs are rare-trigger and 20% of cases have a double bug;
  - 10% coordinated liars, with the liar defence on;
  - a 6 h clock (24 ticks of 15 minutes) and a $0.75 cap per case;
  - solo gets 10 probes.
- **Families:**
  - **Solo:** chat (gpt-6-astra), jev, rule (cone tracing) and random.
  - **Baker Street:** Holmes is gpt-6-astra or counting, Wiggins is on or off, and 12 boys are Jev, rule or random.
  - **Swarm:** 100 Irregulars with a quorum of 30, a radio range of 2 or 4 wires, and policies rule, jev, hybrid or random.
- **Files:** `isa.py`, `netlist.py`, `case.py`, `kb.py`, `solo.py`, `leader.py`, `swarm.py`, `engine.py`, `server.py`,
  `batch.py` and `report.py`. Run `tests/test_checks.py` for the offline checks.

**Results:**
- **Easy pilot** (`circuit/docs/pilot_2026-10-03.md`, 5 bugs, $0.30): everyone scored 4-5/5. The genius was helped by
  free waveform reads. This led to the hardening.
- **Hardened 20-seed benchmark** (`circuit/docs/benchmark_20seeds_2026-10-03.md` and `.csv`, $9.31). Sonny asked to
  put solo on the same table as Baker Street.

| Setting | Solved /20 | Cost/case |
|---|---|---|
| Solo gpt-6-astra | **14** (block right 18) | $0.171 |
| Solo Jev / rule / random | 3 / 3 / 2 | $0.0004 / free / free |
| Baker Street, gpt-6-astra Holmes + Jev boys / rule boys | 11 / 12 | $0.143 / $0.137 |
| Baker Street, counting Holmes + Jev boys (no Wiggins) | 11 (8) | $0.0027 |
| Baker Street, counting Holmes + rule boys (no Wiggins) | 13 (12) | free |
| Baker Street, counting Holmes + random boys | 9 | free |
| Swarm rule, 2 / 4 wires | 6 / 3 | free |
| Swarm Jev / hybrid / random, 2 wires | 3 (13 wrong quorums, all on the frame-up) / 5 / 0 | $0.004 / $0.005 / free |

**Reading:**
- Circuit reverses the detective game.
  - With gpt-6-astra, solo wins: it commits early (median 1.2 h), while as Holmes it waits to the deadline.
  - Without a frontier model, the squad wins.
- Two-bug cases were fixed only once (gpt-6-astra Holmes). A practical ceiling is about 17/20.
- Sonny asked why the solve rate dropped from Holmes's 19/20 to 11-13. The circuit has no solvability guarantee, it
  includes two-bug cases, finding the block is not the same as naming the fix, and it has a shorter clock and more
  liars. No ablation isolates these causes yet.
- Claude recommended keeping the difficulty. A separate "brutal" preset was proposed and not built.
- Jev rows on 3 Oct ran on a contended endpoint (2-4% fallbacks; real time not comparable).

**Open (circuit). Pending request from Sonny (4 Oct 21:48), not started:** the circuit thread hit the weekly
usage limit and is set to auto-resume around 7 Oct 05:00 UTC. Nothing for it is in the repo yet.
1. Write `circuit/docs/problem_setup.md`, covering:
   - the CPU and its block kinds and wiring, the tests and the bug generation (with examples);
   - what an investigator sees, what a probe returns and costs, grading, and every hardening knob.
   Then answer honestly with evidence whether the problem is really divide-and-conquer solvable:
   - Is a block check local, or does it need upstream context?
   - How much of the search is sequential back-tracing and how much is parallel?
   - Measure an ideal-parallel oracle (probe all 96 blocks at once) and how many rounds a perfect back-tracer needs.
   - If it is not D&C-friendly, say so and propose changes.
2. Rerun the hardened benchmark on **100 seeds** for every setting (solo 4, Baker Street 7, swarm 5):
   - expect about $45-50 with the spend guard at $60, and reuse seeds 1-20 if their rows are identical;
   - run the cheap rows first and report Wilson CIs;
   - write `circuit/docs/benchmark_100seeds_<date>.md` plus the CSV, push to main, and report the table, findings,
     cost and commit. Don't touch `holmes/`.

Other circuit ideas:
- probe budgets of 20, 40 and 80;
- let Jev request a confirming drive before naming a fix;
- run the Jev and hybrid swarms at 4 wires;
- the "brutal" preset.

## 6. Side discussion: "calculations history" thread (2-3 Oct)

Sonny asked whether early hand-computed nuclear-weapon calculations were divide and conquer. On Sonny's request the
answer was kept to the mathematics only, with no nationality element.

- Spherical implosion hydrodynamics parallelises in space (concentric shells, each needing only its neighbours) but
  not in time (CFL-limited steps, a global sync each step).
- Shocks needed artificial viscosity.
- Errors were caught by redundancy (independent teams), conserved-quantity invariants and bounding arguments.
- Mapped onto this project: the shells are the Irregulars, the per-step sync is Wiggins, the invariant checks are the
  liar defence, and the bounds are Holmes's deductions.

This motivates the circuit "is it really divide and conquer?" question above. No code came from it.

## 7. Timeline of commits (main)

| Date | Milestone (commit) |
|---|---|
| 30 Sep | Fish simulator (a9cbc16), causal check and pilot (99a9c6e), escape cues (cd2f8bb), fancier viewer (6a72cbb), repo reorganised into sub-projects (a5d921e), honeybee (0890444, 8644ac1), schooling and escape strategies (322d3bc, d282b77, 476e2a1) |
| 1-2 Oct | Holmes game and pilot (f34921f), liar defence (b0b0e50), overview (7ef89c7), hybrid (576cbf9), Baker Street (20c90d3), 20-case benchmark (1e11a21), viewer redesign and launch-screen wording (795c36f to 6bcb303) |
| 3 Oct | 12 h clock for all (67b86f5, c980691), Holmesian cases (ecd3081), circuit sub-project (73fc05a), hardened circuit (ea87593), circuit Baker Street rows and solo table (b761aad, eecf317), Holmesian benchmark (4980be9) |
| 4 Oct | Trailer v1 to v3 (3a091ff to 6593185), challenge casebook (dfea211), 100-case benchmark (f3f8b31), 80 s trailer and assets (6593185) |

The larger spends recorded in the docs:
- Holmes: the 100-case run $107.66, the Holmesian runs about $58 (including the discarded run 1 and a wasted attempt),
  the 12 h swarm re-runs about $22 and the challenges $13.10. The 2 Oct benchmark spend isn't totalled in the docs.
- Circuit: $9.31 for the benchmark plus $0.30 for the pilot.
- Fish: about $6.3 for the pilots.
- Honeybee: under $0.20.

Holmes alone is over $200.

## 8. Open threads a new thread could pick up

1. **Circuit, problem setup and the divide-and-conquer analysis** (`circuit/docs/problem_setup.md`, with the
   oracle and back-tracer measurements). This is Sonny's pending ask, queued in the circuit thread.
2. **Circuit 100-seed benchmark** for all 16 settings (about $45-50, guard $60). This is Sonny's pending ask too.
3. **Trailer feedback loop:** Sonny hasn't reacted to the 80 s cut, the three clips and the results figure yet.
4. **Holmes, fixing wrong swarm agreement:** a quorum of 50, own-evidence-only votes and double-checker boys,
   compared on the 100 standard cases (heuristic variants are free; Jev about $15).
5. **Holmes, the hybrid swarm at 100 cases (about $28) and Holmesian cases at 100 seeds** (about $280 at current per-case costs).
6. **Holmes, a better Jev culprit question** (one yes/no per suspect) and an earlier-committing gpt-6-astra Holmes.
7. **Fish:** tune and freeze parameters, damp FLEE_WITH contagion, run more seeds, and add visibility-path tracing to the causal check.
8. **Honeybee:** 20+ seed Jev runs on the hard scenarios, and stop signals.
9. **Hygiene:** delete the stale `~/worksapce/jev-swarm-schooling` clone once Sonny agrees. The repo has no
   CI; run each `tests/test_checks.py` before pushing.
