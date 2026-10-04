"""Solo mode: one detective, one address at a time, then an accusation.

The detective sees the brief, the address directory with cab times from where it stands, and its notebook (the
text of every lead it has collected). It never sees the structured facts, which leads are lies, or the truth;
only the rule baseline reads structured facts, and only for leads it has collected.
"""
import json
import random

from swarmcore.llm import JevClient, LLMClient, LLMError

from .reasoning import deduce, to_probs

INSTRUCTION = (
    "You are a consulting detective in Victorian London working one case. You know the brief and your notebook of "
    "leads; each address holds one short lead, and many are irrelevant. Witnesses sometimes lie, so prefer facts "
    "that turn up at more than one address. Each visit costs cab time and one visit from a limited budget. When you "
    "are confident, stop and accuse; an accusation scores one point each for the right culprit, motive and hideout."
)
Q_ACTION = INSTRUCTION + " Choose your next move: visit one address, or accuse now."
Q_CULPRIT = "Given only the brief and the notebook, who is most likely the culprit?"
Q_MOTIVE = "Given only the brief and the notebook, what was the most likely motive?"
Q_HIDEOUT = "Given only the brief and the notebook, which possible hideout is the culprit most likely using?"
Q_READY = ("Does the notebook already establish, with corroborating leads, one culprit, one motive and one hideout, "
           "so that accusing now would very likely be right on all three? Early accusations usually fail.")


def hhmm(minute):
    m = int(round(minute)) + 8 * 60
    return f"{(m // 60) % 24:02d}:{m % 60:02d}" + ("" if m < 24 * 60 else f" (+{m // (24 * 60)}d)")


class SoloGame:
    def __init__(self, case, cfg):
        self.case, self.cfg = case, cfg
        self.at = case.specials["baker"]
        self.minute = 0.0
        self.visits = 0
        self.path = [self.at]
        self.visited = {self.at}
        self.notebook = [{"n": 0, "address": self.at, "minute": 0.0, "text": case.leads[self.at]["text"]}]
        self.accusation = None
        self.forced = False
        self.belief = {}
        self.ended = False

    # ------------------------------------------------------------------ what the detective sees
    def reachable(self):
        """Unvisited addresses that can still be reached and interviewed before the deadline."""
        c, cfg = self.case, self.cfg
        if self.visits >= cfg["visit_budget"]:
            return {}
        left = cfg["deadline_hours"] * 60 - self.minute
        out = {}
        for a in c.by_id:
            if a in self.visited:
                continue
            t = c.travel_min(self.at, a)
            if t + cfg["interview_min"] <= left:
                out[a] = t
        return out

    def candidates(self):
        c = self.case
        reach = self.reachable()
        out = {}
        for a in sorted(reach, key=lambda a: reach[a]):
            x = c.by_id[a]
            out[f"VISIT_{a}"] = f"{x['street']}, {x['district']} ({x['type']}), {int(round(reach[a]))} min by cab"
        out["ACCUSE"] = "Stop investigating and name the culprit, the motive and the hideout now"
        return out

    def observation(self):
        c, cfg = self.case, self.cfg
        x = c.by_id[self.at]
        return {
            "brief": c.brief(),
            "now": {"at": f"{self.at} {x['street']}, {x['district']}", "clock": hhmm(self.minute),
                    "minutes_left": int(cfg["deadline_hours"] * 60 - self.minute),
                    "visits_left": cfg["visit_budget"] - self.visits},
            "notebook": [{"address": f"{n['address']} {c.label(n['address'])}", "lead": n["text"]}
                         for n in self.notebook],
        }

    def facts(self):
        return [self.case.leads[n["address"]]["fact"] for n in self.notebook]

    # ------------------------------------------------------------------ moves
    def visit(self, a):
        c, cfg = self.case, self.cfg
        t = c.travel_min(self.at, a)
        self.minute += t + cfg["interview_min"]
        self.at = a
        self.visits += 1
        self.visited.add(a)
        self.path.append(a)
        lead = c.leads[a]
        self.notebook.append({"n": self.visits, "address": a, "minute": round(self.minute, 1), "text": lead["text"]})
        return lead

    def accuse(self, culprit, motive, hideout, forced=False):
        t = self.case.truth_ids()
        acc = {"culprit": culprit, "motive": motive, "hideout": hideout}
        ok = {k: acc[k] == t[k] for k in acc}
        self.accusation = {**acc, "ok": ok, "parts": sum(ok.values()), "solved": all(ok.values()),
                           "forced": forced, "minute": round(self.minute, 1), "visits": self.visits}
        self.ended = True
        return self.accusation


# ---------------------------------------------------------------------- detectives
def _argmax(p):
    return max(p, key=lambda k: (p[k], k)) if p else None


def _norm(raw, keys):
    p = {k: max(0.0, float((raw or {}).get(k) or 0)) for k in keys}
    s = sum(p.values())
    if s <= 0:
        raise LLMError("no probability mass on any valid option")
    return {k: v / s for k, v in p.items()}


class Random:
    name, remote = "random", False

    def __init__(self, cfg):
        self.rng = random.Random(f"random-{cfg['seed']}")

    def decide(self, g, final=False):
        c = g.case
        cands = {} if final else g.candidates()
        b = {"culprit": {s["id"]: 1 / len(c.suspects) for s in c.suspects},
             "motive": {f"M{i + 1}": 1 / len(c.motives) for i in range(len(c.motives))},
             "hideout": {h["id"]: 1 / len(c.hideouts) for h in c.hideouts}}
        pick = {k: self.rng.choice(sorted(v)) for k, v in b.items()}
        act = None
        if cands:
            visits = [k for k in cands if k != "ACCUSE"]
            act = self.rng.choice(visits) if visits else "ACCUSE"
        return {"action": act, "belief": b, "pick": pick, "note": "", "meta": {}}


class Rule:
    """Follows pointers, then works outward from where each open question's evidence should be, and accuses as soon
    as culprit, motive and hideout each lead their alternatives by at least one uncontradicted lead."""
    name, remote = "rule", False

    def __init__(self, cfg):
        self.cfg = cfg

    def decide(self, g, final=False):
        c = g.case
        b = deduce(g.facts(), c)
        belief = {k: to_probs(v["scores"]) for k, v in b.items()}
        pick = {k: v["best"] for k, v in b.items()}
        note = ", ".join(f"{k} {v['best']}{'' if v['confident'] else '?'}" for k, v in b.items())
        if final:
            return {"action": None, "belief": belief, "pick": pick, "note": note, "meta": {}}
        if all(v["confident"] for v in b.values()):
            return {"action": "ACCUSE", "belief": belief, "pick": pick, "note": "sure: " + note, "meta": {}}
        reach = g.reachable()
        if not reach:
            return {"action": "ACCUSE", "belief": belief, "pick": pick, "note": "out of time: " + note, "meta": {}}
        # 1. unvisited pointer targets, newest first
        for n in reversed(g.notebook):
            f = c.leads[n["address"]]["fact"]
            if f[0] == "pointer" and f[1] in reach:
                return {"action": f"VISIT_{f[1]}", "belief": belief, "pick": pick, "note": "following a pointer",
                        "meta": {}}
        # 2. score addresses by where the evidence for still-open questions should be
        want = {}
        if not b["culprit"]["confident"]:
            for a in c.nearest(c.scene, 18):
                want[a] = want.get(a, 0) + 3
            for s in c.suspects:  # homes of suspects still in the running (alibis live there)
                if b["culprit"]["scores"][s["id"]] >= max(b["culprit"]["scores"].values()) - 0.5:
                    want[s["home"]] = want.get(s["home"], 0) + 2.5
                    for a in c.nearest(s["home"], 4):
                        want[a] = want.get(a, 0) + 1
        if not b["motive"]["confident"]:
            for a in c.nearest(c.victim["home"], 22):
                want[a] = want.get(a, 0) + 2
        if not b["hideout"]["confident"]:
            hs = b["hideout"]["scores"]
            top = max(hs.values())
            for h in c.hideouts:
                if hs[h["id"]] >= top - 0.5 and b["hideout"]["margin"] < 1:
                    want[h["address"]] = want.get(h["address"], 0) + (4 if top > -50 else 1)
            if top < -50 or b["hideout"]["margin"] >= 1:
                best = c.hideout(b["hideout"]["best"])
                want[best["address"]] = want.get(best["address"], 0) + 6
        best = max(reach, key=lambda a: (want.get(a, 0.2) / (reach[a] + g.cfg["interview_min"]), a))
        return {"action": f"VISIT_{best}", "belief": belief, "pick": pick, "note": note, "meta": {}}


class Jev:
    """One System One call per step: a choice over moves plus three belief questions."""
    name, remote = "jev", True

    def __init__(self, cfg):
        self.cfg = cfg
        self.client = JevClient(cfg["jev_provider"], cfg["jev_model"], cfg["jev_key"],
                                timeout=max(cfg["request_timeout_s"], 20))
        self.rng = random.Random(f"jev-{cfg['seed']}")

    def questions(self, g, cands):
        c = g.case
        q = {"culprit": {"type": "choice", "instructions": Q_CULPRIT,
                         "criteria": c.brief()["suspects"]},
             "motive": {"type": "choice", "instructions": Q_MOTIVE, "criteria": c.brief()["motives"]},
             "hideout": {"type": "choice", "instructions": Q_HIDEOUT, "criteria": c.brief()["possible_hideouts"]}}
        visits = {k: v for k, v in cands.items() if k != "ACCUSE"}
        if visits:
            q["action"] = {"type": "choice", "instructions": Q_ACTION.replace(", or accuse now", ""),
                           "criteria": visits}
            q["ready"] = {"type": "noul", "instructions": Q_READY}
        return q

    def decide(self, g, final=False):
        cands = {} if final else g.candidates()
        if len(cands) > 255:  # System One accepts at most 255 choices: offer the nearest addresses (sorted by cab time)
            cands = {**dict(list((k, v) for k, v in cands.items() if k != "ACCUSE")[:254]), "ACCUSE": cands["ACCUSE"]}
        state = json.dumps(g.observation(), separators=(",", ":"))
        answers, meta = self.client.ask(state, self.questions(g, cands), retries=1)
        belief, pick = {}, {}
        keys = {"culprit": [s["id"] for s in g.case.suspects], "motive": list(g.case.brief()["motives"]),
                "hideout": [h["id"] for h in g.case.hideouts]}
        for k, ks in keys.items():
            a = answers.get(k) or {}
            raw = a.get("probabilities") or ({a["choice"]: 1.0} if a.get("choice") in ks else {})
            belief[k] = _norm(raw, ks)
            pick[k] = _argmax(belief[k])
        act, aprobs, ready = None, None, None
        visits = [k for k in cands if k != "ACCUSE"]
        if cands and not visits:
            act = "ACCUSE"
        elif visits:
            ready = float((answers.get("ready") or {}).get("noul") or 0)
            a = answers.get("action") or {}
            raw = a.get("probabilities") or ({a["choice"]: 1.0} if a.get("choice") in visits else {})
            aprobs = _norm(raw, visits)
            if self.cfg["sampling"] == "sample":
                r, acc, act = self.rng.random(), 0.0, None
                for k, v in aprobs.items():
                    acc += v
                    if r < acc:
                        act = k
                        break
                act = act or _argmax(aprobs)
            else:
                act = _argmax(aprobs)
            if ready >= self.cfg["jev_accuse_at"]:
                act = "ACCUSE"
        u = meta.get("usage") or {}
        top = sorted(aprobs.items(), key=lambda kv: -kv[1])[:6] if aprobs else []
        return {"action": act, "belief": belief, "pick": pick,
                "note": f"ready to accuse: {ready:.2f}" if ready is not None else "", "ready": ready,
                "action_probs": {k: round(v, 3) for k, v in top},
                "meta": {"model": meta.get("model"), "in": int(u.get("input_tokens") or u.get("prompt_tokens") or 0),
                         "out": int(u.get("output_tokens") or u.get("completion_tokens") or 0),
                         "cost": float(u.get("cost") or 0)}}


class Chat:
    """The 'genius': a chat model reads the brief, directory and notebook and answers with a move and its current
    best accusation. The static case file is sent first so the provider can cache it across steps."""
    name, remote = "chat", True
    FORMAT = ('Reply with one JSON object: {"thinking": "<at most 40 words>", "action": "VISIT_<address id>" or '
              '"ACCUSE", "culprit": "<S id>", "motive": "<M id>", "hideout": "<H id>"}. culprit, motive and hideout '
              'are your current best answer even if you keep investigating.')

    def __init__(self, cfg):
        self.cfg = cfg
        self.client = LLMClient("openai", cfg["chat_model"], cfg["chat_key"], timeout=120, temperature=1.0)

    def static(self, g):
        c = g.case
        directory = [f"{a['id']}: {a['street']}, {a['district']} ({a['type']})" for a in c.addresses]
        return (INSTRUCTION + "\n\n" + self.FORMAT + "\n\nCASE BRIEF\n" + json.dumps(c.brief(), indent=0) +
                "\n\nADDRESS DIRECTORY\n" + "\n".join(directory))

    def decide(self, g, final=False):
        obs = g.observation()
        reach = {} if final else g.reachable()
        dyn = {"now": obs["now"], "notebook": obs["notebook"],
               "visit_options_minutes_by_cab": {a: int(round(t)) for a, t in sorted(reach.items(), key=lambda kv: kv[1])}}
        if final or not reach:
            dyn["note"] = "You must accuse now: give action ACCUSE with your final culprit, motive and hideout."
        out = self.client.chat(self.static(g), json.dumps(dyn, separators=(",", ":")), json_mode=True,
                               max_tokens=1500, retries=1)
        u = self.client.last_usage or {}
        tin = int(u.get("prompt_tokens") or 0)
        cached = int((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        tout = int(u.get("completion_tokens") or 0)
        cfg = self.cfg
        cost = ((tin - cached) * cfg["chat_price_in"] + cached * cfg["chat_price_cached"] +
                tout * cfg["chat_price_out"]) / 1e6
        c = g.case
        valid = {"culprit": [s["id"] for s in c.suspects], "motive": list(c.brief()["motives"]),
                 "hideout": [h["id"] for h in c.hideouts]}
        pick, belief = {}, {}
        for k, ks in valid.items():
            v = str(out.get(k) or "").strip().upper()
            pick[k] = v if v in ks else ks[0]
            belief[k] = {x: (1.0 if x == pick[k] else 0.0) for x in ks}
        act = str(out.get("action") or "").strip().upper().replace(" ", "_")
        if act.startswith("VISIT") and not act.startswith("VISIT_"):
            act = "VISIT_" + act[5:].lstrip("_")
        if final:
            act = None
        elif act != "ACCUSE" and (not act.startswith("VISIT_") or act[6:] not in reach):
            act = "ACCUSE" if not reach else f"VISIT_{min(reach, key=reach.get)}"  # invalid move: nearest address
        return {"action": act, "belief": belief, "pick": pick, "note": str(out.get("thinking") or "")[:300],
                "meta": {"model": self.client.model, "in": tin, "cached": cached, "out": tout, "cost": cost}}


def make(name, cfg):
    return {"jev": Jev, "chat": Chat, "rule": Rule, "random": Random}[name](cfg)
