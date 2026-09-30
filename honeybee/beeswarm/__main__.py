import argparse

from .server import serve

ap = argparse.ArgumentParser(prog="python3 -m beeswarm", description="Jev honeybee nest-site selection simulator")
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8779)
a = ap.parse_args()
serve(a.host, a.port)
