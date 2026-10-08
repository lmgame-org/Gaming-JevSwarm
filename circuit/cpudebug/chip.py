"""Circuit v3: a 12-core chip of about 1,190 blocks, with cross-block bugs and scarce bench tests.

The chip
  12 identical cores c0..c11 (each the 96-block pipelined CPU, names prefixed `c<k>.`), each running its own test
  program. Each core feeds a signature unit: `c<k>.sig_mix` (logic) compresses the core's write-back and store stream
  every cycle and `c<k>.sig_reg` (verified register) accumulates it (a MISR, as in built-in self-test). An XOR
  reduction tree `tree0..tree10` (logic) folds the 12 signatures into the chip signature. A chip test passes when every
  core ends with the right registers and memory and the chip signature matches its golden value.

What investigators see
  Only which chip tests fail and that the chip signature is wrong. The test documentation lists each core's golden
  signature, so the first, global step is to find which cores went wrong: a `SIG:c<k>` probe reads core k's
  signature and scans out its final registers and memory (one probe each). A lone investigator spends many probes
  on this; a group reads all twelve in one tick.

Bugs (one per case, sometimes two)
  block faults   as in v2 (stuck-at, swapped mux, wrong forwarding/hazard path, off-by-one), in any core's logic or the
                 signature fabric; rare-trigger faults fire for one input pattern in `rare_mod`
  wire faults    on one connection inside a core: `delay` (the receiver sees last cycle's value: a load-timing bug) or
                 `convention` (the receiver reads the bus bit-reversed, or a 1-bit signal inverted: an interface
                 mismatch). Both blocks meet their own specs, so no block check or bench drive can see it; only a
                 `link` probe on that wire (`L:c<k>:<receiver>.<port>`) compares what was sent with what arrived.

Probes
  check(block, cycle)   one tick; as in v2
  link(L:..., cycle)    one tick; the driver's output and the receiver's input over the window
  SIG:c<k>              one tick; core k's signature against its golden value, plus its final-state differences
  drive(block, kind)    `drive_ticks` (3) ticks and one of `bench_slots` (2) shared bench slots; only 4 vectors from
                        one input region (`corner`, `sweep`, `boundary`, `random`), or `trace` (replays the inputs
                        the block saw around a given cycle of the failing test)

Grading
  Up to three fixes. Solved = every chip test passes after the fixes AND no fix names an innocent site.
"""
import heapq
import random
from collections import deque

from .isa import MEM_SIZE, load_tests
from .netlist import BUG_TYPES, CPU, Block, all_faults, build_cpu, mask, trig_active, wire_xform

N_CORES = 12
STAGE_COL = {"IF": 0, "IF/ID": 1, "ID": 3, "ID/EX": 5, "EX": 7, "EX/MEM": 8, "MEM": 9, "MEM/WB": 10, "WB": 11}
_CORE_TRACES = {}    # (program name, fault key or None) -> Trace (clean cores are shared across cases)


def rotl(s):
    return ((s << 1) | (s >> 7)) & 255


def sig_mix_fn(p, i, s):
    m = (i["data"] ^ ((i["rd"] << p["rd_shift"]) & 255)) if i["we"] else 0
    if i["sw"]:
        m ^= (i["sd"] + i["sa"] * p["mul"]) & 255
    return {"m": m & 255}


class Pseudo:
    """A checkable thing that is not a netlist block: a wire (link) or a core signature."""
    seq = False
    deps = []

    def __init__(self, name, stage, group, spec, outs, faults, core):
        self.name, self.stage, self.group, self.spec = name, stage, group, spec
        self.outs, self.faults, self.core = outs, faults, core
        self.ins = {}
        self.trusted = False
        self.params = {f["key"]: None for f in faults}

    def eff(self, fault=None):
        p = dict(self.params)
        for f in (fault if isinstance(fault, list) else [fault] if fault else []):
            if f["block"] == self.name:
                p[f["key"]] = f["value"]
        return p

    def eval(self, p, inp, state=None):
        if self.group != "wire":
            return {"sig": inp.get("sig", 0)}
        w = self.outs["v"]
        if p.get("delay"):
            return {"v": inp["prev"]}
        if p.get("convention"):
            return {"v": wire_xform("convention", inp["now"], inp["prev"], w)}
        return {"v": inp["now"]}

    def public(self):
        return {"name": self.name, "stage": self.stage, "group": self.group, "spec": self.spec, "ins": {}, "outs": self.outs,
                "trusted": False, "seq": False}


def link_name(k, blk, port):
    return f"L:c{k}:{blk}.{port}"


def chip_tests(n):
    """Three chip tests, each giving every core one of the eight short programs (fibonacci, 199 cycles, is left out)."""
    progs = [t for t in load_tests() if t["name"] != "fibonacci"]
    out = []
    for t, (name, stride) in enumerate((("chip_a", 1), ("chip_b", 4), ("chip_c", 7))):
        out.append({"name": name, "desc": f"12 cores run programs rotated by {stride}",
                    "cores": [progs[(k * stride + t) % len(progs)] for k in range(n)]})
    return out


class ChipCase:
    """Same interface as case.Case, for the 12-core chip."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.tier = "v3"
        self.seed = int(cfg["seed"])
        self.window = max(1, int(cfg.get("window", 2)))
        self.noise = float(cfg.get("noise", 0.0))
        self.n_cores = int(cfg.get("n_cores", N_CORES))
        self.rare_mod = int(cfg.get("rare_mod", 4))
        self.final_only = True
        self.core_blocks = build_cpu()
        self.core_by = {b.name: b for b in self.core_blocks}
        self.tests = chip_tests(self.n_cores)
        self._build_names()
        rng = random.Random(f"chip-{self.seed}")
        self._pick_bugs(rng, cfg)
        self.drivers = {}
        for b in self.blocks:
            for port in b.outs:
                self.drivers[b.net(port)] = (b.name, port)
        self.spec_p = {b.name: b.eff(None) for b in self.blocks}
        self._adj = None
        self._hops = {}
        self._slice = None
        self._occ = None

    # ------------------------------------------------------------------ names and fabric
    def _build_names(self):
        n = self.n_cores
        blocks = []
        for k in range(n):
            for b in self.core_blocks:
                blocks.append(_Alias(b, k))
        for k in range(n):
            P = f"c{k}."
            blocks.append(Block(f"c{k}.sig_mix", "SIG", "signature",
                                {"we": P + "wb_guard.we", "rd": P + "memwb_rd.q", "data": P + "wb_mux.out",
                                 "sw": P + "exmem_memwrite.q", "sa": P + "exmem_alu.q", "sd": P + "exmem_sd.q"},
                                {"m": 8}, sig_mix_fn, f"core {k} signature mixer: m = (data ^ (rd << 5) if we) ^ "
                                "((sd + 7*sa) if sw), mod 256", params={"rd_shift": 5, "mul": 7},
                                faults=[{"key": "rd_shift", "value": 4, "type": "off_by_one", "port": "m",
                                         "desc": "register number shifted by 4 instead of 5"},
                                        {"key": "mul", "value": 8, "type": "off_by_one", "port": "m",
                                         "desc": "store address weighted by 8 instead of 7"}]))
            blocks.append(Block(f"c{k}.sig_reg", "SIG", "signature", {"m": f"c{k}.sig_mix.m"}, {"q": 8},
                                lambda p, i, s: {"q": s}, f"core {k} signature register: s <- rotl(s) ^ m",
                                nxt=lambda p, i, s: rotl(s) ^ i["m"], init=lambda: 0, deps=[], trusted=True,
                                relevant=lambda i, s: ["m"]))
        # XOR reduction tree
        level = [f"c{k}.sig_reg.q" for k in range(n)]
        t = 0
        while len(level) > 1:
            nxt = []
            for i in range(0, len(level) - 1, 2):
                blocks.append(Block(f"tree{t}", "TREE", "signature", {"a": level[i], "b": level[i + 1]}, {"x": 8},
                                    lambda p, i, s: {"x": i["a"] ^ i["b"]}, "signature tree: x = a XOR b"))
                nxt.append(f"tree{t}.x")
                t += 1
            if len(level) % 2:
                nxt.append(level[-1])
            level = nxt
        self.root = level[0]
        self.blocks = blocks
        self.by = {b.name: b for b in blocks}
        # pseudo-blocks: wires inside cores, and core signatures
        self.links = {}
        for k in range(n):
            for b in self.core_blocks:
                for port, net in b.ins.items():
                    d, dp = net.split(".")
                    w = self.core_by[d].outs[dp]
                    nm = link_name(k, b.name, port)
                    self.links[nm] = Pseudo(
                        nm, b.stage, "wire", f"wire {d}.{dp} -> {b.name}.{port} in core {k}: the receiver gets "
                        "exactly what the driver sends", {"v": w},
                        [{"key": "delay", "value": True, "type": "wire_timing", "port": "v",
                          "desc": f"{b.name}.{port} sees last cycle's value of {d}.{dp} (a load-timing bug)"},
                         {"key": "convention", "value": True, "type": "wire_interface", "port": "v",
                          "desc": f"{b.name}.{port} reads {d}.{dp} {'bit-reversed' if w > 1 else 'inverted'} "
                                  "(an interface mismatch)"}], k)
                    self.links[nm].src = (f"c{k}.{d}", dp)
                    self.links[nm].dst = (f"c{k}.{b.name}", port)
            sg = Pseudo(f"SIG:c{k}", "SIG", "core signature",
                        f"core {k}'s signature and final state against their golden values", {"sig": 8}, [], k)
            self.links[sg.name] = sg
        self.by.update(self.links)

    def core_of(self, name):
        if name.startswith("L:c"):
            return int(name[3:].split(":")[0])
        if name.startswith("SIG:c"):
            return int(name[5:])
        if name.startswith("c") and "." in name:
            return int(name[1:name.index(".")])
        return None

    def local(self, name):
        return name.split(".", 1)[1] if name.startswith("c") and "." in name else name

    # ------------------------------------------------------------------ bugs and simulation
    def _pick_bugs(self, rng, cfg):
        rare, double, wire_frac = float(cfg.get("rare_frac", 0)), float(cfg.get("double_frac", 0)), float(cfg.get("wire_frac", 0.35))
        types = list(BUG_TYPES)
        core_faults = all_faults(self.core_blocks)
        fabric = [dict(f, block=b.name) for b in self.blocks if b.name.startswith(("c0.sig_mix", "tree")) for f in b.faults]
        pick = None
        for attempt in range(300):
            fs = []
            n = 2 if rng.random() < double else 1
            for j in range(n):
                k = rng.randrange(self.n_cores)
                if rng.random() < wire_frac:
                    b = rng.choice(self.core_blocks)
                    port = rng.choice(sorted(b.ins)) if b.ins else None
                    if port is None:
                        continue
                    nm = link_name(k, b.name, port)
                    kind = rng.choice(["delay", "convention"])
                    f = next(x for x in self.links[nm].faults if x["key"] == kind)
                    fs.append(dict(f, block=nm, wire=(b.name, port), core=k))
                elif rng.random() < 0.06:
                    f = dict(rng.choice(fabric))
                    if f["block"].startswith("c0.sig_mix"):
                        f["block"] = f"c{k}.sig_mix"
                    f["core"] = None if f["block"].startswith("tree") else k
                    fs.append(f)
                else:
                    t = types[(self.seed + attempt + j) % len(types)]
                    f = dict(rng.choice([x for x in core_faults if x["type"] == t]))
                    f["core"] = k
                    f["local"] = f["block"]
                    f["block"] = f"c{k}.{f['block']}"
                    if rng.random() < rare:
                        f["trigger"] = self.rare_mod
                    fs.append(f)
            if len({f["block"] for f in fs}) < len(fs) or not fs:
                continue
            res = self._run_suite(fs)
            if not any(not ok for ok, _ in res):
                continue
            if len(fs) == 2:
                a, b = self._run_suite([fs[0]]), self._run_suite([fs[1]])
                if all(ok for ok, _ in a) or all(ok for ok, _ in b):
                    fs = [fs[0]] if not all(ok for ok, _ in a) else [fs[1]]
                    res = self._run_suite(fs)
            # the investigators get one failing test: it must show every bug (a wrong signature in each bug's core,
            # or in the chip signature for a tree bug)
            pick = None
            for t, (ok, tr) in zip(self.tests, res):
                if ok:
                    continue
                if all((f.get("core") is None and tr.final_sig != tr.golden.final_sig) or
                       (f.get("core") is not None and tr.core_sigs[f["core"]] != tr.golden.core_sigs[f["core"]])
                       for f in fs):
                    pick = (t, tr)
                    break
            if pick is None:
                continue
            self.faults = [{k_: f.get(k_) for k_ in ("block", "key", "value", "type", "port", "desc", "trigger",
                                                      "core", "local", "wire")} for f in fs]
            break
        self.fault = self.faults[0]
        self.results = [{"name": t["name"], "desc": t["desc"], "ok": ok} for t, (ok, _) in zip(self.tests, res)]
        self.test, self.trace = pick
        self.n = self.trace.n
        # public start points: every core's signature, and the root of the signature tree (the chip signature is wrong)
        self.starts = [(f"SIG:c{k}", self.n - 1) for k in range(self.n_cores)] + [(self.root.rsplit(".", 1)[0], self.n - 1)]

    def _core_trace(self, k, test, faults):
        """Core k's run of its program in `test` under the faults that live in core k (cached when clean)."""
        mine = [f for f in faults if f.get("core") == k and (f.get("local") or f.get("wire"))]
        prog = test["cores"][k]
        key = (prog["name"], tuple(sorted((f["block"], f["key"], str(f["value"]), f.get("trigger") or 0) for f in mine)))
        if key in _CORE_TRACES:
            return _CORE_TRACES[key]
        bf = [dict(f, block=f["local"]) for f in mine if f.get("local")]
        wires = {f["wire"]: f["key"] for f in mine if f.get("wire")}
        cpu = CPU(self.core_blocks, bf, wires)
        g = prog["golden"]
        tr = cpu.run(prog["prog"], prog["data"], max_cycles=3 * len(g["retire"]) + 40)
        tr.ok = tr.halted is not None and tr.regs == g["regs"] and tr.mem == g["mem"]
        if not mine:
            if len(_CORE_TRACES) > 400:
                _CORE_TRACES.clear()
            _CORE_TRACES[key] = tr
        return tr

    def _run_suite(self, faults, tests=None):
        return [self._run_chip(t, faults) for t in (tests or self.tests)]

    def _run_chip(self, test, faults):
        cores = [self._core_trace(k, test, faults) for k in range(self.n_cores)]
        tr = ChipTrace(self, test, cores, faults)
        golden = ChipTrace(self, test, [self._core_trace(k, test, []) for k in range(self.n_cores)], [])
        ok = all(c.ok for c in cores) and tr.final_sig == golden.final_sig
        tr.golden = golden
        return ok, tr

    # ------------------------------------------------------------------ public views
    def failure_text(self):
        bad = [r["name"] for r in self.results if not r["ok"]]
        return (f"{self.test['name']} fails ({len(bad)} of 3 chip tests fail): the chip signature is "
                f"{self.trace.final_sig} (expected {self.trace.golden.final_sig}). Read the cores' signatures to find "
                "which went wrong.")

    def brief(self):
        progs = [p["name"] for p in self.test["cores"]]
        return {"failing_tests": [r["name"] for r in self.results if not r["ok"]],
                "passing_tests": [r["name"] for r in self.results if r["ok"]],
                "test": self.test["name"], "test_desc": self.test["desc"], "cycles": self.n,
                "program": [f"core {k}: {p}" for k, p in enumerate(progs)],
                "core_programs": progs, "failure": self.failure_text(),
                "golden_signatures": self.trace.golden.core_sigs,
                "start_points": [f"{b}@{c}" for b, c in self.starts], "first_bad_cycle": None, "n_cores": self.n_cores}

    def public_blocks(self):
        out = []
        for b in self.blocks:
            d = b.public()
            d["faults"] = [] if b.trusted else sorted({f["key"].split(":")[0] if f["type"] == "stuck_at" else f["key"]
                                                       for f in b.faults})
            d["core"] = self.core_of(b.name)
            out.append(d)
        return out

    def edges(self):
        out = []
        for b in self.blocks:
            for port, net in b.ins.items():
                out.append([self.drivers[net][0], b.name, port])
        return out

    def occupancy(self, k=None):
        k = 0 if k is None else k
        tr = self.trace.cores[k]
        out = []
        for c in range(self.n):
            if c < tr.n:
                out.append([(tr.instr_at(s, c) or {}).get("pc") for s in ("IF", "ID", "EX", "MEM", "WB")])
            else:
                out.append([None] * 5)
        return out

    def secret(self):
        bugs = [{"block": f["block"], "port": f["port"], "type": f["type"], "key": f["key"], "desc": f["desc"],
                 "type_label": BUG_TYPES.get(f["type"], f["type"].replace("_", " ")), "rare": bool(f.get("trigger")),
                 "core": f.get("core")} for f in self.faults]
        out = dict(bugs[0])
        out["bugs"] = bugs
        return out

    def col(self, name):
        k = self.core_of(name)
        b = self.by[name]
        base = 0 if k is None else 12 * k
        if name.startswith("tree"):
            return 12 * self.n_cores + 2
        return base + STAGE_COL.get(b.stage, 11)

    # ------------------------------------------------------------------ probes
    def window_of(self, c):
        lo = max(0, c - (self.window - 1) // 2)
        hi = min(self.n - 1, lo + self.window - 1)
        return max(0, hi - self.window + 1), hi

    def _glitch(self, outs, out, rng):
        if self.noise <= 0 or rng.random() >= self.noise or not outs:
            return out, False
        port = rng.choice(sorted(outs))
        out = dict(out)
        out[port] ^= 1 << rng.randrange(outs[port])
        return out, True

    def check(self, block, c, rng=None):
        rng = rng or random.Random(f"check-{self.seed}-{block}-{c}")
        b = self.by[block]
        if block.startswith("SIG:"):
            k = b.core
            act, gold = self.trace.core_sigs[k], self.trace.golden.core_sigs[k]
            out, gl = self._glitch(b.outs, {"sig": act}, rng)
            note = "; ".join(self.trace.core_diffs(k)[:4]) or "final registers and memory as expected"
            row = {"cycle": self.n - 1, "in": {}, "out": out, "spec": {"sig": gold}, "ok": out == {"sig": gold},
                   "instr": {"pc": -1, "text": note}, "_glitch": gl}
            return {"type": "check", "block": block, "cycle": self.n - 1, "window": [self.n - 1, self.n - 1],
                    "rows": [row], "mismatch": not row["ok"]}
        lo, hi = self.window_of(c)
        rows = [self._row(b, k, rng) for k in range(lo, hi + 1)]
        return {"type": "check", "block": block, "cycle": c, "window": [lo, hi], "rows": rows,
                "mismatch": any(not r["ok"] for r in rows)}

    def _row(self, b, k, rng):
        tr = self.trace
        if b.group == "wire":
            now = tr.net(b.src[0] + "." + b.src[1], k)
            prev = tr.net(b.src[0] + "." + b.src[1], k - 1) if k > 0 else 0
            got = tr.inputs(b.dst[0], k).get(b.dst[1], 0)
            out, gl = self._glitch(b.outs, {"v": got}, rng)
            exp = {"v": now}
            return {"cycle": k, "in": {"now": now, "prev": prev}, "out": out, "spec": exp, "ok": out == exp,
                    "instr": tr.instr_at(b.core, b.stage, k), "_glitch": gl}
        inp = tr.inputs(b.name, k)
        out = tr.outputs(b.name, k)
        if b.trusted:
            exp, ok, gl = dict(out), True, False
        else:
            exp = b.eval(self.spec_p[b.name], inp, None)
            out, gl = self._glitch(b.outs, out, rng)
            ok = exp == out
        return {"cycle": k, "in": inp, "out": out, "spec": exp, "ok": ok,
                "instr": tr.instr_at(self.core_of(b.name), b.stage, k), "_glitch": gl}

    def drive(self, block, kind, rng=None, cycle=None):
        b = self.by[block]
        vrng = random.Random(f"drive-{self.seed}-{block}-{kind}-{cycle}")
        rng = rng or vrng
        rows = []
        if b.trusted or block.startswith(("L:", "SIG:")):
            return {"type": "drive", "block": block, "kind": kind, "rows": [], "mismatch": False}
        loc = self.local(block)
        core_b = self.core_by.get(loc)
        fault = [f for f in self.faults if f["block"] == block and not f.get("wire")]
        for inp in self.vectors(b, kind, vrng, cycle):
            p_act = b.eff([dict(f, block=b.name) for f in fault])
            trig = next((f.get("trigger") for f in fault if f.get("trigger")), None)
            if trig and not trig_active(inp, trig):
                p_act = self.spec_p[block]
            out = b.eval(p_act, inp, None)
            exp = b.eval(self.spec_p[block], inp, None)
            out, gl = self._glitch(b.outs, out, rng)
            rows.append({"cycle": None, "in": inp, "out": out, "spec": exp, "ok": out == exp, "instr": None, "_glitch": gl})
        return {"type": "drive", "block": block, "kind": kind, "rows": rows, "mismatch": any(not r["ok"] for r in rows)}

    def vectors(self, b, kind, rng, cycle=None):
        """Only four vectors from one input region (v3 makes bench tests partial)."""
        w = {port: self.by[self.drivers[net][0]].outs[self.drivers[net][1]] for port, net in b.ins.items()}
        ports = list(w)
        if not ports:
            return [{}]
        if kind == "trace" and cycle is not None:
            lo, hi = max(0, cycle - 1), min(self.n - 1, cycle + 2)
            return [self.trace.inputs(b.name, c) for c in range(lo, hi + 1)][:4]
        sel = [p for p in ports if p in ("sel", "op", "type", "addr") or (w[p] <= 2 and p not in ("a", "b"))]
        data = [p for p in ports if p not in sel]
        vecs = []
        if kind == "corner":
            for pat in (0x00, 0xFF, 0x55, 0xAA):
                vecs.append({p: pat & mask(w[p]) for p in ports})
        elif kind == "sweep":
            sp = sel[0] if sel else None
            vals = rng.sample(range(1 << w[sp]), min(4, 1 << w[sp])) if sp else [0]
            for v in vals:
                vec = {p: ((17 * (k + 1) + 3) & mask(w[p])) for k, p in enumerate(data)}
                if sp:
                    vec[sp] = v
                for q in sel[1:]:
                    vec[q] = 1 & mask(w[q])
                vecs.append(vec)
        elif kind == "boundary":
            for a, bb in rng.sample([(0, 0), (7, 7), (7, 8), (8, 7), (255, 255), (255, 0), (0, 255), (128, 127)], 4):
                vecs.append({p: (a if k % 2 == 0 else bb) & mask(w[p]) for k, p in enumerate(ports)})
        else:
            for _ in range(4):
                vecs.append({p: rng.getrandbits(w[p]) for p in ports})
        return vecs[:4]

    def read(self, net, lo, hi):
        lo = max(0, int(lo))
        hi = min(self.n - 1, int(hi), lo + 15)
        return {k: self.trace.net(net, k) for k in range(lo, hi + 1)}

    # ------------------------------------------------------------------ back-slice
    def _core_starts(self, k):
        tr = self.trace.cores[k]
        g = self.test["cores"][k]["golden"]
        P = f"c{k}."
        last = min(tr.n, self.n) - 1
        out = []
        if tr.halted is None:
            out += [(P + "memwb_pc", last), (P + "memwb_valid", last)]
        for r in range(8):
            if tr.regs[r] != g["regs"][r]:
                out.append((f"c{k}.r{r}", last))
        for a in range(MEM_SIZE):
            if tr.mem[a] != g["mem"][a]:
                ws = [c for c in range(tr.n) if tr.vals[c]["exmem_memwrite.q"] and tr.vals[c]["exmem_alu.q"] % MEM_SIZE == a]
                out += [(P + "exmem_sd", ws[-1]), (P + "exmem_alu", ws[-1])] if ws else [(P + "exmem_memwrite", last)]
        if not out and self.trace.core_sigs[k] != self.trace.golden.core_sigs[k]:
            # the final state is right but the signature is not: the write-back stream went wrong somewhere; start
            # from the core's signature mixer at every cycle the core ran
            out += [(f"c{k}.sig_mix", c) for c in range(0, min(tr.n, self.n))]
        return out

    def preds(self, node):
        name, c = node
        if name.startswith("SIG:"):
            return self._core_starts(self.by[name].core)
        if name.startswith("L:"):
            lk = self.by[name]
            return [(lk.src[0], c)]
        k = self.core_of(name)
        b = self.by[name]
        tr = self.trace
        if isinstance(b, _Alias):
            lb = b.base
            ctr = tr.cores[k]
            if c >= ctr.n:
                c = ctr.n - 1
            if lb.name == "dmem":
                out = [self._lk(k, "dmem", "addr", c)]
                a = ctr.vals[c][lb.ins["addr"]] % MEM_SIZE
                for cc in range(c - 1, -1, -1):
                    v = ctr.vals[cc]
                    if v["exmem_memwrite.q"] and v["exmem_alu.q"] % MEM_SIZE == a:
                        out += [self._lk(k, "dmem", p, cc) for p in ("wdata", "addr", "we")]
                        break
                return out
            if lb.name == "imem":
                return [self._lk(k, "imem", "pc", c)]
            if lb.seq:
                if c == 0:
                    return []
                inp = ctr.inputs(lb.name, c - 1)
                if lb.group == "regfile" and lb.name.startswith("r") and not (inp["we"] >> int(lb.name[1])) & 1:
                    # a register that held its value: jump back to its last write; on the way, only cycles where some
                    # other register was written could hide a missed write, so only those keep a wire to check
                    idx = int(lb.name[1])
                    out, cw = [], None
                    for cc in range(c - 1, -1, -1):
                        i2 = ctr.inputs(lb.name, cc)
                        if (i2["we"] >> idx) & 1:
                            cw = cc
                            break
                        if ctr.vals[cc]["wb_guard.we"]:
                            out.append(self._lk(k, lb.name, "we", cc))
                    if cw is not None:
                        out.append((name, cw + 1))
                    return out
                ports = lb.relevant(inp, ctr.state(lb.name, c - 1)) if lb.relevant else list(lb.ins)
                out = [self._lk(k, lb.name, p, c - 1) for p in ports]
                if "d" not in ports and not inp.get("flush", 0):
                    out.append((name, c - 1))
                return out
            inp = ctr.inputs(lb.name, c)
            ports = lb.relevant(inp, None) if lb.relevant else list(lb.ins)
            return [self._lk(k, lb.name, p, c) for p in ports]
        # fabric blocks: the search enters a core only through that core's signature (SIG:c<k>), never through the
        # mixer's inputs, so the tree start does not drag the search into every core
        if name.endswith("sig_mix"):        # into the core: the write-back and store nets it mixes
            k2 = self.core_of(name)
            ctr = tr.cores[k2]
            if c >= ctr.n:
                return []
            return [(self.drivers[net][0], c) for net in b.ins.values()]
        if b.seq:                            # a signature register reached from the tree: a dead end (cores are
            return []                        # searched through their SIG node)
        return [(self.drivers[net][0], c) for net in b.ins.values()]

    def _lk(self, k, blk, port, c):
        return (link_name(k, blk, port), c)

    def frontier(self, cleared, stopped, boost=None, limit=40):
        """As in Case.frontier, with links as checkable nodes, and core signatures: a core whose signature reads clean
        is not searched; one that reads bad is searched (not stopped)."""
        boost = boost or {}
        # the cores' signatures first; the signature tree (a rarer bug site) after them
        pq = [(0.0 if b.startswith("SIG:") else 6.0, b, c) for b, c in self.starts]
        heapq.heapify(pq)
        best, out, seen_blocks = {}, [], {}
        while pq and len(out) < limit * 6:
            pr, b, c = heapq.heappop(pq)
            if best.get((b, c), 1e9) <= pr:
                continue
            best[(b, c)] = pr
            blk = self.by[b]
            step = 0.0
            if b.startswith("SIG:"):
                if c in cleared.get(b, ()):
                    continue          # this core's signature reads clean: nothing to search in it
                if b not in stopped:
                    out.append((round(pr + boost.get(b, 0.0), 2), b, c))
                    continue          # unknown: read it first; no look-ahead into a core before its signature
                step = 0.5            # read bad: search the core
            elif not blk.trusted:
                wire = b.startswith("L:")
                if c in cleared.get(b, ()):
                    step = 1.0
                elif (b, c) in stopped or b in stopped:
                    continue
                else:
                    # wires are checked after the blocks around them: a wire is only suspect once both ends conform
                    out.append((round(pr + boost.get(b, 0.0) + (3.0 if wire else 0.0), 2), b, c))
                    step = 1.5 if wire else 4.0
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

    def ancestors(self, node, limit=60000):
        seen, todo = {node}, [node]
        while todo and len(seen) < limit:
            for nb in self.preds(todo.pop()):
                if nb not in seen:
                    seen.add(nb)
                    todo.append(nb)
        return seen

    def slice_cycles(self):
        """block -> cycles on the back-slice of the cores whose signature is wrong (what the search can reach)."""
        if self._slice is None:
            seen = set()
            for k in range(self.n_cores):
                if self.trace.core_sigs[k] != self.trace.golden.core_sigs[k]:
                    seen |= self.ancestors((f"SIG:c{k}", self.n - 1))
            sl = {}
            for b, c in seen:
                if not self.by[b].trusted and not b.startswith("SIG:"):
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
        if src.startswith(("L:", "SIG:")):
            src = self.by[src].dst[0] if src.startswith("L:") else f"c{self.by[src].core}.sig_mix"
        if src not in self._hops:
            adj, dist, q = self.adjacency(), {src: 0}, deque([src])
            while q:
                x = q.popleft()
                for y in adj[x]:
                    if y not in dist:
                        dist[y] = dist[x] + 1
                        q.append(y)
            for nm, lk in self.links.items():   # pseudo-blocks sit at their receiver / the core's signature unit
                anchor = lk.dst[0] if lk.group == "wire" else f"c{lk.core}.sig_mix"
                if anchor in dist:
                    dist[nm] = dist[anchor]
            self._hops[src] = dist
        return self._hops[src]

    # ------------------------------------------------------------------ deduction and grading
    def fit(self, block, rows):
        b = self.by[block]
        if b.trusted or not rows or not b.faults:
            return []
        if not any(not r["ok"] for r in rows):
            return []
        allow = (len(rows) // 8 + 1) if self.noise > 0 else 0
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
        a = answer or {}
        fixes = a.get("fixes") if isinstance(a, dict) and "fixes" in a else ([a] if a else [])
        fixes = [x for x in fixes if x][:3]
        sites = {(f["block"], f["key"]) for f in self.faults}
        left = [f for f in self.faults if not any(x.get("block") == f["block"] and x.get("key") == f["key"] for x in fixes)]
        innocent = sum(1 for x in fixes if not any(x.get("block") == f["block"] for f in self.faults))
        passed = sum(1 for ok, _ in self._run_suite(left)) if left else len(self.tests)
        passed = sum(1 for ok, _ in self._run_suite(left) if ok) if left else len(self.tests)
        named = lambda f: [x for x in fixes if x.get("block") == f["block"]]
        return {"block_ok": all(named(f) for f in self.faults),
                "location_ok": all(any(x.get("port") == f["port"] for x in named(f)) for f in self.faults),
                "type_ok": all(any(x.get("type") == f["type"] for x in named(f)) for f in self.faults),
                "fix_ok": passed == len(self.tests) and innocent == 0, "tests_passed": passed,
                "tests_total": len(self.tests), "n_bugs": len(self.faults), "innocent_fixes": innocent}


class _Alias:
    """Core k's view of a core block: the same block, with chip-level names and nets."""

    def __init__(self, base, k):
        self.base, self.k = base, k
        P = f"c{k}."
        self.name = P + base.name
        self.stage, self.group, self.spec = base.stage, base.group, f"core {k}: {base.spec}"
        self.ins = {p: P + n for p, n in base.ins.items()}
        self.outs = base.outs
        self.params, self.faults, self.trusted, self.seq = base.params, base.faults, base.trusted, base.seq
        self.deps, self.relevant = base.deps, base.relevant

    def net(self, port):
        return f"{self.name}.{port}"

    def eff(self, fault=None):
        fs = fault if isinstance(fault, list) else ([fault] if fault else [])
        return self.base.eff([dict(f, block=self.base.name) for f in fs if f["block"] == self.name])

    def eval(self, p, inp, state):
        return self.base.eval(p, inp, state)

    def public(self):
        d = self.base.public()
        d.update(name=self.name, spec=self.spec, ins=self.ins)
        return d


class ChipTrace:
    """The chip's waveform: twelve core traces (shared when clean) plus the signature fabric."""

    def __init__(self, case, test, cores, faults):
        self.case, self.test, self.cores = case, test, cores
        self.n = max(c.n for c in cores)
        self.halted = 0
        fab = [b for b in case.blocks if not isinstance(b, _Alias)]
        self.fab = {b.name: b for b in fab}
        fp = {b.name: b.eff(faults) for b in fab}
        trig = {f["block"]: f.get("trigger") for f in faults if f.get("trigger")}
        self.fvals = []
        self.fstates = []
        state = {b.name: b.init() for b in fab if b.seq}
        order = [b for b in fab if b.name.endswith("sig_mix")] + [b for b in fab if b.seq] + \
            [b for b in fab if b.name.startswith("tree")]
        for c in range(self.n):
            v = {}
            for b in order:
                if b.seq:
                    v[b.net("q")] = state[b.name]
                    continue
                inp = {p: (v[n] if n in v else self.core_net(n, c)) for p, n in b.ins.items()}
                p = fp[b.name] if not (b.name in trig and not trig_active(inp, trig[b.name])) else b.eff(None)
                for port, x in b.eval(p, inp, None).items():
                    v[b.net(port)] = x
            self.fvals.append(v)
            self.fstates.append(dict(state))
            for b in fab:
                if b.seq:
                    k = int(b.name[1:b.name.index(".")])
                    if c < self.cores[k].n:   # a signature stops when its core has finished
                        state[b.name] = b.nxt(fp[b.name], {"m": v[b.ins["m"]]}, state[b.name])
        self.core_sigs = [state[f"c{k}.sig_reg"] for k in range(case.n_cores)]
        last = self.fvals[-1]
        self.final_sig = last.get(case.root, None)
        if self.final_sig is None:  # the root is a sig register when the tree is trivial
            self.final_sig = state.get(case.root.rsplit(".", 1)[0], 0)
        # the root net is combinational on registered values: recompute it from the final register states
        self.final_sig = self._root_from(state)

    def _root_from(self, state):
        vals = {f"c{k}.sig_reg.q": state[f"c{k}.sig_reg"] for k in range(self.case.n_cores)}
        for b in self.case.blocks:
            if b.name.startswith("tree"):
                vals[b.net("x")] = vals[b.ins["a"]] ^ vals[b.ins["b"]]
        return vals[self.case.root]

    def core_net(self, net, c):
        k = int(net[1:net.index(".")])
        tr = self.cores[k]
        if c >= tr.n:
            return 0
        return tr.vals[c][net.split(".", 1)[1]]

    def net(self, net, c):
        if c < 0:
            return 0
        if net.startswith("c") and net.split(".")[0][1:].isdigit() and net.split(".")[1] not in ("sig_mix", "sig_reg"):
            k = int(net[1:net.index(".")])
            tr = self.cores[k]
            return tr.vals[min(c, tr.n - 1)][net.split(".", 1)[1]]
        return self.fvals[c].get(net, 0)

    def inputs(self, block, c):
        b = self.case.by[block]
        if isinstance(b, _Alias):
            tr = self.cores[b.k]
            return tr.inputs(b.base.name, min(c, tr.n - 1))
        return {p: (self.fvals[c][n] if n in self.fvals[c] else self.core_net(n, c)) for p, n in b.ins.items()}

    def outputs(self, block, c):
        b = self.case.by[block]
        if isinstance(b, _Alias):
            tr = self.cores[b.k]
            return tr.outputs(b.base.name, min(c, tr.n - 1))
        return {p: self.fvals[c][b.net(p)] for p in b.outs}

    def state(self, block, c):
        b = self.case.by[block]
        if isinstance(b, _Alias):
            tr = self.cores[b.k]
            return tr.state(b.base.name, min(c, tr.n - 1))
        return self.fstates[c].get(block)

    def instr_at(self, k, stage, c):
        if k is None:
            return None
        tr = self.cores[k]
        if c >= tr.n:
            return None
        st = stage if stage in ("IF", "IF/ID", "ID", "ID/EX", "EX", "EX/MEM", "MEM", "MEM/WB", "WB") else "WB"
        return tr.instr_at(st, c)

    def core_diffs(self, k):
        tr, g = self.cores[k], self.test["cores"][k]["golden"]
        out = [] if tr.halted is not None else ["never reached HALT"]
        out += [f"r{r} = {v} (expected {g['regs'][r]})" for r, v in enumerate(tr.regs) if v != g["regs"][r]]
        out += [f"mem[{a}] = {v} (expected {g['mem'][a]})" for a, v in enumerate(tr.mem) if v != g["mem"][a]]
        return out
