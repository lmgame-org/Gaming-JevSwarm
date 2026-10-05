"""The ideal-parallel baseline: unit-test every block on the bench, all at once, with the hardened noise.

Round 1: every untrusted block x 4 vector kinds (corner, sweep, boundary, random), in parallel.
Round 2: re-drive every (block, kind) that mismatched; a vector is confirmed when it reads the same wrong value twice
(a glitch rarely repeats). Blocks are ranked by confirmed vectors; a block needs two (one repeated glitch is one row). Answer: up to two confirmed blocks, each with the fault that best explains its rows.
No waveform, no back-trace, no upstream context: each probe needs only the block and its spec.

    cd circuit && PYTHONPATH=.:../common python3 tools/bench_sweep.py --seeds 1-100 [--out docs/bench_sweep_100seeds.csv]
"""
import argparse
import csv
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(os.path.dirname(HERE)), "common")]

from cpudebug.case import Case  # noqa: E402
from cpudebug.config import coerce  # noqa: E402
from cpudebug.kb import fault_answer  # noqa: E402

KINDS = ("corner", "sweep", "boundary", "random")


def run(seed):
    c = Case(coerce({"seed": seed}))
    rng = random.Random(f"sweep-{seed}")
    blocks = [b.name for b in c.blocks if not b.trusted]
    probes, flagged, rows = 0, {}, {}
    for b in blocks:
        for k in KINDS:
            p = c.drive(b, k, random.Random(rng.random()))
            probes += 1
            rows.setdefault(b, []).extend(p["rows"])
            if p["mismatch"]:
                flagged.setdefault(b, []).append((k, p))
    score = {}
    for b, hits in flagged.items():
        for k, p1 in hits:
            p2 = c.drive(b, k, random.Random(rng.random()))
            probes += 1
            rows[b].extend(p2["rows"])
            for r1, r2 in zip(p1["rows"], p2["rows"]):
                if not r1["ok"] and not r2["ok"] and json.dumps(r1["out"], sort_keys=True) == json.dumps(r2["out"], sort_keys=True):
                    score[b] = score.get(b, 0) + 1
    # a real bug repeats on several vectors; a repeated glitch is a single row. Rank by repeated vectors.
    confirmed = sorted(score, key=lambda b: -score[b])
    confirmed = [b for b in confirmed if score[b] >= 2] or confirmed[:1]
    fixes = []
    for b in confirmed[:2]:
        fs = c.fit(b, rows[b])
        if fs:
            fixes.append(fault_answer(b, fs[0]))
    g = c.grade({"fixes": fixes})
    bugs = {f["block"] for f in c.faults}
    return {"seed": seed, "n_bugs": len(bugs), "probes": probes, "rounds": 2, "flagged_round1": len(flagged),
            "confirmed": len(confirmed), "false_confirmed": len([b for b in confirmed if b not in bugs]),
            "block_ok": int(g["block_ok"]), "fix_ok": int(g["fix_ok"])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1-100")
    ap.add_argument("--out")
    a = ap.parse_args()
    lo, hi = map(int, a.seeds.split("-"))
    rows = []
    for s in range(lo, hi + 1):
        rows.append(run(s))
        print(rows[-1], flush=True)
    if a.out:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
