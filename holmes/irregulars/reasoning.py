"""Vote-counting deduction over structured facts. Used by the rule baseline, the swarm's reflex rule and the
solvability oracle. It reads only facts a detective has collected plus the public brief (suspect descriptions,
motive list, hideout candidates); it does not know which leads are lies.
"""
from collections import Counter


def deduce(facts, case, need=2):
    """facts: list of fact lists. Returns {culprit|motive|hideout: {scores, best, margin, confident}} using ids."""
    traits, alibi, motive, hd, ht = {}, Counter(), Counter(), Counter(), Counter()
    found, empty = set(), set()
    addr_to_h = {h["address"]: h["id"] for h in case.hideouts}
    for f in facts:
        k = f[0]
        if k == "trait":
            traits.setdefault(f[1], Counter())[f[2]] += 1
        elif k == "alibi":
            alibi[f[1]] += 1
        elif k == "motive":
            motive[f[1]] += 1
        elif k == "hide_district":
            hd[f[1]] += 1
        elif k == "hide_type":
            ht[f[1]] += 1
        elif k == "hide_found" and len(f) > 1:
            found.add(addr_to_h.get(f[1], f[1]))
        elif k == "hide_not" and len(f) > 1:
            empty.add(addr_to_h.get(f[1], f[1]))
    # Maximum likelihood with every lead equally reliable: score = minus the number of collected leads that would
    # have to be lies if this answer were true.
    cs = {}
    for s in case.suspects:
        bad = sum(sum(v.values()) - v[s["traits"][d]] for d, v in traits.items()) + alibi[s["id"]]
        cs[s["id"]] = -float(bad)
    ms = {case.motive_id(m): float(motive[m]) - (sum(motive.values()) - motive[m]) for m in case.motives}
    hs = {}
    for h in case.hideouts:
        bad = (sum(hd.values()) - hd[h["district"]]) + (sum(ht.values()) - ht[h["type"]])
        sc = -float(bad) + 0.01 * (hd[h["district"]] + ht[h["type"]])
        if h["id"] in found:
            sc += 100
        if h["id"] in empty:
            sc -= 100
        hs[h["id"]] = round(sc, 2)
    n = {"culprit": sum(sum(v.values()) for v in traits.values()) + sum(alibi.values()),
         "motive": sum(motive.values()), "hideout": sum(hd.values()) + sum(ht.values()) + len(found) + len(empty)}
    out = {}
    for name, sc, thr in (("culprit", cs, 1.0), ("motive", ms, 1.0), ("hideout", hs, 1.0)):
        order = sorted(sc, key=lambda k: (-sc[k], k))
        best = order[0]
        margin = sc[best] - (sc[order[1]] if len(order) > 1 else 0)
        conf = margin >= thr
        if name == "motive":
            conf = conf and motive[case.motives[int(best[1:]) - 1]] >= need
        if name == "hideout" and best in found:
            conf = True
        if name == "culprit":
            conf = conf and sum(sum(v.values()) for v in traits.values()) >= need
        out[name] = {"scores": sc, "best": best, "margin": round(margin, 2), "confident": bool(conf),
                     "n": n[name]}
    return out


def to_probs(scores, temp=1.0):
    """Softmax of vote scores, for display and as a policy distribution."""
    import math
    m = max(scores.values())
    e = {k: math.exp((v - m) / temp) for k, v in scores.items()}
    s = sum(e.values())
    return {k: round(v / s, 4) for k, v in e.items()}
