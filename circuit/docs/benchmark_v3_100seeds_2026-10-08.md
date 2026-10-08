# Circuit v3: the 12-core chip, 100 seeds, 8 October 2026

v3 is a new difficulty tier, designed from [problem_setup.md](problem_setup.md) section 8 after v2 turned out to be
solvable by a blind parallel sweep (80/100). The easy and v2 tiers stay selectable on the launch screen. Per-case
rows: [benchmark_v3_100seeds_2026-10-08.csv](benchmark_v3_100seeds_2026-10-08.csv).

## What changed from v2

- **A chip of 1,187 blocks.** 12 cores, each the 96-block CPU, each running its own program (the eight short tests;
  fibonacci is left out). Each core has a signature unit: a mixer (logic) plus a MISR register. An XOR tree of 11
  logic blocks folds the 12 signatures into the chip signature. That's about 2,500 wires.
- **A global first step.** Investigators learn only that the chip signature is wrong, plus each core's golden
  signature. Reading one core's signature and its final-state differences (`SIG:c<k>`) costs a probe. A group reads
  all 12 in one tick; one investigator needs up to 12 probes.
- **Cross-block bugs (38 of 100 cases).** A wire inside a core is faulty: it delivers last cycle's value (a
  load-timing bug), or the receiver reads it bit-reversed or inverted (an interface mismatch). Both blocks meet their
  specs, so no block check or bench drive can see it. A link probe on the wire can, and so can cross-block
  reasoning: the notebook clears a wire when both of its ends were observed agreeing.
- **Scarce, partial bench tests.** A drive takes 3 ticks and one of 2 bench slots shared by the whole team. It covers
  4 vectors from one input region; the `trace` region replays what the block saw at a chosen cycle. Rare-trigger
  bugs fire for 1 input pattern in 4.
- **Penalty.** Up to 3 fixes; any fix that names an innocent block or wire makes the answer wrong.
- **Defaults:**

  | Setting | v3 | v2 |
  |---|---|---|
  | Check window | 4 cycles | 2 |
  | Clock | 8 h (32 ticks) | 6 h |
  | Solo budget | the clock (32 probes) | 10 |
  | Swarm quorum | 12% | 30% |

  Noise (5%), liars (10%), rare-trigger (40%) and two-bug (20%) shares are unchanged.
- **Families.** Solo and swarm got the plumbing for the new probes. Baker Street keeps its v2 design and strategy
  (Holmes, Wiggins, 12 boys; counting or gpt-6-astra Holmes). It only got the new probe kinds as actions, a
  condensed chip description in Holmes's prompt, bench-slot timing, and positions for wire and signature probes.
- **Shared notebook: v3-only evidence rules, used by every family.**
  - Each source counts once per reading point.
  - A single glitch among a source's agreeing readings is not a lie.
  - A wire is cleared when both ends were observed agreeing.

  Without them the signature and wire probes don't work.
- **Not implemented: spec errata.** No probe could ever detect them, so they would only add guessing.

## Calibration

- **Blind sweep baselines** ([bench_sweep_v3_100seeds.csv](bench_sweep_v3_100seeds.csv), tool
  `tools/bench_sweep_v3.py`):

  | Sweep | v3 | v2 |
  |---|---|---|
  | Blind parallel bench sweep | 0/100 | 80/100 |
  | Read signatures first, then sweep the bad core | 9/100 | - |

  The bench allows about 21 drives in 8 hours, against 588 logic blocks. Wire bugs have no bench test.
- **Oracle, perfect knowledge** ([parallelism_v3_100seeds.csv](parallelism_v3_100seeds.csv), tool
  `tools/parallelism_v3.py`):

  | Tracer | Median | p90 | v2 median |
  |---|---|---|---|
  | One probe at a time: probes | 194 | 691 | 92 |
  | Whole frontier in parallel: rounds | 5 | 13 | - |
  | Whole frontier in parallel: probes | 208 | - | - |

  Only 12 of 100 cases are within 32 probes, one person's clock.
- **Bugs fixed on the way:**
  - the signature register kept rotating after its core halted, so clean cores read bad;
  - the search could enter all cores through the signature tree;
  - a single glitch could get an honest boy distrusted;
  - register-hold chains were checked one cycle at a time.

## Results

| Setting | Solved (95% CI) | Block / signal / type / fix | Case time p50 / p90 | Ran to deadline | Real time p50 / p90 | Calls / case | Cost / case | Wrong quorums |
|---|---|---|---|---|---|---|---|---|
| Solo · gpt-6-astra | 39/82 (0.37-0.58) | 49 / 49 / 48 / 39 | 8.0 h / 8.0 h | 79 | 38.9 s / 57.8 s | 6 | $0.222 | - |
| Solo · Jev | 1/100 (0.00-0.05) | 5 / 5 / 4 / 1 | 3.5 h / 5.5 h | 16 | 2.7 s / 4.2 s | 9 | $0.0003 | - |
| Solo · rule (cone tracing) | 7/100 (0.03-0.14) | 7 / 7 / 7 / 7 | 8.0 h / 8.0 h | 92 | 0.1 s / 0.2 s | 0 | free | - |
| Solo · random | 2/100 (0.01-0.07) | 2 / 2 / 2 / 2 | 8.0 h / 8.0 h | 100 | 0.1 s / 0.2 s | 0 | free | - |
| Baker Street · gpt-6-astra Holmes, Jev boys | 19/99 (0.13-0.28) | 22 / 22 / 18 / 19 | 8.0 h / 8.0 h | 99 | 73.7 s / 96.4 s | 185 | $0.150 | - |
| Baker Street · gpt-6-astra Holmes, rule boys | 23/97 (0.16-0.33) | 29 / 29 / 21 / 23 | 8.0 h / 8.0 h | 97 | 57.9 s / 86.8 s | 6 | $0.157 | - |
| Baker Street · counting Holmes, Jev boys | 15/100 (0.09-0.23) | 16 / 16 / 15 / 15 | 8.0 h / 8.0 h | 92 | 11.5 s / 14.5 s | 173 | $0.0049 | - |
| Baker Street · counting Holmes, Jev boys, no Wiggins | 18/100 (0.12-0.27) | 19 / 19 / 19 / 18 | 8.0 h / 8.0 h | 90 | 10.9 s / 12.8 s | 138 | $0.0038 | - |
| Baker Street · counting Holmes, rule boys | 24/100 (0.17-0.33) | 25 / 25 / 24 / 24 | 8.0 h / 8.0 h | 80 | 0.2 s / 0.3 s | 0 | free | - |
| Baker Street · counting Holmes, rule boys, no Wiggins | 23/100 (0.16-0.32) | 24 / 24 / 23 / 23 | 8.0 h / 8.0 h | 77 | 0.2 s / 0.3 s | 0 | free | - |
| Baker Street · counting Holmes, random boys | 11/100 (0.06-0.19) | 11 / 11 / 11 / 11 | 8.0 h / 8.0 h | 91 | 0.2 s / 0.2 s | 0 | free | - |
| Swarm · rule · 2 wires | 0/100 (0.00-0.04) | 0 / 0 / 0 / 0 | 8.0 h / 8.0 h | 96 | 0.6 s / 0.7 s | 0 | free | 4 |
| Swarm · random · 2 wires | 0/100 (0.00-0.04) | 0 / 0 / 0 / 0 | 2.5 h / 4.5 h | 2 | 0.2 s / 0.4 s | 0 | free | 98 |
| Swarm · Jev · 2 wires | 0/100 (0.00-0.04) | 0 / 0 / 0 / 0 | 3.2 h / 8.0 h | 31 | 1.2 s / 2.6 s | 8 | $0.0004 | 69 |
| Swarm · hybrid · 2 wires | 0/100 (0.00-0.04) | 0 / 0 / 0 / 0 | 8.0 h / 8.0 h | 99 | 1.8 s / 3.2 s | 8 | $0.0004 | 1 |
| Swarm · rule · 4 wires | 0/100 (0.00-0.04) | 0 / 0 / 0 / 0 | 8.0 h / 8.0 h | 98 | 0.7 s / 0.8 s | 0 | free | 2 |

**The gpt-6-astra rows stopped at their spend guards:**

| Setting | Seeds run | Missing seeds |
|---|---|---|
| Solo gpt-6-astra | 82 | 42-50 and 92-100 (each half of its lane ran out) |
| Baker Street, gpt-6-astra Holmes, Jev boys | 99 | 100 |
| Baker Street, gpt-6-astra Holmes, rule boys | 97 | 49, 50, 100 |

On the same 82 seeds as solo gpt-6-astra:

| Setting | Fixed |
|---|---|
| Solo gpt-6-astra | 39/82 |
| Counting Holmes, rule boys | 18/82 |
| gpt-6-astra Holmes, rule boys | 17/82 |
| gpt-6-astra Holmes, Jev boys | 16/82 |
| Solo rule | 6/82 |

**By bug kind** (fixed / cases):

| Setting | Wire bugs | Block bugs | Two-bug cases | Right block, wrong fix |
|---|---|---|---|---|
| Solo gpt-6-astra | 18/32 | 21/50 | 0/15 | 10 |
| Baker, gpt-6-astra Holmes, rule boys | 9/38 | 14/59 | 2/19 | 6 |
| Baker, gpt-6-astra Holmes, Jev boys | 7/38 | 12/61 | 0/19 | 3 |
| Baker, counting Holmes, rule boys | 7/38 | 17/62 | 0/19 | 1 |
| Baker, counting Holmes, Jev boys | 5/38 | 10/62 | 0/19 | 1 |
| Solo rule | 3/38 | 4/62 | 0/19 | 0 |
| Swarm, rule, 2 wires | 0/38 | 0/62 | 0/19 | 0 |

Wrong quorums:
- Jev swarm: 69, nearly always the liars' frame-up.
- Random swarm: 98.
- Rule swarm: 4 (2 wires) and 2 (4 wires).
- Hybrid: 1.

## What it shows

1. **The divide-and-conquer shortcut is gone.** The blind sweep that solved 80% of v2 solves 0% of v3. Splitting the
   work now pays only when global reasoning targets it:
   - the signature reads point to the bad core;
   - the back-trace inside it points to the next block or wire to check.
2. **The expert alone leads: solo gpt-6-astra fixed 39/82** (0.37-0.58).
   - It reads signatures selectively, goes straight to the bad core, and reasons about wires. It fixed 18 of its 32
     wire-bug cases, against at most 9 for anyone else.
   - It is the only setting where a lone investigator is not crushed by the bigger chip: the solo rule fixes 7/100,
     solo Jev 1/100.
   - It still runs to the deadline in 79 of 82 cases, and in 10 cases it named the right block with the wrong fix.
3. **Baker Street is the best team, and the best free setting.**
   - Counting Holmes with rule boys fixes 24/100 at no cost. With Jev boys: 15-18/100 for /bin/zsh.004-0.005 a case.
     With random boys: 11/100.
   - Wiggins makes no difference (24 vs 23 with rule boys, 15 vs 18 with Jev boys).
   - A gpt-6-astra Holmes (19-23/100 at /bin/zsh.15 a case) does not beat counting at Baker Street, as on v2. With the
     same unchanged strategy, the team also falls far behind the lone expert on v3: 18/82 against 39/82 on the
     same seeds.
4. **Leaderless swarms reach 0/100 on the big chip.** This is structural, not a tuning problem:
   - About 8 of the 100 Irregulars live in any one core, and radio does not cross cores.
   - A quorum must outnumber the liars (10%). No single core holds enough honest witnesses to reach it.
   - The rule and hybrid swarms end without a quorum (96-99 cases). The Jev swarm is talked into the liars'
     frame-up 69 times.
   - Rescuing it would take a leader-like broadcast, which is what the swarm family is meant to do without.
5. **Two-bug cases are nearly unsolved** (2 of 19 at best). After finding one bug, every family stops.
6. **Cost per fixed case:**

   | Setting | Cost per fixed case |
   |---|---|
   | Counting Holmes, rule boys | free |
   | Counting Holmes, Jev boys | $0.03 |
   | Solo gpt-6-astra | $0.47 |
   | Baker Street, gpt-6-astra Holmes | $0.67-0.78 |

## Spend

$49.17 for v3, under the $50 guard:

| Setting | Spend |
|---|---|
| Solo gpt-6-astra | $18.17 |
| Baker Street, gpt-6-astra Holmes, rule boys | $15.23 |
| Baker Street, gpt-6-astra Holmes, Jev boys | $14.80 |
| All Jev rows together | about $1 |

Jev ran with 0 fallbacks.

## Caveats

- Solo gpt-6-astra has 82 seeds, not 100, and the missing seeds are two contiguous blocks. Its interval is wider and
  its comparison with the 100-seed rows is approximate. The same-seed comparison above avoids that.
- The v3-only notebook rules apply to every family, including Baker Street's counting Holmes.
- One chip layout and one 8-hour clock. The clock was calibrated on the free rows (perfect tracers need a median of
  194 probes), so families that can't parallelise are expected to fail most cases.

## Reproduce

```
cd circuit && export PYTHONPATH=.:../common
python3 -m cpudebug.batch --settings solo_rule,baker_rule_rule,swarm_rule_r2 --seeds 1-100 --out docs/x.csv tier=v3
python3 tools/bench_sweep_v3.py --seeds 1-100 --out docs/bench_sweep_v3_100seeds.csv
python3 tools/parallelism_v3.py --seeds 1-100 --out docs/parallelism_v3_100seeds.csv
python3 -m cpudebug.report docs/x.csv
```
