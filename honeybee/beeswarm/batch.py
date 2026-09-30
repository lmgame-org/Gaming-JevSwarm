"""Headless matched comparisons: same seeds for every policy and setting, with 95% intervals.

Examples:
  python3 -m beeswarm.batch --policies local_rule random --seeds 20
  python3 -m beeswarm.batch --policies local_rule --vary misinfo_frac=0,0.1,0.2,0.3 --seeds 30
  python3 -m beeswarm.batch --policies jev local_rule --scenario close_call --seeds 5   # Jev: ~$0.02 per episode
"""
import argparse
import itertools
import json
import math
import os
import time

from .engine import RUNS, Engine


def parse_val(v):
    try:
        return json.loads(v)
    except ValueError:
        return v


def wilson(k, n):
    if not n:
        return (0.0, 0.0)
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (c - h) / d), min(1.0, (c + h) / d))


def mean_ci(xs):
    if not xs:
        return (None, None)
    m = sum(xs) / len(xs)
    if len(xs) < 2:
        return (m, 0.0)
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
    return (m, 1.96 * sd / math.sqrt(len(xs)))


def main():
    ap = argparse.ArgumentParser(prog="python3 -m beeswarm.batch")
    ap.add_argument("--policies", nargs="+", default=["local_rule", "random"])
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--scenario", default="classic")
    ap.add_argument("--set", nargs="*", default=[], help="fixed overrides, key=value")
    ap.add_argument("--vary", nargs="*", default=[], help="swept settings, key=v1,v2,...")
    a = ap.parse_args()
    fixed = {k: parse_val(v) for k, v in (s.split("=", 1) for s in a.set)}
    sweeps = [(k, [parse_val(x) for x in v.split(",")]) for k, v in (s.split("=", 1) for s in a.vary)]
    keys = [k for k, _ in sweeps]
    combos = list(itertools.product(*[vals for _, vals in sweeps])) or [()]
    out_dir = os.path.join(RUNS, f"batch_{time.strftime('%Y%m%d-%H%M%S')}_{a.scenario}")
    os.makedirs(out_dir, exist_ok=True)
    rows, episodes = [], []
    for combo in combos:
        over = dict(zip(keys, combo))
        for pol in a.policies:
            res = []
            for seed in range(1, a.seeds + 1):
                cfg = {"scenario": a.scenario, "policy": pol, "seed": seed, **fixed, **over}
                s = Engine(cfg, realtime=False, runs_dir=out_dir).run_all()
                res.append(s)
                episodes.append({"cfg": cfg, "summary": s})
            n = len(res)
            k = sum(r["correct"] for r in res)
            lo, hi = wilson(k, n)
            hrs = [r["decision_hours"] for r in res if r["decided"]]
            m, ci = mean_ci(hrs)
            row = {**over, "policy": pol, "n": n, "correct": k / n, "ci": (round(lo, 2), round(hi, 2)),
                   "hours": m, "hours_ci": ci, "splits": sum(r["split"] for r in res),
                   "undecided": sum(not r["decided"] for r in res),
                   "cost": sum(r["inference"]["cost"] for r in res)}
            rows.append(row)
            label = " ".join(f"{k}={v}" for k, v in over.items())
            hs = f"{m:.2f}±{ci:.2f} h" if m is not None else "-"
            print(f"{label:28s} {pol:11s} best site {k:3d}/{n} = {k / n:.2f} [{lo:.2f},{hi:.2f}]  time {hs:14s} "
                  f"splits {row['splits']}  undecided {row['undecided']}  cost ${row['cost']:.3f}", flush=True)
    with open(os.path.join(out_dir, "table.json"), "w") as f:
        json.dump(rows, f, indent=1, default=str)
    with open(os.path.join(out_dir, "episodes.json"), "w") as f:
        json.dump(episodes, f, default=str)
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
