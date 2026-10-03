# Circuit, hardened: 20-case benchmark across solo, Baker Street and swarm, 3 October 2026

The same 20 seeded bugs (seeds 1-20) for every setting, with the hardened defaults. The three families mirror the
Holmes detective game: one debugger, Holmes directing street boys, and a leaderless swarm. Per-case rows:
[benchmark_20seeds_2026-10-03.csv](benchmark_20seeds_2026-10-03.csv).

## The cases

- **Bugs.** 20 cases with 23 bugs: 6 swapped muxes, 5 wrong forwarding / hazard paths, 5 stuck-at wires and 4
  off-by-ones as the first bug.
  - 9 of the 20 cases have a rare-trigger bug, which misbehaves only for one input pattern in three.
  - 3 cases have two bugs, and both must be fixed.
- **What the investigators get.** They learn only the final wrong registers or memory (or that the test never
  halted), plus the longest failing test: 19 to 199 cycles, fibonacci in 6 cases.
- **Measurements.** A check covers 2 cycles. About 1 row in 20 reads one glitched bit.
- **Liars.** 10% of boys and Irregulars are bribed. They hide the real bug and push one coordinated frame-up block.
  The liar defence is on.
- **Clock and money.** Every family has the same 6-case-hour clock: 24 ticks of 15 minutes. One probe or one long walk
  costs one tick. The spend cap is $0.75 per case.
- **Family sizes.** Solo gets 10 probes (genius waveform reads included). Baker Street has 12 boys. The swarm has 100
  Irregulars, quorum 30.

## How it was measured

- **Solved** means every test passes after applying the named fix(es). The interval is a Wilson 95% interval on 20
  cases.
- **Block / signal / type / fix** count cases where every bug's block, output signal and bug type was named, and
  where the fix passed every test.
- **Case time** is simulated bench time to the answer. A swarm without a quorum is counted at the deadline.
- **Ran to deadline** counts cases where the decider never committed early:
  - Solo: probes or time ran out.
  - Baker Street: Holmes was never sure. Solo and Baker Street still give a forced answer, which is scored.
  - Swarm: no quorum, scored as unsolved.
- **Wrong quorums** count swarms that agreed on a wrong answer.
- **Real time** is wall-clock seconds per case, headless, on one Mac.
  - The Jev rows are flagged. OpenRouter's Jev endpoint was shared all day with the Holmes thread's own benchmark
    runs, so single calls took 10-80 s.
  - With a 30-second limit per call, 2-4% of Jev decisions fell back to the rule: 240 of 8,954 calls.
  - Real time for Jev rows reflects that day's contention, not Jev's speed.
- **Cost** is OpenRouter's reported cost for Jev. For gpt-6-astra it is token counts at list price ($10 / M input,
  $1 / M cached, $50 / M output).

## Results

| Setting | Solved (95% CI) | Block / signal / type / fix | Case time p50 / p90 | Ran to deadline | Real time p50 / p90 | Calls / case | Cost / case | Wrong quorums |
|---|---|---|---|---|---|---|---|---|
| Solo · gpt-6-astra | 14/20 (0.48-0.85) | 18 / 18 / 18 / 14 | 1.2 h / 2.5 h | 3 | 18.0 s / 26.0 s | 5 | $0.171 | - |
| Solo · Jev | 3/20 (0.05-0.36) | 3 / 3 / 3 / 3 | 2.8 h / 3.5 h | 15 | 171.2 s / 225.6 s | 9 | $0.0004 | - |
| Solo · rule (cone tracing) | 3/20 (0.05-0.36) | 3 / 3 / 3 / 3 | 2.8 h / 3.2 h | 17 | 0.1 s / 0.2 s | 0 | free | - |
| Solo · random | 2/20 (0.03-0.30) | 2 / 2 / 2 / 2 | 3.5 h / 3.8 h | 20 | 0.1 s / 0.2 s | 0 | free | - |
| Baker Street · gpt-6-astra Holmes, Jev boys | 11/20 (0.34-0.74) | 17 / 17 / 17 / 11 | 6.0 h / 6.0 h | 20 | 473.1 s / 1151.5 s | 155 | $0.143 | - |
| Baker Street · gpt-6-astra Holmes, rule boys | 12/20 (0.39-0.78) | 18 / 18 / 18 / 12 | 6.0 h / 6.0 h | 19 | 33.8 s / 42.3 s | 6 | $0.137 | - |
| Baker Street · counting Holmes, Jev boys | 11/20 (0.34-0.74) | 14 / 14 / 13 / 11 | 4.5 h / 6.0 h | 7 | 293.1 s / 532.7 s | 102 | $0.0027 | - |
| Baker Street · counting Holmes, Jev boys, no Wiggins | 8/20 (0.22-0.61) | 9 / 9 / 9 / 8 | 5.5 h / 6.0 h | 10 | 5.7 s / 7.4 s | 93 | $0.0024 | - |
| Baker Street · counting Holmes, rule boys | 13/20 (0.43-0.82) | 15 / 15 / 14 / 13 | 4.5 h / 6.0 h | 6 | 0.1 s / 0.3 s | 0 | free | - |
| Baker Street · counting Holmes, rule boys, no Wiggins | 12/20 (0.39-0.78) | 14 / 14 / 13 / 12 | 3.8 h / 6.0 h | 3 | 0.1 s / 0.2 s | 0 | free | - |
| Baker Street · counting Holmes, random boys | 9/20 (0.26-0.66) | 10 / 10 / 10 / 9 | 6.0 h / 6.0 h | 10 | 0.1 s / 0.2 s | 0 | free | - |
| Swarm · rule · 2 wires | 6/20 (0.15-0.52) | 6 / 6 / 6 / 6 | 6.0 h / 6.0 h | 12 | 0.3 s / 0.5 s | 0 | free | 2 |
| Swarm · random · 2 wires | 0/20 (0.00-0.16) | 0 / 0 / 0 / 0 | 0.8 h / 1.0 h | 0 | 0.1 s / 0.3 s | 0 | free | 20 |
| Swarm · Jev · 2 wires | 3/20 (0.05-0.36) | 3 / 3 / 3 / 3 | 1.0 h / 6.0 h | 4 | 121.9 s / 628.3 s | 77 | $0.0039 | 13 |
| Swarm · hybrid · 2 wires | 5/20 (0.11-0.47) | 5 / 5 / 5 / 5 | 6.0 h / 6.0 h | 12 | 273.6 s / 730.6 s | 100 | $0.0046 | 3 |
| Swarm · rule · 4 wires | 3/20 (0.05-0.36) | 3 / 3 / 3 / 3 | 6.0 h / 6.0 h | 15 | 0.4 s / 0.4 s | 0 | free | 2 |

### Baker Street, every combination (added on 3 October, evening)

Holmes × boys × Wiggins on the same 20 seeds. Two rows were added after the first run:
- gpt-6-astra Holmes with rule boys;
- counting Holmes with Jev boys and no Wiggins.

| Holmes | Boys | Wiggins | Solved (95% CI) | Block / signal / type / fix | Case time p50 / p90 | Ran to deadline | Calls / case | Cost / case |
|---|---|---|---|---|---|---|---|---|
| gpt-6-astra | Jev | on | 11/20 (0.34-0.74) | 17 / 17 / 17 / 11 | 6.0 h / 6.0 h | 20 | 155 | $0.143 |
| gpt-6-astra | rule | on | 12/20 (0.39-0.78) | 18 / 18 / 18 / 12 | 6.0 h / 6.0 h | 19 | 6 | $0.137 |
| counting | Jev | on | 11/20 (0.34-0.74) | 14 / 14 / 13 / 11 | 4.5 h / 6.0 h | 7 | 102 | $0.0027 |
| counting | Jev | off | 8/20 (0.22-0.61) | 9 / 9 / 9 / 8 | 5.5 h / 6.0 h | 10 | 93 | $0.0024 |
| counting | rule | on | 13/20 (0.43-0.82) | 15 / 15 / 14 / 13 | 4.5 h / 6.0 h | 6 | 0 | free |
| counting | rule | off | 12/20 (0.39-0.78) | 14 / 14 / 13 / 12 | 3.8 h / 6.0 h | 3 | 0 | free |
| counting | random | on | 9/20 (0.26-0.66) | 10 / 10 / 10 / 9 | 6.0 h / 6.0 h | 10 | 0 | free |

- **Holmes decides the location; the counting rule is better at naming the fix.**
  - Both gpt-6-astra rows find the block in 17-18/20 against 9-15/20 for the counting Holmes. But they run to the
    deadline in 19-20 of 20 cases and solve only 11-12/20.
  - Rule boys and Jev boys behave about the same under gpt-6-astra (12 vs 11 solved), so the boys are not the
    bottleneck there.
- **Wiggins matters more with Jev boys.**
  - With Jev boys: 11/20 with Wiggins, 8/20 without.
  - With rule boys: 13/20 with Wiggins, 12/20 without.
  - Without Wiggins each boy walks back to 221B after every errand. Jev boys run back more often (they choose
    RETURN), so they lose more of the clock to walking.
- **The two added rows ran later, when the Jev endpoint was no longer shared:** 0 fallbacks in 1,988 calls, and about
  6 s per case for the no-Wiggins row. Real time for that row is therefore not comparable with the earlier Jev-boys
  row (293 s median).
- **Two-bug cases:** gpt-6-astra Holmes with rule boys also fixed one of the 3, making two Baker Street settings that
  did, both with a gpt-6-astra Holmes.

**Wrong quorums.** All 13 of the Jev swarm's wrong quorums were the liars' frame-up block, and so were all 20 of the
random swarm's. For the other swarms: hybrid 2 of 3, rule 2 of 2 at each range.

**Hard cases.** Two-bug cases were fixed only once in 3: by Baker Street with the gpt-6-astra Holmes. Every other
setting fixed 0 of 3. On the 9 rare-trigger cases:

| Setting | Rare-trigger cases fixed |
|---|---|
| Solo gpt-6-astra | 4 of 9 |
| Counting Holmes, rule boys | 4 of 9 |
| Counting Holmes, Jev boys | 3 of 9 |
| Rule swarm | 2 of 9 |
| gpt-6-astra Holmes | 1 of 9 |
| Hybrid swarm | 1 of 9 |

## What it shows

1. **The hardening works.** The pilot on the easy setting had every mode at 4-5 out of 5. Now the families separate:
   solo 2-14/20, Baker Street 9-13/20, swarm 0-6/20. Nobody beats 14/20.
2. **The genius is the best single investigator.** Solo gpt-6-astra solved 14/20 and found the right block in 18/20,
   at $0.17 a case and a median 1.2 case hours. It fell short on the fix, not the location: the 3 two-bug cases, and
   choosing between faults that explain the same rows. Its edge comes from reading the pipeline timing and choosing
   probes well. With 10 probes, the rule tracer (3/20) and Jev (3/20) run out before the back-trace from the final
   registers gets anywhere.
3. **Baker Street is the most reliable cheap family.** Exact counting with rule boys solved 13/20 for free. With Jev
   boys it solved 11/20 for $0.003 a case. Wiggins helps a little (13 against 12 without him), and boy quality
   matters (random boys 9/20). Twelve boys over 24 ticks make about 100-160 probes, enough to walk the back-trace,
   re-measure every mismatch with a second boy, and outvote the liars. Holmes named the liars' frame-up block once in 100
   Baker Street cases (no Wiggins, rule boys).
4. **A gpt-6-astra Holmes does not beat counting at Baker Street.**
   - It found the block more often (17/20 against 14-15/20) and was the only setting to fix a two-bug case.
   - But with at most 6 planning rounds it never felt sure early, so all 20 cases ran to the deadline and it picked
     the wrong fault more often (11/20 fixed).
   - It cost $0.14 a case, about 50 times the counting Holmes.
5. **The leaderless swarm struggles, and Jev deciding makes it worse.**
   - The rule swarm with liar defence solved 6/20 at 2 wires with only 2 wrong quorums. Its votes need a reproduced
     reading, so it is safe but slow: 12 of 20 cases ended without a quorum.
   - A longer radio (4 wires) hurt (3/20). Each Irregular takes in at most 3 shares a tick, so more voices crowd out
     the useful ones.
   - Jev choosing what to chase and how to vote reached quorums quickly (median 1 case hour), but 13 of 20 were the
     liars' frame-up. Jev votes for well-corroborated fabricated readings that the exact vote would have refused.
   - Hybrid (Jev chases, exact vote) avoided most of that (3 wrong quorums) and solved 5/20.
   - This matches the Holmes game: vote-counting swarms are what liars capture, and range and bandwidth trade off.
6. **Cost per solved case.**

   | Setting | Cost per solved case |
   |---|---|
   | Baker Street, counting Holmes, rule boys | free |
   | Baker Street, counting Holmes, Jev boys | $0.005 |
   | Hybrid swarm | $0.018 |
   | Solo gpt-6-astra | $0.24 |
   | Baker Street, gpt-6-astra Holmes | $0.26 |

## Spend

**Total $9.31** over 320 runs, under the $15 guard:

| Setting | Spend |
|---|---|
| Solo gpt-6-astra | $3.42 |
| Baker Street, gpt-6-astra Holmes, Jev boys | $2.85 |
| Baker Street, gpt-6-astra Holmes, rule boys (added) | $2.75 |
| Jev swarm | $0.08 |
| Hybrid swarm | $0.09 |
| Baker Street, counting Holmes, Jev boys | $0.05 |
| Baker Street, counting Holmes, Jev boys, no Wiggins (added) | $0.05 |
| Solo Jev | $0.01 |

The free settings cost nothing.

## Caveats

- 20 cases. The intervals overlap for most neighbouring rows.
- The Jev swarm consults Jev only for judgment calls: whether to chase a newly confirmed suspect, and what to vote.
  Routine tracing between those calls is the reflex rule. Asking Jev every tick for 100 agents would have needed
  about 1,000 calls per case, roughly 10-20 minutes per case on that day's shared endpoint.
- Jev and hybrid swarms ran only at the 2-wire range; the 4-wire comparison is rule-only.
- The Jev rows had 2-4% fallbacks because of API contention. Their real-time columns are not comparable with the
  others.

## Reproduce

```
cd circuit
export PYTHONPATH=.:../common
python3 -m cpudebug.batch --settings solo_genius,solo_jev,solo_rule,solo_random --seeds 1-20 --out docs/a.csv
python3 -m cpudebug.batch --settings baker_genius_jev,baker_genius_rule,baker_rule_jev,baker_rule_jev_nowiggins,baker_rule_rule,baker_rule_rule_nowiggins,baker_rule_random --seeds 1-20 --out docs/b.csv
python3 -m cpudebug.batch --settings swarm_rule_r2,swarm_random_r2,swarm_jev_r2,swarm_hybrid_r2,swarm_rule_r4 --seeds 1-20 --out docs/c.csv
python3 -m cpudebug.report docs/a.csv docs/b.csv docs/c.csv
```
