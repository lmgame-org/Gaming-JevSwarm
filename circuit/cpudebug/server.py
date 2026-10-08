"""HTTP server: launch screen, live viewer (Server-Sent Events) and a small JSON API. Stdlib only."""
import json
import os
import threading
import time
from urllib.parse import parse_qs, urlparse

from swarmcore.keys import key_files
from swarmcore.llm import JevClient, LLMClient
from swarmcore.web import BaseHandler, redact, serve as _serve

from .case import Case
from .chip import ChipCase
from .config import BOYS, DEFAULTS, HOLMES, MODES, PRESETS, SCHEMA, SOLO_POLICIES, SWARM_POLICIES, coerce
from .engine import RUNS, Engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = {"engine": None, "thread": None}
LOCK = threading.Lock()


def list_runs():
    if not os.path.isdir(RUNS):
        return []
    out = []
    for name in sorted(os.listdir(RUNS), reverse=True)[:40]:
        p = os.path.join(RUNS, name, "summary.json")
        if not os.path.isfile(p):
            continue
        with open(p) as f:
            s = json.load(f)
        r = s.get("result") or {}
        out.append({"name": name, "mode": s.get("mode"), "setting": s.get("setting"), "seed": s.get("seed"),
                    "fix_ok": r.get("fix_ok"),
                    "location_ok": r.get("location_ok"), "probes": s.get("probes"),
                    "cost": (s.get("inference") or {}).get("cost"), "bug": (s.get("bug") or {}).get("desc")})
    return out


def bench():
    """Per-tier, per-setting results of the benchmark CSVs in docs/ (shown on the launch screen)."""
    import csv
    import glob
    files = {"v2": sorted(glob.glob(os.path.join(ROOT, "docs", "benchmark_100seeds_v2*.csv"))) or
             sorted(glob.glob(os.path.join(ROOT, "docs", "benchmark_20seeds_*.csv"))),
             "v3": sorted(glob.glob(os.path.join(ROOT, "docs", "benchmark_v3_*.csv")))}
    out = {}
    for tier, paths in files.items():
        rows = []
        for p in paths:
            with open(p) as f:
                rows += list(csv.DictReader(f))
        t = out.setdefault(tier, {})
        for r in rows:
            if "setting" not in r:
                continue
            d = t.setdefault(r["setting"], {"solved": 0, "n": 0, "spend": 0.0, "walls": []})
            d["n"] += 1
            d["solved"] += r["fix_ok"] == "True"
            d["spend"] += float(r["cost_usd"] or 0)
            d["walls"].append(float(r.get("wall_s") or 0))
        for d in t.values():
            c = d["spend"] / max(1, d["n"])
            d["cost"] = "free" if c == 0 else f"${c:.4f} per case" if c < 0.01 else f"${c:.3f} per case"
            w = sorted(d.pop("walls"))
            m = w[len(w) // 2] if w else 0
            d["wall"] = f"{m:.0f} s" if m >= 1 else "under a second"
    return out


def preview(q):
    cfg = coerce(q)
    c = ChipCase(cfg) if cfg["tier"] == "v3" else Case(cfg)
    sl = c.slice_cycles()
    return {"blocks": c.public_blocks(), "edges": c.edges(), "brief": c.brief(), "results": c.results,
            "occupancy": c.occupancy(), "n": c.n, "starts": c.starts, "src": c.test.get("src", ""), "window": c.window,
            # v3: no per-block shading (it would show which core is broken)
            "slice": {} if cfg["tier"] == "v3" else {b: len(v) for b, v in sl.items()}, "tier": cfg["tier"],
            # spoiler-free solvability: does the handed-out test's back-trace reach every broken block?
            "check": {"reachable": all(f["block"] in sl for f in c.faults), "slice_blocks": len(sl),
                      "slice_nodes": sum(len(v) for v in sl.values()), "suspect_blocks": sum(1 for b in c.blocks if not b.trusted),
                      "failing": sum(1 for r in c.results if not r["ok"]), "cycles": c.n}}


class Handler(BaseHandler):
    WEB = os.path.join(ROOT, "web")

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        eng = STATE["engine"]
        if path == "/api/schema":
            return self.send_json({"schema": [[g, [list(f) for f in fields]] for g, fields in SCHEMA],
                                   "defaults": DEFAULTS, "presets": PRESETS, "modes": MODES,
                                   "solo_policies": SOLO_POLICIES, "holmes": HOLMES, "boys": BOYS,
                                   "swarm_policies": SWARM_POLICIES, "bench": bench(),
                                   "key_files": key_files(), "runs": list_runs(),
                                   "running": bool(eng and not eng.ended)})
        if path == "/api/preview":
            return self.send_json(preview(q))
        if path == "/api/static":
            return self.send_json(eng.static() if eng else {"error": "no run"}, 200 if eng else 404)
        if path == "/api/frame":
            return self.send_json(eng.frame(full=True) if eng else {"error": "no run"}, 200 if eng else 404)
        if path == "/api/secret":  # viewer-only spoiler; investigators never get this
            if not eng:
                return self.send_json({"error": "no run"}, 404)
            sec = eng.case.secret()
            sec["liars"] = eng.game.liars() if hasattr(eng.game, "liars") else []
            return self.send_json(sec)
        if path == "/api/agent":
            if not eng:
                return self.send_json({"error": "no run"}, 404)
            d = eng.agent_detail(q.get("id", "0"))
            return self.send_json(d or {"error": "no such agent"}, 200 if d else 404)
        if path == "/api/inspect":
            if not eng:
                return self.send_json({"error": "no run"}, 404)
            d = eng.inspect(q.get("block"), q.get("cycle", 0))
            return self.send_json(d or {"error": "no such block"}, 200 if d else 404)
        if path == "/api/stream":
            if not eng:
                return self.send_json({"error": "no run"}, 404)
            return self.stream(eng, eng.frame(full=True), lambda: STATE["engine"] is eng)
        return self.send_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.read_body()
        eng = STATE["engine"]
        if path == "/api/test":
            return self.send_json(test_model(body))
        if path == "/api/launch":
            with LOCK:
                old = STATE["engine"]
                if old:
                    old.stopped = True
                    if STATE["thread"]:
                        STATE["thread"].join(timeout=10)
                try:
                    e = Engine(body.get("cfg") or {}, realtime=True)
                except Exception as ex:  # noqa: BLE001
                    return self.send_json({"ok": False, "error": redact(f"{type(ex).__name__}: {ex}")}, 400)
                STATE["engine"] = e
                th = threading.Thread(target=e.run, daemon=True)
                STATE["thread"] = th
                th.start()
            return self.send_json({"ok": True, "run": os.path.basename(e.run_dir or "")})
        if not eng:
            return self.send_json({"error": "no run"}, 404)
        if path == "/api/cmd":
            eng.command(body)
            return self.send_json({"ok": True})
        if path == "/api/guess":
            g = eng.add_guess(body)
            return self.send_json({"ok": bool(g), "guess": g})
        return self.send_json({"error": "not found"}, 404)


def test_model(body):
    cfg = coerce(body.get("cfg") or {})
    t0 = time.time()
    try:
        if body.get("which") == "chat":
            c = LLMClient("openai", cfg["chat_model"], cfg["chat_key"], timeout=60)
            out = c.chat("Reply with JSON only.", 'Return {"ok": true}.', json_mode=True, max_tokens=200)
            return {"ok": True, "model": c.model, "reply": out, "latency": round(time.time() - t0, 2)}
        j = JevClient(cfg["jev_provider"], cfg["jev_model"], cfg["jev_key"], timeout=20)
        ans, meta = j.ask(json.dumps({"block": "alu_sub", "spec": "a - b", "rows": [
            {"in": {"a": 9, "b": 4}, "out": {"out": 6}, "spec_out": {"out": 5}}]}),
            {"faulty": {"type": "noul", "instructions": "Does out differ from spec_out?"}})
        return {"ok": True, "model": meta.get("model"), "reply": ans, "usage": meta.get("usage"),
                "latency": round(time.time() - t0, 2)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": redact(e)[:300]}


def serve(host="127.0.0.1", port=8783):
    def stop():
        if STATE["engine"]:
            STATE["engine"].stopped = True
    _serve(Handler, host, port, "jev-swarm circuit (CPU debugging)", on_exit=stop)
