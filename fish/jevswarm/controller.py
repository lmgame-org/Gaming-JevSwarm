"""Motion controller with the same information limits as the policy.

It receives only the chosen action, the snapshot it was chosen from (for slot resolution) and the
fish's fresh local frames. Output is a desired heading and speed; world.step integrates them with
turn, acceleration and energy limits. Separation uses visible fish within sep_radius only;
avoidance uses currently visible walls and rocks only. Nothing here reads hidden state.
"""
import math

from .sensors import wrap

FOLLOW_GRACE_S = 0.5
ORIENT_RADIUS = 4.0          # Couzin-style zones: separation < sep_radius < orientation < attraction (vision)

# How much background social steering (align + attract toward visible fish) each action keeps.
# 0 = the action's own heading only. Scaled by cfg["social_weight"].
SOCIAL = {"CONTINUE": 1.0, "SCAN": 0.5, "RECOVER": 0.8, "ALIGN": 0.0, "COHERE": 0.0, "FOLLOW": 0.3,
          "FORAGE": 0.3, "BURST": 0.25, "ESCAPE": 0.0, "ESCAPE_GROUP": 0.0, "ESCAPE_SELFISH": 0.0,
          "FLEE_WITH": 0.5}
ESCAPE_KINDS = ("ESCAPE", "ESCAPE_GROUP", "ESCAPE_SELFISH")


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
    elif k in ESCAPE_KINDS:
        # the away-from-predator direction is fixed from the observed bearing at application time;
        # it is never updated from the predator's hidden position afterwards
        p = next((e for e in obs["visible_predators"] if e["slot"] == spec["slot"]), None)
        if p is not None:
            a.fixed_h = heading + math.radians(p["bearing_deg"]) + math.pi + math.radians(spec.get("offset", 0))
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
    if k in ESCAPE_KINDS:
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
    elif k == "ESCAPE_GROUP":
        # cooperative escape: flee the observed threat while matching and staying with visible neighbours
        v = burst
        ax, ay = math.cos(a.fixed_h), math.sin(a.fixed_h)
        if fw:
            mx = sum(math.cos(x) for x in frame.fish_heading_world) / len(fw)
            my = sum(math.sin(x) for x in frame.fish_heading_world) / len(fw)
            cx = sum(p[0] for p in fw) / len(fw) - pos[0]
            cy = sum(p[1] for p in fw) / len(fw) - pos[1]
            cd = math.hypot(cx, cy) or 1.0
            ax, ay = ax + 0.8 * mx + 0.5 * cx / cd, ay + 0.8 * my + 0.5 * cy / cd
        h = math.atan2(ay, ax)
    elif k == "ESCAPE_SELFISH":
        # selfish herd: dive toward the nearest visible neighbours on the side away from the threat,
        # putting their bodies between this fish and the predator
        v = burst
        ax, ay = math.cos(a.fixed_h), math.sin(a.fixed_h)
        far = [p for p in fw if (p[0] - pos[0]) * ax + (p[1] - pos[1]) * ay > 0] or list(fw)
        far.sort(key=lambda p: (p[0] - pos[0]) ** 2 + (p[1] - pos[1]) ** 2)
        if far:
            tx = sum(p[0] for p in far[:2]) / len(far[:2])
            ty = sum(p[1] for p in far[:2]) / len(far[:2])
            h = math.atan2(ty - pos[1], tx - pos[0])
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
    ux, uy = math.cos(h), math.sin(h)
    # background social steering from visible fish only: orientation zone aligns, beyond it attracts
    w_soc = SOCIAL.get(k, 0.0) * cfg.get("social_weight", 0.0)
    if w_soc > 0 and fw:
        mx = my = cx = cy = 0.0
        n_o = n_a = 0
        for (x, y), hw in zip(fw, frame.fish_heading_world):
            d = math.hypot(x - pos[0], y - pos[1])
            if d < ORIENT_RADIUS:
                mx += math.cos(hw)
                my += math.sin(hw)
                n_o += 1
            else:
                cx += (x - pos[0]) / d
                cy += (y - pos[1]) / d
                n_a += 1
        if n_o:
            m = math.hypot(mx, my) or 1.0
            ux += w_soc * mx / m
            uy += w_soc * my / m
        if n_a:
            m = math.hypot(cx, cy) or 1.0
            wa = w_soc * (0.6 + 0.8 * n_a / (n_a + n_o))   # pull harder when most neighbours are far
            ux += wa * cx / m
            uy += wa * cy / m
    # superimpose separation from visible fish and avoidance of visible obstacles
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
    return spec["kind"] in ("BURST", "FLEE_WITH") + ESCAPE_KINDS
