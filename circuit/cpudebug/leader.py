"""Baker Street: leader-based scatter and gather.

Holmes stays at 221B (left of the schematic) and decides: he reads the reports that reach him, keeps the suspicion
notebook, sends errands (one to three blocks to check, each at a cycle on the back-trace) and names the bug and fix
once he is sure. He is gpt-6-astra (`holmes = chat`) or exact counting with the back-trace planner (`holmes = rule`).
Wiggins (`wiggins = on`) takes the orders to a forward post near the errands, hands them to idle boys there,
collects reports in his bag and runs the batch back to Baker Street when he has three, one has waited two ticks, or
no boy is out. Without Wiggins every boy walks back to 221B with his report and gets his next errand there.
The boys only probe their errand's blocks and report; they never accuse. Each makes small local choices (which item
next, re-measure a mismatch, bench-drive it, or run back): Jev, rule or random.
Bribed boys (`liar_frac`) hide the real bug (they report it clean) and frame an innocent block. The counting Holmes
asks a second boy to confirm every mismatch and, with the liar defence on, outvoted boys lose his trust.
"""
import random

from swarmcore.llm import JevClient, LLMClient, LLMError

from . import kb
from .solo import describe, heat_of

BOY_INSTRUCTION = (
    "You are one of Holmes's street boys, sent to check a few blocks of a broken CPU. A check shows a block's inputs, "
    "measured outputs ('out') and spec outputs ('spec_out'); a block is broken only where out differs from spec_out "
    "and that repeats when re-measured (about one row in twenty is a glitch). Do your errand, re-measure anything "
    "that mismatched, and run back with your report once you have something solid or are done.")

HOLMES_SYSTEM = """You are Sherlock Holmes directing a dozen street boys who debug a broken CPU for you. You never
leave Baker Street: you read the reports that reach you, send boys on errands, and name the broken block(s) and the
fix once you are sure.

{primer}

Each errand is one to three blocks for one boy, each checked at a cycle (use the back-trace suggestions, or cycles
where a block mismatched before). A mismatch needs a second boy to confirm it: glitches happen and some boys are
bribed (a bribed boy reports the real bug as clean and frames an innocent block). Reply with JSON only:
{{"thinking": "<short>", "assignments": [{{"blocks": ["<block>", ...], "cycles": [<cycle>, ...]}}, ...],
  "accuse": true|false, "fixes": [{{"block": "...", "port": "...", "type": "...", "key": "<fault key>"}}]}}
Give fixes (one, or two for two broken blocks) when accuse is true.

The netlist (name [stage] spec | inputs port<-net | outputs port:width | fault keys):
{netlist}"""


class Boy:
    def __init__(self, i, liar):
        self.id = i
        self.liar = liar
        self.pos = "HQ"
        self.errand = None
        self.done_items = set()
        self.notes = []
        self.travel = 0
        self.status = "idle"
        self.last = ""
        self.rechecked = set()

    def busy(self):
        return self.errand is not None


class BakerStreet:
    track = "leader"

    def __init__(self, eng):
        self.eng, self.case, self.cfg = eng, eng.case, eng.cfg
        c = self.cfg
        self.rng = random.Random(f"baker-{self.case.seed}")
        n = c["n_boys"]
        liars = set(self.rng.sample(range(1, n + 1), int(round(c["liar_frac"] * n))))
        self.boys = [Boy(i, i in liars) for i in range(1, n + 1)]
        self.nb = kb.Notebook(self.case, owner="H", need_sources=2 if c["liar_defence"] else 1,
                              defence=c["liar_defence"])
        self.bug_blocks = {f["block"] for f in self.case.faults}
        sl = sorted(b for b in self.case.slice_cycles() if b not in self.bug_blocks)
        self.frame = self.rng.choice(sl) if sl else None
        fc = self.case.slice_cycles().get(self.frame) or [self.case.n - 1]
        self.frame_cycle = fc[len(fc) // 2]
        self.tick = 0
        self.done = False
        self.forced = False
        self.answer = None
        self.answer_tick = None
        self.queue = []            # errands waiting for a boy
        self.outbox = []           # (arrive_tick, boy, report) walking to the post or to 221B
        self.bag = []              # (since_tick, boy_id, report) with Wiggins
        self.transit = []          # (arrive_tick, [reports]) Wiggins running to 221B
        self.post = 6
        self.new_reports = 0
        self.report_log = []       # viewer: (tick, boy, block, mismatch)
        self.calls = 0
        self.pid = 0
        self.plans = 0
        self.wiggins = c["wiggins"]
        if c["holmes"] == "chat":
            self.chat = LLMClient("openai", c["chat_model"], c["chat_key"], timeout=180, temperature=0.2)
            self.system = HOLMES_SYSTEM.format(primer=kb.primer(self.case), netlist=kb.netlist_text(self.case))
        if c["boy_policy"] == "jev":
            self.jev = JevClient(c["jev_provider"], c["jev_model"], c["jev_key"], timeout=c["request_timeout_s"])

    # ------------------------------------------------------------------ one tick
    def step(self):
        if self.done:
            return
        self.tick += 1
        self.deliver()
        if self.done:
            return
        self.plan()
        if self.done:
            return
        self.hand_out()
        self.boys_act()
        self.wiggins_run()
        if self.tick >= self.eng.deadline:
            self.final()

    def deliver(self):
        arrived = [x for x in self.outbox if x[0] <= self.tick]
        self.outbox = [x for x in self.outbox if x[0] > self.tick]
        for _, boy, rep in arrived:
            if self.wiggins:
                self.bag.append((self.tick, boy.id, rep))
                boy.pos = "post"
            else:
                self.ingest(boy.id, rep)
                boy.pos = "HQ"
            boy.status = "idle"
        got = [x for x in self.transit if x[0] <= self.tick]
        self.transit = [x for x in self.transit if x[0] > self.tick]
        for _, reps in got:
            for bid, rep in reps:
                self.ingest(bid, rep)
            self.eng.event("wiggins", f"Wiggins brings {len(reps)} report(s) to Baker Street")

    def ingest(self, bid, rep):
        for p in rep:
            self.pid += 1
            self.nb.add_probe(p, bid, self.pid, first_hand=False)
            self.report_log.append({"tick": self.tick, "boy": bid, "block": p["block"], "bad": bool(p["mismatch"])})
            self.eng.event("report", f"boy #{bid}: {p['block']} " + ("does NOT match its spec" if p["mismatch"]
                                                                       else "matches its spec"), block=p["block"])
        self.new_reports += 1

    def wiggins_run(self):
        if not self.wiggins or not self.bag:
            return
        out = sum(1 for b in self.boys if b.busy())
        oldest = min(t for t, _, _ in self.bag)
        if len(self.bag) >= 3 or self.tick - oldest >= 2 or out == 0:
            run = 1 + (1 if self.post > 5 else 0)
            self.transit.append((self.tick + run, [(bid, rep) for _, bid, rep in self.bag]))
            self.bag = []

    # ------------------------------------------------------------------ Holmes
    def plan(self):
        idle = [b for b in self.boys if not b.busy() and b.pos in (("post",) if self.wiggins else ("HQ",)) + ("HQ",)]
        if not self.new_reports and (self.queue or not idle) and self.tick > 1:
            return
        use_chat = (self.cfg["holmes"] == "chat" and self.calls < self.cfg["hq_max_calls"] - 1 and
                    not self.eng.over_budget() and (self.new_reports >= self.cfg["hq_min_new"] or self.tick == 1 or
                                                    (idle and not self.queue and not self.outbox and not self.transit)))
        self.new_reports = 0 if (use_chat or self.cfg["holmes"] != "chat") else self.new_reports
        if use_chat:
            try:
                return self.plan_chat(len(idle))
            except LLMError as e:
                self.eng.failure(e)
        ans = self.nb.answer()
        if ans and self.cfg["holmes"] != "chat":
            return self.accuse(ans, "Holmes (counting) names " + describe(ans))
        if self.cfg["holmes"] != "chat" or not self.queue:
            self.queue = self.rule_errands(max(len(idle), 1))

    def rule_errands(self, n):
        tasks, taken = [], {it[0] for b in self.boys if b.busy() for it in b.errand["items"]}
        for b, v in self.nb.suspects():
            if v["confirmed"] or b in taken:
                continue
            key = next((k for k in v["bad"] if not isinstance(k, tuple)), None)
            if key is not None:
                tasks.append((b, key, set(v["sources"])))
                taken.add(b)
        for _, b, c in self.nb.frontier(limit=6 * n):
            if b not in taken:
                tasks.append((b, c, set()))
                taken.add(b)
        tasks.sort(key=lambda t: self.case.col(t[0]))
        k = self.cfg["errand_max"]
        groups = [tasks[i:i + k] for i in range(0, len(tasks), k)][:max(n, 1)]
        return [{"items": [(b, c) for b, c, _ in g], "avoid": set().union(*[s for _, _, s in g]),
                 "why": "check " + ", ".join(f"{b}@{c}" for b, c, _ in g)} for g in groups]

    def plan_chat(self, n_idle):
        self.calls += 1
        sug = [f"{b}@{c}" for _, b, c in self.nb.frontier(limit=10)]
        conf = [{"block": b, "reported_bad_by_boys": sorted(map(str, v["sources"]))} for b, v in self.nb.suspects()
                if not v["confirmed"]]
        seen = [self.nb.summary(b, 3) for b, _ in self.nb.suspects()[:6]]
        cleared = sorted(self.nb.cleared())
        st = {"brief": self.case.brief(), "tick": self.tick, "ticks_left": self.eng.deadline - self.tick,
              "boys_idle": n_idle, "boys_out": sum(1 for b in self.boys if b.busy()),
              "suspects": seen, "needs_confirmation": conf, "cleared_blocks": cleared,
              "distrusted_boys": sorted(map(str, self.nb.distrust)), "back_trace_suggestions": sug,
              "planning_rounds_left": self.cfg["hq_max_calls"] - self.calls}
        out = self.eng.chat(self.chat, self.system, kb.dumps(st), max_tokens=1500)
        self.eng.event("holmes", "Holmes: " + str(out.get("thinking") or "plans")[:300])
        if out.get("accuse"):
            fixes = [kb.parse_fix(self.case, x) for x in (out.get("fixes") or [])][:2]
            fixes = [f for f in fixes if f]
            if fixes:
                return self.accuse({"fixes": fixes}, "Holmes names " + describe({"fixes": fixes}))
        errands = []
        for a in (out.get("assignments") or [])[:max(1, n_idle + 2)]:
            if not isinstance(a, dict):
                continue
            blocks = [b for b in (a.get("blocks") or []) if b in self.case.by and not self.case.by[b].trusted]
            cyc = a.get("cycles") or []
            items = []
            for i, b in enumerate(blocks[:self.cfg["errand_max"]]):
                try:
                    c = int(cyc[i])
                except (IndexError, TypeError, ValueError):
                    c = self.default_cycle(b)
                items.append((b, max(0, min(self.case.n - 1, c))))
            if items:
                errands.append({"items": items, "avoid": set(), "why": "Holmes: check " +
                                ", ".join(f"{b}@{c}" for b, c in items)})
        self.queue = errands or self.rule_errands(max(n_idle, 1))

    def default_cycle(self, b):
        fr = [c for _, x, c in self.nb.frontier(limit=40) if x == b]
        if fr:
            return fr[0]
        sl = self.case.slice_cycles().get(b)
        return sl[-1] if sl else self.case.n - 1

    def accuse(self, ans, why):
        self.answer, self.answer_tick, self.done = {"fixes": ans["fixes"]}, self.tick, True
        self.eng.event("accuse", why)

    def final(self):
        if self.done:
            return
        self.forced = True
        ans = None
        if self.cfg["holmes"] == "chat" and not self.eng.over_budget():
            try:
                st = {"brief": self.case.brief(), "suspects": [self.nb.summary(b, 3) for b, _ in self.nb.suspects()[:6]],
                      "cleared_blocks": sorted(self.nb.cleared()), "distrusted_boys": sorted(map(str, self.nb.distrust)),
                      "note": "Time is up: accuse now (accuse true, fixes required, no assignments)."}
                out = self.eng.chat(self.chat, self.system, kb.dumps(st), max_tokens=1200)
                fixes = [f for f in (kb.parse_fix(self.case, x) for x in (out.get("fixes") or [])[:2]) if f]
                ans = {"fixes": fixes} if fixes else None
            except LLMError as e:
                self.eng.failure(e)
        ans = ans or self.nb.answer(forced=True)
        self.accuse(ans or {"fixes": []}, "time is up; Holmes names " + describe(ans))

    # ------------------------------------------------------------------ boys
    def hand_out(self):
        for boy in self.boys:
            if boy.busy() or not self.queue:
                continue
            if boy.pos not in ("post", "HQ"):
                continue
            idx = next((i for i, e in enumerate(self.queue) if boy.id not in e["avoid"]), None)
            if idx is None:
                continue
            e = self.queue.pop(idx)
            boy.errand, boy.done_items, boy.notes, boy.rechecked = e, set(), [], set()
            first = e["items"][0][0]
            boy.travel = 1 if (self.wiggins and abs(self.case.col(first) - self.post) <= 3) else 2 if self.case.col(first) > 5 else 1
            boy.pos, boy.status, boy.last = self.anchor(first), "walking", e["why"]
        if self.wiggins:
            busy = [self.case.col(it[0]) for b in self.boys if b.busy() for it in b.errand["items"]]
            if busy:
                busy.sort()
                self.post = busy[len(busy) // 2]

    def options(self, boy):
        opts = {}
        for i, (b, c) in enumerate(boy.errand["items"]):
            if i not in boy.done_items:
                opts[f"C{i}"] = (f"check {b} at cycle {c}: {self.case.by[b].spec}", {"type": "check", "block": b, "cycle": c})
        for p in boy.notes:
            if p["mismatch"] and p["block"] not in boy.rechecked:
                if p["type"] != "check" and not self.eng.bench_free():
                    continue
                spec = {"type": "check", "block": p["block"], "cycle": p["cycle"]} if p["type"] == "check" else \
                    {"type": "drive", "block": p["block"], "kind": p["kind"]}
                opts[f"R_{p['block']}"] = (f"re-measure {p['block']}: it mismatched once (glitch or bug?)", spec)
        opts["RETURN"] = ("run back with your report now", None)
        return opts

    def rule_choice(self, boy, opts):
        r = [k for k in opts if k.startswith("R_")]
        if r:
            return r[0]
        c = [k for k in opts if k.startswith("C")]
        return c[0] if c else "RETURN"

    def boys_act(self):
        ready = []
        for boy in self.boys:
            if not boy.busy():
                continue
            if boy.travel > 0:
                boy.travel -= 1
                continue
            ready.append(boy)
        if not ready:
            return
        pol = self.cfg["boy_policy"]
        choices = {}
        if pol == "jev" and not self.eng.over_budget():
            jobs = []
            for boy in ready:
                opts = self.options(boy)
                crit = {k: v[0] for k, v in opts.items()}
                st = {"errand": boy.errand["why"], "ticks_left": self.eng.deadline - self.tick,
                      "seen": [kb.probe_view(p, 4) for p in boy.notes]}
                jobs.append((boy, opts, st, {"action": {"type": "choice", "criteria": crit,
                                                        "instructions": BOY_INSTRUCTION + " What next?"}}))
            res = self.eng.parallel([(self.jev, st, q) for _, _, st, q in jobs])
            for (boy, opts, _, _), r in zip(jobs, res):
                act = None
                if isinstance(r, dict):
                    act, _ = kb.jev_pick(r.get("action"), set(opts))
                choices[boy.id] = (opts, act or self.rule_choice(boy, opts))
        for boy in ready:
            if boy.id in choices:
                opts, act = choices[boy.id]
            else:
                opts = self.options(boy)
                if pol == "random":
                    act = "RETURN" if self.rng.random() < 0.15 else self.rng.choice(sorted(opts))
                else:
                    act = self.rule_choice(boy, opts)
            if act == "RETURN" or opts.get(act, (None, None))[1] is None:
                self.send_back(boy)
                continue
            spec = opts[act][1]
            p = self.eng.probe(boy.id, spec)
            if spec["type"] == "drive":
                boy.travel += self.eng.drive_cost()
            boy.notes.append(p)
            boy.pos = spec["block"] if spec["block"] in self.case.by and not spec["block"].startswith(("L:", "SIG:")) else \
                self.anchor(spec["block"])
            boy.status, boy.last = "probing", opts[act][0]
            if act.startswith("C"):
                boy.done_items.add(int(act[1:]))
            else:
                boy.rechecked.add(spec["block"])
            if len(boy.done_items) == len(boy.errand["items"]) and not any(k.startswith("R_") for k in self.options(boy)):
                self.send_back(boy)

    def anchor(self, name):
        if name.startswith("L:"):
            return self.case.by[name].dst[0]
        if name.startswith("SIG:"):
            return f"c{self.case.by[name].core}.sig_mix"
        return name

    def send_back(self, boy):
        rep = [self.lie(p) if boy.liar else p for p in boy.notes]
        here = boy.pos if boy.pos in self.case.by else None
        if self.wiggins:
            t = 0 if here is None or abs(self.case.col(here) - self.post) <= 3 else 1
        else:
            t = 1 + (1 if here is not None and self.case.col(here) > 5 else 0)
        self.outbox.append((self.tick + t, boy, rep))
        boy.errand, boy.status, boy.last = None, "returning", "running back with the report"

    def lie(self, p):
        b = p["block"]
        if b in self.bug_blocks:
            return kb.fabricate(self.case, b, self.rng, guilty_view=False)
        if b == self.frame:
            return kb.fabricate(self.case, b, self.rng, guilty_view=True, cycle=self.frame_cycle)
        if self.rng.random() < 0.3:
            return kb.fabricate(self.case, b, self.rng, guilty_view=True, cycle=p.get("cycle"))
        return p

    # ------------------------------------------------------------------ viewer
    def view(self):
        agents = []
        for b in self.boys:
            items = [it[0] for it in b.errand["items"]] if b.errand else []
            agents.append({"id": b.id, "block": b.pos if b.pos in self.case.by else None, "where": b.pos,
                           "status": b.status, "last": b.last, "role": "boy", "items": items,
                           "done": sorted(b.done_items)})
        runners = [{"boy": boy.id, "from": boy.pos if boy.pos in self.case.by else None, "arrive": t,
                    "to": "post" if self.wiggins else "HQ", "n": len(rep)} for t, boy, rep in self.outbox]
        ans = self.nb.answer()
        if not ans:
            sus = self.nb.suspects()
            if sus:
                fs = self.nb.fits(sus[0][0])
                ans = {"fixes": [kb.fault_answer(sus[0][0], fs[0])]} if fs else None
        openq = [{"block": b, "by": sorted(map(str, v["sources"]))} for b, v in self.nb.suspects() if not v["confirmed"]][:5]
        nxt = [f"{b}@{c}" for _, b, c in self.nb.frontier(limit=6)] if not self.done else []
        return {"agents": agents, "heat": heat_of(self.nb), "tick": self.tick, "post": self.post if self.wiggins else None,
                "holmes": {"calls": self.calls, "distrusted": sorted(map(str, self.nb.distrust)), "kind": self.cfg["holmes"],
                           "answer_now": ans, "open": openq, "next": nxt,
                           "confirmed": [b for b, v in self.nb.suspects() if v["confirmed"]]},
                "reports": self.report_log[-12:], "runners": runners,
                "transit": [{"arrive": t, "n": len(r)} for t, r in self.transit],
                "bag": len(self.bag), "queue": len(self.queue), "wiggins": self.wiggins}

    def detail(self, i):
        b = next((x for x in self.boys if x.id == i), None)
        if not b:
            return None
        return {"role": "boy", "id": b.id, "status": b.status, "where": b.pos, "last": b.last,
                "errand": b.errand["why"] if b.errand else None,
                "items": [f"{x}@{c}" for x, c in b.errand["items"]] if b.errand else [],
                "probes": [kb.probe_view(p, 3) for p in b.notes[-3:]],
                "reports_by_him": sum(1 for r in self.report_log if r["boy"] == b.id),
                "distrusted_by_holmes": str(b.id) in set(map(str, self.nb.distrust))}

    def liars(self):
        return [b.id for b in self.boys if b.liar]
