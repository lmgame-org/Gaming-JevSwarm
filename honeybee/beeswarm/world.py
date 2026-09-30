"""Ground truth: candidate sites, scouts, trips, the dance floor, quorum and lift-off.

Nothing in here is shown to a policy directly. observation.py builds each scout's local view from its own
memory (what it inspected, which dances it happened to see); the evaluator metrics at the bottom are for the
viewer and the logs only.
"""
import math
import string

import numpy as np

from .config import quorum_count

LETTERS = string.ascii_uppercase


class Site:
    def __init__(self, label, x, y, quality, appears_min=0.0):
        self.label = label
        self.x, self.y = float(x), float(y)
        self.dist = math.hypot(x, y)
        self.quality = float(quality)
        self.appears_min = float(appears_min)

    def public(self):
        return {"label": self.label, "x": round(self.x, 1), "y": round(self.y, 1), "dist": round(self.dist),
                "quality": round(self.quality, 3), "appears_min": self.appears_min}


class Scout:
    """One scout's body and memory. `known` and `dance_mem` are the only things its observation is built from."""

    def __init__(self, i, seed, sd):
        self.i = i
        self.rng = np.random.default_rng([seed, i, 1])       # assessment noise, dance watching, trips
        self.pick_rng = np.random.default_rng([seed, i, 2])  # sampling the policy's distribution
        self.sd = sd
        self.bias_site = None
        self.bias = 0.0
        self.misinfo_site = None
        self.misinfo = 0.0
        self.stubborn = False
        self.stubborn_site = None
        self.energy = 1.0
        self.state = "idle"          # idle | waiting | dancing | trip
        self.until = 0.0
        self.trip = None             # dict: kind, site, t0, t_arrive, t_leave, t_back, found, bearing
        self.dance = None            # dict: site, circuits, t0, t1
        self.known = {}              # label -> {dist, est, n, last_t, bees_seen, source, bouts}
        self.dance_mem = []          # (t, site, circuits, dancer)
        self.advertising = None
        self.last_action = None
        self.last_result = "just joined the swarm cluster"
        self.quorum_sensed = None
        self.k = 0                   # decision counter

    # ---- memory helpers
    def learn(self, site, source):
        if site.label not in self.known:
            self.known[site.label] = {"dist": site.dist, "est": None, "n": 0, "last_t": None, "bees_seen": None,
                                      "source": source, "bouts": 0}
        return self.known[site.label]

    def confidence(self, label, calibration):
        k = self.known.get(label)
        if not k or not k["n"]:
            return None
        sd_eff = self.sd / math.sqrt(k["n"])
        c = 1.0 / (1.0 + (sd_eff / 0.15) ** 2)
        if calibration >= 0:
            c = c + calibration * (1.0 - c)
        else:
            c = max(0.02, c * (1.0 + calibration))
        return c


class World:
    def __init__(self, cfg):
        self.cfg = cfg
        self.t = 0.0
        self.rng = np.random.default_rng([cfg["seed"], 0])
        self.sites = self._make_sites()
        self.scouts = self._make_scouts()
        self.quorum_t = {}           # label -> first minute quorum was present
        self.liftoff_at = None
        self.outcome = None
        self.events = []             # (t, kind, detail) appended here, drained by the engine
        self.dance_log = []          # (t0, site, circuits, scout) for evaluator metrics

    # ------------------------------------------------------------------ setup
    def _make_sites(self):
        c, rng = self.cfg, self.rng
        n = c["n_sites"]
        best = c["best_quality"]
        second = max(0.0, best - c["quality_gap"])
        lo = min(c["min_quality"], second)
        rest = list(rng.uniform(lo, max(lo, second - 0.05), n - 2)) if n > 2 else []
        qualities = [best, second] + rest
        dists = sorted(rng.uniform(c["min_dist_m"], c["max_dist_m"], n))
        if c["best_far"]:
            order = [n - 1] + list(rng.permutation(n - 1))  # best gets the farthest distance
        else:
            order = list(rng.permutation(n))
        labels = [str(x) for x in rng.permutation(list(LETTERS[:n]))]   # labels carry no information about quality
        angles = rng.uniform(0, 2 * math.pi, n)
        # spread angles so sites do not overlap on screen
        angles = np.sort(angles) + np.linspace(0, 2 * math.pi, n, endpoint=False) * 0.5
        rng.shuffle(angles)
        sites = []
        for j in range(n):
            d = dists[order[j]]
            a = angles[j]
            appears = c["late_site_min"] if (j == 0 and c["late_site_min"] > 0) else 0.0
            sites.append(Site(labels[j], d * math.cos(a), d * math.sin(a), qualities[j], appears))
        return sorted(sites, key=lambda s: s.label)

    def _make_scouts(self):
        c, rng = self.cfg, self.rng
        n = c["n_scouts"]
        noisy = rng.random(n) < c["noisy_frac"]
        biased = rng.random(n) < c["biased_frac"]
        misinf = rng.random(n) < c["misinfo_frac"]
        stubborn = rng.random(n) < c["stubborn_frac"]
        nearest = min(self.sites, key=lambda s: s.dist)
        worst = min(self.sites, key=lambda s: s.quality)
        scouts = []
        for i in range(n):
            s = Scout(i, c["seed"], c["noisy_sd"] if noisy[i] else c["quality_noise"])
            if biased[i]:
                s.bias_site, s.bias = nearest.label, c["bias_strength"]
            if misinf[i]:
                self._misinform(s, worst, c["misinfo_boost"])
            s.stubborn = bool(stubborn[i])
            scouts.append(s)
        return scouts

    def _misinform(self, s, site, boost):
        s.misinfo_site, s.misinfo = site.label, boost
        k = s.learn(site, "misinformation")
        k["est"] = min(1.0, site.quality + boost)
        k["n"] = max(k["n"], 1)
        k["last_t"] = self.t
        k["bees_seen"] = 0

    # ------------------------------------------------------------------ lookups
    def site(self, label):
        for s in self.sites:
            if s.label == label:
                return s
        return None

    def discoverable(self):
        return [s for s in self.sites if s.appears_min <= self.t]

    def at_site(self, label):
        """Scouts physically at a site right now."""
        return [s for s in self.scouts if s.state == "trip" and s.trip["site"] == label and s.trip["found"]
                and s.trip["t_arrive"] <= self.t < s.trip["t_leave"]]

    def active_dances(self):
        return [s for s in self.scouts if s.state == "dancing"]

    def idle(self):
        return [s for s in self.scouts if s.state == "idle"]

    def flight_min(self, dist):
        return dist / self.cfg["flight_m_per_min"]

    def trip_energy(self, dist):
        return self.cfg["energy_per_km"] * 2 * dist / 1000.0 + 0.002 * self.cfg["inspect_min"]

    def explore_energy(self):
        return self.cfg["energy_per_km"] * self.cfg["explore_min"] * self.cfg["flight_m_per_min"] / 1000.0 * 0.4

    def circuits_for(self, s, label):
        """Waggle circuits scout s would dance for `label` now (0 = it cannot dance for it)."""
        c = self.cfg
        k = s.known.get(label)
        if not k or not k["n"] or k["est"] is None:
            return 0
        thr = c["dance_threshold"]
        base = c["circuits_max"] * max(0.0, (k["est"] - thr) / max(1e-6, 1.0 - thr))
        conf = s.confidence(label, c["confidence_calibration"])
        base *= 0.5 + 0.5 * conf
        if not s.stubborn:
            base -= c["dance_attrition"] * k["bouts"]
        return max(0, int(round(base)))

    # ------------------------------------------------------------------ actions
    def apply(self, s, action):
        """Start the physical consequence of a chosen action. Returns a short description."""
        c = self.cfg
        s.last_action = action
        s.k += 1
        target = action.rsplit("_", 1)[-1] if action.startswith(("INSPECT_", "FOLLOW_DANCE_", "ADVERTISE_")) else None
        if s.quorum_sensed and (action == "EXPLORE" or (target and target != s.quorum_sensed)):
            s.quorum_sensed = None  # it has switched allegiance, so it no longer pipes for the old site
        if action == "WAIT":
            s.state, s.until = "waiting", self.t + c["wait_min"]
            return "rests on the cluster"
        if action == "STOP_ADVERTISING":
            s.advertising = None
            s.state, s.until = "waiting", self.t + 1.0
            return "stops advertising"
        if action == "EXPLORE":
            return self._start_explore(s)
        kind, _, label = action.partition("_")
        if action.startswith("INSPECT_"):
            return self._start_trip(s, self.site(action[8:]), "inspect")
        if action.startswith("FOLLOW_DANCE_"):
            label = action[len("FOLLOW_DANCE_"):]
            return self._start_trip(s, self.site(label), "follow")
        if action.startswith("ADVERTISE_"):
            label = action[len("ADVERTISE_"):]
            return self.start_dance(s, label, self.circuits_for(s, label))
        s.state, s.until = "waiting", self.t + 1.0
        return f"unknown action {action}"

    def start_dance(self, s, label, circuits):
        circuits = int(circuits)
        if circuits <= 0:
            s.state, s.until = "waiting", self.t + 1.0
            return f"cannot dance for {label}"
        dur = max(1.0, circuits * self.cfg["circuit_s"] / 60.0)
        s.state, s.until = "dancing", self.t + dur
        s.dance = {"site": label, "circuits": circuits, "t0": self.t, "t1": self.t + dur}
        s.advertising = label
        if label in s.known:
            s.known[label]["bouts"] += 1
        self.dance_log.append((self.t, label, circuits, s.i))
        s.energy = max(0.0, s.energy - 0.0002 * circuits)
        return f"dances {circuits} circuits for {label}"

    def _start_trip(self, s, site, kind):
        c = self.cfg
        fl = self.flight_min(site.dist)
        found = True
        if kind == "follow":
            found = s.rng.random() < c["follow_success"]
            fl *= 1.2  # followers search a little around the advertised spot
        t_arrive = self.t + fl
        if found:
            t_leave = t_arrive + c["inspect_min"] * float(s.rng.uniform(0.8, 1.2))
            t_back = t_leave + self.flight_min(site.dist)
        else:
            t_leave = t_arrive + 3.0
            t_back = t_leave + self.flight_min(site.dist)
        s.state = "trip"
        s.trip = {"kind": kind, "site": site.label, "t0": self.t, "t_arrive": t_arrive, "t_leave": t_leave,
                  "t_back": t_back, "found": found, "bearing": math.atan2(site.y, site.x), "dist": site.dist,
                  "assessed": False}
        s.until = t_back
        s.energy = max(0.0, s.energy - self.trip_energy(site.dist))
        return f"flies to {site.label}" if kind == "inspect" else f"follows a dance for {site.label}"

    def _start_explore(self, s):
        c = self.cfg
        s.energy = max(0.0, s.energy - self.explore_energy())
        cands = self.discoverable()
        found = None
        if cands and s.rng.random() < c["discover_rate"]:
            w = np.array([(1000.0 / max(200.0, x.dist)) ** 0.8 for x in cands])
            found = cands[int(s.rng.choice(len(cands), p=w / w.sum()))]
        if found is None:
            bearing = float(s.rng.uniform(0, 2 * math.pi))
            s.state = "trip"
            s.trip = {"kind": "explore", "site": None, "t0": self.t, "t_arrive": self.t + c["explore_min"] / 2,
                      "t_leave": self.t + c["explore_min"] / 2, "t_back": self.t + c["explore_min"], "found": False,
                      "bearing": bearing, "dist": c["explore_min"] / 2 * c["flight_m_per_min"] * 0.5,
                      "assessed": False}
            s.until = s.trip["t_back"]
            return "searches for a new site"
        search = c["explore_min"] * float(s.rng.uniform(0.2, 0.6))
        t_arrive = self.t + search + self.flight_min(found.dist) * 0.5
        t_leave = t_arrive + c["inspect_min"] * float(s.rng.uniform(0.8, 1.2))
        s.state = "trip"
        s.trip = {"kind": "explore", "site": found.label, "t0": self.t, "t_arrive": t_arrive, "t_leave": t_leave,
                  "t_back": t_leave + self.flight_min(found.dist), "found": True,
                  "bearing": math.atan2(found.y, found.x), "dist": found.dist, "assessed": False}
        s.until = s.trip["t_back"]
        return "searches for a new site"

    # ------------------------------------------------------------------ time
    def advance(self, dt):
        """Move truth forward by dt minutes: finish inspections, trips, dances and rests; watch dances; quorum."""
        self.t = round(self.t + dt, 6)
        c = self.cfg
        Q = quorum_count(c)
        # inspections that finish now: assess quality and count bees present
        for s in self.scouts:
            tr = s.trip
            if s.state == "trip" and tr["found"] and not tr["assessed"] and self.t >= tr["t_leave"]:
                self._assess(s, Q)
        # arrivals back at the swarm, ends of dances and rests
        for s in self.scouts:
            if s.state == "trip" and self.t >= s.trip["t_back"]:
                tr = s.trip
                if tr["kind"] == "explore" and not tr["found"]:
                    s.last_result = "searched but found no new site"
                elif tr["kind"] == "follow" and not tr["found"]:
                    s.last_result = f"followed a dance for {tr['site']} but could not find the site"
                s.state, s.trip = "idle", None
            elif s.state == "dancing" and self.t >= s.until:
                s.last_result = f"finished a {s.dance['circuits']}-circuit dance for {s.dance['site']}"
                s.state, s.dance = "idle", None
            elif s.state == "waiting" and self.t >= s.until:
                s.state = "idle"
            if s.state in ("idle", "waiting"):
                s.energy = min(1.0, s.energy + c["rest_gain_per_min"] * dt)
        self._watch_dances(dt)
        # quorum (evaluator view of the mechanism) and lift-off
        for site in self.sites:
            present = self.at_site(site.label)
            if len(present) >= Q:
                for s in present:
                    s.quorum_sensed = site.label  # scouts at a site with a quorum switch to piping for it
            if site.label not in self.quorum_t and len(present) >= Q:
                self.quorum_t[site.label] = self.t
                self.events.append((self.t, "quorum", f"quorum of {Q} scouts reached at {site.label}"))
                if self.liftoff_at is None:
                    self.liftoff_at = self.t + c["liftoff_delay_min"]
                    self.events.append((self.t, "piping", f"piping starts; lift-off at {self.liftoff_at:.0f} min"))
        if self.liftoff_at is not None and self.t >= self.liftoff_at and not self.outcome:
            self.outcome = self._liftoff()

    def _assess(self, s, Q):
        tr = s.trip
        tr["assessed"] = True
        site = self.site(tr["site"])
        present = len(self.at_site(site.label))  # includes s itself
        k = s.learn(site, "inspected" if tr["kind"] != "follow" else "dance")
        sample = site.quality + float(s.rng.normal(0, s.sd))
        if s.bias_site == site.label:
            sample += s.bias
        if s.misinfo_site == site.label:
            sample += s.misinfo
        sample = min(1.0, max(0.0, sample))
        if k["est"] is None or not k["n"]:
            k["est"], k["n"] = sample, 1
        else:
            k["est"] = (k["est"] * k["n"] + sample) / (k["n"] + 1)
            k["n"] += 1
        k["last_t"] = self.t
        k["bees_seen"] = present - 1
        if tr["kind"] == "explore" and k["n"] == 1 and k["source"] != "misinformation":
            k["source"] = "found by searching"
            if not any(x.known.get(site.label, {}).get("n") for x in self.scouts if x is not s):
                self.events.append((self.t, "discovery", f"scout {s.i} discovers site {site.label}"))
        if present >= Q and s.quorum_sensed != site.label:
            s.quorum_sensed = site.label
        if s.stubborn and s.stubborn_site is None and k["est"] >= self.cfg["dance_threshold"]:
            s.stubborn_site = site.label
        s.last_result = f"inspected {site.label}: found {present - 1} other scouts there"

    def _watch_dances(self, dt):
        dancers = self.active_dances()
        if not dancers:
            return
        c = self.cfg
        rate = c["dance_bandwidth"] / 10.0 * dt
        w = np.array([d.dance["circuits"] for d in dancers], dtype=float)
        p = w / w.sum()
        horizon = self.t - c["dance_memory_min"]
        for s in self.scouts:
            if s.state not in ("idle", "waiting"):
                continue
            n = int(s.rng.poisson(rate))
            for _ in range(min(n, len(dancers))):
                d = dancers[int(s.rng.choice(len(dancers), p=p))]
                if d is s:
                    continue
                s.dance_mem.append((self.t, d.dance["site"], d.dance["circuits"], d.i))
            if s.dance_mem and s.dance_mem[0][0] < horizon:
                s.dance_mem = [m for m in s.dance_mem if m[0] >= horizon]

    def _liftoff(self):
        piping = {}
        for s in self.scouts:
            if s.quorum_sensed:
                piping[s.quorum_sensed] = piping.get(s.quorum_sensed, 0) + 1
        ranked = sorted(piping.items(), key=lambda kv: -kv[1])
        chosen = ranked[0][0] if ranked else max(self.quorum_t, key=lambda k: -self.quorum_t[k])
        split = len(ranked) > 1 and ranked[1][0] in self.quorum_t and ranked[1][1] >= 0.5 * ranked[0][1]
        best = max(self.sites, key=lambda x: x.quality)
        ch = self.site(chosen)
        out = {"t": self.t, "chosen": chosen, "chosen_quality": round(ch.quality, 3), "best": best.label,
               "best_quality": round(best.quality, 3), "correct": chosen == best.label, "split": bool(split),
               "piping": piping, "quorum_t": dict(self.quorum_t),
               "rank": 1 + sorted([x.quality for x in self.sites], reverse=True).index(ch.quality)}
        msg = f"lift-off to {chosen} (quality {ch.quality:.2f}, best is {best.label} {best.quality:.2f})"
        if split:
            msg += f"; SPLIT with {ranked[1][0]}"
        self.events.append((self.t, "liftoff", msg))
        return out

    # ------------------------------------------------------------------ evaluator metrics
    def metrics(self):
        c = self.cfg
        horizon = self.t - 30.0
        circ = {x.label: 0 for x in self.sites}
        for t0, label, n, _ in self.dance_log:
            if t0 >= horizon:
                circ[label] = circ.get(label, 0) + n
        total = sum(circ.values())
        per = {}
        for x in self.sites:
            per[x.label] = {
                "dancers": sum(1 for d in self.active_dances() if d.dance["site"] == x.label),
                "circuits_30": circ.get(x.label, 0),
                "at_site": len(self.at_site(x.label)),
                "known_by": sum(1 for s in self.scouts if s.known.get(x.label, {}).get("n")),
                "advertisers": sum(1 for s in self.scouts if s.advertising == x.label),
            }
        lead = max(circ, key=lambda k: circ[k]) if total else None
        shares = [v / total for v in circ.values() if v] if total else []
        best = max(self.sites, key=lambda x: x.quality).label
        states = {}
        for s in self.scouts:
            states[s.state] = states.get(s.state, 0) + 1
        return {
            "t": self.t, "sites": per, "leader": lead,
            "consensus": round(circ[lead] / total, 3) if total else 0.0,
            "entropy": round(-sum(p * math.log(p) for p in shares), 3),
            "best": best, "best_share": round(circ.get(best, 0) / total, 3) if total else 0.0,
            "discovered": sum(1 for x in self.sites if per[x.label]["known_by"]),
            "quorum": dict(self.quorum_t), "liftoff_at": self.liftoff_at, "quorum_count": quorum_count(c),
            "mean_energy": round(float(np.mean([s.energy for s in self.scouts])), 3),
            "states": states,
        }
