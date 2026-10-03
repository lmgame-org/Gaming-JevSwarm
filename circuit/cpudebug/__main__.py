import argparse

from .server import serve

ap = argparse.ArgumentParser(prog="python3 -m cpudebug", description="Circuit: debug a CPU with Holmes and the Irregulars")
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8783)
a = ap.parse_args()
serve(a.host, a.port)
