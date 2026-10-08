"""python3 -m irregulars [--port N] [--preset NAME] [--set key=value ...]; options: swarmcore/cli.py."""
from swarmcore.cli import app_main

from . import config
from .server import serve

app_main(config, serve, prog="python3 -m irregulars", description="The Irregulars: a Holmes case for one detective or a Jev swarm", port=8781)
