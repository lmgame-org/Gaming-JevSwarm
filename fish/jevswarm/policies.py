"""Action selectors. Each takes an immutable local observation (JSON text + dict) and the candidate
set, and returns a probability distribution over candidate ids. None has a reference to the world.
"""
import hashlib
import json
import math
import os

from .candidates import criteria, instruction
from .llm import JevClient, LLMClient, LLMError



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
    """School with visible fish, flee visible predators, rest when tired."""
    name = "local_rule"
    remote = False

    def __init__(self, cfg, react=False, escape="ESCAPE_S"):
        self.cfg = cfg
        self.react = react
        self.escape = escape

    def decide(self, obs, cands, state_json=None):
        for cid in (self.escape, "ESCAPE_S"):
            if cid in cands:
                return one_hot(cands, cid), {}
        if self.react:
            fast = cands and [e for e in obs["visible_fish"][:3]
                              if (e["speed_estimate"] or 0) >= self.cfg["cruise"] + 1.0
                              or abs(e["turn_rate_estimate_deg_s"] or 0) >= 60]
            if fast:
                for cid in (f"FLEE_WITH_{fast[0]['slot']}", f"FOLLOW_{fast[0]['slot']}"):
                    if cid in cands:
                        return one_hot(cands, cid), {}
        if obs["self"]["energy"] < 0.3:
            return one_hot(cands, "RECOVER"), {}
        if "ALIGN" in cands:
            near = obs["visible_fish"][0]["range"]
            return one_hot(cands, "COHERE" if near > 3.0 else "ALIGN"), {}
        return one_hot(cands, "SCAN_L" if obs["self"]["previous_action"] != "SCAN_R" else "SCAN_R"), {}


class FixedSchool:
    name = "fixed_school"
    remote = False

    def __init__(self, cfg):
        pass

    def decide(self, obs, cands, state_json=None):
        return one_hot(cands, "ALIGN" if "ALIGN" in cands else "CONTINUE"), {}


class Uniform:
    name = "random"
    remote = False

    def __init__(self, cfg):
        pass

    def decide(self, obs, cands, state_json=None):
        return {k: 1.0 / len(cands) for k in cands}, {}


class Jev:
    """One Jev choice question per fish: state = that fish's observation, criteria = candidate map."""
    name = "jev"
    remote = True

    def __init__(self, cfg):
        self.cfg = cfg
        self.client = JevClient(cfg["jev_provider"], cfg["jev_model"], cfg["jev_key"],
                                timeout=cfg["request_timeout_s"])

    def decide(self, obs, cands, state_json):
        q = {"action": {"type": "choice", "instructions": instruction(self.cfg), "criteria": criteria(cands)}}
        answers, meta = self.client.ask(state_json, q, retries=0)
        a = answers.get("action") or {}
        raw = a.get("probabilities") or {}
        if not raw and a.get("choice") in cands:
            raw = {a["choice"]: 1.0}
        return normalize(raw, cands), {"raw": raw, "model": meta.get("model"),
                                       "usage": meta.get("usage"), "jev_choice": a.get("choice")}


class Chat:
    """A chat model asked for a distribution over the same candidates (comparison selector)."""
    name = "chat"
    remote = True
    SYSTEM = (" You receive one fish's local observation as JSON and a map of "
              "available action ids to descriptions. Reply with a JSON object {\"probabilities\": {id: p}} "
              "over the available ids only, summing to 1.")

    def __init__(self, cfg):
        self.cfg = cfg
        self.client = LLMClient("openai", cfg["chat_model"], cfg["chat_key"], timeout=cfg["request_timeout_s"] * 3,
                                temperature=1.0)

    def decide(self, obs, cands, state_json):
        user = json.dumps({"observation": obs, "available_actions": criteria(cands)})
        out = self.client.chat(instruction(self.cfg) + self.SYSTEM, user, json_mode=True, max_tokens=400, retries=0)
        raw = out.get("probabilities", out) if isinstance(out, dict) else {}
        return normalize(raw, cands), {"raw": raw, "model": self.client.model}


class Replay:
    """Returns the recorded applied action for (fish, decision index); no model call."""
    name = "replay"
    remote = False

    def __init__(self, cfg, run_dir):
        self.table = {}
        path = os.path.join(run_dir, "decisions.jsonl")
        with open(path) as f:
            for line in f:
                d = json.loads(line)
                self.table[(d["fish"], d["k"])] = d["applied"]

    def lookup(self, fish, k, cands):
        cid = self.table.get((fish, k))
        if cid in cands:
            return one_hot(cands, cid), {"replayed": True}
        return None


def make(name, cfg, run_dir=None):
    if name == "jev":
        return Jev(cfg)
    if name == "chat":
        return Chat(cfg)
    if name == "local_rule":
        return LocalRule(cfg)
    if name == "local_react":
        return LocalRule(cfg, react=True)
    if name == "local_coop":
        return LocalRule(cfg, escape="ESCAPE_GROUP")
    if name == "local_selfish":
        return LocalRule(cfg, escape="ESCAPE_SELFISH")
    if name == "random":
        return Uniform(cfg)
    if name == "fixed_school":
        return FixedSchool(cfg)
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
