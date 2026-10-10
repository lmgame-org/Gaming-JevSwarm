"""jev-swarm-games launcher: every game starts the same way from the repo root.

    python3 run.py list                                   the games, their ports and presets
    python3 run.py <game> [options]                       launch the browser viewer (launch screen + live view)
    python3 run.py <game> batch [batch options]           headless experiments, results under <game>/runs/
    python3 run.py <game> test                            offline correctness checks (no API calls)

Viewer options, the same for every game (see common/swarmcore/cli.py):
    --port N  --host H  --preset NAME  --config FILE.json  --set key=value ...
    --list-presets  --list-params  --print-config

Examples:
    python3 run.py holmes --list-params
    python3 run.py fish --preset two_predators --set n_fish=128 policy=local_react
    python3 run.py circuit --print-config --preset solo_genius
"""
import os
import runpy
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
# game: (folder, package, default port, description)
GAMES = {
    "holmes": ("holmes", "irregulars", 8781, "The Irregulars: a Holmes case, Solo detective or Irregular swarm"),
    "fish": ("fish", "jevswarm", 8777, "Fish schooling under predator attack (one Jev decision per fish)"),
    "honeybee": ("honeybee", "beeswarm", 8779, "Honeybee nest-site selection (one Jev decision per scout)"),
    "circuit": ("circuit", "cpudebug", 8783, "CPU debugging: Holmes, Wiggins and Jev Irregulars hunt one hardware bug"),
}
ALIASES = {"bee": "honeybee", "bees": "honeybee", "school": "fish", "irregulars": "holmes", "sherlock": "holmes",
           "cpu": "circuit", "debug": "circuit"}


def list_games():
    print(__doc__)
    print("Games:")
    for k, (folder, pkg, port, desc) in GAMES.items():
        print(f"  {k:9s} :{port}  {desc}   (package {folder}/{pkg})")


def main():
    args = sys.argv[1:]
    name = ALIASES.get(args[0], args[0]) if args else "list"
    if name not in GAMES:
        if name not in ("list", "-h", "--help"):
            print(f"unknown game {name!r}\n")
        return list_games()
    folder, module, _, _ = GAMES[name]
    rest = args[1:]
    paths = [os.path.join(ROOT, folder), os.path.join(ROOT, "common")]
    if rest[:1] == ["test"]:
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(paths + [os.environ.get("PYTHONPATH", "")]))
        sys.exit(subprocess.call([sys.executable, os.path.join(ROOT, folder, "tests", "test_checks.py")] + rest[1:],
                                 cwd=os.path.join(ROOT, folder), env=env))
    if rest[:1] == ["batch"]:
        module, rest = f"{module}.batch", rest[1:]
    sys.path[:0] = paths
    sys.argv = [f"python3 run.py {name}"] + rest
    runpy.run_module(module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
