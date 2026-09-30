"""World state and fixed-step physics (60 Hz).

The world knows everything. It exposes that knowledge only to the sensor layer
(sensors.perceive / sensors.predator_view), the physical contact solver and the evaluator.
Fish steering is computed by controller.py from a fish's own frame.
"""
import math

import numpy as np

from .sensors import predator_view, wrap


class Grid:
    """Uniform spatial hash rebuilt each tick; queries return candidate indices only."""

    def __init__(self, cell):
        self.cell = cell
        self.cells = {}

    def build(self, pos, alive):
        self.cells = {}
        c = self.cell
        for j in np.nonzero(alive)[0]:
            key = (int(pos[j, 0] // c), int(pos[j, 1] // c))
            self.cells.setdefault(key, []).append(int(j))

    def query(self, p, r):
        c = self.cell
        x0, x1 = int((p[0] - r) // c), int((p[0] + r) // c)
        y0, y1 = int((p[1] - r) // c), int((p[1] + r) // c)
        out = []
        for gx in range(x0, x1 + 1):
            for gy in range(y0, y1 + 1):
                out.extend(self.cells.get((gx, gy), ()))
        out.sort()
        return out


class Predator:
    def __init__(self, pid, pos, heading, cfg):
        self.pid = pid
        self.pos = np.array(pos, float)
        self.prev = self.pos.copy()
        self.heading = heading
        self.speed = cfg["pred_cruise"]
        self.active = True
        self.target = None
        self.mode = "patrol"          # patrol | pursue | withdraw
        self.burst_left = 0.0
        self.cooldown = 0.0
        self.capture_cd = 0.0
        self.patrol_turn = 0.0
        self.pursuit_start = None
        self.pursuits = []            # durations
        self.captures = 0


class World:
    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.w, self.h = cfg["world_w"], cfg["world_h"]
        self.fish_r = cfg["fish_radius"]
        n = cfg["n_fish"]
        self.n = n
        self.rng = rng
        # loosely aligned cluster with randomised headings and positions
        cx, cy = self.w * 0.4, self.h * 0.5
        rad = 0.9 * math.sqrt(n) + 2
        ang = rng.uniform(0, 2 * math.pi, n)
        rr = rad * np.sqrt(rng.uniform(0, 1, n))
        self.fish_pos = np.column_stack([cx + rr * np.cos(ang), cy + rr * np.sin(ang)])
        base = rng.uniform(-math.pi, math.pi)
        self.fish_h = base + rng.normal(0, math.radians(45), n)
        self.fish_v = np.full(n, cfg["cruise"])
        self.fish_e = np.ones(n)
        self.alive = np.ones(n, bool)
        self.burst_ok = np.ones(n, bool)
        self.des_h = self.fish_h.copy()
        self.des_v = self.fish_v.copy()
        self.recovering = np.zeros(n, bool)
        self.prev_pos = self.fish_pos.copy()
        self.predators = []
        self.rocks = []
        self.food = []
        self._place_rocks(cfg["n_rocks"])
        for _ in range(cfg["n_food"]):
            self.food.append((float(rng.uniform(8, self.w - 8)), float(rng.uniform(8, self.h - 8)), 1.5))
        self._push_out_of_rocks()
        self.grid = Grid(4.0)
        self.grid.build(self.fish_pos, self.alive)
        self.contacts = 0
        self._contact_pairs = set()
        self.captures = []           # (t, fish, predator)
        self.speed_overrides = 0

    def _place_rocks(self, k):
        tries = 0
        while len(self.rocks) < k and tries < 500:
            tries += 1
            r = float(self.rng.uniform(1.5, 3.5))
            x = float(self.rng.uniform(r + 4, self.w - r - 4))
            y = float(self.rng.uniform(r + 4, self.h - r - 4))
            if all(math.hypot(x - a, y - b) > r + c + 3 for a, b, c in self.rocks):
                self.rocks.append((x, y, r))

    def add_rock(self, x, y, r):
        self.rocks.append((float(x), float(y), float(r)))
        self._push_out_of_rocks()

    def _push_out_of_rocks(self):
        for (x, y, r) in self.rocks:
            d = self.fish_pos - (x, y)
            dist = np.hypot(d[:, 0], d[:, 1]) + 1e-9
            m = dist < r + self.fish_r
            if m.any():
                self.fish_pos[m] = np.array((x, y)) + d[m] / dist[m, None] * (r + self.fish_r + 1e-3)

    def grid_query(self, p, r):
        return self.grid.query(p, r)

    def add_predator(self, pos, heading):
        p = Predator(len(self.predators), pos, heading, self.cfg)
        self.predators.append(p)
        return p

    # ---------------------------------------------------------------- physics
    def step(self, dt, t):
        cfg = self.cfg
        a = self.alive
        self.prev_pos = self.fish_pos.copy()
        # turn toward desired heading within the turn limit
        turn = math.radians(cfg["turn_deg_s"]) * dt
        dh = (self.des_h - self.fish_h + np.pi) % (2 * np.pi) - np.pi
        self.fish_h = self.fish_h + np.clip(dh, -turn, turn)
        # energy gate with hysteresis, then speed toward target under an accel limit
        self.burst_ok = np.where(self.fish_e < cfg["burst_off"], False,
                                 np.where(self.fish_e > cfg["burst_on"], True, self.burst_ok))
        target_v = np.where(self.burst_ok, self.des_v, np.minimum(self.des_v, cfg["cruise"]))
        dv = np.clip(target_v - self.fish_v, -cfg["accel"] * dt, cfg["accel"] * dt)
        self.fish_v = np.maximum(self.fish_v + dv, 0.0)
        bursting = self.fish_v > cfg["cruise"] + 0.05
        self.fish_e = np.where(bursting, self.fish_e - cfg["burst_drain"] * dt, self.fish_e)
        rec = self.recovering & (self.fish_v <= cfg["cruise"] * 0.6)
        self.fish_e = np.clip(np.where(rec, self.fish_e + cfg["recover_rate"] * dt, self.fish_e), 0, 1)
        vel = np.column_stack([np.cos(self.fish_h), np.sin(self.fish_h)]) * self.fish_v[:, None]
        self.fish_pos = np.where(a[:, None], self.fish_pos + vel * dt, self.fish_pos)
        self._resolve_contacts(t)
        self._bounds()
        self.grid.build(self.fish_pos, self.alive)
        for p in self.predators:
            if p.active:
                self._step_predator(p, dt, t)

    def _resolve_contacts(self, t):
        """Physical non-overlap only: no anticipatory steering, sensing or threat avoidance."""
        idx = np.nonzero(self.alive)[0]
        if len(idx) < 2:
            return
        P = self.fish_pos[idx]
        d = P[:, None, :] - P[None, :, :]
        dist = np.hypot(d[..., 0], d[..., 1])
        np.fill_diagonal(dist, np.inf)
        mind = 2 * self.fish_r
        ii, jj = np.nonzero(np.triu(dist < mind, 1))
        pairs = set()
        for a_, b_ in zip(ii, jj):
            ia, ib = int(idx[a_]), int(idx[b_])
            pairs.add((ia, ib))
            dd = dist[a_, b_] + 1e-9
            push = (mind - dd) / 2 * (P[a_] - P[b_]) / dd
            self.fish_pos[ia] += push
            self.fish_pos[ib] -= push
        new = pairs - self._contact_pairs
        self.contacts += len(new)
        self._contact_pairs = pairs

    def _bounds(self):
        r = self.fish_r
        np.clip(self.fish_pos[:, 0], r, self.w - r, out=self.fish_pos[:, 0])
        np.clip(self.fish_pos[:, 1], r, self.h - r, out=self.fish_pos[:, 1])
        self._push_out_of_rocks()

    def _step_predator(self, p, dt, t):
        cfg = self.cfg
        p.prev = p.pos.copy()
        p.capture_cd = max(0.0, p.capture_cd - dt)
        p.cooldown = max(0.0, p.cooldown - dt)
        want_h, want_v = p.heading, cfg["pred_cruise"]
        if p.mode == "withdraw":
            # head for the nearest wall and leave
            x, y = p.pos
            opts = [(x, math.pi), (self.w - x, 0.0), (y, -math.pi / 2), (self.h - y, math.pi / 2)]
            dist, want_h = min(opts)
            if dist < 1.0:
                p.active = False
                return
            p.target = None
        else:
            idx, rng_ = p._seen if hasattr(p, "_seen") else (np.zeros(0, int), np.zeros(0))
            if p.target is not None and p.target not in set(idx.tolist()):
                if p.pursuit_start is not None:
                    p.pursuits.append(t - p.pursuit_start)
                    p.pursuit_start = None
                p.target = None
            if p.target is None and len(idx):
                p.target = int(idx[int(np.argmin(rng_))])
                p.pursuit_start = t
            if p.target is not None:
                d = self.fish_pos[p.target] - p.pos
                want_h = math.atan2(d[1], d[0])
                dist = math.hypot(*d)
                if p.burst_left <= 0 and p.cooldown <= 0 and dist < cfg["pred_burst_range"]:
                    p.burst_left = cfg["pred_burst_s"]
                p.mode = "pursue"
            else:
                p.mode = "patrol"
                p.patrol_turn += float(self.rng.normal(0, 0.6)) * dt
                p.patrol_turn = max(-0.6, min(0.6, p.patrol_turn))
                want_h = p.heading + p.patrol_turn
                # turn away from walls it is heading into (the predator sees walls)
                ahead = p.pos + 6 * np.array([math.cos(p.heading), math.sin(p.heading)])
                if not (4 < ahead[0] < self.w - 4 and 4 < ahead[1] < self.h - 4):
                    c = np.array([self.w / 2, self.h / 2]) - p.pos
                    want_h = math.atan2(c[1], c[0])
            if p.burst_left > 0:
                want_v = cfg["pred_burst"]
                p.burst_left -= dt
                if p.burst_left <= 0:
                    p.cooldown = cfg["pred_cooldown_s"]
        turn = math.radians(cfg["pred_turn_deg_s"]) * dt
        p.heading = p.heading + max(-turn, min(turn, wrap(want_h - p.heading)))
        p.speed = want_v
        p.pos = p.pos + p.speed * dt * np.array([math.cos(p.heading), math.sin(p.heading)])
        if p.mode != "withdraw":
            p.pos[0] = min(max(p.pos[0], 0.5), self.w - 0.5)
            p.pos[1] = min(max(p.pos[1], 0.5), self.h - 0.5)
        for (x, y, r) in self.rocks:
            d = p.pos - (x, y)
            dd = math.hypot(*d)
            if dd < r + cfg["pred_radius"]:
                p.pos = np.array((x, y)) + d / (dd + 1e-9) * (r + cfg["pred_radius"])
        self._captures(p, t)

    def _captures(self, p, t):
        """Swept test: min distance between predator and fish over the tick < capture radius."""
        if p.capture_cd > 0 or p.mode == "withdraw":
            return
        idx = np.nonzero(self.alive)[0]
        if not len(idx):
            return
        r0 = self.prev_pos[idx] - p.prev
        r1 = self.fish_pos[idx] - p.pos
        dr = r1 - r0
        tt = np.clip(-(r0 * dr).sum(1) / ((dr * dr).sum(1) + 1e-12), 0, 1)
        closest = r0 + dr * tt[:, None]
        md = np.hypot(closest[:, 0], closest[:, 1])
        hit = md < self.cfg["capture_radius"]
        if hit.any():
            j = int(idx[np.nonzero(hit)[0][np.argmin(md[hit])]])
            self.alive[j] = False
            self.captures.append((t, j, p.pid))
            p.captures += 1
            p.capture_cd = self.cfg["capture_cooldown_s"]
            if p.pursuit_start is not None:
                p.pursuits.append(t - p.pursuit_start)
                p.pursuit_start = None
            p.target = None
            self.grid.build(self.fish_pos, self.alive)

    def refresh_predator_vision(self):
        for p in self.predators:
            if p.active and p.mode != "withdraw":
                p._seen = predator_view(self, p, self.cfg)
