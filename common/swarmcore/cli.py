"""One command line for every game: `python3 run.py <game> [options]` or `python3 -m <package> [options]`.

    --host H / --port N     where the viewer listens
    --preset NAME           start from a preset (fish and honeybee call these scenarios)
    --config FILE.json      settings from a JSON file ({key: value}, the same shape the launch screen sends)
    --set key=value ...     individual settings; applied after --preset and --config
    --list-presets          print the presets and exit
    --list-params           print every setting with its default, type and launch-screen label, and exit
    --print-config          print the resolved config as JSON and exit (nothing is launched)

Settings given here become the launch screen's starting values; everything stays editable in the browser.
"""
import argparse
import json
import sys

from .params import load_config_file, parse_assignments
from .web import redact


def _kind(default):
    return type(default).__name__ if not isinstance(default, str) else "str"


def _labels(schema):
    return {f[0]: (group, f[1]) for group, fields in schema for f in fields}


def resolve(config, preset=None, config_file=None, sets=None):
    """The full config for these command-line choices, through the game's own coerce()."""
    raw = {}
    if config_file:
        raw.update(load_config_file(config_file))
    raw.update(parse_assignments(sets))
    if preset:
        if preset not in config.PRESETS:
            raise SystemExit(f"unknown preset {preset!r}; try --list-presets")
        raw[config.PRESET_KEY] = preset
    unknown = sorted(k for k in raw if k not in config.DEFAULTS and k != config.PRESET_KEY)
    if unknown:
        raise SystemExit(f"unknown setting(s): {', '.join(unknown)}; try --list-params")
    return raw, config.coerce(raw)


def app_main(config, serve, prog, description, port, argv=None):
    ap = argparse.ArgumentParser(prog=prog, description=description,
                                 epilog="Settings: --list-params. Batch experiments: python3 run.py <game> batch --help")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=port)
    ap.add_argument("--preset", help=f"preset name ({config.PRESET_KEY})")
    ap.add_argument("--config", dest="config_file", metavar="FILE.json")
    ap.add_argument("--set", nargs="+", default=[], metavar="KEY=VALUE")
    ap.add_argument("--list-presets", action="store_true")
    ap.add_argument("--list-params", action="store_true")
    ap.add_argument("--print-config", action="store_true")
    a = ap.parse_args(argv)

    if a.list_presets:
        for k, v in config.PRESETS.items():
            extra = ", ".join(f"{kk}={vv}" for kk, vv in v["overrides"].items())
            print(f"  {k:16s} {v['label']}" + (f"  [{extra}]" if extra else ""))
        return
    if a.list_params:
        labels = _labels(config.SCHEMA)
        for k, d in config.DEFAULTS.items():
            group, label = labels.get(k, ("", ""))
            live = " (live)" if k in config.LIVE_KEYS else ""
            print(f"  {k:24s} {_kind(d):6s} {redact(json.dumps(d)):28s} {group + ': ' if group else ''}{label}{live}")
        return

    raw, cfg = resolve(config, a.preset, a.config_file, a.set)
    if a.print_config:
        print(redact(json.dumps(cfg, indent=2)))
        return
    changed = {k: v for k, v in cfg.items() if k in config.DEFAULTS and v != config.DEFAULTS[k]}
    if raw:
        # the launch screen and every later coerce() start from these values
        config.DEFAULTS.update(changed)
        shown = ", ".join(f"{k}={v}" for k, v in changed.items()) or "(same as defaults)"
        print(redact(f"launch settings: {shown}"), file=sys.stderr)
    serve(a.host, a.port)
