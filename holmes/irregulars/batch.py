"""Headless matched comparisons on the same seeded cases, with 95% intervals.

Examples:
  python3 -m irregulars.batch --mode solo --policies rule random --seeds 20
  python3 -m irregulars.batch --mode solo --policies jev chat rule random --seeds 5
  python3 -m irregulars.batch --mode swarm --policies jev rule random --seeds 5
  python3 -m irregulars.batch --mode swarm --policies rule --vary liar_frac=0,0.05,0.15 --seeds 20
  python3 -m irregulars.batch --mode swarm --policies jev --fair-to runs/batch_..._solo   # cap $ at the genius's spend
"""
import argparse
import itertools
import json
import math
import os
import time

from .config import DEFAULTS, coerce
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


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def genius_costs(folder):
    """Per-seed spend of the chat (genius) detective in an earlier solo batch."""
    with open(os.path.join(folder, "episodes.json")) as f:
        eps = json.load(f)
    return {e["cfg"]["seed"]: e["summary"]["inference"]["cost"] for e in eps if e["cfg"].get("policy") == "chat"}


def main():
    ap = argparse.ArgumentParser(prog="python3 -m irregulars.batch")
    ap.add_argument("--mode", default="solo", choices=["solo", "swarm"])
    ap.add_argument("--policies", nargs="+", default=["rule", "random"])
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--set", nargs="*", default=[], help="fixed overrides, key=value")
    ap.add_argument("--vary", nargs="*", default=[], help="swept settings, key=v1,v2,...")
    ap.add_argument("--max-usd", type=float, default=0.0, help="stop starting new runs once this much is spent")
    ap.add_argument("--fair-to", default="", help="solo batch folder: cap each swarm run at the genius's spend")
    a = ap.parse_args()
    fixed = {k: parse_val(v) for k, v in (s.split("=", 1) for s in a.set)}
    checked = coerce(fixed)
    for k, v in fixed.items():  # refuse silently ignored settings (e.g. "difficulty=holmesian x=1" passed as one word)
        if k not in DEFAULTS or (isinstance(DEFAULTS[k], str) and checked[k] != str(v)):
            ap.error(f"--set {k}={v!r} is not a valid setting")
    sweeps = [(k, [parse_val(x) for x in v.split(",")]) for k, v in (s.split("=", 1) for s in a.vary)]
    keys = [k for k, _ in sweeps]
    combos = list(itertools.product(*[vals for _, vals in sweeps])) or [()]
    caps = genius_costs(a.fair_to) if a.fair_to else {}
    out_dir = os.path.join(RUNS, f"batch_{time.strftime('%Y%m%d-%H%M%S')}_{a.mode}_{os.getpid()}")
    os.makedirs(out_dir, exist_ok=True)
    rows, episodes = [], []
    pkey = "policy" if a.mode == "solo" else "swarm_policy"
    for combo in combos:
        over = dict(zip(keys, combo))
        for pol in a.policies:
            res = []
            for seed in range(a.first_seed, a.first_seed + a.seeds):
                spent = sum(ep["summary"]["inference"]["cost"] for ep in episodes)
                if a.max_usd and spent >= a.max_usd:
                    print(f"  stopping: ${spent:.3f} spent >= --max-usd {a.max_usd}", flush=True)
                    break
                cfg = {"mode": a.mode, pkey: pol, "seed": seed, **fixed, **over}
                if caps.get(seed):
                    cfg["budget_cap_usd"] = caps[seed]
                t0 = time.time()
                s = Engine(cfg, realtime=False, runs_dir=out_dir).run_all()
                s["wall_s"] = round(time.time() - t0, 1)
                res.append(s)
                episodes.append({"cfg": cfg, "summary": s})
                o = s["outcome"] or {}
                print(f"  seed {seed:3d} {pol:7s} parts {s['parts']}/3 {o.get('ok')} "
                      f"{'visits ' + str(s.get('visits')) if a.mode == 'solo' else 'tick ' + str(s.get('ticks'))} "
                      f"${s['inference']['cost']:.4f} {s['wall_s']}s", flush=True)
            n = len(res)
            if not n:
                continue
            k = sum(r["solved"] for r in res)
            lo, hi = wilson(k, n)
            part = {p: sum(bool((r["outcome"] or {}).get("ok", {}).get(p)) and r["parts"] > 0 for r in res)
                    for p in ("culprit", "motive", "hideout")}
            row = {**over, "policy": pol, "n": n, "solved": k, "ci": (round(lo, 2), round(hi, 2)),
                   "parts_mean": mean([r["parts"] for r in res]), "part_correct": part,
                   "cost": sum(r["inference"]["cost"] for r in res),
                   "tokens_in": sum(r["inference"]["tokens_in"] for r in res),
                   "tokens_out": sum(r["inference"]["tokens_out"] for r in res),
                   "calls": sum(r["inference"]["calls"] for r in res),
                   "fallbacks": sum(r["inference"]["fallbacks"] for r in res),
                   "wall_s": sum(r["wall_s"] for r in res)}
            # end-to-end latency: real seconds per case (headless) and simulated hours until the answer
            walls = sorted(r["wall_s"] for r in res)
            sims = sorted((r["minutes"] if a.mode == "solo" else (r["outcome"] or {}).get("minute", r["minutes"])) / 60
                          for r in res)
            pct = lambda xs, q: xs[min(len(xs) - 1, int(q * len(xs)))]  # noqa: E731
            row.update({"wall_s_mean": mean(walls), "wall_s_p50": pct(walls, 0.5), "wall_s_p90": pct(walls, 0.9),
                        "sim_h_mean": mean(sims), "sim_h_p50": pct(sims, 0.5), "sim_h_p90": pct(sims, 0.9)})
            if a.mode == "solo":
                row["visits_mean"] = mean([r["visits"] for r in res])
                row["minutes_mean"] = mean([r["minutes"] for r in res])
                row["forced"] = sum(bool((r["outcome"] or {}).get("forced")) for r in res)
            else:
                row["quorum"] = sum(bool(r["outcome"]["quorum"]) for r in res)
                row["ticks_mean"] = mean([r["ticks"] for r in res])
                row["plurality_parts_mean"] = mean([r["outcome"]["plurality_parts"] for r in res])
            rows.append(row)
            label = " ".join(f"{k}={v}" for k, v in over.items())
            extra = (f"visits {row['visits_mean']:.1f}" if a.mode == "solo"
                     else f"quorum {row['quorum']}/{n} ticks {row['ticks_mean']:.1f}")
            print(f"{label:24s} {pol:7s} solved {k}/{n} [{lo:.2f},{hi:.2f}] parts {row['parts_mean']:.2f}/3 "
                  f"{part} {extra} cost ${row['cost']:.4f} | real s p50 {row['wall_s_p50']:.1f} p90 "
                  f"{row['wall_s_p90']:.1f} | sim h p50 {row['sim_h_p50']:.1f} p90 {row['sim_h_p90']:.1f}", flush=True)
    with open(os.path.join(out_dir, "table.json"), "w") as f:
        json.dump(rows, f, indent=1, default=str)
    with open(os.path.join(out_dir, "episodes.json"), "w") as f:
        json.dump(episodes, f, default=str)
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
