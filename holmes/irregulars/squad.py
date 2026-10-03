"""Baker Street mode: scatter and gather, as in the stories.

Holmes stays at 221B and decides. He briefs Wiggins, the Irregulars' leader, with what to look for and where;
Wiggins splits the boys across those assignments and collects their reports at a forward post. The boys go on foot,
make only small local decisions within their assignment (which nearby address to check, whether to tail a suspect,
when to run back), and never accuse anyone. Reports travel physically: a boy runs back to Wiggins (or to Baker
Street when Wiggins is off), and Wiggins carries the batch to Holmes. Holmes reads the reports, lists what is still
open, re-tasks the boys, and names culprit, motive and hideout when he is sure.

Holmes is gpt-6-astra (`holmes = chat`) or exact counting with a rule planner (`holmes = rule`); the boys' local
choices are Jev (`boy_policy = jev`) or a rule. Bribed boys report made-up leads for the addresses they were sent
to; mistaken boys get one report wrong.
"""
import json
import math
import random

from swarmcore.llm import JevClient, LLMClient, LLMError

from .case import TRAITS
from .reasoning import deduce

KEY_KINDS = {"trait", "alibi", "motive", "hide_district", "hide_type", "hide_found", "seen", "trace", "bribe"}
BOY_NAMES = ["Simpson", "Alfie", "Nobby", "Tom", "Billy", "Jem", "Sid", "Mick", "Charlie", "Ned", "Kit", "Dodger",
             "Bert", "Lenny", "Ike", "Pip", "Ollie", "Sam", "Toby", "Fred"]
BOY_INSTRUCTION = (
    "You are one of the Baker Street Irregulars, a street child on an errand for Mr Sherlock Holmes, sent out by "
    "Wiggins. Nobody notices you, so you can look and listen anywhere. You never accuse anyone yourself: you check "
    "places in your assignment, watch the suspect you were told to watch, and run back with anything worth "
    "reporting. Running back costs time, so go when you have something useful or your assignment is done. "
    "Choose your next move."
)
HOLMES_FORMAT = (
    'Reply with one JSON object: {"thinking": "<at most 50 words>", "open_questions": ["<what is still unknown>", '
    '...], "assignments": [{"addresses": ["<address id>", ... at most 4, ideally close together], "watch": "<S id or '
    'null>", "look_for": "<one short sentence for the boys>"}, ...], "accuse": true or false, "culprit": "<S id>", '
    '"motive": "<M id>", "hideout": "<H id>"}. Give at most {n} assignments; Wiggins splits the boys across them. '
    'Do not send boys to addresses already reported unless you want a report re-checked. Set accuse to true only '
    'when the reports clearly establish all three; culprit, motive and hideout are always your current best answer.'
)


def _ticks(case, a, b, cfg):
    metres = case.path_len(a)[b] * 10.0
    return max(1, math.ceil(metres / (cfg["walk_m_per_min"] * cfg["tick_min"])))


class Walker:
    """Anyone who walks the streets: a boy or Wiggins."""

    def __init__(self, at, case):
        self.case = case
        self.at = at            # address while standing, None while walking
        self.leg = None         # (from_addr, to_addr, t0, t1, purpose)

    def go(self, to, purpose, tick, cfg):
        frm = self.at if self.at else self.leg[1]
        self.leg = (frm, to, tick, tick + _ticks(self.case, frm, to, cfg), purpose)
        self.at = None

    def pos(self, tick):
        c = self.case
        if self.at:
            a = c.by_id[self.at]
            return a["x"], a["y"]
        frm, to, t0, t1, _ = self.leg
        f = min(1.0, max(0.0, (tick - t0) / max(1, t1 - t0)))
        a, b = c.by_id[frm], c.by_id[to]
        return a["x"] + (b["x"] - a["x"]) * f, a["y"] + (b["y"] - a["y"]) * f


class Boy(Walker):
    def __init__(self, i, at, case):
        super().__init__(at, case)
        self.i = i
        self.name = BOY_NAMES[i % len(BOY_NAMES)] + ("" if i < len(BOY_NAMES) else f" {i // len(BOY_NAMES) + 1}")
        self.state = "idle"     # idle | out | back
        self.assignment = None
        self.targets = []
        self.checked = []
        self.carrying = []
        self.liar = self.mistaken = False
        self.delivered = 0
        self.guinea = False
        self.tailing = None     # (suspect id, tick due)
        self.last_action, self.last_result = None, "waiting for orders"


class Wiggins(Walker):
    def __init__(self, at, case):
        super().__init__(at, case)
        self.post = at
        self.bag = []           # reports dropped at his post
        self.carrying = []      # reports he is taking to Baker Street
        self.orders = []        # assignments he is taking from Holmes to the boys
        self.state = "post"     # post | to_baker | to_post


class SquadGame:
    def __init__(self, case, cfg):
        self.case, self.cfg = case, cfg
        self.rng = random.Random(f"squad-{cfg['seed']}")
        self.baker = case.specials["baker"]
        n = max(1, cfg["n_irregulars"])
        self.boys = [Boy(i, self.baker, case) for i in range(n)]
        self.irr = self.boys
        order = list(range(n))
        self.rng.shuffle(order)
        for j in order[:round(cfg["liar_frac"] * n)]:
            self.boys[j].liar = True
        for j in order[round(cfg["liar_frac"] * n):round(cfg["liar_frac"] * n) + round(cfg["misinformed_frac"] * n)]:
            self.boys[j].mistaken = True
        self.wiggins = Wiggins(self.baker, case) if cfg["wiggins"] else None
        t = case.truth_ids()
        r = self.rng
        self.frame_up = {"culprit": r.choice([s["id"] for s in case.suspects if s["id"] != t["culprit"]]),
                         "motive": r.choice([m for m in case.brief()["motives"] if m != t["motive"]] or [t["motive"]]),
                         "hideout": r.choice([h["id"] for h in case.hideouts if h["id"] != t["hideout"]])}
        self.notebook = []      # reports Holmes has received
        self.assignments = []   # Holmes's current assignments
        self.open_questions = ["Everything: no reports yet."]
        self.answer = None
        self.assigned = set()   # addresses currently in someone's assignment
        self.reported = set()
        self.tick = 0
        self.minute = 0.0
        self.outcome = None
        self.ended = False
        self.series = []
        self.deliveries = []    # this tick: (x, y) for viewer pulses
        self.new_reports = 0
        self.plan_now = True    # Holmes plans at the start
        self.guineas = []

    # ------------------------------------------------------------------ reports
    def _report(self, boy, addr):
        c = self.case
        lead = c.leads[addr]
        rec = {"address": addr, "text": lead["text"], "fact": list(lead["fact"]), "boy": boy.i,
               "boy_name": boy.name, "seen_tick": self.tick, "fake": False}
        if boy.liar or (boy.mistaken and not any(r["fake"] for r in boy.carrying) and not boy.delivered):
            fact = self._fake_fact(boy.liar)
            saved = c.r
            c.r = random.Random(f"fake-{self.cfg['seed']}-{boy.i}-{addr}")
            try:
                rec.update(text=c._text(fact, c.r.choice(["a cabman", "a barmaid", "a dock porter", "a lamplighter"])),
                           fact=list(fact), fake=True)
            finally:
                c.r = saved
        boy.carrying.append(rec)
        boy.checked.append(addr)
        return rec

    def _fake_fact(self, liar):
        c, r = self.case, self.rng
        if not liar:  # a mistaken boy: one random wrong fact
            return c._lie(r.choice(c.key_facts), c.suspect(c.truth["culprit"])) or ("herring",)
        f = self.frame_up
        kind = r.choice(["trait", "trait", "alibi", "motive", "hide"])
        if kind == "trait":
            d = r.choice(list(TRAITS))
            return ("trait", d, c.suspect(f["culprit"])["traits"][d])
        if kind == "alibi":
            return ("alibi", c.truth["culprit"])
        if kind == "motive":
            return ("motive", c.motives[int(f["motive"][1:]) - 1])
        h = c.hideout(f["hideout"])
        return r.choice([("hide_district", h["district"]), ("hide_type", h["type"])])

    def holmes_facts(self):
        """Reports Holmes counts: one per address (conflicting reports about one address cancel until a third
        report breaks the tie; a boy outvoted that way is no longer believed)."""
        by_addr = {}
        for r in self.notebook:  # a tail is the boy's own observation, not a claim about an address
            key = r["address"] if r["address"] in self.case.by_id else (r["address"], r["boy"], r["seen_tick"])
            by_addr.setdefault(key, []).append(r)
        distrust = set()
        for recs in by_addr.values():
            texts = {}
            for r in recs:
                texts.setdefault(r["text"], set()).add(r["boy"])
            if len(texts) > 1:
                ranked = sorted(texts.items(), key=lambda kv: -len(kv[1]))
                if len(ranked[0][1]) > len(ranked[1][1]):
                    for _, boys in ranked[1:]:
                        distrust |= boys
        out, contested = [], []
        for addr, recs in by_addr.items():
            recs = [r for r in recs if r["boy"] not in distrust]
            if not recs:
                continue
            if len({r["text"] for r in recs}) == 1:
                out.append(recs[0])
            elif isinstance(addr, str):
                contested.append(addr)
        return out, contested, distrust

    # ------------------------------------------------------------------ boys' local choices
    def options(self, boy):
        c = self.case
        out = {}
        here = boy.at
        rest = [a for a in boy.targets if a not in boy.checked]
        near = [nb for nb, _ in sorted(c.nbrs[here], key=lambda nw: nw[1])
                if nb not in boy.checked and nb not in self.reported and nb not in rest][:2]
        for a in rest[:4] + near:
            x = c.by_id[a]
            tag = "in your assignment" if a in rest else "next door, not in your assignment"
            out[f"CHECK_{a}"] = (f"Go to {x['street']}, {x['district']} ({x['type']}), {tag}, "
                                 f"{_ticks(c, here, a, self.cfg) * int(self.cfg['tick_min'])} min on foot")
        watch = (boy.assignment or {}).get("watch")
        for s in c.suspects:
            if s["home"] == here and (watch == s["id"] or not watch):
                out[f"TAIL_{s['id']}"] = f"Follow {s['name']}, who lives here, for about an hour"
        dest = self.report_point()
        out["RUN_BACK"] = (f"Run back to {'Wiggins' if self.wiggins else 'Baker Street'} with what you have "
                           f"({len(boy.carrying)} report{'s' if len(boy.carrying) != 1 else ''}), "
                           f"{_ticks(c, here, dest, self.cfg) * int(self.cfg['tick_min'])} min")
        return out

    def observation(self, boy):
        c = self.case
        asg = boy.assignment or {}
        w = asg.get("watch")
        pay = ("You are paid a shilling a day, and Mr Holmes gives a guinea to whoever brings the lead that cracks "
               "the case." if self.cfg["pay"] == "shilling_guinea" else "Nobody is paying you for this.")
        return {
            "you": {"name": boy.name, "at": c.label(boy.at), "ticks_left": self.cfg["swarm_ticks"] - self.tick,
                    "minutes_per_tick": self.cfg["tick_min"], "pay": pay},
            "assignment": {"look_for": asg.get("look_for", ""), "district": asg.get("district"),
                           "watch": (f"{w}: {c.brief()['suspects'].get(w, '')}" if w else None),
                           "addresses_left": [c.label(a) for a in boy.targets if a not in boy.checked]},
            "found_on_this_errand": [r["text"] for r in boy.carrying],
            "victim": c.brief()["victim"],
        }

    def boy_rule(self, boy, opts):
        c = self.case
        key = any(r["fact"][0] in KEY_KINDS for r in boy.carrying)
        if self.cfg["pay"] == "shilling_guinea" and key and "RUN_BACK" in opts:
            return "RUN_BACK"  # a guinea for the key lead: hurry back with it
        watch = (boy.assignment or {}).get("watch")
        if watch and f"TAIL_{watch}" in opts:
            return f"TAIL_{watch}"
        rest = [k for k in opts if k.startswith("CHECK_") and k[6:] in boy.targets]
        if rest:
            return min(rest, key=lambda k: c.path_len(boy.at)[k[6:]])
        return "RUN_BACK"

    def boy_random(self, boy, opts):
        """Random local choice (a baseline for the boys' policy)."""
        r = random.Random(f"boy-{self.cfg['seed']}-{boy.i}-{self.tick}")
        return r.choice(sorted(opts))

    def max_checks(self):
        return 99 if self.cfg["pay"] == "shilling_guinea" else 2  # unpaid boys give up after two calls

    # ------------------------------------------------------------------ the tick
    def report_point(self):
        return self.wiggins.post if self.wiggins else self.baker

    def begin_tick(self):
        """Move everyone; return boys who have arrived somewhere and must choose their next step."""
        c, cfg = self.case, self.cfg
        self.deliveries = []
        due = []
        for b in self.boys:
            if b.tailing and b.tailing[1] <= self.tick:
                self._finish_tail(b)
                due.append(b)
                continue
            if b.leg and b.leg[3] <= self.tick:
                frm, to, t0, t1, purpose = b.leg
                b.at, b.leg = to, None
                if purpose == "check":
                    rec = self._report(b, to)
                    b.last_result = f"checked {c.label(to)}: {rec['text'][:80]}"
                    if len(b.checked) >= self.max_checks():
                        self._send_back(b)
                        continue
                    due.append(b)
                elif purpose == "report":
                    self._deliver(b)
        w = self.wiggins
        if w and w.leg and w.leg[3] <= self.tick:
            frm, to, t0, t1, purpose = w.leg
            w.at, w.leg = to, None
            if purpose == "to_baker":
                self._add_to_notebook(w.carrying, "Wiggins")
                w.carrying = []
                w.state = "baker"
                self.plan_now = True
            else:
                w.state = "post"
                self._hand_out(w.orders)
                w.orders = []
        if w and w.state == "post" and w.bag:
            out = sum(1 for b in self.boys if b.state == "out")
            oldest = min(r["delivered_tick"] for r in w.bag)
            if len(w.bag) >= 3 or self.tick - oldest >= 2 or out == 0:
                if w.post == self.baker:
                    self._add_to_notebook(w.bag, "Wiggins")
                    w.bag = []
                    self.plan_now = True
                else:  # Wiggins runs the batch to Baker Street
                    w.carrying, w.bag = w.bag, []
                    w.go(self.baker, "to_baker", self.tick, cfg)
                    w.state = "to_baker"
        if not w and any(b.state == "idle" for b in self.boys) and \
                (self.new_reports >= cfg["hq_min_new"] or not any(b.state != "idle" for b in self.boys)):
            self.plan_now = True
        return due

    def _send_back(self, b):
        b.state = "back"
        dest = self.report_point()
        if b.at == dest:
            self._deliver(b)
        else:
            b.go(dest, "report", self.tick, self.cfg)

    def _deliver(self, b):
        for r in b.carrying:
            r["delivered_tick"] = self.tick
        x, y = b.pos(self.tick)
        self.deliveries.append((x, y))
        b.delivered += len(b.carrying)
        if self.wiggins:
            self.wiggins.bag.extend(b.carrying)
        else:
            self._add_to_notebook(b.carrying, b.name)
        b.carrying = []
        b.state = "idle"
        b.assignment, b.targets, b.checked = None, [], []
        b.last_result = "reported and is waiting for orders"
        if self.wiggins and self.wiggins.state == "post" and self.wiggins.orders:
            self._hand_out(self.wiggins.orders)

    def _add_to_notebook(self, recs, via):
        truth = {tuple(f) for f in self.case.key_facts}
        for r in recs:
            r["reached_holmes_tick"] = self.tick
            self.notebook.append(r)
            if r["address"] in self.case.by_id:
                self.reported.add(r["address"])
                self.assigned.discard(r["address"])
            if not r["fake"] and tuple(r["fact"]) in truth and not any(g[1] == tuple(r["fact"]) for g in self.guineas):
                self.guineas.append((r["boy"], tuple(r["fact"])))
        self.new_reports += len(recs)

    def _finish_tail(self, b):
        c = self.case
        sid = b.tailing[0]
        b.tailing = None
        s = c.suspect(sid)
        if b.liar:
            fact = self._fake_fact(True)
            text = f"I followed {s['name']} all evening. " + c._text(fact, "a lamplighter")
        elif sid == c.truth["culprit"]:
            if self.rng.random() < self.cfg["tail_success"]:
                d = c.hideout(c.truth["hideout"])["district"]
                fact, text = ("hide_district", d), f"I followed {s['name']}, who kept looking back and slipped off toward {d}."
            else:
                fact, text = ("bland",), f"I lost {s['name']} in the fog."
        else:
            fact = ("alibi", sid)
            text = f"I followed {s['name']}; a dozen people vouch for where {s['name']} was that night."
        b.carrying.append({"address": f"tail:{sid}", "text": text, "fact": list(fact), "boy": b.i,
                           "boy_name": b.name, "seen_tick": self.tick, "fake": b.liar})
        b.last_result = text

    def apply(self, b, action):
        c, cfg = self.case, self.cfg
        b.last_action = action
        if action.startswith("CHECK_"):
            b.go(action[6:], "check", self.tick, cfg)
            b.last_result = f"walking to {c.label(action[6:])}"
        elif action.startswith("TAIL_"):
            b.tailing = (action[5:], self.tick + max(1, round(60 / cfg["tick_min"])))
            b.last_result = f"tailing {action[5:]}"
        else:
            self._send_back(b)
            b.last_result = f"running back with {len(b.carrying)} reports" if b.state == "back" else b.last_result

    # ------------------------------------------------------------------ orders
    def plan_due(self, calls_used):
        return self.plan_now and calls_used < self.cfg["hq_max_calls"]

    def apply_plan(self, plan):
        self.plan_now = False
        self.new_reports = 0
        self.answer = {k: plan.get(k) for k in ("culprit", "motive", "hideout", "accuse", "note")}
        self.open_questions = plan.get("open_questions") or self.open_questions
        asg = []
        for k, a in enumerate(plan.get("assignments") or []):
            addrs = [x for x in a.get("addresses") or [] if x in self.case.by_id][:self.cfg["errand_max"]]
            if not addrs:
                continue
            dist = self.case.by_id[addrs[0]]["district"]
            asg.append({"id": len(self.assignments) + k + 1, "addresses": addrs, "watch": a.get("watch"),
                        "look_for": str(a.get("look_for") or "")[:160], "district": dist, "boys": []})
        self.assignments = asg
        for a in asg:
            self.assigned.update(a["addresses"])
        w = self.wiggins
        first = not self.notebook and w is not None and w.post == self.baker and w.at == self.baker
        if not w:
            self._hand_out(asg)
            return
        if w.at != self.baker:
            return
        idle_here = [b for b in self.boys if b.state == "idle" and b.at == self.baker]
        if idle_here:  # boys at Baker Street get their orders on the spot
            self._hand_out(asg, boys=idle_here)
        if first:
            # Wiggins sets up a forward post near the first assignments; the boys report to him there
            pts = [self.case.by_id[x] for a in asg for x in a["addresses"]]
            if pts:
                cx, cy = sum(p["x"] for p in pts) / len(pts), sum(p["y"] for p in pts) / len(pts)
                w.post = min(self.case.by_id, key=lambda i: (self.case.by_id[i]["x"] - cx) ** 2 +
                             (self.case.by_id[i]["y"] - cy) ** 2)
        w.orders = asg
        if w.post == self.baker:
            w.state = "post"
            self._hand_out(asg)
            w.orders = []
        else:
            w.go(w.post, "to_post", self.tick, self.cfg)
            w.state = "to_post"

    def _hand_out(self, asg, boys=None):
        """Wiggins splits the idle boys across the assignments (one boy per assignment without Wiggins)."""
        if not asg:
            return
        here = self.wiggins.post if self.wiggins and boys is None else None
        idle = boys if boys is not None else [b for b in self.boys if b.state == "idle" and
                                              (here is None or b.at == here or not self.wiggins)]
        if not idle:
            return
        if not self.wiggins:
            pairs = list(zip(idle, asg))
            groups = {a["id"]: [b] for b, a in pairs}
        else:
            groups = {a["id"]: [] for a in asg}
            for k, b in enumerate(idle):
                groups[asg[k % len(asg)]["id"]].append(b)
        for a in asg:
            team = groups.get(a["id"]) or []
            for j, b in enumerate(team):
                share = a["addresses"][j::len(team)] or a["addresses"][:1]
                b.assignment, b.targets, b.checked = a, share, []
                b.state = "out"
                a["boys"].append(b.i)
                first = min(share, key=lambda x: self.case.path_len(b.at)[x])
                b.go(first, "check", self.tick, self.cfg)
                b.last_action = f"CHECK_{first}"
                b.last_result = f"sent to {self.case.label(first)}"

    # ------------------------------------------------------------------ ending
    def end_tick(self):
        self.tick += 1
        self.minute = self.tick * self.cfg["tick_min"]
        out = sum(1 for b in self.boys if b.state != "idle")
        self.series.append({"tick": self.tick, "reports": len(self.notebook), "out": out, "top": 0, "truth": 0,
                            "firm": 0, "frame": 0})

    def finish(self, plan, forced):
        t = self.case.truth_ids()
        acc = {k: plan.get(k) for k in ("culprit", "motive", "hideout")}
        ok = {k: acc[k] == t[k] for k in acc}
        self.outcome = {**acc, "ok": ok, "parts": sum(ok.values()), "solved": all(ok.values()),
                        "quorum": not forced, "forced": forced, "closed_by": "holmes" if not forced else "deadline",
                        "tick": self.tick, "minute": self.minute, "plurality_parts": sum(ok.values()), "votes": 0,
                        "need": 0, "reports": len(self.notebook), "guineas": [g[0] for g in self.guineas]}
        self.ended = True

    def coverage(self):
        keys = {ad for ad, l in self.case.leads.items() if l["fact"][0] in KEY_KINDS and not l["lie"]}
        return {"addresses": len(self.reported), "key_leads_found": len(keys & self.reported), "key_leads": len(keys)}

    def idle_count(self):
        return sum(1 for b in self.boys if b.state == "idle")


# ---------------------------------------------------------------------- Holmes
class RuleHolmes:
    """Exact counting over the reports, plus a rule planner: pointers first, re-check contested addresses, then
    where each open question's evidence should be."""
    name = "rule"

    def __init__(self, cfg):
        self.cfg = cfg

    def plan(self, g, final=False):
        c = g.case
        facts, contested, distrust = g.holmes_facts()
        b = deduce([r["fact"] for r in facts], c)
        ans = {k: v["best"] for k, v in b.items()}
        sure = all(v["confident"] for v in b.values())
        open_q = []
        if not b["culprit"]["confident"]:
            top = max(b["culprit"]["scores"].values())
            left = [s for s, v in b["culprit"]["scores"].items() if v >= top - 0.5]
            open_q.append(f"Culprit: {', '.join(left)} still possible; need alibis or more sightings")
        if not b["motive"]["confident"]:
            open_q.append("Motive: not yet corroborated by two reports")
        if not b["hideout"]["confident"]:
            open_q.append("Hideout: district and type not yet established")
        if contested:
            open_q.append(f"Conflicting reports about {', '.join(contested[:4])}: re-check")
        plan = {**ans, "accuse": sure, "open_questions": open_q or ["None: the reports agree."], "assignments": [],
                "note": f"boys not believed: {sorted(distrust)}" if distrust else ""}
        if sure or final:
            return plan, {}
        want = {}
        for a in contested:
            want[a] = 6
        for r in g.notebook:
            if r["fact"][0] == "pointer" and r["fact"][1] not in g.reported:
                want[r["fact"][1]] = want.get(r["fact"][1], 0) + 5
        if not b["culprit"]["confident"]:
            for a in c.nearest(c.scene, 18) + [c.scene]:
                want[a] = want.get(a, 0) + 2
            top = max(b["culprit"]["scores"].values())
            for s in c.suspects:
                if b["culprit"]["scores"][s["id"]] >= top - 0.5:
                    want[s["home"]] = want.get(s["home"], 0) + 3
        if not b["motive"]["confident"]:
            for a in c.nearest(c.victim["home"], 22):
                want[a] = want.get(a, 0) + 1.5
        if not b["hideout"]["confident"]:
            for h in c.hideouts:
                want[h["address"]] = want.get(h["address"], 0) + (2.5 if b["hideout"]["scores"][h["id"]] >=
                                                                  max(b["hideout"]["scores"].values()) - 0.5 else 0.5)
        free = {a: w for a, w in want.items() if (a not in g.reported or a in contested) and a not in g.assigned}
        n = max(1, g.idle_count()) if not g.wiggins else min(6, max(1, g.idle_count()))
        asg, used = [], set()
        for a in sorted(free, key=lambda x: (-free[x], x)):
            if len(asg) >= n:
                break
            if a in used:
                continue
            group = [a] + [x for x in sorted(free, key=lambda x: c.path_len(a)[x])
                           if x not in used and x != a and c.path_len(a)[x] <= 120 and free[x] >= 1][:self.cfg["errand_max"] - 1]
            used.update(group)
            watch = next((s["id"] for s in c.suspects if s["home"] in group and not b["culprit"]["confident"]), None)
            asg.append({"addresses": group, "watch": watch, "look_for": open_q[0] if open_q else "anything odd"})
        if len(asg) < n:  # nothing targeted left: explore unreported addresses near where the open question points
            centre = (c.victim["home"] if not b["motive"]["confident"] else
                      c.hideout(b["hideout"]["best"])["address"] if not b["hideout"]["confident"] else c.scene)
            rest = [x for x in c.nearest(centre, len(c.by_id)) if x not in g.reported and x not in g.assigned
                    and x not in used]
            while rest and len(asg) < n:
                a = rest.pop(0)
                group = [a] + [x for x in rest if c.path_len(a)[x] <= 120][:self.cfg["errand_max"] - 1]
                rest = [x for x in rest if x not in group]
                used.update(group)
                asg.append({"addresses": group, "watch": None, "look_for": open_q[0] if open_q else "anything odd"})
        plan["assignments"] = asg
        return plan, {}


class ChatHolmes:
    """gpt-6-astra as Holmes. The brief and address directory go first so they are cached between calls."""
    name = "chat"

    def __init__(self, cfg):
        self.cfg = cfg
        self.client = LLMClient("openai", cfg["chat_model"], cfg["chat_key"], timeout=120, temperature=1.0)

    def static(self, g, n):
        c = g.case
        directory = [f"{a['id']}: {a['street']}, {a['district']} ({a['type']}), "
                     f"{_ticks(c, g.baker, a['id'], self.cfg) * int(self.cfg['tick_min'])} min on foot from 221B"
                     for a in c.addresses]
        return ("You are Sherlock Holmes at 221B Baker Street, directing the Baker Street Irregulars through "
                "Wiggins. You do not leave Baker Street. Boys go out on foot, check the addresses you assign, "
                "watch suspects you name, and run back to report in person, so reports arrive with a delay. Some "
                "witnesses lie, and a boy may be bribed or mistaken; true facts usually turn up at more than one "
                "address, and you can send another boy to re-check a report. "
                + HOLMES_FORMAT.replace("{n}", str(n)) + "\n\nCASE BRIEF\n" + json.dumps(c.brief(), indent=0) +
                "\n\nADDRESS DIRECTORY\n" + "\n".join(directory))

    def plan(self, g, final=False):
        c = g.case
        n = g.idle_count() if not g.wiggins else min(6, max(1, g.idle_count()))
        reports = [{"lead": r["text"], "address": (f"{r['address']} {c.label(r['address'])}" if r["address"] in c.by_id
                                                    else "while tailing a suspect"),
                    "boy": r["boy_name"], "reached_you_at_tick": r.get("reached_holmes_tick")} for r in g.notebook]
        state = {"tick": g.tick, "ticks_left": self.cfg["swarm_ticks"] - g.tick, "minutes_per_tick": self.cfg["tick_min"],
                 "boys_free": g.idle_count(), "boys_out": sum(1 for b in g.boys if b.state != "idle"),
                 "addresses_already_reported": sorted(g.reported), "addresses_being_checked": sorted(g.assigned),
                 "your_previous_open_questions": g.open_questions, "reports": reports}
        if final:
            state["note"] = "Time is up: give your final culprit, motive and hideout now (accuse true, no assignments)."
        out = self.client.chat(self.static(g, max(1, n)), json.dumps(state, separators=(",", ":")), json_mode=True,
                               max_tokens=1800, retries=1)
        u = self.client.last_usage or {}
        tin = int(u.get("prompt_tokens") or 0)
        cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        tout = int(u.get("completion_tokens") or 0)
        cost = ((tin - cached) * self.cfg["chat_price_in"] + cached * self.cfg["chat_price_cached"] +
                tout * self.cfg["chat_price_out"]) / 1e6
        valid = {"culprit": [s["id"] for s in c.suspects], "motive": list(c.brief()["motives"]),
                 "hideout": [h["id"] for h in c.hideouts]}
        plan = {}
        for k, ks in valid.items():
            v = str(out.get(k) or "").strip().upper()
            plan[k] = v if v in ks else (g.answer or {}).get(k) or ks[0]
        plan["accuse"] = bool(out.get("accuse"))
        plan["open_questions"] = [str(q)[:140] for q in (out.get("open_questions") or [])][:6]
        plan["note"] = str(out.get("thinking") or "")[:300]
        asg = []
        for a in (out.get("assignments") or [])[:max(1, n)]:
            if not isinstance(a, dict):
                continue
            addrs = [str(x).strip().upper() for x in (a.get("addresses") or [])]
            addrs = [x for x in addrs if x in c.by_id]
            w = str(a.get("watch") or "").strip().upper()
            asg.append({"addresses": addrs, "watch": w if w in valid["culprit"] else None,
                        "look_for": str(a.get("look_for") or "")})
        plan["assignments"] = [] if final else asg
        return plan, {"model": self.client.model, "in": tin, "cached": cached, "out": tout, "cost": cost}


class JevBoy:
    """A boy's small local choice with Jev: one call each time he arrives somewhere."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.client = JevClient(cfg["jev_provider"], cfg["jev_model"], cfg["jev_key"], timeout=cfg["request_timeout_s"])

    def decide(self, g, b, opts):
        q = {"action": {"type": "choice", "instructions": BOY_INSTRUCTION, "criteria": opts}}
        answers, meta = self.client.ask(json.dumps(g.observation(b), separators=(",", ":")), q, retries=0)
        a = answers.get("action") or {}
        probs = {x: float(p or 0) for x, p in (a.get("probabilities") or {}).items() if x in opts}
        if not probs and a.get("choice") in opts:
            probs = {a["choice"]: 1.0}
        if not probs:
            raise LLMError("no usable answer for the boy's action")
        u = meta.get("usage") or {}
        return max(probs, key=lambda x: (probs[x], x)), {"model": meta.get("model"), "in": int(u.get("input_tokens") or 0),
                                                          "out": int(u.get("output_tokens") or 0),
                                                          "cost": float(u.get("cost") or 0)}


def make_holmes(cfg):
    return ChatHolmes(cfg) if cfg["holmes"] == "chat" else RuleHolmes(cfg)
