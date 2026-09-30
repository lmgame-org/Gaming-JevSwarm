"""Clock, decisions, interventions, predictions, logging and viewer frames.

One tick is one simulated minute. At every tick the world advances, then every scout that is idle on the
cluster decides. Remote decisions for a tick are sent together (up to `concurrency` in flight) and the clock
waits for them, so a run is comparable across policies and replays exactly from its decision log.
"""
import json
import math
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from swarmcore.web import Broadcaster, redact

from . import observation as O
from . import policies as P
from .config import LIVE_KEYS, coerce, quorum_count
from .world import Site, World

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "runs")
SITE_COLORS = ["#f4b400", "#4d8df0", "#e8618c", "#3fc1a9", "#b07cf2", "#ff8c42", "#8bc34a", "#29b6f6",
               "#ef5350", "#c0ca33"]


class Engine:
    def __init__(self, cfg, realtime=True, log=True, runs_dir=None):
        cfg = dict(cfg or {})
        self.replay_log = []
        if cfg.get("policy") == "replay":
            src = os.path.join(runs_dir or RUNS, cfg.get("replay_run") or "")
            with open(os.path.join(src, "config.json")) as f:
                rec = json.load(f)
            cfg = {**rec["cfg"], "policy": "replay", "replay_run": cfg.get("replay_run"),
                   "speed": cfg.get("speed", rec["cfg"].get("speed"))}
            with open(os.path.join(src, "events.jsonl")) as f:
                self.replay_log = [e for e in map(json.loads, f) if e.get("kind") == "intervention"]
            self.replay_dir = src
        self.cfg = coerce(cfg)
        self.realtime = realtime
        self.world = World(self.cfg)
        self.policy = self._make_policy(self.cfg["policy"])
        self.fallback = P.make(self.cfg["fallback"], self.cfg)
        self.pool = ThreadPoolExecutor(max_workers=max(1, self.cfg["concurrency"]))
        self.bus = Broadcaster()
        self.cmds = queue.Queue()
        self.paused = False
        self.step_req = 0
        self.stopped = False
        self.ended = False
        self.stats = {"decisions": 0, "requests": 0, "completed": 0, "failures": 0, "fallbacks": 0,
                      "input_tokens": 0, "cost": 0.0, "latencies": [], "models": set(), "by_source": {}}
        self.errors = []
        self._lock = threading.Lock()
        self.last = {}               # scout -> last decision record (for the viewer)
        self.history = {}            # scout -> recent applied actions
        self.series = []
        self.event_tail = []
        self.predictions = []
        self.bankroll = 1000.0
        self.summary = None
        self._last_pub = 0.0
        self.run_dir = None
        self._files = {}
        if log:
            os.makedirs(runs_dir or RUNS, exist_ok=True)
            name = f"{time.strftime('%Y%m%d-%H%M%S')}_{self.cfg['scenario']}_{self.cfg['policy']}_s{self.cfg['seed']}"
            self.run_dir = os.path.join(runs_dir or RUNS, name)
            os.makedirs(self.run_dir, exist_ok=True)
            safe = {k: v for k, v in self.cfg.items()}
            with open(os.path.join(self.run_dir, "config.json"), "w") as f:
                json.dump({"cfg": safe, "prompt_hash": P.prompt_hash(self.cfg), "instruction": O.instruction(self.cfg),
                           "sites": [s.public() for s in self.world.sites], "quorum": quorum_count(self.cfg)},
                          f, indent=1)
            for k in ("decisions", "events", "metrics"):
                self._files[k] = open(os.path.join(self.run_dir, f"{k}.jsonl"), "w", buffering=1)
        self._event("run", f"{len(self.world.scouts)} scouts, {len(self.world.sites)} sites, quorum "
                           f"{quorum_count(self.cfg)}, policy {self.cfg['policy']}")

    def _make_policy(self, name):
        if name == "replay":
            return P.make("replay", self.cfg, getattr(self, "replay_dir", None))
        return P.make(name, self.cfg)

    # ------------------------------------------------------------------ logging
    def _write(self, kind, obj):
        f = self._files.get(kind)
        if f:
            f.write(json.dumps(obj, default=str) + "\n")

    def _event(self, kind, detail, extra=None):
        e = {"t": round(self.world.t, 2), "kind": kind, "detail": detail}
        if extra:
            e.update(extra)
        self.event_tail = (self.event_tail + [e])[-80:]
        self._write("events", e)

    # ------------------------------------------------------------------ main loop
    def run(self):
        try:
            while not self.stopped and not self.ended:
                self._drain_cmds()
                if self.paused and not self.step_req:
                    time.sleep(0.05)
                    continue
                if self.step_req:
                    self.step_req -= 1
                w0 = time.time()
                self.tick()
                if self.realtime:
                    self._publish()
                    time.sleep(max(0.0, 1.0 / max(0.05, self.cfg["speed"]) - (time.time() - w0)))
            self._publish(force=True)
        except Exception as e:  # noqa: BLE001
            self.errors.append(redact(f"engine crashed: {type(e).__name__}: {e}"))
            self._publish(force=True)
            raise
        finally:
            self.pool.shutdown(wait=False)

    def run_all(self):
        """Headless: run to lift-off or the time limit."""
        while not self.ended:
            self.tick()
        return self.summary

    def tick(self):
        w = self.world
        for rec in self.replay_log:
            if abs(rec["t"] - w.t) < 1e-6:
                self._intervene(rec["cmd"], replaying=True)
        w.advance(1.0)
        for (t, kind, detail) in w.events:
            self._event(kind, detail)
        w.events.clear()
        if not w.outcome:
            self._decide(w.idle())
        if int(w.t) % 5 == 0 or w.outcome:
            m = w.metrics()
            self.series.append({"t": w.t, **{k: m["sites"][k]["circuits_30"] for k in m["sites"]},
                                "_at": {k: m["sites"][k]["at_site"] for k in m["sites"]}})
            self.series = self.series[-400:]
            self._write("metrics", m)
        if w.outcome or w.t >= self.cfg["max_hours"] * 60:
            self._finish()

    # ------------------------------------------------------------------ decisions
    def _decide(self, due):
        if not due:
            return
        jobs = []
        for s in due:
            obs = O.observe(self.world, s)
            cands = O.candidates(self.world, s)
            jobs.append((s, obs, cands))
        results = {}
        remote = []
        for s, obs, cands in jobs:
            forced = self._forced(s, cands)
            if forced:
                results[s.i] = (P.one_hot(cands, forced), {}, "stubborn", 0.0)
            elif self.cfg["policy"] == "replay":
                p = self.policy.lookup(s.i, s.k, cands)
                results[s.i] = (p, {"replayed": True}, "replay", 0.0) if p else None
            elif getattr(self.policy, "remote", False):
                remote.append((s, obs, cands))
            else:
                probs, meta = self.policy.decide(obs, cands, None)
                results[s.i] = (probs, meta, "policy", 0.0)
        if remote:
            futs = [(s, obs, cands, self.pool.submit(self._call, obs, cands)) for s, obs, cands in remote]
            for s, obs, cands, fut in futs:
                results[s.i] = fut.result()
        for s, obs, cands in jobs:
            r = results.get(s.i)
            if r is None or r[0] is None:
                probs, _ = self.fallback.decide(obs, cands, None)
                meta, source, lat = (r[1] if r else {}), "fallback", (r[3] if r else 0.0)
                self.stats["fallbacks"] += 1
            else:
                probs, meta, source, lat = r
            applied = P.sample(probs, s.pick_rng, argmax=self.cfg["sampling"] == "argmax")
            k = s.k
            what = self.world.apply(s, applied)
            self.stats["decisions"] += 1
            self.stats["by_source"][source] = self.stats["by_source"].get(source, 0) + 1
            rec = {"t": self.world.t, "scout": s.i, "k": k, "source": source, "obs": obs, "cands": cands,
                   "probs": {c: round(v, 4) for c, v in probs.items()}, "applied": applied, "latency": round(lat, 3),
                   "model": meta.get("model"), "raw": meta.get("raw"), "error": meta.get("error")}
            self.last[s.i] = rec
            h = self.history.setdefault(s.i, [])
            h.append((self.world.t, applied, what))
            del h[:-12]
            self._write("decisions", rec)

    def _forced(self, s, cands):
        """Stubborn scouts bypass the policy: never follow dances, keep advertising their first site."""
        if not s.stubborn:
            return None
        if s.energy < 0.2:
            return "WAIT"
        site = s.stubborn_site
        if site:
            if s.last_action == f"ADVERTISE_{site}" and f"INSPECT_{site}" in cands:
                return f"INSPECT_{site}"
            if f"ADVERTISE_{site}" in cands:
                return f"ADVERTISE_{site}"
            return f"INSPECT_{site}" if f"INSPECT_{site}" in cands else "WAIT"
        return "EXPLORE" if "EXPLORE" in cands else "WAIT"

    def _call(self, obs, cands):
        """Runs in the pool. Returns (probs or None, meta, source, latency)."""
        t0 = time.time()
        with self._lock:
            self.stats["requests"] += 1
        if len(cands) == 1:
            return P.one_hot(cands, next(iter(cands))), {}, "only_option", 0.0
        try:
            probs, meta = self.policy.decide(obs, cands, O.state_json(obs))
            lat = time.time() - t0
            u = meta.get("usage") or {}
            with self._lock:
                self.stats["completed"] += 1
                self.stats["latencies"].append(lat)
                self.stats["input_tokens"] += int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
                self.stats["cost"] += float(u.get("cost") or 0)
                if meta.get("model"):
                    self.stats["models"].add(meta["model"])
            return probs, meta, "policy", lat
        except Exception as e:  # noqa: BLE001
            msg = redact(f"{type(e).__name__}: {e}")[:240]
            with self._lock:
                self.stats["failures"] += 1
                self.errors = (self.errors + [msg])[-6:]
            return None, {"error": msg}, "fallback", time.time() - t0

    # ------------------------------------------------------------------ interventions
    def command(self, cmd):
        self.cmds.put(cmd)

    def _drain_cmds(self):
        while True:
            try:
                cmd = self.cmds.get_nowait()
            except queue.Empty:
                return
            op = cmd.get("op")
            if op == "pause":
                self.paused = True
            elif op == "resume":
                self.paused = False
            elif op == "step":
                self.paused = True
                self.step_req += int(cmd.get("n") or 5)
            elif op == "stop":
                self.stopped = True
            else:
                self._intervene(cmd)

    def _intervene(self, cmd, replaying=False):
        w = self.world
        op = cmd.get("op")
        rng = np.random.default_rng([self.cfg["seed"], 99, int(w.t)])
        detail = None
        if op == "set":
            k, v = cmd.get("key"), cmd.get("value")
            if k not in LIVE_KEYS:
                return
            new = coerce({**self.cfg, k: v})
            self.cfg[k] = new[k]
            if k == "policy" and not replaying:
                try:
                    self.policy = self._make_policy(self.cfg["policy"])
                except Exception as e:  # noqa: BLE001
                    self.errors.append(redact(e))
            if k == "speed":
                return  # not an intervention on the colony
            detail = f"set {k} = {self.cfg[k]}"
        elif op == "site_quality":
            s = w.site(cmd.get("site"))
            if not s:
                return
            s.quality = max(0.0, min(1.0, float(cmd.get("quality", s.quality))))
            detail = f"site {s.label} quality set to {s.quality:.2f}"
        elif op == "add_site":
            used = {s.label for s in w.sites}
            label = next((c for c in "ABCDEFGHIJKLMNOP" if c not in used), None)
            if not label:
                return
            x, y = float(cmd.get("x", 1000)), float(cmd.get("y", 0))
            s = Site(label, x, y, float(cmd.get("quality", 0.95)), w.t)
            w.sites.append(s)
            w.sites.sort(key=lambda z: z.label)
            detail = f"new site {label} at {s.dist:.0f} m, quality {s.quality:.2f}"
        elif op == "misinform":
            s = w.site(cmd.get("site"))
            n = int(cmd.get("n") or 3)
            if not s:
                return
            pool = [b for b in w.scouts if b.misinfo_site != s.label]
            for i in rng.choice(len(pool), size=min(n, len(pool)), replace=False):
                w._misinform(pool[int(i)], s, self.cfg["misinfo_boost"])
            detail = f"{n} scouts now believe site {s.label} is excellent"
        elif op == "fake_dances":
            s = w.site(cmd.get("site"))
            n = int(cmd.get("n") or 3)
            idle = [b for b in w.scouts if b.state in ("idle", "waiting")]
            if not s or not idle:
                return
            for i in rng.choice(len(idle), size=min(n, len(idle)), replace=False):
                w.start_dance(idle[int(i)], s.label, self.cfg["circuits_max"] // 2)
            detail = f"{n} fake dances for site {s.label} injected"
        elif op == "stubborn":
            n = int(cmd.get("n") or 3)
            pool = [b for b in w.scouts if not b.stubborn]
            for i in rng.choice(len(pool), size=min(n, len(pool)), replace=False):
                pool[int(i)].stubborn = True
            detail = f"{n} scouts turned stubborn"
        else:
            return
        self._event("intervention", detail, {"cmd": cmd})

    # ------------------------------------------------------------------ predictions (play money)
    def add_prediction(self, kind, value, stake):
        if self.ended:
            return None
        stake = max(1.0, min(float(stake or 0), self.bankroll))
        if stake <= 0:
            return None
        m = self.world.metrics()
        if kind == "winner":
            site = str(value)
            if not self.world.site(site):
                return None
            tot = sum(v["circuits_30"] for v in m["sites"].values())
            share = m["sites"][site]["circuits_30"] / tot if tot else 0.0
            p = 0.8 * share + 0.2 / len(self.world.sites)
            odds = min(25.0, max(1.05, 0.95 / p))
            label = f"swarm chooses {site}"
        elif kind == "by_hour":
            hrs = float(value)
            odds = 1.4 if m["quorum"] else 2.0
            label = f"lift-off by {hrs:g} h"
        elif kind in ("correct", "split"):
            yes = str(value).lower() in ("yes", "true", "1")
            odds = (1.3 if yes else 3.0) if kind == "correct" else (4.0 if yes else 1.15)
            label = ("swarm picks the best site" if kind == "correct" else "the swarm splits") + ("" if yes else ": no")
            value = yes
        else:
            return None
        if m["quorum"]:
            odds = 1 + (odds - 1) * 0.5  # late bets pay less
        self.bankroll -= stake
        p = {"id": len(self.predictions) + 1, "kind": kind, "value": value, "label": label, "stake": stake,
             "odds": round(odds, 2), "t": self.world.t, "status": "open"}
        self.predictions.append(p)
        self._event("prediction", f"bet {stake:.0f} on '{label}' at {odds:.2f}x")
        return p

    def _settle(self):
        o = self.world.outcome
        for p in self.predictions:
            if p["status"] != "open":
                continue
            if p["kind"] == "winner":
                win = bool(o) and o["chosen"] == p["value"]
            elif p["kind"] == "by_hour":
                win = bool(o) and o["t"] <= float(p["value"]) * 60
            elif p["kind"] == "correct":
                win = bool(o) and o["correct"] == p["value"]
            else:
                win = bool(o) and o["split"] == p["value"]
            p["status"] = "won" if win else "lost"
            if win:
                p["payout"] = round(p["stake"] * p["odds"], 1)
                self.bankroll += p["payout"]

    # ------------------------------------------------------------------ end of run
    def _finish(self):
        if self.ended:
            return
        self.ended = True
        w = self.world
        if not w.outcome:
            self._event("timeout", f"no lift-off within {self.cfg['max_hours']:g} h")
        self._settle()
        m = w.metrics()
        self.summary = {"outcome": w.outcome, "decided": bool(w.outcome), "t_end": w.t,
                        "decision_hours": round(w.outcome["t"] / 60, 2) if w.outcome else None,
                        "correct": bool(w.outcome and w.outcome["correct"]),
                        "split": bool(w.outcome and w.outcome["split"]),
                        "discovered": m["discovered"], "sites": [s.public() for s in w.sites],
                        "inference": self.inference(), "bankroll": round(self.bankroll, 1),
                        "scenario": self.cfg["scenario"], "seed": self.cfg["seed"], "policy": self.cfg["policy"]}
        if self.run_dir:
            with open(os.path.join(self.run_dir, "summary.json"), "w") as f:
                json.dump(self.summary, f, indent=1, default=str)
            for f in self._files.values():
                f.close()
            self._files = {}

    def inference(self):
        s = self.stats
        lat = sorted(s["latencies"])

        def q(p):
            return round(lat[min(len(lat) - 1, int(p * len(lat)))], 3) if lat else None
        return {"decisions": s["decisions"], "requests": s["requests"], "completed": s["completed"],
                "failures": s["failures"], "fallbacks": s["fallbacks"], "by_source": s["by_source"],
                "latency_p50": q(0.5), "latency_p95": q(0.95), "input_tokens": s["input_tokens"],
                "cost": round(s["cost"], 5), "models": sorted(s["models"]), "policy": self.cfg["policy"],
                "cost_per_decision": round(s["cost"] / s["completed"], 7) if s["completed"] else None}

    # ------------------------------------------------------------------ viewer
    def scout_pos(self, s):
        w = self.world
        ang = (s.i * 2.399963) % (2 * math.pi)
        r = 18 + (s.i * 7.3) % 30
        home = (r * math.cos(ang), r * math.sin(ang))
        if s.state != "trip":
            return home
        tr = s.trip
        tx, ty = tr["dist"] * math.cos(tr["bearing"]), tr["dist"] * math.sin(tr["bearing"])
        if tr["site"] and tr["found"]:
            site = w.site(tr["site"])
            tx, ty = site.x + 25 * math.cos(ang), site.y + 25 * math.sin(ang)
        t = w.t
        if t < tr["t_arrive"]:
            f = (t - tr["t0"]) / max(1e-6, tr["t_arrive"] - tr["t0"])
        elif t < tr["t_leave"]:
            f = 1.0
        else:
            f = 1.0 - (t - tr["t_leave"]) / max(1e-6, tr["t_back"] - tr["t_leave"])
        f = max(0.0, min(1.0, f))
        return home[0] + (tx - home[0]) * f, home[1] + (ty - home[1]) * f

    def frame(self):
        w = self.world
        m = w.metrics()
        scouts = []
        for s in w.scouts:
            x, y = self.scout_pos(s)
            tgt = (s.dance or {}).get("site") if s.state == "dancing" else (s.trip or {}).get("site")
            scouts.append([s.i, round(x, 1), round(y, 1), s.state[0], tgt, (s.dance or {}).get("circuits", 0),
                           round(s.energy, 2), int(s.stubborn), int(bool(s.misinfo_site)), s.quorum_sensed])
        return {"t": w.t, "max_t": self.cfg["max_hours"] * 60, "paused": self.paused, "ended": self.ended,
                "speed": self.cfg["speed"], "policy": self.cfg["policy"], "sampling": self.cfg["sampling"],
                "sites": [{**s.public(), "color": SITE_COLORS[ord(s.label) - 65 if ord(s.label) - 65 < 10 else 0]}
                          for s in w.sites],
                "scouts": scouts, "metrics": m, "series": self.series[-240:], "events": self.event_tail[-30:],
                "inference": self.inference(), "errors": self.errors[-4:], "outcome": w.outcome,
                "predictions": self.predictions[-12:], "bankroll": round(self.bankroll, 1),
                "run": os.path.basename(self.run_dir or ""), "live": {k: self.cfg[k] for k in LIVE_KEYS}}

    def scout_detail(self, i):
        if not (0 <= i < len(self.world.scouts)):
            return None
        s = self.world.scouts[i]
        traits = [x for x, on in (("stubborn", s.stubborn), ("noisy", s.sd > self.cfg["quality_noise"]),
                                  ("misinformed about " + str(s.misinfo_site), bool(s.misinfo_site)),
                                  ("biased toward " + str(s.bias_site), bool(s.bias_site))) if on]
        return {"scout": i, "state": s.state, "traits": traits, "energy": round(s.energy, 2),
                "last": self.last.get(i), "history": self.history.get(i, []),
                "observation_now": O.observe(self.world, s)}

    def analyst_context(self):
        m = self.world.metrics()
        return {"minute": self.world.t, "sites_truth": [s.public() for s in self.world.sites], "metrics": m,
                "recent_events": self.event_tail[-15:], "outcome": self.world.outcome, "policy": self.cfg["policy"],
                "settings": {k: self.cfg[k] for k in ("n_scouts", "quorum_frac", "dance_bandwidth", "quality_noise",
                                                      "misinfo_frac", "stubborn_frac", "biased_frac",
                                                      "confidence_calibration")}}

    def subscribe(self):
        return self.bus.subscribe()

    def unsubscribe(self, q):
        self.bus.unsubscribe(q)

    def _publish(self, force=False):
        now = time.time()
        if not force and now - self._last_pub < 1 / 15:
            return
        self._last_pub = now
        self.bus.publish(self.frame())
