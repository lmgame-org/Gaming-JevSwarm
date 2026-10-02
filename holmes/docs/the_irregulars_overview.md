# The Irregulars: background, design and results

*jev-swarm / holmes, as of 2 October 2026*

## 1. Background

jev-swarm studies collective behaviour where **every agent picks its next action with Jev**, TypeSafe's "System
One" decision model. Jev answers typed questions (a yes/no probability, a choice among options) about a JSON
state. It is fast (about 0.2 s a call) and very cheap (about $0.0001-0.0003 a call), but it reasons in one step
rather than at length. The two earlier studies, fish schooling and honeybee nest-site selection, asked whether
many cheap, local Jev decisions add up to good group behaviour.

The immediate inspiration was the Hao AI Lab's benchmark that had frontier models play *Ace Attorney*, which
drew wide attention as a test of whether LLMs can reason through evidence and spot contradictions. That raised a
swarm version of the question: **can 100 cheap AIs out-detect one genius AI?** The Irregulars asks exactly that
on an original, procedurally generated case (no game assets or text are reused). A detective case suits this
because:

- the answer is unambiguous and scored exactly (culprit, motive, hideout);
- evidence is scattered, so a swarm can cover ground one detective cannot, but each clue is weak alone and must
  be combined;
- lies and red herrings let us stress-test both a lone reasoner and a group;
- in the Holmes stories, Holmes relies on the Baker Street Irregulars, street children who are everywhere and
  notice everything. That is a natural swarm.

Three questions:

1. **Solo:** given the same case and the same visit budget, how do Jev, `gpt-6-astra` (the genius), a rule
   baseline and random compare on accuracy, visits and cost?
2. **Swarm:** can 100 Jev Irregulars that each see only their own corner of London reach a correct consensus
   (a quorum) before the clock runs out, and at what cost?
3. **Robustness:** what do limited communication, lying and misinformed agents, stubbornness and noisy memory do
   to the swarm, and can a simple defence protect it?

## 2. Design

### 2.1 The case generator

Every case comes from a seed, so the same settings give the same case and every detective faces identical
evidence.

- **Map:** about 100 addresses across ten London districts (Kensington, Marylebone, Bloomsbury, Soho, Covent
  Garden, Westminster, the City, Whitechapel, Southwark, Limehouse). The Thames splits Southwark from the rest.
  Each address links to its nearest neighbours to form a connected street graph; travel is by cab along the
  streets.
- **Cast:** a victim; about 10 suspects, each with six visible traits (height, handedness, hair, tobacco, boots,
  gait) and a home address; up to 6 possible motives; up to 8 candidate hideouts, each with a district and a
  place type.
- **Hidden truth:** one culprit, one motive, one hideout.
- **Which facts identify the culprit:** trait dimensions are added until three or fewer suspects remain
  consistent, then an alibi is generated for each remaining innocent. Motive and hideout each get their own key
  facts (the hideout gets a district and a place type).
- **One lead per address,** placed where it belongs:

| Lead kind | Example | Placed |
|---|---|---|
| Trait sighting | "Fresh prints in the mud: the culprit wears large, heavy boots." | near the scene |
| Alibi | "The register shows X signed in at ten and the night porter saw no one leave." | at or near the suspect's home |
| Motive | "Half-burnt in the grate: a draft of a new will cutting someone out." | near the victim's home |
| Hideout clue | "A boatman rowed a silent passenger toward Limehouse." / "...candles 'for a cellar'." | near the hideout |
| Hideout search | "Lived in very recently: a cot, cold tea, a bloodied cuff." / "Undisturbed dust." | at each candidate hideout |
| Pointer | "Ask at 17 Wardour Street; they saw more than they let on." | near the scene, Scotland Yard, 221B |
| Red herring | "X bought arsenic here; the chemist confirms it is for the rats." | filler |
| Empty | "Nobody here saw anything; the fog was too thick." | filler |
| Lie | a single copy that contradicts one key fact | anywhere |

- **Redundancy and lies:** every true key fact appears at 2 addresses; each lie is a single copy and never
  outnumbers the truth. The generator checks that counting all leads recovers the truth; all 30 default seeds
  tested pass.
- **Originality:** all text is new. The only borrowed names are public-domain Holmes characters (Holmes, Mrs
  Hudson, Lestrade, Wiggins's Irregulars, the Professor).

### 2.2 Solo mode

The detective starts at 221B Baker Street with the brief and Mrs Hudson's telegram. Each step it either visits
an address (cab time plus a 20-minute interview) or accuses. Default limits are 20 visits and 12 case hours. It
sees the brief, the address directory with cab times, and its notebook of lead texts, never the structured facts
or which leads are lies.

| Detective | Decision per step |
|---|---|
| **Jev** | One call with four typed questions: which address to visit (a choice among up to 100), "ready to accuse?" (yes/no; it accuses once this reaches a threshold), and culprit / motive / hideout choices that double as its live belief |
| **gpt-6-astra** | Reads the brief, directory and notebook and returns a move plus its current best answer. The static case file is sent first so the provider can cache it |
| **Rule** | Follows pointers, works outward from where each open question's evidence should be, counts corroborating facts, and accuses when all three answers lead by at least one uncontradicted lead. It reads the structured facts of leads it has collected, so it never misreads one |
| **Random** | Random visits and a random accusation |

Scoring: one point each for culprit, motive and hideout ("solved" = all three), plus visits, case minutes,
tokens and dollars.

### 2.3 Swarm mode

100 Irregulars start on distinct addresses. Each knows the brief, the leads at addresses it has stood on, what
others within shouting range (default 1 km) told it, and the votes it hears nearby. Every tick (15 case minutes)
each one:

- picks an action: `MOVE` to a neighbouring address, `SHARE` a lead with everyone in range, `TAIL` a suspect
  (only at the suspect's home; tailing the culprit may reveal the hideout's district, tailing an innocent gives
  an alibi), `REFUTE` a liar (see 2.4) or `WAIT`;
- states its current vote for culprit, motive and hideout, each possibly UNSURE.

The case closes when a **quorum** (default 30 of 100) holds the identical full answer; after 32 ticks it goes
cold. Each Irregular takes in at most 3 messages a tick and remembers 16 leads.

- **Jev Irregulars:** one call per Irregular per tick (the action plus three votes). A call that fails or misses
  the per-call deadline falls back to the reflex rule for that tick. In both pilots there were no fallbacks.
- **Reflex rule:** share the most useful unshared lead when someone can hear, tail a suspect still in the
  running, follow pointers, walk to unvisited neighbours; vote what its own leads establish, or a clear local
  majority that its own leads allow.
- **Random:** random actions and votes.

Adversaries and imperfections, each a knob:

| Knob | Behaviour |
|---|---|
| Lying Irregulars | All push one wrong answer (an innocent suspect, a wrong motive and hideout) with made-up sightings and vote for it |
| Misinformed | Start out holding one false lead |
| Stubborn | Never change their first firm vote |
| Noisy memory | Forget a random lead with some probability each tick |
| Range / bandwidth / memory | Who hears a shout, how many messages are taken in, how many leads are kept |
| $ cap | Above it, every Irregular uses the reflex rule (fairness against the genius's spend) |

### 2.4 The liar defence (added in the follow-up, on by default)

1. **Each witness address counts once.** Conflicting second-hand claims about one address cancel out.
2. **First-hand contradiction.** If a claim contradicts what an Irregular saw itself at that address, the speaker
   is marked a liar and everything from them is forgotten. The Irregular can then `REFUTE` it out loud, and
   trusted hearers distrust the liar too.
3. **Plausibility.** An Irregular walks at most one street per tick, and hearers can see where a speaker stands.
   A first-hand claim about an address farther away than the speaker could have walked since the start is
   rejected, and the speaker is distrusted.
4. **Quorum hygiene.** Votes heard from known liars are ignored, and an Irregular caught by two or more others has
   its vote struck from the count.

Jev Irregulars share the same memory: rejected leads never reach them, contested leads are flagged, and they see
whom they have caught lying.

### 2.5 The live viewer and tooling

- **Launch screen:** presets, every knob, a live preview of the seeded map with a solvability check, model and
  key tests, and a cost estimate.
- **Live map:** districts, the Thames, the street graph, 221B, Scotland Yard, the scene, candidate hideouts and
  suspects' homes. Solo shows the cab route and lights up visited addresses; Swarm shows each Irregular as a dot
  coloured by its vote, with shouts rippling out to the shouting range.
- **Panels:** Solo has the notebook and live belief bars. Swarm has the vote tally against the quorum line, a time
  series, and a click-through to any Irregular's exact knowledge and last decision.
- **Speculate:** lock in your own culprit, motive and hideout; it is scored at the end. A spoiler toggle
  reveals true leads, lies, the culprit and the liars. Pause, step, speed and live swarm knobs are logged as
  interventions.
- **Batch runner:** matched seeds, sweeps, Wilson intervals, a fairness cap per seed and a spend guard. Every run
  logs its config (without keys), the full case with the truth, every decision and event, and a summary.
- **Models and keys:** Jev `typesafe/jev-1.13` through OpenRouter and OpenAI `gpt-6-astra`, read from
  `~/.credentials` as in the other sub-projects. Keys are never logged or sent to the browser.
- **Tests:** 15 offline checks (reproducibility, connectivity, solvability, information boundaries, budgets,
  quorum, liars, stubbornness, the defence, no keys in logs).

## 3. Results

All numbers use the same five seeded cases (seeds 1-5) unless noted. With five seeds most differences are
within noise; the 95% intervals overlap widely.

### 3.1 Solo: one detective

| Detective | Solved | Culprit / motive / hideout right | Visits | Accused before running out | Cost per case | Latency per step |
|---|---|---|---|---|---|---|
| **gpt-6-astra** | **5/5** | 5 / 5 / 5 | 17.8 | 3 of 5 | $0.34 | 4.5 s |
| Jev (threshold 0.6) | 2/5 | 2 / 5 / 5 | 18.8 | 0 of 5 | $0.005 | 0.24 s |
| Jev (threshold 0.4) | 1/5 | 2 / 5 / 4 | 19.2 | 0 of 5 | $0.005 | 0.24 s |
| Rule | 2/5 (9/20 over 20 seeds) | 2 / 5 / 5 | 20.0 | 0 of 5 | free | - |
| Random | 0/5 (0/20) | 0 / 4 / 0 | 15.4 | - | free | - |

- gpt-6-astra solved every case and usually knew when to stop. Its notes are real deductions ("two independent
  cigar traces and two dark-haired samples identify Henry Pargeter").
- Jev always got the motive and nearly always the hideout, but the culprit only 2 times in 5. Naming the culprit
  means intersecting several trait clues with ten suspect descriptions and discounting a lie, which is
  multi-step reasoning.
- Jev never accused on its own: its "ready" answer peaked between 0.11 and 0.42, so lowering the threshold from
  0.6 to 0.4 changed nothing.

### 3.2 Swarm: 100 Irregulars, 1 km range, quorum 30

| Policy | Solved | Quorum reached | Ticks | Final majority, parts right | Cost per case |
|---|---|---|---|---|---|
| Jev (first pilot) | 2/5 | 4/5 (2 wrong culprit) | 22.0 | 2.2 | $0.27 |
| Jev (with defence and call skipping) | 1/5 | 2/5 (1 wrong) | 26.0 | 2.0 | $0.19 |
| Reflex rule | 3/5 (13/20 over 20 seeds) | 3/5 (never wrong) | 20.0 | 2.6 | free |
| Random | 0/5 | 0/5 | 32 | 0.2 | free |

At **2 km range** the Jev swarm solved 2/5 and always reached a quorum within about 10 ticks, but 3 of those 5
had the wrong culprit (cost $0.14 per case). The reflex rule solved 4/5 (18/20 over 20 seeds).

Behaviour: Jev Irregulars almost never walk (0.6% of actions); they split between shouting leads (49%) and
waiting (50%). They commit to a wrong consensus more readily than the rule, which stays undecided when unsure.

### 3.3 Robustness: communication, liars, misinformation (reflex rule, 20 seeds, free)

| Setting | No defence | With defence |
|---|---|---|
| Honest, 0.5 km range | 1/20 | - |
| Honest, 1 km | 13/20 | 13/20 |
| Honest, 2 km | 18/20 | 18/20 |
| 5% lying Irregulars, 1 km | 2/20 | **10/20** |
| 15% lying Irregulars, 1 km | 0/20 (20 wrong quorums) | **6/20** |
| 20% misinformed, 1 km | 0/20 | **9/20** |
| 15% liars, 2 km | 0/20 | **12/20** |
| 10% misinformed + 20% stubborn | 4/20 | - |

- **Communication range dominates.** At 0.5 km the facts never meet; at 2 km the rule swarm is nearly perfect.
- **Coordinated liars capture vote-counting swarms.** Without a defence, five liars in 100 were enough to
  produce wrong quorums. Relayed leads look independent, so counting corroboration rewards repetition.
- **The defence restores much of the accuracy at no cost to honest cases.** Most of the gain comes from the
  plausibility check: fakes claim addresses the liar never walked past, so they are rejected at the first hop.
  The first version, without that check, caught liars, but too slowly.
- **Jev swarm with 15% liars (5 seeds):** 0/5 solved with or without the defence. With it, the final majority
  answer was less wrong: 1.6 of 3 parts right instead of 0.4.

### 3.4 Genius vs swarm at similar spend

| | Cost per case | Solved |
|---|---|---|
| One gpt-6-astra detective | $0.34 | 5/5 |
| 100 Jev Irregulars, 1 km | $0.19-0.27 | 1-2/5 |
| 100 Jev Irregulars, 2 km | $0.14 | 2/5 |
| One Jev detective | $0.005 | 1-2/5 |
| Reflex-rule swarm, 2 km | free | 4/5 (18/20) |

On this task and at this budget, **one strong reasoner clearly beats a hundred cheap ones.** The swarm's
advantage, coverage, is real (it sees every address at once), but each Irregular must still combine clues, and
that is where Jev falls short. The rule swarm, which combines clues exactly, shows coverage plus correct local
combination works well; the bottleneck is local reasoning quality, not the swarm structure.

### 3.5 Spend

| Round | Spend |
|---|---|
| Building and testing | about $0.45 |
| First pilot (Solo: Jev, gpt-6-astra; Swarm: Jev honest and with liars) | $4.04 |
| Follow-up (Jev Solo; Jev swarm: honest, liars, 2 km) | $2.50 |
| **Total** | **about $7.00** |

gpt-6-astra is costed from token counts at OpenRouter's list price ($10 per million input tokens, $1 cached, $50
output), because OpenAI's API does not return a cost. Jev costs are as reported by OpenRouter.

## 4. Conclusions

1. **A single strong model wins the head-to-head:** gpt-6-astra solved 5/5 for $0.34 a case. Neither one Jev
   detective nor a hundred Jev Irregulars came close (1-2/5).
2. **Jev is good at single-step judgements** (motive, hideout, which lead to follow) and weak at multi-clue
   elimination (the culprit). It also lacks a usable sense of when it is done.
3. **Swarm success is mostly about the plumbing:** communication range, and whether the group can tell
   independent evidence from repetition. With good plumbing, even a simple rule swarm solves 18/20.
4. **Coordinated lying is the main threat to a vote-counting swarm,** and simple, local, physically grounded
   checks (where could this speaker have been?) recover much of the loss.

## 5. Limitations

- Five seeds per Jev / gpt-6-astra cell; most intervals overlap. The robust findings are those backed by the
  20-seed rule sweeps and by gpt-6-astra's 5/5 against random's 0/5.
- The rule baselines read structured facts for leads they collected, so they never misread text; the models read
  text only.
- In the follow-up, the Jev swarm's "after" numbers changed two things at once: the defence and call skipping.
- Jev's answers vary from run to run on the same seed, so in-sample threshold calibration did not carry over.
- The liar model is simple: liars never refute honest Irregulars or claim plausible nearby addresses.

## 6. Possible next steps

- **More seeds:** 20 seeds of Jev Solo against the rule (about $0.10).
- **A hybrid swarm:** Jev Irregulars gather and share, and a structured counter or one genius call per tick does
  the elimination.
- **Give Jev a decomposed culprit question:** for example, one yes/no per suspect ("is this suspect consistent
  with the notebook?") instead of a single ten-way choice.
- **Smarter liars:** nearby, plausible fakes and false accusations, to test the defence properly.
- **Fairness runs:** cap the swarm's spend at the genius's per seed (`batch --fair-to`).

## Reproduce

```
cd ~/worksapce/jev-swarm
python3 run.py holmes                     # viewer at http://127.0.0.1:8781
cd holmes
python3 -m irregulars.batch --mode solo  --policies jev chat rule random --seeds 5
python3 -m irregulars.batch --mode swarm --policies jev rule random --seeds 5
python3 -m irregulars.batch --mode swarm --policies rule --vary liar_frac=0,0.05,0.15 --seeds 20
python3 tests/test_checks.py
```

Detailed pilot tables: [pilot_2026-10-01.md](pilot_2026-10-01.md). Screenshots:
[viewer_solo.jpg](viewer_solo.jpg), [viewer_swarm.jpg](viewer_swarm.jpg).
