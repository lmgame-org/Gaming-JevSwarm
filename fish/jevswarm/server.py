"""HTTP server: launch screen, live viewer (Server-Sent Events) and a small JSON API. Stdlib only."""
import json
import os
import queue
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from swarmcore.keys import key_files
from swarmcore.web import redact

from . import candidates as C
from .config import DEFAULTS, POLICIES, SCENARIOS, SCHEMA, coerce
from .engine import RUNS, Engine
from .llm import JevClient, LLMClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript", ".css": "text/css"}
STATE = {"engine": None, "thread": None}
LOCK = threading.Lock()


def list_runs():
    if not os.path.isdir(RUNS):
        return []
    out = []
    for name in sorted(os.listdir(RUNS), reverse=True)[:40]:
        d = os.path.join(RUNS, name)
        if not os.path.isfile(os.path.join(d, "config.json")):
            continue
        s = None
        if os.path.isfile(os.path.join(d, "summary.json")):
            with open(os.path.join(d, "summary.json")) as f:
                s = json.load(f)
        with open(os.path.join(d, "config.json")) as f:
            c = json.load(f)
        out.append({"name": name, "mode": c.get("mode"), "policy": c.get("policy"),
                    "survivors": s and s.get("survivors"), "captures": s and s.get("captures")})
    return out


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return {}

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        eng = STATE["engine"]
        if path == "/api/schema":
            return self._json({
                "schema": [[g, [list(f) for f in fields]] for g, fields in SCHEMA],
                "defaults": DEFAULTS, "scenarios": {k: v["overrides"] for k, v in SCENARIOS.items()},
                "policies": POLICIES, "key_files": key_files(), "runs": list_runs(),
                "instruction": C.DECISION_INSTRUCTION,
                "running": bool(eng and not eng.stopped),
            })
        if path == "/api/runs":
            return self._json(list_runs())
        if path == "/api/fish":
            if not eng:
                return self._json({"error": "no run"}, 404)
            i = int(parse_qs(url.query).get("id", ["0"])[0])
            d = eng.fish_detail(i)
            return self._json(d or {"error": "no such fish"}, 200 if d else 404)
        if path == "/api/frame":
            if not eng:
                return self._json({"error": "no run"}, 404)
            return self._json(eng.frame())
        if path == "/api/stream":
            return self._stream()
        if path == "/":
            path = "/index.html"
        fp = os.path.normpath(os.path.join(WEB, path.lstrip("/")))
        if not fp.startswith(WEB) or not os.path.isfile(fp):
            return self._json({"error": "not found"}, 404)
        with open(fp, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(os.path.splitext(fp)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _stream(self):
        eng = STATE["engine"]
        if not eng:
            return self._json({"error": "no run"}, 404)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = eng.subscribe()
        try:
            self.wfile.write(f"data: {json.dumps(eng.frame(), default=str)}\n\n".encode())
            self.wfile.flush()
            while STATE["engine"] is eng and not eng.stopped:
                try:
                    msg = q.get(timeout=5)
                    payload = f"data: {msg}\n\n"
                except queue.Empty:
                    payload = ": keepalive\n\n"
                self.wfile.write(payload.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            eng.unsubscribe(q)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()
        eng = STATE["engine"]
        if path == "/api/test":
            cfg = coerce(body.get("cfg") or {})
            t0 = time.time()
            try:
                if body.get("which") == "chat":
                    c = LLMClient("openai", cfg["chat_model"], cfg["chat_key"], timeout=60)
                    out = c.chat("Reply with JSON only.", 'Return {"ok": true}.', json_mode=True, max_tokens=200)
                    return self._json({"ok": True, "model": c.model, "reply": out, "latency": round(time.time() - t0, 2)})
                j = JevClient(cfg["jev_provider"], cfg["jev_model"], cfg["jev_key"], timeout=20)
                obs = {"self": {"speed": 2.0, "energy": 0.8, "previous_action": "ALIGN"},
                       "visible_fish": [], "visible_predators": [{"slot": "p0", "range": 5.0, "bearing_deg": 30}]}
                ans, meta = j.ask(json.dumps(obs), {"action": {"type": "choice", "instructions": C.instruction(cfg),
                                                               "criteria": {"CONTINUE": "Keep heading",
                                                                            "ESCAPE_S": "Burst away from p0"}}})
                return self._json({"ok": True, "model": meta.get("model"), "reply": ans,
                                   "latency": round(time.time() - t0, 2)})
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "error": redact(e)[:300]})
        if path == "/api/launch":
            with LOCK:
                old = STATE["engine"]
                if old:
                    old.stopped = True
                    if STATE["thread"]:
                        STATE["thread"].join(timeout=3)
                try:
                    e = Engine(body.get("cfg") or {}, realtime=True)
                except Exception as ex:  # noqa: BLE001
                    return self._json({"ok": False, "error": redact(f"{type(ex).__name__}: {ex}")}, 400)
                STATE["engine"] = e
                th = threading.Thread(target=e.run, daemon=True)
                STATE["thread"] = th
                th.start()
            return self._json({"ok": True, "run": os.path.basename(e.run_dir or "")})
        if not eng:
            return self._json({"error": "no run"}, 404)
        if path == "/api/cmd":
            eng.command(body)
            return self._json({"ok": True})
        if path == "/api/predict":
            p = eng.add_prediction(body.get("kind"), body.get("op"), body.get("value", 0),
                                   body.get("stake", 50), body.get("at"))
            return self._json({"ok": bool(p), "prediction": p})
        if path == "/api/analyst":
            cfg = eng.cfg
            try:
                c = LLMClient("openai", body.get("model") or cfg["chat_model"], cfg["chat_key"], timeout=90)
                ctx = eng.analyst_context()
                q = (body.get("question") or "").strip() or "What is the school doing right now, and why?"
                sys = ("You are an analyst watching a fish-schooling simulation in which each fish chooses actions "
                       "from its own local vision only. You see global evaluator metrics the fish never see. "
                       "Answer in at most 120 words, plainly, citing the numbers you rely on. Do not claim "
                       "emergent patterns the metrics do not show.")
                txt = c.chat(sys, f"Question: {q}\n\nSimulation data:\n{json.dumps(ctx, default=str)}",
                             json_mode=False, max_tokens=900)
                return self._json({"ok": True, "model": c.model, "answer": txt})
            except Exception as e:  # noqa: BLE001
                return self._json({"ok": False, "error": redact(e)[:300]})
        return self._json({"error": "not found"}, 404)


def serve(host="127.0.0.1", port=8777):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    print(f"jev-swarm-games fish running at http://{host}:{port}  (Ctrl+C to quit)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if STATE["engine"]:
            STATE["engine"].stopped = True
        httpd.server_close()
