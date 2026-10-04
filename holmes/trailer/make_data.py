"""Collect everything the trailer shows from real (free) runs and real case files: python3 trailer/make_data.py"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import irregulars  # noqa: E402,F401
from irregulars.case import Case  # noqa: E402
from irregulars.config import coerce  # noqa: E402
from irregulars.engine import Engine  # noqa: E402

GENIUS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs",
                      "batch_20261002-154711_solo_62084")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trailer_data.json")


def track(cfg):
    e = Engine(cfg, realtime=False, log=False)
    ticks = []
    f = e.frame(full=True)
    m = f["case"]["map"]
    while True:
        f = e.frame()
        t = {"boys": [[round(b[1]), round(b[2])] for b in f["irregulars"]]}
        if e.squad:
            w = f["hq"]["wiggins"]
            t["w"] = [round(w["x"]), round(w["y"])] if w else None
            t["reports"] = f["hq"]["reports"]
        else:
            truth = e.case.truth_ids()
            want = (truth["culprit"], truth["motive"], truth["hideout"])
            t["truth_votes"] = sum(1 for b in f["irregulars"] if (b[3], b[4], b[5]) == want)
            t["parts"] = [sum(int(v == w) for v, w in zip((b[3], b[4], b[5]), want)) for b in f["irregulars"]]
            t["shares"] = [[round(x), round(y)] for _, x, y in f["shares"]][:60]
        ticks.append(t)
        if e.ended:
            break
        e.step()
    e.pool.shutdown(wait=False)
    return m, ticks, e.summary


def main():
    m, baker, s1 = track({"mode": "swarm", "swarm_policy": "baker_street", "holmes": "rule", "boy_policy": "rule",
                          "n_irregulars": 12, "seed": 3})
    _, swarm, s2 = track({"mode": "swarm", "swarm_policy": "rule", "comm_range": 200, "seed": 3})
    # the lone genius: gpt-6-astra's actual route on case 3 in the 2 October benchmark (it solved it)
    run = [d for d in os.listdir(GENIUS) if d.endswith("_chat_s3")][0]
    steps = [json.loads(line) for line in open(os.path.join(GENIUS, run, "decisions.jsonl"))]
    summ = json.load(open(os.path.join(GENIUS, run, "summary.json")))
    case_map = json.load(open(os.path.join(GENIUS, run, "case.json")))["map"]
    stops = [[case_map["baker"], 0.0]]
    for a, b in zip(steps, steps[1:] + [None]):
        if a["action"].startswith("VISIT_"):
            stops.append([a["action"][6:], b["minute"] if b else summ["minutes"]])
    solo = {"stops": stops, "minutes": summ["minutes"], "solved": summ["solved"], "visits": summ["visits"]}
    c = Case(coerce({"seed": 1, "difficulty": "holmesian"}))
    frame = [c.leads[a]["text"] for a in c.frame_addrs]
    bribe = [l["text"] for l in c.leads.values() if l["fact"][0] == "bribe"]
    planted = c.leads[c.scene]["text"]
    culprit, framed = c.suspect(c.truth["culprit"]), c.suspect(c.framed)
    data = {
        "map": {"addresses": [[a["x"], a["y"]] for a in m["addresses"]],
                "ids": [a["id"] for a in m["addresses"]],
                "edges": m["edges"], "districts": m["districts"], "thames": m["thames"],
                "baker": m["baker"], "scene": m["scene"], "hideouts": list(m["hideouts"].values())},
        "baker": baker, "swarm": swarm, "solo": solo,
        "baker_result": s1["solved"], "swarm_result": s2["solved"],
        "holmesian": {"culprit": culprit["name"], "framed": framed["name"], "frame": frame, "bribe": bribe,
                      "planted": planted,
                      # gpt-6-astra as Holmes, Holmesian case 1, 3 October run 2 (runs/batch_20261003-163912_swarm_92155)
                      "holmes": "Wiggins, Pargeter's servants supply both his alibi and evidence against Leopold; "
                                "the dry snuff-box suggests planting. Pargeter merits suspicion, not accusation."},
    }
    with open(OUT, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(OUT, len(baker), "baker ticks", len(swarm), "swarm ticks", "solved", s1["solved"], s2["solved"])
    print(json.dumps(data["holmesian"], indent=1))


if __name__ == "__main__":
    main()
