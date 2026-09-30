"""Stdlib HTTP scaffolding shared by the sub-project viewers: JSON replies, static files, Server-Sent Events."""
import json
import os
import queue
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript", ".css": "text/css",
         ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg"}
SECRET = re.compile(r"(sk-[A-Za-z0-9_\-]{6})[A-Za-z0-9_\-*]+")


def redact(s):
    """Mask anything that looks like an API key before it reaches a log or the browser."""
    return SECRET.sub(r"\1…", str(s))


class BaseHandler(BaseHTTPRequestHandler):
    """Subclasses set WEB (static folder) and implement get_api / post_api returning a JSON-able object or None."""
    protocol_version = "HTTP/1.1"
    WEB = None

    def log_message(self, fmt, *args):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return {}

    def send_static(self, path):
        if path == "/":
            path = "/index.html"
        root = os.path.abspath(self.WEB)
        fp = os.path.normpath(os.path.join(root, path.lstrip("/")))
        if not fp.startswith(root + os.sep) or not os.path.isfile(fp):
            return self.send_json({"error": "not found"}, 404)
        with open(fp, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(os.path.splitext(fp)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def stream(self, source, first, alive):
        """Server-Sent Events: send `first`, then every message from `source.subscribe()` while alive() holds."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = source.subscribe()
        try:
            self.wfile.write(f"data: {json.dumps(first, default=str)}\n\n".encode())
            self.wfile.flush()
            while alive():
                try:
                    payload = f"data: {q.get(timeout=5)}\n\n"
                except queue.Empty:
                    payload = ": keepalive\n\n"
                self.wfile.write(payload.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            source.unsubscribe(q)


class Broadcaster:
    """Fan-out of JSON messages to SSE subscribers; slow subscribers drop old messages."""

    def __init__(self, maxsize=8):
        self._subs = []
        self._maxsize = maxsize

    def subscribe(self):
        q = queue.Queue(maxsize=self._maxsize)
        self._subs.append(q)
        return q

    def unsubscribe(self, q):
        if q in self._subs:
            self._subs.remove(q)

    def publish(self, obj):
        msg = json.dumps(obj, default=str)
        for q in list(self._subs):
            try:
                q.put_nowait(msg)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(msg)
                except (queue.Empty, queue.Full):
                    pass


def serve(handler, host, port, name, on_exit=None):
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    print(f"{name} running at http://{host}:{port}  (Ctrl+C to quit)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if on_exit:
            on_exit()
        httpd.server_close()
