"""The investigators.

Scatter: Holmes (through Wiggins' back-trace) hands each Irregular one block, or one window of the failing test's
waveform with a few blocks in it. An Irregular only probes locally (check a block against its spec over a window of
cycles, or drive it alone on the bench) and reports.
Gather: Wiggins keeps the suspicion map. He walks back from the failing output through every block-cycle that was
checked and found innocent; the first unchecked block-cycles on that walk are the next frontier. A bug corrupts
everything after it, so a block that only passes on bad values is innocent, and a suspect whose bad values are
explained by another suspect upstream is a red herring.
Deduce: Holmes names the faulty block, the signal, the bug type and the fix (which param to put back to spec).

Who decides what, per mode:
  jev         Jev picks each probe, judges each block, and Jev Holmes names the bug and the fix
  hybrid      Jev picks each probe and which input to follow; the verdicts, tally and deduction are exact
  rule_swarm  the same swarm with exact rules everywhere (no model)
  cone        one exact tracer, one probe at a time (no model)
  genius      gpt-6-astra alone: whole netlist and failing test, its own probes, the same $ and probe budget
"""
import json
import random
from collections import Counter

from swarmcore.llm import JevClient, LLMClient, LLMError

from .netlist import BUG_TYPES

DRIVE_KINDS = {
    "corner": "drive it alone with corner values (all zeros, all ones, 0x55, 0xAA, ...) on every input",
    "sweep": "drive it alone sweeping the select / opcode input through every value with distinct data on each input",
    "boundary": "drive it alone with boundary pairs (a = b, a = b +- 1, 0 and 255)",
    "random": "drive it alone with ten random input vectors",
}

IRR_INSTRUCTION = (
    "You are one Irregular helping to debug a pipelined 8-bit CPU whose test failed. Exactly one combinational block "
    "is broken. You may only probe the block(s) you were given. A check shows, for each cycle, the block's inputs, its "
    "actual outputs ('out') and what its spec says the outputs should be for those same inputs ('spec_out'). The block "
    "is broken only if 'out' differs from 'spec_out' in some row. Values that look wrong for the program but equal "
    "spec_out mean the block is innocent: the bad value came in through its inputs from upstream. A bench drive tests "
    "the block alone; some bugs (a stuck bit, swapped inputs, an off-by-one at a boundary) only show for the right "
    "inputs.")
HOLMES_INSTRUCTION = (
    "You are Holmes, leading a team debugging a pipelined 8-bit CPU with exactly one broken combinational block. Your "
    "Irregulars probed blocks; each observation row shows inputs, actual outputs ('out') and the spec's outputs "
    "('spec_out') for the same inputs. The broken block is the one whose 'out' differs from 'spec_out'. A block whose "
    "outputs equal spec_out is innocent even if its values look wrong (it was fed bad values).")


def row_view(r):
    d = {"cycle": r["cycle"], "in": r["in"], "out": r["out"], "spec_out": r["spec"]}
    if r.get("instr"):
        d["instr"] = f"pc {r['instr']['pc']}: {r['instr']['text']}"
    return d


def probe_view(p, limit=6):
    if p["type"] == "check":
        title = f"check {p['block']} over cycles {p['window'][0]}-{p['window'][1]}"
    else:
        title = f"bench drive of {p['block']} ({p['kind']})"
    rows = p["rows"]
    # mismatching rows first so a short view still shows the evidence
    rows = sorted(rows, key=lambda r: r["ok"])[:limit]
    rows.sort(key=lambda r: (r["cycle"] is None, r["cycle"] or 0))
    return {"probe": title, "rows": [row_view(r) for r in rows]}


def jev_pick(answer, allowed):
    a = answer or {}
    probs = {k: float(v or 0) for k, v in (a.get("probabilities") or {}).items() if k in allowed}
    if not probs and a.get("choice") in allowed:
        probs = {a["choice"]: 1.0}
    if not probs:
        return None, {}
    return max(probs, key=lambda k: (probs[k], k)), probs


def jev_noul(answer):
    try:
        return max(0.0, min(1.0, float((answer or {}).get("noul"))))
    except (TypeError, ValueError):
        return None


def jev_meta(meta):
    u = (meta or {}).get("usage") or {}
    return {"model": (meta or {}).get("model"), "in": int(u.get("input_tokens") or 0),
            "out": int(u.get("output_tokens") or 0), "cost": float(u.get("cost") or 0)}


# ----------------------------------------------------------------------------------------------- the Irregulars
class Agent:
    def __init__(self, i):
        self.id = i
        self.assignment = None
        self.notes = []          # probe results this round
        self.used = 0
        self.done = True
        self.judgment = {}
        self.block = None        # where it stands on the schematic
        self.status = "idle"
        self.last = ""

    def reset(self, a):
        self.assignment, self.notes, self.used, self.done, self.judgment = a, [], 0, False, {}
        self.block = a["blocks"][0]
        self.status = "walking"
        self.last = a["why"]


def options(case, a, agent):
    """Probe options left for this Irregular: id -> (description, probe spec)."""
    done = {n.get("opt") for n in agent.notes}
    out = {}
    if a["kind"] == "block":
        b = a["blocks"][0]
        for c in a["cycles"][b][:3]:
            lo, hi = case.window_of(c)
            out[f"C{c}"] = (f"check {b} against its spec over cycles {lo}-{hi} (the failure's back-trace passes "
                            f"through it at cycle {c})", {"type": "check", "block": b, "cycle": c})
        for k, d in DRIVE_KINDS.items():
            out[f"D_{k}"] = (d, {"type": "drive", "block": b, "kind": k})
    else:
        for b in a["blocks"]:
            c = a["cycles"][b][0]
            lo, hi = case.window_of(c)
            out[f"B_{b}"] = (f"check {b} ({case.by[b].spec}) over cycles {lo}-{hi}",
                             {"type": "check", "block": b, "cycle": c})
    return {k: v for k, v in out.items() if k not in done}


def run_probe(case, spec):
    return case.check(spec["block"], spec["cycle"]) if spec["type"] == "check" else case.drive(spec["block"], spec["kind"])


def exact_judgment(case, agent):
    """What exact logic concludes from the rows this Irregular has seen."""
    per = {}
    for n in agent.notes:
        p = n["probe"]
        v = per.setdefault(p["block"], {"mismatch": False, "cycles": set(), "ports": Counter()})
        for r in p["rows"]:
            if r["cycle"] is not None:
                v["cycles"].add(r["cycle"])
            if not r["ok"]:
                v["mismatch"] = True
                for port in r["out"]:
                    if r["out"][port] != r["spec"][port]:
                        v["ports"][port] += 1
    return per


class RuleIrregular:
    """Exact rules: check the back-trace windows in order; if the block is caught, drive it until the fault fits
    one explanation; then report."""
    uses_model = False

    def __init__(self, cfg):
        self.cfg = cfg

    def decide(self, case, agent, final=False):
        if final:
            return "REPORT", {}, None
        opts = options(case, agent.assignment, agent)
        per = exact_judgment(case, agent)
        caught = [b for b, v in per.items() if v["mismatch"]]
        if caught:
            b = caught[0]
            rows = [r for n in agent.notes for r in n["probe"]["rows"] if n["probe"]["block"] == b]
            if len(case.fit(b, rows)) > 1:
                for k in ("D_sweep", "D_corner", "D_boundary", "D_random"):
                    if k in opts:
                        return k, {}, None
            return "REPORT", {}, None
        checks = [k for k in opts if k[0] in "CB"]
        if agent.assignment["kind"] == "block":
            return (checks[0] if checks and agent.used == 0 else "REPORT"), {}, None
        return (checks[0] if checks else "REPORT"), {}, None


class JevIrregular:
    """One Jev call per decision: which probe next (or report), plus the Irregular's own reading of what it saw."""
    uses_model = True

    def __init__(self, cfg, judge=True):
        self.cfg = cfg
        self.judge = judge      # False in hybrid mode: Jev only steers, exact logic judges
        self.client = JevClient(cfg["jev_provider"], cfg["jev_model"], cfg["jev_key"], timeout=cfg["request_timeout_s"])

    def state(self, case, agent):
        a = agent.assignment
        return {"you": f"Irregular #{agent.id}", "failure": case.failure_text(), "task": a["why"],
                "blocks": {b: {"spec": case.by[b].spec, "inputs": case.by[b].ins, "outputs": list(case.by[b].outs)}
                           for b in a["blocks"]},
                "seen": [probe_view(n["probe"]) for n in agent.notes],
                "probes_left": self.cfg["probes_per_irregular"] - agent.used}

    def questions(self, case, agent, opts, final):
        a = agent.assignment
        q = {}
        if not final:
            crit = {k: v[0] for k, v in opts.items()}
            crit["REPORT"] = "stop probing and report what you found"
            q["action"] = {"type": "choice", "criteria": crit,
                           "instructions": "Which probe should you do next? Pick REPORT once you have caught the block "
                                           "misbehaving, or once what you have seen is enough."}
        if not agent.notes:
            return q
        if a["kind"] == "block":
            b = a["blocks"][0]
            if self.judge:
                q["faulty"] = {"type": "noul", "instructions":
                               f"Is {b} itself broken? Yes only if in some row its 'out' differs from 'spec_out'."}
            ins = {p: f"input {p} (from {n})" for p, n in case.by[b].ins.items()}
            ins["NONE"] = "none of them / the block itself is the problem"
            q["upstream"] = {"type": "choice", "criteria": ins, "instructions":
                             f"If {b} matches its spec, which input most likely carried the bad value into it, "
                             "so it should be checked next?"}
        elif self.judge:
            checked = sorted({n["probe"]["block"] for n in agent.notes})
            crit = {b: f"{b}: {case.by[b].spec}" for b in checked}
            crit["NONE"] = "every block I checked matched its spec"
            q["suspect"] = {"type": "choice", "criteria": crit, "instructions":
                            "Which checked block is itself broken ('out' differs from 'spec_out' in some row)?"}
            q["faulty"] = {"type": "noul", "instructions": "How sure are you that the block you named is broken?"}
        return q

    def decide(self, case, agent, final=False):
        opts = {} if final else options(case, agent.assignment, agent)
        q = self.questions(case, agent, opts, final)
        if not q:
            return "REPORT", {}, None
        answers, meta = self.client.ask(json.dumps(self.state(case, agent), separators=(",", ":"), default=str), q,
                                        retries=0)
        act = "REPORT"
        if not final:
            act, _ = jev_pick(answers.get("action"), set(opts) | {"REPORT"})
            if act is None:
                raise LLMError("no usable action from Jev")
        j = {}
        if "faulty" in q:
            j["faulty"] = jev_noul(answers.get("faulty"))
        if "upstream" in q:
            j["upstream"], _ = jev_pick(answers.get("upstream"), set(q["upstream"]["criteria"]))
        if "suspect" in q:
            j["suspect"], _ = jev_pick(answers.get("suspect"), set(q["suspect"]["criteria"]))
        return act, j, jev_meta(meta)


# ------------------------------------------------------------------------------------------------- Wiggins
class Board:
    """Wiggins' notebook: what has been cleared, who is suspected, and every row anyone has seen."""

    def __init__(self, case, cfg):
        self.case, self.cfg = case, cfg
        self.cleared = {}          # block -> cycles checked and found innocent
        self.susp = {}             # block -> {"score", "n", "ports": Counter, "cycles": set, "by": [ids]}
        self.inconclusive = Counter()
        self.rows = {}             # block -> every observed row (for fitting the fault)
        self.boost = Counter()     # block -> priority penalty (+) or bonus (-) for the next frontier
        self.herring = {}          # block -> the upstream suspect that explains it
        self.probes = []           # log
        self.assigned = Counter()  # times each block was handed out

    def suspects(self, live=True):
        out = [(b, s) for b, s in self.susp.items() if not (live and b in self.herring)]
        out.sort(key=lambda x: (-x[1]["score"], -x[1]["n"], x[0]))
        return out

    def add_rows(self, probe):
        self.rows.setdefault(probe["block"], []).extend(probe["rows"])

    def frontier(self, limit=60):
        stopped = {b for b, s in self.suspects() if s["score"] >= self.cfg["suspect_above"]}
        boost = {b: 0.6 * v for b, v in self.boost.items()}
        return self.case.frontier(self.cleared, stopped, boost, limit=limit)


class Wiggins:
    def __init__(self, case, cfg, board, exact):
        self.case, self.cfg, self.board, self.exact = case, cfg, board, exact

    def scatter(self, n, rnd):
        """Up to n assignments for this round."""
        c, bd = self.case, self.board
        out, used = [], set()
        # 1. confirm the leading suspect (exact: until one fault explains it; Jev: a second opinion)
        for b, s in bd.suspects()[:2]:
            if len(out) >= max(1, n // 4):
                break
            need = (len(c.fit(b, bd.rows.get(b, []))) > 1) if self.exact else \
                (s["n"] < 2 and s["score"] < 0.9 and bd.assigned[b] < 3)
            if need:
                cyc = sorted(s["cycles"]) or [c.starts[0][1]]
                out.append({"kind": "block", "blocks": [b], "cycles": {b: cyc[:3]}, "confirm": True,
                            "why": f"{b} looks guilty; confirm it and pin down how it misbehaves"})
                used.add(b)
        # 2. the back-trace frontier
        fr = bd.frontier()
        order, cyc = [], {}
        for pr, b, cy in fr:
            if b in used:
                continue
            if b not in cyc:
                order.append(b)
                cyc[b] = []
            cyc[b].append(cy)
        k = 0
        while order and len(out) < n:
            b = order.pop(0)
            if b in used:
                continue
            mode = self.cfg["assign"]
            as_window = mode == "window" or (mode == "mixed" and k % 2 == 1)
            k += 1
            if as_window:
                c0 = cyc[b][0]
                lo, hi = c0 - c.window, c0 + c.window
                group = [b] + [x for x in order if x not in used and any(lo <= y <= hi for y in cyc[x])][:4]
                if len(group) > 1:
                    for x in group:
                        used.add(x)
                    gc = {x: [min(cyc[x], key=lambda y: abs(y - c0))] for x in group}
                    out.append({"kind": "window", "blocks": group, "cycles": gc,
                                "why": f"check the blocks the failure traces back through around cycles {lo}-{hi}"})
                    order = [x for x in order if x not in used]
                    continue
            used.add(b)
            out.append({"kind": "block", "blocks": [b], "cycles": {b: cyc[b][:3]},
                        "why": f"the failure traces back through {b} at cycle{'s' if len(cyc[b]) > 1 else ''} "
                               f"{', '.join(map(str, cyc[b][:3]))}; check whether it obeys its spec"})
        for a in out:
            for b in a["blocks"]:
                bd.assigned[b] += 1
        return out

    def gather(self, agent, verdicts, upstream=None):
        """Fold one Irregular's report into the board. verdicts: block -> {"susp", "cycles", "ports"}."""
        bd, ev = self.board, []
        for b, v in verdicts.items():
            s = v["susp"]
            if s is None:
                bd.inconclusive[b] += 1
                bd.boost[b] += 2
                continue
            if s <= self.cfg["clear_below"]:
                bd.cleared.setdefault(b, set()).update(v["cycles"])
                ev.append(("clear", b, agent.id))
            elif s >= self.cfg["suspect_above"]:
                e = bd.susp.setdefault(b, {"score": 0.0, "n": 0, "ports": Counter(), "cycles": set(), "by": []})
                e["score"] = 1 - (1 - e["score"]) * (1 - s)
                e["n"] += 1
                e["ports"].update(v.get("ports") or {})
                e["cycles"].update(v["cycles"])
                e["by"].append(agent.id)
                ev.append(("suspect", b, agent.id))
            else:
                bd.inconclusive[b] += 1
                bd.boost[b] += 2
                ev.append(("unsure", b, agent.id))
        if upstream:
            b = agent.assignment["blocks"][0]
            net = self.case.by[b].ins.get(upstream)
            if net:
                d = self.case.drivers[net][0]
                bd.boost[d] -= 2
                ev.append(("follow", d, agent.id))
        return ev

    def red_herrings(self):
        """A suspect whose checked cycles lie downstream of another suspect is explained by it."""
        if not self.cfg["red_herrings"]:
            return []
        bd, ev = self.board, []
        sus = [b for b, s in bd.suspects(live=False) if s["score"] >= self.cfg["suspect_above"]]
        for x in sus:
            cx = sorted(bd.susp[x]["cycles"])
            if not cx:
                continue
            anc = self.case.ancestors((x, cx[-1]))
            for y in sus:
                if y != x and any(n[0] == y for n in anc) and y not in bd.herring:
                    if x not in bd.herring:
                        bd.herring[x] = y
                        ev.append(("herring", x, y))
                    break
        return ev


# --------------------------------------------------------------------------------------------------- Holmes
def fault_answer(block, f):
    return {"block": block, "port": f["port"], "type": f["type"], "key": f["key"], "value": f["value"],
            "desc": f["desc"]}


class ExactHolmes:
    uses_model = False

    def __init__(self, case, cfg):
        self.case, self.cfg = case, cfg

    def consider(self, board, final=False):
        c = self.case
        caught = [b for b, s in board.suspects() if s["score"] >= 0.99]
        if caught:
            b = caught[0]
            fits = c.fit(b, board.rows.get(b, []))
            if len(fits) == 1 or (fits and final):
                return fault_answer(b, fits[0]), f"{b} is caught: only one fault explains every row", None
            if final:
                bad = board.susp[b]["ports"].most_common(1)
                return {"block": b, "port": bad[0][0] if bad else list(c.by[b].outs)[0], "type": None, "key": None,
                        "desc": "no single fault explains the rows"}, f"{b} is caught, but no fault fits", None
            return None, None, None
        if not final:
            return None, None, None
        fr = board.frontier()
        if not fr:
            return None, "nothing left to suspect", None
        b = fr[0][1]
        fits = c.fit(b, board.rows.get(b, [])) or [f for f in c.by[b].faults if f["type"] != "stuck_at"] or c.by[b].faults
        return fault_answer(b, fits[0]), f"out of probes: guessing the next block on the back-trace, {b}", None


class JevHolmes:
    uses_model = True

    def __init__(self, case, cfg):
        self.case, self.cfg = case, cfg
        self.client = JevClient(cfg["jev_provider"], cfg["jev_model"], cfg["jev_key"], timeout=cfg["request_timeout_s"])

    def _state(self, board, cands):
        c = self.case
        sus = []
        for b in cands:
            s = board.susp.get(b)
            rows = sorted(board.rows.get(b, []), key=lambda r: r["ok"])[:5]
            sus.append({"block": b, "spec": c.by[b].spec, "reports_saying_broken": s["n"] if s else 0,
                        "suspicion": round(s["score"], 2) if s else 0.0,
                        "explained_by_upstream_suspect": board.herring.get(b),
                        "rows": [row_view(r) for r in rows]})
        return {"failure": c.failure_text(), "suspects": sus, "probes_left": self.cfg["probe_budget"] - len(board.probes),
                "blocks_cleared": len(board.cleared)}

    def _fix(self, board, b):
        c = self.case
        rows = board.rows.get(b, [])
        bad = [r for r in rows if not r["ok"]]
        cands = []
        for f in c.by[b].faults:
            if f["type"] == "stuck_at":
                _, port, bit = f["key"].split(":")
                bit = int(bit)
                if not any(((r["out"][port] ^ r["spec"][port]) >> bit) & 1 and ((r["out"][port] >> bit) & 1) == f["value"]
                           for r in bad):
                    continue
            cands.append(f)
        cands = cands[:16] or c.by[b].faults[:16]
        crit = {f"F{k}": f"{BUG_TYPES[f['type']]}: {f['desc']}" for k, f in enumerate(cands)}
        q = {"fix": {"type": "choice", "criteria": crit, "instructions":
                     f"{b} is the broken block. Which fault explains its rows (out vs spec_out)?"}}
        st = {"block": b, "spec": c.by[b].spec, "rows": [row_view(r) for r in sorted(rows, key=lambda r: r["ok"])[:8]]}
        answers, meta = self.client.ask(json.dumps(st, separators=(",", ":"), default=str), q, retries=1)
        pick, _ = jev_pick(answers.get("fix"), set(crit))
        f = cands[int(pick[1:])] if pick else cands[0]
        return fault_answer(b, f), jev_meta(meta)

    def consider(self, board, final=False):
        c = self.case
        cands = [b for b, s in board.suspects()][:6]
        if not cands:
            if not final:
                return None, None, None
            cands = list(dict.fromkeys(b for _, b, _ in board.frontier()))[:6]
            if not cands:
                return None, "nothing left to suspect", None
        crit = {b: f"{b}: {c.by[b].spec}" for b in cands}
        q = {"culprit": {"type": "choice", "criteria": dict(crit), "instructions":
                         "Which block is the broken one?" + ("" if final else " KEEP_LOOKING if the evidence is not "
                                                                               "yet enough.")}}
        if not final:
            q["culprit"]["criteria"]["KEEP_LOOKING"] = "not enough evidence yet; send the Irregulars out again"
            q["ready"] = {"type": "noul", "instructions": "Is the evidence already enough to name the broken block?"}
        answers, meta = self.client.ask(json.dumps(self._state(board, cands), separators=(",", ":"), default=str), q,
                                        retries=1)
        metas = [jev_meta(meta)]
        pick, _ = jev_pick(answers.get("culprit"), set(q["culprit"]["criteria"]))
        ready = 1.0 if final else (jev_noul(answers.get("ready")) or 0.0)
        if pick in (None, "KEEP_LOOKING") or ready < self.cfg["holmes_ready_at"]:
            if not final:
                return None, f"Holmes is not ready yet (ready {ready:.2f})", metas
            pick = pick if pick in crit else cands[0]
        ans, m2 = self._fix(board, pick)
        metas.append(m2)
        return ans, f"Holmes names {pick} (ready {ready:.2f})", metas


# ------------------------------------------------------------------------------------------------- the genius
GENIUS_SYSTEM = """You are an expert hardware debugger. A pipelined 8-bit CPU fails a test. Find the one broken block.

The CPU: 16-bit instructions, eight 8-bit registers (r0 is always 0), 64 bytes of data memory. Stages IF, ID, EX, MEM,
WB with pipeline registers between them. Branches resolve in EX (predict not taken, two younger instructions flushed);
EX/MEM and MEM/WB forward to EX; WB bypasses to the ID register read; a load followed by a dependent instruction
stalls one cycle. ISA: R-type ADD SUB AND OR XOR SLT SHL SHR (rd, rs1, rs2); ADDI rd, rs1, imm6; LDI rd, imm8;
LD rd, imm6(rs1); ST rt, imm6(rs1); BEQ/BNE/BLT rs1, rt, imm6 (target pc+1+imm6, unsigned compare); NOP; HALT.

Fault model: exactly one combinational block deviates from its spec through one parameter (its "fault key"):
  stuck_at          an output bit stuck at 0 or 1, key "stuck:<port>:<bit>"
  swapped_mux       two mux inputs swapped, key "swap:<a>:<b>"
  wrong_forwarding  a forwarding / bypass / hazard path wrong (keys listed per block)
  off_by_one        an adder, comparator, shift, field or sign bit off by one (keys listed per block)
Registers, the data memory and the instruction ROM are verified and never broken (marked [verified]).

Tools, per turn (you may use several):
  reads   free: {"net": "<block>.<port>", "from": c0, "to": c1} returns that net's value per cycle (at most 6 reads
          of at most 16 cycles each per turn)
  check   costs 1 probe: {"check": "<block>", "cycle": c} returns, for every cycle in a window around c, the block's
          inputs, actual outputs ("out") and its spec's outputs for those inputs ("spec_out"). The block is broken
          only where out differs from spec_out; a block that matches its spec but carries wrong values was fed them.
  drive   costs 1 probe: {"drive": "<block>", "kind": "corner"|"sweep"|"boundary"|"random"} tests the block alone
          on the bench with a batch of input vectors (out vs spec_out).
Probes and dollars are limited; stop as soon as you are sure. The failing value's start point(s) are given as
"<block>@<cycle>": that block's output at that cycle carried the wrong result.

Reply with JSON only:
{"thinking": "<short reasoning>", "reads": [...], "probes": [...],
 "answer": null or {"block": "<name>", "port": "<output port>", "type": "stuck_at|swapped_mux|wrong_forwarding|off_by_one",
                    "key": "<fault key>"}}
Give "answer" (and no probes) once you know; the fix is putting that key back to spec.

The netlist (name [stage] spec | inputs port<-net | outputs port:width | fault keys):
"""


class Genius:
    uses_model = True

    def __init__(self, case, cfg):
        self.case, self.cfg = case, cfg
        self.client = LLMClient("openai", cfg["chat_model"], cfg["chat_key"], timeout=180, temperature=0.2)
        self.system = GENIUS_SYSTEM + self.netlist_text()
        self.history = []

    def netlist_text(self):
        lines = []
        for b in self.case.blocks:
            ins = ", ".join(f"{p}<-{n}" for p, n in b.ins.items())
            outs = ", ".join(f"{p}:{w}" for p, w in b.outs.items())
            if b.trusted:
                fk = "[verified]"
            else:
                keys = [f"{f['key']}={f['value']} ({f['desc']})" for f in b.faults if f["type"] != "stuck_at"]
                fk = "; ".join(keys + ["stuck:<port>:<bit>"])
            lines.append(f"{b.name} [{b.stage}] {b.spec} | {ins} | {outs} | {fk}")
        return "\n".join(lines)

    def user(self, turn, probes_left, usd_left, final):
        c = self.case
        occ = c.occupancy()
        pipe = [f"c{k}: " + " ".join(f"{s}={'-' if pc is None else pc}" for s, pc in zip(("IF", "ID", "EX", "MEM", "WB"), row))
                for k, row in enumerate(occ)]
        st = {"turn": turn, "brief": c.brief(), "pipeline_pc_per_cycle": pipe, "history": self.history[-12:],
              "probes_left": probes_left, "budget_left_usd": round(usd_left, 3)}
        if final:
            st["note"] = "No budget left: give your final answer now (answer required, no reads or probes)."
        return json.dumps(st, separators=(",", ":"), default=str)

    def turn(self, turn, probes_left, usd_left, final=False):
        out = self.client.chat(self.system, self.user(turn, probes_left, usd_left, final), json_mode=True,
                               max_tokens=2500, retries=1)
        u = self.client.last_usage or {}
        tin = int(u.get("prompt_tokens") or 0)
        cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        tout = int(u.get("completion_tokens") or 0)
        cfg = self.cfg
        cost = ((tin - cached) * cfg["chat_price_in"] + cached * cfg["chat_price_cached"] + tout * cfg["chat_price_out"]) / 1e6
        return out, {"model": self.client.model, "in": tin, "cached": cached, "out": tout, "cost": cost}

    def do_reads(self, reads):
        c, res = self.case, []
        for r in (reads or [])[:6]:
            try:
                net = str(r.get("net"))
                lo = max(0, int(r.get("from", 0)))
                hi = min(c.n - 1, int(r.get("to", lo)), lo + 15)
            except (TypeError, ValueError, AttributeError):
                continue
            if net not in c.drivers:
                res.append({"net": net, "error": "no such net"})
                continue
            res.append({"net": net, "values": {k: c.trace.vals[k][net] for k in range(lo, hi + 1)}})
        return res

    def parse_probes(self, probes):
        c, out = self.case, []
        for p in probes or []:
            if not isinstance(p, dict):
                continue
            if p.get("check") in c.by:
                try:
                    cy = max(0, min(c.n - 1, int(p.get("cycle", 0))))
                except (TypeError, ValueError):
                    continue
                out.append({"type": "check", "block": p["check"], "cycle": cy})
            elif p.get("drive") in c.by:
                k = p.get("kind") if p.get("kind") in DRIVE_KINDS else "corner"
                out.append({"type": "drive", "block": p["drive"], "kind": k})
        return out[:self.cfg["probes_per_turn"]]

    def parse_answer(self, a):
        c = self.case
        if not isinstance(a, dict) or a.get("block") not in c.by:
            return None
        b = c.by[a["block"]]
        key = str(a.get("key") or "")
        f = next((f for f in b.faults if f["key"] == key), None)
        port = a.get("port") if a.get("port") in b.outs else (f["port"] if f else list(b.outs)[0])
        typ = a.get("type") if a.get("type") in BUG_TYPES else (f["type"] if f else None)
        return {"block": b.name, "port": port, "type": typ, "key": key or None,
                "value": f["value"] if f else None, "desc": f["desc"] if f else "(fault key not in the catalogue)"}


def make_irregular(mode, cfg):
    if mode == "jev":
        return JevIrregular(cfg, judge=True)
    if mode == "hybrid":
        return JevIrregular(cfg, judge=False)
    return RuleIrregular(cfg)


def make_holmes(mode, case, cfg):
    return JevHolmes(case, cfg) if mode == "jev" else ExactHolmes(case, cfg)


def rng_for(seed, what):
    return random.Random(f"{seed}-{what}")
