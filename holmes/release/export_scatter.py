"""Export the scatter-and-gather data behind the blog's evidence-board figure: python3 release/export_scatter.py

For every case already exported by export_traces.py it writes release/site/data/sg/<kind>_<seed>.json with, for each of
the three detectives, every first visit to an address (case minute, agent lane, address), how the evidence was gathered
(the Lone Genius's own key finds, the reports that reached Holmes, the swarm's votes), and the final accusation. It also
lists the case's key evidence and its lies, with a short label for each, so the page can pin them on an evidence board."""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "trailer"))
import export_traces as et  # noqa: E402
import make_data as md  # noqa: E402

DATA = os.path.join(HERE, "site", "data")
OUT = os.path.join(DATA, "sg")
PART = {"trait": "culprit", "alibi": "culprit", "seen": "culprit", "bribe": "culprit", "motive": "motive",
        "trace": "hideout", "hide_district": "hideout", "hide_type": "hideout", "hide_found": "hideout"}
TRAIT = {"boots": "{} boots", "hand": "{}-handed", "hair": "{} hair", "gait": "walks {}", "tobacco": "{}",
         "height": "{}", "limp": "{}"}


def surname(brief, sid):
    return brief["suspects"].get(sid, sid).split(";")[0].split(",")[0].split()[-1]


def label(fact, brief):
    kind = fact[0]
    if kind == "trait":
        return TRAIT.get(fact[1], fact[1] + ": {}").format(fact[2])
    if kind == "alibi":
        return f"alibi: {surname(brief, fact[1])}"
    if kind == "seen":
        return f"{surname(brief, fact[1])} seen {fact[3]}"
    if kind == "bribe":
        return f"bribe by {surname(brief, fact[1])}"
    if kind == "hide_found":
        return "hideout found"
    if kind == "trace":
        return " ".join(fact[1].split()[:2])
    return str(fact[1])


def names(brief):
    sus = {k: v.split(",")[0] for k, v in brief["suspects"].items()}
    mot = {k: v.split(":")[0].replace(" for an old wrong done by the victim", "") for k, v in brief["motives"].items()}
    hid = {}
    for k, v in brief["possible_hideouts"].items():
        m = re.match(r"[^,]*, ([^(]*) \(A\d+\), an? (.*)", v)
        hid[k] = f"{m.group(1).strip()}, {m.group(2)}" if m else v
    return sus, mot, hid


def accused(run_dir, brief):
    sus, mot, hid = names(brief)
    for line in open(os.path.join(run_dir, "events.jsonl")):
        e = json.loads(line)
        if e["kind"] != "accuse":
            continue
        if "accusation" in e:
            a = e["accusation"]
            ids = [a["culprit"], a["motive"], a["hideout"]]
        else:
            m = re.search(r"(S\d+)/(M\d+)/(H\d+)", e["detail"])
            if not m:
                return None
            ids = list(m.groups())
        return [sus.get(ids[0], ids[0]), mot.get(ids[1], ids[1]), hid.get(ids[2], ids[2])]
    return None


def first_visits(ticks, where, allowed=None):
    """Every address's first visit by any boy: [minute, lane, address], read off the boys' positions each quarter-hour.
    allowed(minute) gives the addresses a boy may be working at by then (Holmes's errands so far); None means any."""
    seen, out = set(), []
    for t in ticks:
        ok = allowed(t["minute"]) if allowed else None
        for lane, p in enumerate(t["boys"]):
            a = where.get((round(p[0]), round(p[1])))
            if a and a not in seen and (ok is None or a in ok):
                seen.add(a)
                out.append([t["minute"], lane, a])
    return out


def picks_solo(run_dir, brief, truth):
    """The Lone Genius's working answer after each visit: [minute, [culprit, motive, hideout], [right?, right?, right?]]."""
    sus, mot, hid = names(brief)
    out = []
    for line in open(os.path.join(run_dir, "decisions.jsonl")):
        x = json.loads(line)
        p = x.get("pick")
        if p and x.get("minute", 0) > 0:
            out.append([x["minute"], [sus.get(p["culprit"]), mot.get(p["motive"]), hid.get(p["hideout"])],
                        [p[k] == truth[k] for k in ("culprit", "motive", "hideout")]])
    return out


def holmes_plans(run_dir):
    return [x for x in map(json.loads, open(os.path.join(run_dir, "decisions.jsonl"))) if x.get("who") == "holmes"]


def picks_holmes(plans, brief, truth, tick_min):
    """Holmes's working answer at each planning session after the first (the first is a stated placeholder)."""
    sus, mot, hid = names(brief)
    return [[x["tick"] * tick_min, [sus.get(x["plan"]["culprit"]), mot.get(x["plan"]["motive"]), hid.get(x["plan"]["hideout"])],
             [x["plan"][k] == truth[k] for k in ("culprit", "motive", "hideout")]] for x in plans if x["tick"] > 0]


def main():
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for kind, batches in et.SETS.items():
        dirs = [os.path.join(et.RUNS, b) for b in batches]
        for seed in range(1, 101):
            name = f"{kind}_{seed}.json"
            if not os.path.exists(os.path.join(DATA, name)):
                continue
            d = json.load(open(os.path.join(DATA, name)))
            solo_dir = md.find(dirs, f"*_solo_chat_s{seed}")
            baker_dir = md.find(dirs, f"*_swarm_baker_street_chat_s{seed}")
            swarm_dir = md.find(dirs, f"*_swarm_jev_s{seed}")
            case = json.load(open(os.path.join(baker_dir, "case.json")))
            brief, secret, leads = case["brief"], case["secret"], case["leads"]
            key_facts = [list(f) for f in secret["key_facts"]]
            keys, lies = [], []
            for a, k in secret["lead_kinds"].items():
                fact = leads[a]["fact"]
                if leads[a]["lie"]:
                    lies.append([a, label(fact, brief)])
                elif k in PART and (list(fact) in key_facts or k == "hide_found"):
                    keys.append([a, PART[k], label(fact, brief)])
            order = {"culprit": 0, "motive": 1, "hideout": 2}
            keys.sort(key=lambda x: (order[x[1]], x[2], x[0]))
            where = {}
            for (x, y), a in zip(d["map"]["addresses"], d["map"]["ids"]):
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        where.setdefault((round(x) + dx, round(y) + dy), a)
            solo, baker, swarm = d["solo"], d["baker"], d["swarm"]
            truth = secret["truth"]
            plans = holmes_plans(baker_dir)
            tick_min = 15.0

            def errands(minute):
                return {a for x in plans if x["tick"] * tick_min < minute
                        for g in x["plan"].get("assignments") or [] for a in g.get("addresses") or []}

            # the leaderless swarm starts with one boy at every address; lanes follow where each boy stood first
            lane_of = {}
            if swarm["ticks"]:
                for lane, p in enumerate(swarm["ticks"][0]["boys"]):
                    a = where.get((round(p[0]), round(p[1])))
                    if a and a not in lane_of:
                        lane_of[a] = lane
            free = iter(sorted(set(range(len(swarm["ticks"][0]["boys"]) if swarm["ticks"] else 100)) - set(lane_of.values())))
            swarm_visits = [[0, lane_of[a] if a in lane_of else next(free, 0), a] for a in d["map"]["ids"]]
            ballots, held = [], {}
            for t in swarm["ticks"]:
                for boy, v in enumerate(t["vote"]):
                    if v >= 0 and held.get(boy) != v:
                        held[boy] = v
                        ballots.append([t["minute"], boy, v])
            swarm_picks = []
            for t in swarm["ticks"]:
                counts = [sum(1 for v in t["vote"] if v == i) for i in range(len(swarm["answers"]))]
                if counts and max(counts) > 0:
                    i = counts.index(max(counts))
                    swarm_picks.append([t["minute"], swarm["answers"][i]["parts"], swarm["answers"][i]["ok"]])
            out = {
                "kind": kind, "seed": seed, "keys": keys, "lies": lies,
                "solo": {"lanes": 1, "visits": [[s["minute"], 0, s["at"]] for s in solo["stops"][1:]],
                         "end": solo["minutes"], "ok": solo["ok"], "accused": accused(solo_dir, brief),
                         "picks": picks_solo(solo_dir, brief, truth)},
                "baker": {"lanes": len(baker["ticks"][0]["boys"]) if baker["ticks"] else 12,
                          "visits": first_visits(baker["ticks"], where, errands),
                          "picks": picks_holmes(plans, brief, truth, tick_min),
                          "reports": [[t["minute"], r["at"]] for t in baker["ticks"] for r in t["new"]],
                          "end": baker["minute"], "ok": baker["ok"], "accused": accused(baker_dir, brief)},
                "swarm": {"lanes": len(swarm["ticks"][0]["boys"]) if swarm["ticks"] else 100,
                          "visits": swarm_visits, "picks": swarm_picks, "ballots": ballots,
                          "votes": [[t["minute"], [sum(1 for v in t["vote"] if v == i) for i in range(len(swarm["answers"]))]]
                                    for t in swarm["ticks"]],
                          "answers": swarm["answers"], "end": swarm["minute"], "ok": swarm["ok"],
                          "quorum": swarm["quorum"],
                          "accused": accused(swarm_dir, brief) or (swarm["answers"][0]["parts"] if swarm["answers"] else None)},
            }
            with open(os.path.join(OUT, name), "w") as f:
                json.dump(et.rnd(out), f, separators=(",", ":"))
            n += 1
    print(n, "cases")


if __name__ == "__main__":
    main()
