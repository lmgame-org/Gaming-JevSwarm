"""Headless benchmark runs over named settings, resumable, with a total spend guard.

    python3 -m cpudebug.batch --settings solo_rule,baker_rule_jev --seeds 1-20 --out docs/bench.csv [--max-usd 15]
    python3 -m cpudebug.batch --list
Rows already in --out (same setting and seed) are skipped, so a stopped run can be resumed. Every finished run is
appended at once. --max-usd stops starting new runs once the CSV's total cost reaches it.
"""
import argparse
import csv
import json
import os
import sys
import time

from .engine import Engine

SETTINGS = {
    "solo_genius": ("Solo · gpt-6-astra", {"mode": "solo", "solo_policy": "chat"}),
    "solo_jev": ("Solo · Jev", {"mode": "solo", "solo_policy": "jev"}),
    "solo_rule": ("Solo · rule (cone tracing)", {"mode": "solo", "solo_policy": "rule"}),
    "solo_random": ("Solo · random", {"mode": "solo", "solo_policy": "random"}),
    "baker_genius_jev": ("Baker Street · gpt-6-astra Holmes, Jev boys", {"mode": "leader", "holmes": "chat", "boy_policy": "jev"}),
    "baker_genius_rule": ("Baker Street · gpt-6-astra Holmes, rule boys", {"mode": "leader", "holmes": "chat", "boy_policy": "rule"}),
    "baker_rule_jev": ("Baker Street · counting Holmes, Jev boys", {"mode": "leader", "holmes": "rule", "boy_policy": "jev"}),
    "baker_rule_jev_nowiggins": ("Baker Street · counting Holmes, Jev boys, no Wiggins",
                                 {"mode": "leader", "holmes": "rule", "boy_policy": "jev", "wiggins": False}),
    "baker_rule_rule": ("Baker Street · counting Holmes, rule boys", {"mode": "leader", "holmes": "rule", "boy_policy": "rule"}),
    "baker_rule_rule_nowiggins": ("Baker Street · counting Holmes, rule boys, no Wiggins",
                                  {"mode": "leader", "holmes": "rule", "boy_policy": "rule", "wiggins": False}),
    "baker_rule_random": ("Baker Street · counting Holmes, random boys", {"mode": "leader", "holmes": "rule", "boy_policy": "random"}),
    "swarm_rule_r2": ("Swarm · rule · 2 wires", {"mode": "swarm", "swarm_policy": "rule", "comm_range": 2}),
    "swarm_random_r2": ("Swarm · random · 2 wires", {"mode": "swarm", "swarm_policy": "random", "comm_range": 2}),
    "swarm_jev_r2": ("Swarm · Jev · 2 wires", {"mode": "swarm", "swarm_policy": "jev", "comm_range": 2}),
    "swarm_hybrid_r2": ("Swarm · hybrid · 2 wires", {"mode": "swarm", "swarm_policy": "hybrid", "comm_range": 2}),
    "swarm_rule_r4": ("Swarm · rule · 4 wires", {"mode": "swarm", "swarm_policy": "rule", "comm_range": 4}),
    "swarm_jev_r4": ("Swarm · Jev · 4 wires", {"mode": "swarm", "swarm_policy": "jev", "comm_range": 4}),
    "swarm_hybrid_r4": ("Swarm · hybrid · 4 wires", {"mode": "swarm", "swarm_policy": "hybrid", "comm_range": 4}),
}

FIELDS = ["setting", "label", "seed", "test", "n_bugs", "bug_blocks", "bug_types", "bug_keys", "rare",
          "named_blocks", "named_keys", "block_ok", "location_ok", "type_ok", "fix_ok", "tests_passed",
          "sim_hours", "ran_to_deadline", "wrong_quorum", "probes", "calls", "failures", "fallbacks", "cost_usd",
          "wall_s", "liars", "errors"]


def seeds(s):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def read_rows(path):
    if not path or not os.path.isfile(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser(prog="python3 -m cpudebug.batch")
    ap.add_argument("--settings", default="solo_rule,baker_rule_rule,swarm_rule_r2")
    ap.add_argument("--seeds", default="1-20")
    ap.add_argument("--out", required=False)
    ap.add_argument("--max-usd", type=float, default=15.0)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("overrides", nargs="*", help="key=value config overrides")
    a = ap.parse_args()
    if a.list:
        for k, (lab, cfg) in SETTINGS.items():
            print(f"{k:28s} {lab}")
        return 0
    over = dict(kv.split("=", 1) for kv in a.overrides)
    done = {(r["setting"], int(r["seed"])) for r in read_rows(a.out)}
    for name in a.settings.split(","):
        label, cfg = SETTINGS[name]
        for s in seeds(a.seeds):
            if (name, s) in done:
                continue
            spent = sum(float(r["cost_usd"] or 0) for r in read_rows(a.out))
            if spent >= a.max_usd:
                print(f"spend guard: ${spent:.2f} >= ${a.max_usd:.2f}, stopping", flush=True)
                return 1
            t = time.time()
            e = Engine(dict(over, **cfg, seed=s), realtime=False)
            e.run()
            sm = e.summary
            r, ans, inf, bug = sm["result"], sm["answer"] or {}, sm["inference"], sm["bug"]
            fixes = ans.get("fixes") or []
            row = {"setting": name, "label": label, "seed": s, "test": sm["test"], "n_bugs": len(bug["bugs"]),
                   "bug_blocks": "+".join(b["block"] for b in bug["bugs"]),
                   "bug_types": "+".join(b["type"] for b in bug["bugs"]),
                   "bug_keys": "+".join(b["key"] for b in bug["bugs"]),
                   "rare": "+".join(str(int(b["rare"])) for b in bug["bugs"]),
                   "named_blocks": "+".join(f["block"] for f in fixes), "named_keys": "+".join(str(f["key"]) for f in fixes),
                   "block_ok": r["block_ok"], "location_ok": r["location_ok"], "type_ok": r["type_ok"],
                   "fix_ok": r["fix_ok"], "tests_passed": r["tests_passed"], "sim_hours": sm["sim_hours"],
                   "ran_to_deadline": sm["ran_to_deadline"], "wrong_quorum": sm["wrong_quorum"],
                   "probes": sm["probes"], "calls": inf["calls"], "failures": inf["failures"],
                   "fallbacks": inf["fallbacks"], "cost_usd": inf["cost"], "wall_s": round(time.time() - t, 1),
                   "liars": len(sm["liars"]), "errors": "; ".join(sm["errors"])[:200]}
            if a.out:
                new = not os.path.isfile(a.out)
                with open(a.out, "a", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=FIELDS)
                    if new:
                        w.writeheader()
                    w.writerow(row)
            print(json.dumps(row), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
