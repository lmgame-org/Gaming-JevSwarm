# Circuit: the problem setup, and whether it is really divide-and-conquer

This page describes exactly what an investigator faces in the circuit-debugging game. It then answers, with
measurements on 100 hardened cases, whether the problem can be split into independent local sub-problems.

## 1. The CPU

A pure-Python netlist of **96 blocks joined by 209 wires** (`cpudebug/netlist.py`). It is an 8-bit, 5-stage pipelined
CPU:
- 16-bit instructions, eight registers (r0 is always 0), 64 bytes of data memory.
- EX/MEM and MEM/WB forwarding to EX, a WB-to-ID register bypass, and a one-cycle load-use stall.
- Branches resolved in EX (predict not taken; two younger instructions flushed).

Each block has named input ports wired to nets (a net is `<driver block>.<port>`), output ports with bit widths, a
one-line spec, and an executable reference: its function with the specified parameters. Registers and memories also
have a next-state function. One clock cycle evaluates the combinational blocks in dependency order, records every
net, then latches every register.

| Stage | Blocks | What they are |
|---|---|---|
| IF (5) | `pc`, `imem`, `pc_inc`, `pc_mux`, `tie_hi` | program counter, instruction ROM, pc+1, next-pc mux (pc+1 or branch target) |
| IF/ID (3) | `ifid_instr`, `ifid_pc`, `ifid_valid` | pipeline latches (flush on a taken branch, hold on a stall) |
| ID decode (8) | `dec_op`, `dec_rd`, `dec_rs1`, `dec_rs2`, `dec_funct`, `sext6`, `imm8`, `imm_mux` | instruction field extractors, sign extension, immediate select |
| ID control (11) | `ctrl_regwrite`, `ctrl_memread`, `ctrl_memwrite`, `ctrl_alusrc`, `ctrl_aluop`, `ctrl_branch`, `ctrl_halt`, `ctrl_usert`, `ctrl_immsel`, `hazard`, `idex_clear` | opcode decoders, the load-use hazard unit, the bubble/flush signal |
| ID registers (13) | `r0`..`r7`, `regb_addr`, `rf_read_a`, `rf_read_b`, `rf_byp_a`, `rf_byp_b` | eight registers, port-B address mux, two 8:1 read muxes, two WB-to-ID bypasses |
| ID/EX (15) | `idex_*` | pipeline latches for control bits, operands, immediate, register numbers, pc |
| EX forwarding + branch (9) | `fwd_a`, `fwd_b`, `fwd_mux_a`, `fwd_mux_b`, `alu_src`, `br_eq`, `br_lt`, `br_decide`, `br_target` | forwarding select logic and 3:1 muxes, ALU-B source mux, branch comparators, decision and target adder |
| EX ALU (11) | `alu_add_lo`, `alu_add_hi`, `alu_add`, `alu_sub`, `alu_and`, `alu_or`, `alu_xor`, `alu_slt`, `alu_shl`, `alu_shr`, `alu_res` | nibble adders with a carry chain, subtract, logic, compare, shifts, 9:1 result mux |
| EX/MEM (9) | `exmem_*` | pipeline latches |
| MEM (1) | `dmem` | 64-byte data memory |
| MEM/WB (8) | `memwb_*` | pipeline latches |
| WB (3) | `wb_mux`, `wb_guard`, `wb_dec` | write-back select, r0 guard, one-hot write decoder |

- **47 blocks are "verified IP"** (registers, pipeline latches, memories, the ROM, a constant) and are never broken.
- **The other 49 combinational blocks** are where bugs live.
- **Wiring** follows the pipeline left to right, with feedback wires:
  - branch decision → `pc_mux` and the flush inputs;
  - EX/MEM and WB results → the forwarding muxes;
  - WB → the register file and bypasses;
  - `hazard.go` → the pc and IF/ID enables.

## 2. The tests

Nine programs (`cpudebug/isa.py`):

| Test | What it exercises |
|---|---|
| arith_chain | back-to-back adds and subtracts |
| logic_shift | logic, shifts, compare |
| load_store | loads, stores, a load-use stall |
| loop_sum | a backward branch loop |
| fibonacci | memory writes in a loop |
| max_scan | a max scan with two branch kinds |
| reg_sweep | every register written and read |
| forward_mix | double writes, stores whose rt field must not forward |
| countdown_mul | a multiply loop |

A golden interpreter executes each program one instruction at a time; a test passes when the pipelined netlist halts
with the same registers and memory. The bug-free netlist passes all nine.

## 3. How a bug is made

Each block's spec is a set of parameters. A bug changes one of them. The full catalogue has 530 faults:

| Type | How it is injected | Example |
|---|---|---|
| stuck-at wire | one output bit forced to 0 or 1 after the block computes | `alu_shr.out` bit 1 stuck at 1 (seed 4) |
| swapped mux inputs | two data inputs of a mux exchanged | `fwd_mux_a` inputs 1 and 2 swapped: EX/MEM and WB forwarded values trade places (seed 1) |
| wrong forwarding / hazard path | a flag in a forwarding, bypass or hazard unit flipped | `fwd_b` gives MEM/WB priority over EX/MEM, so the older value is forwarded (seed 2) |
| off-by-one | an adder constant, comparator, shift amount, field position or sign bit moved by one | `br_lt` computes `A <= B` instead of `A < B` (seed 3); `dec_rs1` reads bits 7:5 instead of 8:6 |

**How a seed picks its case:**
- **Type:** the bug type rotates with the seed (seed mod 4); the fault within that type is random.
- **Rare trigger:** with probability 0.4 the fault fires only when a hash of the block's inputs is 0 mod 3.
- **Second bug:** with probability 0.2 a second, non-stuck fault goes into another block. Each bug alone must break a
  test, so both must be fixed.
- **Retry:** a seed is retried until some test fails.
- **The waveform handed out:** the longest failing test's, preferring one whose back-trace reaches every bug.

Over seeds 1-100: 25 two-bug cases, rare-trigger bugs in about 40%, test length 19-199 cycles (median 142).

## 4. What an investigator sees at the start

- **The failure, from the final state only:** for example "loop_sum fails: it never reached HALT within 133 cycles;
  at the end r2 = 0 (expected 45), mem[5] = 0 (expected 45)". Not which instruction went wrong first, or when.
- **The test results:** which of the nine tests failed and which passed.
- **The program listing and the pipeline occupancy:** which pc is in which stage at every cycle.
- **The netlist:** every block, its spec, its ports, its wiring, and its fault keys (the parameters that could be
  wrong).
- **The back-trace start points**, for example `r2@132`: where the wrong final values sit. From these, the planners
  compute the dynamic back-slice for free. It follows the values that actually carried the result (through a mux only
  the selected input, through a register the value it loaded or held) and has a median of 3,018 block-cycles over 40
  of the 49 suspect blocks.

## 5. What a probe returns and costs

Every probe costs one tick (15 minutes of bench time). Walking to a block more than three schematic columns away
costs one more tick.

- `check(block, cycle)`: for each cycle in a 2-cycle window, the block's inputs, its outputs as measured, and the
  outputs its spec gives for those inputs. A block is innocent if it matches its spec, even when its values are wrong
  for the program; it was fed bad values. **Measurement noise:** each row has a 5% chance of one glitched output bit.
- `drive(block, kind)`: the block alone on the bench, with up to 16 vectors of one kind:
  - `corner`: 0, all ones, 0x55, 0xAA, ...
  - `sweep`: the select or opcode stepped through every value;
  - `boundary`: a = b, a = b±1, 0, 255;
  - `random`.

  It returns measured vs spec outputs for each vector, with the same noise.
- `read(net, cycles)`: raw waveform values. Used by the solo genius; costs a probe.

**Budgets:**
- **Solo:** 10 probes in 6 hours.
- **Baker Street:** 12 boys acting in parallel for 24 ticks, about 100-160 probes in practice. Holmes and Wiggins
  move reports by legs.
- **Swarm:** 100 Irregulars acting in parallel for 24 ticks.
- **Model spend:** capped at $0.75 per case for every family.

## 6. How answers are graded

**What an answer is:** up to two fixes, each a (block, output signal, bug type, fault key). Applying a fix puts that
parameter back to spec. All nine tests are re-run.

**What is scored:**
- **Solved:** every test passes.
- **Block / signal / type:** every bug's block, its affected output and its type was named.

**Loophole:** naming an innocent block costs nothing, because putting an already-correct parameter "back" changes
nothing. The two-fix cap is the only limit on shotgun answers.

## 7. Hardening knobs (defaults)

| Knob | Default | Effect |
|---|---|---|
| `failure_info` | final | only the final wrong values (the easy setting gives the first wrong instruction and its cycle) |
| `test_pick` | longest | the longest failing test (easy: shortest) |
| `window` | 2 | cycles per check (easy: 4) |
| `noise` | 0.05 | glitched-bit chance per measured row |
| `rare_frac` | 0.4 | share of rare-trigger bugs |
| `double_frac` | 0.2 | share of two-bug cases |
| `liar_frac` | 0.1 | bribed boys or lying Irregulars: they hide the real bug and push one coordinated frame-up |
| `liar_defence` | on | a mismatch needs two sources reading the same wrong value; outvoted or contradicted sources lose trust; swarm plausibility and quorum hygiene |
| `deadline_hours` / `tick_min` | 6 / 15 | 24 ticks for every family |
| `probe_budget` | 10 | solo only |
| `budget_usd` | 0.75 | model spend cap per case |

## 8. Is it really divide-and-conquer solvable?

**Short answer: yes. Too easily, and not in the way our agents attack it.** A bug lives inside one block (or two
independent blocks). Every other block meets its spec exactly. Whether a block is guilty is therefore a local
question with a local test. The search splits into 49 independent sub-problems that need no communication. Our
agents mostly do something else: they trace back from the failure, which is the sequential route.

### Is each check local?

- **Comparing against the spec is fully local.** A `check` needs only that block's inputs and outputs at the probed
  cycles. A `drive` needs nothing but the block and its spec: no waveform, no upstream context.
- **Choosing *where and when* to check is global.** A block shows its bug only on cycles where the bad case is
  exercised: a stuck bit that should have differed, a swapped mux whose inputs differ, a comparator at equality.
  Finding those cycles in the failing test means following the back-slice from the wrong final values. That needs
  the whole waveform, and "innocent but fed wrong values" pushes you upstream one step at a time.
- So in-situ checks are local tests with a global targeting problem. Bench drives are local tests with no targeting
  problem.

### Measurements

100 hardened seeds, perfect knowledge (no noise, no liars, exact checks) unless stated.
[parallelism_100seeds.csv](parallelism_100seeds.csv), [bench_sweep_100seeds.csv](bench_sweep_100seeds.csv),
tools in `circuit/tools/`.

| Strategy | Rounds | Probes | Finds the bug |
|---|---|---|---|
| One check per suspect block at its latest back-slice cycle, all in parallel | 1 | 49 | 74/100 (some bug block mismatches) |
| Bench drives of every suspect block × 4 vector kinds, all in parallel | 1 | 196 | 89/100 (every bug block mismatches) |
| Check every back-slice block-cycle once (exhaustive in-situ) | 1 | median 1,700 (p90 2,627) | 86/100 |
| Perfect back-tracer, whole frontier in parallel each round | median 4 (p10 2, p90 8, max 16) | median 230 (p90 2,547) | 100/100 |
| Perfect back-tracer, one probe at a time | = probes | median 92 (p10 7, p90 1,341) | 100/100 |
| **Bench sweep with the hardened noise, then a confirming re-drive, then fault fitting** | **2** | **mean 264** | **80/100 fixed** (82 right block; 17 of 25 two-bug cases) |

What this says:

- **Embarrassingly parallel works.** A blind unit-test sweep needs no back-trace, no waveform and no coordination
  beyond "everyone take a block". In two rounds of about 264 probes it fixes 80/100 hardened cases, including 17 of
  the 25 two-bug cases. That is better than every agent setting in the benchmark (best: solo gpt-6-astra, 14/20).
  - With 100 swarm Irregulars, the sweep takes about 3 ticks.
  - With 12 Baker Street boys, about 22 ticks, which fits the 24-tick clock.
  - With the solo budget of 10 probes it is impossible.
- **The sequential part is short in rounds but explodes in width.** A perfect back-tracer needs a median of only 4
  rounds of parallel frontier checks (at most 16). But the frontier fans out, so it spends a median of 230 probes
  (p90 2,547). One probe at a time, a perfect tracer needs a median of 92 probes. 19 of 100 cases fall within 10
  probes, which explains why the solo debuggers sometimes win with 10 probes and usually don't.
- **Our agents underuse the parallel route.**
  - Baker Street boys and swarm Irregulars spend most probes on back-trace windows and use bench drives only to
    confirm.
  - Holmes plans from the back-trace frontier.
  - The swarm's rule walks upstream from wherever it stands.
  - That is why the swarm, which has the most parallel capacity, scores lowest.

### Verdict

As built, the problem is divide-and-conquer friendly in the trivial sense: per-block conformance testing solves most
of it. The interesting search (back-tracing from symptoms) is optional. The benchmark currently measures how well
each family follows the back-trace under noise and liars, not whether splitting the work pays off.

### What would make it a real divide-and-conquer test

1. **Make local unit tests scarce or partial**, so blind sweeping isn't free:
   - charge a bench drive 3-4 ticks, or give the bench only a few slots;
   - or let a drive cover only one input region, so a rare-trigger bug needs the right region from the trace.

   Splitting would then pay only if agents use the trace to pick where to look.
2. **Scale the chip past one investigator's reach.** At 1,000+ blocks (several cores, caches, a bus), a sequential
   tracer and a lone expert run out of time, while a parallel sweep or a parallel frontier still fits. This tests
   whether a swarm exploits its width.
3. **Add bugs that no local test can see**, which bound what divide-and-conquer can do:
   - interface bugs where two blocks each meet their own spec but disagree on a convention (bit order, active-low
     enable);
   - timing bugs in which cycle a register loads;
   - spec errata.

   These need integration reasoning across blocks: the "conquer" step, not just the "divide".
4. **Close the grading loophole:** penalise every fix on an innocent block, so shotgun answers lose.

Doing (1) and (2) together would make the benchmark measure what the question asks: when the work must be split
because no one can do it alone, and local evidence must be targeted by global reasoning, which family splits it best?
Doing (3) as well would add a further dimension that the current version doesn't cover.
