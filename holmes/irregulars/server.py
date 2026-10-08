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
from .challenges import public as challenge_list
from .config import DEFAULTS, POLICIES, PRESETS, SCHEMA, SWARM_POLICIES, coerce
from .engine import RUNS, Engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = {"engine": None, "thread": None}
LOCK = threading.Lock()


CHALLENGE_LIST = challenge_list()


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
        out.append({"name": name, "mode": s.get("mode"), "policy": s.get("policy"), "parts": s.get("parts"),
                    "solved": s.get("solved"), "cost": (s.get("inference") or {}).get("cost")})
    return out


class Handler(BaseHandler):
    WEB = os.path.join(ROOT, "web")

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        eng = STATE["engine"]
        if path == "/api/schema":
            return self.send_json({
                "schema": [[g, [list(f) for f in fields]] for g, fields in SCHEMA], "defaults": DEFAULTS,
                "presets": {k: v for k, v in PRESETS.items()}, "policies": POLICIES, "swarm_policies": SWARM_POLICIES,
                "key_files": key_files(), "runs": list_runs(), "running": bool(eng and not eng.ended),
                "challenges": CHALLENGE_LIST})
        if path == "/api/preview":
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            c = Case(coerce(q))
            return self.send_json({"map": c.public_map(), "brief": c.brief(), "solvable": c.solvable,
                                   "counting": getattr(c, "counting_fooled", None), "kinds": _kind_counts(c)})
        if path == "/api/irregular":
            if not eng:
                return self.send_json({"error": "no run"}, 404)
            d = eng.irregular_detail(int(parse_qs(url.query).get("id", ["0"])[0]))
            return self.send_json(d or {"error": "no such Irregular"}, 200 if d else 404)
        if path == "/api/secret":  # viewer-only spoilers; detectives never get this
            return self.send_json(eng.case.secret() if eng else {"error": "no run"}, 200 if eng else 404)
        if path == "/api/observation":
            return self.send_json({"observation": eng.solo_observation()} if eng else {"error": "no run"})
        if path == "/api/frame":
            return self.send_json(eng.frame(full=True) if eng else {"error": "no run"}, 200 if eng else 404)
        if path == "/api/stream":
            if not eng:
                return self.send_json({"error": "no run"}, 404)
            return self.stream(eng, eng.frame(full=True), lambda: STATE["engine"] is eng and not eng.stopped)
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


def _kind_counts(c):
    out = {}
    for l in c.leads.values():
        k = "lie" if l["lie"] else l["fact"][0]
        out[k] = out.get(k, 0) + 1
    return out


def test_model(body):
    cfg = coerce(body.get("cfg") or {})
    t0 = time.time()
    try:
        if body.get("which") == "chat":
            c = LLMClient("openai", cfg["chat_model"], cfg["chat_key"], timeout=60)
            out = c.chat("Reply with JSON only.", 'Return {"ok": true}.', json_mode=True, max_tokens=200)
            return {"ok": True, "model": c.model, "reply": out, "latency": round(time.time() - t0, 2)}
        j = JevClient(cfg["jev_provider"], cfg["jev_model"], cfg["jev_key"], timeout=20)
        ans, meta = j.ask(json.dumps({"notebook": ["Fresh boot prints by the door: the culprit wears large boots."]}),
                          {"culprit": {"type": "choice", "instructions": "Who is most likely the culprit?",
                                       "criteria": {"S1": "wears small boots", "S2": "wears large boots"}}})
        return {"ok": True, "model": meta.get("model"), "reply": ans, "usage": meta.get("usage"),
                "latency": round(time.time() - t0, 2)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": redact(e)[:300]}


def serve(host="127.0.0.1", port=8781):
    def stop():
        if STATE["engine"]:
            STATE["engine"].stopped = True
    _serve(Handler, host, port, "jev-swarm-games holmes (The Irregulars)", on_exit=stop)
