"""Hyperparameters and their launch-screen schema.

Units: case time in minutes (the clock starts at 08:00 on the morning the body is found), distances in map units of
10 m. One Solo visit costs the cab ride plus an interview; one Swarm tick is `tick_min` minutes for every Irregular.
"""
from swarmcore.keys import CHAT_KEY_CANDIDATES, JEV_KEY_CANDIDATES, first_key
from swarmcore.params import merge

DEFAULTS = {
    # run
    "mode": "solo",              # solo | swarm
    "seed": 1,
    "speed": 1.5,                # steps (Solo visits or Swarm ticks) per wall second, live-adjustable
    # case
    "difficulty": "standard",    # standard | holmesian (frame-up, planted clue, timed alibis, single key clues)
    "n_addresses": 100,
    "n_suspects": 10,
    "n_motives": 6,
    "n_hideouts": 8,
    "redundancy": 2,             # copies of each true key fact
    "lie_rate": 0.1,             # lies per key-lead copy (each lie contradicts one key fact)
    "red_herring_rate": 0.5,     # share of filler addresses with a suspicious-looking but empty lead
    "pointer_rate": 0.6,         # share of key leads that some other address points to
    # solo
    "policy": "jev",             # jev | chat | rule | random
    "visit_budget": 20,
    "deadline_hours": 12.0,
    "interview_min": 20.0,
    "cab_m_per_min": 200.0,
    "jev_accuse_at": 0.4,        # Jev accuses when its "ready" answer (yes/no probability) reaches this
    # swarm
    "swarm_policy": "jev",       # jev | rule | random
    "n_irregulars": 100,
    "comm_range": 100.0,         # map units (x10 m): who hears a SHARE
    "bandwidth": 3,              # messages an Irregular can take in per tick
    "memory_cap": 16,            # leads an Irregular can hold (oldest forgotten first)
    "forget_rate": 0.0,          # chance per tick of forgetting one random remembered lead
    "liar_frac": 0.0,            # Irregulars who share made-up leads and vote for a wrong answer
    "misinformed_frac": 0.0,     # Irregulars who start out holding one false lead
    "stubborn_frac": 0.0,        # Irregulars who never change their first firm vote
    "quorum_frac": 0.3,          # share of the swarm voting the identical answer that closes the case
    "swarm_ticks": 48,           # clock in ticks; follows deadline_hours unless set explicitly
    "tick_min": 15.0,
    "tail_success": 0.6,         # chance tailing the culprit reveals the hideout's district
    "corroboration": "address",  # liar defence: each witness address counts once; contradicting first-hand -> distrust
    "skip_unchanged": True,      # an Irregular whose view is unchanged since it chose WAIT waits again, no call
    "holmes": "chat",            # baker_street: who Holmes is (chat = gpt-6-astra, rule = exact counting + rule planner)
    "boy_policy": "jev",         # baker_street: the boys' small local choices (jev | rule | random)
    "wiggins": True,             # baker_street: Wiggins splits the boys and carries reports from a forward post
    "pay": "shilling_guinea",    # baker_street: shilling_guinea (eager boys, guinea for the key lead) | none
    "walk_m_per_min": 100.0,     # baker_street: a running boy's speed
    "hq_max_calls": 12,          # baker_street: most times Holmes re-plans in a case
    "hq_min_new": 2,             # baker_street (no Wiggins): new reports before Holmes re-plans
    "errand_max": 4,             # baker_street: addresses per assignment
    "hub_max_calls": 8,          # hybrid_genius: most genius calls per case
    "hub_min_new": 3,            # hybrid_genius: new leads at the Yard before the genius is asked again
    "budget_cap_usd": 0.0,       # 0 = none; above it every Irregular falls back to the reflex rule
    # inference
    "sampling": "argmax",        # argmax | sample
    "fallback": "rule",
    "concurrency": 32,
    "request_timeout_s": 8.0,
    "jev_provider": "openrouter",
    "jev_model": "typesafe/jev-1.13",
    "jev_key": first_key(JEV_KEY_CANDIDATES),
    "chat_model": "gpt-6-astra",
    "chat_key": first_key(CHAT_KEY_CANDIDATES),
    # gpt-6-astra list price (USD per million tokens) used to cost chat calls; OpenAI does not return a cost.
    "chat_price_in": 10.0,
    "chat_price_cached": 1.0,
    "chat_price_out": 50.0,
}

POLICIES = {
    "jev": "Jev: one quick call per step",
    "chat": "gpt-6-astra: reads the whole notebook each step",
    "rule": "heuristic: follows tips, counts corroboration (free)",
    "random": "random visits and guess (free)",
}
SWARM_POLICIES = {
    "baker_street": "Baker Street: Holmes directs the boys, who report back",
    "jev": "Jev swarm: every Irregular decides and votes with Jev",
    "rule": "heuristic swarm: the same simple heuristic for every Irregular (free)",
    "hybrid": "hybrid: Jev moves and shares, exact counting votes",
    "hybrid_genius": "hybrid + genius at the Yard: gpt-6-astra reads leads reaching Scotland Yard",
    "random": "random swarm (free)",
}

PRESETS = {
    "classic": {"label": "Default case, Solo with Jev", "overrides": {}},
    "genius": {"label": "Solo with the genius (gpt-6-astra)", "overrides": {"policy": "chat"}},
    "rule": {"label": "Solo with the rule baseline (free)", "overrides": {"policy": "rule"}},
    "liars": {"label": "Many lying witnesses (lie rate 0.4)", "overrides": {"lie_rate": 0.4}},
    "small": {"label": "Small case: 40 addresses, 6 suspects", "overrides": {"n_addresses": 40, "n_suspects": 6}},
    "baker_street": {"label": "Baker Street: Holmes (gpt-6-astra), Wiggins and a dozen boys",
                     "overrides": {"mode": "swarm", "swarm_policy": "baker_street", "n_irregulars": 12,
                                   "swarm_ticks": 48}},
    "baker_street_counting": {"label": "Baker Street with Holmes as exact counting (Jev boys)",
                              "overrides": {"mode": "swarm", "swarm_policy": "baker_street", "n_irregulars": 12,
                                            "swarm_ticks": 48, "holmes": "rule"}},
    "swarm": {"label": "Swarm: 100 Jev Irregulars", "overrides": {"mode": "swarm"}},
    "swarm_rule": {"label": "Swarm with the reflex rule (free)", "overrides": {"mode": "swarm", "swarm_policy": "rule"}},
    "swarm_liars": {"label": "Swarm with 15% lying Irregulars", "overrides": {"mode": "swarm", "liar_frac": 0.15}},
    "swarm_hybrid": {"label": "Hybrid: Jev gathers, exact counting votes", "overrides": {"mode": "swarm", "swarm_policy": "hybrid"}},
    "swarm_hybrid_genius": {"label": "Hybrid: Jev gathers, gpt-6-astra at the Yard decides",
                            "overrides": {"mode": "swarm", "swarm_policy": "hybrid_genius", "comm_range": 200.0}},
    "swarm_quiet": {"label": "Swarm with short radio range", "overrides": {"mode": "swarm", "comm_range": 50.0}},
}

# Launch-screen schema: (key, label, kind, extra). kind: int | float | bool | choice | text
PRESET_KEY = "preset"

SCHEMA = [
    ("Playback", [
        ("mode", "Who investigates", "choice", {"solo": "one detective", "swarm": "street boys (Baker Street or a swarm)"}),
        ("seed", "Case number (same number, same case)", "int", {"min": 0}),
        ("speed", "Playback speed (steps per second)", "float", {"min": 0.1, "max": 30}),
    ]),
    ("The case", [
        ("difficulty", "Kind of case", "choice", {"standard": "standard: true facts repeat, lies are lone voices",
                                                  "holmesian": "Holmesian: a planned crime with a frame-up, a planted clue and timed alibis"}),
        ("n_addresses", "Addresses on the map", "int", {"min": 20, "max": 300}),
        ("n_suspects", "Suspects", "int", {"min": 3, "max": 16}),
        ("n_motives", "Possible motives", "int", {"min": 2, "max": 6}),
        ("n_hideouts", "Possible hideouts", "int", {"min": 2, "max": 8}),
        ("redundancy", "Addresses that hold each true fact", "int", {"min": 1, "max": 4}),
        ("lie_rate", "Witnesses who lie (share of key leads, 0-1)", "float", {"min": 0, "max": 1}),
        ("red_herring_rate", "Red herrings (share of addresses without evidence, 0-1)", "float", {"min": 0, "max": 1}),
        ("pointer_rate", "'Ask at...' tips (share of key leads, 0-1)", "float", {"min": 0, "max": 1}),
    ]),
    ("Solo detective", [
        ("policy", "Detective", "choice", POLICIES),
        ("visit_budget", "Most visits allowed", "int", {"min": 1, "max": 200}),
        ("deadline_hours", "Time limit for every approach (case hours)", "float", {"min": 1, "max": 96}),
        ("interview_min", "Interview length (case minutes)", "float", {"min": 0}),
        ("cab_m_per_min", "Cab speed (metres per minute)", "float", {"min": 50}),
        ("jev_accuse_at", "Jev accuses when its readiness reaches (0-1)", "float", {"min": 0, "max": 1}),
    ]),
    ("Swarm baselines (also squad size and time for Baker Street)", [
        ("swarm_policy", "Swarm type", "choice", SWARM_POLICIES),
        ("n_irregulars", "Number of street boys / Irregulars", "int", {"min": 1, "max": 400}),
        ("swarm_ticks", "Time limit in ticks (follows the case hours)", "int", {"min": 1, "max": 400}),
        ("tick_min", "Case minutes per tick", "float", {"min": 1}),
        ("liar_frac", "Boys who lie, bribed (share, 0-1)", "float", {"min": 0, "max": 1}),
        ("misinformed_frac", "Boys who get a fact wrong (share, 0-1)", "float", {"min": 0, "max": 1}),
        ("comm_range", "How far a shout carries (x10 m)", "float", {"min": 0, "max": 1000}),
        ("bandwidth", "Shouts each Irregular can take in per tick", "int", {"min": 0, "max": 20}),
        ("memory_cap", "Leads each Irregular can remember", "int", {"min": 1, "max": 50}),
        ("forget_rate", "Chance per tick of forgetting a lead (0-1)", "float", {"min": 0, "max": 1}),
        ("stubborn_frac", "Irregulars who never change their vote (share, 0-1)", "float", {"min": 0, "max": 1}),
        ("quorum_frac", "Votes needed to close the case (share, 0-1)", "float", {"min": 0.02, "max": 1}),
        ("tail_success", "Chance that following the culprit reveals the hideout area (0-1)", "float", {"min": 0, "max": 1}),
        ("corroboration", "Liar defence", "choice", {
            "address": "on: each address counts once, caught liars are no longer believed",
            "none": "off: every lead heard counts"}),
        ("skip_unchanged", "Save calls: an Irregular with nothing new waits without asking Jev", "bool", {}),
        ("hub_max_calls", "Genius at the Yard: most calls per case", "int", {"min": 1, "max": 64}),
        ("hub_min_new", "Genius at the Yard: new leads before asking again", "int", {"min": 1, "max": 50}),
        ("budget_cap_usd", "Spending cap per case in $ (0 = none)", "float", {"min": 0}),
    ]),
    ("Baker Street", [
        ("holmes", "Holmes, the decision-maker", "choice", {"chat": "gpt-6-astra reads the reports and plans",
                                                            "rule": "counting heuristic: tallies the facts, plans by fixed priorities (free)"}),
        ("boy_policy", "Street boys' choices", "choice", {"jev": "Jev", "rule": "heuristic (free)", "random": "random (free)"}),
        ("wiggins", "Wiggins collects reports at a post near the boys", "bool", {}),
        ("pay", "Pay the boys", "choice", {"shilling_guinea": "a shilling a day and a guinea for the key lead",
                                          "none": "unpaid: boys give up after two addresses"}),
        ("walk_m_per_min", "Boys' running speed (metres per minute)", "float", {"min": 20}),
        ("hq_max_calls", "Most planning rounds for Holmes", "int", {"min": 1, "max": 64}),
        ("hq_min_new", "Reports needed before Holmes plans again (without Wiggins)", "int", {"min": 1, "max": 20}),
        ("errand_max", "Most addresses in one assignment", "int", {"min": 1, "max": 8}),
    ]),
    ("Models and costs", [
        ("sampling", "How Jev's answer becomes a move", "choice", {"argmax": "take its top choice", "sample": "draw from its probabilities"}),
        ("concurrency", "Model calls at the same time", "int", {"min": 1, "max": 256}),
        ("request_timeout_s", "Time allowed per call (seconds)", "float", {"min": 0.5}),
        ("jev_model", "Jev model name", "text", {}),
        ("jev_key", "Jev key file (OpenRouter)", "text", {}),
        ("chat_model", "Genius model name", "text", {}),
        ("chat_key", "Genius key file (OpenAI)", "text", {}),
        ("chat_price_in", "Genius price: $ per million input tokens", "float", {"min": 0}),
        ("chat_price_cached", "Genius price: $ per million cached input tokens", "float", {"min": 0}),
        ("chat_price_out", "Genius price: $ per million output tokens", "float", {"min": 0}),
    ]),
]

LIVE_KEYS = {"speed", "comm_range", "bandwidth", "forget_rate", "quorum_frac", "sampling"}


def coerce(cfg):
    out = merge(DEFAULTS, PRESETS, PRESET_KEY, cfg)
    pre = (cfg or {}).get(PRESET_KEY)
    out["n_addresses"] = max(20, min(300, out["n_addresses"]))
    out["n_suspects"] = max(3, min(16, out["n_suspects"]))
    # One time limit for every approach: the swarm clock follows the case hours unless ticks are set explicitly.
    explicit = "swarm_ticks" in (cfg or {}) or "swarm_ticks" in PRESETS.get(pre, {}).get("overrides", {})
    if not explicit:
        out["swarm_ticks"] = max(1, round(out["deadline_hours"] * 60 / out["tick_min"]))
    out["n_motives"] = max(2, min(6, out["n_motives"]))
    out["n_hideouts"] = max(2, min(8, out["n_hideouts"]))
    # room for Baker Street, the Yard, the scene, the victim's home, hideouts, suspects' homes and some leads
    out["n_addresses"] = max(out["n_addresses"], out["n_suspects"] + out["n_hideouts"] + 12)
    if out["difficulty"] not in ("standard", "holmesian"):
        out["difficulty"] = "standard"
    if out["mode"] not in ("solo", "swarm"):
        out["mode"] = "solo"
    return out
