# The Irregulars: 20-case benchmark, 2 October 2026

Every main setting on the same 20 seeded cases (seeds 1-20, default case settings: 100 addresses, 10 suspects,
6 motives, 8 hideouts, lie rate 0.1). Per-case rows: [benchmark_20seeds_2026-10-02.csv](benchmark_20seeds_2026-10-02.csv).

## How it was measured

- **Solved** means culprit, motive and hideout all right. The interval is a Wilson 95% interval on 20 cases.
- **Culprit / motive / hideout** counts cases where that part was right. For the self-organising swarms a part
  counts only when the swarm reached a quorum; a swarm that runs out of time has given no answer.
- **Sim time** is simulated case time, in hours, from the start of the case to the final answer.
  - Solo: the cab and interview clock, 12 h limit, 20 visits.
  - Swarms and hybrids: 32 ticks of 15 minutes, an 8 h limit.
  - Baker Street: 48 ticks, a 12 h limit, the same as Solo.
  - **Ran to deadline** counts cases that hit the limit without the decider committing early (Solo: out of visits
    or time; swarms: no quorum; Baker Street: Holmes never sure). At the deadline Solo and Baker Street still give
    a forced answer, which is scored; a swarm without a quorum is scored as unsolved.
- **Real time** is wall-clock seconds from case start to final answer, run headless (the viewer's pacing off), on
  one Mac, with up to 32 model calls in flight. Two lanes ran at the same time: one for the gpt-6-astra settings
  (Solo gpt-6-astra, then Baker Street with gpt-6-astra Holmes), one for everything else (Jev through OpenRouter,
  plus the free settings).
- **Calls / case** counts model calls (Jev or gpt-6-astra). **Cost** is OpenRouter's reported cost for Jev, and
  for gpt-6-astra its token counts at OpenRouter's list price ( / M input,  / M cached,  / M output).

## Results

| Setting | Solved (95% CI) | Culprit / motive / hideout | Sim time p50 / p90 | Ran to deadline | Real time p50 / p90 | Calls / case | Cost / case |
|---|---|---|---|---|---|---|---|
| Solo · gpt-6-astra | 11/20 (0.34-0.74) | 17 / 14 / 19 | 10.9 h / 11.8 h | 13 | 81.3 s / 95.0 s | 19 | $0.347 |
| Baker Street · gpt-6-astra Holmes, Jev boys | 19/20 (0.76-0.99) | 20 / 19 / 20 | 11.2 h / 12.0 h | 8 | 102.0 s / 155.1 s | 109 | $0.615 |
| Solo · Jev | 5/20 (0.11-0.47) | 8 / 12 / 19 | 11.9 h / 12.0 h | 20 | 4.7 s / 5.0 s | 19 | $0.005 |
| Solo · rule | 9/20 (0.26-0.66) | 13 / 16 / 20 | 9.2 h / 11.1 h | 18 | 0.0 s / 0.0 s | 0 | free |
| Solo · random | 0/20 (0.00-0.16) | 1 / 5 / 3 | 11.9 h / 12.0 h | 20 | 0.0 s / 0.0 s | 0 | free |
| Swarm · Jev · 1 km | 5/20 (0.11-0.47) | 7 / 7 / 11 | 4.0 h / 8.0 h | 9 | 16.9 s / 27.0 s | 1352 | $0.171 |
| Swarm · rule · 1 km | 13/20 (0.43-0.82) | 13 / 13 / 13 | 6.5 h / 8.0 h | 7 | 0.3 s / 0.4 s | 0 | free |
| Swarm · random · 1 km | 0/20 (0.00-0.16) | 0 / 0 / 0 | 8.0 h / 8.0 h | 20 | 0.2 s / 0.3 s | 0 | free |
| Swarm · Jev · 2 km | 10/20 (0.30-0.70) | 12 / 17 / 19 | 2.2 h / 5.8 h | 1 | 12.4 s / 32.7 s | 993 | $0.130 |
| Swarm · rule · 2 km | 18/20 (0.70-0.97) | 18 / 18 / 18 | 1.8 h / 8.0 h | 2 | 0.1 s / 0.4 s | 0 | free |
| Hybrid · 1 km | 10/20 (0.30-0.70) | 10 / 10 / 10 | 8.0 h / 8.0 h | 10 | 28.1 s / 37.0 s | 2069 | $0.208 |
| Hybrid · 2 km | 17/20 (0.64-0.95) | 17 / 18 / 18 | 2.5 h / 8.0 h | 2 | 9.7 s / 32.2 s | 1222 | $0.130 |
| Baker Street · counting Holmes, Jev boys | 19/20 (0.76-0.99) | 19 / 20 / 20 | 6.5 h / 10.8 h | 1 | 4.7 s / 6.1 s | 67 | $0.002 |
| Baker Street · counting Holmes, rule boys | 19/20 (0.76-0.99) | 19 / 19 / 20 | 8.2 h / 12.0 h | 6 | 0.0 s / 0.0 s | 0 | free |

Wrong quorums (a swarm agreed on a wrong answer): Jev 1 km 6, Jev 2 km 9, hybrid 2 km 1; none for the rule swarm or
hybrid 1 km. Tokens per case: Solo gpt-6-astra 67k, Baker Street gpt-6-astra Holmes 136k, Solo Jev 139k, Jev
swarms 3.5-4.6M, hybrids 3.2-5.2M, Baker Street with counting Holmes and Jev boys 53k.

## What changed with 20 cases

- **Solo gpt-6-astra is not a sure thing.** It solved all of seeds 1-5 but only 6 of seeds 6-20 (11/20 overall).
  All 9 failures ran out of visits or time: with 20 visits it often had the culprit (17/20) but not a corroborated
  motive (14/20).
- **Holmes at Baker Street fixes that.** The same model as Holmes, with Wiggins and 12 Jev boys doing the
  legwork, solved 19/20. It sees about 70-100 reports per case instead of about 18 visits. It costs more (/bin/zsh.62
  against /bin/zsh.35 per case) and is slower in real time (102 s against 81 s median), because each plan re-reads every
  report.
- **Baker Street with exact counting is the best value:** 19/20 for /bin/zsh.002 per case and under 5 s, naming the
  answer in a median 6.5 case hours.
- **Range still decides the self-organising swarms.** At 2 km the rule swarm solved 18/20 and the hybrid 17/20,
  both in about 2 case hours. At 1 km they solved 13/20 and 10/20. Jev deciding everything stays weak (5/20 and
  10/20), and it reaches wrong quorums (6 and 9).
- **Fastest answers in case time** come from the 2 km swarms (median about 2 h). The most reliable answers come
  from Baker Street (19/20 for both Holmeses).

## Spend

Total $32.16: Solo gpt-6-astra $6.94, Baker Street with gpt-6-astra Holmes $12.30, Jev swarms $6.03, hybrids
$6.76, Solo Jev $0.10, Baker Street with counting Holmes and Jev boys $0.04. No spend guard tripped; every
setting has all 20 cases.

## Reproduce

```
python3 -m irregulars.batch --mode solo  --policies chat jev rule random --seeds 20
python3 -m irregulars.batch --mode swarm --policies jev rule random --seeds 20
python3 -m irregulars.batch --mode swarm --policies jev rule --seeds 20 --set comm_range=200
python3 -m irregulars.batch --mode swarm --policies hybrid --seeds 20            # and --set comm_range=200
python3 -m irregulars.batch --mode swarm --policies baker_street --seeds 20 --set n_irregulars=12 swarm_ticks=48 holmes=chat
python3 -m irregulars.batch --mode swarm --policies baker_street --seeds 20 --set n_irregulars=12 swarm_ticks=48 holmes=rule
python3 -m irregulars.report runs/batch_... --csv out.csv --md out.md
```
