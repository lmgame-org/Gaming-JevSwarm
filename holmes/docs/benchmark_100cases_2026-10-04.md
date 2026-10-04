# The Irregulars: 100-case benchmark (standard cases), 4 October 2026

Standard cases, seeds 1-100, 12 case hours for every approach; Baker Street with 12 boys, swarms with 100 boys and a
2 km shout. Model decisions had 30 seconds each; 0 decisions fell back to the heuristic. Spend: $107.66.
Per-case rows: [benchmark_100cases_2026-10-04.csv](benchmark_100cases_2026-10-04.csv). Every Baker Street and swarm run
also saved its positions round by round (`track.jsonl`), so any case can be replayed.

| Setting | Solved (95% CI) | Culprit / motive / hideout | Sim time p50 / p90 | Ran to deadline | Real time p50 / p90 | Calls / case | Cost / case | Heuristic fallbacks |
|---|---|---|---|---|---|---|---|---|
| Solo detective · gpt-6-astra | 57/100 (0.47-0.66) | 83 / 68 / 100 | 10.5 h / 11.7 h | 59 | 82.0 s / 95.6 s | 18 | $0.339 | 0.00% |
| Solo detective · Jev | 25/100 (0.18-0.34) | 46 / 56 / 95 | 11.8 h / 12.0 h | 95 | 4.5 s / 4.9 s | 19 | $0.005 | 0.00% |
| Solo detective · heuristic | 61/100 (0.51-0.70) | 81 / 79 / 98 | 9.0 h / 10.3 h | 77 | 0.0 s / 0.0 s | 0 | free | 0.00% |
| Solo detective · random | 0/100 (0.00-0.04) | 10 / 15 / 21 | 11.9 h / 12.0 h | 100 | 0.0 s / 0.0 s | 0 | free | 0.00% |
| Baker Street Irregulars · gpt-6-astra Holmes, Jev boys | 96/100 (0.90-0.98) | 99 / 97 / 100 | 11.0 h / 12.0 h | 31 | 96.5 s / 130.0 s | 108 | $0.582 | 0.00% |
| Baker Street Irregulars · counting-heuristic Holmes, Jev boys | 95/100 (0.89-0.98) | 98 / 97 / 100 | 7.8 h / 12.0 h | 10 | 4.9 s / 7.1 s | 71 | $0.002 | 0.00% |
| Baker Street Irregulars · counting-heuristic Holmes, heuristic boys | 97/100 (0.92-0.99) | 99 / 97 / 100 | 8.8 h / 12.0 h | 28 | 0.0 s / 0.0 s | 0 | free | 0.00% |
| Swarm Detectives · Jev swarm · 2 km | 38/100 (0.29-0.48) | 50 / 72 / 91 | 2.2 h / 10.2 h | 9 | 8.9 s / 30.0 s | 1123 | $0.149 | 0.00% |
| Swarm Detectives · heuristic swarm · 2 km | 95/100 (0.89-0.98) | 95 / 98 / 98 | 1.5 h / 3.0 h | 2 | 0.1 s / 0.2 s | 0 | free | 0.00% |
| Swarm Detectives · random swarm · 2 km | 0/100 (0.00-0.04) | 0 / 0 / 0 | 12.0 h / 12.0 h | 100 | 0.3 s / 0.4 s | 0 | free | 0.00% |

## What changed from 20 cases

- **Holmes & the Irregulars with gpt-6-astra: 96/100** (19/20 before). Still the best, and a leader with helpers
  wins under any policy: counting Holmes 95-97/100.
- **gpt-6-astra alone: 57/100** (11/20 before). In 59 of 100 cases it ran to its limit; its misses are mostly the
  motive (68/100 right) and sometimes the culprit (83/100), never the hideout.
- **The free heuristic detective alone: 61/100**, level with gpt-6-astra alone on these cases: with no deception
  to see through, careful counting and following tips does as well as reasoning.
- **Jev swarm: 38/100** (11/20 before). It agreed in 91 cases, but on a wrong answer in 53 of them (fast, half
  within 2.2 h). The counting-rule swarm: 95/100, half within 1.5 h.

The trailer's example is case 9: gpt-6-astra alone ran out of visits (right hideout, wrong culprit and motive), the
Jev swarm converged in 1.5 h on a wrong culprit, and gpt-6-astra as Holmes with 12 Jev boys solved it in 7h 45m.
