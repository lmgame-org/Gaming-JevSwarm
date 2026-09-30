"""Local vision: the only path from world state to a fish's (or predator's) knowledge.

`perceive` turns the world into a body-frame observation for one fish:
  range + FOV filter -> line-of-sight test on silhouette samples (occlusion by fish,
  predators and rocks) -> sensor noise and dropout -> closest-first capacity limits.
Motion estimates come from two of the fish's own sensor samples, never from true velocity.

The returned Frame carries the JSON-ready observation (what policies see) and, separately,
the slot -> track-key map that the controller uses to keep following the same neighbour.
Slot keys never enter a policy request.
"""
import json
import math

import numpy as np

PRED_ID = 100000
ROCK_ID = 200000
FOOD_ID = 300000
FAST_MARGIN = 1.0          # BL/s above own cruise speed -> "fast" (same threshold as the evaluator's speed cue)
SHARP_TURN_DEG_S = 60.0    # = 30 deg within 0.5 s, the evaluator's turn cue


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def los_visible(origin, targets, t_r, target_ids, occ, occ_ids, samples):
    """Line-of-sight test. A target is visible if any silhouette sample is unobstructed.

    origin (2,), targets (M,2), t_r (M,), target_ids (M,), occ (K,3) as x,y,r, occ_ids (K,).
    Silhouette samples are spread across the target's width perpendicular to the sight line.
    """
    M = len(targets)
    if M == 0:
        return np.zeros(0, bool)
    if len(occ) == 0:
        return np.ones(M, bool)
    d = targets - origin
    dist = np.hypot(d[:, 0], d[:, 1]) + 1e-9
    perp = np.stack([-d[:, 1], d[:, 0]], 1) / dist[:, None]
    offs = [0.0] if samples <= 1 else list(np.linspace(-0.9, 0.9, samples))
    S = np.concatenate([targets + perp * (t_r[:, None] * o) for o in offs])
    tid = np.tile(target_ids, len(offs))
    D = S - origin
    W = occ[:, :2] - origin
    dd = (D * D).sum(1) + 1e-12
    t = np.clip((D @ W.T) / dd[:, None], 0.0, 1.0)
    cx = t * D[:, 0:1] - W[None, :, 0]
    cy = t * D[:, 1:2] - W[None, :, 1]
    blocked = (cx * cx + cy * cy) < (occ[None, :, 2] ** 2)
    blocked &= tid[:, None] != occ_ids[None, :]
    vis = ~blocked.any(1)
    return vis.reshape(len(offs), M).any(0)


class Frame:
    __slots__ = ("t", "obs", "fish_keys", "pred_keys", "food_keys", "fish_world", "pred_world",
                 "food_world", "fish_heading_world", "fish_speed", "json")

    def __init__(self):
        self.fish_keys, self.pred_keys, self.food_keys = [], [], []
        self.fish_world, self.pred_world, self.food_world = [], [], []
        self.fish_heading_world, self.fish_speed = [], []
        self.json = None

    def state_json(self):
        if self.json is None:
            self.json = json.dumps(self.obs, separators=(",", ":"), sort_keys=True)
        return self.json


class Tracker:
    """A fish's own short sensor tracks, used only to estimate the motion of what it sees.

    Samples are noisy positions and headings reconstructed from the fish's own measurements.
    A key is dropped as soon as the object is not visible (no memory of hidden objects).
    """

    def __init__(self):
        self.tracks = {}

    def update(self, t, seen):
        """seen: {key: (x, y, heading)} measured this refresh. Returns {key: (speed, turn_deg_s) or None}."""
        est = {}
        new = {}
        for k, (x, y, h) in seen.items():
            hist = self.tracks.get(k, [])
            hist = [s for s in hist if t - s[0] <= 0.65]
            ref = None
            for s in hist:
                if t - s[0] >= 0.25:
                    ref = s
                    break
            if ref:
                dt = t - ref[0]
                est[k] = (math.hypot(x - ref[1], y - ref[2]) / dt,
                          math.degrees(wrap(h - ref[3])) / dt)
            else:
                est[k] = None
            hist.append((t, x, y, h))
            new[k] = hist
        self.tracks = new
        return est


def _r(v, n=1):
    return round(float(v), n)


def perceive(world, i, t, rng, tracker, prev_action, cfg, memory=None):
    """Build fish i's observation from its own field of view."""
    P = world.fish_pos
    me = P[i]
    hd = world.fish_h[i]
    R = cfg["vision_range"] * (1.0 - cfg.get("turbidity", 0.0))
    half = math.radians(cfg["fov_deg"]) / 2
    ch, sh = math.cos(hd), math.sin(hd)

    def body(xy):
        dx, dy = xy[..., 0] - me[0], xy[..., 1] - me[1]
        return dx * ch + dy * sh, -dx * sh + dy * ch   # forward x, left y

    alive = world.alive.copy()
    alive[i] = False
    idx_f = np.nonzero(alive)[0]
    # spatial query: candidates within range (vectorised; the grid in world.py narrows it first)
    if len(idx_f):
        near = world.grid_query(me, R + 1.0)
        near = [j for j in near if alive[j]]
        idx_f = np.array(near, dtype=int)
    fx, fy = body(P[idx_f]) if len(idx_f) else (np.zeros(0), np.zeros(0))
    fr = np.hypot(fx, fy)
    fb = np.arctan2(fy, fx)
    in_f = (fr <= R) & (np.abs(fb) <= half)

    preds = [p for p in world.predators if p.active]
    pp = np.array([p.pos for p in preds]).reshape(-1, 2)
    px, py = body(pp) if len(pp) else (np.zeros(0), np.zeros(0))
    pr = np.hypot(px, py)
    pb = np.arctan2(py, px)
    in_p = (pr <= R) & (np.abs(pb) <= half)

    foods = world.food
    fdp = np.array([f[:2] for f in foods]).reshape(-1, 2)
    qx, qy = body(fdp) if len(fdp) else (np.zeros(0), np.zeros(0))
    qr = np.hypot(qx, qy)
    qb = np.arctan2(qy, qx)
    in_q = (qr <= R) & (np.abs(qb) <= half)

    # occluders: other fish and predators within range, and rocks; never the observer itself
    if cfg["occlusion"]:
        occ = [np.column_stack([P[idx_f][fr <= R + 1], np.full(int((fr <= R + 1).sum()), world.fish_r)])]
        occ_ids = [idx_f[fr <= R + 1]]
        if len(pp):
            occ.append(np.column_stack([pp, np.full(len(pp), cfg["pred_radius"])]))
            occ_ids.append(np.arange(len(pp)) + PRED_ID)
        if world.rocks:
            occ.append(np.array(world.rocks))
            occ_ids.append(np.arange(len(world.rocks)) + ROCK_ID)
        occ = np.concatenate(occ) if occ else np.zeros((0, 3))
        occ_ids = np.concatenate(occ_ids).astype(int) if occ_ids else np.zeros(0, int)
    else:
        occ, occ_ids = np.zeros((0, 3)), np.zeros(0, int)

    S = cfg["silhouette_samples"]
    vis_f = np.zeros(len(idx_f), bool)
    if in_f.any():
        sel = np.nonzero(in_f)[0]
        vis_f[sel] = los_visible(me, P[idx_f[sel]], np.full(len(sel), world.fish_r), idx_f[sel], occ, occ_ids, S)
    vis_p = np.zeros(len(pp), bool)
    if in_p.any():
        sel = np.nonzero(in_p)[0]
        vis_p[sel] = los_visible(me, pp[sel], np.full(len(sel), cfg["pred_radius"]), sel + PRED_ID, occ, occ_ids, S)
    vis_q = np.zeros(len(fdp), bool)
    if in_q.any():
        sel = np.nonzero(in_q)[0]
        vis_q[sel] = los_visible(me, fdp[sel], np.array([foods[k][2] for k in sel]), sel + FOOD_ID, occ, occ_ids, S)

    rn, bn, drop = cfg["range_noise"], math.radians(cfg["bearing_noise_deg"]), cfg["dropout"]

    def measure(rng_, rr, bb):
        rr = rr * (1 + rn * rng_.standard_normal()) if rn else rr
        bb = bb + bn * rng_.standard_normal() if bn else bb
        return max(rr, 0.0), bb

    seen = {}
    fish_meas = []
    for k in np.nonzero(vis_f)[0]:
        if drop and rng.random() < drop:
            continue
        j = int(idx_f[k])
        rr, bb = measure(rng, fr[k], fb[k])
        hrel = wrap(world.fish_h[j] - hd + (math.radians(5) * rng.standard_normal() if bn else 0))
        wx, wy = me[0] + rr * math.cos(hd + bb), me[1] + rr * math.sin(hd + bb)
        seen[("f", j)] = (wx, wy, hd + hrel)
        fish_meas.append((rr, bb, hrel, ("f", j), (wx, wy)))
    pred_meas = []
    for k in np.nonzero(vis_p)[0]:
        if drop and rng.random() < drop:
            continue
        rr, bb = measure(rng, pr[k], pb[k])
        hrel = wrap(preds[k].heading - hd + (math.radians(5) * rng.standard_normal() if bn else 0))
        wx, wy = me[0] + rr * math.cos(hd + bb), me[1] + rr * math.sin(hd + bb)
        seen[("p", preds[k].pid)] = (wx, wy, hd + hrel)
        pred_meas.append((rr, bb, hrel, ("p", preds[k].pid), (wx, wy)))
    est = tracker.update(t, seen)

    fish_meas.sort(key=lambda m: m[0])
    pred_meas.sort(key=lambda m: m[0])
    fish_meas = fish_meas[:cfg["max_visible_fish"]]
    pred_meas = pred_meas[:cfg["max_visible_predators"]]

    fr_ = Frame()
    fr_.t = t
    use_motion = cfg.get("motion_estimates", True)
    cues = use_motion and cfg.get("escape_cues", False)

    def entry(prefix, n, m):
        e = {"slot": f"{prefix}{n}", "range": _r(m[0]), "bearing_deg": int(round(math.degrees(m[1]))),
             "heading_relative_deg": int(round(math.degrees(m[2])))}
        mv = est.get(m[3]) if use_motion else None
        e["speed_estimate"] = _r(mv[0]) if mv else None
        e["turn_rate_estimate_deg_s"] = int(round(mv[1])) if mv else None
        if cues:
            # qualitative label derived only from this fish's own estimates of what it sees
            if not mv:
                e["motion"] = "unknown"
            elif mv[0] >= cfg["cruise"] + FAST_MARGIN:
                e["motion"] = "fast"
            elif abs(mv[1]) >= SHARP_TURN_DEG_S:
                e["motion"] = "sharp_turn"
            else:
                e["motion"] = "normal"
        return e

    vf = []
    for n, m in enumerate(fish_meas):
        vf.append(entry("n", n, m))
        fr_.fish_keys.append(m[3])
        fr_.fish_world.append(m[4])
        fr_.fish_heading_world.append(hd + m[2])
        mv = est.get(m[3]) if use_motion else None
        fr_.fish_speed.append(mv[0] if mv else None)
    vp = []
    for n, m in enumerate(pred_meas):
        vp.append(entry("p", n, m))
        fr_.pred_keys.append(m[3])
        fr_.pred_world.append(m[4])

    vq = []
    for n, k in enumerate(np.nonzero(vis_q)[0]):
        rr, bb = measure(rng, qr[k], qb[k])
        vq.append({"slot": f"f{n}", "range": _r(rr), "bearing_deg": int(round(math.degrees(bb))),
                   "radius": _r(foods[k][2])})
        fr_.food_keys.append(("q", int(k)))
        fr_.food_world.append((me[0] + rr * math.cos(hd + bb), me[1] + rr * math.sin(hd + bb)))

    # obstacles: walls (nearest point) and rocks (nearest surface point), if in range and FOV
    vo = []
    W, H = world.w, world.h
    for name, pt in (("wall", (0.0, me[1])), ("wall", (W, me[1])), ("wall", (me[0], 0.0)), ("wall", (me[0], H))):
        bx, by = body(np.array(pt))
        d = math.hypot(bx, by)
        b = math.atan2(by, bx)
        if d <= R and abs(b) <= half:
            vo.append({"kind": "wall", "range": _r(d), "bearing_deg": int(round(math.degrees(b)))})
    for k, (x, y, r) in enumerate(world.rocks):
        bx, by = body(np.array((x, y)))
        d = math.hypot(bx, by) - r
        b = math.atan2(by, bx)
        if d <= R and (abs(b) <= half or d < r):
            vo.append({"kind": "rock", "range": _r(max(d, 0)), "bearing_deg": int(round(math.degrees(b))),
                       "radius": _r(r)})
    vo.sort(key=lambda o: o["range"])

    obs = {
        "self": {"speed": _r(world.fish_v[i]), "energy": _r(world.fish_e[i], 2),
                 "previous_action": prev_action},
        "vision": {"range": _r(R), "fov_degrees": int(cfg["fov_deg"])},
        "visible_fish": vf,
        "visible_predators": vp,
        "visible_obstacles": vo,
        "visible_food": vq,
    }
    if cues:
        obs["self"]["cruise_speed"] = _r(cfg["cruise"])
        obs["self"]["burst_speed"] = _r(cfg["burst"])
    if vf:
        sx = sum(math.cos(math.radians(e["heading_relative_deg"])) for e in vf)
        sy = sum(math.sin(math.radians(e["heading_relative_deg"])) for e in vf)
        sp = [e["speed_estimate"] for e in vf if e["speed_estimate"] is not None]
        obs["visible_fish_summary"] = {
            "count": len(vf),
            "mean_heading_relative_deg": int(round(math.degrees(math.atan2(sy, sx)))),
            "mean_speed_estimate": _r(sum(sp) / len(sp)) if sp else None,
        }
        if cues:
            obs["visible_fish_summary"]["fast_or_sharp_turning_count"] = sum(
                e["motion"] in ("fast", "sharp_turn") for e in vf)
    else:
        obs["visible_fish_summary"] = {"count": 0}
    if memory is not None:
        obs["recent_observations"] = memory.recall(t, hd, me)
        memory.store(t, fr_, pred_meas, hd, me)
    fr_.obs = obs
    return fr_


class Memory:
    """Optional ablation: up to N seconds of the fish's OWN past observations, age-tagged.

    Stored as the fish measured them; re-expressed in the current body frame from the fish's own
    pose (dead reckoning on itself). Hidden locations are never refreshed.
    """

    def __init__(self, horizon):
        self.horizon = horizon
        self.items = []  # (t, kind, wx, wy)

    def store(self, t, frame, pred_meas, hd, me):
        for m in pred_meas:
            self.items.append((t, "predator", m[4][0], m[4][1]))
        self.items = [x for x in self.items if t - x[0] <= self.horizon]

    def recall(self, t, hd, me):
        ch, sh = math.cos(hd), math.sin(hd)
        out = []
        for (ts, kind, wx, wy) in self.items:
            dx, dy = wx - me[0], wy - me[1]
            bx, by = dx * ch + dy * sh, -dx * sh + dy * ch
            out.append({"kind": f"last_seen_{kind}", "age_s": _r(t - ts), "range": _r(math.hypot(bx, by)),
                        "bearing_deg": int(round(math.degrees(math.atan2(by, bx))))})
        return out[-4:]


def predator_view(world, p, cfg):
    """Predator's own local vision: indices of visible fish, same occlusion rules."""
    R = cfg["pred_vision"]
    half = math.radians(cfg["pred_fov_deg"]) / 2
    idx = np.array([j for j in world.grid_query(p.pos, R + 1.0) if world.alive[j]], dtype=int)
    if not len(idx):
        return idx, np.zeros(0)
    d = world.fish_pos[idx] - p.pos
    r = np.hypot(d[:, 0], d[:, 1])
    b = np.arctan2(d[:, 1], d[:, 0]) - p.heading
    b = (b + np.pi) % (2 * np.pi) - np.pi
    m = (r <= R) & (np.abs(b) <= half)
    idx, r = idx[m], r[m]
    if not len(idx) or not cfg["occlusion"]:
        return idx, r
    near = np.array([j for j in world.grid_query(p.pos, R + 1.0) if world.alive[j]], dtype=int)
    occ = [np.column_stack([world.fish_pos[near], np.full(len(near), world.fish_r)])]
    ids = [near]
    if world.rocks:
        occ.append(np.array(world.rocks))
        ids.append(np.arange(len(world.rocks)) + ROCK_ID)
    vis = los_visible(p.pos, world.fish_pos[idx], np.full(len(idx), world.fish_r), idx,
                      np.concatenate(occ), np.concatenate(ids).astype(int), cfg["silhouette_samples"])
    return idx[vis], r[vis]
