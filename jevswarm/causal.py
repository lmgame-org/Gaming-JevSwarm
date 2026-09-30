"""Causal propagation check: branch at the first local escape.

For each seed:
  1. Source: run a live controlled episode until some fish first applies ESCAPE after the attack begins
     (the witness w, at decision barrier K).
  2. Branch A (permit): replay the recorded prefix through barrier K exactly, then continue live.
  3. Branch B (suppress): identical, except w's action at K is replaced by CONTINUE for that one interval.
Both branches share the world seed, the predator schedule and every random stream, so they are matched.
Outcome: over the next H seconds, responses among fish that have NOT directly seen a predator:
  - naive fish that reached fast-swim speed (> cruise + 1 BL/s) without ever seeing a predator
  - bursts they applied (BURST_*, the only fast action available without a visible predator)
  - evaluator-detected indirect responses (turn >= 30 deg or speed +1 BL/s within 0.5 s after a visible cue)
Trajectories diverge after the branch, so this complements, not replaces, observational visibility paths.

  python3 -m jevswarm.causal --policy jev --seeds 5
"""
import argparse
import json
import os
import shutil
import tempfile
import time

import numpy as np

from .batch import ci
from .engine import RUNS, Engine


class Branch:
    def __init__(self, table, until_k, override=None):
        self.table = table          # (fish, k) -> applied id from the source run
        self.until_k = until_k      # replay barriers k <= until_k
        self.override = override or {}

    def get(self, i, k, cands):
        if (i, k) in self.override:
            cid = self.override[(i, k)]
            return (cid, "branch") if cid in cands else None
        if k <= self.until_k:
            cid = self.table.get((i, k))
            if cid in cands:
                return cid, "replay"
        return None


def run_source(cfg, root):
    e = Engine(cfg, realtime=False, run_root=root)
    found = None
    while e.t < e.cfg["episode_s"] and e.world.alive.any():
        n0 = len(e.applied_log)
        e.tick()
        if e.attack_started:
            for (t, i, cid, src) in e.applied_log[n0:]:
                if cid.startswith("ESCAPE") and src == "policy":
                    found = (i, e.barrier_k - 1, t)
                    break
        if found:
            break
    e.finish()
    e.close()
    table = {}
    with open(os.path.join(e.run_dir, "decisions.jsonl")) as f:
        for line in f:
            d = json.loads(line)
            table[(d["fish"], d["k"])] = d["applied"]
    return found, table


def run_branch(cfg, table, K, witness, suppress, horizon, root):
    e = Engine(cfg, realtime=False, run_root=root, log=False)
    e.branch = Branch(table, K, {(witness, K): "CONTINUE"} if suppress else None)
    t_branch = None
    fast_naive = set()
    while e.world.alive.any():
        e.tick()
        if t_branch is None and e.barrier_k > K:
            t_branch = e.t
            seen_at_branch = e.evaluator.seen_pred.copy()
            resp0 = len(e.evaluator.responses)
        if t_branch is not None:
            w_ = e.world
            fast = np.nonzero(w_.alive & (w_.fish_v > e.cfg["cruise"] + 1.0) & ~e.evaluator.seen_pred)[0]
            fast_naive.update(int(j) for j in fast if j != witness and not seen_at_branch[j])
            if e.t >= t_branch + horizon:
                break
    ev = e.evaluator
    naive = [j for j in range(e.world.n) if j != witness and not seen_at_branch[j]]
    bursts = {i for (t, i, cid, src) in e.applied_log
              if t > t_branch and cid.startswith("BURST") and i in naive and not ev.seen_pred[i]}
    e.close()
    return {"naive_fish": len(naive), "naive_bursters": len(bursts), "naive_fast": len(fast_naive),
            "indirect_responses": len(ev.responses) - resp0,
            "witness_action_at_K": e.last_decision[witness]["applied"] if e.last_decision[witness] else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="jev")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--seed0", type=int, default=1)
    ap.add_argument("--scenario", default="flank")
    ap.add_argument("--horizon", type=float, default=3.0)
    a = ap.parse_args()
    out = os.path.join(RUNS, f"causal_{time.strftime('%Y%m%d-%H%M%S')}_{a.policy}")
    os.makedirs(out, exist_ok=True)
    rows = []
    for s in range(a.seed0, a.seed0 + a.seeds):
        cfg = {"policy": a.policy, "seed": s, "scenario": a.scenario, "mode": "controlled"}
        tmp = tempfile.mkdtemp(dir=out)
        found, table = run_source(dict(cfg), tmp)
        if not found:
            print(f"seed {s}: no local escape observed; skipped")
            continue
        w, K, t = found
        A = run_branch(dict(cfg), table, K, w, False, a.horizon, tmp)
        B = run_branch(dict(cfg), table, K, w, True, a.horizon, tmp)
        rows.append({"seed": s, "witness": w, "K": K, "t": round(t, 2), "permit": A, "suppress": B})
        print(f"seed {s}: witness {w} at t={t:.1f}s  naive bursters permit {A['naive_bursters']} vs suppress "
              f"{B['naive_bursters']}  naive fast {A['naive_fast']} vs {B['naive_fast']}  indirect responses {A['indirect_responses']} vs {B['indirect_responses']}",
              flush=True)
        shutil.rmtree(tmp, ignore_errors=True)
    d1 = [r["permit"]["naive_bursters"] - r["suppress"]["naive_bursters"] for r in rows]
    d2 = [r["permit"]["indirect_responses"] - r["suppress"]["indirect_responses"] for r in rows]
    d3 = [r["permit"]["naive_fast"] - r["suppress"]["naive_fast"] for r in rows]
    m3, h3, _ = ci(d3)
    m1, h1, n = ci(d1)
    m2, h2, _ = ci(d2)
    summary = {"policy": a.policy, "horizon_s": a.horizon, "episodes": n,
               "naive_bursters_diff": {"mean": m1, "ci95": h1},
               "indirect_responses_diff": {"mean": m2, "ci95": h2},
               "naive_fast_diff": {"mean": m3, "ci95": h3}, "rows": rows}
    with open(os.path.join(out, "causal.json"), "w") as f:
        json.dump(summary, f, indent=1)
    fmt = lambda m, h: "–" if m is None else f"{m:+.2f}" + (f" ± {h:.2f}" if h else "")  # noqa: E731
    print(f"\npermit - suppress over {a.horizon}s, {n} episodes:")
    print(f"  naive bursters      {fmt(m1, h1)}")
    print(f"  naive fast swimmers {fmt(m3, h3)}")
    print(f"  indirect responses  {fmt(m2, h2)}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
