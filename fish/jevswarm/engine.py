"""Simulation engine: clock, scenarios, decision loop (interactive and controlled), logs, viewer API.

Layers stay separate: world (truth) -> sensors (per-fish frame) -> candidates -> policy
(observation only) -> controller (action + local frames) -> world physics. The evaluator reads the
world for metrics; nothing it computes is sent in a fish request.
"""
import concurrent.futures as cf
import json
import math
import os
import queue
import random
import re
import threading
import time
from datetime import datetime

import numpy as np

from . import candidates as C
from . import controller as ctl
from . import policies
from .config import LIVE_KEYS, coerce
from .metrics import Evaluator
from .sensors import Memory, Tracker, perceive, wrap
from .world import World

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "runs")
FRAME_HZ = 20
SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{6})[A-Za-z0-9_\-*]+")


def pct(xs, q):
    return round(float(np.percentile(xs, q)), 3) if xs else None


class Engine:
    def __init__(self, cfg, realtime=True, run_root=RUNS, log=True):
        self.cfg = coerce(cfg)
        cfg = self.cfg
        if cfg["policy"] == "replay":
            self._prepare_replay(run_root)
            cfg = self.cfg
        self.realtime = realtime
        seed = int(cfg["seed"])
        self.world = World(cfg, np.random.default_rng([seed, 0]))
        n = self.world.n
        self.sensor_rng = [np.random.default_rng([seed, 1, i]) for i in range(n)]
        self.action_rng = [random.Random(seed * 1_000_003 + 7919 * i + 17) for i in range(n)]
        self.event_rng = np.random.default_rng([seed, 3])
        self.trackers = [Tracker() for _ in range(n)]
        self.memories = [Memory(cfg["memory_s"]) if cfg["memory_s"] > 0 else None for _ in range(n)]
        self.frames = {}
        self.actions = [ctl.ActionState(heading=float(self.world.fish_h[i])) for i in range(n)]
        self.prev_action = ["CONTINUE"] * n
        self.last_decision = [None] * n
        self.seq = [0] * n
        self.k = [0] * n
        self.outstanding = [False] * n
        self.dt = 1.0 / cfg["physics_hz"]
        self.tick_n = 0
        self.t = 0.0
        self.sensor_every = max(1, int(round(cfg["physics_hz"] / cfg["sensor_hz"])))
        self.interval = 1.0 / cfg["decision_hz"]
        self.next_dec = [(i / max(n, 1)) * self.interval for i in range(n)]
        self.next_barrier = 0.0
        self.barrier_k = 0
        self.evaluator = Evaluator(self.world, cfg)
        self.results = queue.Queue()
        self.executor = None
        self.policy = None
        self._set_policy(cfg["policy"])
        self.fallback = policies.make(cfg["fallback"], cfg)
        self.stats = {"requests": 0, "completed": 0, "failures": 0, "stale": 0, "superseded": 0,
                      "invalid": 0, "timeouts": 0, "fallbacks": 0, "policy_applied": 0, "applied": 0,
                      "busy_skips": 0, "forced": 0, "input_tokens": 0, "cost": 0.0}
        self.latencies = []
        self.ages = []
        self.applied_times = []
        self.errors = []
        self.model_versions = set()
        self.events = []
        self.cmds = queue.Queue()
        self.paused = False
        self.step_until = None
        self.stopped = False
        self.done = False
        self.attack_started = False
        self.withdrawn = False
        self.subscribers = []
        self.sub_lock = threading.Lock()
        self.lock = threading.RLock()
        self.branch = None           # causal.Branch: replay a recorded prefix, then optionally override one action
        self.applied_log = []
        self.predictions = []
        self.bankroll = 1000.0
        self.pred_id = 0
        self.summary = None
        self.row = {}
        self.run_dir = None
        self.logs = {}
        if log:
            self._open_logs(run_root)
        self._sensor_refresh()
        self.row = self.evaluator.sample(0.0, self._inference_row())

    # ------------------------------------------------------------ setup
    def _prepare_replay(self, run_root):
        run = self.cfg["replay_run"]
        d = run if os.path.isabs(run) else os.path.join(run_root, run)
        with open(os.path.join(d, "config.json")) as f:
            orig = json.load(f)
        keep = {"replay_run": run, "speed": self.cfg["speed"]}
        self.cfg = coerce({**orig, **keep, "policy": "replay", "mode": "controlled"})
        self.replay_dir = d
        self.replay_orig_policy = orig.get("policy")
        self.replay_interventions = {}
        ev = os.path.join(d, "events.jsonl")
        if os.path.exists(ev):
            with open(ev) as f:
                for line in f:
                    e = json.loads(line)
                    if e.get("type") == "intervention" and e.get("cmd"):
                        self.replay_interventions.setdefault(e["tick"], []).append(e["cmd"])

    def _set_policy(self, name):
        self.cfg["policy"] = name
        self.policy = policies.make(name, self.cfg, getattr(self, "replay_dir", None))
        if self.policy.remote and self.executor is None:
            self.executor = cf.ThreadPoolExecutor(max_workers=int(self.cfg["concurrency"]))

    def _open_logs(self, run_root):
        os.makedirs(run_root, exist_ok=True)
        name = f"{datetime.now():%Y%m%d-%H%M%S}_{self.cfg['scenario']}_{self.cfg['policy']}_s{self.cfg['seed']}"
        self.run_dir = os.path.join(run_root, name)
        os.makedirs(self.run_dir, exist_ok=True)
        safe = {k: v for k, v in self.cfg.items()}
        safe["prompt_hash"] = policies.prompt_hash(self.cfg)
        safe["decision_instruction"] = C.instruction(self.cfg)
        with open(os.path.join(self.run_dir, "config.json"), "w") as f:
            json.dump(safe, f, indent=1)
        for k in ("decisions", "events", "metrics"):
            self.logs[k] = open(os.path.join(self.run_dir, f"{k}.jsonl"), "w", buffering=1 << 16)

    def _log(self, kind, obj):
        f = self.logs.get(kind)
        if f:
            f.write(json.dumps(obj, separators=(",", ":"), default=str) + "\n")

    def event(self, text, kind="info", cmd=None, manual=False):
        e = {"t": round(self.t, 2), "tick": self.tick_n, "type": "intervention" if manual else kind, "text": text}
        if cmd is not None:
            e["cmd"] = cmd
        self.events.append(e)
        self._log("events", e)

    # ------------------------------------------------------------ perception and control
    def _sensor_refresh(self):
        w, cfg = self.world, self.cfg
        for i in np.nonzero(w.alive)[0]:
            i = int(i)
            self.frames[i] = perceive(w, i, self.t, self.sensor_rng[i], self.trackers[i],
                                      self.prev_action[i], cfg, self.memories[i])
            self._update_desired(i)
        for i in list(self.frames):
            if not w.alive[i]:
                del self.frames[i]
        w.refresh_predator_vision()
        self.evaluator.on_sensor(self.t, self.frames, self.attack_started)

    def _update_desired(self, i):
        w = self.world
        a = self.actions[i]
        h, v = ctl.desired(a, self.frames[i], w.fish_pos[i], float(w.fish_h[i]), self.cfg, self.t)
        w.des_h[i] = h
        w.des_v[i] = v
        w.recovering[i] = a.kind == "RECOVER"

    def _apply(self, i, cid, cands, frame, source, probs=None, meta=None, obs_t=None, k=None):
        w = self.world
        spec = cands[cid]
        a = ctl.apply(cid, spec, frame, float(w.fish_h[i]), self.t, source)
        self.actions[i] = a
        self.prev_action[i] = cid
        if ctl.is_burst(spec) and not w.burst_ok[i]:
            w.speed_overrides += 1
        self._update_desired(i)
        self.evaluator.note_action(i, spec["kind"])
        self.stats["applied"] += 1
        if source in ("policy", "replay"):
            self.stats["policy_applied"] += 1
            self.applied_times.append(self.t)
        elif source == "fallback":
            self.stats["fallbacks"] += 1
        age = None if obs_t is None else round(self.t - obs_t, 3)
        if age is not None and source == "policy":
            self.ages.append(age)
        rec = {"t": round(self.t, 3), "fish": i, "k": k, "seq": self.seq[i], "source": source,
               "obs_t": None if obs_t is None else round(obs_t, 3), "age": age,
               "obs": frame.obs, "candidates": C.criteria(cands),
               "probs": {kk: round(vv, 4) for kk, vv in (probs or {}).items()},
               "applied": cid}
        if meta:
            for kk in ("raw", "model", "latency", "jev_choice", "error"):
                if kk in meta:
                    rec[kk] = meta[kk]
        self.last_decision[i] = rec
        self.applied_log.append((self.t, i, cid, source))
        self._log("decisions", rec)

    # ------------------------------------------------------------ decisions
    def _decide_local(self, pol, i, frame, cands, k=None):
        if isinstance(pol, policies.Replay):
            r = pol.lookup(i, k, cands)
            if r is None:
                return None
            return r
        return pol.decide(frame.obs, cands, frame.state_json())

    def _remote_call(self, i, seq, k, obs_t, frame, cands):
        t0 = time.time()
        try:
            probs, meta = self.policy.decide(frame.obs, cands, frame.state_json())
            err = None
        except Exception as e:  # noqa: BLE001 - any failure becomes a logged fallback
            probs, meta, err = None, {}, SECRET.sub(r"\1…", f"{type(e).__name__}: {e}")[:300]
        meta["latency"] = round(time.time() - t0, 3)
        return i, seq, k, obs_t, frame, cands, probs, meta, err

    def _request(self, i):
        frame = self.frames.get(i)
        if frame is None:
            return
        cands = C.build(frame.obs)
        self.seq[i] += 1
        k = self.k[i]
        self.k[i] += 1
        if self.policy.remote:
            self.outstanding[i] = True
            self.stats["requests"] += 1
            fut = self.executor.submit(self._remote_call, i, self.seq[i], k, self.t, frame, cands)
            fut.add_done_callback(lambda f: self.results.put(f.result()))
        else:
            out = self._decide_local(self.policy, i, frame, cands, k)
            if out is None:
                probs, meta = self.fallback.decide(frame.obs, cands)
                self._apply(i, policies.sample(probs, self.action_rng[i], True), cands, frame, "fallback",
                            probs, meta, self.t, k)
                return
            probs, meta = out
            cid = policies.sample(probs, self.action_rng[i], self.cfg["sampling"] == "argmax")
            self._apply(i, cid, cands, frame, "replay" if isinstance(self.policy, policies.Replay) else "policy",
                        probs, meta, self.t, k)

    def _handle_result(self, r, barrier=False):
        i, seq, k, obs_t, frame, cands, probs, meta, err = r
        self.outstanding[i] = False
        self.latencies.append(meta.get("latency", 0))
        self.latencies = self.latencies[-5000:]
        u = meta.get("usage") or {}
        self.stats["input_tokens"] += int(u.get("input_tokens") or u.get("prompt_tokens") or 0)
        self.stats["cost"] += float(u.get("cost") or 0)
        if meta.get("model"):
            self.model_versions.add(meta["model"])
        if err:
            self.stats["failures"] += 1
            self.errors.append({"t": round(self.t, 2), "fish": i, "error": err})
            self.errors = self.errors[-50:]
            return False
        self.stats["completed"] += 1
        if not self.world.alive[i]:
            return False
        if not barrier:
            if self.t - obs_t > self.cfg["stale_s"]:
                self.stats["stale"] += 1
                return False
            if seq != self.seq[i]:
                self.stats["superseded"] += 1
                return False
        a = self.actions[i]
        if a.forced_until is not None and self.t < a.forced_until:
            return False
        cid = policies.sample(probs, self.action_rng[i], self.cfg["sampling"] == "argmax")
        spec = cands[cid]
        cur = self.frames.get(i)
        if spec["kind"] == "FOLLOW" and not barrier:
            slots = [e["slot"] for e in frame.obs["visible_fish"]]
            key = frame.fish_keys[slots.index(spec["slot"])]
            if cur is None or key not in cur.fish_keys:
                self.stats["invalid"] += 1
                return False
        self._apply(i, cid, cands, frame, "policy", probs, meta, obs_t, k)
        return True

    def _drain(self):
        while True:
            try:
                r = self.results.get_nowait()
            except queue.Empty:
                return
            self._handle_result(r)

    def _expire(self):
        hold = self.interval * 1.5
        for i in np.nonzero(self.world.alive)[0]:
            i = int(i)
            a = self.actions[i]
            if a.forced_until is not None:
                if self.t < a.forced_until:
                    continue
                a.forced_until = None
                a.t0 = self.t - hold  # forced interval over: let the next decision or fallback take over
            if self.t - a.t0 >= hold and i in self.frames:
                self._fallback(i)

    def _fallback(self, i):
        frame = self.frames[i]
        cands = C.build(frame.obs)
        probs, meta = self.fallback.decide(frame.obs, cands)
        self._apply(i, policies.sample(probs, self.action_rng[i], True), cands, frame, "fallback",
                    probs, meta, self.t)

    def _barrier(self):
        """Controlled mode: snapshot every surviving fish, query independently, apply together."""
        self._sensor_refresh()
        alive = [int(i) for i in np.nonzero(self.world.alive)[0]]
        pending = {}
        applied = []
        for i in alive:
            a = self.actions[i]
            if a.forced_until is not None and self.t < a.forced_until:
                continue
            frame = self.frames[i]
            cands = C.build(frame.obs)
            self.seq[i] += 1
            k = self.barrier_k
            if self.branch is not None:
                pre = self.branch.get(i, k, cands)
                if pre is not None:
                    applied.append((i, pre[0], cands, frame, pre[1], policies.one_hot(cands, pre[0]), {}, k))
                    continue
            if self.policy.remote:
                self.stats["requests"] += 1
                pending[self.executor.submit(self._remote_call, i, self.seq[i], k, self.t, frame, cands)] = (i, frame, cands, k)
            else:
                out = self._decide_local(self.policy, i, frame, cands, k)
                if out is None:
                    probs, meta = self.fallback.decide(frame.obs, cands)
                    applied.append((i, policies.sample(probs, self.action_rng[i], True), cands, frame, "fallback", probs, meta, k))
                else:
                    probs, meta = out
                    cid = policies.sample(probs, self.action_rng[i], self.cfg["sampling"] == "argmax")
                    src = "replay" if isinstance(self.policy, policies.Replay) else "policy"
                    applied.append((i, cid, cands, frame, src, probs, meta, k))
        if pending:
            deadline = time.time() + self.cfg["barrier_deadline_s"]
            left = set(pending)
            while left and time.time() < deadline and not self.stopped:
                done, left = cf.wait(left, timeout=0.05)
                self._process_cmds(barrier=True)
                self._maybe_publish(force=False)
            for fut, (i, frame, cands, k) in pending.items():
                if fut in left:
                    fut.cancel()
                    self.stats["timeouts"] += 1
                    probs, meta = self.fallback.decide(frame.obs, cands)
                    applied.append((i, policies.sample(probs, self.action_rng[i], True), cands, frame, "fallback", probs, meta, k))
                    continue
                r = fut.result()
                _, seq, k2, obs_t, fr, cd, probs, meta, err = r
                ok = self._handle_result_barrier(r)
                if ok is None:
                    probs2, meta2 = self.fallback.decide(frame.obs, cands)
                    applied.append((i, policies.sample(probs2, self.action_rng[i], True), cands, frame, "fallback", probs2, meta2, k))
                else:
                    applied.append((i, ok, cands, frame, "policy", probs, meta, k))
        for (i, cid, cands, frame, src, probs, meta, k) in applied:
            self._apply(i, cid, cands, frame, src, probs, meta, self.t, k)
        self.barrier_k += 1

    def _handle_result_barrier(self, r):
        i, seq, k, obs_t, frame, cands, probs, meta, err = r
        self.latencies.append(meta.get("latency", 0))
        self.latencies = self.latencies[-5000:]
        u = meta.get("usage") or {}
        self.stats["input_tokens"] += int(u.get("input_tokens") or 0)
        self.stats["cost"] += float(u.get("cost") or 0)
        if meta.get("model"):
            self.model_versions.add(meta["model"])
        if err:
            self.stats["failures"] += 1
            self.errors.append({"t": round(self.t, 2), "fish": i, "error": err})
            self.errors = self.errors[-50:]
            return None
        self.stats["completed"] += 1
        return policies.sample(probs, self.action_rng[i], self.cfg["sampling"] == "argmax")

    # ------------------------------------------------------------ scenario
    def _school(self):
        w = self.world
        a = w.alive
        c = w.fish_pos[a].mean(0)
        m = math.atan2(np.sin(w.fish_h[a]).mean(), np.cos(w.fish_h[a]).mean())
        spread = float(np.sqrt(((w.fish_pos[a] - c) ** 2).sum(1).mean()))
        return c, m, spread

    def _clamp(self, p):
        return np.array([min(max(p[0], 2), self.world.w - 2), min(max(p[1], 2), self.world.h - 2)])

    def _start_attack(self):
        self.attack_started = True
        cfg, w = self.cfg, self.world
        scen = cfg["scenario"]
        if not w.alive.any():
            return
        c, m, spread = self._school()
        fwd = np.array([math.cos(m), math.sin(m)])
        side = np.array([-fwd[1], fwd[0]])
        spawns = []
        if scen == "false_alarm":
            i = int(self.event_rng.choice(np.nonzero(w.alive)[0]))
            self.force_burst(i, manual=False)
            return
        rel = w.fish_pos[w.alive] - c

        def beyond(u):
            # just outside the school's extent along direction u, so most fish cannot see it yet
            u = u / (np.linalg.norm(u) + 1e-9)
            p = c + u * (float((rel @ u).max()) + 14)
            if not (2 <= p[0] <= w.w - 2 and 2 <= p[1] <= w.h - 2):
                p2 = c - u * (float((rel @ -u).max()) + 14)
                if 2 <= p2[0] <= w.w - 2 and 2 <= p2[1] <= w.h - 2:
                    return p2
            return p

        for n in range(cfg["n_predators"]):
            if scen == "blind":
                pos = beyond(-fwd) + side * (n * 6)
            elif scen == "rock" and w.rocks:
                rx, ry, rr = min(w.rocks, key=lambda r: math.hypot(r[0] - c[0], r[1] - c[1]))
                u = np.array([rx, ry]) - c
                u = u / (np.linalg.norm(u) + 1e-9)
                pos = np.array([rx, ry]) + u * (rr + 2.5) + side * (n * 5)
            else:
                pos = beyond(side * (1 if n % 2 == 0 else -1))
            pos = self._clamp(pos)
            spawns.append(pos)
        for pos in spawns:
            d = c - pos
            p = w.add_predator(pos, math.atan2(d[1], d[0]))
            self.event(f"Predator {p.pid} enters at ({pos[0]:.0f}, {pos[1]:.0f}) [{scen}]", "scenario")

    def _withdraw(self):
        self.withdrawn = True
        for p in self.world.predators:
            if p.active:
                p.mode = "withdraw"
        self.evaluator.withdraw_t = self.t
        self.event("Predators withdraw", "scenario")

    def force_burst(self, i, manual=True, secs=2.0):
        frame = self.frames.get(i)
        if frame is None or not self.world.alive[i]:
            return
        cands = C.build(frame.obs)
        self._apply(i, "BURST_F", cands, frame, "forced")
        self.actions[i].forced_until = self.t + secs
        self.stats["forced"] += 1
        self.event(f"Fish {i} forced to burst for {secs:.0f} s (false alarm)", "scenario",
                   cmd={"op": "false_alarm", "fish": i} if manual else None, manual=manual)

    # ------------------------------------------------------------ commands from the viewer
    def command(self, cmd):
        self.cmds.put(cmd)

    def _process_cmds(self, barrier=False):
        while True:
            try:
                cmd = self.cmds.get_nowait()
            except queue.Empty:
                return
            try:
                self._do_cmd(cmd)
            except Exception as e:  # noqa: BLE001
                self.event(f"Command failed: {cmd.get('op')}: {e}", "error")

    def _do_cmd(self, cmd):
        op = cmd.get("op")
        w = self.world
        if op == "pause":
            self.paused = True
        elif op == "resume":
            self.paused = False
            self.step_until = None
            self._anchor()
        elif op == "step":
            self.paused = False
            self.step_until = self.t + float(cmd.get("secs", self.interval))
            self._anchor()
        elif op == "set":
            k, v = cmd["key"], cmd["value"]
            if k not in LIVE_KEYS:
                return
            old = self.cfg[k]
            new = coerce({"scenario": self.cfg["scenario"], k: v})[k]
            if k == "policy":
                if new == "replay":
                    return
                self._set_policy(new)
            self.cfg[k] = new
            if k == "speed":
                self._anchor()
                return
            self.event(f"Set {k}: {old} -> {new}", cmd=cmd, manual=True)
        elif op == "place_predator":
            pos = self._clamp((float(cmd["x"]), float(cmd["y"])))
            h = float(cmd.get("heading", math.atan2(w.h / 2 - pos[1], w.w / 2 - pos[0])))
            p = w.add_predator(pos, h)
            self.attack_started = True
            self.event(f"Predator {p.pid} placed at ({pos[0]:.0f}, {pos[1]:.0f})", cmd=cmd, manual=True)
        elif op == "withdraw":
            self._withdraw()
            self.events[-1]["type"] = "intervention"
        elif op == "add_rock":
            w.add_rock(cmd["x"], cmd["y"], cmd.get("r", 2.5))
            self.event(f"Rock added at ({cmd['x']:.0f}, {cmd['y']:.0f})", cmd=cmd, manual=True)
        elif op == "false_alarm":
            i = cmd.get("fish")
            if i is None:
                i = int(self.event_rng.choice(np.nonzero(w.alive)[0]))
            self.force_burst(int(i), manual=True)
        elif op == "stop":
            self.stopped = True

    # ------------------------------------------------------------ predictions (speculation)
    PRED_KINDS = {
        "survivors_end": "Survivors at the end",
        "captures_by": "Captures by time T",
        "lcf_end": "Largest group fraction at the end",
        "polarization_end": "Polarization at the end",
        "recovers": "School recovers after withdrawal (1 = yes)",
    }

    def add_prediction(self, kind, op, value, stake, at=None):
        with self.lock:
            if kind not in self.PRED_KINDS or op not in (">=", "<=") or self.done:
                return None
            stake = max(1.0, min(float(stake), self.bankroll))
            if stake <= 0:
                return None
            self.bankroll -= stake
            self.pred_id += 1
            remaining = max(0.0, 1 - self.t / self.cfg["episode_s"])
            p = {"id": self.pred_id, "kind": kind, "op": op, "value": float(value), "stake": stake,
                 "made_t": round(self.t, 1), "at": float(at) if at not in (None, "") else None,
                 "odds": round(1 + remaining, 2), "status": "open"}
            self.predictions.append(p)
            self.event(f"Prediction #{p['id']}: {self.PRED_KINDS[kind]} {op} {value} (stake {stake:.0f})", "prediction")
            return p

    def _resolve_predictions(self, final=False):
        s = self.row
        for p in self.predictions:
            if p["status"] != "open":
                continue
            val = None
            if p["kind"] == "captures_by" and p["at"] is not None and self.t >= p["at"]:
                val = s["captures"]
            elif final:
                val = {"survivors_end": s["alive"], "lcf_end": s["largest_component"],
                       "polarization_end": s["polarization"], "captures_by": s["captures"],
                       "recovers": 1.0 if self.evaluator.recover_t is not None else 0.0}[p["kind"]]
            if val is None:
                continue
            ok = val >= p["value"] if p["op"] == ">=" else val <= p["value"]
            p["actual"] = val
            p["status"] = "won" if ok else "lost"
            if ok:
                p["payout"] = round(p["stake"] * (1 + p["odds"]), 1)
                self.bankroll += p["payout"]
            self.event(f"Prediction #{p['id']} {p['status']} (actual {val})", "prediction")

    # ------------------------------------------------------------ main loop
    def _anchor(self):
        self.wall0 = time.time()
        self.sim0 = self.t

    def tick(self):
        cfg = self.cfg
        self.tick_n += 1
        self.t = self.tick_n * self.dt
        if hasattr(self, "replay_interventions"):
            for c in self.replay_interventions.get(self.tick_n, []):
                self._do_cmd(c)
        if not self.attack_started and cfg["attack_s"] >= 0 and self.t >= cfg["attack_s"]:
            self._start_attack()
        if cfg["withdraw_s"] > 0 and not self.withdrawn and self.t >= cfg["withdraw_s"] and self.attack_started:
            self._withdraw()
        if cfg["mode"] == "controlled":
            if self.t + 1e-9 >= self.next_barrier:
                self._barrier()
                self.next_barrier += self.interval
            elif self.tick_n % self.sensor_every == 0:
                self._sensor_refresh()
            self._expire_forced_only()
        else:
            if self.tick_n % self.sensor_every == 0:
                self._sensor_refresh()
            for i in np.nonzero(self.world.alive)[0]:
                i = int(i)
                if self.t >= self.next_dec[i]:
                    self.next_dec[i] += self.interval
                    if self.outstanding[i]:
                        self.stats["busy_skips"] += 1
                    elif self.actions[i].forced_until is None:
                        self._request(i)
            self._drain()
            self._expire()
        self.world.step(self.dt, self.t)
        if self.tick_n % (cfg["physics_hz"] // 2 or 1) == 0:
            self.row = self.evaluator.sample(self.t, self._inference_row())
            self._log("metrics", self.row)
            self._resolve_predictions()

    def _expire_forced_only(self):
        for i in np.nonzero(self.world.alive)[0]:
            a = self.actions[int(i)]
            if a.forced_until is not None and self.t >= a.forced_until:
                a.forced_until = None

    def _inference_row(self):
        s = self.stats
        n_alive = max(int(self.world.alive.sum()), 1)
        recent = [x for x in self.applied_times if self.t - x <= 5.0]
        self.applied_times = recent
        span = min(5.0, max(self.t, 1e-9))
        return {
            "achieved_hz": round(len(recent) / span / n_alive, 3),
            "latency_p50": pct(self.latencies[-500:], 50),
            "latency_p95": pct(self.latencies[-500:], 95),
            "decision_age": round(float(np.mean(self.ages[-500:])), 3) if self.ages else None,
            "fallback_frac": round(s["fallbacks"] / max(s["applied"], 1), 3),
            "in_flight": sum(self.outstanding),
        }

    def inference_summary(self):
        s = dict(self.stats)
        s["cost"] = round(s["cost"], 5)
        s.update({
            "policy": self.cfg["policy"], "mode": self.cfg["mode"],
            "latency_p50": pct(self.latencies, 50), "latency_p95": pct(self.latencies, 95),
            "latency_p99": pct(self.latencies, 99),
            "mean_decision_age": round(float(np.mean(self.ages)), 3) if self.ages else None,
            "fallback_fraction": round(s["fallbacks"] / max(s["applied"], 1), 3),
            "policy_fraction": round(s["policy_applied"] / max(s["applied"], 1), 3),
            "model_versions": sorted(self.model_versions),
            "prompt_hash": policies.prompt_hash(self.cfg),
        })
        return s

    def run(self):
        """Real-time loop (viewer). Returns when the episode ends or is stopped."""
        self._anchor()
        last_pub = 0.0
        while not self.stopped:
            self._process_cmds()
            if self.done:
                self._maybe_publish(force=True)
                time.sleep(0.1)
                continue
            if self.paused:
                self._maybe_publish(force=True)
                time.sleep(0.05)
                self._anchor()
                continue
            with self.lock:
                self.tick()
            if self.step_until is not None and self.t >= self.step_until:
                self.step_until = None
                self.paused = True
            if self.t >= self.cfg["episode_s"] or not self.world.alive.any():
                self.finish()
            if self.realtime:
                lead = (self.t - self.sim0) / max(self.cfg["speed"], 1e-3) - (time.time() - self.wall0)
                if lead > 0.002:
                    time.sleep(lead)
                elif lead < -0.5:
                    self._anchor()
            now = time.time()
            if now - last_pub >= 1 / FRAME_HZ:
                last_pub = now
                self._maybe_publish(force=True)
        self.close()

    def run_headless(self, until=None):
        until = until or self.cfg["episode_s"]
        while self.t < until and self.world.alive.any() and not self.stopped:
            self.tick()
        self.finish()
        self.close()
        return self.summary

    def finish(self):
        if self.done:
            return
        self.done = True
        # interactive: collect in-flight results so logs are complete
        self.row = self.evaluator.sample(self.t, self._inference_row())
        self._resolve_predictions(final=True)
        self.summary = self.evaluator.summary(self.t, self.inference_summary())
        self.summary["scenario"] = self.cfg["scenario"]
        self.summary["seed"] = self.cfg["seed"]
        self.summary["predictions_bankroll"] = round(self.bankroll, 1)
        self.event(f"Episode ended at {self.t:.1f} s: {self.summary['survivors']} survivors, "
                   f"{self.summary['captures']} captures", "end")
        if self.run_dir:
            with open(os.path.join(self.run_dir, "summary.json"), "w") as f:
                json.dump(self.summary, f, indent=1, default=str)

    def close(self):
        for f in self.logs.values():
            try:
                f.flush()
                f.close()
            except ValueError:
                pass
        self.logs = {}
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------ viewer output
    def subscribe(self):
        q = queue.Queue(maxsize=4)
        with self.sub_lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self.sub_lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def _maybe_publish(self, force=False):
        if not self.subscribers:
            return
        msg = json.dumps(self.frame(), separators=(",", ":"), default=str)
        with self.sub_lock:
            for q in self.subscribers:
                if q.full():
                    try:
                        q.get_nowait()
                    except queue.Empty:
                        pass
                q.put_nowait(msg)

    def frame(self):
        w = self.world
        fish = []
        for i in np.nonzero(w.alive)[0]:
            i = int(i)
            a = self.actions[i]
            fish.append([i, round(float(w.fish_pos[i, 0]), 2), round(float(w.fish_pos[i, 1]), 2),
                         round(float(w.fish_h[i]), 3), round(float(w.fish_v[i]), 2),
                         round(float(w.fish_e[i]), 2), a.kind, a.source])
        preds = [[p.pid, round(float(p.pos[0]), 2), round(float(p.pos[1]), 2), round(float(p.heading), 3), p.mode,
                  p.target] for p in w.predators if p.active]
        return {
            "t": round(self.t, 2), "episode_s": self.cfg["episode_s"], "paused": self.paused, "done": self.done,
            "fish": fish, "preds": preds, "rocks": w.rocks, "food": w.food, "w": w.w, "h": w.h,
            "captures": [[round(c[0], 1), c[1]] for c in w.captures[-20:]],
            "row": self.row, "series": self.evaluator.series[-400:][::2] if self.tick_n % 30 == 0 else None,
            "stats": self.inference_summary(), "events": self.events[-40:], "errors": self.errors[-5:],
            "predictions": self.predictions, "bankroll": round(self.bankroll, 1),
            "cfg": {k: self.cfg[k] for k in LIVE_KEYS | {"mode", "scenario", "n_fish", "decision_hz",
                                                          "attack_s", "withdraw_s", "seed"}},
            "run_dir": os.path.basename(self.run_dir) if self.run_dir else None,
            "summary": self.summary,
        }

    def fish_detail(self, i):
        """Viewer-only inspector for one fish: its exact observation plus ground-truth context."""
        w, cfg = self.world, self.cfg
        with self.lock:
            if i < 0 or i >= w.n:
                return None
            frame = self.frames.get(i)
            me, hd = w.fish_pos[i].copy(), float(w.fish_h[i])
            R = cfg["vision_range"] * (1 - cfg["turbidity"])
            ch, sh = math.cos(hd), math.sin(hd)
            half = math.radians(cfg["fov_deg"]) / 2

            def body(x, y):
                dx, dy = x - me[0], y - me[1]
                return round(dx * ch + dy * sh, 2), round(-dx * sh + dy * ch, 2)

            vis_f = set(frame.fish_keys) if frame else set()
            vis_p = set(frame.pred_keys) if frame else set()
            ents = []
            for j in w.grid_query(me, R + 4):
                if j == i or not w.alive[j]:
                    continue
                bx, by = body(*w.fish_pos[j])
                rr, bb = math.hypot(bx, by), math.atan2(by, bx)
                status = "visible" if ("f", j) in vis_f else ("outside" if rr > R or abs(bb) > half else "hidden")
                ents.append({"kind": "fish", "id": j, "x": bx, "y": by, "h": round(wrap(float(w.fish_h[j]) - hd), 3),
                             "status": status,
                             "slot": f"n{frame.fish_keys.index(('f', j))}" if status == "visible" else None})
            for p in w.predators:
                if not p.active:
                    continue
                bx, by = body(*p.pos)
                rr, bb = math.hypot(bx, by), math.atan2(by, bx)
                if rr > R + 8:
                    continue
                status = "visible" if ("p", p.pid) in vis_p else ("outside" if rr > R or abs(bb) > half else "hidden")
                ents.append({"kind": "predator", "id": p.pid, "x": bx, "y": by, "h": round(wrap(p.heading - hd), 3),
                             "status": status,
                             "slot": f"p{frame.pred_keys.index(('p', p.pid))}" if status == "visible" else None})
            rocks = []
            for (x, y, r) in w.rocks:
                bx, by = body(x, y)
                if math.hypot(bx, by) - r <= R + 4:
                    rocks.append([bx, by, r])
            a = self.actions[i]
            return {
                "fish": i, "alive": bool(w.alive[i]), "t": round(self.t, 2),
                "energy": round(float(w.fish_e[i]), 3), "speed": round(float(w.fish_v[i]), 2),
                "burst_ok": bool(w.burst_ok[i]),
                "action": {"id": a.cid, "kind": a.kind, "source": a.source, "since": round(a.t0, 2)},
                "observation": frame.obs if frame else None,
                "candidates": C.criteria(C.build(frame.obs)) if frame else {},
                "last_decision": self.last_decision[i],
                "view": {"range": R, "fov_deg": cfg["fov_deg"], "entities": ents, "rocks": rocks,
                         "fish_r": w.fish_r, "pred_r": cfg["pred_radius"]},
            }

    def analyst_context(self):
        s = self.evaluator.series
        step = max(1, len(s) // 40)
        return {"config": {k: self.cfg[k] for k in ("scenario", "policy", "mode", "n_fish", "n_predators",
                                                    "vision_range", "fov_deg", "attack_s", "withdraw_s")},
                "t": round(self.t, 1), "metrics_series": s[::step], "latest": self.row,
                "events": self.events[-30:], "inference": self.inference_summary()}
