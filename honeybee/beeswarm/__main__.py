"""python3 -m beeswarm [--port N] [--preset NAME] [--set key=value ...]; options: swarmcore/cli.py."""
from swarmcore.cli import app_main

from . import config
from .server import serve

app_main(config, serve, prog="python3 -m beeswarm", description="Honeybee nest-site selection, one Jev decision per scout", port=8779)
