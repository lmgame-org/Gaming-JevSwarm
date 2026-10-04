# The Irregulars: the challenge casebook, 4 October 2026

Ten hard cases, each built to stress one weakness, played by all 11 investigator settings. Each case is one fixed
seed plus its own rules (`irregulars/challenges.py`), checked to be solvable by a careful reader. Pick them in the
app under step 2, "Challenge casebook", or run `python3 -m irregulars.challenges`.

| # | Case | Rules | Tests |
|---|---|---|---|
| 1 | The Frame-Up | Holmesian case | judging who is speaking |
| 2 | The Liars' Chorus | true facts ×3, lie rate 0.5 (a lie can appear twice) | weighing conflicting reports |
| 3 | The Single Thread | every true fact at one address, lie rate 0.1 | covering the whole map |
| 4 | The Sprawling City | 300 addresses, 16 suspects | searching a big map |
| 5 | Before the Dawn Train | 4-hour limit | speed |
| 6 | Moriarty's Boys | 25% of boys bribed, 10% mistaken | trusting your helpers |
| 7 | The London Particular | red herrings everywhere, almost no tips | ignoring noise |
| 8 | The Frame-Up in the Sprawl | Holmesian, 250 addresses | reasoning and searching |
| 9 | The Frame-Up at Dawn | Holmesian, 6-hour limit | reasoning under time pressure |
| 10 | The Perfect Crime | Holmesian, lie rate 0.3, 16 suspects, 15% bribed boys, 8 hours | everything |

Every other setting as in the benchmarks (12 boys for Baker Street, 100 boys and a 2 km shout for swarms). Jev had
30 seconds per decision; 0 of 101,434 decisions fell back to the heuristic. Spend: $13.10. Per-run records:
[challenge_casebook_2026-10-04.json](challenge_casebook_2026-10-04.json).

## Results (one run per case; "2/3" = two of culprit, motive and hideout right)

| Case | Solo · gpt-6-astra | Solo · Jev | Solo · heuristic | Solo · random | Baker Street · gpt-6-astra Holmes, Jev boys | Baker Street · counting Holmes, Jev boys | Baker Street · counting Holmes, heuristic boys | Swarm · Jev, 2 km | Swarm · hybrid, 2 km | Swarm · heuristic, 2 km | Swarm · random, 2 km |
|---|---|---|---|---|---|---|---|---|---|---|---|
| The Frame-Up | 2/3 | 2/3 | 2/3 | 0/3 | **solved** | 2/3 | 2/3 | **solved** | 2/3 | 2/3 | 0/3 |
| The Liars' Chorus | **solved** | **solved** | **solved** | 0/3 | **solved** | **solved** | 2/3 | **solved** | **solved** | **solved** | 0/3 |
| The Single Thread | 2/3 | 1/3 | 2/3 | 0/3 | **solved** | **solved** | **solved** | 2/3 | 0/3 | 0/3 | 0/3 |
| The Sprawling City | 2/3 | 2/3 | 2/3 | 1/3 | 2/3 | 2/3 | 2/3 | 0/3 | 0/3 | **solved** | 0/3 |
| Before the Dawn Train | 0/3 | 0/3 | 1/3 | 0/3 | 1/3 | 1/3 | 1/3 | 2/3 | **solved** | **solved** | 0/3 |
| Moriarty's Boys | **solved** | **solved** | **solved** | 0/3 | **solved** | **solved** | 2/3 | 0/3 | 0/3 | 0/3 | 0/3 |
| The London Particular | **solved** | 1/3 | 2/3 | 0/3 | **solved** | **solved** | **solved** | 2/3 | **solved** | **solved** | 0/3 |
| The Frame-Up in the Sprawl | **solved** | 2/3 | 2/3 | 0/3 | **solved** | 2/3 | 2/3 | 2/3 | 0/3 | 2/3 | 0/3 |
| The Frame-Up at Dawn | 2/3 | 1/3 | 1/3 | 0/3 | 2/3 | 2/3 | 2/3 | 2/3 | 2/3 | 2/3 | 0/3 |
| The Perfect Crime | **solved** | 2/3 | 2/3 | 0/3 | 2/3 | 1/3 | 2/3 | 0/3 | 0/3 | 2/3 | 0/3 |
| **Solved** | **5/10** (0.24-0.76) $3.58 | **2/10** (0.06-0.51) $0.05 | **2/10** (0.06-0.51) $0.00 | **0/10** (0.00-0.28) $0.00 | **6/10** (0.31-0.83) $5.41 | **4/10** (0.17-0.69) $0.02 | **2/10** (0.06-0.51) $0.00 | **2/10** (0.06-0.51) $1.58 | **3/10** (0.11-0.60) $2.47 | **4/10** (0.17-0.69) $0.00 | **0/10** (0.00-0.28) $0.00 |

## What it shows

One run per case, so each cell is an anecdote; the patterns across cases are what count.

1. **Baker Street with gpt-6-astra Holmes solves the most (6/10), then gpt-6-astra alone (5/10).** The two gpt-6-astra
   detectives are the only ones that solve a frame-up on a big map (case 8), and only gpt-6-astra alone solves the
   Perfect Crime.
2. **Each approach has a case it owns, and one that breaks it:**
   - *Coverage wins The Single Thread:* all three Baker Street variants solve it; no swarm does (gossip spreads what
     was found, but nobody makes sure every door is knocked on), and the lone genius misses a door.
   - *Parallel speed wins Before the Dawn Train (4 hours):* only swarms (hybrid, heuristic) solve it; one detective or
     one Holmes waiting for runners is too slow.
   - *Scale wins The Sprawling City:* only the 100-boy heuristic swarm solves it.
   - *A leader protects against Moriarty's Boys:* both gpt-6-astra settings, counting Holmes with Jev boys, and even
     the lone detectives (no boys to betray them) solve it; every swarm fails, because bribed boys poison the gossip.
   - *Reasoning is needed for frame-ups:* counting players never solve one.
3. **Nobody solves The Frame-Up at Dawn:** reasoning and time pressure together beat every approach.
