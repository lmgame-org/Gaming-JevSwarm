"""Candidate actions built from ONE fish's observation only.

Each candidate is a complete action (kind, target, direction, speed class). The builder computes
geometry and eligibility; it attaches no utility score, survival estimate or recommendation.
The same candidate set is shared by every action selector.
"""

DECISION_INSTRUCTION = (
    "Choose one available action for this fish using only the supplied local observations. "
    "Stay alive, avoid collisions and conserve enough energy for future escapes. "
    "Remaining near visible fish can help, but following a neighbor may also be misleading. "
    "Rapid neighbor motion is evidence of possible danger, not proof of an unseen predator. "
    "No observed predator does not establish safety. "
    "Do not assume information outside your field of view."
)

CUE_INSTRUCTION = (
    " A visible neighbor marked fast or sharp_turn may be escaping a predator you cannot see. "
    "Joining its escape (FLEE_WITH or FOLLOW it) is often safer than ignoring it, although it can be a false alarm "
    "and bursting costs energy."
)


def instruction(cfg):
    return DECISION_INSTRUCTION + (CUE_INSTRUCTION if cfg.get("escape_cues") else "")


MAX_FOLLOW = 5
ESCAPE_OFFSETS = {"L": 45, "S": 0, "R": -45}      # degrees, left positive
BURST_DIRS = {"L": 60, "F": 0, "R": -60}


def build(obs):
    """Return an ordered dict: candidate id -> {"desc": str, "kind": str, ...}."""
    c = {}
    vf = obs["visible_fish"]
    vp = obs["visible_predators"]
    c["CONTINUE"] = {"kind": "CONTINUE", "desc": "Keep current heading at cruise speed."}
    c["SCAN_L"] = {"kind": "SCAN", "turn": 1, "desc": "Cruise slowly while turning left to look at new space."}
    c["SCAN_R"] = {"kind": "SCAN", "turn": -1, "desc": "Cruise slowly while turning right to look at new space."}
    if vf:
        c["ALIGN"] = {"kind": "ALIGN", "desc": f"Match the mean heading of the {len(vf)} visible fish at cruise speed."}
        c["COHERE"] = {"kind": "COHERE", "desc": f"Swim toward the centroid of the {len(vf)} visible fish at cruise speed."}
        cues = "motion" in vf[0]
        alarm = [e for e in vf if e.get("motion") in ("fast", "sharp_turn")]
        # the 3 closest, plus (cue mode) any fast or sharply turning neighbour, up to MAX_FOLLOW
        follow = list(vf[:3]) + [e for e in alarm if e not in vf[:3]]
        for e in follow[:MAX_FOLLOW if cues else 3]:
            sp = e["speed_estimate"]
            sp_txt = f"observed speed {sp} BL/s" if sp is not None else "speed unknown"
            if e.get("motion") == "fast":
                sp_txt += f", moving fast (own cruise {obs['self'].get('cruise_speed')} BL/s)"
            elif e.get("motion") == "sharp_turn":
                sp_txt += f", turning sharply ({e['turn_rate_estimate_deg_s']} deg/s)"
            c[f"FOLLOW_{e['slot']}"] = {
                "kind": "FOLLOW", "slot": e["slot"],
                "desc": (f"Follow neighbor {e['slot']} (range {e['range']} BL, bearing {e['bearing_deg']} deg, "
                         f"{sp_txt}) at its observed speed, capped at burst.")}
        for e in alarm[:3]:
            what = "moving fast" if e["motion"] == "fast" else "turning sharply"
            c[f"FLEE_WITH_{e['slot']}"] = {
                "kind": "FLEE_WITH", "slot": e["slot"],
                "desc": (f"Burst in the direction neighbor {e['slot']} is heading ({e['heading_relative_deg']} deg "
                         f"relative to you); it is {what} and may be escaping an unseen threat.")}
    if vp:
        p = vp[0]
        for k, off in ESCAPE_OFFSETS.items():
            side = {"L": "veering left", "S": "straight away", "R": "veering right"}[k]
            c[f"ESCAPE_{k}"] = {
                "kind": "ESCAPE", "slot": p["slot"], "offset": off,
                "desc": f"Burst away from visible predator {p['slot']} (range {p['range']} BL), {side}."}
    for k, d in BURST_DIRS.items():
        where = {"L": "60 deg to the left", "F": "straight ahead", "R": "60 deg to the right"}[k]
        c[f"BURST_{k}"] = {"kind": "BURST", "dir": d, "desc": f"Burst at high speed {where} (drains energy)."}
    for f in obs["visible_food"][:2]:
        c[f"FORAGE_{f['slot']}"] = {"kind": "FORAGE", "slot": f["slot"],
                                    "desc": f"Swim to visible food {f['slot']} (range {f['range']} BL)."}
    c["RECOVER"] = {"kind": "RECOVER", "desc": "Slow down to restore energy."}
    return c


def criteria(cands):
    return {k: v["desc"] for k, v in cands.items()}
