"""Evaluator: global metrics computed from the world. Never serialized into a fish request."""
import math

import numpy as np

FRAG_THRESHOLD = 6.0
TURN_CUE_DEG = 30.0
SPEED_CUE = 1.0
CUE_WINDOW = 0.5


def polarization(world):
    h = world.fish_h[world.alive]
    if not len(h):
        return 0.0
    return float(math.hypot(np.cos(h).mean(), np.sin(h).mean()))


def components(world):
    idx = np.nonzero(world.alive)[0]
    n = len(idx)
    if n == 0:
        return 0, 0.0
    P = world.fish_pos[idx]
    d = np.hypot(*(P[:, None, :] - P[None, :, :]).transpose(2, 0, 1))
    adj = d < FRAG_THRESHOLD
    seen = np.zeros(n, bool)
    sizes = []
    for s in range(n):
        if seen[s]:
            continue
        stack, size = [s], 0
        seen[s] = True
        while stack:
            u = stack.pop()
            size += 1
            for v in np.nonzero(adj[u] & ~seen)[0]:
                seen[v] = True
                stack.append(int(v))
        sizes.append(size)
    return len(sizes), max(sizes) / n


class Evaluator:
    def __init__(self, world, cfg):
        self.world = world
        self.cfg = cfg
        n = world.n
        self.hist = []                        # (t, headings copy, speeds copy) at sensor rate
        self.seen_pred = np.zeros(n, bool)    # ever directly saw a predator
        self.cue_t = np.full(n, np.nan)
        self.responses = []                   # latencies (s)
        self.series = []
        self.recover_t = None
        self._ok_since = None
        self.withdraw_t = None
        self.first_capture = None
        self.contact_samples = []

    def on_sensor(self, t, frames, attack_started):
        w = self.world
        self.hist.append((t, w.fish_h.copy(), w.fish_v.copy()))
        self.hist = [h for h in self.hist if t - h[0] <= CUE_WINDOW + 0.11]
        if not attack_started or len(self.hist) < 2:
            return
        t0, h0, v0 = self.hist[0]
        turned = np.degrees(np.abs((w.fish_h - h0 + np.pi) % (2 * np.pi) - np.pi)) >= TURN_CUE_DEG
        sped = (w.fish_v - v0) >= SPEED_CUE
        moved = turned | sped
        for i, fr in frames.items():
            if not w.alive[i] or fr is None:
                continue
            if fr.pred_keys:
                self.seen_pred[i] = True
                self.cue_t[i] = np.nan
                continue
            if self.seen_pred[i]:
                continue
            if not np.isnan(self.cue_t[i]):
                if moved[i]:
                    self.responses.append(t - self.cue_t[i])
                    self.cue_t[i] = np.nan
                elif t - self.cue_t[i] > 3.0:
                    self.cue_t[i] = np.nan
                continue
            for key in fr.fish_keys:
                j = key[1]
                if moved[j]:
                    self.cue_t[i] = t
                    break

    def sample(self, t, extra):
        w = self.world
        alive = int(w.alive.sum())
        pol = polarization(w)
        ncomp, lcf = components(w)
        e = w.fish_e[w.alive]
        row = {
            "t": round(t, 2), "alive": alive, "captures": len(w.captures), "polarization": round(pol, 3),
            "components": ncomp, "largest_component": round(lcf, 3),
            "mean_energy": round(float(e.mean()) if len(e) else 0.0, 3),
            "depleted": round(float((e < self.cfg["burst_off"]).mean()) if len(e) else 0.0, 3),
            "contacts": w.contacts,
        }
        row.update(extra)
        self.series.append(row)
        if w.captures and self.first_capture is None:
            self.first_capture = w.captures[0][0]
        if self.withdraw_t is not None and self.recover_t is None:
            ok = lcf >= 0.9 and pol >= 0.7
            if ok:
                self._ok_since = self._ok_since if self._ok_since is not None else t
                if t - self._ok_since >= 3.0:
                    self.recover_t = self._ok_since - self.withdraw_t
            else:
                self._ok_since = None
        return row

    def summary(self, t, inference):
        w = self.world
        last = self.series[-1] if self.series else {}
        minutes = max(t / 60.0, 1e-9) * max(w.n, 1)
        pursuits = [d for p in w.predators for d in p.pursuits]
        return {
            "t_end": round(t, 2),
            "survival_fraction": round(float(w.alive.mean()), 3),
            "survivors": int(w.alive.sum()),
            "captures": len(w.captures),
            "time_to_first_capture": self.first_capture,
            "mean_pursuit_s": round(float(np.mean(pursuits)), 2) if pursuits else None,
            "polarization": last.get("polarization"),
            "largest_component": last.get("largest_component"),
            "components": last.get("components"),
            "recovery_s": None if self.recover_t is None else round(self.recover_t, 2),
            "recovered": None if self.withdraw_t is None else self.recover_t is not None,
            "mean_energy": last.get("mean_energy"),
            "depleted_fraction": last.get("depleted"),
            "contacts_per_fish_minute": round(w.contacts / minutes, 3),
            "burst_speed_overrides": w.speed_overrides,
            "indirect_responses": len(self.responses),
            "indirect_response_latency_mean": round(float(np.mean(self.responses)), 3) if self.responses else None,
            "direct_witness_fraction": round(float(self.seen_pred.mean()), 3),
            "inference": inference,
        }
