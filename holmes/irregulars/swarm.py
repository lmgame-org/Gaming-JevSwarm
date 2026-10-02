"""Swarm mode: Wiggins's Irregulars spread over the map and solve the case together.

Each Irregular knows only the lead at addresses it has stood on, what it heard from Irregulars within shouting
range, and the public brief. Every tick each one makes one decision (move to a neighbouring address, share a lead,
tail a suspect, or wait) and states its current vote. The case closes when a quorum votes the identical full answer
(culprit, motive, hideout) before the clock runs out.

Liars (Moriarty's paid boys) all push the same wrong answer with made-up leads; misinformed Irregulars start with
one false lead; stubborn ones never change their first firm vote; noisy memory forgets leads at random.
"""
import json
import random

from swarmcore.llm import JevClient, LLMError

from .case import TRAITS
from .reasoning import deduce

KEY_KINDS = {"trait", "alibi", "motive", "hide_district", "hide_type", "hide_found", "hide_not", "pointer"}
SHARE_ORDER = ["hide_found", "motive", "trait", "alibi", "hide_district", "hide_type", "hide_not"]
INSTRUCTION = (
    "You are one of Wiggins's Baker Street Irregulars, a street child helping Sherlock Holmes with a murder case. "
    "You know only the leads you saw yourself and those other Irregulars shouted to you; some witnesses and some "
    "Irregulars lie, so trust facts that come from more than one place. The case is solved when enough Irregulars "
    "vote the same culprit, motive and hideout before the clock runs out. Choose your next action."
)
Q_VOTE = ("Your current vote for the {what}. Answer UNSURE unless your leads support one answer; the case closes "
          "only when many Irregulars vote the same full answer.")


class Irregular:
    def __init__(self, i, at, rng):
        self.i, self.at = i, at
        self.known = []          # dicts: address, text, fact, via, fake
        self.inbox = []
        self.visited = {at}
        self.shared = set()
        self.vote = {"culprit": None, "motive": None, "hideout": None}
        self.liar = self.misinformed = self.stubborn = False
        self.locked = False
        self.tailing = None      # (suspect id, tick due)
        self.heard = {}          # part -> {answer: count} of votes heard nearby this tick
        self.last_action, self.last_result = None, "arrived"
        self.rng = rng
        self.own = {}            # address -> lead text I saw there myself (incl. empty ones)
        self.distrust = set()    # Irregulars I caught lying (or was told about by one I trust)
        self.refute = []         # (address, liar) I should set straight

    def remember(self, rec, cap, defend=False):
        key = (rec["address"], rec["text"])
        if any((k["address"], k["text"]) == key for k in self.known):
            return False
        if defend and rec["via"] != "seen":
            if rec.get("implausible"):  # claims to have stood somewhere it could not have walked from yet
                self.catch(rec["via"])
                return False
            if rec.get("refutes") is not None and rec["via"] not in self.distrust:
                self.catch(rec["refutes"])  # a trusted Irregular says this one lied
            if rec["via"] in self.distrust:
                return False
            mine = self.own.get(rec["address"])
            if mine is not None and mine != rec["text"]:
                self.catch(rec["via"])
                self.refute.append((rec["address"], rec["via"]))
                return False
        self.known.append(rec)
        del self.known[:-cap]
        return True

    def catch(self, liar):
        if liar == self.i or liar == "seen":
            return
        self.distrust.add(liar)
        self.known = [k for k in self.known if k["via"] != liar]

    def effective(self, defend):
        """Leads that count: with the defence, distrusted sources are gone and an address with conflicting
        second-hand claims counts for nothing (each witness address counts once)."""
        if not defend:
            return list(self.known)
        by_addr = {}
        for k in self.known:
            by_addr.setdefault(k["address"], []).append(k)
        out = []
        for recs in by_addr.values():
            first = [r for r in recs if r["via"] == "seen"]
            if first:
                out.append(first[0])
            elif len({r["text"] for r in recs}) == 1:
                out.append(recs[0])
        return out

    def contested(self, rec):
        return rec["via"] != "seen" and any(k["address"] == rec["address"] and k["text"] != rec["text"]
                                            for k in self.known)

    def full_vote(self):
        v = self.vote
        return (v["culprit"], v["motive"], v["hideout"]) if all(v.values()) else None


class SwarmGame:
    def __init__(self, case, cfg):
        self.case, self.cfg = case, cfg
        self.defend = cfg.get("corroboration", "address") == "address"
        self.rng = random.Random(f"swarm-{cfg['seed']}")
        r = self.rng
        n = max(3, cfg["n_irregulars"])
        ids = sorted(case.by_id)
        starts = r.sample(ids, n) if n <= len(ids) else [r.choice(ids) for _ in range(n)]
        self.irr = [Irregular(i, a, random.Random(f"irr-{cfg['seed']}-{i}")) for i, a in enumerate(starts)]
        order = list(range(n))
        r.shuffle(order)
        k_l = round(cfg["liar_frac"] * n)
        k_m = round(cfg["misinformed_frac"] * n)
        k_s = round(cfg["stubborn_frac"] * n)
        for j in order[:k_l]:
            self.irr[j].liar = True
        for j in order[k_l:k_l + k_m]:
            self.irr[j].misinformed = True
        for j in order[k_l + k_m:k_l + k_m + k_s]:
            self.irr[j].stubborn = True
        t = case.truth_ids()
        # Moriarty's line: one wrong answer every liar pushes
        self.frame_up = {"culprit": r.choice([s["id"] for s in case.suspects if s["id"] != t["culprit"]]),
                         "motive": r.choice([m for m in case.brief()["motives"] if m != t["motive"]] or [t["motive"]]),
                         "hideout": r.choice([h["id"] for h in case.hideouts if h["id"] != t["hideout"]])}
        for a in self.irr:
            self._read(a, a.at)
            if a.misinformed:
                a.remember(self._fake(a.rng, None), cfg["memory_cap"])
            if a.liar:
                a.vote = dict(self.frame_up)
                a.repertoire = [self._fake(a.rng, self.frame_up) for _ in range(2)]
        self.tick = 0
        self.minute = 0.0
        self.outcome = None
        self.ended = False
        self.shares = []          # this tick: (sender, x, y)
        self.series = []
        self.events = []

    # ------------------------------------------------------------------ helpers
    def _read(self, a, addr):
        lead = self.case.leads[addr]
        a.visited.add(addr)
        a.own[addr] = lead["text"]
        if self.defend:  # anyone who told me something else about this address was lying
            for k in list(a.known):
                if k["address"] == addr and k["via"] != "seen" and k["text"] != lead["text"]:
                    a.catch(k["via"])
                    a.refute.append((addr, k["via"]))
        if lead["fact"][0] == "bland":
            return False  # "nobody saw anything" is not worth a memory slot
        return a.remember({"address": addr, "text": lead["text"], "fact": lead["fact"], "via": "seen", "fake": False},
                          self.cfg["memory_cap"])

    def _fake(self, rng, target):
        """A made-up lead. Liars' fakes support Moriarty's frame-up; misinformed Irregulars hold a random lie."""
        c = self.case
        f_up = self.frame_up
        if target is None:
            f = rng.choice(c.key_facts)
            fact = c._lie(f, c.suspect(c.truth["culprit"])) or ("herring",)
        else:
            kind = rng.choice(["trait", "trait", "alibi", "motive", "hide"])
            fs = c.suspect(f_up["culprit"])
            if kind == "trait":
                d = rng.choice(list(TRAITS))
                fact = ("trait", d, fs["traits"][d])
            elif kind == "alibi":
                fact = ("alibi", c.truth["culprit"])
            elif kind == "motive":
                fact = ("motive", c.motives[int(f_up["motive"][1:]) - 1])
            else:
                h = c.hideout(f_up["hideout"])
                fact = rng.choice([("hide_district", h["district"]), ("hide_type", h["type"])])
        saved = c.r
        c.r = rng
        try:
            text = c._text(fact, rng.choice(["a cabman", "a barmaid", "a dock porter", "a lamplighter"]))
        finally:
            c.r = saved
        addr = rng.choice(sorted(c.by_id))
        return {"address": addr, "text": text, "fact": list(fact), "via": "seen", "fake": True}

    def pos(self, a):
        x = self.case.by_id[a.at]
        return x["x"], x["y"]

    def within(self, a, rng_units):
        ax, ay = self.pos(a)
        out = []
        for b in self.irr:
            if b is a:
                continue
            bx, by = self.pos(b)
            if (ax - bx) ** 2 + (ay - by) ** 2 <= rng_units ** 2:
                out.append(b)
        return out

    def neighbours(self, a):
        return sorted(self.case.nbrs[a.at], key=lambda nw: nw[1])[:5]

    # ------------------------------------------------------------------ what an Irregular sees
    def candidates(self, a):
        c = self.case
        out = {"WAIT": "Stay here and listen"}
        for nb, w in self.neighbours(a):
            x = c.by_id[nb]
            seen = " (you have been there)" if nb in a.visited else ""
            out[f"MOVE_{nb}"] = f"Walk to {x['street']}, {x['district']} ({x['type']}){seen}"
        for k, rec in enumerate(a.known):
            if (rec["address"], rec["text"]) in a.shared:
                continue
            out[f"SHARE_{k}"] = f"Shout lead #{k} to every Irregular within earshot: \"{rec['text'][:90]}\""
        for addr, liar in a.refute[-3:]:
            if liar in a.distrust:
                out[f"REFUTE_{addr}"] = (f"Shout what you really saw at {c.label(addr)}: Irregular {liar}'s story "
                                         f"about it is false and Irregular {liar} should not be trusted")
        for s in c.suspects:
            if s["home"] == a.at:
                out[f"TAIL_{s['id']}"] = f"Tail {s['name']}, who lives here, for the next hour"
        return out

    def observation(self, a):
        c = self.case
        x = c.by_id[a.at]
        b = c.brief()
        return {
            "brief": {"victim": b["victim"], "suspects": b["suspects"], "motives": b["motives"],
                      "possible_hideouts": b["possible_hideouts"]},
            "you": {"irregular": a.i, "at": f"{a.at} {x['street']}, {x['district']}", "tick": self.tick,
                    "ticks_left": self.cfg["swarm_ticks"] - self.tick,
                    "irregulars_within_earshot": len(self.within(a, self.cfg["comm_range"])),
                    "last_action": a.last_action, "last_result": a.last_result,
                    "my_vote": {k: v or "UNSURE" for k, v in a.vote.items()},
                    "votes_heard_nearby": a.heard},
            "my_leads": [{"#": k, "lead": r["text"],
                          "source": ("found it out myself" if r["address"] not in c.by_id and r["via"] == "seen"
                                     else f"saw it myself at {c.label(r['address'])}" if r["via"] == "seen"
                                     else f"heard from Irregular {r['via']}, who says it was at {c.label(r['address'])}"
                                     if r["address"] in c.by_id else f"heard from Irregular {r['via']}"),
                          **({"contested": "another Irregular told you something different about the same address"}
                             if self.defend and a.contested(r) else {})}
                         for k, r in enumerate(a.known)],
            **({"irregulars_caught_lying": sorted(a.distrust)} if self.defend else {}),
        }

    def vote_questions(self):
        c = self.case
        b = c.brief()
        unsure = {"UNSURE": "Not enough evidence yet"}
        return {"culprit": {"type": "choice", "instructions": Q_VOTE.format(what="culprit"),
                            "criteria": {**{s["id"]: s["name"] for s in c.suspects}, **unsure}},
                "motive": {"type": "choice", "instructions": Q_VOTE.format(what="motive"),
                           "criteria": {**b["motives"], **unsure}},
                "hideout": {"type": "choice", "instructions": Q_VOTE.format(what="hideout"),
                            "criteria": {**{h["id"]: f"{c.label(h['address'])}, a {h['type']}" for h in c.hideouts},
                                         **unsure}}}

    # ------------------------------------------------------------------ reflex rule and random
    def reflex(self, a, cands):
        c = self.case
        b = deduce([r["fact"] for r in a.effective(self.defend)], c, need=2)
        vote = {}
        for k in b:  # own evidence first; otherwise go with a clear local majority of heard votes
            h = a.heard.get(k) or {}
            top = max(h, key=lambda x: (h[x], x)) if h else None
            if b[k]["confident"]:
                vote[k] = b[k]["best"]
            elif top and h[top] * 2 > sum(h.values()) and (
                    (h[top] >= 2 and b[k]["n"] > 0 and b[k]["scores"][top] >= max(b[k]["scores"].values()))
                    or (h[top] >= 3 and b[k]["n"] == 0)):
                vote[k] = top  # a clear local majority that my own leads allow (or I have none on this question)
            else:
                vote[k] = None
        near = len(self.within(a, self.cfg["comm_range"]))
        if near:
            for k in cands:
                if k.startswith("REFUTE_"):
                    return k, vote
            for kind in SHARE_ORDER:
                for k in range(len(a.known) - 1, -1, -1):
                    if f"SHARE_{k}" in cands and a.known[k]["fact"][0] == kind:
                        return f"SHARE_{k}", vote
        if not b["culprit"]["confident"]:
            for s in c.suspects:
                if f"TAIL_{s['id']}" in cands and b["culprit"]["scores"][s["id"]] >= \
                        max(b["culprit"]["scores"].values()) - 0.5:
                    return f"TAIL_{s['id']}", vote
        moves = [k for k in cands if k.startswith("MOVE_")]
        pointed = {r["fact"][1] for r in a.known if r["fact"][0] == "pointer"}
        for m in moves:
            if m[5:] in pointed and m[5:] not in a.visited:
                return m, vote
        fresh = [m for m in moves if m[5:] not in a.visited]
        if fresh:
            return a.rng.choice(fresh), vote
        return (a.rng.choice(moves) if moves else "WAIT"), vote

    def randomly(self, a, cands):
        r = a.rng
        c = self.case
        vote = {"culprit": r.choice([None] + [s["id"] for s in c.suspects]),
                "motive": r.choice([None] + list(c.brief()["motives"])),
                "hideout": r.choice([None] + [h["id"] for h in c.hideouts])}
        return r.choice(sorted(cands)), vote

    def forced(self, a, cands):
        """Liars bypass the policy: shout a made-up lead when anyone can hear, otherwise wander."""
        if not a.liar:
            return None
        if self.within(a, self.cfg["comm_range"]):
            return "LIE"
        moves = [k for k in cands if k.startswith("MOVE_")]
        return a.rng.choice(moves) if moves else "WAIT"

    # ------------------------------------------------------------------ one tick
    def begin_tick(self):
        """Deliver last tick's shouts, apply forgetting and finish tails. Returns Irregulars due to decide."""
        cfg, r = self.cfg, self.rng
        for a in self.irr:
            if a.inbox:
                r.shuffle(a.inbox)
                got = 0
                for rec in a.inbox:
                    if got >= cfg["bandwidth"]:
                        break
                    if a.remember(rec, cfg["memory_cap"], self.defend):
                        got += 1
                a.inbox = []
            if cfg["forget_rate"] > 0 and a.known and a.rng.random() < cfg["forget_rate"]:
                a.known.pop(a.rng.randrange(len(a.known)))
            if a.tailing and a.tailing[1] <= self.tick:
                self._finish_tail(a)
        self.shares = []
        for a in self.irr:  # votes are shouted too: each Irregular hears the votes of the nearest few in range
            near = sorted((b for b in self.within(a, cfg["comm_range"]) if not (self.defend and b.i in a.distrust)),
                          key=lambda b: self._d2(a, b))[:8]
            a.heard = {k: {} for k in ("culprit", "motive", "hideout")}
            for b in near:
                for k, v in b.vote.items():
                    if v:
                        a.heard[k][v] = a.heard[k].get(v, 0) + 1
        return [a for a in self.irr if not a.tailing]

    def _d2(self, a, b):
        (ax, ay), (bx, by) = self.pos(a), self.pos(b)
        return (ax - bx) ** 2 + (ay - by) ** 2

    def _finish_tail(self, a):
        c = self.case
        sid = a.tailing[0]
        a.tailing = None
        s = c.suspect(sid)
        if sid == c.truth["culprit"]:
            if a.rng.random() < self.cfg["tail_success"]:
                d = c.hideout(c.truth["hideout"])["district"]
                rec = {"address": f"tail:{sid}", "fact": ["hide_district", d], "via": "seen", "fake": False,
                       "text": f"You tailed {s['name']}, who kept looking back and slipped away toward {d}."}
            else:
                rec = {"address": f"tail:{sid}", "fact": ["bland"], "via": "seen", "fake": False,
                       "text": f"You lost {s['name']} in the fog."}
        else:
            rec = {"address": f"tail:{sid}", "fact": ["alibi", sid], "via": "seen", "fake": False,
                   "text": f"You tailed {s['name']}; a dozen people vouch for where {s['name']} was that night."}
        a.remember(rec, self.cfg["memory_cap"], self.defend)
        a.last_result = rec["text"]

    def apply(self, a, action, vote):
        c, cfg = self.case, self.cfg
        a.last_action = action
        if action == "LIE":
            rec = a.rng.choice(a.repertoire)
            self._shout(a, {**rec, "via": a.i})
            a.last_result = "shouted a made-up lead"
        elif action.startswith("MOVE_"):
            a.at = action[5:]
            new = self._read(a, a.at)
            a.last_result = f"walked to {c.label(a.at)}" + ("" if new else " (nothing new)")
        elif action.startswith("SHARE_"):
            k = int(action[6:])
            if 0 <= k < len(a.known):
                rec = a.known[k]
                a.shared.add((rec["address"], rec["text"]))
                n = self._shout(a, {**rec, "via": a.i if rec["via"] == "seen" else rec["via"]})
                a.last_result = f"shouted lead #{k} to {n} Irregulars"
        elif action.startswith("REFUTE_"):
            addr = action[7:]
            liar = next((l for ad, l in reversed(a.refute) if ad == addr), None)
            a.refute = [r for r in a.refute if r[0] != addr]
            lead = c.leads[addr]
            n = self._shout(a, {"address": addr, "text": lead["text"], "fact": lead["fact"], "via": a.i,
                                "fake": False, "refutes": liar})
            a.last_result = f"told {n} Irregulars that Irregular {liar} lied about {c.label(addr)}"
        elif action.startswith("TAIL_"):
            a.tailing = (action[5:], self.tick + max(1, round(60 / cfg["tick_min"])))
            a.last_result = f"tailing {action[5:]}"
        else:
            a.last_result = "waited and listened"
        if a.liar:
            a.vote = dict(self.frame_up)
        elif not a.locked:
            a.vote = vote
            if a.stubborn and a.full_vote():
                a.locked = True

    def _shout(self, a, rec):
        hearers = self.within(a, self.cfg["comm_range"])
        if self.defend and rec["via"] == a.i and rec["address"] in self.case.by_id:
            # Hearers can see where the speaker stands; one street per tick bounds where it can have been.
            if self.case.hops(a.at).get(rec["address"], 999) > self.tick + 1:
                rec = {**rec, "implausible": True}
        for b in hearers:
            b.inbox.append(rec)
        x, y = self.pos(a)
        self.shares.append((a.i, x, y))
        return len(hearers)

    def end_tick(self):
        cfg = self.cfg
        self.tick += 1
        self.minute = self.tick * cfg["tick_min"]
        tally = self.tally()
        need = self.quorum_need()
        t = self.case.truth_ids()
        truth = (t["culprit"], t["motive"], t["hideout"])
        top = tally[0] if tally else None
        self.series.append({"tick": self.tick, "top": top[1] if top else 0, "truth": dict(tally).get(truth, 0),
                            "firm": sum(1 for a in self.irr if a.full_vote()),
                            "frame": dict(tally).get(tuple(self.frame_up.values()), 0)})
        if top and top[1] >= need:
            self.outcome = self._outcome(top[0], top[1], True)
            self.ended = True
        elif self.tick >= cfg["swarm_ticks"]:
            self.outcome = self._outcome(top[0] if top else None, top[1] if top else 0, False)
            self.ended = True

    def _outcome(self, triple, votes, quorum):
        t = self.case.truth_ids()
        if triple:
            acc = dict(zip(("culprit", "motive", "hideout"), triple))
        else:  # nobody holds a full vote: take the plurality of each part
            acc = {k: self.part_tally(k)[0][0] if self.part_tally(k) else None for k in ("culprit", "motive", "hideout")}
        ok = {k: acc[k] == t[k] for k in acc}
        return {**acc, "ok": ok, "parts": sum(ok.values()) if quorum else 0, "solved": quorum and all(ok.values()),
                "quorum": quorum, "votes": votes, "need": self.quorum_need(), "tick": self.tick,
                "minute": self.minute, "plurality_parts": sum(ok.values())}

    def quorum_need(self):
        return max(2, round(self.cfg["quorum_frac"] * len(self.irr)))

    def discredited(self):
        """With the defence, an Irregular caught lying by at least two others has its vote struck from the count."""
        if not self.defend:
            return set()
        caught = {}
        for a in self.irr:
            for j in a.distrust:
                caught[j] = caught.get(j, 0) + 1
        return {j for j, n in caught.items() if n >= 2}

    def tally(self):
        cnt = {}
        struck = self.discredited()
        for a in self.irr:
            if a.i in struck:
                continue
            v = a.full_vote()
            if v:
                cnt[v] = cnt.get(v, 0) + 1
        return sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))

    def part_tally(self, k):
        cnt = {}
        for a in self.irr:
            if a.vote[k]:
                cnt[a.vote[k]] = cnt.get(a.vote[k], 0) + 1
        return sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))

    def coverage(self):
        seen = set()
        for a in self.irr:
            seen |= a.visited
        keys = {ad for ad, l in self.case.leads.items() if l["fact"][0] in KEY_KINDS - {"pointer"} and not l["lie"]}
        return {"addresses": len(seen), "key_leads_found": len(keys & seen), "key_leads": len(keys)}


class JevIrregular:
    """One System One call per Irregular per tick: the action choice plus its three votes."""
    name, remote = "jev", True

    def __init__(self, cfg):
        self.cfg = cfg
        self.client = JevClient(cfg["jev_provider"], cfg["jev_model"], cfg["jev_key"], timeout=cfg["request_timeout_s"])

    def decide(self, game, a, cands):
        q = {"action": {"type": "choice", "instructions": INSTRUCTION, "criteria": cands}, **game.vote_questions()}
        state = json.dumps(game.observation(a), separators=(",", ":"))
        answers, meta = self.client.ask(state, q, retries=0)
        out = {}
        for k in ("action", "culprit", "motive", "hideout"):
            ans = answers.get(k) or {}
            valid = cands if k == "action" else q[k]["criteria"]
            probs = {x: float(p or 0) for x, p in (ans.get("probabilities") or {}).items() if x in valid}
            if not probs and ans.get("choice") in valid:
                probs = {ans["choice"]: 1.0}
            if not probs:
                raise LLMError(f"no usable answer for {k}")
            if k == "action" and self.cfg["sampling"] == "sample":
                r, acc, pick = a.rng.random() * sum(probs.values()), 0.0, None
                for x, p in probs.items():
                    acc += p
                    if r < acc:
                        pick = x
                        break
                out[k] = pick or max(probs, key=probs.get)
            else:
                out[k] = max(probs, key=lambda x: (probs[x], x))
        vote = {k: (None if out[k] == "UNSURE" else out[k]) for k in ("culprit", "motive", "hideout")}
        u = meta.get("usage") or {}
        return out["action"], vote, {"model": meta.get("model"), "in": int(u.get("input_tokens") or 0),
                                     "out": int(u.get("output_tokens") or 0), "cost": float(u.get("cost") or 0)}
