# The Irregulars: background, design and results

*jev-swarm / holmes, as of 2 October 2026 (hybrid swarm and Baker Street mode added the same day)*

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
- **Hybrid** (`hybrid`, added after the first results): Jev picks each Irregular's action (move, share, tail,
  refute, wait), but its culprit/motive/hideout vote comes from exact counting over the leads it holds, the same
  counting as the reflex rule, with the liar defence. Jev is asked only for the action, so each call is about 30%
  cheaper.
- **Hybrid with a genius at the Yard** (`hybrid_genius`): Jev Irregulars gather as in `hybrid`. Every lead
  shouted within range of Scotland Yard reaches a hub (implausible claims are dropped). When at least 3 new
  leads have arrived (at most 8 times a case), gpt-6-astra reads every lead at the hub and announces an answer
  and whether it is sure. The case closes when it is sure; the Irregulars' own quorum does not close it.

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

### 2.5 Baker Street mode: scatter and gather, as in the stories

The swarm modes above let the Irregulars organise themselves. In the stories they do not: Holmes summons Wiggins and
his "dozen" boys, tells them what to find, pays them a shilling a day with a guinea for whoever finds the thing, and
waits at Baker Street for them to report. `baker_street` follows that chain of command.

- **Holmes (decides, never leaves 221B).** He reads every report that has reached him, lists the open questions
  ("no alibi yet for S3", "hideout district unconfirmed", "conflicting reports about A045"), issues up to six
  assignments (1-4 nearby addresses each, a suspect to watch, one sentence on what to look for), and names
  culprit, motive and hideout once he is sure. He is either gpt-6-astra (`holmes = chat`, default) or exact
  counting with a rule planner (`holmes = rule`, free). He re-plans at most 12 times a case.
- **Wiggins (splits the boys, collects the reports).** He takes Holmes's orders to a forward post near the
  assignments, splits the idle boys across them, collects reports in his bag, and runs the batch back to Baker
  Street when he has three reports, one has waited two ticks, or no boys are out. With `wiggins = off`, each boy
  runs all the way back to 221B and gets the next order there.
- **The boys (observe, never accuse).** About a dozen by default (up to 100). They go on foot at 100 m a minute.
  Each makes only small local choices with Jev, one call each time it arrives somewhere: check the next address in
  its assignment or one next door, tail a suspect it spots at home, or run back with what it has. No long-range
  shouting: every report travels by legs.
- **Pay.** A shilling a day and a guinea for the key lead make boys eager: they finish their assignment, and the
  rule boy hurries back with a key lead. Unpaid boys give up after two calls. The game records who would have
  earned a guinea (the first boy to bring each true key fact).
- **Bribed or mistaken boys.** A bribed boy (`liar_frac`) reports made-up leads for every address he was sent to,
  all supporting Moriarty's wrong answer. A mistaken boy (`misinformed_frac`) gets one report wrong. Holmes sees
  who reported what. The counting Holmes treats conflicting reports about one address as contested and sends
  another boy; once a third report breaks the tie, the outvoted boy is no longer believed.
- **Clock.** The preset gives 48 ticks of 15 minutes, the same 12 case hours as the Solo detective.

### 2.6 The live viewer and tooling

- **Launch screen:** presets, every knob, a live preview of the seeded map with a solvability check, model and
  key tests, and a cost estimate.
- **Live map:** districts, the Thames, the street graph, 221B, Scotland Yard, the scene, candidate hideouts and
  suspects' homes. Solo shows the cab route and lights up visited addresses; Swarm shows each Irregular as a dot
  coloured by its vote, with shouts rippling out to the shouting range. Baker Street shows Wiggins (W) and his post,
  each boy coloured by the district of his assignment with a dashed line to where he is heading, runners heading
  back ringed in white, and a pulse where a report is handed over. Its side panel shows Holmes's current answer,
  his open questions, the assignments and the latest reports.
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
| Jev (with defence and call skipping) | 1/5 | 2/5 (1 wrong) | 27.2 | 2.0 | $0.19 |
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

### 3.4 Hybrid swarm: Jev gathers, exact counting votes

Same seeds 1-5, defaults otherwise (quorum 30, 32 ticks, liar defence on, no liars).

| Policy | Range | Solved | Wrong quorums | Ticks to close | Final majority, parts right | Cost per case |
|---|---|---|---|---|---|---|
| **hybrid** | 1 km | **4/5** | 0 | 18.8 | 3.0 | $0.18 |
| **hybrid** | 2 km | **4/5** | 0 | 16.0 | 3.0 | $0.16 |
| hybrid_genius (3 seeds) | 2 km | 2/3 | 0 | 22.7 | 3.0 | $0.41 ($0.17 of it gpt-6-astra) |
| Jev swarm (votes from Jev) | 1 km | 1-2/5 | 1-2 | 22-27 | 2.0-2.2 | $0.19-0.27 |
| Jev swarm | 2 km | 2/5 | 3 | 10.4 | 2.2 | $0.14 |
| Reflex-rule swarm | 1 km / 2 km | 3/5 / 4/5 | 0 | 20.0 / 13.8 | 2.6 / 2.4 | free |
| Solo gpt-6-astra | - | 5/5 | - | - | - | $0.34 |

- **Splitting the jobs works.** Letting Jev decide only where to go and what to shout, and counting the leads
  exactly for the vote, raised the Jev swarm from 1-2/5 to 4/5 at both ranges, with no wrong quorums.
- **Seed 1 is the one miss everywhere.** No hybrid run reached a quorum on seed 1, but the final majority answer
  was fully right every time. The rule swarm also failed seed 1, and the genius at the Yard saw the right
  answer there but was never sure enough to close.
- **Jev gathers better than the rule.** At 1 km, hybrid solved 4/5 while the reflex rule, with the same
  counting but rule-chosen actions, solved 3/5. With 5 seeds that is suggestive, not proven.
- **The genius at the Yard adds cost, not accuracy, here.** It solved 2 of 3 seeds for $0.41 per case, more than
  Solo gpt-6-astra ($0.34). Leads reach the Yard only from Irregulars within range of it, so it waits on
  partial evidence.
- Caveats: hybrid_genius ran on 3 seeds only (spend guard). On seed 5 at 2 km, hybrid reached a $0.12 per-run
  cap in its last ticks, and the reflex rule chose actions from then on.

### 3.5 Baker Street: Holmes, Wiggins and a dozen Irregulars

Seeds 1-5, 12 boys with Wiggins and pay, 48 ticks (12 case hours, as in Solo), Jev for the boys' local choices.
"Named" means Holmes named the answer before the deadline; at the deadline he gives his best answer anyway, which
is scored like the Solo detective's forced accusation.

| Holmes | Solved | Named before the deadline | Case time used | Reports reaching Holmes | Holmes's plans | Cost per case |
|---|---|---|---|---|---|---|
| **gpt-6-astra** | **5/5** | 2 of 5 | 11.4 h | 67-98 | 7-12 | $0.56 (Holmes $0.55, boys $0.003) |
| **Exact counting** | **5/5** | 5 of 5 | 7.0 h | 34-54 | 4-6 | **$0.002** (boys' Jev calls only) |
| Solo gpt-6-astra (no Irregulars) | 5/5 | 3 of 5 | 9.3 h | 15-20 visits | - | $0.34 |
| Hybrid swarm (100 Jev Irregulars) | 4/5 | - | 4.0-4.7 h | - | - | $0.16-0.18 |

Chain-of-command knobs, exact-counting Holmes with rule boys, 20 seeds (free):

| Setting | Solved | Named before the deadline | Case time used |
|---|---|---|---|
| 12 boys, Wiggins, paid (canon) | **19/20** | 14 | 8.9 h |
| no Wiggins (boys run all the way back) | 13/20 | 5 | 10.1 h |
| unpaid (boys give up after two calls) | 17/20 | 11 | 9.0 h |
| 2 of 12 boys bribed | 6/20 | 9 | 9.6 h |
| 100 boys | 19/20 | 18 | 7.1 h |
| 12 boys, 8-hour clock instead of 12 | 14/20 | 6 | 7.4 h |

- **Command and control solves the case.** Both Holmeses solved all five cases. With exact counting, the canon
  setup solved 19 of 20 for a fifth of a cent per case, naming the answer in about 7-9 case hours.
- **gpt-6-astra as Holmes is right but slow to commit.** It solved 5/5 but named the answer early in only 2
  cases. In the other 3 it was still asking for corroboration when time ran out (its final answers were right),
  and it cost $0.56 a case, more than gpt-6-astra working alone ($0.34).
- **Wiggins matters.** Without his forward post the boys spend their time running to Baker Street: 13/20 instead
  of 19/20.
- **Bribed boys are the weak point.** Two bribed boys out of twelve cut the counting Holmes to 6/20. Each bribed
  report claims an address he really was sent to, so only a re-check by another boy exposes it.
- **More boys mainly saves time** (7.1 h with 100 boys against 8.9 h with 12); the canon dozen is enough.
- Caveats: the counting Holmes reads the structured fact behind each report, so it never misreads a lead (gpt-6-astra
  reads the text). gpt-6-astra Holmes was run on 5 seeds only.

![Baker Street viewer](viewer_baker_street.jpg)

### 3.6 Genius vs swarm at similar spend

| | Cost per case | Solved |
|---|---|---|
| One gpt-6-astra detective | $0.34 | 5/5 |
| 100 Jev Irregulars, 1 km | $0.19-0.27 | 1-2/5 |
| 100 Jev Irregulars, 2 km | $0.14 | 2/5 |
| One Jev detective | $0.005 | 1-2/5 |
| Reflex-rule swarm, 2 km | free | 4/5 (18/20) |
| **Hybrid swarm (Jev actions + exact counting), 1 km or 2 km** | **$0.16-0.18** | **4/5** |
| Hybrid + gpt-6-astra at the Yard, 2 km | $0.41 | 2/3 |
| **Baker Street: gpt-6-astra Holmes, Wiggins, 12 Jev boys** | $0.56 | **5/5** |
| **Baker Street: exact-counting Holmes, Wiggins, 12 Jev boys** | **$0.002** | **5/5** (19/20 with rule boys) |

With Jev doing everything, **one strong reasoner clearly beats a hundred cheap ones.** The swarm's advantage,
coverage, is real (it sees every address at once), but each Irregular must still combine clues, and that is where
Jev falls short. **The hybrid closes most of the gap:** Jev gathers and spreads evidence, exact counting combines
it, and the swarm solves 4/5 with no wrong answers for about half the genius's cost per case. **Organising the
Irregulars the way Holmes does closes the rest of the gap:** a central decider who assigns errands and reads every
report solved 5/5, and with exact counting as that decider it costs almost nothing.

### 3.7 Spend

| Round | Spend |
|---|---|
| Building and testing | about $0.45 |
| First pilot (Solo: Jev, gpt-6-astra; Swarm: Jev honest and with liars) | $4.04 |
| Follow-up (Jev Solo; Jev swarm: honest, liars, 2 km) | $2.50 |
| Hybrid round (hybrid 1 km and 2 km, 5 seeds each; hybrid_genius 2 km, 3 seeds; smoke tests) | $3.04 |
| Baker Street round (gpt-6-astra Holmes $2.80 and counting Holmes $0.01 on 5 seeds; smoke test $0.12) | $2.93 |
| **Total** | **about $13.00** |

gpt-6-astra is costed from token counts at OpenRouter's list price ($10 per million input tokens, $1 cached, $50
output), because OpenAI's API does not return a cost. Jev costs are as reported by OpenRouter.

## 4. Conclusions

1. **A single strong model wins the head-to-head, narrowly once the swarm is designed well:** gpt-6-astra solved
   5/5 for $0.34 a case. One Jev detective, or a hundred Jev Irregulars doing everything, managed 1-2/5. The
   hybrid swarm (Jev gathers, exact counting votes) reached 4/5 with no wrong answers for $0.16-0.18 a case.
   Organised the way Holmes runs them (section 3.5), the Irregulars matched the genius at 5/5.
2. **Jev is good at single-step judgements** (motive, hideout, which lead to follow) and weak at multi-clue
   elimination (the culprit). It also lacks a usable sense of when it is done.
3. **Swarm success is mostly about the plumbing:** communication range, and whether the group can tell
   independent evidence from repetition. With good plumbing, even a simple rule swarm solves 18/20.
4. **Coordinated lying is the main threat to a vote-counting swarm,** and simple, local, physically grounded
   checks (where could this speaker have been?) recover much of the loss.
5. **Give each part of the job to what does it best.** Cheap models choose where to look and what to share; exact
   counting combines the evidence. That beat both "Jev does everything" and "rules do everything" at 1 km.
6. **Holmes's own method wins.** Scatter and gather with one decider at Baker Street, Wiggins as the relay and a
   dozen boys on errands solved every one of the five cases. With exact counting as Holmes it solved 19 of 20 for
   almost nothing. The self-organising swarm's real handicap was not the boys but the lack of someone to
   assign errands and weigh every report.

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
- **Hybrid on more seeds and under liars:** 20 seeds at 1 km, and 5-15% liars (about $0.20 per case).
- **A better Yard:** let the hub hear the whole city (or have Irregulars run leads to it), so the genius decides on
  full evidence instead of partial evidence.
- **Baker Street:** gpt-6-astra Holmes on 20 seeds and with bribed boys (about $0.60 per case); tell gpt-6-astra
  Holmes to commit earlier (it was right but waited); a cheaper Holmes (Jev planning, exact counting deciding).
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
python3 -m irregulars.batch --mode swarm --policies hybrid --seeds 5 --set comm_range=200
python3 -m irregulars.batch --mode swarm --policies hybrid_genius --seeds 3 --set comm_range=200 --max-usd 1.0
python3 -m irregulars.batch --mode swarm --policies baker_street --seeds 5 --set n_irregulars=12 swarm_ticks=48 holmes=chat
python3 -m irregulars.batch --mode swarm --policies baker_street --seeds 20 --set n_irregulars=12 swarm_ticks=48 holmes=rule boy_policy=rule
python3 tests/test_checks.py
```

Detailed pilot tables: [pilot_2026-10-01.md](pilot_2026-10-01.md). Screenshots:
[viewer_solo.jpg](viewer_solo.jpg), [viewer_swarm.jpg](viewer_swarm.jpg), [viewer_baker_street.jpg](viewer_baker_street.jpg).
