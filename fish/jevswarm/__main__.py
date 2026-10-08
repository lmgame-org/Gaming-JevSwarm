"""python3 -m jevswarm [--port N] [--preset NAME] [--set key=value ...]; options: swarmcore/cli.py."""
from swarmcore.cli import app_main

from . import config
from .server import serve

app_main(config, serve, prog="python3 -m jevswarm", description="Fish schooling under predator attack, one Jev decision per fish", port=8777)
