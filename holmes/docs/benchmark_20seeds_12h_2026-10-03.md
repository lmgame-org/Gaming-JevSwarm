# The Irregulars: 20-case benchmark on one 12-hour clock, 3 October 2026

All 14 setups on the same 20 seeded cases (seeds 1-20), now on the same 12-case-hour time limit. Per-case rows:
[benchmark_20seeds_12h_2026-10-03.csv](benchmark_20seeds_12h_2026-10-03.csv). Method and column meanings as in
[benchmark_20seeds_2026-10-02.md](benchmark_20seeds_2026-10-02.md).

## Where each row comes from

- **Solo detective and Baker Street Irregulars:** unchanged from the 2 October benchmark, which already ran on 12 hours.
- **Heuristic and random swarms:** re-run on 3 October at 12 hours (free).
- **Jev swarm and hybrid** (flagged): re-run on 3 October at 12 hours with **30 seconds per Jev decision** instead of 8.
  - The Jev API was much slower that day. A first attempt with the usual 8 seconds had 15-26% of decisions taken
    over by the heuristic, so it was stopped and discarded.
  - With 30 seconds, only 25 of about 128,000 Jev calls (0.02%) fell back to the heuristic.
  - Accuracy and cost are comparable with the other rows. **Real time is not**, because it reflects that day's API
    speed. These four rows should be re-run later with the standard 8 seconds to cross-check.

## Results

| Setting | Solved (95% CI) | Culprit / motive / hideout | Sim time p50 / p90 | Ran to deadline | Real time p50 / p90 | Calls / case | Cost / case |
|---|---|---|---|---|---|---|---|
| Solo detective · gpt-6-astra | 11/20 (0.34-0.74) | 17 / 14 / 19 | 10.9 h / 11.8 h | 13 | 81.3 s / 95.0 s | 19 | $0.347 |
| Solo detective · Jev | 5/20 (0.11-0.47) | 8 / 12 / 19 | 11.9 h / 12.0 h | 20 | 4.7 s / 5.0 s | 19 | $0.005 |
| Solo detective · heuristic | 9/20 (0.26-0.66) | 13 / 16 / 20 | 9.2 h / 11.1 h | 18 | 0.0 s / 0.0 s | 0 | free |
| Solo detective · random | 0/20 (0.00-0.16) | 1 / 5 / 3 | 11.9 h / 12.0 h | 20 | 0.0 s / 0.0 s | 0 | free |
| Baker Street Irregulars · gpt-6-astra Holmes, Jev boys | 19/20 (0.76-0.99) | 20 / 19 / 20 | 11.2 h / 12.0 h | 8 | 102.0 s / 155.1 s | 109 | $0.615 |
| Baker Street Irregulars · counting-heuristic Holmes, Jev boys | 19/20 (0.76-0.99) | 19 / 20 / 20 | 6.5 h / 10.8 h | 1 | 4.7 s / 6.1 s | 67 | $0.002 |
| Baker Street Irregulars · counting-heuristic Holmes, heuristic boys | 19/20 (0.76-0.99) | 19 / 19 / 20 | 8.2 h / 12.0 h | 6 | 0.0 s / 0.0 s | 0 | free |
| Swarm Detectives · heuristic swarm · 1 km | 13/20 (0.43-0.82) | 13 / 13 / 13 | 6.5 h / 12.0 h | 7 | 0.3 s / 0.4 s | 0 | free |
| Swarm Detectives · random swarm · 1 km | 0/20 (0.00-0.16) | 0 / 0 / 0 | 12.0 h / 12.0 h | 20 | 0.3 s / 0.3 s | 0 | free |
| Swarm Detectives · heuristic swarm · 2 km | 18/20 (0.70-0.97) | 18 / 19 / 19 | 1.8 h / 10.0 h | 1 | 0.1 s / 0.5 s | 0 | free |
| Swarm Detectives · Jev swarm · 1 km | 2/20 (0.03-0.30) | 4 / 7 / 11 | 7.0 h / 12.0 h | 9 | 16.7 s / 325.0 s | 1473 | $0.188 |
| Swarm Detectives · Jev swarm · 2 km | 11/20 (0.34-0.74) | 12 / 16 / 19 | 2.0 h / 3.8 h | 1 | 8.4 s / 15.5 s | 927 | $0.121 |
| Swarm Detectives · hybrid · 1 km | 10/20 (0.30-0.70) | 10 / 10 / 10 | 12.0 h / 12.0 h | 10 | 33.8 s / 92.3 s | 2580 | $0.262 |
| Swarm Detectives · hybrid · 2 km | 16/20 (0.58-0.92) | 16 / 18 / 18 | 2.8 h / 12.0 h | 2 | 10.6 s / 45.7 s | 1412 | $0.150 |

Wrong quorums (the swarm agreed on a wrong answer): Jev swarm 1 km 9, Jev swarm 2 km 8, hybrid 2 km 2, heuristic
swarm 2 km 1; none for the heuristic swarm at 1 km or hybrid at 1 km.

## What changed from the 8-hour swarm runs

| Setup | 8 h (2 Oct) | 12 h (3 Oct) |
|---|---|---|
| Heuristic swarm, 1 km | 13/20 | 13/20 |
| Heuristic swarm, 2 km | 18/20 | 18/20 |
| Random swarm, 1 km | 0/20 | 0/20 |
| Jev swarm, 1 km | 5/20 | 2/20 (flagged) |
| Jev swarm, 2 km | 10/20 | 11/20 (flagged) |
| Hybrid, 1 km | 10/20 | 10/20 (flagged) |
| Hybrid, 2 km | 17/20 | 16/20 (flagged) |

- **The extra four hours change little.** Swarms that agree, agree early. Those that don't usually fail for reasons
  more time doesn't fix: short shouting range, or settling on a wrong answer.
- **The Jev swarm at 1 km did worse with more time** (2/20 against 5/20): it reached a quorum 11 times, 9 of them on
  a wrong answer. Longer clocks give a Jev swarm more chances to agree on the wrong thing. With 20 cases, part of
  this difference may be noise.
- **The overall ranking is unchanged.**
  1. Baker Street Irregulars: 19/20 with either Holmes.
  2. Heuristic swarm at 2 km: 18/20.
  3. Hybrid at 2 km: 16/20.
  4. Solo gpt-6-astra: 11/20; Jev swarm at 2 km: 11/20.
  5. Weaker setups below that.

## Spend

Re-run with 30 seconds per decision: $14.43 (Jev swarm 1 km $3.77, 2 km $2.41; hybrid 1 km $5.25, 2 km $3.00).
The discarded 8-second attempt cost about $7.60. Total about $22. The other rows reuse earlier runs (no new spend).
