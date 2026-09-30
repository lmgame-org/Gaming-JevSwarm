"""Hyperparameters, their launch-screen schema, and scenario presets.

Units: lengths in fish body lengths (BL), time in simulated seconds, angles in degrees.
Starting values follow the design doc; they are engineering defaults, not species estimates.
"""
import os

# First readable file wins. Keys are only ever read at call time and never logged.
JEV_KEY_CANDIDATES = [
    "/workspace/.credentials/openrouter_api_key",
    "~/.credentials/openrouter_api_key",
]
CHAT_KEY_CANDIDATES = [
    "/workspace/.credentials/llm_api_key",
    "~/.credentials/llm_api_key",
    "~/.credentials/astra_api_key",
    "~/.credentials/openai_key",
]


def first_key(paths):
    for p in paths:
        if os.path.isfile(os.path.expanduser(p)):
            return p
    return paths[0]


DEFAULTS = {
    # run
    "seed": 1,
    "scenario": "demo",
    "episode_s": 120.0,
    "attack_s": 20.0,
    "withdraw_s": 80.0,          # 0 = predator never withdraws
    "speed": 1.0,                # sim seconds per wall second (live-adjustable)
    # world
    "world_w": 120.0,
    "world_h": 80.0,
    "n_fish": 64,
    "n_predators": 1,
    "n_rocks": 0,
    "n_food": 0,
    # fish vision
    "vision_range": 12.0,
    "fov_deg": 240.0,
    "max_visible_fish": 8,
    "max_visible_predators": 2,
    "occlusion": True,
    "silhouette_samples": 3,
    "range_noise": 0.01,         # fractional sd
    "bearing_noise_deg": 1.0,
    "dropout": 0.02,
    "turbidity": 0.0,            # 0..1 shrinks the effective range
    "motion_estimates": True,    # ablation: remove neighbour motion estimates
    "escape_cues": True,         # label fast / sharply turning neighbours, offer FLEE_WITH, cue-aware instruction
    "memory_s": 0.0,             # 0 = strict current view; up to 2 s own-observation memory
    # timing
    "physics_hz": 60,
    "decision_hz": 2.0,
    "sensor_hz": 10,
    # fish motion and energy
    "fish_radius": 0.25,
    "cruise": 2.0,
    "burst": 4.0,
    "turn_deg_s": 180.0,
    "accel": 6.0,
    "sep_radius": 1.2,
    "burst_drain": 0.10,
    "recover_rate": 0.06,
    "burst_off": 0.15,
    "burst_on": 0.25,
    # predator
    "pred_vision": 20.0,
    "pred_fov_deg": 180.0,
    "pred_cruise": 2.5,
    "pred_burst": 4.5,
    "pred_turn_deg_s": 120.0,
    "pred_burst_s": 2.0,
    "pred_cooldown_s": 3.0,
    "pred_burst_range": 8.0,
    "pred_radius": 0.5,
    "capture_radius": 0.6,
    "capture_cooldown_s": 1.0,
    # policy and inference
    "policy": "jev",             # jev | chat | local_rule | local_react | random | fixed_school | replay
    "sampling": "sample",        # sample | argmax
    "mode": "interactive",       # interactive | controlled
    "fallback": "local_rule",
    "concurrency": 48,
    "request_timeout_s": 4.0,
    "barrier_deadline_s": 6.0,
    "stale_s": 0.5,
    "jev_provider": "openrouter",
    "jev_model": "typesafe/jev-1.13",
    "jev_key": first_key(JEV_KEY_CANDIDATES),
    "chat_model": "gpt-6-astra",
    "chat_key": first_key(CHAT_KEY_CANDIDATES),
    "replay_run": "",
}

POLICIES = {
    "jev": "Jev (TypeSafe System One) choice over the local candidates",
    "chat": "Chat LLM (default gpt-6-astra) returns a distribution over the candidates",
    "local_rule": "Local rule: school with visible fish, flee visible predators",
    "local_react": "Local rule that also follows visibly fast or turning neighbours",
    "random": "Uniform random over the candidate set",
    "fixed_school": "Always ALIGN (or CONTINUE): what the steering controller alone gives",
    "replay": "Replay the applied actions of a recorded run without calling any model",
}

SCENARIOS = {
    "demo": {"label": "First demo: flank attack, withdraw at 80 s", "overrides": {}},
    "flank": {"label": "Flank approach (no withdrawal)", "overrides": {"withdraw_s": 0}},
    "blind": {"label": "Attack from the blind sector", "overrides": {"withdraw_s": 0}},
    "rock": {"label": "Rock blocks the predator", "overrides": {"n_rocks": 4, "withdraw_s": 0}},
    "two_predators": {"label": "Two predators, both flanks", "overrides": {"n_predators": 2, "withdraw_s": 0}},
    "short_vision": {"label": "Shortened vision range (6 BL)", "overrides": {"vision_range": 6.0, "withdraw_s": 0}},
    "false_alarm": {"label": "False alarm: one fish forced to burst, no predator", "overrides": {"n_predators": 0}},
    "withdrawal": {"label": "Predator withdrawal at 50 s", "overrides": {"withdraw_s": 50.0}},
    "calm": {"label": "No predator (schooling only)", "overrides": {"n_predators": 0}},
}

# Launch-screen schema: (key, label, kind, extra). kind: int | float | bool | choice | text
SCHEMA = [
    ("Run", [
        ("scenario", "Scenario", "choice", {k: v["label"] for k, v in SCENARIOS.items()}),
        ("seed", "World seed", "int", {"min": 0}),
        ("episode_s", "Episode length (s)", "float", {"min": 10, "max": 1200}),
        ("attack_s", "Attack begins at (s)", "float", {"min": 0}),
        ("withdraw_s", "Predator withdraws at (s, 0 = never)", "float", {"min": 0}),
        ("speed", "Sim speed (x real time)", "float", {"min": 0.05, "max": 20}),
    ]),
    ("Policy", [
        ("policy", "Action selector", "choice", POLICIES),
        ("sampling", "Use the distribution by", "choice", {"sample": "sampling (per-fish RNG)", "argmax": "argmax"}),
        ("mode", "Execution mode", "choice", {
            "interactive": "Interactive: physics keeps running while Jev thinks",
            "controlled": "Controlled: decision barrier, physics pauses for inference"}),
        ("fallback", "Timeout / stale fallback", "choice", {"local_rule": "local rule", "fixed_school": "fixed school"}),
        ("concurrency", "Max requests in flight", "int", {"min": 1, "max": 512}),
        ("request_timeout_s", "Request timeout (wall s)", "float", {"min": 0.5}),
        ("jev_model", "Jev model", "text", {}),
        ("jev_key", "Jev key file (OpenRouter)", "text", {}),
        ("chat_model", "Chat model", "text", {}),
        ("chat_key", "Chat key file (OpenAI)", "text", {}),
        ("replay_run", "Replay run (folder in runs/)", "text", {}),
    ]),
    ("World", [
        ("n_fish", "Fish", "int", {"min": 1, "max": 1000}),
        ("n_predators", "Predators", "int", {"min": 0, "max": 4}),
        ("n_rocks", "Rocks", "int", {"min": 0, "max": 20}),
        ("n_food", "Food patches", "int", {"min": 0, "max": 20}),
        ("world_w", "Arena width (BL)", "float", {"min": 20}),
        ("world_h", "Arena height (BL)", "float", {"min": 20}),
    ]),
    ("Fish vision", [
        ("vision_range", "Vision radius (BL)", "float", {"min": 1, "max": 60}),
        ("fov_deg", "Field of view (deg)", "float", {"min": 30, "max": 360}),
        ("max_visible_fish", "Max visible fish", "int", {"min": 0, "max": 32}),
        ("max_visible_predators", "Max visible predators", "int", {"min": 0, "max": 4}),
        ("occlusion", "Occlusion by fish and rocks", "bool", {}),
        ("silhouette_samples", "Silhouette samples", "int", {"min": 1, "max": 7}),
        ("range_noise", "Range noise (fraction)", "float", {"min": 0}),
        ("bearing_noise_deg", "Bearing noise (deg)", "float", {"min": 0}),
        ("dropout", "Detection dropout", "float", {"min": 0, "max": 1}),
        ("turbidity", "Turbidity (0..1)", "float", {"min": 0, "max": 0.95}),
        ("motion_estimates", "Neighbour motion estimates", "bool", {}),
        ("escape_cues", "Neighbour escape cues (labels + FLEE_WITH)", "bool", {}),
        ("memory_s", "Own-observation memory (s, 0..2)", "float", {"min": 0, "max": 2}),
    ]),
    ("Timing and motion", [
        ("decision_hz", "Decisions per fish (Hz)", "float", {"min": 0.25, "max": 10}),
        ("sensor_hz", "Sensor refresh (Hz)", "int", {"min": 2, "max": 60}),
        ("cruise", "Cruise speed (BL/s)", "float", {"min": 0.1}),
        ("burst", "Burst speed (BL/s)", "float", {"min": 0.1}),
        ("turn_deg_s", "Turn limit (deg/s)", "float", {"min": 10}),
        ("burst_drain", "Burst drain (/s)", "float", {"min": 0}),
        ("recover_rate", "RECOVER restore (/s)", "float", {"min": 0}),
    ]),
    ("Predator", [
        ("pred_vision", "Vision radius (BL)", "float", {"min": 1}),
        ("pred_fov_deg", "Field of view (deg)", "float", {"min": 30, "max": 360}),
        ("pred_cruise", "Cruise (BL/s)", "float", {"min": 0.1}),
        ("pred_burst", "Burst (BL/s)", "float", {"min": 0.1}),
        ("pred_turn_deg_s", "Turn limit (deg/s)", "float", {"min": 10}),
        ("pred_burst_s", "Burst duration (s)", "float", {"min": 0}),
        ("pred_cooldown_s", "Burst cooldown (s)", "float", {"min": 0}),
        ("capture_radius", "Capture radius (BL)", "float", {"min": 0.1}),
    ]),
]

# Settings the viewer may change while a run is live (logged as interventions).
LIVE_KEYS = {"speed", "vision_range", "turbidity", "sampling", "policy", "fov_deg",
             "max_visible_fish", "occlusion", "motion_estimates", "dropout", "escape_cues"}


def coerce(cfg):
    """Merge user values over defaults with type coercion; apply scenario overrides first."""
    out = dict(DEFAULTS)
    scen = (cfg or {}).get("scenario", out["scenario"])
    if scen in SCENARIOS:
        out.update(SCENARIOS[scen]["overrides"])
    for k, v in (cfg or {}).items():
        if k not in DEFAULTS or v is None or v == "":
            if k in DEFAULTS and k in ("replay_run",):
                out[k] = ""
            continue
        d = DEFAULTS[k]
        try:
            if isinstance(d, bool):
                out[k] = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "on", "yes")
            elif isinstance(d, int):
                out[k] = int(float(v))
            elif isinstance(d, float):
                out[k] = float(v)
            else:
                out[k] = str(v)
        except (TypeError, ValueError):
            pass
    out["memory_s"] = max(0.0, min(2.0, out["memory_s"]))
    return out
