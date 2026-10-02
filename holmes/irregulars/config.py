"""Hyperparameters and their launch-screen schema.

Units: case time in minutes (the clock starts at 08:00 on the morning the body is found), distances in map units of
10 m. One Solo visit costs the cab ride plus an interview; one Swarm tick is `tick_min` minutes for every Irregular.
"""
from swarmcore.keys import CHAT_KEY_CANDIDATES, JEV_KEY_CANDIDATES, first_key

DEFAULTS = {
    # run
    "mode": "solo",              # solo | swarm
    "seed": 1,
    "speed": 1.5,                # steps (Solo visits or Swarm ticks) per wall second, live-adjustable
    # case
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
    "swarm_ticks": 32,           # clock: ticks before the case goes cold
    "tick_min": 15.0,
    "tail_success": 0.6,         # chance tailing the culprit reveals the hideout's district
    "corroboration": "address",  # liar defence: each witness address counts once; contradicting first-hand -> distrust
    "skip_unchanged": True,      # an Irregular whose view is unchanged since it chose WAIT waits again, no call
    "holmes": "chat",            # baker_street: who Holmes is (chat = gpt-6-astra, rule = exact counting + rule planner)
    "boy_policy": "jev",         # baker_street: the boys' small local choices (jev | rule)
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
    "jev": "Jev (TypeSafe System One): one typed call per step, choice over moves plus culprit/motive/hideout",
    "chat": "Genius: chat model (default gpt-6-astra) reads the whole notebook each step",
    "rule": "Rule baseline: follows pointers, counts corroborating facts, accuses when sure (free)",
    "random": "Random: visits uniformly at random, guesses at random (free)",
}
SWARM_POLICIES = {
    "jev": "Jev per Irregular, reflex rule if a call is too slow or fails",
    "hybrid": "Jev picks each Irregular's action; its votes come from exact counting of the leads it holds",
    "hybrid_genius": "Jev Irregulars gather; a genius at Scotland Yard reads the leads that reach it and closes the case",
    "baker_street": "Scatter and gather as in the stories: Holmes at 221B directs Wiggins and the boys, who run back to report",
    "rule": "Reflex rule per Irregular: share what is new, walk to unvisited neighbours, vote when sure (free)",
    "random": "Random moves, shares and votes (free)",
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
SCHEMA = [
    ("Run", [
        ("mode", "Mode", "choice", {"solo": "one detective", "swarm": "swarm of Irregulars"}),
        ("seed", "Case seed", "int", {"min": 0}),
        ("speed", "Steps per wall second", "float", {"min": 0.1, "max": 30}),
    ]),
    ("Case", [
        ("n_addresses", "Addresses on the map", "int", {"min": 20, "max": 300}),
        ("n_suspects", "Suspects", "int", {"min": 3, "max": 16}),
        ("n_motives", "Possible motives", "int", {"min": 2, "max": 6}),
        ("n_hideouts", "Possible hideouts", "int", {"min": 2, "max": 8}),
        ("redundancy", "Copies of each true fact", "int", {"min": 1, "max": 4}),
        ("lie_rate", "Lie rate", "float", {"min": 0, "max": 1}),
        ("red_herring_rate", "Red-herring rate", "float", {"min": 0, "max": 1}),
        ("pointer_rate", "Pointer rate", "float", {"min": 0, "max": 1}),
    ]),
    ("Solo detective", [
        ("policy", "Detective", "choice", POLICIES),
        ("visit_budget", "Visit budget", "int", {"min": 1, "max": 200}),
        ("deadline_hours", "Deadline (case hours)", "float", {"min": 1, "max": 96}),
        ("interview_min", "Minutes per interview", "float", {"min": 0}),
        ("cab_m_per_min", "Cab speed (m/min)", "float", {"min": 50}),
        ("jev_accuse_at", "Jev accuses when 'ready' reaches", "float", {"min": 0, "max": 1}),
    ]),
    ("Swarm of Irregulars", [
        ("swarm_policy", "Irregular policy", "choice", SWARM_POLICIES),
        ("n_irregulars", "Swarm size", "int", {"min": 3, "max": 400}),
        ("comm_range", "Radio / shouting range (x10 m)", "float", {"min": 0, "max": 1000}),
        ("bandwidth", "Messages taken in per tick", "int", {"min": 0, "max": 20}),
        ("memory_cap", "Leads remembered", "int", {"min": 1, "max": 50}),
        ("forget_rate", "Noisy memory (forget chance per tick)", "float", {"min": 0, "max": 1}),
        ("liar_frac", "Lying Irregulars (fraction)", "float", {"min": 0, "max": 1}),
        ("misinformed_frac", "Misinformed Irregulars (fraction)", "float", {"min": 0, "max": 1}),
        ("stubborn_frac", "Stubborn Irregulars (fraction)", "float", {"min": 0, "max": 1}),
        ("quorum_frac", "Quorum (share voting the same answer)", "float", {"min": 0.02, "max": 1}),
        ("swarm_ticks", "Clock (ticks)", "int", {"min": 1, "max": 200}),
        ("tick_min", "Case minutes per tick", "float", {"min": 1}),
        ("tail_success", "Tailing the culprit pays off", "float", {"min": 0, "max": 1}),
        ("corroboration", "Liar defence", "choice", {
            "address": "each witness address counts once; caught liars are distrusted and refuted",
            "none": "count every lead heard (no defence)"}),
        ("skip_unchanged", "Skip the call when nothing changed since a WAIT", "bool", {}),
        ("hub_max_calls", "Genius calls at the Yard (hybrid_genius)", "int", {"min": 1, "max": 64}),
        ("hub_min_new", "New leads before asking the genius again", "int", {"min": 1, "max": 50}),
        ("budget_cap_usd", "Swarm $ cap (0 = none)", "float", {"min": 0}),
    ]),
    ("Baker Street (scatter and gather)", [
        ("holmes", "Holmes", "choice", {"chat": "gpt-6-astra reads the reports and plans",
                                        "rule": "exact counting with a rule planner (free)"}),
        ("boy_policy", "Boys' local choices", "choice", {"jev": "Jev", "rule": "rule (free)"}),
        ("wiggins", "Wiggins collects reports at a forward post", "bool", {}),
        ("pay", "Pay", "choice", {"shilling_guinea": "a shilling a day, a guinea for the key lead (eager boys)",
                                  "none": "unpaid (boys give up after two calls)"}),
        ("walk_m_per_min", "Boys' running speed (m/min)", "float", {"min": 20}),
        ("hq_max_calls", "Most times Holmes re-plans", "int", {"min": 1, "max": 64}),
        ("hq_min_new", "New reports before re-planning (no Wiggins)", "int", {"min": 1, "max": 20}),
        ("errand_max", "Addresses per assignment", "int", {"min": 1, "max": 8}),
    ]),
    ("Models", [
        ("sampling", "Use Jev's distribution by", "choice", {"argmax": "argmax", "sample": "sampling (seeded)"}),
        ("concurrency", "Max requests in flight", "int", {"min": 1, "max": 256}),
        ("request_timeout_s", "Decision deadline per call (s)", "float", {"min": 0.5}),
        ("jev_model", "Jev model", "text", {}),
        ("jev_key", "Jev key file (OpenRouter)", "text", {}),
        ("chat_model", "Genius / analyst model", "text", {}),
        ("chat_key", "Genius key file (OpenAI)", "text", {}),
        ("chat_price_in", "Genius $ per M input tokens", "float", {"min": 0}),
        ("chat_price_cached", "Genius $ per M cached input", "float", {"min": 0}),
        ("chat_price_out", "Genius $ per M output tokens", "float", {"min": 0}),
    ]),
]

LIVE_KEYS = {"speed", "comm_range", "bandwidth", "forget_rate", "quorum_frac", "sampling"}


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
                out[k] = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "on", "yes")
            elif isinstance(d, int):
                out[k] = int(float(v))
            elif isinstance(d, float):
                out[k] = float(v)
            else:
                out[k] = str(v)
        except (TypeError, ValueError):
            pass
    out["n_addresses"] = max(20, min(300, out["n_addresses"]))
    out["n_suspects"] = max(3, min(16, out["n_suspects"]))
    out["n_motives"] = max(2, min(6, out["n_motives"]))
    out["n_hideouts"] = max(2, min(8, out["n_hideouts"]))
    # room for Baker Street, the Yard, the scene, the victim's home, hideouts, suspects' homes and some leads
    out["n_addresses"] = max(out["n_addresses"], out["n_suspects"] + out["n_hideouts"] + 12)
    if out["mode"] not in ("solo", "swarm"):
        out["mode"] = "solo"
    return out
