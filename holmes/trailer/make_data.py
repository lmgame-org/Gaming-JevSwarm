"""Collect what the trailer shows from the real benchmark runs of one case:
python3 trailer/make_data.py --seed 17 --batches runs/batch_A runs/batch_B ...

The footage is the actual runs from the 100-case benchmark: gpt-6-astra alone (its route and its own notes), gpt-6-astra
as Holmes with twelve Jev boys (positions, the reports reaching 221B, Holmes's orders), and the 100-boy Jev swarm
(positions, shouts, votes). The casebook numbers come from the same batches (--table)."""
import argparse
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "trailer_data.json")
KEY = {"trait", "alibi", "motive", "hide_district", "hide_type", "hide_found"}
PART = {"trait": "culprit", "alibi": "culprit", "motive": "motive", "hide_district": "hideout", "hide_type": "hideout",
        "hide_found": "hideout"}


def find(batches, pattern):
    hits = [d for b in batches for d in glob.glob(os.path.join(b, pattern))]
    if not hits:
        raise SystemExit(f"no run matches {pattern}")
    return hits[0]


def jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def wall_of(run_dir):
    """Real seconds the run took, from its batch's episodes.json."""
    path = os.path.join(os.path.dirname(run_dir), "episodes.json")
    if not os.path.exists(path):  # batch still running
        return None
    eps = json.load(open(path))
    cfg = json.load(open(os.path.join(run_dir, "config.json")))["cfg"]
    pol = cfg.get("policy") if cfg["mode"] == "solo" else cfg["swarm_policy"]
    for e in eps:
        c = e["cfg"]
        if c["seed"] == cfg["seed"] and (c.get("policy") if c["mode"] == "solo" else c.get("swarm_policy")) == pol:
            return e["summary"]["wall_s"]
    return None


def short(s, n=96):
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def solo(run_dir, leads):
    steps = jsonl(os.path.join(run_dir, "decisions.jsonl"))
    summ = json.load(open(os.path.join(run_dir, "summary.json")))
    case = json.load(open(os.path.join(run_dir, "case.json")))
    stops = [{"at": case["map"]["baker"], "minute": 0.0, "note": short(steps[0].get("note") or "", 150)}]
    for a, b in zip(steps, steps[1:] + [None]):
        if a["action"].startswith("VISIT_"):
            addr = a["action"][6:]
            lead = leads[addr]
            stops.append({"at": addr, "minute": b["minute"] if b else summ["minutes"],
                          "note": short((b or {}).get("note") or "", 150), "clue": short(lead["text"]),
                          "key": lead["fact"][0] in KEY and not lead["lie"],
                          "part": PART.get(lead["fact"][0]) if not lead["lie"] else None})
    o = summ["outcome"] or {}
    return {"stops": stops, "minutes": summ["minutes"], "solved": summ["solved"], "ok": o.get("ok"),
            "visits": summ["visits"], "budget": json.load(open(os.path.join(run_dir, "config.json")))["cfg"]["visit_budget"],
            "wall": wall_of(run_dir)}


def baker(run_dir):
    track = jsonl(os.path.join(run_dir, "track.jsonl"))
    summ = json.load(open(os.path.join(run_dir, "summary.json")))
    orders = []
    for e in jsonl(os.path.join(run_dir, "events.jsonl")):
        if e["kind"] == "hub":
            note = e["detail"].split(". ", 2)[-1] if e["detail"].count(". ") >= 2 else e["detail"]
            orders.append({"minute": e["t"], "text": short(note, 170)})
    ticks = [{"boys": [b[:2] for b in t["boys"]], "w": t["w"], "reports": t["reports"], "wall": t["wall"],
              "minute": t["minute"],
              "new": [{"text": short(r["text"]), "at": r["address"], "part": PART[r["kind"]]} for r in t["new"]
                      if r["kind"] in KEY and not r.get("fake")][:3]}
             for t in track]
    o = summ["outcome"]
    return {"ticks": ticks, "orders": orders, "solved": summ["solved"], "ok": o["ok"], "minute": o["minute"],
            "wall": wall_of(run_dir) or track[-1]["wall"]}


def swarm(run_dir):
    track = jsonl(os.path.join(run_dir, "track.jsonl"))
    summ = json.load(open(os.path.join(run_dir, "summary.json")))
    o = summ["outcome"]
    want = [o["culprit"], o["motive"], o["hideout"]]
    ticks = []
    for t in track:
        parts = [sum(int(v == w) for v, w in zip(vt, want)) for vt in t["votes"]]
        ticks.append({"boys": t["boys"], "parts": parts, "shares": t["shares"], "wall": t["wall"], "minute": t["minute"],
                      "truth_votes": sum(1 for p in parts if p == 3),
                      "per": [sum(1 for vt in t["votes"] if vt[k] == want[k]) for k in range(3)]})
    return {"ticks": ticks, "solved": summ["solved"], "ok": o["ok"], "quorum": o["quorum"], "minute": o["minute"],
            "wall": wall_of(run_dir) or track[-1]["wall"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--batches", nargs="+", required=True)
    ap.add_argument("--table", default="", help="json with the casebook numbers")
    a = ap.parse_args()
    s = a.seed
    solo_dir = find(a.batches, f"*_solo_chat_s{s}")
    baker_dir = find(a.batches, f"*_swarm_baker_street_chat_s{s}")
    swarm_dir = find(a.batches, f"*_swarm_jev_s{s}")
    case = json.load(open(os.path.join(baker_dir, "case.json")))
    m = case["map"]
    data = {
        "seed": s,
        "map": {"addresses": [[x["x"], x["y"]] for x in m["addresses"]], "ids": [x["id"] for x in m["addresses"]],
                "edges": m["edges"], "districts": m["districts"], "thames": m["thames"], "baker": m["baker"],
                "scene": m["scene"], "hideouts": list(m["hideouts"].values())},
        "truth": case["secret"]["truth_names"],
        "solo": solo(solo_dir, case["leads"]), "baker": baker(baker_dir), "swarm": swarm(swarm_dir),
        "table": json.load(open(a.table)) if a.table else None,
    }
    with open(OUT, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(OUT, "solo solved", data["solo"]["solved"], "baker solved", data["baker"]["solved"],
          "swarm quorum", data["swarm"]["quorum"], "solved", data["swarm"]["solved"])


if __name__ == "__main__":
    main()
