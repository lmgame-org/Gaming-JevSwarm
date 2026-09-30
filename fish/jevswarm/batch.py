"""Headless matched comparisons: same seeds, scenario and controller for every policy.

  python3 -m jevswarm.batch --policies local_rule local_react random fixed_school --seeds 10
  python3 -m jevswarm.batch --policies jev local_rule --seeds 5 --scenario flank   # Jev costs money

The episode is the statistical unit; the table reports episode means with 95% t-intervals.
Remote policies run in controlled mode (decision barrier) so timing is comparable.
"""
import argparse
import json
import math
import os
import time

import numpy as np

from .engine import RUNS, Engine

METRICS = ["survival_fraction", "captures", "time_to_first_capture", "attack_largest_component",
           "attack_polarization", "strikes_spoiled_by_confusion", "largest_component", "polarization",
           "recovery_s", "mean_energy", "contacts_per_fish_minute", "indirect_response_latency_mean"]
T95 = {1: 12.71, 2: 4.30, 3: 3.18, 4: 2.78, 5: 2.57, 6: 2.45, 7: 2.36, 8: 2.31, 9: 2.26, 10: 2.23, 15: 2.13,
       20: 2.09, 29: 2.05}


def ci(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None, None, 0
    m = float(np.mean(xs))
    if len(xs) < 2:
        return m, None, len(xs)
    df = len(xs) - 1
    t = T95.get(df) or next((T95[k] for k in sorted(T95) if k >= df), 1.96)
    return m, t * float(np.std(xs, ddof=1)) / math.sqrt(len(xs)), len(xs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies", nargs="+", default=["local_rule", "local_react", "random", "fixed_school"])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--seed0", type=int, default=1)
    ap.add_argument("--scenario", default="demo")
    ap.add_argument("--set", nargs="*", default=[], help="extra key=value overrides")
    ap.add_argument("--no-logs", action="store_true")
    a = ap.parse_args()
    extra = dict(kv.split("=", 1) for kv in a.set)
    out_dir = os.path.join(RUNS, f"batch_{time.strftime('%Y%m%d-%H%M%S')}_{a.scenario}")
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for pol in a.policies:
        for s in range(a.seed0, a.seed0 + a.seeds):
            cfg = {"policy": pol, "seed": s, "scenario": a.scenario, "mode": "controlled", **extra}
            t0 = time.time()
            e = Engine(cfg, realtime=False, run_root=out_dir, log=not a.no_logs)
            sm = e.run_headless()
            sm["policy"] = pol
            sm["wall_s"] = round(time.time() - t0, 1)
            rows.append(sm)
            print(f"{pol:13s} seed {s}: survivors {sm['survivors']:3d}  captures {sm['captures']:3d}  "
                  f"LCF {sm['largest_component']}  policy-decisions {sm['inference']['policy_fraction']:.2f}  "
                  f"({sm['wall_s']} s)", flush=True)
    with open(os.path.join(out_dir, "episodes.json"), "w") as f:
        json.dump(rows, f, indent=1, default=str)
    print(f"\n{'metric':34s}" + "".join(f"{p:>22s}" for p in a.policies))
    table = {}
    for m in METRICS:
        line = f"{m:34s}"
        for p in a.policies:
            mean, half, n = ci([r[m] for r in rows if r["policy"] == p])
            table.setdefault(p, {})[m] = {"mean": mean, "ci95": half, "n": n}
            cell = "–" if mean is None else (f"{mean:.3f}" + (f" ± {half:.3f}" if half is not None else ""))
            line += f"{cell:>22s}"
        print(line)
    for p in a.policies:
        rec = [r for r in rows if r["policy"] == p and r.get("recovered") is not None]
        if rec:
            print(f"{p}: unrecovered fraction {sum(not r['recovered'] for r in rec) / len(rec):.2f}")
    for p in a.policies:
        mix, by = {}, {}
        for r in rows:
            if r["policy"] != p:
                continue
            for k, v in r["escape_mix"].items():
                mix[k] = mix.get(k, 0) + v
            for k, b in r["capture_rate_by_last_escape"].items():
                t = by.setdefault(k, [0, 0])
                t[0] += b["captured"]
                t[1] += b["fish"]
        tot = sum(mix.values()) or 1
        print(f"{p}: escape mix " + ", ".join(f"{k} {v / tot:.0%}" for k, v in sorted(mix.items())) +
              " | capture rate by last escape " + ", ".join(f"{k} {c / n:.2f} (n={n})" for k, (c, n) in sorted(by.items())))
    with open(os.path.join(out_dir, "table.json"), "w") as f:
        json.dump(table, f, indent=1)
    print(f"\nwrote {out_dir}")


if __name__ == "__main__":
    main()
