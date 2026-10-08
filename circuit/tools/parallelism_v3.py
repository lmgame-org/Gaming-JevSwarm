"""Oracle measurements on the v3 chip (no noise, no liars): how many probes a perfect tracer needs.

    cd circuit && PYTHONPATH=.:../common python3 tools/parallelism_v3.py --seeds 1-100 [--out docs/parallelism_v3_100seeds.csv]
  serial_probes   one exact probe at a time from the chip's start points (signatures first), to the first probe that
                  catches a bug site (block, wire or signature fabric)
  layered_rounds  rounds of probing the whole frontier at once (the ideal-parallel depth), and the probes it spends
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(os.path.dirname(HERE)), "common")]

from cpudebug.chip import ChipCase  # noqa: E402
from cpudebug.config import coerce  # noqa: E402


def trace_once(c, bugs, width, cap=3000):
    cleared, stopped, probes, rounds = {}, set(), 0, 0
    while probes < cap:
        fr = c.frontier(cleared, stopped, limit=width)
        if not fr:
            return None, probes
        rounds += 1
        for _, b, cy in fr:
            p = c.check(b, cy)
            probes += 1
            if p["mismatch"]:
                if b in bugs:
                    return rounds, probes
                stopped.add(b)
            else:
                for r in p["rows"]:
                    cleared.setdefault(b, set()).add(r["cycle"])
    return None, probes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1-100")
    ap.add_argument("--out")
    ap.add_argument("overrides", nargs="*")
    a = ap.parse_args()
    over = dict(kv.split("=", 1) for kv in a.overrides)
    lo, hi = map(int, a.seeds.split("-"))
    rows = []
    for s in range(lo, hi + 1):
        c = ChipCase(coerce(dict(over, seed=s, tier="v3", noise=0.0)))
        bugs = {f["block"] for f in c.faults}
        _, serial = trace_once(c, bugs, 1)
        rounds, lp = trace_once(c, bugs, 60)
        rows.append({"seed": s, "n_bugs": len(bugs), "wire": int(any(b.startswith("L:") for b in bugs)),
                     "serial_probes": serial, "layered_rounds": rounds, "layered_probes": lp,
                     "slice_nodes": sum(len(v) for v in c.slice_cycles().values())})
        print(rows[-1], flush=True)
    if a.out:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
