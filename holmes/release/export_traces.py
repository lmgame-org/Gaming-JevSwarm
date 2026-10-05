"""Export the benchmark traces for the interactive site: python3 release/export_traces.py

For every case (standard seeds 1-100 and frame-up seeds 1-100) it writes release/site/data/<kind>_<seed>.json with the
three real runs: The Lone Genius (GPT6-Astra), Holmes (GPT6-Astra) + Jev Swarm, and the Jev Swarm. index.json lists
every case with its outcomes."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "trailer"))
import make_data as md  # noqa: E402

RUNS = os.path.join(ROOT, "runs")
SETS = {
    "standard": ["batch_20261004-051436_solo_71984", "batch_20261004-051436_solo_71986", "batch_20261004-051436_swarm_71985",
                 "batch_20261004-051436_swarm_71987", "batch_20261004-051436_swarm_71990"],
    "frameup": ["batch_20261004-163104_solo_30951", "batch_20261004-163104_solo_30955", "batch_20261004-163104_solo_30959",
                "batch_20261004-163104_solo_30963", "batch_20261004-163104_swarm_30952", "batch_20261004-163104_swarm_30956",
                "batch_20261004-163104_swarm_30960", "batch_20261004-163104_swarm_30964", "batch_20261004-164849_swarm_32852"],
}
OUT = os.path.join(HERE, "site", "data")


def rnd(x):
    """Trim floats so the files stay small."""
    if isinstance(x, float):
        return round(x, 1)
    if isinstance(x, list):
        return [rnd(v) for v in x]
    if isinstance(x, dict):
        return {k: rnd(v) for k, v in x.items()}
    return x


def main():
    os.makedirs(OUT, exist_ok=True)
    index = []
    for kind, batches in SETS.items():
        dirs = [os.path.join(RUNS, b) for b in batches]
        for seed in range(1, 101):
            try:
                solo_dir = md.find(dirs, f"*_solo_chat_s{seed}")
                baker_dir = md.find(dirs, f"*_swarm_baker_street_chat_s{seed}")
                swarm_dir = md.find(dirs, f"*_swarm_jev_s{seed}")
            except SystemExit:
                continue
            case = json.load(open(os.path.join(baker_dir, "case.json")))
            m = case["map"]
            data = {
                "kind": kind, "seed": seed, "brief": {"victim": case["brief"]["victim"]},
                "map": {"addresses": [[a["x"], a["y"]] for a in m["addresses"]], "ids": [a["id"] for a in m["addresses"]],
                        "edges": m["edges"], "districts": m["districts"], "thames": m["thames"], "baker": m["baker"],
                        "scene": m["scene"]},
                "truth": case["secret"]["truth_names"],
                "solo": md.solo(solo_dir, case["leads"]), "baker": md.baker(baker_dir), "swarm": md.swarm(swarm_dir),
            }
            name = f"{kind}_{seed}.json"
            with open(os.path.join(OUT, name), "w") as f:
                json.dump(rnd(data), f, separators=(",", ":"))
            index.append({"file": name, "kind": kind, "seed": seed, "solo": data["solo"]["solved"],
                          "baker": data["baker"]["solved"], "swarm": data["swarm"]["solved"],
                          "swarm_agreed": data["swarm"]["quorum"]})
    with open(os.path.join(OUT, "index.json"), "w") as f:
        json.dump(index, f, separators=(",", ":"))
    print(len(index), "cases")


if __name__ == "__main__":
    main()
