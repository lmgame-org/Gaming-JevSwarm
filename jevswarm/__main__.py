import argparse

from .server import serve

ap = argparse.ArgumentParser(prog="python3 -m jevswarm", description="Jev fish-schooling simulator")
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8777)
a = ap.parse_args()
serve(a.host, a.port)
