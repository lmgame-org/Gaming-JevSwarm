"""HTTP server: launch screen, live viewer (Server-Sent Events) and a small JSON API. Stdlib only."""
import json
import os
import threading
import time
from urllib.parse import parse_qs, urlparse

from swarmcore.keys import key_files
from swarmcore.llm import JevClient, LLMClient
from swarmcore.web import BaseHandler, redact, serve as _serve

from . import observation as O
from .config import DEFAULTS, POLICIES, SCENARIOS, SCHEMA, coerce
from .engine import RUNS, Engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = {"engine": None, "thread": None}
LOCK = threading.Lock()


def list_runs():
    if not os.path.isdir(RUNS):
        return []
    out = []
    for name in sorted(os.listdir(RUNS), reverse=True)[:40]:
        d = os.path.join(RUNS, name)
        if not os.path.isfile(os.path.join(d, "summary.json")):
            continue
        with open(os.path.join(d, "summary.json")) as f:
            s = json.load(f)
        o = s.get("outcome") or {}
        out.append({"name": name, "policy": s.get("policy"), "chosen": o.get("chosen"), "correct": o.get("correct"),
                    "hours": s.get("decision_hours"), "cost": (s.get("inference") or {}).get("cost")})
    return out


class Handler(BaseHandler):
    WEB = os.path.join(ROOT, "web")

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        eng = STATE["engine"]
        if path == "/api/schema":
            return self.send_json({
                "schema": [[g, [list(f) for f in fields]] for g, fields in SCHEMA],
                "defaults": DEFAULTS, "scenarios": {k: v["overrides"] for k, v in SCENARIOS.items()},
                "policies": POLICIES, "key_files": key_files(), "runs": list_runs(),
                "instruction": O.instruction(DEFAULTS), "running": bool(eng and not eng.ended),
            })
        if path == "/api/scout":
            if not eng:
                return self.send_json({"error": "no run"}, 404)
            d = eng.scout_detail(int(parse_qs(url.query).get("id", ["0"])[0]))
            return self.send_json(d or {"error": "no such scout"}, 200 if d else 404)
        if path == "/api/frame":
            return self.send_json(eng.frame() if eng else {"error": "no run"}, 200 if eng else 404)
        if path == "/api/stream":
            if not eng:
                return self.send_json({"error": "no run"}, 404)
            return self.stream(eng, eng.frame(), lambda: STATE["engine"] is eng and not eng.stopped)
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
                        STATE["thread"].join(timeout=5)
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
        if path == "/api/predict":
            p = eng.add_prediction(body.get("kind"), body.get("value"), body.get("stake", 50))
            return self.send_json({"ok": bool(p), "prediction": p})
        if path == "/api/analyst":
            return self.send_json(ask_analyst(eng, body))
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
        obs = {"self": {"energy": 0.9, "currently_advertising": None, "last_action": "WAIT",
                        "last_result": "rested on the cluster", "sensed_quorum_at": None},
               "known_sites": [],
               "dances_observed_recently": {"window_min": 30, "sites": [
                   {"site": "C", "dancers": 3, "dances_seen": 4, "total_circuits": 260, "minutes_since_last_seen": 1}]}}
        ans, meta = j.ask(O.state_json(obs), {"action": {"type": "choice", "instructions": O.instruction(cfg),
                                                         "criteria": {"WAIT": "Rest and watch dances",
                                                                      "EXPLORE": "Search for a new site",
                                                                      "FOLLOW_DANCE_C": "Follow a dancer for site C"}}})
        return {"ok": True, "model": meta.get("model"), "reply": ans, "usage": meta.get("usage"),
                "latency": round(time.time() - t0, 2)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": redact(e)[:300]}


def ask_analyst(eng, body):
    cfg = eng.cfg
    try:
        c = LLMClient("openai", body.get("model") or cfg["chat_model"], cfg["chat_key"], timeout=90)
        q = (body.get("question") or "").strip() or "What is the swarm doing right now, and is it heading for the best site?"
        sys = ("You are an analyst watching a honeybee nest-site selection simulation in which each scout acts only "
               "on what it inspected itself and the dances it happened to see. You see the true site qualities and "
               "global metrics the scouts never see. Answer in at most 120 words, plainly, citing the numbers you "
               "rely on. Do not claim patterns the data does not show.")
        txt = c.chat(sys, f"Question: {q}\n\nSimulation data:\n{json.dumps(eng.analyst_context(), default=str)}",
                     json_mode=False, max_tokens=900)
        return {"ok": True, "model": c.model, "answer": txt}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": redact(e)[:300]}


def serve(host="127.0.0.1", port=8779):
    def stop():
        if STATE["engine"]:
            STATE["engine"].stopped = True
    _serve(Handler, host, port, "jev-swarm honeybee", on_exit=stop)
