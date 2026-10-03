"""What an investigator knows, and the helpers every family shares.

A Notebook holds measured rows by block with their source (who measured them, in which probe). Verdicts are robust to
measurement noise and to lying sources:
  - a row key is a cycle of the failing test, or a bench vector ("d", kind, index);
  - per key, every (source, probe) counts once; a key is bad when mismatching rows outnumber matching ones, cleared
    when matching rows do;
  - a block is CONFIRMED when at least two bad measurements, from `need_sources` different sources, agree (a glitch
    does not repeat; a real bug does, even a rare-trigger one, because the inputs are the same);
  - liar defence: when three or more sources measured one key, the outvoted ones get a strike; two strikes and a
    source is distrusted and everything from it is ignored. A first-hand row counts double for its owner.
"""
import json
from collections import Counter

from swarmcore.llm import LLMError

from .netlist import BUG_TYPES

DRIVE_KINDS = {
    "corner": "drive it alone with corner values (all zeros, all ones, 0x55, 0xAA, ...) on every input",
    "sweep": "drive it alone sweeping the select / opcode input through every value with distinct data on each input",
    "boundary": "drive it alone with boundary pairs (a = b, a = b +- 1, 0 and 255)",
    "random": "drive it alone with ten random input vectors",
}


def row_key(p, k, r):
    return r["cycle"] if r["cycle"] is not None else ("d", p.get("kind"), k)


class Notebook:
    def __init__(self, case, owner=None, need_sources=1, defence=True, cap=None):
        self.case = case
        self.owner = owner
        self.need = need_sources
        self.defence = defence
        self.cap = cap
        self.rows = {}            # block -> {key: {(src, pid): row}}
        self.order = []           # (block, key, srcpid) in arrival order, for the memory cap
        self.distrust = set()
        self.strikes = Counter()
        self.version = 0

    # ------------------------------------------------------------------ input
    def add_probe(self, p, src, pid, first_hand=True):
        """Fold a probe result (or a reported / heard one) into the notebook. Returns False if rejected."""
        if src in self.distrust:
            return False
        b = p["block"]
        for k, r in enumerate(p["rows"]):
            key = row_key(p, k, r)
            slot = self.rows.setdefault(b, {}).setdefault(key, {})
            if (src, pid) in slot:
                continue
            slot[(src, pid)] = {"in": r["in"], "out": r["out"], "spec": r["spec"], "ok": r["ok"], "cycle": r["cycle"],
                                "instr": r.get("instr"), "first": first_hand and src == self.owner}
            self.order.append((b, key, (src, pid)))
            if self.defence:
                if src != self.owner:
                    mine = [x for sp, x in slot.items() if sp[0] == self.owner]
                    if mine and all(x["ok"] != r["ok"] for x in mine) and len(mine) >= 1:
                        self.strike(src)
                self._vote(b, key)
        self._trim()
        self.version += 1
        return True

    def _vote(self, b, key):
        slot = self.rows[b][key]
        live = {sp: r for sp, r in slot.items() if sp[0] not in self.distrust}
        srcs = {sp[0] for sp in live}
        if len(srcs) < 3:
            return
        w = Counter()
        for sp, r in live.items():
            w[r["ok"]] += 2 if r["first"] else 1
        if w[True] == w[False]:
            return
        maj = w[True] > w[False]
        for sp, r in live.items():
            if r["ok"] != maj and sp[0] != self.owner:
                self.strike(sp[0])

    def strike(self, src):
        self.strikes[src] += 1
        if self.strikes[src] >= 2:
            self.distrust.add(src)

    def _trim(self):
        if not self.cap:
            return
        while len(self.order) > self.cap:
            # forget the oldest heard row first; own rows are kept longest
            idx = next((i for i, x in enumerate(self.order) if x[2][0] != self.owner), 0)
            b, key, sp = self.order.pop(idx)
            slot = self.rows.get(b, {}).get(key)
            if slot is not None:
                slot.pop(sp, None)
                if not slot:
                    del self.rows[b][key]

    # ------------------------------------------------------------------ verdicts
    def tally(self, b, key):
        ok = bad = 0
        srcs = set()
        for sp, r in self.rows.get(b, {}).get(key, {}).items():
            if sp[0] in self.distrust:
                continue
            if r["ok"]:
                ok += 2 if r["first"] else 1
            else:
                bad += 2 if r["first"] else 1
                srcs.add(sp[0])
        return ok, bad, srcs

    def block_view(self, b):
        """{"bad": keys, "cleared": cycles, "confirmed": bool, "suspect": bool, "sources": set}. Confirmed needs one
        key measured bad, with the same wrong value, at least twice (by `need` different sources): a glitch does not
        repeat, a bug does."""
        bad, cleared, srcs, confirmed = [], set(), set(), False
        for key, slot in self.rows.get(b, {}).items():
            ok, bd, s = self.tally(b, key)
            if bd > ok:
                bad.append(key)
                srcs |= s
                # a real bug reads the same wrong value every time; two glitches almost never agree
                outs = Counter((json.dumps(r["out"], sort_keys=True), sp[0]) for sp, r in slot.items()
                               if not r["ok"] and sp[0] not in self.distrust)
                same = Counter()
                srcs_by = {}
                for (o, src), k in outs.items():
                    same[o] += k
                    srcs_by.setdefault(o, set()).add(src)
                if any(k >= 2 and len(srcs_by[o]) >= self.need for o, k in same.items()):
                    confirmed = True
            elif ok > bd and not isinstance(key, tuple):
                cleared.add(key)
        bad.sort(key=lambda k: (isinstance(k, tuple), str(k)))
        return {"bad": bad, "cleared": cleared, "confirmed": confirmed, "suspect": bool(bad), "sources": srcs}

    def verified(self, b):
        """True if this notebook's owner has itself reproduced a bad reading of `b`: at one key, at least three bad
        readings with the same value (one of them its own) and more bad readings than good ones. Trust, but verify."""
        for key, slot in self.rows.get(b, {}).items():
            live = [(sp, r) for sp, r in slot.items() if sp[0] not in self.distrust]
            n_ok = sum(1 for _, r in live if r["ok"])
            for sp0, m in live:
                if sp0[0] != self.owner or m["ok"]:
                    continue
                o = json.dumps(m["out"], sort_keys=True)
                k = sum(1 for _, r in live if not r["ok"] and json.dumps(r["out"], sort_keys=True) == o)
                if k >= 3 and k > n_ok:
                    return True
        return False

    def unverified_keys(self, b):
        """Bad keys of `b` heard from others that the owner has not measured itself yet."""
        out = []
        for key in self.block_view(b)["bad"]:
            if isinstance(key, tuple):
                continue
            if not any(sp[0] == self.owner for sp in self.rows[b][key]):
                out.append(key)
        return out

    def blocks(self):
        return list(self.rows)

    def cleared(self):
        return {b: v["cleared"] for b in self.rows for v in [self.block_view(b)] if v["cleared"]}

    def suspects(self):
        """[(block, view)] for blocks with bad keys, confirmed first, then most bad keys."""
        out = [(b, v) for b in self.rows for v in [self.block_view(b)] if v["suspect"]]
        out.sort(key=lambda x: (not x[1]["confirmed"], -len(x[1]["bad"]), x[0]))
        return out

    def live_rows(self, b):
        rows = []
        for key, slot in self.rows.get(b, {}).items():
            for sp, r in slot.items():
                if sp[0] not in self.distrust:
                    rows.append(r)
        return rows

    def fits(self, b):
        return self.case.fit(b, self.live_rows(b))

    def frontier(self, limit=40):
        stopped = {b for b, v in self.suspects()}
        return self.case.frontier(self.cleared(), stopped, limit=limit)

    def answer(self, forced=False, verify=False):
        """Exact deduction: up to two confirmed blocks with the fault that best explains each (with `verify`, only
        blocks the owner reproduced itself or that three independent trusted sources measured bad). When forced, fall back to the best suspect, then to the next block on
        the back-trace."""
        fixes = []
        sus = self.suspects()
        for b, v in sus:
            if not v["confirmed"] or (verify and not self.verified(b) and len(v["sources"]) < 3):
                continue
            fs = self.fits(b)
            if fs:
                fixes.append(fault_answer(b, fs[0]))
            if len(fixes) == 2:
                break
        if fixes or not forced:
            return {"fixes": fixes} if fixes else None
        for b, v in sus:
            fs = self.fits(b)
            if fs:
                return {"fixes": [fault_answer(b, fs[0])]}
        fr = self.frontier(limit=1)
        if fr:
            b = fr[0][1]
            f = next((f for f in self.case.by[b].faults if f["type"] != "stuck_at"), self.case.by[b].faults[0])
            return {"fixes": [fault_answer(b, f)]}
        return None

    def summary(self, b, limit=4):
        v = self.block_view(b)
        rows = sorted(self.live_rows(b), key=lambda r: r["ok"])[:limit]
        return {"block": b, "bad_measurements": len(v["bad"]), "confirmed": v["confirmed"],
                "cleared_cycles": len(v["cleared"]), "sources": sorted(map(str, v["sources"])),
                "rows": [row_view(r) for r in rows]}


# ------------------------------------------------------------------------------------------- shared helpers
def fault_answer(block, f):
    return {"block": block, "port": f["port"], "type": f["type"], "key": f["key"], "value": f["value"],
            "desc": f["desc"]}


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
    rows = sorted(p["rows"], key=lambda r: r["ok"])[:limit]
    rows.sort(key=lambda r: (r["cycle"] is None, r["cycle"] or 0))
    return {"probe": title, "rows": [row_view(r) for r in rows]}


def strip(p):
    """A probe as the investigators may see it (no hidden glitch flags)."""
    q = dict(p)
    q["rows"] = [{k: v for k, v in r.items() if not k.startswith("_")} for r in p["rows"]]
    return q


def fabricate(case, block, rng, guilty_view, cycle=None):
    """A bribed source's made-up check of `block`: clean rows for a block it is hiding, one wrong bit otherwise.
    Liars coordinate: a frame-up is always claimed at the same cycle, with the same wrong bit."""
    cyc = case.slice_cycles().get(block) or [case.n - 1]
    c = cycle if cycle is not None else rng.choice(cyc)
    p = case.check(block, c, rng)
    rows = []
    for r in p["rows"]:
        r = dict(r)
        if guilty_view:
            b = case.by[block]
            port = sorted(b.outs)[0]
            out = dict(r["spec"])
            out[port] ^= 1 << ((r["cycle"] or 0) % b.outs[port])
            r["out"], r["ok"] = out, False
        else:
            r["out"], r["ok"] = dict(r["spec"]), True
        rows.append(r)
    p["rows"] = rows
    p["mismatch"] = guilty_view
    return p


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


def chat_meta(client, cfg):
    u = client.last_usage or {}
    tin = int(u.get("prompt_tokens") or 0)
    cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    tout = int(u.get("completion_tokens") or 0)
    cost = ((tin - cached) * cfg["chat_price_in"] + cached * cfg["chat_price_cached"] + tout * cfg["chat_price_out"]) / 1e6
    return {"model": client.model, "in": tin, "cached": cached, "out": tout, "cost": cost}


def vote_options(case, nb, limit=6):
    """(block, fault) pairs worth voting for, from the notebook's suspects: label -> fault answer."""
    out = {}
    for b, v in nb.suspects():
        fs = nb.fits(b)[:3] or [f for f in case.by[b].faults if f["type"] != "stuck_at"][:2]
        for f in fs:
            lab = f"{b}|{f['key']}"
            out[lab] = fault_answer(b, f)
            if len(out) >= limit:
                return out
    return out


def fix_label(a):
    return f"{BUG_TYPES[a['type']]} in {a['block']}: {a['desc']}"


def dumps(x):
    return json.dumps(x, separators=(",", ":"), default=str)


def need_answer(ans):
    if not ans or not ans.get("fixes"):
        raise LLMError("no answer")
    return ans


def netlist_text(case):
    lines = []
    for b in case.blocks:
        ins = ", ".join(f"{p}<-{n}" for p, n in b.ins.items())
        outs = ", ".join(f"{p}:{w}" for p, w in b.outs.items())
        if b.trusted:
            fk = "[verified]"
        else:
            keys = [f"{f['key']}={f['value']} ({f['desc']})" for f in b.faults if f["type"] != "stuck_at"]
            fk = "; ".join(keys + ["stuck:<port>:<bit>"])
        lines.append(f"{b.name} [{b.stage}] {b.spec} | {ins} | {outs} | {fk}")
    return "\n".join(lines)


def parse_fix(case, a):
    if not isinstance(a, dict) or a.get("block") not in case.by:
        return None
    b = case.by[a["block"]]
    key = str(a.get("key") or "")
    f = next((f for f in b.faults if f["key"] == key), None)
    port = a.get("port") if a.get("port") in b.outs else (f["port"] if f else list(b.outs)[0])
    typ = a.get("type") if a.get("type") in BUG_TYPES else (f["type"] if f else None)
    return {"block": b.name, "port": port, "type": typ, "key": key or None, "value": f["value"] if f else None,
            "desc": f["desc"] if f else "(fault key not in the catalogue)"}


CPU_PRIMER = """The CPU: 16-bit instructions, eight 8-bit registers (r0 is always 0), 64 bytes of data memory. Stages IF, ID,
EX, MEM, WB with pipeline registers between them. Branches resolve in EX (predict not taken, two younger instructions
flushed); EX/MEM and MEM/WB forward to EX; WB bypasses to the ID register read; a load followed by a dependent
instruction stalls one cycle. ISA: R-type ADD SUB AND OR XOR SLT SHL SHR (rd, rs1, rs2); ADDI rd, rs1, imm6; LDI rd,
imm8; LD rd, imm6(rs1); ST rt, imm6(rs1); BEQ/BNE/BLT rs1, rt, imm6 (target pc+1+imm6, unsigned compare); NOP; HALT.

Fault model: one combinational block (sometimes two) deviates from its spec through one parameter (its fault key):
  stuck_at          an output bit stuck at 0 or 1, key "stuck:<port>:<bit>"
  swapped_mux       two mux inputs swapped, key "swap:<a>:<b>"
  wrong_forwarding  a forwarding / bypass / hazard path wrong (keys listed per block)
  off_by_one        an adder, comparator, shift, field or sign bit off by one (keys listed per block)
Some bugs are rare-trigger: they misbehave only for some input values. Measurements are noisy: about one row in
twenty has one glitched bit, so a single mismatch can be a glitch; a real bug repeats when measured again.
Registers, the data memory and the instruction ROM are verified and never broken.
A check row shows a block's inputs, its measured outputs ("out") and its spec's outputs for those inputs
("spec_out"). The block is broken only where out differs from spec_out (and the difference repeats); a block that
matches its spec but carries wrong values was fed them from upstream."""
