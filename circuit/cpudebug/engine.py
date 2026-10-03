"""Run loop for the three families: ticks, pacing, pause/step, budgets, model calls, logging and viewer frames.

One tick is `tick_min` case minutes (15). The time limit is `deadline_hours` for every family. Solo spends one tick
per probe (plus walking); Baker Street and the swarm act in parallel, one action per agent per tick.
"""
import json
import os
import queue
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from swarmcore.llm import LLMError
from swarmcore.web import Broadcaster, redact

from . import kb
from .case import Case
from .config import LIVE_KEYS, coerce
from .leader import BakerStreet
from .solo import Solo
from .swarm import Swarm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "runs")


class Stop(Exception):
    pass


def setting_name(c):
    if c["mode"] == "solo":
        return f"solo_{c['solo_policy']}"
    if c["mode"] == "leader":
        return f"baker_{c['holmes']}_{c['boy_policy']}" + ("" if c["wiggins"] else "_nowiggins")
    return f"swarm_{c['swarm_policy']}_r{c['comm_range']}"


class Engine:
    def __init__(self, cfg, realtime=True, log=True, runs_dir=None):
        self.cfg = coerce(cfg)
        c = self.cfg
        self.realtime = realtime
        self.mode = c["mode"]
        self.setting = setting_name(c)
        self.case = Case(c)
        self.deadline = max(1, int(round(c["deadline_hours"] * 60 / c["tick_min"])))
        self.prng = random.Random(f"probe-{c['seed']}")
        self.pool = ThreadPoolExecutor(max_workers=max(1, c["concurrency"]))
        self.bus = Broadcaster()
        self.cmds = queue.Queue()
        self.paused = False
        self.step_req = 0
        self.stopped = False
        self.ended = False
        self.stats = {"calls": 0, "failures": 0, "fallbacks": 0, "in": 0, "out": 0, "cached": 0, "cost": 0.0,
                      "latencies": [], "models": set()}
        self.probes = []
        self.events = []
        self.result = None
        self.guesses = []
        self.errors = []
        self.summary = None
        self.t0 = time.time()
        self.t_answer = None
        self._lock = threading.Lock()
        self.run_dir = None
        self._ev = None
        if log:
            os.makedirs(runs_dir or RUNS, exist_ok=True)
            name = f"{time.strftime('%Y%m%d-%H%M%S')}_{self.setting}_s{c['seed']}"
            self.run_dir = os.path.join(runs_dir or RUNS, name)
            os.makedirs(self.run_dir, exist_ok=True)
            with open(os.path.join(self.run_dir, "config.json"), "w") as f:
                json.dump({k: v for k, v in c.items() if not k.endswith("_key")}, f, indent=1)
            self._ev = open(os.path.join(self.run_dir, "events.jsonl"), "w", buffering=1)
        self.game = {"solo": Solo, "leader": BakerStreet, "swarm": Swarm}[self.mode](self)

    # ------------------------------------------------------------------ services for the games
    def over_budget(self):
        return self.stats["cost"] >= self.cfg["budget_usd"]

    def account(self, meta, latency=None):
        if not meta:
            return
        with self._lock:
            s = self.stats
            s["calls"] += 1
            s["in"] += meta.get("in", 0)
            s["out"] += meta.get("out", 0)
            s["cached"] += meta.get("cached", 0)
            s["cost"] += meta.get("cost", 0.0)
            if meta.get("model"):
                s["models"].add(meta["model"])
            if latency is not None:
                s["latencies"].append(latency)

    def failure(self, e):
        with self._lock:
            self.stats["failures"] += 1
            self.stats["fallbacks"] += 1
            if len(self.errors) < 20:
                self.errors.append(redact(f"{type(e).__name__}: {e}")[:300])

    def jev(self, client, state, q):
        t = time.time()
        answers, meta = client.ask(kb.dumps(state), q, retries=0)
        self.account(kb.jev_meta(meta), time.time() - t)
        return answers

    def chat(self, client, system, user, max_tokens=2000):
        t = time.time()
        out = client.chat(system, user, json_mode=True, max_tokens=max_tokens, retries=1)
        self.account(kb.chat_meta(client, self.cfg), time.time() - t)
        return out

    def parallel(self, jobs):
        """Jev calls for many agents at once: [(client, state, q)] -> [answers or None]. Failures fall back."""
        futs = [self.pool.submit(self.jev, c, s, q) for c, s, q in jobs]
        out = []
        for f in futs:
            try:
                out.append(f.result(timeout=self.cfg["request_timeout_s"] + 5))
            except Exception as e:  # noqa: BLE001
                self.failure(e)
                out.append(None)
        return out

    def probe(self, who, spec, quiet=False):
        rng = random.Random(self.prng.random())
        p = self.case.check(spec["block"], spec["cycle"], rng) if spec["type"] == "check" else \
            self.case.drive(spec["block"], spec["kind"], rng)
        where = f"cycles {p['window'][0]}-{p['window'][1]}" if p["type"] == "check" else f"bench, {p['kind']}"
        self.log_probe(who, p, f"#{who} {'checks' if p['type'] == 'check' else 'drives'} {p['block']} ({where})"
                       + (": MISMATCH" if p["mismatch"] else ""), quiet=quiet)
        return kb.strip(p)

    def log_probe(self, who, p, text, quiet=False):
        self.probes.append({"by": who, "block": p["block"], "type": p["type"], "window": p.get("window"),
                            "kind": p.get("kind"), "mismatch": p.get("mismatch", False), "tick": self.game_tick()})
        if not quiet or p.get("mismatch"):
            self.event("probe", text, block=p["block"], by=who, mismatch=p.get("mismatch", False))

    def game_tick(self):
        g = getattr(self, "game", None)
        return g.tick if g else 0

    def event(self, kind, text, **kw):
        e = {"t": round(time.time() - self.t0, 2), "tick": self.game_tick(), "kind": kind, "text": text}
        e.update(kw)
        self.events.append(e)
        if len(self.events) > 2000:
            self.events = self.events[-1000:]
        if self._ev:
            self._ev.write(json.dumps(e, default=str) + "\n")

    # ------------------------------------------------------------------ pacing and commands
    def command(self, cmd):
        self.cmds.put(cmd)

    def _handle(self, cmd):
        a = cmd.get("action")
        if a == "pause":
            self.paused = True
        elif a == "resume":
            self.paused = False
        elif a == "step":
            self.paused = True
            self.step_req += 1
        elif a == "stop":
            self.stopped = True
        elif a == "set":
            for k, v in (cmd.get("cfg") or {}).items():
                if k in LIVE_KEYS:
                    self.cfg[k] = coerce({k: v})[k]

    def pace(self):
        self.publish()
        if not self.realtime:
            return
        deadline = time.time() + 1.0 / max(0.1, self.cfg["speed"])
        while True:
            try:
                self._handle(self.cmds.get(timeout=0.05))
            except queue.Empty:
                pass
            if self.stopped:
                raise Stop()
            if self.paused:
                if self.step_req:
                    self.step_req -= 1
                    return
                deadline = time.time() + 1.0 / max(0.1, self.cfg["speed"])
                continue
            if time.time() >= deadline:
                return

    # ------------------------------------------------------------------ run
    def run(self):
        try:
            self.event("start", self.case.failure_text())
            self.pace()
            g = self.game
            guard = self.deadline * 3 + 10
            while not g.done and guard > 0:
                g.step()
                guard -= 1
                self.pace()
        except Stop:
            self.event("stop", "stopped by the viewer")
        except Exception as e:  # noqa: BLE001
            import traceback
            self.errors.append(redact(f"{type(e).__name__}: {e} | {traceback.format_exc()[-400:]}")[:700])
            self.event("error", self.errors[-1])
        finally:
            self.finish()

    def finish(self):
        g = self.game
        ans = g.answer if (g.answer and g.answer.get("fixes")) else None
        self.result = self.case.grade(ans) if ans else {
            "block_ok": False, "location_ok": False, "type_ok": False, "fix_ok": False, "tests_passed": None,
            "tests_total": len(self.case.tests), "n_bugs": len(self.case.faults)}
        self.ended = True
        sec = self.case.secret()
        self.event("end", ("SOLVED: " if self.result["fix_ok"] else "NOT SOLVED: ") +
                   (("named " + "; ".join(f"{f['block']}.{f['port']} ({f.get('desc')})" for f in ans["fixes"]))
                    if ans else "no answer") + "; the bug: " +
                   "; ".join(f"{b['block']}.{b['port']} ({b['desc']}{', rare trigger' if b['rare'] else ''})"
                             for b in sec["bugs"]))
        self.summary = self.make_summary()
        if self.run_dir:
            with open(os.path.join(self.run_dir, "summary.json"), "w") as f:
                json.dump(self.summary, f, indent=1, default=str)
            if self._ev:
                self._ev.close()
                self._ev = None
        self.publish()
        self.pool.shutdown(wait=False)

    def make_summary(self):
        s, g, c = self.stats, self.game, self.cfg
        lat = sorted(s["latencies"])
        at = g.answer_tick if g.answer_tick is not None else self.deadline
        ans = g.answer if (g.answer and g.answer.get("fixes")) else None
        return {"mode": self.mode, "setting": self.setting, "seed": c["seed"], "test": self.case.test["name"],
                "bug": self.case.secret(), "answer": ans, "result": self.result,
                "probes": len(self.probes), "ticks": g.tick, "deadline_ticks": self.deadline,
                "sim_hours": round(min(at, self.deadline) * c["tick_min"] / 60, 2),
                "ran_to_deadline": bool(getattr(g, "forced", False)) or ans is None,
                "wrong_quorum": bool(getattr(g, "wrong_quorum", False)),
                "liars": g.liars() if hasattr(g, "liars") else [], "guesses": self.guesses,
                "errors": self.errors[:10], "wall_s": round(time.time() - self.t0, 1),
                "inference": {"calls": s["calls"], "failures": s["failures"], "fallbacks": s["fallbacks"],
                              "in": s["in"], "out": s["out"], "cached": s["cached"], "cost": round(s["cost"], 5),
                              "p50_latency": lat[len(lat) // 2] if lat else None, "models": sorted(s["models"])}}

    def add_guess(self, body):
        b = body.get("block")
        if b not in self.case.by:
            return None
        g = {"block": b, "t": round(time.time() - self.t0, 1), "probes": len(self.probes), "tick": self.game_tick()}
        self.guesses.append(g)
        self.event("guess", f"you suspect {b}", block=b)
        return g

    # ------------------------------------------------------------------ frames
    def frame(self, full=False):
        g, s = self.game, self.stats
        v = g.view()
        fr = []
        nb = getattr(g, "nb", None)
        if nb is not None and not self.ended:
            try:
                fr = [[b, cy, pr] for pr, b, cy in nb.frontier(limit=12)]
            except Exception:  # noqa: BLE001
                fr = []
        f = {"mode": self.mode, "setting": self.setting, "tick": g.tick, "deadline": self.deadline,
             "tick_min": self.cfg["tick_min"], "ended": self.ended, "paused": self.paused, "speed": self.cfg["speed"],
             "probes": len(self.probes), "probe_budget": self.cfg["probe_budget"] if self.mode == "solo" else None,
             "cost": round(s["cost"], 5), "budget_usd": self.cfg["budget_usd"], "calls": s["calls"],
             "failures": s["failures"], "fallbacks": s["fallbacks"], "elapsed": round(time.time() - self.t0, 1),
             "probe_log": self.probes[-60:], "events": self.events[-80:], "frontier": fr,
             "answer": g.answer if g.answer and g.answer.get("fixes") else None,
             "result": self.result if self.ended else None, "guesses": self.guesses, "errors": self.errors[-3:]}
        f.update(v)
        if self.ended:
            f["secret"] = self.case.secret()
            f["liars"] = g.liars() if hasattr(g, "liars") else []
            f["summary"] = self.summary
        return f

    def publish(self):
        self.bus.publish(self.frame())

    def subscribe(self):
        return self.bus.subscribe()

    def unsubscribe(self, q):
        self.bus.unsubscribe(q)

    def static(self):
        c = self.case
        return {"blocks": c.public_blocks(), "edges": c.edges(), "brief": c.brief(), "results": c.results,
                "occupancy": c.occupancy(), "n": c.n, "starts": c.starts, "window": c.window,
                "src": c.test["src"], "mode": self.mode, "setting": self.setting, "deadline": self.deadline,
                "cfg": {k: v for k, v in self.cfg.items() if not k.endswith("_key")}}

    def inspect(self, block, cycle):
        """Viewer-only: a free look at one block's values over a window (does not count as a probe)."""
        c = self.case
        if block not in c.by:
            return None
        cycle = max(0, min(c.n - 1, int(cycle)))
        lo, hi = c.window_of(cycle)
        rows = []
        for k in range(lo, hi + 1):
            ins = c.trace.instr_at(c.by[block].stage, k)
            rows.append({"cycle": k, "in": c.trace.inputs(block, k), "out": c.trace.outputs(block, k),
                         "instr": f"pc {ins['pc']}: {ins['text']}" if ins else None})
        return {"block": block, "spec": c.by[block].spec, "window": [lo, hi], "rows": rows}
