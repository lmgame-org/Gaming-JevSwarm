"""Solo debugger: one investigator, one probe at a time, a probe budget and a time limit.

Each probe (check, bench drive, or for the genius a waveform read) costs one probe and one tick (15 case minutes);
walking more than three schematic columns to the next block costs one more tick. The debugger accuses when it is
sure; at the end of its probes or time it must accuse anyway.

Policies: rule (robust cone tracing: re-measure any mismatch, then follow the back-trace), jev (Jev picks each probe
and, when accusing, the bug and fix), chat (gpt-6-astra reads the netlist and its notes each turn and asks for probes),
random.
"""
import random

from swarmcore.llm import JevClient, LLMClient, LLMError

from . import kb

JEV_SOLO = (
    "You are debugging a pipelined 8-bit CPU whose test failed, one probe at a time with a small probe budget. "
    "Exactly one combinational block is broken (rarely two). A check shows a block's inputs, measured outputs ('out') "
    "and spec outputs ('spec_out'); the block is broken only where out differs from spec_out and the difference "
    "repeats when measured again (about one row in twenty is a glitch). Work back from the failure along the "
    "back-trace; re-measure a block that mismatched once; accuse once a block has mismatched twice.")

GENIUS_TOOLS = """Tools, per turn (each costs one probe from your budget and 15 minutes of bench time):
  read    {"read": "<block>.<port>", "from": c0, "to": c1}: that net's values per cycle (at most 16 cycles)
  check   {"check": "<block>", "cycle": c}: for every cycle in a 2-cycle window at c, the block's inputs, measured
          outputs ("out") and spec outputs ("spec_out")
  drive   {"drive": "<block>", "kind": "corner"|"sweep"|"boundary"|"random"}: the block alone on the bench
The back-trace start points "<block>@<cycle>" are where the wrong final values came from (found by reading the
final state; they are free). Reply with JSON only:
{"thinking": "<short>", "probes": [...], "answer": null or {"fixes": [{"block": "...", "port": "...",
 "type": "stuck_at|swapped_mux|wrong_forwarding|off_by_one", "key": "<fault key>"}]}}
Give "answer" (one fix, or two if you found two broken blocks) once you are sure, or when told time is up.

The netlist (name [stage] spec | inputs port<-net | outputs port:width | fault keys):
"""


class Solo:
    track = "solo"

    def __init__(self, eng):
        self.eng, self.case, self.cfg = eng, eng.case, eng.cfg
        self.policy = self.cfg["solo_policy"]
        self.nb = kb.Notebook(self.case, owner=1, need_sources=1, defence=False)
        self.tick = 0
        self.used = 0
        self.pos = None
        self.done = False
        self.forced = False
        self.answer = None
        self.answer_tick = None
        self.rng = random.Random(f"solo-{self.case.seed}")
        self.status, self.last = "thinking", ""
        self.recent = []
        self.history = []
        self.turns = 0
        if self.policy == "jev":
            self.jev = JevClient(self.cfg["jev_provider"], self.cfg["jev_model"], self.cfg["jev_key"],
                                 timeout=self.cfg["request_timeout_s"])
        if self.policy == "chat":
            self.chat = LLMClient("openai", self.cfg["chat_model"], self.cfg["chat_key"], timeout=180, temperature=0.2)
            self.system = ("You are an expert hardware debugger working alone with a small probe budget.\n\n" +
                           kb.CPU_PRIMER + "\n\n" + GENIUS_TOOLS + kb.netlist_text(self.case))

    # ------------------------------------------------------------------ mechanics
    def travel(self, b):
        if self.pos is None or b is None:
            return 0
        return 1 if abs(self.case.col(self.pos) - self.case.col(b)) > 3 else 0

    def do(self, spec):
        """Run one probe; returns the stripped result."""
        b = spec.get("block")
        self.tick += 1 + self.travel(b)
        self.used += 1
        if spec["type"] == "read":
            vals = self.case.read(spec["net"], spec["from"], spec["to"])
            self.eng.log_probe(1, {"type": "read", "block": spec["net"].split(".")[0], "mismatch": False,
                                   "window": [min(vals), max(vals)] if vals else None},
                               f"reads {spec['net']} over cycles {min(vals) if vals else '-'}-{max(vals) if vals else '-'}")
            self.pos = spec["net"].split(".")[0]
            return {"type": "read", "net": spec["net"], "values": vals}
        p = self.eng.probe(1, spec)
        self.nb.add_probe(p, 1, self.used)
        self.pos = b
        self.recent.append(p)
        return p

    def accuse(self, ans, why):
        ans = {"fixes": list((ans or {}).get("fixes") or [])} if ans else None
        self.answer, self.answer_tick, self.done = ans, self.tick, True
        self.eng.event("accuse", why)

    def out_of_time(self):
        return self.used >= self.cfg["probe_budget"] or self.tick >= self.eng.deadline

    # ------------------------------------------------------------------ one step
    def step(self):
        if self.done:
            return
        if self.out_of_time():
            return self.final()
        try:
            if self.policy == "chat":
                return self.step_chat()
            if self.policy == "jev" and not self.eng.over_budget():
                return self.step_jev()
        except LLMError as e:
            self.eng.failure(e)
        if self.policy == "random":
            return self.step_random()
        return self.step_rule()

    def rule_next(self):
        """(spec, why) for the robust cone tracer, or ("ACCUSE", answer)."""
        nb = self.nb
        for b, v in nb.suspects():
            if v["confirmed"]:
                continue
            key = v["bad"][0]
            if isinstance(key, tuple):
                return {"type": "drive", "block": b, "kind": key[1]}, f"re-drive {b} to see if the mismatch repeats"
            return {"type": "check", "block": b, "cycle": key}, f"re-check {b} at cycle {key}: glitch or bug?"
        ans = nb.answer()
        if ans:
            return "ACCUSE", ans
        fr = nb.frontier(limit=1)
        if fr:
            _, b, c = fr[0]
            return {"type": "check", "block": b, "cycle": c}, f"next on the back-trace: {b} at cycle {c}"
        return "ACCUSE", nb.answer(forced=True)

    def step_rule(self):
        spec, why = self.rule_next()
        if spec == "ACCUSE":
            return self.accuse(why, "accuses: " + describe(why))
        self.last = why
        self.do(spec)

    def step_random(self):
        sl = self.case.slice_cycles()
        b = self.rng.choice(sorted(sl))
        self.last = "random check"
        self.do({"type": "check", "block": b, "cycle": self.rng.choice(sl[b])})

    def final(self):
        self.forced = True
        ans = None
        if self.policy == "chat":
            try:
                ans = self.chat_turn(final=True)
            except LLMError as e:
                self.eng.failure(e)
        elif self.policy == "jev" and not self.eng.over_budget():
            try:
                ans = self.jev_accuse()
            except LLMError as e:
                self.eng.failure(e)
        elif self.policy == "random":
            opts = kb.vote_options(self.case, self.nb)
            if opts:
                ans = {"fixes": [opts[self.rng.choice(sorted(opts))]]}
            else:
                b = self.rng.choice(sorted(self.case.slice_cycles()))
                ans = {"fixes": [kb.fault_answer(b, self.rng.choice(self.case.by[b].faults))]}
        if not ans or not ans.get("fixes"):
            ans = self.nb.answer(forced=True)
        self.accuse(ans, "out of probes or time; must accuse: " + describe(ans))

    # ------------------------------------------------------------------ Jev
    def jev_state(self):
        return {"failure": self.case.failure_text(), "probes_left": self.cfg["probe_budget"] - self.used,
                "ticks_left": self.eng.deadline - self.tick,
                "suspects": [self.nb.summary(b) for b, _ in self.nb.suspects()[:4]],
                "blocks_cleared": len(self.nb.cleared()),
                "last_probes": [kb.probe_view(p, 4) for p in self.recent[-3:]]}

    def step_jev(self):
        nb, opts = self.nb, {}
        for _, b, c in nb.frontier(limit=4):
            opts[f"C|{b}|{c}"] = (f"check {b} at cycle {c} (on the back-trace from the failure): {self.case.by[b].spec}",
                                  {"type": "check", "block": b, "cycle": c})
        for b, v in nb.suspects()[:2]:
            key = v["bad"][0]
            if not isinstance(key, tuple):
                opts[f"R|{b}|{key}"] = (f"re-check {b} at cycle {key}: it mismatched there once",
                                        {"type": "check", "block": b, "cycle": key})
            for k in ("sweep", "boundary"):
                opts[f"D|{b}|{k}"] = (f"bench-drive {b}: " + kb.DRIVE_KINDS[k], {"type": "drive", "block": b, "kind": k})
        crit = {k: v[0] for k, v in opts.items()}
        if nb.suspects():
            crit["ACCUSE"] = "accuse now: name the broken block and the fix"
        if not crit:
            return self.step_rule()
        q = {"action": {"type": "choice", "instructions": JEV_SOLO + " What next?", "criteria": crit}}
        ans = self.eng.jev(self.jev, self.jev_state(), q)
        act, _ = kb.jev_pick(ans.get("action"), set(crit))
        if act is None:
            raise LLMError("no usable action")
        if act == "ACCUSE":
            return self.accuse(self.jev_accuse(), "Jev accuses")
        self.last = opts[act][0]
        self.do(opts[act][1])

    def jev_accuse(self):
        opts = kb.vote_options(self.case, self.nb, limit=8)
        if not opts:
            return self.nb.answer(forced=True)
        crit = {k: kb.fix_label(v) for k, v in opts.items()}
        q = {"fix": {"type": "choice", "criteria": crit,
                     "instructions": "Which block is broken and how? Pick the fault that explains the rows."}}
        ans = self.eng.jev(self.jev, self.jev_state(), q)
        pick, _ = kb.jev_pick(ans.get("fix"), set(crit))
        return {"fixes": [opts[pick or next(iter(opts))]]}

    # ------------------------------------------------------------------ the genius
    def chat_user(self, final):
        c = self.case
        occ = c.occupancy()
        pipe = [f"c{k}: " + " ".join(f"{s}={'-' if pc is None else pc}" for s, pc in zip(("IF", "ID", "EX", "MEM", "WB"), row))
                for k, row in enumerate(occ)]
        st = {"brief": c.brief(), "pipeline_pc_per_cycle": pipe, "history": self.history[-10:],
              "probes_left": self.cfg["probe_budget"] - self.used, "ticks_left": self.eng.deadline - self.tick,
              "budget_left_usd": round(self.cfg["budget_usd"] - self.eng.stats["cost"], 3)}
        if final:
            st["note"] = "No probes or time left: give your final answer now (answer required, no probes)."
        return kb.dumps(st)

    def chat_turn(self, final=False):
        self.turns += 1
        out = self.eng.chat(self.chat, self.system, self.chat_user(final), max_tokens=2500)
        think = str(out.get("thinking") or "")[:400]
        self.eng.event("genius", f"turn {self.turns}: {think}" if think else f"turn {self.turns}")
        a = out.get("answer")
        fixes = [kb.parse_fix(self.case, x) for x in ((a or {}).get("fixes") or [])][:2] if isinstance(a, dict) else []
        fixes = [f for f in fixes if f]
        if fixes:
            return {"fixes": fixes, "_probes": []}
        return {"fixes": [], "_probes": out.get("probes") or [], "_think": think}

    def step_chat(self):
        if self.turns >= self.cfg["max_turns"] or self.eng.over_budget():
            return self.final()
        self.status, self.last = "thinking", "reading the netlist and its notes"
        res = self.chat_turn()
        if res["fixes"]:
            res.pop("_probes", None)
            return self.accuse({"fixes": res["fixes"]}, "the genius accuses: " + describe(res))
        entry = {"turn": self.turns, "thinking": res.get("_think"), "results": []}
        self.history.append(entry)
        n = 0
        for p in res["_probes"]:
            if n >= self.cfg["probes_per_turn"] or self.out_of_time() or not isinstance(p, dict):
                break
            spec = self.parse_probe(p)
            if not spec:
                continue
            r = self.do(spec)
            n += 1
            entry["results"].append(r if r["type"] == "read" else kb.probe_view(r, 6))
            self.eng.pace()
        if not n:
            entry["note"] = "you asked for no valid probe; answer or ask for one"

    def parse_probe(self, p):
        c = self.case
        try:
            if p.get("check") in c.by:
                return {"type": "check", "block": p["check"], "cycle": max(0, min(c.n - 1, int(p.get("cycle", 0))))}
            if p.get("drive") in c.by:
                k = p.get("kind") if p.get("kind") in kb.DRIVE_KINDS else "corner"
                return {"type": "drive", "block": p["drive"], "kind": k}
            if p.get("read") in c.drivers:
                lo = int(p.get("from", 0))
                return {"type": "read", "net": p["read"], "from": lo, "to": int(p.get("to", lo + 7)),
                        "block": p["read"].split(".")[0]}
        except (TypeError, ValueError):
            return None
        return None

    # ------------------------------------------------------------------ viewer
    def view(self):
        heat = heat_of(self.nb)
        return {"agents": [{"id": 1, "block": self.pos, "status": self.status, "last": self.last, "role": "solo"}],
                "heat": heat, "tick": self.tick, "probes_used": self.used}


def describe(ans):
    fx = (ans or {}).get("fixes") or []
    return "; ".join(f"{f['block']}.{f['port']} ({f.get('desc')})" for f in fx) or "no answer"


def heat_of(nb, frontier=True):
    heat = {}
    for b, cyc in nb.cleared().items():
        heat[b] = [0.0, "c"]
    for b, v in nb.suspects():
        heat[b] = [1.0 if v["confirmed"] else 0.6, "x" if v["confirmed"] else "u"]
    if frontier:
        for pr, b, c in nb.frontier(limit=12):
            heat.setdefault(b, [round(max(0.1, 0.5 - 0.04 * pr), 2), "f"])
    return heat
