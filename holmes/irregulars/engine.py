"""Run loop for both modes: pacing, pause/step, live knobs, player deductions, logging and viewer frames.

Solo: one step = one detective decision (a visit or the accusation).
Swarm: one step = one tick; every free Irregular decides, remote calls go out together (up to `concurrency`), each
with a hard deadline, and an Irregular whose call fails or is too slow uses the reflex rule for that tick.
"""
import json
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

from swarmcore.web import Broadcaster, redact

from . import solo as S
from . import swarm as W
from .case import Case
from .config import LIVE_KEYS, coerce

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "runs")


class Engine:
    def __init__(self, cfg, realtime=True, log=True, runs_dir=None):
        self.cfg = coerce(cfg)
        c = self.cfg
        self.realtime = realtime
        self.case = Case(c)
        self.mode = c["mode"]
        self.policy_name = c["policy"] if self.mode == "solo" else c["swarm_policy"]
        if self.mode == "solo":
            self.game = S.SoloGame(self.case, c)
            self.policy = S.make(c["policy"], c)
            self.fallback = S.Rule(c)
        else:
            self.game = W.SwarmGame(self.case, c)
            self.policy = W.JevIrregular(c) if c["swarm_policy"] == "jev" else None
        self.pool = ThreadPoolExecutor(max_workers=max(1, c["concurrency"]))
        self.bus = Broadcaster()
        self.cmds = queue.Queue()
        self.paused = False
        self.step_req = 0
        self.stopped = False
        self.ended = False
        self.stats = {"decisions": 0, "calls": 0, "failures": 0, "fallbacks": 0, "timeouts": 0, "in": 0, "out": 0,
                      "cached": 0, "cost": 0.0, "latencies": [], "models": set(), "by_source": {}}
        self.capped = False
        self.errors = []
        self._lock = threading.Lock()
        self.last = None             # solo: last decision; swarm: per-Irregular last decision
        self.swarm_last = {}
        self.event_tail = []
        self.guesses = []
        self.summary = None
        self._last_pub = 0.0
        self.run_dir = None
        self._files = {}
        if log:
            os.makedirs(runs_dir or RUNS, exist_ok=True)
            name = f"{time.strftime('%Y%m%d-%H%M%S')}_{self.mode}_{self.policy_name}_s{c['seed']}"
            self.run_dir = os.path.join(runs_dir or RUNS, name)
            os.makedirs(self.run_dir, exist_ok=True)
            safe = {k: v for k, v in c.items() if not k.endswith("_key")}
            with open(os.path.join(self.run_dir, "config.json"), "w") as f:
                json.dump({"cfg": safe, "instruction": S.INSTRUCTION if self.mode == "solo" else W.INSTRUCTION},
                          f, indent=1)
            with open(os.path.join(self.run_dir, "case.json"), "w") as f:
                json.dump({"brief": self.case.brief(), "map": self.case.public_map(), "secret": self.case.secret(),
                           "leads": self.case.leads}, f, indent=1)
            for k in ("decisions", "events"):
                self._files[k] = open(os.path.join(self.run_dir, f"{k}.jsonl"), "w", buffering=1)
        brief = self.case.brief()
        self._event("case", brief["victim"])
        if self.mode == "solo":
            self._event("start", f"{self.policy_name} starts at 221B Baker Street with {c['visit_budget']} visits "
                                 f"and {c['deadline_hours']:g} h")
            self._event("lead", self.game.notebook[0]["text"], {"address": self.game.at})
        else:
            g = self.game
            self._event("start", f"{len(g.irr)} Irregulars ({self.policy_name}), quorum {g.quorum_need()}, "
                                 f"{c['swarm_ticks']} ticks of {c['tick_min']:g} min")

    # ------------------------------------------------------------------ logging
    def _write(self, kind, obj):
        f = self._files.get(kind)
        if f:
            f.write(json.dumps(obj, default=str) + "\n")

    def _event(self, kind, detail, extra=None):
        e = {"t": round(self.game.minute, 1), "kind": kind, "detail": detail}
        if extra:
            e.update(extra)
        self.event_tail = (self.event_tail + [e])[-80:]
        self._write("events", e)

    def _account(self, meta, lat, source="policy"):
        with self._lock:
            s = self.stats
            s["decisions"] += 1
            s["by_source"][source] = s["by_source"].get(source, 0) + 1
            if source == "policy" and getattr(self.policy, "remote", True) and meta:
                s["calls"] += 1
                s["latencies"].append(lat)
                s["in"] += meta.get("in", 0)
                s["out"] += meta.get("out", 0)
                s["cached"] += meta.get("cached", 0)
                s["cost"] += meta.get("cost", 0.0)
                if meta.get("model"):
                    s["models"].add(meta["model"])

    def _late(self, fu):
        """A call that missed its tick still costs money: count it."""
        if not fu.cancelled() and fu.exception() is None:
            meta = fu.result()[2]
            with self._lock:
                self.stats["cost"] += meta.get("cost", 0.0)
                self.stats["in"] += meta.get("in", 0)
                self.stats["out"] += meta.get("out", 0)

    def _fail(self, e):
        msg = redact(f"{type(e).__name__}: {e}")[:240]
        with self._lock:
            self.stats["failures"] += 1
            self.errors = (self.errors + [msg])[-6:]

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
                self.step()
                self._publish(force=True)
                time.sleep(max(0.0, 1.0 / max(0.05, self.cfg["speed"]) - (time.time() - w0)))
            self._publish(force=True)
        except Exception as e:  # noqa: BLE001
            self.errors.append(redact(f"engine crashed: {type(e).__name__}: {e}"))
            self._publish(force=True)
            raise
        finally:
            self.pool.shutdown(wait=False)

    def run_all(self):
        while not self.ended:
            self.step()
        self.pool.shutdown(wait=False)
        return self.summary

    def step(self):
        if self.ended:
            return
        if self.mode == "solo":
            self._solo_step()
        else:
            self._swarm_step()
        if self.game.ended:
            self._finish()

    # ------------------------------------------------------------------ solo
    def _solo_decide(self, final=False):
        t0 = time.time()
        try:
            d = self.policy.decide(self.game, final=final)
            self._account(d.get("meta"), time.time() - t0)
            return d, "policy"
        except Exception as e:  # noqa: BLE001
            self._fail(e)
            d = self.fallback.decide(self.game, final=final)
            self.stats["fallbacks"] += 1
            self._account({}, 0, "fallback")
            return d, "fallback"

    def _solo_step(self):
        g = self.game
        d, src = self._solo_decide()
        act = d["action"]
        rec = {"step": g.visits, "minute": g.minute, "source": src, "action": act, "pick": d["pick"],
               "note": d.get("note"), "action_probs": d.get("action_probs"), "ready": d.get("ready"),
               "belief": {k: {x: round(p, 3) for x, p in v.items()} for k, v in d["belief"].items()},
               "meta": d.get("meta")}
        self.last = rec
        self._write("decisions", rec)
        if act and act.startswith("VISIT_"):
            a = act[6:]
            lead = g.visit(a)
            self._event("lead", lead["text"], {"address": a, "visit": g.visits})
            return
        forced = act != "ACCUSE" or not g.reachable()
        if act != "ACCUSE":  # out of visits or time: one last call for the accusation
            d2, _ = self._solo_decide(final=True)
            d = {**d, "pick": d2["pick"], "belief": d2["belief"]}
            self.last = {**rec, "pick": d2["pick"], "belief": d["belief"]}
        acc = g.accuse(d["pick"]["culprit"], d["pick"]["motive"], d["pick"]["hideout"], forced=forced)
        self.last["belief"] = {k: {x: round(p, 3) for x, p in v.items()} for k, v in d["belief"].items()}
        self._event("accuse", self._acc_text(acc), {"accusation": acc})

    def _acc_text(self, acc):
        c = self.case
        s = c.suspect(acc["culprit"])
        h = c.hideout(acc["hideout"])
        mark = lambda k: "right" if acc["ok"][k] else "wrong"  # noqa: E731
        return (f"{'Forced to accuse' if acc.get('forced') else 'Accuses'}: {s['name'] if s else acc['culprit']} "
                f"({mark('culprit')}), motive {acc['motive']} ({mark('motive')}), hideout "
                f"{c.label(h['address']) if h else acc['hideout']} ({mark('hideout')})")

    # ------------------------------------------------------------------ swarm
    def _swarm_step(self):
        g, c = self.game, self.cfg
        due = g.begin_tick()
        jobs = []
        for a in due:
            cands = g.candidates(a)
            f = g.forced(a, cands)
            jobs.append((a, cands, f))
        results = {}
        if self.policy and not self.capped:
            futs = {}
            for a, cands, f in jobs:
                if f is None:
                    futs[a.i] = (time.time(), self.pool.submit(self.policy.decide, g, a, cands))
            done, _ = wait([fu for _, fu in futs.values()], timeout=c["request_timeout_s"] + 1.0)
            for i, (t0, fu) in futs.items():
                if fu in done and fu.exception() is None:
                    results[i] = fu.result() + (time.time() - t0,)
                elif fu in done:
                    self._fail(fu.exception())
                else:
                    fu.cancel()
                    self.stats["timeouts"] += 1
                    fu.add_done_callback(self._late)
        for a, cands, f in jobs:
            meta, src, counted = {}, "policy", False
            if f is not None:
                act, vote, src = f, None, "liar"
            elif a.i in results:
                act, vote, meta, lat = results[a.i]
                if act not in cands:
                    act, vote2 = g.reflex(a, cands)
                    src = "fallback"
                self._account(meta, lat, "policy")
                counted = True
            elif self.policy_name == "random":
                act, vote = g.randomly(a, cands)
                src = "random"
            else:
                act, vote = g.reflex(a, cands)
                src = "rule" if self.policy_name == "rule" else ("capped" if self.capped else "fallback")
                if src in ("fallback", "capped"):
                    self.stats["fallbacks"] += 1
            if not counted:
                self._account({}, 0, src)
            g.apply(a, act, vote or {"culprit": None, "motive": None, "hideout": None})
            self.swarm_last[a.i] = {"tick": g.tick, "action": act, "vote": dict(a.vote), "source": src,
                                    "result": a.last_result}
            self._write("decisions", {"tick": g.tick, "irr": a.i, "action": act, "vote": a.vote, "source": src,
                                      "meta": meta})
        if c["budget_cap_usd"] > 0 and not self.capped and self.stats["cost"] >= c["budget_cap_usd"]:
            self.capped = True
            self._event("budget", f"swarm spent ${self.stats['cost']:.4f}: cap reached, reflex rule from now on")
        g.end_tick()
        top = g.tally()[:1]
        if top and g.tick % 2 == 0:
            (cu, mo, hi), n = top[0]
            self._event("tally", f"tick {g.tick}: leading answer {cu}/{mo}/{hi} with {n} votes "
                                 f"(quorum {g.quorum_need()})")
        if g.ended:
            o = g.outcome
            if o["quorum"]:
                self._event("accuse", f"Quorum: {o['votes']} Irregulars agree on {o['culprit']}/{o['motive']}/"
                                      f"{o['hideout']}: " + ", ".join(f"{k} {'right' if v else 'wrong'}"
                                                                      for k, v in o["ok"].items()))
            else:
                self._event("timeout", f"The case went cold after {g.tick} ticks: no quorum (best {o['votes']} of "
                                       f"{o['need']} votes)")

    # ------------------------------------------------------------------ commands
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
                self.step_req += int(cmd.get("n") or 1)
            elif op == "stop":
                self.stopped = True
            elif op == "set" and cmd.get("key") in LIVE_KEYS:
                k = cmd["key"]
                self.cfg[k] = coerce({**self.cfg, k: cmd.get("value")})[k]
                if k != "speed":
                    self._event("intervention", f"set {k} = {self.cfg[k]}")

    def add_guess(self, body):
        if self.ended:
            return None
        g = {k: body.get(k) for k in ("culprit", "motive", "hideout")}
        if not all(g.values()):
            return None
        g.update({"id": len(self.guesses) + 1, "minute": self.game.minute,
                  "progress": self.game.visits if self.mode == "solo" else self.game.tick, "status": "open"})
        self.guesses.append(g)
        self._event("guess", f"you guess {g['culprit']}/{g['motive']}/{g['hideout']}")
        return g

    # ------------------------------------------------------------------ end of run
    def _finish(self):
        if self.ended:
            return
        self.ended = True
        t = self.case.truth_ids()
        for gs in self.guesses:
            gs["ok"] = {k: gs[k] == t[k] for k in t}
            gs["status"] = f"{sum(gs['ok'].values())}/3"
        g = self.game
        o = g.accusation if self.mode == "solo" else g.outcome
        self.summary = {"mode": self.mode, "policy": self.policy_name, "seed": self.cfg["seed"], "outcome": o,
                        "solved": bool(o and o["solved"]), "parts": o["parts"] if o else 0,
                        "truth": t, "solvable": self.case.solvable, "minutes": round(g.minute, 1),
                        "inference": self.inference(), "guesses": self.guesses}
        if self.mode == "solo":
            self.summary["visits"] = g.visits
        else:
            self.summary.update({"ticks": g.tick, "coverage": g.coverage(), "series": g.series,
                                 "n_irregulars": len(g.irr)})
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
        return {"decisions": s["decisions"], "calls": s["calls"], "failures": s["failures"],
                "fallbacks": s["fallbacks"], "timeouts": s["timeouts"], "by_source": s["by_source"],
                "latency_p50": q(0.5), "latency_p95": q(0.95), "tokens_in": s["in"], "tokens_out": s["out"],
                "tokens_cached": s["cached"], "cost": round(s["cost"], 5), "models": sorted(s["models"]),
                "policy": self.policy_name, "capped": self.capped}

    # ------------------------------------------------------------------ viewer
    def frame(self, full=False):
        g = self.game
        f = {"mode": self.mode, "policy": self.policy_name, "minute": g.minute, "paused": self.paused,
             "ended": self.ended, "speed": self.cfg["speed"], "events": self.event_tail[-40:],
             "inference": self.inference(), "errors": self.errors[-4:], "guesses": self.guesses,
             "run": os.path.basename(self.run_dir or ""), "live": {k: self.cfg[k] for k in LIVE_KEYS},
             "summary": self.summary}
        if full or self.ended:
            f["case"] = {"brief": self.case.brief(), "map": self.case.public_map()}
        if self.ended:
            f["secret"] = self.case.secret()
        if self.mode == "solo":
            f.update({"at": g.at, "path": g.path, "visits": g.visits, "budget": self.cfg["visit_budget"],
                      "deadline": self.cfg["deadline_hours"] * 60, "notebook": g.notebook, "last": self.last,
                      "accusation": g.accusation})
        else:
            irr = []
            for a in g.irr:
                x, y = g.pos(a)
                v = a.vote
                irr.append([a.i, round(x, 1), round(y, 1), v["culprit"], v["motive"], v["hideout"],
                            int(a.liar) | (2 * int(a.stubborn)) | (4 * int(a.misinformed)),
                            (a.last_action or "").split("_")[0], bool(a.tailing)])
            f.update({"tick": g.tick, "ticks": self.cfg["swarm_ticks"], "irregulars": irr, "shares": g.shares,
                      "comm_range": self.cfg["comm_range"], "tally": [[list(k), n] for k, n in g.tally()[:8]],
                      "parts": {k: g.part_tally(k) for k in ("culprit", "motive", "hideout")},
                      "need": g.quorum_need(), "series": g.series, "coverage": g.coverage(),
                      "outcome": g.outcome})
        return f

    def irregular_detail(self, i):
        g = self.game
        if self.mode != "swarm" or not (0 <= i < len(g.irr)):
            return None
        a = g.irr[i]
        traits = [t for t, on in (("liar", a.liar), ("stubborn", a.stubborn), ("misinformed", a.misinformed)) if on]
        return {"irregular": i, "traits": traits, "last": self.swarm_last.get(i), "vote": a.vote,
                "observation": g.observation(a), "candidates": g.candidates(a)}

    def solo_observation(self):
        return self.game.observation() if self.mode == "solo" else None

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
