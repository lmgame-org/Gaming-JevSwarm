# The Irregulars: Holmesian cases, 20-case benchmark, 4 October 2026

The same 20 seeds (1-20) as the standard benchmark, with `difficulty = holmesian`: a frame-up by the culprit's own
servants (false traits two copies against one true copy, plus a false alibi), one planted clue at the scene, two
witnesses who saw the bribe, single copies of the true culprit clues, timed alibis and mud-and-dust hideout traces.
See the README for how a case is built. Every case is checked to be solvable by a reader who discounts the bribed
witnesses and the planted clue; plain counting names the framed suspect in all 20.

12 case hours for every approach; Baker Street with 12 boys, swarms with 100 boys and a 2 km shout. Jev had 30 seconds
per decision. Per-case rows: [benchmark_holmesian_20seeds_2026-10-04.csv](benchmark_holmesian_20seeds_2026-10-04.csv).

## Results (run 2, all rows clean)

| Setting | Solved (95% CI) | Culprit / motive / hideout | Sim time p50 / p90 | Ran to deadline | Real time p50 / p90 | Calls / case | Cost / case | Heuristic fallbacks |
|---|---|---|---|---|---|---|---|---|
| Solo detective · gpt-6-astra | 11/20 (0.34-0.74) | 20 / 11 / 20 | 10.9 h / 11.9 h | 12 | 85.8 s / 100.4 s | 19 | $0.371 | 0.00% |
| Solo detective · Jev | 3/20 (0.05-0.36) | 7 / 11 / 20 | 11.8 h / 12.0 h | 19 | 5.0 s / 5.7 s | 20 | $0.005 | 0.00% |
| Solo detective · heuristic | 0/20 (0.00-0.16) | 1 / 14 / 19 | 9.4 h / 10.2 h | 18 | 0.0 s / 0.0 s | 0 | free | 0.00% |
| Solo detective · random | 0/20 (0.00-0.16) | 1 / 5 / 3 | 11.9 h / 12.0 h | 20 | 0.0 s / 0.0 s | 0 | free | 0.00% |
| Baker Street Irregulars · gpt-6-astra Holmes, Jev boys | 17/20 (0.64-0.95) | 19 / 18 / 20 | 12.0 h / 12.0 h | 11 | 93.5 s / 126.9 s | 108 | $0.604 | 0.00% |
| Baker Street Irregulars · counting-heuristic Holmes, Jev boys | 0/20 (0.00-0.16) | 0 / 19 / 19 | 9.5 h / 12.0 h | 5 | 6.9 s / 9.6 s | 79 | $0.002 | 0.00% |
| Baker Street Irregulars · counting-heuristic Holmes, heuristic boys | 0/20 (0.00-0.16) | 0 / 17 / 20 | 12.0 h / 12.0 h | 12 | 0.0 s / 0.0 s | 0 | free | 0.00% |
| Swarm Detectives · Jev swarm · 2 km | 9/20 (0.26-0.66) | 9 / 16 / 18 | 2.2 h / 12.0 h | 2 | 10.8 s / 41.3 s | 1177 | $0.161 | 0.00% |
| Swarm Detectives · hybrid · 2 km | 0/20 (0.00-0.16) | 0 / 14 / 14 | 6.5 h / 12.0 h | 6 | 27.4 s / 52.3 s | 2500 | $0.275 | 0.00% |
| Swarm Detectives · heuristic swarm · 2 km | 0/20 (0.00-0.16) | 0 / 18 / 18 | 2.2 h / 12.0 h | 2 | 0.1 s / 0.5 s | 0 | free | 0.00% |

"Heuristic fallbacks" is the share of decisions the heuristic made because a model call failed or timed out. Every row
is at 0.00%.

## Who was accused

| Setting | Right culprit | The framed suspect | Another wrong suspect |
|---|---|---|---|
| Solo · gpt-6-astra | 20 | 0 | 0 |
| Solo · Jev | 7 | 2 | 11 |
| Baker Street · gpt-6-astra Holmes, Jev boys | 19 | 0 | 1 |
| Baker Street · counting Holmes, Jev boys | 0 | 11 | 9 |
| Jev swarm · 2 km (plurality of votes) | 11 | 5 | 4 |
| Hybrid · 2 km (plurality of votes) | 0 | 12 | 8 |

## Cross-check: run 1 against run 2

Run 1 (3 October) ran all batches at once with 8 seconds per Jev decision; the Jev API could not keep up and most
Jev decisions in the Baker Street and swarm rows fell back to the heuristic. Run 2 ran the Jev-heavy batches one at a
time with 30 seconds per decision.

| Setting | Run 1 | Run 1 fallbacks | Run 2 | Run 2 fallbacks |
|---|---|---|---|---|
| Solo · gpt-6-astra | 7/20 (culprit 19, motive 9, hideout 18) | 0% | 11/20 (20 / 11 / 20) | 0% |
| Solo · Jev | 3/20 | 0% | 3/20 | 0% |
| Baker Street · gpt-6-astra Holmes, Jev boys | 17/20 | 64% | 17/20 | 0% |
| Baker Street · counting Holmes, Jev boys | 0/20 | 72% | 0/20 | 0% |
| Jev swarm · 2 km | 1/20 | 95% | 9/20 | 0% |
| Hybrid · 2 km | 0/20 | 95% | 0/20 | 0% |

- The clean rows agree within noise: solo gpt-6-astra 7 and 11 (95% intervals 0.18-0.57 and 0.34-0.74 overlap; the
  difference is the motive, which depends on whether the visits happen to reach both motive clues), solo Jev 3 and 3.
- Baker Street with gpt-6-astra is 17/20 both times; with heuristic boys standing in for most Jev boys in run 1 it
  made no difference, as on standard cases.
- The Jev swarm changes most (1 to 9): run 1 was really a heuristic swarm, which always falls for the frame-up.
- A wasted first attempt at the run 2 solo rows ran on standard cases by mistake (a garbled setting); it was thrown
  away, and the batch runner now refuses invalid settings.

## What it shows

1. **Reasoning beats counting on a planned crime.** Every counting player scores 0/20: it names the framed suspect
   or another wrong one. gpt-6-astra names the right culprit in 20/20 cases solo and 19/20 as Holmes.
2. **Scatter and gather still wins.** Baker Street with gpt-6-astra Holmes solves 17/20 against 11/20 for gpt-6-astra
   alone, for about $0.60 against $0.37 a case. Solo gpt-6-astra always finds the culprit but runs out of visits
   before finding both motive clues (motive 11/20); twelve boys cover the map.
3. **The leaderless Jev swarm now beats every counting approach (9/20 against 0/20),** the reverse of the standard
   cases. Reading the text lets some boys doubt the servants' matching story. But with no leader it still agrees on
   a wrong answer in 9 cases, 5 of them on the framed suspect.
4. **The hybrid falls with the counting rule (0/20).** On standard cases, letting the counting rule vote was what made
   the hybrid strong (16/20); here it is exactly what loses.
5. **The ranking flips with the case.** Standard: Baker Street 19, heuristic swarm 18, hybrid 16, solo gpt-6-astra 11.
   Holmesian: Baker Street with gpt-6-astra 17, solo gpt-6-astra 11, Jev swarm 9, everything that counts 0.

Spend: run 1 $22.77 (Baker Street and swarm rows discarded), the wasted solo attempt about $7, run 2 $28.37.
