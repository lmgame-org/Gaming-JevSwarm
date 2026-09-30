"""Action selectors. Each gets one scout's observation (dict + exact JSON) and its candidate map, and returns a
probability distribution over candidate ids. None of them has a reference to the world.
"""
import hashlib
import json
import math
import os

from swarmcore.llm import JevClient, LLMClient, LLMError

from .observation import instruction


def prompt_hash(cfg):
    return hashlib.sha256(instruction(cfg).encode()).hexdigest()[:12]


def one_hot(cands, cid):
    return {k: (1.0 if k == cid else 0.0) for k in cands}


def normalize(probs, cands):
    p = {k: max(0.0, float(probs.get(k, 0.0) or 0.0)) for k in cands}
    s = sum(p.values())
    if s <= 0:
        raise LLMError("distribution has no mass on any available candidate")
    return {k: v / s for k, v in p.items()}


class LocalRule:
    """Seeley-style scout: dance for a good site right after inspecting it, keep re-inspecting and dancing (dance
    attrition does the forgetting), otherwise follow a remembered dance in proportion to its circuits, and search
    now and then."""
    name = "local_rule"
    remote = False

    def __init__(self, cfg):
        self.cfg = cfg

    def decide(self, obs, cands, state_json=None):
        me = obs["self"]
        if me["energy"] < 0.2:
            return one_hot(cands, "WAIT"), {}
        last = me["last_action"] or ""
        # just back from a site: advertise it if it is good enough to dance for
        for prefix in ("INSPECT_", "FOLLOW_DANCE_"):
            if last.startswith(prefix) and f"ADVERTISE_{last[len(prefix):]}" in cands:
                return one_hot(cands, f"ADVERTISE_{last[len(prefix):]}"), {}
        if last == "EXPLORE" and me["last_result"].startswith("inspected "):
            label = me["last_result"].split()[1].rstrip(":")
            if f"ADVERTISE_{label}" in cands:
                return one_hot(cands, f"ADVERTISE_{label}"), {}
        # just danced: go back and re-inspect the site (the next dance will be shorter)
        if last.startswith("ADVERTISE_"):
            label = last[len("ADVERTISE_"):]
            if f"INSPECT_{label}" in cands and f"ADVERTISE_{label}" in cands:
                return one_hot(cands, f"INSPECT_{label}"), {}
            if "STOP_ADVERTISING" in cands:
                return one_hot(cands, "STOP_ADVERTISING"), {}
        # holds a belief about a good site it has never danced for (e.g. misinformation): advertise it
        fresh = [k for k in obs["known_sites"] if k.get("inspections") and not k.get("my_dance_bouts_for_it")
                 and f"ADVERTISE_{k['site']}" in cands]
        if fresh and not me["currently_advertising"]:
            best = max(fresh, key=lambda k: k["my_quality_estimate"])
            return one_hot(cands, f"ADVERTISE_{best['site']}"), {}
        # uncommitted: follow dances in proportion to their circuits, else explore or wait
        dances = {d["site"]: d["total_circuits"] for d in obs["dances_observed_recently"]["sites"]}
        follow = {k: dances.get(k[len("FOLLOW_DANCE_"):], 0) for k in cands if k.startswith("FOLLOW_DANCE_")}
        tot = sum(follow.values())
        p = {k: 0.0 for k in cands}
        if tot > 0:
            for k, v in follow.items():
                p[k] = 0.7 * v / tot
            rest = 0.3
        else:
            rest = 1.0
        if "EXPLORE" in cands:
            p["EXPLORE"] += rest * 0.5
            p["WAIT"] += rest * 0.5
        else:
            p["WAIT"] += rest
        return normalize(p, cands), {}


class Uniform:
    name = "random"
    remote = False

    def __init__(self, cfg):
        pass

    def decide(self, obs, cands, state_json=None):
        return {k: 1.0 / len(cands) for k in cands}, {}


class Jev:
    """One Jev choice question per scout: state = that scout's observation, criteria = its candidate map."""
    name = "jev"
    remote = True

    def __init__(self, cfg):
        self.cfg = cfg
        self.client = JevClient(cfg["jev_provider"], cfg["jev_model"], cfg["jev_key"],
                                timeout=cfg["request_timeout_s"])

    def decide(self, obs, cands, state_json):
        q = {"action": {"type": "choice", "instructions": instruction(self.cfg), "criteria": cands}}
        answers, meta = self.client.ask(state_json, q, retries=1)
        a = answers.get("action") or {}
        raw = a.get("probabilities") or {}
        if not raw and a.get("choice") in cands:
            raw = {a["choice"]: 1.0}
        return normalize(raw, cands), {"raw": raw, "model": meta.get("model"), "usage": meta.get("usage")}


class Chat:
    """A chat model asked for a distribution over the same candidates (comparison selector)."""
    name = "chat"
    remote = True
    SYSTEM = (" You receive your own observation as JSON and a map of available action ids to descriptions. "
              "Reply with a JSON object {\"probabilities\": {id: p}} over the available ids only, summing to 1.")

    def __init__(self, cfg):
        self.cfg = cfg
        self.client = LLMClient("openai", cfg["chat_model"], cfg["chat_key"],
                                timeout=cfg["request_timeout_s"] * 4, temperature=1.0)

    def decide(self, obs, cands, state_json):
        user = json.dumps({"observation": obs, "available_actions": cands})
        out = self.client.chat(instruction(self.cfg) + self.SYSTEM, user, json_mode=True, max_tokens=400, retries=0)
        raw = out.get("probabilities", out) if isinstance(out, dict) else {}
        return normalize(raw, cands), {"raw": raw, "model": self.client.model}


class Replay:
    """Returns the recorded applied action for (scout, decision index); no model call."""
    name = "replay"
    remote = False

    def __init__(self, cfg, run_dir):
        self.table = {}
        with open(os.path.join(run_dir, "decisions.jsonl")) as f:
            for line in f:
                d = json.loads(line)
                self.table[(d["scout"], d["k"])] = d["applied"]

    def lookup(self, scout, k, cands):
        cid = self.table.get((scout, k))
        return one_hot(cands, cid) if cid in cands else None


def make(name, cfg, run_dir=None):
    if name == "jev":
        return Jev(cfg)
    if name == "chat":
        return Chat(cfg)
    if name == "local_rule":
        return LocalRule(cfg)
    if name == "random":
        return Uniform(cfg)
    if name == "replay":
        return Replay(cfg, run_dir)
    raise ValueError(f"unknown policy {name!r}")


def sample(probs, rng, argmax=False):
    keys = list(probs)
    if argmax:
        return max(keys, key=lambda k: probs[k])
    r = rng.random()
    acc = 0.0
    for k in keys:
        acc += probs[k]
        if r < acc:
            return k
    return keys[-1]


def entropy(probs):
    return -sum(p * math.log(p) for p in probs.values() if p > 0)
