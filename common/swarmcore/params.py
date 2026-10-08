"""The hyperparameter contract every game follows, and the helpers that implement it.

Each game's `config.py` exposes:

    DEFAULTS    {key: default}; the type of the default is the type of the setting
    PRESETS     {name: {"label": str, "overrides": {key: value}}}
    PRESET_KEY  the DEFAULTS key that selects a preset ("scenario" for fish and honeybee, "preset" otherwise)
    SCHEMA      [(group, [(key, label, kind, extra), ...]), ...] for the launch screen; kind: int|float|bool|choice|text
    LIVE_KEYS   settings the viewer may change while a run is live (logged as interventions)
    coerce(cfg) the full, validated config: DEFAULTS, then the preset's overrides, then cfg

The same contract feeds the browser launch screen (GET /api/schema), the command line (`--preset`, `--set`,
`--config`, see cli.py) and the batch runners (`key=value` overrides).
"""
import json


def coerce_value(default, v):
    """`v` converted to the type of `default`. Raises ValueError or TypeError when it cannot be."""
    if isinstance(default, bool):
        return v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "on", "yes")
    if isinstance(default, int):
        return int(float(v))
    if isinstance(default, float):
        return float(v)
    return str(v)


def merge(defaults, presets, preset_key, cfg, keep_empty=(), base=None):
    """`base` (default DEFAULTS), then the selected preset's overrides, then cfg with type coercion.

    Unknown keys and values that do not convert are skipped.
    """
    cfg = cfg or {}
    out = dict(defaults if base is None else base)
    pre = cfg.get(preset_key, out.get(preset_key))
    if pre in presets:
        out.update(presets[pre]["overrides"])
    for k, v in cfg.items():
        if k not in defaults or v is None:
            continue
        if v == "":
            if k in keep_empty:
                out[k] = ""
            continue
        try:
            out[k] = coerce_value(defaults[k], v)
        except (TypeError, ValueError):
            pass
    return out


def parse_assignments(items):
    """["a=1", "b=x"] -> {"a": "1", "b": "x"}. Values stay strings; coerce() types them."""
    out = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"expected key=value, got {it!r}")
        k, v = it.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def load_config_file(path):
    """A JSON file of {key: value} settings (the same shape the launch screen sends)."""
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: expected a JSON object of settings")
    return data.get("cfg", data)
