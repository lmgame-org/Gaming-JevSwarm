"""One debugging case: a seeded bug in the CPU, the failing test, and the tools the investigators may use.

Tools (each `check` or `drive` costs one probe; reading the netlist and the waveform dump is free):
  check(block, cycle)   compare the block against its spec over a window of cycles of the failing test:
                        for every cycle, the block's inputs, its actual outputs and what its spec says the outputs
                        should be for those inputs.
  drive(block, kind)    drive the block alone on the bench with a batch of input vectors (corner, sweep, boundary,
                        random) and compare its outputs with its spec.
Registers, the data memory and the instruction ROM are verified IP: the fault model puts the bug in one
combinational block. The dynamic back-slice follows the values that actually carried the wrong result: through a mux
only the selected input, through a register the value it loaded (or held).
"""
import heapq
import random

from .isa import MEM_SIZE, disasm, load_tests
from .netlist import BUG_TYPES, CPU, STAGES, all_faults, apply_fix, build_cpu, mask, retire_diff, run_test

STAGE_OF_PIPE = {"IF": "IF", "IF/ID": "ID", "ID": "ID", "ID/EX": "EX", "EX": "EX", "EX/MEM": "MEM", "MEM": "MEM",
                 "MEM/WB": "WB", "WB": "WB"}


class Case:
    def __init__(self, cfg):
        self.cfg = cfg
        self.seed = int(cfg["seed"])
        self.window = max(1, int(cfg["window"]))
        self.blocks = build_cpu()
        self.by = {b.name: b for b in self.blocks}
        self.tests = load_tests()
        self.clean = CPU(self.blocks)
        rng = random.Random(f"circuit-{self.seed}")
        types = [t for t in BUG_TYPES if cfg.get("bug_type", "any") in ("any", t)]
        faults = all_faults(self.blocks)
        for attempt in range(400):
            # bug types rotate with the bug number so consecutive numbers cover all four
            t = types[(self.seed + attempt) % len(types)]
            f = rng.choice([x for x in faults if x["type"] == t])
            cpu = CPU(self.blocks, f)
            res = [(t_, *run_test(cpu, t_)) for t_ in self.tests]
            failing = [(t_, tr) for t_, ok, tr in res if not ok]
            if failing:
                break
        self.fault = {k: f[k] for k in ("block", "key", "value", "type", "port", "desc")}
        self.cpu = cpu
        self.results = [{"name": t_["name"], "desc": t_["desc"], "ok": ok} for t_, ok, _ in res]
        # the investigators get the shortest failing test's waveform
        self.test, self.trace = min(failing, key=lambda x: x[1].n)
        self.diff = retire_diff(self.trace, self.test["golden"])
        self.n = self.trace.n
        self.drivers = self.cpu.drivers
        self.spec_p = {b.name: b.eff(None) for b in self.blocks}
        self.starts = self._starts()
        self._occ = None

    # ------------------------------------------------------------------ public views
    def brief(self):
        """What every investigator is told at the start (no spoilers)."""
        d = self.diff or {}
        return {"failing_tests": [r["name"] for r in self.results if not r["ok"]],
                "passing_tests": [r["name"] for r in self.results if r["ok"]],
                "test": self.test["name"], "test_desc": self.test["desc"], "cycles": self.n,
                "program": [f"{pc:2d}: {disasm(w)}" for pc, w in enumerate(self.test["prog"])],
                "failure": self.failure_text(), "first_bad_cycle": d.get("cycle"),
                "start_points": [f"{b}@{c}" for b, c in self.starts]}

    def failure_text(self):
        d = self.diff
        if not d:
            return "the test failed"
        e, g = d["expected"], d["got"]
        if d["kind"] == "final":
            bad = [f"r{k} = {v} (expected {self.test['golden']['regs'][k]})" for k, v in enumerate(self.trace.regs)
                   if v != self.test["golden"]["regs"][k]]
            bad += [f"mem[{a}] = {v} (expected {self.test['golden']['mem'][a]})" for a, v in enumerate(self.trace.mem)
                    if v != self.test["golden"]["mem"][a]]
            return "every instruction retired as expected, but at the end " + ", ".join(bad[:4])
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
        f = self.fault
        return {"block": f["block"], "port": f["port"], "type": f["type"], "key": f["key"], "desc": f["desc"],
                "type_label": BUG_TYPES[f["type"]]}

    # ------------------------------------------------------------------ probes
    def window_of(self, c):
        lo = max(0, c - (self.window - 1) // 2)
        hi = min(self.n - 1, lo + self.window - 1)
        lo = max(0, hi - self.window + 1)
        return lo, hi

    def check(self, block, c):
        """One probe: the block against its spec over the window around cycle c."""
        b = self.by[block]
        lo, hi = self.window_of(c)
        rows = []
        for k in range(lo, hi + 1):
            rows.append(self._row(b, k))
        return {"type": "check", "block": block, "cycle": c, "window": [lo, hi], "rows": rows,
                "mismatch": any(not r["ok"] for r in rows)}

    def _row(self, b, k):
        tr = self.trace
        inp = tr.inputs(b.name, k)
        out = tr.outputs(b.name, k)
        if b.trusted:
            exp, ok = dict(out), True
        else:
            exp = b.eval(self.spec_p[b.name], inp, None)
            ok = exp == out
        ins = tr.instr_at(b.stage if b.stage in STAGES else "ID", k)
        return {"cycle": k, "in": inp, "out": out, "spec": exp, "ok": ok, "instr": ins}

    def drive(self, block, kind, rng=None):
        """One probe: drive the block alone with a batch of vectors."""
        b = self.by[block]
        rng = rng or random.Random(f"drive-{self.seed}-{block}-{kind}")
        p_act = self.cpu.params(b)
        rows = []
        for inp in self.vectors(b, kind, rng):
            out = b.eval(p_act, inp, None)
            exp = b.eval(self.spec_p[block], inp, None)
            rows.append({"cycle": None, "in": inp, "out": out, "spec": exp, "ok": out == exp, "instr": None})
        return {"type": "drive", "block": block, "kind": kind, "rows": rows,
                "mismatch": any(not r["ok"] for r in rows)}

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
        if not d:
            return [("memwb_pc", last)]
        c = d["cycle"]
        if d["kind"] == "value":
            return [("wb_mux", c)]
        if d["kind"] == "rd":
            return [("memwb_rd", c), ("memwb_regwrite", c)]
        if d["kind"] == "store":
            return [("exmem_alu", max(0, c - 1)), ("exmem_sd", max(0, c - 1)), ("exmem_memwrite", max(0, c - 1))]
        if d["kind"] in ("pc", "missing"):
            return [("memwb_pc", c), ("memwb_valid", c)]
        out = []
        g = self.test["golden"]
        for k in range(8):
            if tr.regs[k] != g["regs"][k]:
                out.append((f"r{k}", last))
        for a in range(MEM_SIZE):
            if tr.mem[a] != g["mem"][a]:
                cw = max([k for k in range(tr.n) if tr.vals[k]["exmem_memwrite.q"] and
                          tr.vals[k]["exmem_alu.q"] % MEM_SIZE == a] or [last])
                out += [("exmem_sd", cw), ("exmem_alu", cw)]
        return out or [("memwb_pc", last)]

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
        """Faults in `block` that reproduce every observed row (trace windows and bench vectors)."""
        b = self.by[block]
        if b.trusted or not rows:
            return []
        out = []
        for f in b.faults:
            p = b.eff(dict(f, block=block))
            if all(b.eval(p, r["in"], None) == r["out"] for r in rows):
                out.append(f)
        return out

    def grade(self, answer):
        """answer: {block, port, type, key}. Returns location / type / fix scores; the fix is checked by re-running
        the whole test suite with that param put back to spec."""
        f = self.fault
        a = answer or {}
        fix = {"block": a.get("block"), "key": a.get("key")}
        left = apply_fix(self.cpu.fault, fix)
        cpu = CPU(self.blocks, left)
        passed = sum(1 for t in self.tests if run_test(cpu, t)[0])
        return {"block_ok": a.get("block") == f["block"],
                "location_ok": a.get("block") == f["block"] and a.get("port") == f["port"],
                "type_ok": a.get("type") == f["type"],
                "fix_ok": passed == len(self.tests), "tests_passed": passed, "tests_total": len(self.tests)}
