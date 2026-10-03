"""Benchmark table from batch CSVs, with the same columns as the Holmes benchmark.

    python3 -m cpudebug.report docs/bench_a.csv docs/bench_b.csv [--md out.md]
"""
import argparse
import csv
import math

from .batch import SETTINGS


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return 0.0
    i = min(len(xs) - 1, max(0, int(math.ceil(q * len(xs))) - 1))
    return xs[i]


def table(rows):
    T = lambda v: str(v).lower() == "true"
    order = [k for k in SETTINGS if any(r["setting"] == k for r in rows)]
    out = ["| Setting | Solved (95% CI) | Block / signal / type / fix | Case time p50 / p90 | Ran to deadline | "
           "Real time p50 / p90 | Calls / case | Cost / case | Wrong quorums |",
           "|---|---|---|---|---|---|---|---|---|"]
    for k in order:
        rs = [r for r in rows if r["setting"] == k]
        n = len(rs)
        solved = sum(T(r["fix_ok"]) for r in rs)
        lo, hi = wilson(solved, n)
        parts = " / ".join(str(sum(T(r[c]) for r in rs)) for c in ("block_ok", "location_ok", "type_ok", "fix_ok"))
        sim = [float(r["sim_hours"]) for r in rs]
        wall = [float(r["wall_s"]) for r in rs]
        calls = sum(int(r["calls"]) for r in rs) / n
        cost = sum(float(r["cost_usd"]) for r in rs) / n
        dl = sum(T(r["ran_to_deadline"]) for r in rs)
        wq = sum(T(r["wrong_quorum"]) for r in rs)
        cost_s = "free" if cost == 0 and calls == 0 else f"${cost:.4f}" if cost < 0.01 else f"${cost:.3f}"
        out.append(f"| {SETTINGS[k][0]} | {solved}/{n} ({lo:.2f}-{hi:.2f}) | {parts} | {pct(sim, .5):.1f} h / "
                   f"{pct(sim, .9):.1f} h | {dl} | {pct(wall, .5):.1f} s / {pct(wall, .9):.1f} s | {calls:.0f} | "
                   f"{cost_s} | {wq if SETTINGS[k][1]['mode'] == 'swarm' else '-'} |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(prog="python3 -m cpudebug.report")
    ap.add_argument("csv", nargs="+")
    ap.add_argument("--md")
    a = ap.parse_args()
    rows = []
    for p in a.csv:
        with open(p) as f:
            rows += list(csv.DictReader(f))
    t = table(rows)
    total = sum(float(r["cost_usd"]) for r in rows)
    t += f"\n\nTotal spend: ${total:.2f} over {len(rows)} runs."
    print(t)
    if a.md:
        with open(a.md, "w") as f:
            f.write(t + "\n")


if __name__ == "__main__":
    main()
