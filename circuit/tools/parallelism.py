"""How divide-and-conquer friendly is a case? Oracle measurements on hardened cases (no measurement noise, no liars).

    cd circuit && PYTHONPATH=.:../common python3 tools/parallelism.py --seeds 1-100 [--out docs/parallelism.csv]

For each case:
  slice_blocks / slice_nodes  untrusted blocks and block-cycles on the back-slice of the failure
  bench_round      one round of bench drives, every untrusted block x 4 vector kinds, all in parallel: does any drive of
                   a buggy block mismatch? (fully local: needs no waveform, no upstream context)
  one_check_round  one round, one check per untrusted block at its latest slice cycle: does a bug block mismatch?
  cover_probes     checks needed to cover every slice node of every untrusted block once (one parallel round)
  cover_hit        does that exhaustive round catch every bug?
  layers           a perfect back-tracer that checks its whole frontier in parallel each round: rounds until it
                   reaches a bug block-cycle that mismatches (the sequential depth), and the probes it spends
  serial           the same tracer one probe at a time (the cone tracer with exact checks): probes to the first catch
"""
import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(os.path.dirname(HERE)), "common")]

from cpudebug.case import Case  # noqa: E402
from cpudebug.config import coerce  # noqa: E402

KINDS = ("corner", "sweep", "boundary", "random")


def layered(c, bugs):
    """Frontier BFS from the start nodes over untrusted block-cycles; trusted nodes pass through free."""
    seen, frontier, probes = set(), set(), 0
    todo = list(c.starts)
    # expand through trusted nodes to the first untrusted layer
    def expand(nodes):
        out, stack = set(), list(nodes)
        while stack:
            n = stack.pop()
            for p in c.preds(n):
                if p in seen:
                    continue
                seen.add(p)
                if c.by[p[0]].trusted:
                    stack.append(p)
                else:
                    out.add(p)
        return out
    for s in todo:
        seen.add(s)
    frontier = {s for s in todo if not c.by[s[0]].trusted} | expand([s for s in todo if c.by[s[0]].trusted])
    rnd = 0
    while frontier and rnd < 400:
        rnd += 1
        probes += len(frontier)
        hit = [n for n in frontier if n[0] in bugs and not c._row(c.by[n[0]], n[1], None)["ok"]]
        if hit:
            return rnd, probes
        frontier = expand(frontier)
    return None, probes


def serial(c, bugs, cap=2000):
    cleared, probes = {}, 0
    while probes < cap:
        fr = c.frontier(cleared, set(), limit=1)
        if not fr:
            return None
        _, b, cy = fr[0]
        p = c.check(b, cy)
        probes += 1
        if p["mismatch"] and b in bugs:
            return probes
        for r in p["rows"]:
            cleared.setdefault(b, set()).add(r["cycle"])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1-100")
    ap.add_argument("--out")
    a = ap.parse_args()
    lo, hi = map(int, a.seeds.split("-"))
    rows = []
    for s in range(lo, hi + 1):
        cfg = coerce({"seed": s, "noise": 0.0})
        c = Case(cfg)
        bugs = {f["block"] for f in c.faults}
        sl = c.slice_cycles()
        untrusted = [b.name for b in c.blocks if not b.trusted]
        bench = all(any(c.drive(b, k)["mismatch"] for k in KINDS) for b in bugs)
        one = any(c.check(b, sl[b][-1])["mismatch"] for b in bugs if b in sl)
        cover = 0
        caught = set()
        for b in sl:
            cyc = sl[b]
            i = 0
            while i < len(cyc):
                lo_, hi_ = c.window_of(cyc[i])
                cover += 1
                if b in bugs and c.check(b, cyc[i])["mismatch"]:
                    caught.add(b)
                while i < len(cyc) and cyc[i] <= hi_:
                    i += 1
        rounds, lprobes = layered(c, bugs)
        rows.append({"seed": s, "test": c.test["name"], "cycles": c.n, "n_bugs": len(bugs),
                     "rare": int(any(f.get("trigger") for f in c.faults)),
                     "untrusted_blocks": len(untrusted), "slice_blocks": len(sl),
                     "slice_nodes": sum(len(v) for v in sl.values()),
                     "bench_round_probes": len(untrusted) * len(KINDS), "bench_round_hit": int(bench),
                     "one_check_round_hit": int(one), "cover_probes": cover, "cover_hit": int(caught == bugs),
                     "layers_rounds": rounds, "layers_probes": lprobes, "serial_probes": serial(c, bugs)})
        print(rows[-1], flush=True)
    if a.out:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
