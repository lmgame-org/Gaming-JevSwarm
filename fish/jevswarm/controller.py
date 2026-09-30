"""Motion controller with the same information limits as the policy.

It receives only the chosen action, the snapshot it was chosen from (for slot resolution) and the
fish's fresh local frames. Output is a desired heading and speed; world.step integrates them with
turn, acceleration and energy limits. Separation uses visible fish within sep_radius only;
avoidance uses currently visible walls and rocks only. Nothing here reads hidden state.
"""
import math

from .sensors import wrap

FOLLOW_GRACE_S = 0.5


class ActionState:
    __slots__ = ("cid", "kind", "spec", "t0", "fixed_h", "track", "lost_t", "last_h", "source", "forced_until")

    def __init__(self, cid="CONTINUE", spec=None, t0=0.0, heading=0.0, source="init"):
        self.cid = cid
        self.spec = spec or {"kind": "CONTINUE"}
        self.kind = self.spec["kind"]
        self.t0 = t0
        self.fixed_h = heading
        self.track = None
        self.lost_t = None
        self.last_h = heading
        self.source = source
        self.forced_until = None


def apply(cid, spec, snapshot, heading, t, source):
    """Bind an action at application time. Headings are fixed from the snapshot's observed bearings."""
    a = ActionState(cid, spec, t, heading, source)
    obs = snapshot.obs
    k = spec["kind"]
    if k == "SCAN":
        a.fixed_h = heading + spec["turn"] * math.radians(90)
    elif k == "BURST":
        a.fixed_h = heading + math.radians(spec["dir"])
    elif k == "ESCAPE":
        p = next((e for e in obs["visible_predators"] if e["slot"] == spec["slot"]), None)
        if p is not None:
            a.fixed_h = heading + math.radians(p["bearing_deg"]) + math.pi + math.radians(spec["offset"])
    elif k == "FLEE_WITH":
        e = next((e for e in obs["visible_fish"] if e["slot"] == spec["slot"]), None)
        if e is not None:
            a.fixed_h = heading + math.radians(e["heading_relative_deg"])
    elif k == "FOLLOW":
        slots = [e["slot"] for e in obs["visible_fish"]]
        if spec["slot"] in slots:
            a.track = snapshot.fish_keys[slots.index(spec["slot"])]
    elif k == "FORAGE":
        slots = [e["slot"] for e in obs["visible_food"]]
        if spec["slot"] in slots:
            a.track = snapshot.food_keys[slots.index(spec["slot"])]
    a.last_h = a.fixed_h
    return a


def target_valid(spec, snapshot):
    k = spec["kind"]
    if k == "FOLLOW":
        return any(e["slot"] == spec["slot"] for e in snapshot.obs["visible_fish"])
    if k == "ESCAPE":
        return any(e["slot"] == spec["slot"] for e in snapshot.obs["visible_predators"])
    if k == "FLEE_WITH":
        return any(e["slot"] == spec["slot"] for e in snapshot.obs["visible_fish"])
    if k == "FORAGE":
        return any(e["slot"] == spec["slot"] for e in snapshot.obs["visible_food"])
    return True


def desired(a, frame, pos, heading, cfg, t):
    """Desired (heading, speed) from the current action and the latest local frame."""
    cruise, burst = cfg["cruise"], cfg["burst"]
    k = a.kind
    h, v = a.fixed_h, cruise
    fw = frame.fish_world
    if k == "CONTINUE" or k == "RECOVER":
        h = a.fixed_h
        v = cruise if k == "CONTINUE" else cruise * 0.4
    elif k == "SCAN":
        v = cruise * 0.6
    elif k in ("BURST", "ESCAPE", "FLEE_WITH"):
        v = burst
    elif k == "ALIGN":
        if fw:
            sx = sum(math.cos(x) for x in frame.fish_heading_world)
            sy = sum(math.sin(x) for x in frame.fish_heading_world)
            h = math.atan2(sy, sx)
        else:
            h = heading
    elif k == "COHERE":
        if fw:
            cx = sum(p[0] for p in fw) / len(fw)
            cy = sum(p[1] for p in fw) / len(fw)
            h = math.atan2(cy - pos[1], cx - pos[0])
        else:
            h = heading
    elif k in ("FOLLOW", "FORAGE"):
        keys = frame.fish_keys if k == "FOLLOW" else frame.food_keys
        pts = fw if k == "FOLLOW" else frame.food_world
        if a.track is not None and a.track in keys:
            j = keys.index(a.track)
            h = math.atan2(pts[j][1] - pos[1], pts[j][0] - pos[0])
            a.last_h = h
            a.lost_t = None
            if k == "FOLLOW":
                sp = frame.fish_speed[j]
                v = min(sp if sp is not None else cruise, burst)
                v = max(v, cruise * 0.5)
        else:
            # target not visible: hold last heading briefly, then CONTINUE (never track hidden location)
            if a.lost_t is None:
                a.lost_t = t
            h = a.last_h
            if t - a.lost_t > FOLLOW_GRACE_S:
                a.kind = "CONTINUE"
                a.fixed_h = a.last_h
    # superimpose separation from visible fish and avoidance of visible obstacles
    ux, uy = math.cos(h), math.sin(h)
    sep = cfg["sep_radius"]
    for (x, y) in fw:
        dx, dy = pos[0] - x, pos[1] - y
        d = math.hypot(dx, dy)
        if 1e-6 < d < sep:
            w = 1.5 * (sep - d) / sep
            ux += w * dx / d
            uy += w * dy / d
    for o in frame.obs["visible_obstacles"]:
        rng = o["range"]
        if rng < 4.0:
            b = heading + math.radians(o["bearing_deg"])
            w = 2.0 * (4.0 - rng) / 4.0
            ux -= w * math.cos(b)
            uy -= w * math.sin(b)
    return math.atan2(uy, ux), v



def is_burst(spec):
    return spec["kind"] in ("BURST", "ESCAPE", "FLEE_WITH")
