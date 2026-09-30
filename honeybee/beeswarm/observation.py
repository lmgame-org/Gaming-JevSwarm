"""A scout's local view and its candidate actions. This is the information boundary.

Everything here is built from the scout's own body (energy, what it is advertising) and memory (sites it has
inspected or learned about from a dance, dances it happened to watch). True site quality, other scouts'
beliefs, quorum counts and the global dance tally never appear.
"""
import json

INSTRUCTION = (
    "You are one scout bee in a honeybee swarm hanging from a branch. The swarm must choose one new nest cavity "
    "and then fly there together. You know only what you inspected yourself and the waggle dances you happened "
    "to watch on the cluster; other scouts may be wrong. A dance advertises a site; more circuits mean the "
    "dancer rated it higher. The swarm does best if it settles on the best cavity reasonably quickly, and it "
    "must not split between two sites. Choose your next action."
)

OBS_FIELDS = {"self", "known_sites", "dances_observed_recently"}


def instruction(cfg):
    return INSTRUCTION


def observe(world, s):
    """The exact JSON-able dict a policy sees for scout s."""
    c = world.cfg
    t = world.t
    known = []
    for label in sorted(s.known):
        k = s.known[label]
        e = {"site": label, "distance_m": int(round(k["dist"], -1))}
        if k["n"]:
            e.update({
                "my_quality_estimate": round(k["est"], 2),
                "confidence": round(s.confidence(label, c["confidence_calibration"]), 2),
                "inspections": k["n"],
                "bees_seen_there_last_visit": k["bees_seen"],
                "minutes_since_inspection": int(round(t - k["last_t"])),
                "my_dance_bouts_for_it": k["bouts"],
            })
        else:
            e.update({"learned_from": "a dance", "inspections": 0})
        known.append(e)
    dances = {}
    for (t0, label, circ, dancer) in s.dance_mem:
        d = dances.setdefault(label, {"site": label, "dances_seen": 0, "dancers": set(), "circuits": 0,
                                      "minutes_since_last_seen": None})
        d["dances_seen"] += 1
        d["dancers"].add(dancer)
        d["circuits"] += circ
        d["minutes_since_last_seen"] = int(round(t - t0))
    dance_list = []
    for label in sorted(dances):
        d = dances[label]
        dance_list.append({"site": label, "dancers": len(d["dancers"]), "dances_seen": d["dances_seen"],
                           "total_circuits": d["circuits"], "minutes_since_last_seen": d["minutes_since_last_seen"]})
    return {
        "self": {
            "energy": round(s.energy, 2),
            "currently_advertising": s.advertising,
            "last_action": s.last_action,
            "last_result": s.last_result,
            "sensed_quorum_at": s.quorum_sensed,
        },
        "known_sites": known,
        "dances_observed_recently": {"window_min": int(c["dance_memory_min"]), "sites": dance_list},
    }


def candidates(world, s):
    """Available action ids -> plain descriptions (no scores, no recommendation)."""
    c = world.cfg
    out = {"WAIT": f"Rest on the cluster for about {int(c['wait_min'])} minutes and watch dances"}
    if s.energy >= world.explore_energy():
        out["EXPLORE"] = "Fly out and search the surroundings for a cavity you do not know yet"
    active = {d.dance["site"] for d in world.active_dances() if d is not s}
    seen = {m[1] for m in s.dance_mem if world.t - m[0] <= 10}
    for label in sorted(s.known):
        k = s.known[label]
        if s.energy >= world.trip_energy(k["dist"]):
            what = "again" if k["n"] else "for the first time"
            out[f"INSPECT_{label}"] = f"Fly {int(round(k['dist'], -1))} m to site {label} and inspect it {what}"
    for label in sorted(active & seen):
        site = world.site(label)
        if site is None or s.energy < world.trip_energy(site.dist):
            continue
        if s.known.get(label, {}).get("n"):
            continue  # already knows the way; INSPECT covers it
        out[f"FOLLOW_DANCE_{label}"] = f"Follow a dancer advertising site {label} and fly there to inspect it"
    for label in sorted(s.known):
        n = world.circuits_for(s, label)
        if n > 0:
            out[f"ADVERTISE_{label}"] = f"Perform a waggle dance for site {label} on the cluster ({n} circuits)"
    if s.advertising:
        out["STOP_ADVERTISING"] = f"Stop advertising site {s.advertising}"
    return out


def state_json(obs):
    return json.dumps(obs, separators=(",", ":"), sort_keys=True)
