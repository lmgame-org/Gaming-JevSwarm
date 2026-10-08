"""Swarm: 100 Irregulars, no leader.

The Irregulars start spread over the schematic, one per block (wrapping round). Each knows the failure, what it has
measured itself, what others within radio range told it, and the votes it hears. Every tick (15 case minutes) each:
  CHECK  its current block at a cycle on the back-trace (one probe),
  MOVE   one wire to a neighbouring block,
  SHARE  its newest measurements with everyone within `comm_range` wires (each hearer takes in at most `bandwidth`
         shares a tick and remembers `memory_cap` rows),
  WAIT,
and states its vote: a broken block and the fault (or unsure). The case closes when `quorum_frac` of the swarm holds
the identical vote; when time runs out with no quorum the swarm has given no answer.

Liars (`liar_frac`) share made-up measurements that clear the real bug and frame one innocent block, and all vote for
the frame-up. Liar defence (`liar_defence`): each source counts once per measurement and a mismatch needs two sources
(Notebook); outvoted sources lose trust; plausibility: a first-hand claim about a block farther (in wires) from the
speaker's start than it could have walked by now is rejected and the speaker distrusted; votes of anyone distrusted
by two or more others are struck from the count.

Policies: rule, jev (Jev picks the action and the vote), hybrid (Jev picks the action, the vote is exact counting),
random.
"""
import random
from collections import Counter

from swarmcore.llm import JevClient

from . import kb

JEV_IRR = (
    "You are one Irregular in a swarm of 100 debugging a broken CPU with no leader. You can check the block you stand "
    "on, move one wire to a neighbouring block, share your measurements with Irregulars in radio range, or wait. A "
    "check shows inputs, measured outputs ('out') and spec outputs ('spec_out'); a block is broken only where out "
    "differs from spec_out and that repeats (about one row in twenty is a glitch). Some Irregulars lie. Work back "
    "from the failure along the back-trace; the swarm closes the case when enough of you vote the same answer.")


class Irr:
    def __init__(self, i, start, liar, case, cfg):
        self.id, self.start, self.pos, self.liar = i, start, start, liar
        self.nb = kb.Notebook(case, owner=i, need_sources=2 if cfg["liar_defence"] else 1,
                              defence=cfg["liar_defence"], cap=cfg["memory_cap"])
        self.unshared = []
        self.checked = Counter()
        self.done_cycles = {}
        self.vote = None
        self.heard = {}
        self.inbox = []
        self.action = "WAIT"
        self.last_view = None
        self.rng = random.Random(f"irr-{case.seed}-{i}")
        self.pid = 0
        self.visited = [start]
        self.plan = None
        self.last_call = -99


class Swarm:
    track = "swarm"

    def __init__(self, eng):
        self.eng, self.case, self.cfg = eng, eng.case, eng.cfg
        c = self.cfg
        self.rng = random.Random(f"swarm-{self.case.seed}")
        names = [b.name for b in self.case.blocks]
        order = names[:]
        self.rng.shuffle(order)
        n = c["n_agents"]
        liars = set(self.rng.sample(range(1, n + 1), int(round(c["liar_frac"] * n))))
        self.agents = [Irr(i, order[(i - 1) % len(order)], i in liars, self.case, c) for i in range(1, n + 1)]
        self.by = {a.id: a for a in self.agents}
        self.bug_blocks = {f["block"] for f in self.case.faults}
        sl = sorted(b for b in self.case.slice_cycles() if b not in self.bug_blocks)
        self.frame_block = self.rng.choice(sl) if sl else names[0]
        fb = self.case.by[self.frame_block]
        ff = next((f for f in fb.faults if f["type"] != "stuck_at"), fb.faults[0])
        self.frame = kb.fault_answer(self.frame_block, ff)
        self.frame_label = f"{self.frame_block}|{ff['key']}"
        fc = self.case.slice_cycles().get(self.frame_block) or [self.case.n - 1]
        self.frame_cycle = fc[len(fc) // 2]
        self.tick = 0
        self.done = False
        self.answer = None
        self.answer_tick = None
        self.wrong_quorum = False
        self.quorum = None
        self.shares = []
        self.tally = Counter()
        self.labels = {}
        self.series = []           # viewer: (tick, top vote count, label)
        if c["swarm_policy"] in ("jev", "hybrid"):
            self.jev = JevClient(c["jev_provider"], c["jev_model"], c["jev_key"], timeout=c["request_timeout_s"])

    # ------------------------------------------------------------------ helpers
    def in_range(self, a):
        d = self.case.hops_from(a.pos)
        R = self.cfg["comm_range"]
        return [x for x in self.agents if x is not a and d.get(x.pos, 99) <= R]

    def checkables(self, a):
        """What an Irregular standing on a block can probe: the block itself, and on the v3 chip also the wires that
        arrive at it and its own core's signature."""
        out = [a.pos]
        case = self.case
        if getattr(case, "tier", "") == "v3":
            k = case.core_of(a.pos)
            if k is not None:
                out.append(f"SIG:c{k}")
                loc = case.local(a.pos)
                base = case.core_by.get(loc)
                if base is not None:
                    out += [f"L:c{k}:{loc}.{p}" for p in base.ins]
        return out

    def cand_cycles(self, a):
        """[(name, cycle)] worth probing from here, best first."""
        out = []
        for b in self.checkables(a):
            if self.case.by[b].trusted:
                continue
            if b.startswith("SIG:"):
                if not a.nb.rows.get(b) and a.checked[b] < 2:
                    out.append((b, self.case.n - 1))
                continue
            sl = self.case.slice_cycles().get(b) or []
            if getattr(self.case, "tier", "") == "v3":
                k = self.case.core_of(b)
                if k is None or b.endswith("sig_mix"):
                    sl = [self.case.n - 1]                     # the signature fabric: look at the end of the run
                elif not a.nb.block_view(f"SIG:c{k}")["bad"]:
                    continue                                   # nobody has told me this core went wrong
            if not sl or a.checked[b] >= 6 or (a.checked[b] >= 3 and not a.nb.block_view(b)["bad"]):
                continue
            if self.cfg["liar_defence"] and not a.nb.verified(b):
                bad = [k for k in a.nb.block_view(b)["bad"] if not isinstance(k, tuple)]
                if bad:
                    out.insert(0, (b, bad[0]))  # reproduce a mismatch here (heard or my own) before anything else
                    continue
            cleared = a.nb.block_view(b)["cleared"]
            done = a.done_cycles.get(b, set())
            todo = [c for c in sl if c not in cleared and c not in done]
            if not todo:
                continue
            # spread: the latest few, plus a random earlier one
            pick = todo[-2:] + ([a.rng.choice(todo[:-2])] if len(todo) > 2 else [])
            out += [(b, c) for c in sorted(set(pick))]
        sig = [x for x in out if x[0].startswith("SIG:")]
        return sig + [x for x in out if not x[0].startswith("SIG:")]

    def anchor(self, name):
        """The real block where a wire or a core signature can be probed from."""
        if name.startswith("L:"):
            return self.case.by[name].dst[0]
        if name.startswith("SIG:"):
            return f"c{self.case.by[name].core}.sig_mix"
        return name

    def moves(self, a):
        """Neighbouring blocks, best first: unexplored back-trace blocks, then towards suspects, then the rest."""
        adj = self.case.adjacency()[a.pos]
        sl = self.case.slice_cycles()
        sus = [b for b, v in a.nb.suspects() if (not v["confirmed"] or a.vote is None) and
               (not self.cfg["liar_defence"] or not a.nb.verified(b))]
        tgt = sus[0] if sus else None
        cleared = a.nb.cleared()

        def score(x):
            s = 0.0
            if x in sl and not self.case.by[x].trusted:
                s -= 2
            if x in cleared:
                s += 1.5
            if x in a.visited[-6:]:
                s += 1
            if tgt:
                s += 0.8 * self.case.hops_from(tgt).get(x, 9)
            return s + a.rng.random() * 0.5
        return sorted(adj, key=score)[:4]

    def liar_action(self, a):
        d = self.case.hops_from(self.frame_block)
        if d.get(a.pos, 99) > 1:
            adj = self.case.adjacency()[a.pos]
            return ("MOVE", min(adj, key=lambda x: (d.get(x, 99), a.rng.random())))
        return ("SHARE", None) if self.in_range(a) else ("WAIT", None)

    def rule_action(self, a, chase=True):
        if a.liar:
            return self.liar_action(a)
        if a.unshared and (any(p["mismatch"] for p in a.unshared) or len(a.unshared) >= 2) and self.in_range(a):
            return ("SHARE", None)
        cc = self.cand_cycles(a)
        if cc:
            return ("CHECK", cc[0] if cc[0][0].startswith("SIG:") or cc[0][0] != a.pos else cc[-1])
        tgt = self.target(a) if chase else None
        if tgt and tgt != a.pos:
            d = self.case.hops_from(tgt)
            adj = self.case.adjacency()[a.pos]
            return ("MOVE", min(adj, key=lambda x: (d.get(x, 99), a.rng.random())))
        mv = self.moves(a)
        return ("MOVE", mv[0]) if mv else ("WAIT", None)

    def target(self, a):
        """A confirmed suspect this Irregular has not reproduced itself yet (nearest first), if any within 8 wires."""
        if not self.cfg["liar_defence"]:
            return None
        d = self.case.hops_from(a.pos)
        best = None
        for b, v in a.nb.suspects():
            if not v["confirmed"] or a.nb.verified(b) or self.case.by[b].trusted:
                continue
            if d.get(b, 99) <= 8 and (best is None or d.get(b, 99) < d.get(best, 99)):
                best = b
        return self.anchor(best) if best else None

    def rule_vote(self, a):
        defence = self.cfg["liar_defence"]
        ans = a.nb.answer(verify=defence)
        if ans:
            f = ans["fixes"][0]
            # agree on the fault: among the faults that fit my own rows, take the one most voted around me
            heard = Counter(v for sid, v in a.heard.items() if v and sid not in a.nb.distrust)
            fits = a.nb.fits(f["block"])
            best = max(fits, key=lambda x: (heard.get(f"{f['block']}|{x['key']}", 0), -fits.index(x))) if fits else None
            if best:
                f = kb.fault_answer(f["block"], best)
            return f"{f['block']}|{f['key']}", f
        if defence:
            return None, None  # with the defence an Irregular only votes for a bug it has reproduced itself
        votes = Counter(v for sid, v in a.heard.items() if v and sid not in a.nb.distrust)
        if votes:
            lab, n = votes.most_common(1)[0]
            blk = lab.split("|")[0]
            # a heard majority is adopted only when this Irregular's own notebook also suspects that block
            if n >= 3 and any(b == blk for b, _ in a.nb.suspects()):
                return lab, None
        return None, None

    def options(self, a):
        """A Jev Irregular's judgment call when news arrives: chase a suspect to measure it, keep tracing, share, wait."""
        opts = {}
        d = self.case.hops_from(a.pos)
        for b, v in a.nb.suspects()[:4]:
            if self.case.by[b].trusted or (b == a.pos and a.nb.verified(b)):
                continue
            state = "measured bad twice by others" if v["confirmed"] else "measured bad once (glitch or bug?)"
            here = b == a.pos
            opts[f"GO_{b}"] = ((f"measure {b} here yourself" if here else
                                f"go to {b} ({d.get(b, '?')} wires away; {state}) and measure it yourself"),
                               ("GO", self.anchor(b)))
        opts["TRACE"] = ("ignore it for now and keep tracing the failure back from where you are", ("TRACE", None))
        if a.unshared:
            opts["SHARE"] = (f"share your {len(a.unshared)} newest measurements with Irregulars in range", ("SHARE", None))
        opts["WAIT"] = ("wait", ("WAIT", None))
        return opts

    def jev_state(self, a):
        return {"you": f"Irregular #{a.id} at block {a.pos}", "failure": self.case.failure_text(),
                "ticks_left": self.eng.deadline - self.tick,
                "suspects": [a.nb.summary(b, 3) for b, _ in a.nb.suspects()[:3]],
                "my_last_checks": [kb.probe_view(p, 3) for p in a.unshared[-2:]],
                "votes_heard": dict(Counter(v for v in a.heard.values() if v).most_common(4)),
                "my_vote": a.vote, "blocks_cleared": len(a.nb.cleared())}

    def signature(self, a):
        """News worth a judgment call: confirmed suspects it has not reproduced itself, and (when Jev also votes)
        blocks it has just reproduced."""
        sus = a.nb.suspects()[:4]
        news = tuple(sorted(b for b, v in sus if v["confirmed"] and not a.nb.verified(b)))
        if self.cfg["swarm_policy"] == "jev":
            news += tuple(sorted("ok:" + b for b, v in sus if a.nb.verified(b)))
        return news

    def needs_decision(self, a):
        sig = self.signature(a)
        return bool(sig) and sig != a.last_view

    def follow(self, a):
        """One tick of the current plan (walking or checking)."""
        kind, arg = a.plan
        if kind == "TRACE":
            return self.rule_action(a, chase=False)
        if kind == "GO":
            if a.pos == arg:
                cc = self.cand_cycles(a)
                if cc:
                    return ("CHECK", cc[0])
                a.plan = None
                return self.rule_action(a, chase=False)
            d = self.case.hops_from(arg)
            nxt = min(self.case.adjacency()[a.pos], key=lambda x: (d.get(x, 99), a.rng.random()))
            if d.get(nxt, 99) == 0:
                a.plan = None
            return ("MOVE", nxt)
        if kind == "CHECKS":
            todo = [x for x in arg if x[1] not in a.done_cycles.get(x[0], set())]
            if not todo:
                a.plan = None
                return ("WAIT", None)
            if len(todo) == 1:
                a.plan = None
            return ("CHECK", todo[0])
        a.plan = None
        return (kind, arg)

    # ------------------------------------------------------------------ one tick
    def step(self):
        if self.done:
            return
        self.tick += 1
        pol = self.cfg["swarm_policy"]
        decisions = {}
        jobs = []
        if pol in ("jev", "hybrid") and not self.eng.over_budget():
            for a in self.agents:
                if a.liar or not self.needs_decision(a):
                    continue
                a.last_view = self.signature(a)
                a.last_call = self.tick
                opts = self.options(a)
                q = {"action": {"type": "choice", "instructions": JEV_IRR + " News: a block was measured bad. "
                                "What do you do?",
                                "criteria": {k: v[0] for k, v in opts.items()}}}
                vopts = kb.vote_options(self.case, a.nb) if pol == "jev" else {}
                if vopts:
                    crit = {k: kb.fix_label(v) for k, v in vopts.items()}
                    crit["UNSURE"] = "not sure yet"
                    q["vote"] = {"type": "choice", "criteria": crit,
                                 "instructions": "Your vote: which block is broken and how (or UNSURE)?"}
                jobs.append((a, opts, vopts, q))
            res = self.eng.parallel([(self.jev, self.jev_state(a), q) for a, _, _, q in jobs])
            for (a, opts, vopts, q), r in zip(jobs, res):
                if not isinstance(r, dict):
                    continue
                act, _ = kb.jev_pick(r.get("action"), set(opts))
                vote = None
                if "vote" in q:
                    v, _ = kb.jev_pick(r.get("vote"), set(q["vote"]["criteria"]))
                    vote = (v, vopts.get(v)) if v and v != "UNSURE" else ("UNSURE", None)
                a.plan = opts[act][1] if act else None
                decisions[a.id] = vote
        self.shares = []
        for a in self.agents:
            vote = decisions.get(a.id)
            if a.liar or pol == "rule" or (pol in ("jev", "hybrid") and self.eng.over_budget()):
                act = self.rule_action(a)
            elif pol == "random":
                if a.plan is None:
                    opts = self.options(a)
                    a.plan = opts[a.rng.choice(sorted(opts))][1]
                act = self.follow(a)
            elif a.plan is not None:
                act = self.follow(a)
            else:
                act = self.rule_action(a, chase=False)  # routine tracing between judgment calls is reflex
            self.act(a, act)
            self.set_vote(a, vote, asked=a.id in decisions)
        self.listen()
        self.count()
        if not self.done and self.tick >= self.eng.deadline:
            self.done = True
            self.eng.event("cold", "time is up with no quorum: the swarm gives no answer")

    def act(self, a, act):
        kind, arg = act
        a.action = kind
        if kind == "CHECK":
            name, cyc = arg if isinstance(arg, tuple) else (a.pos, arg)
            p = self.eng.probe(a.id, {"type": "check", "block": name, "cycle": cyc}, quiet=True)
            a.pid += 1
            a.nb.add_probe(p, a.id, a.pid)
            a.checked[name] += 1
            a.done_cycles.setdefault(name, set()).add(cyc)
            a.unshared.append(p)
            a.unshared = a.unshared[-4:]
        elif kind == "MOVE" and arg:
            a.pos = arg
            a.visited.append(arg)
        elif kind == "SHARE":
            near = self.case.hops_from(a.pos)
            msgs = [p for p in a.unshared if near.get(p["block"], 99) <= 2]
            if a.liar:
                # liars claim what serves the frame-up about wherever they stand (and, careless, about the frame-up
                # block itself from afar)
                msgs = [kb.fabricate(self.case, self.frame_block, a.rng, guilty_view=True, cycle=self.frame_cycle)]
                if a.pos in self.bug_blocks:
                    msgs.append(kb.fabricate(self.case, a.pos, a.rng, guilty_view=False))
            for x in self.in_range(a):
                x.inbox.append((a.id, msgs, a.vote))
            self.shares.append(a.pos)
            a.unshared = []

    def set_vote(self, a, vote, asked=False):
        pol = self.cfg["swarm_policy"]
        if a.liar:
            a.vote = self.frame_label
            self.labels[self.frame_label] = self.frame
            return
        if pol == "jev" and not self.eng.over_budget():
            if vote is not None:
                lab, ans = vote
                a.vote = None if lab == "UNSURE" else lab
                if ans:
                    self.labels[lab] = ans
            elif asked:
                a.vote = None
            return
        if pol == "random":
            opts = kb.vote_options(self.case, a.nb)
            heard = [v for v in a.heard.values() if v]
            pool = sorted(opts) + heard
            if pool and a.rng.random() < 0.5:
                a.vote = a.rng.choice(pool)
            for k, v in opts.items():
                self.labels.setdefault(k, v)
            return
        lab, ans = self.rule_vote(a)
        a.vote = lab
        if lab and ans:
            self.labels[lab] = ans

    def listen(self):
        bw, defence = self.cfg["bandwidth"], self.cfg["liar_defence"]
        for x in self.agents:
            for sid, msgs, vote in x.inbox[:bw]:
                if sid in x.nb.distrust:
                    continue
                spk = self.by[sid]
                if defence:
                    # you can only measure the block you stand on: a claim about a block more than two wires from
                    # where the speaker stands now is rejected, and the speaker distrusted
                    near = self.case.hops_from(spk.pos)
                    if any(near.get(m["block"], 99) > 2 for m in msgs):
                        x.nb.distrust.add(sid)
                        continue
                for m in msgs:
                    x.nb.add_probe(m, sid, ("h", sid, m["block"], m.get("cycle"), m.get("kind")), first_hand=False)
                x.heard[sid] = vote
            x.inbox = []

    def count(self):
        n = len(self.agents)
        struck = set()
        if self.cfg["liar_defence"]:
            dc = Counter(d for a in self.agents for d in a.nb.distrust)
            struck = {sid for sid, k in dc.items() if k >= 2}
        self.tally = Counter(a.vote for a in self.agents if a.vote and a.id not in struck)
        top = self.tally.most_common(1)
        self.series.append([self.tick, top[0][1] if top else 0, top[0][0] if top else None,
                            sum(1 for a in self.agents if a.vote)])
        if not self.tally:
            return
        lab, k = self.tally.most_common(1)[0]
        if k >= self.cfg["quorum_frac"] * n:
            ans = self.labels.get(lab)
            if ans is None:
                blk, key = lab.split("|", 1)
                f = next((f for f in self.case.by[blk].faults if f["key"] == key), None)
                ans = kb.fault_answer(blk, f) if f else None
            self.answer = {"fixes": [ans]} if ans else {"fixes": []}
            self.answer_tick, self.done, self.quorum = self.tick, True, lab
            g = self.case.grade(self.answer)
            self.wrong_quorum = not g["fix_ok"]
            self.eng.event("quorum", f"quorum: {k} of {n} vote {lab.replace('|', ' / ')}")

    # ------------------------------------------------------------------ viewer
    def view(self):
        agg = Counter()
        conf = Counter()
        clr = Counter()
        for a in self.agents:
            if a.liar:
                continue
            for b, v in a.nb.suspects():
                agg[b] += 1
                conf[b] += v["confirmed"]
            for b in a.nb.cleared():
                clr[b] += 1
        honest = max(1, sum(1 for a in self.agents if not a.liar))
        heat = {b: [0.0, "c"] for b in clr}
        for b, k in agg.items():
            heat[b] = [round(min(1.0, k / (0.2 * honest)), 2), "x" if conf[b] else "u"]
        agents = [{"id": a.id, "block": a.pos, "status": a.action.lower(), "vote": a.vote, "role": "irr"}
                  for a in self.agents]
        return {"agents": agents, "heat": heat, "tick": self.tick, "shares": self.shares[-60:],
                "tally": self.tally.most_common(6), "quorum_need": self.cfg["quorum_frac"] * len(self.agents),
                "range": self.cfg["comm_range"], "series": self.series[-200:],
                "labels": {k: kb.fix_label(v) for k, v in self.labels.items() if k in dict(self.tally.most_common(6))}}

    def detail(self, i):
        a = self.by.get(i)
        if not a:
            return None
        heard = Counter(v for v in a.heard.values() if v)
        return {"role": "irr", "id": a.id, "at": a.pos, "action": a.action, "vote": a.vote,
                "plan": list(a.plan) if a.plan else None,
                "suspects": [a.nb.summary(b, 2) for b, _ in a.nb.suspects()[:3]],
                "cleared": len(a.nb.cleared()), "heard_votes": heard.most_common(4),
                "distrusts": sorted(map(str, a.nb.distrust)), "unshared": len(a.unshared)}

    def liars(self):
        return [a.id for a in self.agents if a.liar]
