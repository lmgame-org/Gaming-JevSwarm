# Circuit v2 (hardened), 100 seeds: partial results, 5 October 2026

The hardened v2 benchmark extended from 20 to 100 seeds, with the same settings and defaults as
[benchmark_20seeds_2026-10-03.md](benchmark_20seeds_2026-10-03.md). Per-case rows:
[benchmark_100seeds_v2_partial.csv](benchmark_100seeds_v2_partial.csv). Seeds 1-20 are the original 20-seed rows,
reused unchanged.

**Partial.** The 13 free and Jev settings ran all 100 seeds. The three gpt-6-astra settings were stopped partway, on
purpose, when the benchmark was redesigned (v3; see [problem_setup.md](problem_setup.md) section 8):

| Setting | Seeds run |
|---|---|
| solo gpt-6-astra | 39 |
| Baker Street, gpt-6-astra Holmes, Jev boys | 36 |
| Baker Street, gpt-6-astra Holmes, rule boys | 37 |

Their rows are shown on the seeds they ran and are not comparable with the 100-seed rows.

## Results

| Setting | Solved (95% CI) | Block / signal / type / fix | Case time p50 / p90 | Ran to deadline | Real time p50 / p90 | Calls / case | Cost / case | Wrong quorums |
|---|---|---|---|---|---|---|---|---|
| Solo · gpt-6-astra | 27/39 (0.54-0.81) | 34 / 34 / 34 / 27 | 1.5 h / 3.0 h | 7 | 18.7 s / 33.3 s | 5 | $0.189 | - |
| Solo · Jev | 10/100 (0.06-0.17) | 13 / 13 / 10 / 10 | 2.8 h / 3.2 h | 76 | 2.3 s / 171.2 s | 9 | $0.0004 | - |
| Solo · rule (cone tracing) | 12/100 (0.07-0.20) | 13 / 13 / 13 / 12 | 2.8 h / 3.2 h | 84 | 0.1 s / 0.2 s | 0 | free | - |
| Solo · random | 6/100 (0.03-0.12) | 8 / 8 / 6 / 6 | 3.2 h / 4.0 h | 100 | 0.1 s / 0.2 s | 0 | free | - |
| Baker Street · gpt-6-astra Holmes, Jev boys | 20/36 (0.40-0.70) | 29 / 29 / 29 / 20 | 6.0 h / 6.0 h | 36 | 212.0 s / 1119.9 s | 152 | $0.139 | - |
| Baker Street · gpt-6-astra Holmes, rule boys | 23/37 (0.46-0.76) | 29 / 29 / 29 / 23 | 6.0 h / 6.0 h | 36 | 37.1 s / 72.2 s | 6 | $0.143 | - |
| Baker Street · counting Holmes, Jev boys | 33/100 (0.25-0.43) | 36 / 36 / 35 / 33 | 6.0 h / 6.0 h | 58 | 6.9 s / 293.1 s | 106 | $0.0028 | - |
| Baker Street · counting Holmes, Jev boys, no Wiggins | 40/100 (0.31-0.50) | 41 / 41 / 41 / 40 | 6.0 h / 6.0 h | 55 | 6.3 s / 9.0 s | 91 | $0.0023 | - |
| Baker Street · counting Holmes, rule boys | 45/100 (0.36-0.55) | 48 / 48 / 46 / 45 | 6.0 h / 6.0 h | 51 | 0.2 s / 0.3 s | 0 | free | - |
| Baker Street · counting Holmes, rule boys, no Wiggins | 43/100 (0.34-0.53) | 46 / 46 / 44 / 43 | 4.8 h / 6.0 h | 42 | 0.2 s / 0.2 s | 0 | free | - |
| Baker Street · counting Holmes, random boys | 26/100 (0.18-0.35) | 27 / 27 / 27 / 26 | 6.0 h / 6.0 h | 63 | 0.2 s / 0.2 s | 0 | free | - |
| Swarm · rule · 2 wires | 25/100 (0.18-0.34) | 27 / 27 / 25 / 25 | 6.0 h / 6.0 h | 51 | 0.4 s / 0.5 s | 0 | free | 24 |
| Swarm · random · 2 wires | 1/100 (0.00-0.05) | 2 / 2 / 1 / 1 | 1.0 h / 1.8 h | 2 | 0.2 s / 0.4 s | 0 | free | 97 |
| Swarm · Jev · 2 wires | 12/100 (0.07-0.20) | 12 / 12 / 12 / 12 | 1.2 h / 6.0 h | 22 | 2.7 s / 121.9 s | 67 | $0.0036 | 66 |
| Swarm · hybrid · 2 wires | 21/100 (0.14-0.30) | 23 / 23 / 21 / 21 | 6.0 h / 6.0 h | 57 | 4.8 s / 273.6 s | 94 | $0.0046 | 22 |
| Swarm · rule · 4 wires | 15/100 (0.09-0.23) | 16 / 16 / 15 / 15 | 6.0 h / 6.0 h | 62 | 0.4 s / 0.5 s | 0 | free | 23 |

## What it shows

- **Seeds 21-100 are harder than 1-20.** Every setting's rate is lower than on 20 seeds. For example, counting Holmes
  with rule boys drops from 13/20 to 45/100.
- **Baker Street with exact counting is the best free family:**

  | Boys | Solved |
  |---|---|
  | rule | 45/100 |
  | rule, no Wiggins | 43/100 |
  | Jev, no Wiggins | 40/100 |
  | Jev | 33/100 |
  | random | 26/100 |

  The 20-seed Wiggins effect is not significant over 100 seeds.
- **Solo debuggers with 10 probes are weak:** Jev 10/100, rule 12/100. Solo gpt-6-astra solves about 69% of its 39
  seeds.
- **Liars capture swarms often, even with the defence.** Wrong quorums: rule 24 (2 wires) and 23 (4 wires), hybrid
  22, Jev 66, random 97.
- **Every agent setting is below the blind bench-sweep baseline** (80/100; see [problem_setup.md](problem_setup.md)).
  That finding is what led to the v3 redesign.

Spend for the 100-seed extension: $9.71 (the table's total includes the reused 20-seed rows).
