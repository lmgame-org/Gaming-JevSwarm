# The Irregulars (holmes)

A seeded, procedurally generated Sherlock Holmes case, solved either by **one detective** (Solo) or by a **swarm of
Baker Street Irregulars** (Swarm), where every agent picks its next move with Jev.

```
python3 run.py holmes            # from the repo root, then open http://127.0.0.1:8781
cd holmes && python3 -m irregulars --port 8781
```

## The case

- **London map**: ~100 addresses across ten districts (Marylebone, Soho, the City, Whitechapel, Southwark,
  Limehouse, ...), linked into a street graph. Travel is by cab along the streets.
- **Hidden truth**: one culprit among ~10 suspects, one motive among up to 6, one hideout among up to 8 candidate
  places. Suspects differ by six visible traits (height, handedness, hair, tobacco, boots, gait).
- **One lead per address**: trait sightings near the scene, alibis near suspects' homes, motive evidence near the
  victim's home, hideout clues near the hideout, pointers ("ask at ..."), red herrings that look suspicious but
  prove nothing, empty addresses, and lies. Every true key fact appears at `redundancy` addresses (default 2);
  each lie is a single copy that contradicts one key fact. Searching a candidate hideout shows whether it is
  occupied.
- **Reproducible**: everything comes from the seed. The launch screen previews the case and says whether it is
  solvable by counting all leads.

All lead text is original; the only borrowed names are public-domain characters (Holmes, Mrs Hudson, Lestrade,
Wiggins's Irregulars, the Professor).

## Solo mode

The detective starts at 221B Baker Street with the brief (victim, suspects with their traits, motives, candidate
hideouts) and Mrs Hudson's telegram. Each step it either visits one address (cab time + interview) or accuses.
It sees only the brief, the address directory with cab times, and its notebook of lead texts.

| Detective | How it decides | Cost |
|---|---|---|
| `jev` | One Jev System One call per step: a choice over reachable addresses, a yes/no "ready to accuse?" (it accuses once this reaches `jev_accuse_at`, default 0.4) and three choice questions (culprit, motive, hideout) that double as its live belief | ~$0.00025 per step |
| `chat` | The "genius": `gpt-6-astra` reads the case file, directory and notebook and returns a move plus its current answer. The static case file goes first so it is cached between steps | ~$0.018 per step at list price |
| `rule` | Follows pointers, works outward from where each open question's evidence should be, counts corroborating facts and accuses when all three answers lead by one uncontradicted lead (reads structured facts of leads it collected) | free |
| `random` | Random visits, random accusation | free |

Score: one point each for culprit, motive and hideout ("solved" = all three), plus visits, case minutes, tokens
and dollars.

## Swarm mode

~100 Irregulars start spread over the map. Each knows the brief, the leads at addresses it has stood on, what
others within shouting range told it, and the votes it hears nearby. Every tick each one decides
`MOVE_<neighbour>`, `SHARE_<lead>`, `TAIL_<suspect>` (only at a suspect's home; tailing the culprit may reveal the
hideout's district, tailing an innocent yields an alibi) or `WAIT`, and states its vote (culprit, motive,
hideout, each possibly UNSURE). The case closes when a **quorum** holds the identical full answer; if the clock
runs out it goes cold (the plurality answer is still logged).

| Policy | |
|---|---|
| `jev` | One Jev call per Irregular per tick (action choice + three votes). A call that fails or misses the per-call deadline falls back to the reflex rule for that tick |
| `rule` | Reflex rule: share the most useful unshared lead when someone can hear, tail a suspect still in the running, follow pointers, walk to unvisited neighbours; vote what its own leads establish, or a clear local majority its leads allow |
| `random` | Random actions and votes |

**Liar defence** (`corroboration = address`, on by default; `none` turns it off):

- each witness address counts once; if second-hand claims about one address disagree, that address counts for
  nothing;
- a claim that contradicts what an Irregular saw itself at that address marks the speaker as a liar: everything
  from that speaker is forgotten, and the Irregular can `REFUTE` it out loud (trusted hearers then distrust the
  liar too);
- a first-hand claim about an address farther (in streets) from the speaker than it could have walked since the
  start is rejected, and the speaker is distrusted;
- votes heard from known liars are ignored, and a vote from an Irregular caught by two or more others is struck
  from the quorum count.

Jev Irregulars get the same memory: rejected leads never reach them, contested leads are flagged, and they see the
list of Irregulars they have caught lying.

Cost control: with `skip_unchanged` (on by default) an Irregular whose view has not changed since it chose `WAIT`
waits again without a call. `batch --max-usd` stops starting new runs once a spend is reached.

Experimental knobs: swarm size, shouting range, messages taken in per tick (bandwidth), memory size, noisy memory
(forget rate), **lying Irregulars** (all push one wrong answer with made-up leads), misinformed Irregulars (start
with one false lead), stubborn Irregulars (never change their first firm vote), quorum share, clock, and a
**$ cap** for fairness (above it every Irregular uses the reflex rule; `batch --fair-to` sets it per seed to the
genius's Solo spend).

## The viewer

- **Launch screen**: presets, every knob, a live preview of the seeded map, model/key tests, cost estimate.
- **Live map**: districts, the Thames, streets, 221B, Scotland Yard, the scene, candidate hideouts and suspects'
  homes. Solo: the detective's cab route and visited addresses light up; hover an address for its lead. Swarm:
  each Irregular is a dot coloured by its culprit vote; shouts ripple out to the shouting range; click a dot to
  see exactly what that Irregular knows and did.
- **Notebook and belief** (Solo): every lead collected, and Jev's live probabilities over suspects, motives and
  hideouts. **Votes** (Swarm): leading full answers against the quorum line, culprit votes, and a time series.
- **Speculate**: lock in your own culprit/motive/hideout at any time; it is scored against the truth at the end.
- **Reveal truth**: spoiler toggle that colours true key leads, lies and pointers, marks the culprit and the
  true hideout, and rings the lying Irregulars.
- Pause, single step, speed, and live swarm knobs (range, bandwidth, forgetting, quorum), logged as
  interventions. The end banner shows the accusation against the truth.

## Batch comparisons

```
python3 -m irregulars.batch --mode solo  --policies jev chat rule random --seeds 5
python3 -m irregulars.batch --mode swarm --policies jev rule random --seeds 5
python3 -m irregulars.batch --mode swarm --policies rule --vary liar_frac=0,0.05,0.15 --seeds 20
python3 -m irregulars.batch --mode swarm --policies jev --fair-to runs/batch_<solo folder>
```

Each run writes `runs/<time>_<mode>_<policy>_s<seed>/` with `config.json` (no keys), `case.json` (map, brief,
truth, every lead), `decisions.jsonl`, `events.jsonl` and `summary.json`. Tests: `python3 tests/test_checks.py`.

## Models and keys

Same as the other sub-projects: Jev `typesafe/jev-1.13` through OpenRouter (`~/.credentials/openrouter_api_key`)
and OpenAI `gpt-6-astra` (`~/.credentials/llm_api_key`, `astra_api_key` or `openai_key`). OpenAI does not return
a cost, so chat calls are costed at the list price set on the launch screen ($10 / M input, $1 / M cached input,
$50 / M output by default, OpenRouter's published price for `gpt-6-astra`). Keys are read at call time and never
logged, written to run logs or sent to the browser.

Overview (background, design, results): [docs/the_irregulars_overview.md](docs/the_irregulars_overview.md).
Detailed results: [docs/pilot_2026-10-01.md](docs/pilot_2026-10-01.md).
