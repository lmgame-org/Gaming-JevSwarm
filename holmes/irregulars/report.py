"""Summarise batch folders into a per-case CSV and a markdown table.

  python3 -m irregulars.report runs/batch_A runs/batch_B ... --csv out.csv --md out.md

Per case: solved, each part, simulated hours until the answer (and whether it ran to the deadline), real seconds
from case start to final answer (headless), model calls, tokens and dollars. Per setting: solved with a Wilson 95%
interval, p50/p90 of both latencies, and cost per case.
"""
import argparse
import csv
import json
import os

from .batch import wilson


def label(cfg, summary):
    name = _label(cfg)
    return name + " · Holmesian" if cfg.get("difficulty") == "holmesian" else name


def _label(cfg):
    mode = cfg.get("mode", "solo")
    names = {"chat": "gpt-6-astra", "jev": "Jev", "rule": "heuristic", "random": "random"}
    if mode == "solo":
        return "Solo detective · " + names[cfg["policy"]]
    sp = cfg.get("swarm_policy", "jev")
    km = f"{cfg.get('comm_range', 100) / 100:g} km"
    if sp == "baker_street":
        holmes = "gpt-6-astra Holmes" if cfg.get("holmes", "chat") == "chat" else "counting-heuristic Holmes"
        return f"Baker Street Irregulars · {holmes}, {names.get(cfg.get('boy_policy', 'jev'), 'Jev')} boys"
    if sp in ("hybrid", "hybrid_genius"):
        return f"Swarm Detectives · {'hybrid' if sp == 'hybrid' else 'hybrid + Yard genius'} · {km}"
    return f"Swarm Detectives · {names.get(sp, sp)} swarm · {km}"


def rows_from(folder):
    with open(os.path.join(folder, "episodes.json")) as f:
        eps = json.load(f)
    out = []
    for e in eps:
        c, s = e["cfg"], e["summary"]
        o, i = s["outcome"] or {}, s["inference"]
        mode = c.get("mode", "solo")
        answered = bool(o.get("quorum")) if mode == "swarm" and c.get("swarm_policy") != "baker_street" else True
        ok = o.get("ok") or {}
        if mode == "solo":
            sim, deadline = s["minutes"] / 60, bool(o.get("forced"))
        elif c.get("swarm_policy") == "baker_street":
            sim, deadline = o["minute"] / 60, bool(o.get("forced"))
        else:
            sim, deadline = o["minute"] / 60, not o.get("quorum")
        out.append({"setting": label(c, s), "seed": c["seed"], "solved": int(s["solved"]),
                    "culprit": int(answered and bool(ok.get("culprit"))), "motive": int(answered and bool(ok.get("motive"))),
                    "hideout": int(answered and bool(ok.get("hideout"))), "sim_hours": round(sim, 2),
                    "ran_to_deadline": int(deadline), "real_seconds": s.get("wall_s"), "model_calls": i["calls"],
                    "tokens_in": i["tokens_in"], "tokens_out": i["tokens_out"], "cost_usd": round(i["cost"], 5),
                    "decisions": sum(i["by_source"].values()), "fallbacks": i["by_source"].get("fallback", 0),
                    "concurrency": c.get("concurrency", 32), "batch": os.path.basename(folder)})
    return out


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def summarise(rows):
    by = {}
    for r in rows:
        by.setdefault(r["setting"], []).append(r)
    table = []
    for name, rs in by.items():
        n = len(rs)
        k = sum(r["solved"] for r in rs)
        lo, hi = wilson(k, n)
        table.append({"setting": name, "n": n, "solved": k, "ci": (lo, hi),
                      "parts": {p: sum(r[p] for r in rs) for p in ("culprit", "motive", "hideout")},
                      "sim_p50": pct([r["sim_hours"] for r in rs], 0.5), "sim_p90": pct([r["sim_hours"] for r in rs], 0.9),
                      "deadline": sum(r["ran_to_deadline"] for r in rs),
                      "real_p50": pct([r["real_seconds"] for r in rs], 0.5),
                      "real_p90": pct([r["real_seconds"] for r in rs], 0.9),
                      "calls": sum(r["model_calls"] for r in rs) / n,
                      "tokens": sum(r["tokens_in"] + r["tokens_out"] for r in rs) / n,
                      "fallback_pct": 100 * sum(r["fallbacks"] for r in rs) / max(1, sum(r["decisions"] for r in rs)),
                      "cost_case": sum(r["cost_usd"] for r in rs) / n, "cost_total": sum(r["cost_usd"] for r in rs),
                      "seeds": sorted(r["seed"] for r in rs)})
    return table


def markdown(table):
    lines = ["| Setting | Solved (95% CI) | Culprit / motive / hideout | Sim time p50 / p90 | Ran to deadline | "
             "Real time p50 / p90 | Calls / case | Cost / case | Heuristic fallbacks |",
             "|---|---|---|---|---|---|---|---|---|"]
    for t in table:
        lo, hi = t["ci"]
        p = t["parts"]
        lines.append(f"| {t['setting']} | {t['solved']}/{t['n']} ({lo:.2f}-{hi:.2f}) | {p['culprit']} / {p['motive']} / "
                     f"{p['hideout']} | {t['sim_p50']:.1f} h / {t['sim_p90']:.1f} h | {t['deadline']} | "
                     f"{t['real_p50']:.1f} s / {t['real_p90']:.1f} s | {t['calls']:.0f} | "
                     f"{'free' if t['cost_case'] == 0 else '$%.3f' % t['cost_case']} | {t['fallback_pct']:.2f}% |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(prog="python3 -m irregulars.report")
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--csv", default="")
    ap.add_argument("--md", default="")
    a = ap.parse_args()
    rows = [r for f in a.folders for r in rows_from(f)]
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    table = summarise(rows)
    md = markdown(table)
    if a.md:
        with open(a.md, "w") as f:
            f.write(md + "\n")
    print(md)
    print(f"\ntotal cost ${sum(t['cost_total'] for t in table):.2f}")
    for t in table:
        if t["n"] < 20:
            missing = sorted(set(range(1, 21)) - set(t["seeds"]))
            print(f"{t['setting']}: missing seeds {missing}")


if __name__ == "__main__":
    main()
