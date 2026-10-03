"""Run loop for every mode: pacing, pause/step, budgets, logging and viewer frames.

Swarm modes: a round is scatter (Wiggins hands out assignments), a few probe steps (every Irregular still working
decides at once; model calls go out together), then gather (reports folded into the board) and Holmes's deduction.
Cone mode: one exact tracer, one probe per step. Genius mode: one model turn, then its probes one per step.
"""
import json
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from swarmcore.web import Broadcaster, redact

from . import agents as A
from .case import Case
from .config import LIVE_KEYS, coerce

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, "runs")
SWARM = ("jev", "hybrid", "rule_swarm")


class Stop(Exception):
    pass


class Engine:
    def __init__(self, cfg, realtime=True, log=True, runs_dir=None):
        self.cfg = coerce(cfg)
        c = self.cfg
        self.realtime = realtime
        self.mode = c["mode"]
        self.case = Case(c)
        self.board = A.Board(self.case, c)
        n = c["n_irregulars"] if self.mode in SWARM else 1
        self.agents = [A.Agent(i + 1) for i in range(n)]
        self.irr = A.make_irregular(self.mode, c) if self.mode in SWARM else None
        self.rule = A.RuleIrregular(c)
        self.wiggins = A.Wiggins(self.case, c, self.board, exact=self.mode != "jev")
        self.holmes = A.make_holmes(self.mode, self.case, c) if self.mode in SWARM else A.ExactHolmes(self.case, c)
        self.exact_holmes = A.ExactHolmes(self.case, c)
        self.genius = A.Genius(self.case, c) if self.mode == "genius" else None
        self.pool = ThreadPoolExecutor(max_workers=max(1, c["concurrency"]))
        self.bus = Broadcaster()
        self.cmds = queue.Queue()
        self.paused = False
        self.step_req = 0
        self.stopped = False
        self.ended = False
        self.round = 0
        self.phase = "starting"
        self.stats = {"calls": 0, "failures": 0, "fallbacks": 0, "in": 0, "out": 0, "cached": 0, "cost": 0.0,
                      "latencies": [], "models": set()}
        self.events = []
        self.answer = None
        self.answer_note = ""
        self.result = None
        self.guesses = []
        self.errors = []
        self.t0 = time.time()
        self._lock = threading.Lock()
        self.run_dir = None
        self._ev = None
        if log:
            os.makedirs(runs_dir or RUNS, exist_ok=True)
            name = f"{time.strftime('%Y%m%d-%H%M%S')}_{self.mode}_s{c['seed']}"
            self.run_dir = os.path.join(runs_dir or RUNS, name)
            os.makedirs(self.run_dir, exist_ok=True)
            with open(os.path.join(self.run_dir, "config.json"), "w") as f:
                json.dump({k: v for k, v in c.items() if not k.endswith("_key")}, f, indent=1)
            self._ev = open(os.path.join(self.run_dir, "events.jsonl"), "w")

    # ------------------------------------------------------------------ bookkeeping
    def probes_left(self):
        return self.cfg["probe_budget"] - len(self.board.probes)

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

    def event(self, kind, text, **kw):
        e = {"t": round(time.time() - self.t0, 2), "round": self.round, "kind": kind, "text": text}
        e.update(kw)
        self.events.append(e)
        if self._ev:
            self._ev.write(json.dumps(e, default=str) + "\n")

    def probe(self, agent, spec):
        p = A.run_probe(self.case, spec)
        self.board.probes.append({"by": agent.id, "block": p["block"], "type": p["type"], "round": self.round,
                                  "window": p.get("window"), "kind": p.get("kind"), "mismatch": p["mismatch"]})
        self.board.add_rows(p)
        agent.block = p["block"]
        agent.status = "probing"
        where = f"cycles {p['window'][0]}-{p['window'][1]}" if p["type"] == "check" else f"bench, {p['kind']} vectors"
        agent.last = f"{'checks' if p['type'] == 'check' else 'drives'} {p['block']} ({where})"
        self.event("probe", f"#{agent.id} {agent.last}", block=p["block"], by=agent.id, mismatch=p["mismatch"])
        return p

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
            self.event("start", f"{self.case.test['name']} fails: {self.case.failure_text()}")
            self.pace()
            if self.mode == "genius":
                self.run_genius()
            elif self.mode == "cone":
                self.run_cone()
            else:
                self.run_swarm()
        except Stop:
            self.event("stop", "stopped by the viewer")
        except Exception as e:  # noqa: BLE001
            self.errors.append(redact(f"{type(e).__name__}: {e}")[:300])
            self.event("error", self.errors[-1])
        finally:
            self.finish()

    def run_swarm(self):
        c, bd = self.cfg, self.board
        for r in range(1, c["max_rounds"] + 1):
            if self.probes_left() <= 0:
                break
            self.round = r
            self.phase = "scatter"
            plan = self.wiggins.scatter(len(self.agents), r)
            if not plan:
                self.event("note", "Wiggins has nothing left on the back-trace to hand out")
                break
            for ag, a in zip(self.agents, plan):
                ag.reset(a)
            for ag in self.agents[len(plan):]:
                ag.done, ag.status, ag.assignment, ag.notes = True, "idle", None, []
            self.event("scatter", f"round {r}: {len(plan)} Irregulars sent out "
                                  f"({sum(1 for a in plan if a['kind'] == 'window')} with a waveform window)")
            self.pace()
            self.phase = "probe"
            for _ in range(c["probes_per_irregular"] + 1):
                active = [ag for ag in self.agents if not ag.done]
                if not active:
                    break
                self.step(active)
                self.pace()
            self.phase = "gather"
            for ag in self.agents:
                if ag.assignment is None:
                    continue
                verdicts, up = self.verdicts(ag)
                for kind, b, who in self.wiggins.gather(ag, verdicts, up):
                    if kind != "follow" or self.mode == "hybrid" or self.mode == "jev":
                        self.event(kind, self.say(kind, b, who), block=b, by=who)
                ag.status = "report"
            for kind, x, y in self.wiggins.red_herrings():
                self.event("herring", f"Wiggins: {x} only went wrong because {y} fed it bad values (red herring)",
                           block=x)
            self.pace()
            self.phase = "deduce"
            ans, note, metas = self.ask_holmes(final=False)
            if note:
                self.event("holmes", note)
            if ans:
                self.answer, self.answer_note = ans, note
                break
        if not self.answer:
            self.phase = "deduce"
            ans, note, _ = self.ask_holmes(final=True)
            self.answer, self.answer_note = ans, note or ""
            if note:
                self.event("holmes", note)

    def say(self, kind, b, who):
        return {"clear": f"#{who}: {b} matches its spec (cleared)",
                "suspect": f"#{who}: {b} does NOT match its spec",
                "unsure": f"#{who}: not sure about {b}",
                "follow": f"#{who}: the bad value came into it from {b}"}.get(kind, f"{kind} {b}")

    def ask_holmes(self, final):
        h = self.holmes
        if h.uses_model and self.over_budget():
            h = self.exact_holmes if self.mode != "jev" else h
        t = time.time()
        try:
            ans, note, metas = h.consider(self.board, final=final)
        except Exception as e:  # noqa: BLE001
            self.stats["failures"] += 1
            self.errors.append(redact(f"Holmes: {type(e).__name__}: {e}")[:300])
            if not final:
                return None, "Holmes's call failed; another round", None
            # last resort: the top suspect, first fault that fits
            bd = self.board
            sus = bd.suspects()
            if not sus:
                return None, "Holmes could not answer", None
            b = sus[0][0]
            fits = self.case.fit(b, bd.rows.get(b, [])) or self.case.by[b].faults
            return A.fault_answer(b, fits[0]), f"Holmes's call failed; top suspect {b}", None
        for m in metas or []:
            self.account(m, time.time() - t)
        return ans, note, metas

    def step(self, active):
        k = self.cfg["probes_per_irregular"]
        futs = {}
        for ag in active:
            final = ag.used >= k or self.probes_left() <= 0
            use_model = self.irr.uses_model and not self.over_budget()
            if use_model:
                futs[ag.id] = (self.pool.submit(self._timed, self.irr.decide, self.case, ag, final), final)
            else:
                futs[ag.id] = (None, final)
        for ag in active:
            fut, final = futs[ag.id]
            act, j = None, {}
            if fut is not None:
                try:
                    (act, j, meta), lat = fut.result(timeout=self.cfg["request_timeout_s"] + 5)
                    self.account(meta, lat)
                except Exception as e:  # noqa: BLE001
                    self.stats["failures"] += 1
                    self.stats["fallbacks"] += 1
                    if len(self.errors) < 20:
                        self.errors.append(redact(f"Irregular: {type(e).__name__}: {e}")[:300])
                    act = None
            if act is None:
                act, _, _ = self.rule.decide(self.case, ag, final)
            ag.judgment.update({k_: v for k_, v in (j or {}).items() if v is not None})
            if final or act == "REPORT" or self.probes_left() <= 0:
                ag.done, ag.status = True, "report"
                continue
            opts = A.options(self.case, ag.assignment, ag)
            if act not in opts:
                ag.done, ag.status = True, "report"
                continue
            p = self.probe(ag, opts[act][1])
            ag.notes.append({"opt": act, "probe": p})
            ag.used += 1

    def _timed(self, fn, *args):
        t = time.time()
        return fn(*args), time.time() - t

    def verdicts(self, ag):
        """Turn one Irregular's round into verdicts for Wiggins: exact in hybrid / rule modes, its own in Jev mode."""
        per = A.exact_judgment(self.case, ag)
        j = ag.judgment
        if self.mode != "jev":
            v = {b: {"susp": 1.0 if x["mismatch"] else 0.0, "cycles": x["cycles"], "ports": dict(x["ports"])}
                 for b, x in per.items()}
            up = j.get("upstream") if self.mode == "hybrid" and not any(x["mismatch"] for x in per.values()) else None
            return v, (up if up and up != "NONE" else None)
        a = ag.assignment
        if a["kind"] == "block":
            b = a["blocks"][0]
            if b not in per:
                return {}, None
            s = j.get("faulty")
            up = j.get("upstream")
            up = up if up and up != "NONE" and (s is None or s < self.cfg["suspect_above"]) else None
            return {b: {"susp": s, "cycles": per[b]["cycles"], "ports": dict(per[b]["ports"])}}, up
        sus, f = j.get("suspect"), j.get("faulty")
        out = {}
        for b, x in per.items():
            if sus is None:
                s = None
            elif b == sus:
                s = f if f is not None else 0.75
            else:
                s = 0.1
            out[b] = {"susp": s, "cycles": x["cycles"], "ports": dict(x["ports"])}
        return out, None

    def run_cone(self):
        """One exact tracer: always check the closest unchecked block-cycle on the back-trace."""
        ag = self.agents[0]
        ag.assignment = {"kind": "block", "blocks": ["wb_mux"], "cycles": {}, "why": "trace back from the failure"}
        ag.status = "probing"
        self.round = 1
        self.phase = "trace"
        while self.probes_left() > 0:
            bd = self.board
            caught = [b for b, s in bd.suspects() if s["score"] >= 0.99]
            if caught:
                b = caught[0]
                fits = self.case.fit(b, bd.rows.get(b, []))
                if len(fits) <= 1:
                    break
                kinds = [k for k in ("sweep", "corner", "boundary", "random")
                         if not any(p["block"] == b and p.get("kind") == k for p in bd.probes)]
                if not kinds:
                    break
                p = self.probe(ag, {"type": "drive", "block": b, "kind": kinds[0]})
            else:
                fr = bd.frontier(limit=1)
                if not fr:
                    break
                _, b, cy = fr[0]
                p = self.probe(ag, {"type": "check", "block": b, "cycle": cy})
                cyc = {r["cycle"] for r in p["rows"]}
                if p["mismatch"]:
                    e = bd.susp.setdefault(b, {"score": 1.0, "n": 0, "ports": A.Counter(), "cycles": set(), "by": []})
                    e["n"] += 1
                    e["cycles"].update(r["cycle"] for r in p["rows"] if not r["ok"])
                    e["ports"].update(port for r in p["rows"] if not r["ok"] for port in r["out"]
                                      if r["out"][port] != r["spec"][port])
                    self.event("suspect", f"tracer: {b} does NOT match its spec", block=b, by=ag.id)
                else:
                    bd.cleared.setdefault(b, set()).update(cyc)
                    self.event("clear", f"tracer: {b} matches its spec at cycles {min(cyc)}-{max(cyc)}", block=b,
                               by=ag.id)
            self.pace()
        self.phase = "deduce"
        ans, note, _ = self.exact_holmes.consider(self.board, final=True)
        self.answer, self.answer_note = ans, note or ""
        if note:
            self.event("holmes", note)

    def run_genius(self):
        g, c, ag = self.genius, self.cfg, self.agents[0]
        ag.assignment = {"kind": "block", "blocks": ["wb_mux"], "cycles": {}, "why": "reads the whole netlist"}
        ag.status = "thinking"
        last = 0.0
        for turn in range(1, c["max_turns"] + 1):
            self.round = turn
            self.phase = "think"
            final = (turn == c["max_turns"] or self.probes_left() <= 0 or
                     self.stats["cost"] + 1.3 * last > c["budget_usd"])
            ag.status, ag.last = "thinking", "reading the netlist and its notes"
            self.publish()
            t = time.time()
            try:
                out, meta = g.turn(turn, self.probes_left(), c["budget_usd"] - self.stats["cost"], final)
            except Exception as e:  # noqa: BLE001
                self.stats["failures"] += 1
                self.errors.append(redact(f"genius: {type(e).__name__}: {e}")[:300])
                self.event("error", self.errors[-1])
                break
            self.account(meta, time.time() - t)
            last = meta["cost"]
            think = str(out.get("thinking") or "")[:400]
            self.event("genius", f"turn {turn}: {think}" if think else f"turn {turn}")
            ans = g.parse_answer(out.get("answer"))
            if ans:
                self.answer, self.answer_note = ans, think
                break
            if final:
                break
            reads = g.do_reads(out.get("reads"))
            probes = g.parse_probes(out.get("probes"))
            entry = {"turn": turn, "thinking": think, "reads": reads, "probes": []}
            g.history.append(entry)
            if reads:
                self.event("read", f"reads {len(reads)} net(s): " + ", ".join(r["net"] for r in reads))
            for spec in probes:
                if self.probes_left() <= 0:
                    break
                p = self.probe(ag, spec)
                entry["probes"].append(A.probe_view(p, limit=8))
                self.pace()
            if not probes and not reads:
                entry["note"] = "you asked for nothing; answer now"
        self.phase = "deduce"

    # ------------------------------------------------------------------ results
    def finish(self):
        if self.answer is not None or not self.result:
            self.result = self.case.grade(self.answer) if self.answer else {
                "block_ok": False, "location_ok": False, "type_ok": False, "fix_ok": False, "tests_passed": None,
                "tests_total": len(self.case.tests)}
        self.ended = True
        self.phase = "done"
        r = self.result
        sec = self.case.secret()
        self.event("end", ("SOLVED: " if r["fix_ok"] else "NOT SOLVED: ") +
                   (f"named {self.answer['block']}.{self.answer['port']} ({self.answer.get('desc')})"
                    if self.answer else "no answer") + f"; the bug was {sec['block']}.{sec['port']} ({sec['desc']})")
        self.summary = self.make_summary()
        if self.run_dir:
            with open(os.path.join(self.run_dir, "summary.json"), "w") as f:
                json.dump(self.summary, f, indent=1, default=str)
            if self._ev:
                self._ev.close()
                self._ev = None
        self.publish(force=True)
        self.pool.shutdown(wait=False)

    def make_summary(self):
        s = self.stats
        lat = sorted(s["latencies"])
        return {"mode": self.mode, "seed": self.cfg["seed"], "test": self.case.test["name"],
                "bug": self.case.secret(), "answer": self.answer, "result": self.result,
                "probes": len(self.board.probes), "probe_budget": self.cfg["probe_budget"],
                "rounds": self.round, "guesses": self.guesses, "errors": self.errors[:10],
                "wall_s": round(time.time() - self.t0, 1),
                "inference": {"calls": s["calls"], "failures": s["failures"], "fallbacks": s["fallbacks"],
                              "in": s["in"], "out": s["out"], "cached": s["cached"], "cost": round(s["cost"], 5),
                              "p50_latency": lat[len(lat) // 2] if lat else None, "models": sorted(s["models"])}}

    def add_guess(self, body):
        b = body.get("block")
        if b not in self.case.by:
            return None
        g = {"block": b, "t": round(time.time() - self.t0, 1), "probes": len(self.board.probes)}
        self.guesses.append(g)
        self.event("guess", f"you suspect {b}", block=b)
        return g

    # ------------------------------------------------------------------ frames
    def frame(self, full=False):
        bd = self.board
        heat = {}
        sa = self.cfg["suspect_above"]
        for b, cyc in bd.cleared.items():
            heat[b] = [0.0, "c"]
        for b, n in bd.inconclusive.items():
            if b not in heat:
                heat[b] = [0.4, "u"]
        for b, s in bd.susp.items():
            heat[b] = [round(s["score"], 2), "r" if b in bd.herring else "x" if s["score"] >= sa else "u"]
        fr = []
        if not self.ended:
            try:
                fr = bd.frontier(limit=16)
            except Exception:  # noqa: BLE001
                fr = []
        for pr, b, cy in fr:
            if b not in heat:
                heat[b] = [round(max(0.1, 0.5 - 0.04 * pr), 2), "f"]
        s = self.stats
        f = {"mode": self.mode, "round": self.round, "phase": self.phase, "ended": self.ended,
             "paused": self.paused, "speed": self.cfg["speed"],
             "probes": len(bd.probes), "probe_budget": self.cfg["probe_budget"],
             "cost": round(s["cost"], 5), "budget_usd": self.cfg["budget_usd"], "calls": s["calls"],
             "failures": s["failures"], "fallbacks": s["fallbacks"], "elapsed": round(time.time() - self.t0, 1),
             "agents": [{"id": a.id, "block": a.block, "status": a.status, "last": a.last,
                         "kind": (a.assignment or {}).get("kind"), "blocks": (a.assignment or {}).get("blocks"),
                         "judgment": {k: v for k, v in a.judgment.items()}} for a in self.agents],
             "heat": heat, "frontier": [[b, cy, pr] for pr, b, cy in fr],
             "probe_log": bd.probes[-40:], "events": self.events[-60:],
             "answer": self.answer, "answer_note": self.answer_note, "result": self.result if self.ended else None,
             "guesses": self.guesses, "errors": self.errors[-3:]}
        if self.ended:
            f["secret"] = self.case.secret()
        return f

    def publish(self, force=False):
        self.bus.publish(self.frame())

    def subscribe(self):
        return self.bus.subscribe()

    def unsubscribe(self, q):
        self.bus.unsubscribe(q)

    def static(self):
        c = self.case
        return {"blocks": c.public_blocks(), "edges": c.edges(), "brief": c.brief(), "results": c.results,
                "occupancy": c.occupancy(), "n": c.n, "starts": c.starts, "window": c.window,
                "src": c.test["src"], "mode": self.mode, "cfg": {k: v for k, v in self.cfg.items()
                                                                if not k.endswith("_key")}}

    def inspect(self, block, cycle):
        """Viewer-only: a free look at one block over a window (does not count as a probe)."""
        c = self.case
        if block not in c.by:
            return None
        cycle = max(0, min(c.n - 1, int(cycle)))
        p = c.check(block, cycle)
        return {"block": block, "spec": c.by[block].spec, "window": p["window"],
                "rows": [A.row_view(r) for r in p["rows"]]}
