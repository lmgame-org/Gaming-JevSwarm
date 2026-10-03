"""Hyperparameters and their launch-screen schema."""
from swarmcore.keys import CHAT_KEY_CANDIDATES, JEV_KEY_CANDIDATES, first_key

DEFAULTS = {
    # run
    "mode": "jev",               # jev | hybrid | cone | rule_swarm | genius
    "seed": 1,
    "speed": 2.0,                # steps per wall second (live-adjustable)
    # case
    "bug_type": "any",           # any | stuck_at | swapped_mux | wrong_forwarding | off_by_one
    "window": 4,                 # cycles covered by one `check` probe
    # budgets (the same for every mode)
    "probe_budget": 40,
    "budget_usd": 0.40,          # dollar cap per case; the genius gets exactly this, the swarm stops calling models above it
    # swarm
    "n_irregulars": 8,
    "probes_per_irregular": 2,
    "max_rounds": 10,
    "assign": "mixed",           # block | window | mixed: what Holmes hands each Irregular
    "clear_below": 0.35,         # Jev mode: an Irregular's 'faulty' answer below this clears the cycles it checked
    "suspect_above": 0.65,       # Jev mode: above this the block becomes a suspect
    "holmes_ready_at": 0.6,      # Jev mode: Holmes names the culprit once his 'ready' answer reaches this
    "red_herrings": True,        # Wiggins drops suspects whose bad values are explained by an upstream suspect
    # genius
    "probes_per_turn": 6,
    "max_turns": 8,
    # inference
    "concurrency": 16,
    "request_timeout_s": 10.0,
    "jev_provider": "openrouter",
    "jev_model": "typesafe/jev-1.13",
    "jev_key": first_key(JEV_KEY_CANDIDATES),
    "chat_model": "gpt-6-astra",
    "chat_key": first_key(CHAT_KEY_CANDIDATES),
    "chat_price_in": 10.0,       # gpt-6-astra list price, USD per million tokens (OpenAI returns no cost)
    "chat_price_cached": 1.0,
    "chat_price_out": 50.0,
}

MODES = {
    "jev": "Jev swarm: Jev Irregulars probe and judge, Wiggins gathers, Jev Holmes names the bug",
    "hybrid": "Hybrid swarm: Jev picks where to probe, exact logic judges, tallies and deduces",
    "cone": "Exact cone tracing: one tracer walks back from the failure, no model (free)",
    "rule_swarm": "Rule swarm: the swarm machinery with exact rules everywhere, no model (free)",
    "genius": "Solo genius: gpt-6-astra reads the whole netlist and the failing test, same $ budget",
}
BUG_TYPES = {"any": "any of the four", "stuck_at": "stuck-at wire", "swapped_mux": "swapped mux inputs",
             "wrong_forwarding": "wrong forwarding / hazard path", "off_by_one": "off-by-one"}

PRESETS = {
    "jev": {"label": "Jev swarm (8 Irregulars)", "overrides": {}},
    "hybrid": {"label": "Hybrid swarm", "overrides": {"mode": "hybrid"}},
    "cone": {"label": "Exact cone tracing (free)", "overrides": {"mode": "cone"}},
    "genius": {"label": "Solo genius gpt-6-astra", "overrides": {"mode": "genius"}},
    "tight": {"label": "Jev swarm, tight probe budget (20)", "overrides": {"probe_budget": 20}},
    "big": {"label": "Jev swarm, 16 Irregulars, 1 probe each", "overrides": {"n_irregulars": 16, "probes_per_irregular": 1}},
    "forwarding": {"label": "Forwarding bugs only", "overrides": {"bug_type": "wrong_forwarding"}},
}

SCHEMA = [
    ("Run", [
        ("mode", "Who debugs", "choice", MODES),
        ("seed", "Bug number (same number, same bug)", "int", {"min": 0}),
        ("speed", "Playback speed (steps per second)", "float", {"min": 0.1, "max": 30}),
    ]),
    ("The bug", [
        ("bug_type", "Kind of bug", "choice", BUG_TYPES),
        ("window", "Cycles seen by one check probe", "int", {"min": 1, "max": 12}),
    ]),
    ("Budgets (the same for every mode)", [
        ("probe_budget", "Probes allowed (checks + bench drives)", "int", {"min": 1, "max": 400}),
        ("budget_usd", "Model spend allowed per case ($)", "float", {"min": 0}),
    ]),
    ("Swarm", [
        ("n_irregulars", "Irregulars", "int", {"min": 1, "max": 64}),
        ("probes_per_irregular", "Probes per Irregular per round", "int", {"min": 1, "max": 6}),
        ("max_rounds", "Most scatter-gather rounds", "int", {"min": 1, "max": 40}),
        ("assign", "What each Irregular is given", "choice", {
            "mixed": "mixed: some get one block, some a window of the waveform",
            "block": "one block each", "window": "one window of the waveform each"}),
        ("clear_below", "Jev: a 'faulty' answer below this clears the block", "float", {"min": 0, "max": 1}),
        ("suspect_above", "Jev: above this the block is a suspect", "float", {"min": 0, "max": 1}),
        ("holmes_ready_at", "Jev Holmes answers once 'ready' reaches", "float", {"min": 0, "max": 1}),
        ("red_herrings", "Wiggins clears suspects explained by an upstream suspect", "bool", {}),
    ]),
    ("Solo genius", [
        ("probes_per_turn", "Probes per turn", "int", {"min": 1, "max": 20}),
        ("max_turns", "Most turns", "int", {"min": 1, "max": 30}),
    ]),
    ("Models and costs", [
        ("concurrency", "Model calls at the same time", "int", {"min": 1, "max": 128}),
        ("request_timeout_s", "Time allowed per call (s)", "float", {"min": 0.5}),
        ("jev_model", "Jev model", "text", {}),
        ("jev_key", "Jev key file (OpenRouter)", "text", {}),
        ("chat_model", "Genius model", "text", {}),
        ("chat_key", "Genius key file (OpenAI)", "text", {}),
        ("chat_price_in", "Genius $ per million input tokens", "float", {"min": 0}),
        ("chat_price_cached", "Genius $ per million cached input tokens", "float", {"min": 0}),
        ("chat_price_out", "Genius $ per million output tokens", "float", {"min": 0}),
    ]),
]

LIVE_KEYS = {"speed"}


def coerce(cfg):
    out = dict(DEFAULTS)
    pre = (cfg or {}).get("preset")
    if pre in PRESETS:
        out.update(PRESETS[pre]["overrides"])
    for k, v in (cfg or {}).items():
        if k not in DEFAULTS or v is None or v == "":
            continue
        d = DEFAULTS[k]
        try:
            if isinstance(d, bool):
                out[k] = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
            elif isinstance(d, int):
                out[k] = int(float(v))
            elif isinstance(d, float):
                out[k] = float(v)
            else:
                out[k] = str(v)
        except (TypeError, ValueError):
            pass
    if out["mode"] not in MODES:
        out["mode"] = "jev"
    if out["bug_type"] not in BUG_TYPES:
        out["bug_type"] = "any"
    return out
