"""One debugging case: seeded bug(s) in the CPU, the failing test, and the tools the investigators may use.

Tools (each `check`, `drive` or waveform `read` costs one probe and one tick of bench time):
  check(block, cycle)   compare the block against its spec over a window of cycles of the failing test:
                        for every cycle, the block's inputs, its outputs as measured and what its spec says the
                        outputs should be for those inputs.
  drive(block, kind)    drive the block alone on the bench with a batch of input vectors (corner, sweep, boundary,
                        random) and compare its measured outputs with its spec.
Registers, the data memory and the instruction ROM are verified IP: the fault model puts each bug in a combinational
block. The dynamic back-slice follows the values that actually carried the wrong result: through a mux only the
selected input, through a register the value it loaded (or held).

Hardening (each a knob, see config.py):
  failure_info = final  the investigators only learn which registers / memory bytes are wrong at the end (or that the
                        test never halted), not which instruction went wrong first or when
  test_pick = longest   they get the longest failing test's waveform, not the shortest
  noise                 each measured row has this chance of one glitched bit (an innocent block can look guilty)
  rare_frac             share of bugs that only misbehave when a hash of the block's inputs is 0 mod 3
  double_frac           share of cases with a second bug in another block; both must be fixed
"""
import heapq
import random
from collections import deque

from .isa import MEM_SIZE, disasm, load_tests
from .netlist import BUG_TYPES, CPU, STAGES, all_faults, apply_fix, build_cpu, mask, retire_diff, run_test

COLS = ["IF", "IF/ID", "ID decode", "ID control", "ID registers", "ID/EX", "EX fwd+branch", "EX ALU", "EX/MEM", "MEM",
        "MEM/WB", "WB"]


def col_of(b):
    if b.stage == "IF":
        return 0
    if b.stage == "IF/ID":
        return 1
    if b.stage == "ID":
        return 2 if b.group == "decoder" else 3 if b.group in ("control", "hazard") else 4
    if b.stage == "ID/EX":
        return 5
    if b.stage == "EX":
        return 7 if b.group == "alu" else 6
    return {"EX/MEM": 8, "MEM": 9, "MEM/WB": 10}.get(b.stage, 11)


class Case:
    def __init__(self, cfg):
        self.cfg = cfg
        self.seed = int(cfg["seed"])
        self.window = max(1, int(cfg.get("window", 2)))
        self.noise = float(cfg.get("noise", 0.0))
        self.final_only = cfg.get("failure_info", "final") == "final"
        self.blocks = build_cpu()
        self.by = {b.name: b for b in self.blocks}
        self.tests = load_tests()
        rng = random.Random(f"circuit-{self.seed}")
        types = [t for t in BUG_TYPES if cfg.get("bug_type", "any") in ("any", t)]
        faults = all_faults(self.blocks)
        rare, double = float(cfg.get("rare_frac", 0.0)), float(cfg.get("double_frac", 0.0))
        for attempt in range(400):
            # bug types rotate with the bug number so consecutive numbers cover all four
            t = types[(self.seed + attempt) % len(types)]
            f1 = dict(rng.choice([x for x in faults if x["type"] == t]))
            if rng.random() < rare:
                f1["trigger"] = 3
            fs = [f1]
            if rng.random() < double:
                f2 = dict(rng.choice([x for x in faults if x["block"] != f1["block"] and x["type"] != "stuck_at"]))
                fs.append(f2)
            if not self._fails(fs):
                continue
            if len(fs) == 2 and not (self._fails([fs[0]]) and self._fails([fs[1]])):
                # each bug alone must also break a test, or it is not a real double bug
                if not self._fails([fs[0]]):
                    continue
                fs = [fs[0]]
            break
        self.faults = [{k: f.get(k) for k in ("block", "key", "value", "type", "port", "desc", "trigger")} for f in fs]
        self.fault = self.faults[0]
        self.cpu = CPU(self.blocks, self.faults)
        res = [(t_, *run_test(self.cpu, t_)) for t_ in self.tests]
        failing = [(t_, tr) for t_, ok, tr in res if not ok]
        self.results = [{"name": t_["name"], "desc": t_["desc"], "ok": ok} for t_, ok, _ in res]
        longest = cfg.get("test_pick", "longest") == "longest"
        failing.sort(key=lambda x: (x[1].n, x[0]["name"]), reverse=longest)
        self.drivers = self.cpu.drivers
        self.spec_p = {b.name: b.eff(None) for b in self.blocks}
        self._adj = None
        self._hops = {}
        # prefer a failing test whose back-slice reaches every bug (a double bug may only show in another test)
        for t_, tr in failing:
            self.test, self.trace = t_, tr
            self.diff = retire_diff(tr, t_["golden"])
            self.n = tr.n
            self.starts = self._starts()
            self._occ = None
            self._slice = None
            if all(f["block"] in self.slice_cycles() for f in self.faults):
                break
        else:
            self.test, self.trace = failing[0]
            self.diff = retire_diff(self.trace, self.test["golden"])
            self.n = self.trace.n
            self.starts = self._starts()
            self._occ = None
            self._slice = None

    def _fails(self, fs):
        cpu = CPU(self.blocks, fs)
        return any(not run_test(cpu, t)[0] for t in self.tests)

    # ------------------------------------------------------------------ public views
    def brief(self):
        """What every investigator is told at the start (no spoilers)."""
        d = self.diff or {}
        out = {"failing_tests": [r["name"] for r in self.results if not r["ok"]],
               "passing_tests": [r["name"] for r in self.results if r["ok"]],
               "test": self.test["name"], "test_desc": self.test["desc"], "cycles": self.n,
               "program": [f"{pc:2d}: {disasm(w)}" for pc, w in enumerate(self.test["prog"])],
               "failure": self.failure_text(), "start_points": [f"{b}@{c}" for b, c in self.starts],
               "first_bad_cycle": None if self.final_only else d.get("cycle")}
        return out

    def final_diffs(self):
        g, tr = self.test["golden"], self.trace
        bad = [f"r{k} = {v} (expected {g['regs'][k]})" for k, v in enumerate(tr.regs) if v != g["regs"][k]]
        bad += [f"mem[{a}] = {v} (expected {g['mem'][a]})" for a, v in enumerate(tr.mem) if v != g["mem"][a]]
        return bad

    def failure_text(self):
        d = self.diff
        if self.final_only:
            bad = self.final_diffs()
            halt = "" if self.trace.halted is not None else f"it never reached HALT within {self.n} cycles; "
            return (f"{self.test['name']} fails: {halt}at the end " + (", ".join(bad[:5]) if bad else
                                                                      "registers and memory are as expected"))
        if not d:
            return "the test failed"
        e, g = d["expected"], d["got"]
        if d["kind"] == "final":
            return "every instruction retired as expected, but at the end " + ", ".join(self.final_diffs()[:4])
        if d["kind"] == "missing":
            return (f"the pipeline stopped retiring after instruction #{d['index']} (expected next: pc {e['pc']} "
                    f"{e['text']}); it never reached HALT within {self.n} cycles")
        what = lambda r: (f"pc {r['pc']} {r['text']}" + (f", writes r{r['rd']} = {r['value']}" if "rd" in r else "") +
                          (f", stores {r['data']} to mem[{r['addr']}]" if "addr" in r else ""))
        return (f"retired instruction #{d['index']} at cycle {d['cycle']} is wrong: expected {what(e)}; "
                f"got {what(g)}")

    def public_blocks(self):
        out = []
        for b in self.blocks:
            d = b.public()
            d["faults"] = [] if b.trusted else sorted({f["key"].split(":")[0] if f["type"] == "stuck_at" else f["key"]
                                                       for f in b.faults})
            out.append(d)
        return out

    def edges(self):
        out = []
        for b in self.blocks:
            for port, net in b.ins.items():
                out.append([self.drivers[net][0], b.name, port])
        return out

    def occupancy(self):
        """Per cycle, the pc in each of the five stages (None for a bubble)."""
        if self._occ is None:
            self._occ = [[(self.trace.instr_at(s, c) or {}).get("pc") for s in ("IF", "ID", "EX", "MEM", "WB")]
                         for c in range(self.n)]
        return self._occ

    def secret(self):
        bugs = [{"block": f["block"], "port": f["port"], "type": f["type"], "key": f["key"], "desc": f["desc"],
                 "type_label": BUG_TYPES[f["type"]], "rare": bool(f.get("trigger"))} for f in self.faults]
        out = dict(bugs[0])
        out["bugs"] = bugs
        return out

    # ------------------------------------------------------------------ probes
    def window_of(self, c):
        lo = max(0, c - (self.window - 1) // 2)
        hi = min(self.n - 1, lo + self.window - 1)
        lo = max(0, hi - self.window + 1)
        return lo, hi

    def check(self, block, c, rng=None):
        """One probe: the block against its spec over the window around cycle c (measured with noise)."""
        b = self.by[block]
        lo, hi = self.window_of(c)
        rng = rng or random.Random(f"check-{self.seed}-{block}-{c}")
        rows = [self._row(b, k, rng) for k in range(lo, hi + 1)]
        return {"type": "check", "block": block, "cycle": c, "window": [lo, hi], "rows": rows,
                "mismatch": any(not r["ok"] for r in rows)}

    def _glitch(self, b, out, rng):
        """Measurement noise: with probability `noise`, one bit of one output reads wrong."""
        if self.noise <= 0 or rng.random() >= self.noise or not b.outs:
            return out, False
        port = rng.choice(sorted(b.outs))
        out = dict(out)
        out[port] ^= 1 << rng.randrange(b.outs[port])
        return out, True

    def _row(self, b, k, rng):
        tr = self.trace
        inp = tr.inputs(b.name, k)
        out = tr.outputs(b.name, k)
        if b.trusted:
            exp, ok, gl = dict(out), True, False
        else:
            exp = b.eval(self.spec_p[b.name], inp, None)
            out, gl = self._glitch(b, out, rng)
            ok = exp == out
        ins = tr.instr_at(b.stage if b.stage in STAGES else "ID", k)
        return {"cycle": k, "in": inp, "out": out, "spec": exp, "ok": ok, "instr": ins, "_glitch": gl}

    def drive(self, block, kind, rng=None):
        """One probe: drive the block alone with a batch of vectors (measured with noise)."""
        b = self.by[block]
        vrng = random.Random(f"drive-{self.seed}-{block}-{kind}")
        rng = rng or vrng
        p_act = self.cpu.params(b)
        rows = []
        for inp in self.vectors(b, kind, vrng):
            out = self.cpu.eval_block(b, inp, None, p=p_act, spec=self.spec_p[block])
            exp = b.eval(self.spec_p[block], inp, None)
            out, gl = (out, False) if b.trusted else self._glitch(b, out, rng)
            rows.append({"cycle": None, "in": inp, "out": out, "spec": exp, "ok": out == exp, "instr": None,
                         "_glitch": gl})
        return {"type": "drive", "block": block, "kind": kind, "rows": rows,
                "mismatch": any(not r["ok"] for r in rows)}

    def read(self, net, lo, hi):
        """One probe: a net's values over cycles lo..hi (at most 16)."""
        lo = max(0, int(lo))
        hi = min(self.n - 1, int(hi), lo + 15)
        return {k: self.trace.vals[k][net] for k in range(lo, hi + 1)}

    def widths(self, b):
        return {port: self.blocks_out_width(net) for port, net in b.ins.items()}

    def blocks_out_width(self, net):
        d, port = self.drivers[net]
        return self.by[d].outs[port]

    def vectors(self, b, kind, rng):
        w = self.widths(b)
        ports = list(w)
        if not ports:
            return [{}]
        sel_ports = [p for p in ports if p in ("sel", "op", "type", "addr") or w[p] <= 2 and p not in ("a", "b")]
        data_ports = [p for p in ports if p not in sel_ports]
        vecs = []
        if kind == "corner":
            for pat in (0x00, 0xFF, 0x55, 0xAA, 0x0F, 0xF0):
                vecs.append({p: pat & mask(w[p]) for p in ports})
            for p in sel_ports:
                for v in range(min(1 << w[p], 4)):
                    base = {q: (0x5A if q != p else v) & mask(w[q]) for q in ports}
                    vecs.append(base)
        elif kind == "sweep":
            sp = sel_ports[0] if sel_ports else None
            values = range(min(1 << w[sp], 16)) if sp else range(1)
            for v in values:
                vec = {p: ((17 * (k + 1) + 3) & mask(w[p])) for k, p in enumerate(data_ports)}
                if sp:
                    vec[sp] = v
                for q in sel_ports[1:]:
                    vec[q] = 1 & mask(w[q])
                vecs.append(vec)
        elif kind == "boundary":
            for a, bb in ((0, 0), (7, 7), (7, 8), (8, 7), (255, 255), (255, 0), (0, 255), (15, 1), (128, 127), (1, 1)):
                vec = {}
                for k, p in enumerate(ports):
                    vec[p] = (a if k % 2 == 0 else bb) & mask(w[p])
                vecs.append(vec)
        else:  # random
            for _ in range(10):
                vecs.append({p: rng.getrandbits(w[p]) for p in ports})
        return vecs[:16]

    # ------------------------------------------------------------------ dynamic back-slice
    def _starts(self):
        d, tr = self.diff, self.trace
        last = tr.n - 1
        if self.final_only or not d:
            return self._final_starts()
        c = d["cycle"]
        if d["kind"] == "value":
            return [("wb_mux", c)]
        if d["kind"] == "rd":
            return [("memwb_rd", c), ("memwb_regwrite", c)]
        if d["kind"] == "store":
            return [("exmem_alu", max(0, c - 1)), ("exmem_sd", max(0, c - 1)), ("exmem_memwrite", max(0, c - 1))]
        if d["kind"] in ("pc", "missing"):
            return [("memwb_pc", c), ("memwb_valid", c)]
        return self._final_starts()

    def _final_starts(self):
        """Back-trace start points from the final state only: wrong registers, wrong memory bytes, or no HALT."""
        tr, g = self.trace, self.test["golden"]
        last = tr.n - 1
        out = []
        if tr.halted is None:
            out += [("memwb_pc", last), ("memwb_valid", last)]
        for k in range(8):
            if tr.regs[k] != g["regs"][k]:
                out.append((f"r{k}", last))
        for a in range(MEM_SIZE):
            if tr.mem[a] != g["mem"][a]:
                ws = [k for k in range(tr.n) if tr.vals[k]["exmem_memwrite.q"] and tr.vals[k]["exmem_alu.q"] % MEM_SIZE == a]
                if ws:
                    out += [("exmem_sd", ws[-1]), ("exmem_alu", ws[-1])]
                else:  # the expected store never happened: follow the stores that did
                    out += [("exmem_memwrite", last)]
        return out or [("memwb_pc", last)]

    def slice_cycles(self):
        """block -> sorted cycles where the full back-slice of the failure passes through it."""
        if self._slice is None:
            seen = set()
            for st in self.starts:
                seen |= self.ancestors(st, limit=30000)
            sl = {}
            for b, c in seen:
                if not self.by[b].trusted:
                    sl.setdefault(b, set()).add(c)
            self._slice = {b: sorted(cs) for b, cs in sl.items()}
        return self._slice

    def adjacency(self):
        if self._adj is None:
            adj = {b.name: set() for b in self.blocks}
            for b in self.blocks:
                for net in b.ins.values():
                    d = self.drivers[net][0]
                    if d != b.name:
                        adj[b.name].add(d)
                        adj[d].add(b.name)
            self._adj = {k: sorted(v) for k, v in adj.items()}
        return self._adj

    def hops_from(self, src):
        """Graph distance (wires between blocks) from src to every block."""
        if src not in self._hops:
            adj, dist, q = self.adjacency(), {src: 0}, deque([src])
            while q:
                x = q.popleft()
                for y in adj[x]:
                    if y not in dist:
                        dist[y] = dist[x] + 1
                        q.append(y)
            self._hops[src] = dist
        return self._hops[src]

    def col(self, block):
        return col_of(self.by[block])

    def preds(self, node):
        """Block-cycles whose outputs carried the value of this block-cycle's output."""
        block, c = node
        b, tr = self.by[block], self.trace
        out = []
        if block == "dmem":
            out.append((self.drivers[b.ins["addr"]][0], c))
            a = tr.vals[c][b.ins["addr"]] % MEM_SIZE
            for k in range(c - 1, -1, -1):
                v = tr.vals[k]
                if v["exmem_memwrite.q"] and v["exmem_alu.q"] % MEM_SIZE == a:
                    out += [(self.drivers[b.ins[p]][0], k) for p in ("wdata", "addr", "we")]
                    break
            return out
        if block == "imem":
            return [(self.drivers[b.ins["pc"]][0], c)]
        if b.seq:
            if c == 0:
                return []
            inp = tr.inputs(block, c - 1)
            ports = b.relevant(inp, tr.state(block, c - 1)) if b.relevant else list(b.ins)
            out = [(self.drivers[b.ins[p]][0], c - 1) for p in ports]
            if "d" not in ports and not inp.get("flush", 0):
                out.append((block, c - 1))
            return out
        inp = tr.inputs(block, c)
        ports = b.relevant(inp, None) if b.relevant else list(b.ins)
        return [(self.drivers[b.ins[p]][0], c) for p in ports]

    def frontier(self, cleared, stopped, boost=None, limit=40):
        """Dijkstra over the back-slice from the failure. Trusted blocks pass the search through for free;
        a checked-and-cleared block-cycle costs 1; an unchecked one is a frontier node (searched past with a penalty
        so later layers get a lower priority). `stopped` holds block-cycles that are suspects and are not passed.
        Returns [(priority, block, cycle)] for untrusted, uncleared block-cycles, best first."""
        boost = boost or {}
        pq = [(0.0, b, c) for b, c in self.starts]
        heapq.heapify(pq)
        best, out, seen_blocks = {}, [], {}
        while pq and len(out) < limit * 6:
            pr, b, c = heapq.heappop(pq)
            if best.get((b, c), 1e9) <= pr:
                continue
            best[(b, c)] = pr
            blk = self.by[b]
            step = 0.0
            if not blk.trusted:
                if c in cleared.get(b, ()):
                    step = 1.0
                elif (b, c) in stopped or b in stopped:
                    continue
                else:
                    out.append((round(pr + boost.get(b, 0.0), 2), b, c))
                    step = 4.0
            for nb in self.preds((b, c)):
                np_ = pr + step + (0.0 if self.by[nb[0]].trusted else 0.01)
                if np_ < best.get(nb, 1e9):
                    heapq.heappush(pq, (np_, nb[0], nb[1]))
        out.sort()
        res = []
        for pr, b, c in out:
            if seen_blocks.get(b, 0) >= 3:
                continue
            seen_blocks[b] = seen_blocks.get(b, 0) + 1
            res.append((pr, b, c))
            if len(res) >= limit:
                break
        return res

    def ancestors(self, node, limit=4000):
        """Every block-cycle in the back-slice of `node` (the values it was computed from)."""
        seen, todo = {node}, [node]
        while todo and len(seen) < limit:
            for nb in self.preds(todo.pop()):
                if nb not in seen:
                    seen.add(nb)
                    todo.append(nb)
        return seen

    # ------------------------------------------------------------------ deduction helpers
    def fit(self, block, rows):
        """Faults in `block` that explain the observed rows, best first. Tolerant: a rare-trigger fault may leave a row
        at spec, and with measurement noise up to one row in eight may be unexplained."""
        b = self.by[block]
        if b.trusted or not rows:
            return []
        if not any(not r["ok"] for r in rows):
            return []
        allow = (len(rows) // 8 + (1 if self.noise > 0 else 0)) if self.noise > 0 else 0
        scored = []
        for f in b.faults:
            p = b.eff(dict(f, block=block))
            expl = inactive = unexpl = 0
            for r in rows:
                fo = b.eval(p, r["in"], None)
                if fo == r["out"]:
                    expl += 0 if r["ok"] else 1
                elif r["ok"]:
                    inactive += 1
                else:
                    unexpl += 1
            if expl and unexpl <= allow:
                scored.append((-expl, unexpl, inactive, len(scored), f))
        scored.sort(key=lambda x: x[:4])
        return [x[4] for x in scored]

    def grade(self, answer):
        """answer: {"fixes": [{block, port, type, key}, ...]} (or one such dict). The fix is checked by re-running the
        whole test suite with those params put back to spec. Every bug must be named for a part to count."""
        a = answer or {}
        fixes = a.get("fixes") if isinstance(a, dict) and "fixes" in a else ([a] if a else [])
        fixes = [x for x in fixes if x][:2]
        left = apply_fix(self.faults, [{"block": x.get("block"), "key": x.get("key")} for x in fixes])
        cpu = CPU(self.blocks, left)
        passed = sum(1 for t in self.tests if run_test(cpu, t)[0])
        def named(f):
            return [x for x in fixes if x.get("block") == f["block"]]
        return {"block_ok": all(named(f) for f in self.faults),
                "location_ok": all(any(x.get("port") == f["port"] for x in named(f)) for f in self.faults),
                "type_ok": all(any(x.get("type") == f["type"] for x in named(f)) for f in self.faults),
                "fix_ok": passed == len(self.tests), "tests_passed": passed, "tests_total": len(self.tests),
                "n_bugs": len(self.faults)}
