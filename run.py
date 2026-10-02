"""Launch a sub-project from the repo root.

    python3 run.py fish       [--port 8777]   fish schooling under predator attack
    python3 run.py honeybee   [--port 8779]   honeybee nest-site selection
    python3 run.py holmes     [--port 8781]   The Irregulars: Holmes case, Solo detective or Irregular swarm
    python3 run.py list
"""
import os
import runpy
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECTS = {
    "fish": ("fish", "jevswarm", "Fish schooling under predator attack (Jev per fish)"),
    "honeybee": ("honeybee", "beeswarm", "Honeybee nest-site selection (Jev per scout)"),
    "holmes": ("holmes", "irregulars", "The Irregulars: Holmes case, Solo detective or Irregular swarm"),
}
ALIASES = {"bee": "honeybee", "bees": "honeybee", "school": "fish", "irregulars": "holmes", "sherlock": "holmes"}


def main():
    args = sys.argv[1:]
    name = ALIASES.get(args[0], args[0]) if args else "list"
    if name not in PROJECTS:
        print(__doc__)
        for k, (_, _, desc) in PROJECTS.items():
            print(f"  {k:10s} {desc}")
        return
    folder, module, _ = PROJECTS[name]
    sys.path[:0] = [os.path.join(ROOT, folder), os.path.join(ROOT, "common")]
    sys.argv = [f"{module}"] + args[1:]
    runpy.run_module(module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
