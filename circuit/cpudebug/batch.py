"""Headless runs for pilots and benchmarks.

    python3 -m cpudebug.batch --modes jev,hybrid,cone,genius --seeds 1-5 [--out docs/pilot.csv] [key=value ...]
"""
import argparse
import csv
import json
import sys
import time

from .engine import Engine


def seeds(s):
    out = []
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            out += list(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser(prog="python3 -m cpudebug.batch")
    ap.add_argument("--modes", default="jev,hybrid,cone,genius")
    ap.add_argument("--seeds", default="1-5")
    ap.add_argument("--out", default=None)
    ap.add_argument("overrides", nargs="*", help="key=value config overrides")
    a = ap.parse_args()
    over = dict(kv.split("=", 1) for kv in a.overrides)
    rows = []
    for mode in a.modes.split(","):
        for s in seeds(a.seeds):
            t = time.time()
            e = Engine(dict(over, mode=mode, seed=s), realtime=False)
            e.run()
            sm = e.summary
            r, ans, inf = sm["result"], sm["answer"] or {}, sm["inference"]
            row = {"mode": mode, "seed": s, "test": sm["test"], "bug_block": sm["bug"]["block"],
                   "bug_port": sm["bug"]["port"], "bug_type": sm["bug"]["type"], "bug_key": sm["bug"]["key"],
                   "named_block": ans.get("block"), "named_port": ans.get("port"), "named_type": ans.get("type"),
                   "named_key": ans.get("key"), "block_ok": r["block_ok"], "location_ok": r["location_ok"],
                   "type_ok": r["type_ok"], "fix_ok": r["fix_ok"], "probes": sm["probes"], "rounds": sm["rounds"],
                   "calls": inf["calls"], "fallbacks": inf["fallbacks"], "cost_usd": inf["cost"],
                   "wall_s": round(time.time() - t, 1), "errors": "; ".join(sm["errors"])[:200]}
            rows.append(row)
            print(json.dumps(row), flush=True)
    if a.out:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
