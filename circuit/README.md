# Circuit: debugging a CPU with Holmes, Wiggins and the Irregulars

One hardware bug hides in a small pipelined CPU. A test fails. Who finds the faulty block, the signal, the bug type
and the fix with a fixed probe and dollar budget: a swarm of cheap Jev agents that only probe locally, or one
expert model (gpt-6-astra) that reads the whole netlist?

```
python3 run.py circuit            # from the repo root, then open http://127.0.0.1:8783
cd circuit && python3 -m cpudebug # same thing (needs ../common on PYTHONPATH; run.py sets it)
```

## The CPU and the bugs

* **The CPU** (`cpudebug/netlist.py`): 8-bit data, 16-bit instructions, eight registers, 64 bytes of memory, a
  5-stage pipeline (IF, ID, EX, MEM, WB) with EX/MEM and MEM/WB forwarding, a WB-to-ID bypass, a load-use stall and
  branches resolved in EX. It is a pure-Python netlist of **96 blocks**: field decoders, control decoders, the register
  file (8 registers, 2 read muxes, 2 bypasses), the hazard unit, ~45 pipeline registers, forwarding units and muxes,
  an ALU split into nibble adders, subtractor, logic, comparator and shifters, a branch unit, data memory and
  write-back. Each block has a spec (one line of text plus an executable reference) and named ports wired to nets.
* **The ISA and tests** (`cpudebug/isa.py`): an assembler, a golden one-instruction-at-a-time interpreter, and
  nine test programs (forwarding chains, logic and shifts, loads and stores, loops, Fibonacci, a max scan, a register
  sweep, a forwarding mix, a multiply loop). The bug-free netlist passes all nine.
* **One bug per seed**: one param of one combinational block is changed. Four types: **stuck-at** wire (an output
  bit stuck at 0/1), **swapped mux** inputs, **wrong forwarding** / bypass / hazard path, **off-by-one** (adder carry-in,
  pc increment, branch target, comparator `<` vs `<=`, shift amount, instruction field position, sign bit).
  Bug types rotate with the seed; a seed is rerolled until at least one test fails. 530 faults are in the catalogue;
  the test suite catches 488 of them (all swapped-mux and off-by-one faults, 11/12 forwarding faults).
  Registers, the memory and the ROM are "verified IP" and never broken.

## How the investigators work

The failing test's waveform is available to everyone (reading it is free). What costs a **probe** is comparing a
block with its spec:

* `check(block, cycle)`: for every cycle in a window (default 4 cycles), the block's inputs, its actual outputs and
  the spec's outputs for those same inputs.
* `drive(block, kind)`: the block alone on the bench with corner, sweep, boundary or random vectors.

A block that matches its spec but carries wrong values is innocent: the bad value came from upstream. The
**dynamic back-slice** follows the values that actually carried the wrong result (through a mux only the selected
input, through a register the value it loaded or held), starting at the first wrong retired instruction.

* **Scatter**: Holmes, through Wiggins' back-trace, hands each Irregular one block (with the cycles where the slice
  passes through it) or one window of the waveform with a few blocks in it. Irregulars only probe locally and report.
* **Gather**: Wiggins keeps the suspicion map. He walks back from the failing output through every block-cycle that
  was checked and found innocent; the first unchecked block-cycles are the next frontier. A suspect whose bad cycles
  are downstream of another suspect is a **red herring**.
* **Deduce**: Holmes names block + signal + bug type and the fix (the param to put back to spec). The fix is graded by
  re-running all nine tests.

| Mode | Probe choice | Verdicts and tally | Deduction | Cost |
|---|---|---|---|---|
| `jev` Jev swarm | Jev per Irregular | Jev's own reading (noul "is it broken?") | Jev Holmes picks culprit and fix | ~$0.001-0.003 / case |
| `hybrid` hybrid swarm | Jev (and which input to follow) | exact | exact fault fitting | ~$0.001-0.003 / case |
| `cone` exact cone tracing | nearest unchecked block-cycle, one at a time | exact | exact fault fitting | free |
| `rule_swarm` | the swarm machinery with rules | exact | exact | free |
| `genius` solo | gpt-6-astra: whole netlist + failing test + free waveform reads, its own probes | itself | itself | same $ budget |

Metrics: faulty block found, exact location (block + signal), bug type, fix passes all tests, probes used, $ spent.

## The viewer

The launch screen sets every hyperparameter (mode, bug number and type, probe window, probe and dollar budgets,
swarm size, probes per Irregular, rounds, assignment style, Jev thresholds, genius turns, models, key files, prices)
and previews the failing test. The live view shows the schematic with the suspicion heat map (green cleared, amber
unsure, red suspect, blue rings = next on the back-trace), the Irregulars walking to their blocks, probe flashes, a
pipeline diagram of the failing test with the checked windows, Wiggins' notebook, and the event log. Pause, step and
change the speed live; click a block to see its spec and a free look at its values, and name your own suspect
to compare with the investigators at the end.

## Pilot (2026-10-03)

5 bugs, 40 probes and $0.40 per case for every mode ([write-up](docs/pilot_2026-10-03.md)):

| Mode | Exact location | Fix passes tests | Probes (mean) | $ per case |
|---|---|---|---|---|
| Jev swarm | 5/5 | 4/5 | 16.8 | $0.0013 |
| Hybrid swarm | 5/5 | 5/5 | 22.8 | $0.0014 |
| Exact cone tracing | 4/5 | 4/5 | 22.2 | $0 |
| Rule swarm | 5/5 | 5/5 | 29.2 | $0 |
| Solo genius (gpt-6-astra) | 5/5 | 5/5 | 1.0 (plus free waveform reads) | $0.0577 |

## Files

```
cpudebug/isa.py       ISA, assembler, golden interpreter, the nine tests
cpudebug/netlist.py   96-block netlist, simulator, fault catalogue, test runner
cpudebug/case.py      seeded case, probes (check / drive), dynamic back-slice, frontier, fault fitting, grading
cpudebug/agents.py    Irregulars (Jev / rule), Wiggins, Holmes (Jev / exact), the genius
cpudebug/engine.py    run loop, pacing, budgets, frames, run logs (runs/, not committed)
cpudebug/server.py    launch screen + live viewer (stdlib HTTP, Server-Sent Events)
cpudebug/batch.py     headless runs: python3 -m cpudebug.batch --modes jev,hybrid,cone,genius --seeds 1-5
tests/test_checks.py  offline checks (no model calls)
docs/                 pilot write-ups
```

Keys are read from `~/.credentials/openrouter_api_key` (Jev) and `~/.credentials/llm_api_key` (gpt-6-astra) at call
time and are never logged or written to run logs.
