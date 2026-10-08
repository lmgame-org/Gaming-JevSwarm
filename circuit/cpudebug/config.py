"""Hyperparameters and their launch-screen schema. Defaults are the hardened benchmark settings."""
from swarmcore.keys import CHAT_KEY_CANDIDATES, JEV_KEY_CANDIDATES, first_key
from swarmcore.params import merge

DEFAULTS = {
    # difficulty tier: easy and v2 are the single 96-block CPU; v3 is the 12-core chip
    "tier": "v2",                # easy | v2 | v3
    "n_cores": 12,
    "wire_frac": 0.35,           # v3: share of bugs on a wire between two blocks (delay or bus convention)
    "rare_mod": 4,               # v3: a rare-trigger bug fires for one input pattern in this many
    "bench_slots": 2,            # v3: bench drives that can run at the same time, for the whole team
    "drive_ticks": 3,            # v3: ticks one bench drive takes
    # run
    "mode": "leader",            # solo | leader (Baker Street) | swarm
    "seed": 1,
    "speed": 3.0,                # ticks per wall second (live-adjustable)
    # the bug (hardening)
    "bug_type": "any",           # any | stuck_at | swapped_mux | wrong_forwarding | off_by_one
    "failure_info": "final",     # final: only the final wrong registers / memory | first: the first wrong instruction
    "test_pick": "longest",      # longest | shortest failing test
    "window": 2,                 # cycles covered by one check
    "noise": 0.05,               # chance that a measured row has one glitched bit
    "rare_frac": 0.4,            # share of bugs that only misbehave for some inputs
    "double_frac": 0.2,          # share of cases with two bugs (both must be fixed)
    # clock and budgets (the same for every family)
    "deadline_hours": 6.0,
    "tick_min": 15.0,
    "budget_usd": 0.75,          # model spend cap per case; above it every agent falls back to its rule
    "liar_frac": 0.1,            # bribed boys / lying Irregulars
    "liar_defence": True,
    # solo
    "solo_policy": "rule",       # chat | jev | rule | random
    "probe_budget": 10,
    "probes_per_turn": 4,
    "max_turns": 6,
    # Baker Street
    "holmes": "rule",            # chat (gpt-6-astra) | rule (exact counting)
    "boy_policy": "jev",         # jev | rule | random
    "n_boys": 12,
    "wiggins": True,
    "errand_max": 3,
    "hq_max_calls": 6,
    "hq_min_new": 3,
    # swarm
    "swarm_policy": "rule",      # jev | rule | hybrid | random
    "n_agents": 100,
    "comm_range": 2,             # wires (graph hops on the schematic) a share carries
    "bandwidth": 3,
    "memory_cap": 60,            # measured rows an Irregular remembers
    "quorum_frac": 0.3,
    "skip_unchanged": True,
    # inference
    "concurrency": 24,
    "request_timeout_s": 30.0,
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
    "solo": "Solo debugger: one investigator probes block by block with a small probe budget",
    "leader": "Baker Street: Holmes directs a dozen boys; Wiggins carries orders out and reports back",
    "swarm": "Swarm: 100 Irregulars with no leader share findings by radio and close the case by quorum",
}
SOLO_POLICIES = {"chat": "gpt-6-astra (the genius)", "jev": "Jev", "rule": "rule: robust cone tracing (free)",
                 "random": "random (free)"}
HOLMES = {"chat": "gpt-6-astra reads the reports and plans", "rule": "exact counting with the back-trace planner (free)"}
BOYS = {"jev": "Jev", "rule": "rule (free)", "random": "random (free)"}
SWARM_POLICIES = {"jev": "Jev decides moves and votes", "rule": "rule (free)",
                  "hybrid": "hybrid: Jev moves, exact counting votes", "random": "random (free)"}
BUG_TYPES = {"any": "any of the four", "stuck_at": "stuck-at wire", "swapped_mux": "swapped mux inputs",
             "wrong_forwarding": "wrong forwarding / hazard path", "off_by_one": "off-by-one"}

PRESETS = {
    "baker_jev": {"label": "Baker Street: counting Holmes, Jev boys", "overrides": {}},
    "baker_genius": {"label": "Baker Street: gpt-6-astra Holmes, Jev boys", "overrides": {"holmes": "chat"}},
    "solo_genius": {"label": "Solo gpt-6-astra", "overrides": {"mode": "solo", "solo_policy": "chat"}},
    "solo_rule": {"label": "Solo rule (cone tracing)", "overrides": {"mode": "solo"}},
    "swarm_rule": {"label": "Swarm: 100 rule Irregulars", "overrides": {"mode": "swarm"}},
    "swarm_jev": {"label": "Swarm: 100 Jev Irregulars", "overrides": {"mode": "swarm", "swarm_policy": "jev"}},
    "easy": {"label": "Easy: the original setting (first wrong instruction, no noise, no liars)",
             "overrides": {"tier": "easy", "failure_info": "first", "test_pick": "shortest", "window": 4, "noise": 0.0,
                           "rare_frac": 0.0, "double_frac": 0.0, "liar_frac": 0.0, "probe_budget": 40}},
    "v2": {"label": "v2: hardened single CPU (96 blocks)", "overrides": {"tier": "v2"}},
    "v3": {"label": "v3: 12-core chip (1,187 blocks), wire bugs, scarce bench, innocent fixes penalised",
           "overrides": {"tier": "v3"}},
}

PRESET_KEY = "preset"

SCHEMA = [
    ("Run", [
        ("mode", "Who debugs", "choice", MODES),
        ("seed", "Bug number (same number, same bug)", "int", {"min": 0}),
        ("speed", "Playback speed (ticks per second)", "float", {"min": 0.1, "max": 30}),
    ]),
    ("Difficulty tier", [
        ("tier", "Tier", "choice", {"easy": "easy: the original single CPU", "v2": "v2: hardened single CPU",
                                    "v3": "v3: 12-core chip with wire bugs"}),
        ("n_cores", "v3: cores on the chip", "int", {"min": 2, "max": 16}),
        ("wire_frac", "v3: wire bugs (share, 0-1)", "float", {"min": 0, "max": 1}),
        ("rare_mod", "v3: a rare trigger fires 1 time in", "int", {"min": 2, "max": 16}),
        ("bench_slots", "v3: bench slots shared by the team", "int", {"min": 1, "max": 20}),
        ("drive_ticks", "v3: ticks per bench drive", "int", {"min": 1, "max": 10}),
    ]),
    ("The bug (hardening)", [
        ("bug_type", "Kind of bug", "choice", BUG_TYPES),
        ("failure_info", "What the investigators are told", "choice", {
            "final": "only the final wrong registers / memory", "first": "the first wrong instruction and its cycle"}),
        ("test_pick", "Which failing test they get", "choice", {"longest": "the longest", "shortest": "the shortest"}),
        ("window", "Cycles seen by one check", "int", {"min": 1, "max": 12}),
        ("noise", "Glitched measurements (share of rows, 0-1)", "float", {"min": 0, "max": 0.5}),
        ("rare_frac", "Rare-trigger bugs (share, 0-1)", "float", {"min": 0, "max": 1}),
        ("double_frac", "Cases with two bugs (share, 0-1)", "float", {"min": 0, "max": 1}),
    ]),
    ("Clock, budgets and liars (the same for every family)", [
        ("deadline_hours", "Time limit (case hours)", "float", {"min": 0.5, "max": 48}),
        ("tick_min", "Case minutes per tick", "float", {"min": 1}),
        ("budget_usd", "Model spend cap per case ($)", "float", {"min": 0}),
        ("liar_frac", "Bribed boys / lying Irregulars (share, 0-1)", "float", {"min": 0, "max": 1}),
        ("liar_defence", "Liar defence (two sources per mismatch, outvoted lose trust)", "bool", {}),
    ]),
    ("Solo debugger", [
        ("solo_policy", "Debugger", "choice", SOLO_POLICIES),
        ("probe_budget", "Probes allowed", "int", {"min": 1, "max": 200}),
        ("probes_per_turn", "Genius: probes per turn", "int", {"min": 1, "max": 20}),
        ("max_turns", "Genius: most turns", "int", {"min": 1, "max": 30}),
    ]),
    ("Baker Street", [
        ("holmes", "Holmes, the decision-maker", "choice", HOLMES),
        ("boy_policy", "Street boys' choices", "choice", BOYS),
        ("n_boys", "Number of boys", "int", {"min": 1, "max": 100}),
        ("wiggins", "Wiggins collects reports at a post near the boys", "bool", {}),
        ("errand_max", "Most blocks in one errand", "int", {"min": 1, "max": 6}),
        ("hq_max_calls", "Most planning rounds for gpt-6-astra Holmes", "int", {"min": 1, "max": 40}),
        ("hq_min_new", "Reports needed before Holmes plans again", "int", {"min": 1, "max": 20}),
    ]),
    ("Swarm", [
        ("swarm_policy", "Swarm type", "choice", SWARM_POLICIES),
        ("n_agents", "Irregulars", "int", {"min": 2, "max": 300}),
        ("comm_range", "Radio range (wires)", "int", {"min": 0, "max": 12}),
        ("bandwidth", "Shares each Irregular takes in per tick", "int", {"min": 0, "max": 20}),
        ("memory_cap", "Rows each Irregular remembers", "int", {"min": 4, "max": 1000}),
        ("quorum_frac", "Votes needed to close the case (share, 0-1)", "float", {"min": 0.02, "max": 1}),
        ("skip_unchanged", "Save calls: an Irregular with nothing new waits without asking Jev", "bool", {}),
    ]),
    ("Models and costs", [
        ("concurrency", "Model calls at the same time", "int", {"min": 1, "max": 128}),
        ("request_timeout_s", "Time allowed per Jev call (s)", "float", {"min": 0.5}),
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


# v3 changes these defaults unless the caller sets them (a bigger chip needs a wider window, a longer clock and a
# quorum the scattered swarm can reach)
V3_DEFAULTS = {"window": 4, "deadline_hours": 8.0, "quorum_frac": 0.12, "probe_budget": 32}


def coerce(cfg):
    out = dict(DEFAULTS)
    if (cfg or {}).get("tier") == "v3" or ((cfg or {}).get("preset") == "v3"):
        out.update({k: v for k, v in V3_DEFAULTS.items() if k not in (cfg or {})})
    out = merge(DEFAULTS, PRESETS, PRESET_KEY, cfg, base=out)
    for k, opts in (("mode", MODES), ("solo_policy", SOLO_POLICIES), ("holmes", HOLMES), ("boy_policy", BOYS),
                    ("swarm_policy", SWARM_POLICIES), ("bug_type", BUG_TYPES),
                    ("tier", {"easy": 1, "v2": 1, "v3": 1})):
        if out[k] not in opts:
            out[k] = DEFAULTS[k]
    return out
