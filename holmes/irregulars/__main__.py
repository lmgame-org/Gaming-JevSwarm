import argparse

from .server import serve

ap = argparse.ArgumentParser(prog="python3 -m irregulars", description="The Irregulars: Holmes case engine, Solo and Swarm")
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8781)
a = ap.parse_args()
serve(a.host, a.port)
