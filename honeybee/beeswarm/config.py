"""Hyperparameters, their launch-screen schema, and scenario presets.

Units: time in simulated minutes, distances in metres, quality and energy in 0..1.
Starting values are loosely based on Seeley's field work (scouts fly ~6-7 m/s, inspect a cavity for 10-40 min,
dance circuits fall by ~15 per return trip, quorum of ~20-30 bees out of a few hundred scouts). They are
engineering defaults for a scaled-down swarm, not species estimates.
"""
from swarmcore.keys import CHAT_KEY_CANDIDATES, JEV_KEY_CANDIDATES, first_key
from swarmcore.params import merge

DEFAULTS = {
    # run
    "seed": 1,
    "scenario": "classic",
    "max_hours": 12.0,           # give up (no decision) after this much simulated time
    "speed": 6.0,                # simulated minutes per wall second (live-adjustable)
    # colony
    "swarm_size": 10000,         # bees in the cluster (display and piping only)
    "n_scouts": 100,             # scouts that make decisions; each decision is one policy call
    "quorum_frac": 0.15,         # quorum = this fraction of scouts present at one site at once
    "liftoff_delay_min": 45.0,   # piping period between first quorum and lift-off
    # sites
    "n_sites": 5,
    "best_quality": 0.9,
    "quality_gap": 0.2,          # best minus second best
    "min_quality": 0.15,
    "min_dist_m": 300.0,
    "max_dist_m": 3500.0,
    "best_far": False,           # put the best site at the far edge of the distance range
    "late_site_min": 0.0,        # >0: the best site only becomes discoverable at this minute
    # scouting mechanics
    "flight_m_per_min": 400.0,
    "inspect_min": 15.0,
    "explore_min": 40.0,         # length of a search flight
    "discover_rate": 0.35,       # chance a search finds some site (scaled by distance)
    "wait_min": 8.0,             # a WAIT decision rests this long on the cluster
    "circuits_max": 100,
    "circuit_s": 2.5,            # seconds per waggle circuit
    "dance_threshold": 0.5,      # below this estimated quality the dance has zero circuits
    "dance_attrition": 15,       # circuits lost per repeated bout for the same site
    "follow_success": 0.85,      # chance a dance follower actually finds the advertised site
    "energy_per_km": 0.03,
    "rest_gain_per_min": 0.015,
    # communication
    "dance_bandwidth": 4.0,      # dances a resting scout can attend per 10 minutes
    "dance_memory_min": 30.0,    # how long observed dances stay in a scout's memory
    # scout heterogeneity (the experimental knobs)
    "quality_noise": 0.10,       # sd of every scout's quality assessment
    "noisy_frac": 0.0,           # fraction of scouts with extra noise
    "noisy_sd": 0.30,
    "biased_frac": 0.0,          # fraction biased toward the nearest site
    "bias_strength": 0.25,
    "misinfo_frac": 0.0,         # fraction that start out believing the worst site is excellent
    "misinfo_boost": 0.6,
    "stubborn_frac": 0.0,        # fraction that never stop advertising their first site, never follow dances
    "confidence_calibration": 0.0,  # -1 underconfident .. 0 calibrated .. +1 everyone reports full confidence
    # policy and inference
    "policy": "jev",             # jev | chat | local_rule | random | replay
    "sampling": "sample",        # sample | argmax
    "fallback": "local_rule",
    "concurrency": 32,
    "request_timeout_s": 8.0,
    "jev_provider": "openrouter",
    "jev_model": "typesafe/jev-1.13",
    "jev_key": first_key(JEV_KEY_CANDIDATES),
    "chat_model": "gpt-6-astra",
    "chat_key": first_key(CHAT_KEY_CANDIDATES),
    "replay_run": "",
}

POLICIES = {
    "jev": "Jev (TypeSafe System One) choice over the scout's candidate actions",
    "chat": "Chat LLM (default gpt-6-astra) returns a distribution over the candidates",
    "local_rule": "Seeley-style rule: dance in proportion to quality, follow dances, re-inspect (free)",
    "random": "Uniform random over the candidate set (free)",
    "replay": "Replay the applied actions of a recorded run without calling any model",
}

SCENARIOS = {
    "classic": {"label": "Five sites, one clearly best", "overrides": {}},
    "close_call": {"label": "Two sites almost equal (gap 0.05)", "overrides": {"quality_gap": 0.05}},
    "far_best": {"label": "Best site is far, mediocre ones near", "overrides": {"best_far": True}},
    "late_best": {"label": "Best site appears after 2 h", "overrides": {"late_site_min": 120.0}},
    "misinformation": {"label": "15% of scouts believe the worst site is great", "overrides": {"misinfo_frac": 0.15}},
    "noisy_overconfident": {"label": "Noisy scouts that report full confidence",
                            "overrides": {"noisy_frac": 0.4, "confidence_calibration": 1.0}},
    "biased": {"label": "30% of scouts overrate the nearest site", "overrides": {"biased_frac": 0.3}},
    "stubborn": {"label": "10% stubborn scouts", "overrides": {"stubborn_frac": 0.1}},
    "low_bandwidth": {"label": "Scouts see only 1 dance per 10 min", "overrides": {"dance_bandwidth": 1.0}},
    "tiny_swarm": {"label": "Only 20 scouts", "overrides": {"n_scouts": 20}},
    "hasty": {"label": "Low quorum (speed over accuracy)", "overrides": {"quorum_frac": 0.08}},
}

# Launch-screen schema: (key, label, kind, extra). kind: int | float | bool | choice | text
# The shared hyperparameter contract (see swarmcore/params.py) calls scenarios presets.
PRESETS = SCENARIOS
PRESET_KEY = "scenario"

SCHEMA = [
    ("Run", [
        ("scenario", "Scenario", "choice", {k: v["label"] for k, v in SCENARIOS.items()}),
        ("seed", "World seed", "int", {"min": 0}),
        ("max_hours", "Give up after (sim hours)", "float", {"min": 0.5, "max": 72}),
        ("speed", "Sim minutes per wall second", "float", {"min": 0.2, "max": 240}),
    ]),
    ("Policy", [
        ("policy", "Action selector", "choice", POLICIES),
        ("sampling", "Use the distribution by", "choice", {"sample": "sampling (per-scout RNG)", "argmax": "argmax"}),
        ("fallback", "Failure fallback", "choice", {"local_rule": "local rule", "random": "random"}),
        ("concurrency", "Max requests in flight", "int", {"min": 1, "max": 256}),
        ("request_timeout_s", "Request timeout (wall s)", "float", {"min": 0.5}),
        ("jev_model", "Jev model", "text", {}),
        ("jev_key", "Jev key file (OpenRouter)", "text", {}),
        ("chat_model", "Chat / analyst model", "text", {}),
        ("chat_key", "Chat key file (OpenAI)", "text", {}),
        ("replay_run", "Replay run (folder in runs/)", "text", {}),
    ]),
    ("Colony and quorum", [
        ("n_scouts", "Scouts (decision makers)", "int", {"min": 3, "max": 1000}),
        ("swarm_size", "Bees in the swarm", "int", {"min": 100, "max": 50000}),
        ("quorum_frac", "Quorum (fraction of scouts at a site)", "float", {"min": 0.02, "max": 0.9}),
        ("liftoff_delay_min", "Piping before lift-off (min)", "float", {"min": 0}),
    ]),
    ("Candidate sites", [
        ("n_sites", "Sites", "int", {"min": 2, "max": 10}),
        ("best_quality", "Best quality", "float", {"min": 0.1, "max": 1}),
        ("quality_gap", "Gap to second best", "float", {"min": 0, "max": 0.9}),
        ("min_quality", "Worst quality", "float", {"min": 0, "max": 1}),
        ("min_dist_m", "Nearest distance (m)", "float", {"min": 50}),
        ("max_dist_m", "Farthest distance (m)", "float", {"min": 100}),
        ("best_far", "Best site is the farthest", "bool", {}),
        ("late_site_min", "Best site appears at (min, 0 = start)", "float", {"min": 0}),
    ]),
    ("Scouting", [
        ("inspect_min", "Inspection time (min)", "float", {"min": 1}),
        ("explore_min", "Search flight (min)", "float", {"min": 5}),
        ("discover_rate", "Search success rate", "float", {"min": 0, "max": 1}),
        ("wait_min", "WAIT rests for (min)", "float", {"min": 1}),
        ("flight_m_per_min", "Flight speed (m/min)", "float", {"min": 50}),
        ("circuits_max", "Max circuits per dance", "int", {"min": 5}),
        ("dance_threshold", "Min quality for any dance", "float", {"min": 0, "max": 1}),
        ("dance_attrition", "Circuits lost per repeat bout", "int", {"min": 0}),
        ("energy_per_km", "Energy per km flown", "float", {"min": 0}),
    ]),
    ("Communication", [
        ("dance_bandwidth", "Dances seen per 10 min (bandwidth)", "float", {"min": 0, "max": 50}),
        ("dance_memory_min", "Dance memory (min)", "float", {"min": 1}),
        ("follow_success", "Follower finds the site", "float", {"min": 0, "max": 1}),
    ]),
    ("Scout judgment", [
        ("quality_noise", "Assessment noise (sd)", "float", {"min": 0, "max": 1}),
        ("noisy_frac", "Noisy scouts (fraction)", "float", {"min": 0, "max": 1}),
        ("noisy_sd", "Noisy scouts' sd", "float", {"min": 0, "max": 1}),
        ("biased_frac", "Near-site biased scouts (fraction)", "float", {"min": 0, "max": 1}),
        ("bias_strength", "Bias strength", "float", {"min": 0, "max": 1}),
        ("misinfo_frac", "Misinformed scouts (fraction)", "float", {"min": 0, "max": 1}),
        ("misinfo_boost", "Misinformation boost", "float", {"min": 0, "max": 1}),
        ("stubborn_frac", "Stubborn scouts (fraction)", "float", {"min": 0, "max": 1}),
        ("confidence_calibration", "Confidence calibration (-1..1)", "float", {"min": -1, "max": 1}),
    ]),
]

# Settings the viewer may change while a run is live (logged as interventions).
LIVE_KEYS = {"speed", "sampling", "policy", "dance_bandwidth", "quality_noise", "follow_success",
             "confidence_calibration", "quorum_frac", "dance_attrition", "discover_rate"}


def coerce(cfg):
    """Merge user values over defaults with type coercion; apply scenario overrides first."""
    out = merge(DEFAULTS, SCENARIOS, PRESET_KEY, cfg, keep_empty=("replay_run",))
    out["n_sites"] = max(2, min(10, out["n_sites"]))
    out["confidence_calibration"] = max(-1.0, min(1.0, out["confidence_calibration"]))
    out["max_dist_m"] = max(out["max_dist_m"], out["min_dist_m"] + 50)
    return out


def quorum_count(cfg):
    return max(2, round(cfg["quorum_frac"] * cfg["n_scouts"]))
