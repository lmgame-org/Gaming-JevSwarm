"""The challenge casebook: ten hard cases, each built to stress one weakness, and a runner that plays every
investigator on all of them.

  python3 -m irregulars.challenges --list
  python3 -m irregulars.challenges --max-usd 30            # every setting on every case
  python3 -m irregulars.challenges --only rule random       # just some settings (by key, see SETTINGS)

Each case is a fixed seed plus settings, so everyone gets exactly the same case. The seed is the first one at or
after `seed` that a careful reader can solve (the generator's oracle), so no case is impossible.
"""
import argparse
import concurrent.futures as cf
import json
import os
import time

from .batch import wilson
from .case import Case
from .config import coerce
from .engine import RUNS, Engine

CHALLENGES = [
    {"id": "frame", "title": "The Frame-Up", "seed": 101,
     "blurb": "The murderer's servants describe an innocent man and swear their master never left home. "
              "A planted clue at the scene backs them up.",
     "tests": "judging who is speaking, not how often a clue is repeated",
     "overrides": {"difficulty": "holmesian"}},
    {"id": "chorus", "title": "The Liars' Chorus", "seed": 102,
     "blurb": "Half the witnesses lie, and the same lie can turn up twice. The truth still turns up three times, "
              "if you find it.",
     "tests": "weighing many conflicting reports",
     "overrides": {"redundancy": 3, "lie_rate": 0.5}},
    {"id": "lone_clue", "title": "The Single Thread", "seed": 103,
     "blurb": "Every true fact is written down at exactly one address, and a few witnesses lie. Miss one door "
              "and the case may never close.",
     "tests": "covering the whole map; no second chances",
     "overrides": {"redundancy": 1, "lie_rate": 0.1}},
    {"id": "sprawl", "title": "The Sprawling City", "seed": 104,
     "blurb": "Three hundred addresses and sixteen suspects, but still only twelve hours.",
     "tests": "searching a big map quickly",
     "overrides": {"n_addresses": 300, "n_suspects": 16}},
    {"id": "dawn", "title": "Before the Dawn Train", "seed": 105,
     "blurb": "The murderer boards the dawn train in four hours. After that, nobody will ever find him.",
     "tests": "speed under a short deadline",
     "overrides": {"deadline_hours": 4.0}},
    {"id": "moriarty", "title": "Moriarty's Boys", "seed": 106,
     "blurb": "The Professor has bribed a quarter of the street boys to bring back false reports, and others have "
              "simply got it wrong.",
     "tests": "trusting your own helpers (a lone detective has none to betray him)",
     "overrides": {"liar_frac": 0.25, "misinformed_frac": 0.1}},
    {"id": "fog", "title": "The London Particular", "seed": 107,
     "blurb": "A pea-souper fog: nearly every address offers a tempting red herring, and almost nobody points you "
              "to the right door.",
     "tests": "ignoring noise without tips to follow",
     "overrides": {"red_herring_rate": 1.0, "pointer_rate": 0.1}},
    {"id": "frame_sprawl", "title": "The Frame-Up in the Sprawl", "seed": 108,
     "blurb": "A planned murder in a city of two hundred and fifty doors.",
     "tests": "reasoning and searching at once",
     "overrides": {"difficulty": "holmesian", "n_addresses": 250}},
    {"id": "frame_dawn", "title": "The Frame-Up at Dawn", "seed": 109,
     "blurb": "A planned murder, and only six hours before the trail goes cold.",
     "tests": "reasoning under time pressure",
     "overrides": {"difficulty": "holmesian", "deadline_hours": 6.0}},
    {"id": "perfect", "title": "The Perfect Crime", "seed": 110,
     "blurb": "A frame-up, extra lying witnesses, sixteen suspects, bribed street boys and eight hours. "
              "Everything at once.",
     "tests": "everything",
     "overrides": {"difficulty": "holmesian", "lie_rate": 0.3, "n_suspects": 16, "liar_frac": 0.15,
                   "deadline_hours": 8.0}},
]

# Every investigator setting from the benchmarks: (key, label, config).
SETTINGS = [
    ("solo_chat", "Solo · gpt-6-astra", {"mode": "solo", "policy": "chat"}),
    ("solo_jev", "Solo · Jev", {"mode": "solo", "policy": "jev"}),
    ("solo_rule", "Solo · heuristic", {"mode": "solo", "policy": "rule"}),
    ("solo_random", "Solo · random", {"mode": "solo", "policy": "random"}),
    ("baker_chat", "Baker Street · gpt-6-astra Holmes, Jev boys",
     {"mode": "swarm", "swarm_policy": "baker_street", "holmes": "chat", "boy_policy": "jev", "n_irregulars": 12}),
    ("baker_rule_jev", "Baker Street · counting Holmes, Jev boys",
     {"mode": "swarm", "swarm_policy": "baker_street", "holmes": "rule", "boy_policy": "jev", "n_irregulars": 12}),
    ("baker_rule", "Baker Street · counting Holmes, heuristic boys",
     {"mode": "swarm", "swarm_policy": "baker_street", "holmes": "rule", "boy_policy": "rule", "n_irregulars": 12}),
    ("swarm_jev", "Swarm · Jev, 2 km", {"mode": "swarm", "swarm_policy": "jev", "comm_range": 200}),
    ("swarm_hybrid", "Swarm · hybrid, 2 km", {"mode": "swarm", "swarm_policy": "hybrid", "comm_range": 200}),
    ("swarm_rule", "Swarm · heuristic, 2 km", {"mode": "swarm", "swarm_policy": "rule", "comm_range": 200}),
    ("swarm_random", "Swarm · random, 2 km", {"mode": "swarm", "swarm_policy": "random", "comm_range": 200}),
]
GPT = {"solo_chat", "baker_chat"}


def solvable_seed(ch):
    """The first seed at or after ch['seed'] whose case a careful reader can solve."""
    for seed in range(ch["seed"], ch["seed"] + 50):
        if all(Case(coerce({**ch["overrides"], "seed": seed})).solvable.values()):
            return seed
    return ch["seed"]


def case_cfg(ch):
    return {**ch["overrides"], "seed": solvable_seed(ch)}


def public():
    """For the launch screen: each case's settings, ready to apply."""
    return [{"id": c["id"], "title": c["title"], "blurb": c["blurb"], "tests": c["tests"], "cfg": case_cfg(c)}
            for c in CHALLENGES]


def main():
    ap = argparse.ArgumentParser(prog="python3 -m irregulars.challenges")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", nargs="*", default=[], help="setting keys to run (default: all)")
    ap.add_argument("--cases", nargs="*", default=[], help="challenge ids to run (default: all)")
    ap.add_argument("--max-usd", type=float, default=30.0)
    ap.add_argument("--timeout", type=float, default=30.0, help="seconds per model call")
    a = ap.parse_args()
    if a.list:
        for c in CHALLENGES:
            print(f"{c['id']:13s} seed {solvable_seed(c):4d}  {c['title']}: {c['tests']}")
        return
    cases = [c for c in CHALLENGES if not a.cases or c["id"] in a.cases]
    settings = [s for s in SETTINGS if not a.only or s[0] in a.only]
    out_dir = os.path.join(RUNS, f"challenges_{time.strftime('%Y%m%d-%H%M%S')}_{os.getpid()}")
    os.makedirs(out_dir, exist_ok=True)
    episodes, spent = [], [0.0]

    def play(ch, key, label, scfg):
        if a.max_usd and spent[0] >= a.max_usd:
            return None
        cfg = {**scfg, **case_cfg(ch), "request_timeout_s": a.timeout}
        t0 = time.time()
        s = Engine(cfg, realtime=False, runs_dir=out_dir).run_all()
        s["wall_s"] = round(time.time() - t0, 1)
        spent[0] += s["inference"]["cost"]
        ep = {"challenge": ch["id"], "title": ch["title"], "setting": key, "label": label, "cfg": cfg, "summary": s}
        i = s["inference"]
        print(f"{ch['title'][:26]:26s} {label[:46]:46s} solved {int(s['solved'])} parts {s['parts']}/3 "
              f"${i['cost']:.3f} fallbacks {i['by_source'].get('fallback', 0)}/{sum(i['by_source'].values())} "
              f"{s['wall_s']}s", flush=True)
        return ep

    # Two lanes: gpt-6-astra settings in one, everything else in the other, so the Jev API is never flooded by
    # more than one batch at a time.
    jobs = [(c, *s) for c in cases for s in settings]
    lanes = [[j for j in jobs if j[1] in GPT], [j for j in jobs if j[1] not in GPT]]
    with cf.ThreadPoolExecutor(2) as ex:
        for res in ex.map(lambda lane: [play(*j) for j in lane], lanes):
            episodes += [e for e in res if e]
    with open(os.path.join(out_dir, "episodes.json"), "w") as f:
        json.dump(episodes, f, default=str)
    print(f"\nwrote {out_dir}  total ${spent[0]:.2f}")
    print(markdown(episodes))


def markdown(episodes):
    keys = [s for s in SETTINGS if any(e["setting"] == s[0] for e in episodes)]
    cases = [c for c in CHALLENGES if any(e["challenge"] == c["id"] for e in episodes)]
    by = {(e["challenge"], e["setting"]): e["summary"] for e in episodes}
    head = "| Case | " + " | ".join(lbl for _, lbl, _ in keys) + " |"
    lines = [head, "|---|" + "---|" * len(keys)]
    for c in cases:
        cells = []
        for k, _, _ in keys:
            s = by.get((c["id"], k))
            cells.append("-" if s is None else ("**solved**" if s["solved"] else f"{s['parts']}/3"))
        lines.append(f"| {c['title']} | " + " | ".join(cells) + " |")
    tot = []
    for k, _, _ in keys:
        rs = [by[(c["id"], k)] for c in cases if (c["id"], k) in by]
        n, s = len(rs), sum(r["solved"] for r in rs)
        lo, hi = wilson(s, n)
        cost = sum(r["inference"]["cost"] for r in rs)
        tot.append(f"**{s}/{n}** ({lo:.2f}-{hi:.2f}) ${cost:.2f}")
    lines.append("| **Solved** | " + " | ".join(tot) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
