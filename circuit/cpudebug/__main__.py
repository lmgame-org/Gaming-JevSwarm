"""python3 -m cpudebug [--port N] [--preset NAME] [--set key=value ...]; options: swarmcore/cli.py."""
from swarmcore.cli import app_main

from . import config
from .server import serve

app_main(config, serve, prog="python3 -m cpudebug", description="Circuit: Holmes, Wiggins and Jev Irregulars hunt one CPU bug", port=8783)
