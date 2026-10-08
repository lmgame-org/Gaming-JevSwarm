"""Blind parallel sweeps on the v3 chip, under the v3 bench rules (each drive takes 3 ticks and one of 2 shared bench
slots, and covers only 4 vectors of one region), within the same 8-hour (32-tick) clock.

    cd circuit && PYTHONPATH=.:../common python3 tools/bench_sweep_v3.py --seeds 1-100 [--out docs/bench_sweep_v3_100seeds.csv]
  blind     drive logic blocks of the whole chip in random order, as many as the bench allows; confirm any mismatch
            with a second drive; answer the confirmed blocks
  sig_first read all 12 core signatures in one tick (a group can), then drive only the bad cores' logic blocks
Neither can see a wire bug: wires have no bench test.
"""
import argparse
import csv
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(os.path.dirname(HERE)), "common")]

from cpudebug.chip import ChipCase  # noqa: E402
from cpudebug.config import coerce  # noqa: E402
from cpudebug.kb import fault_answer  # noqa: E402

KINDS = ("random", "corner", "sweep", "boundary")


def sweep(c, blocks, rng, ticks):
    slots = c.cfg["bench_slots"]
    per = c.cfg["drive_ticks"]
    budget = (ticks // per) * slots
    rows, hits, used = {}, {}, 0
    for b in blocks:
        if used >= budget:
            break
        k = rng.choice(KINDS)
        p = c.drive(b, k, random.Random(rng.random()))
        used += 1
        rows.setdefault(b, []).extend(p["rows"])
        if p["mismatch"] and used < budget:
            p2 = c.drive(b, k, random.Random(rng.random()))
            used += 1
            rows[b].extend(p2["rows"])
            if any(not r1["ok"] and not r2["ok"] and json.dumps(r1["out"]) == json.dumps(r2["out"])
                   for r1, r2 in zip(p["rows"], p2["rows"])):
                hits[b] = True
    fixes = []
    for b in list(hits)[:3]:
        fs = c.fit(b, rows[b])
        if fs:
            fixes.append(fault_answer(b, fs[0]))
    return fixes, used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1-100")
    ap.add_argument("--out")
    a = ap.parse_args()
    lo, hi = map(int, a.seeds.split("-"))
    rows = []
    for s in range(lo, hi + 1):
        c = ChipCase(coerce({"seed": s, "tier": "v3"}))
        ticks = int(c.cfg["deadline_hours"] * 60 / c.cfg["tick_min"])
        logic = [b.name for b in c.blocks if not b.trusted]
        rng = random.Random(f"sw-{s}")
        rng.shuffle(logic)
        f1, u1 = sweep(c, logic, rng, ticks)
        g1 = c.grade({"fixes": f1})
        bad = [k for k in range(c.n_cores) if c.trace.core_sigs[k] != c.trace.golden.core_sigs[k]]
        inbad = [b for b in logic if c.core_of(b) in bad]
        rng2 = random.Random(f"sw2-{s}")
        rng2.shuffle(inbad)
        f2, u2 = sweep(c, inbad, rng2, ticks - 1)
        g2 = c.grade({"fixes": f2})
        rows.append({"seed": s, "n_bugs": len(c.faults), "wire_bug": int(any(f.get("wire") for f in c.faults)),
                     "blind_drives": u1, "blind_fix": int(g1["fix_ok"]), "blind_block": int(g1["block_ok"]),
                     "sig_first_drives": u2, "sig_first_fix": int(g2["fix_ok"]), "sig_first_block": int(g2["block_ok"])})
        print(rows[-1], flush=True)
    if a.out:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
