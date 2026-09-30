"""Correctness checks for the honeybee simulator. Offline, no API calls.

Run:  python3 tests/test_checks.py      (or: python3 -m pytest tests)
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import beeswarm  # noqa: E402,F401  (puts common/ on the path)
from beeswarm import observation as O  # noqa: E402
from beeswarm import policies as P  # noqa: E402
from beeswarm.config import coerce, quorum_count  # noqa: E402
from beeswarm.engine import Engine  # noqa: E402
from beeswarm.world import World  # noqa: E402


def world(**over):
    return World(coerce({"n_scouts": 20, **over}))


def inspect(w, s, label):
    """Send scout s to a site and fast-forward until it is back on the cluster."""
    w.apply(s, f"INSPECT_{label}") if label in s.known else w._start_trip(s, w.site(label), "inspect")
    while s.state != "idle":
        w.advance(1.0)


def test_observation_whitelist():
    w = world()
    s = w.scouts[0]
    inspect(w, s, w.sites[0].label)
    obs = O.observe(w, s)
    assert set(obs) == O.OBS_FIELDS
    text = O.state_json(obs)
    for banned in ('"quality"', "appears_min", "quorum_count", "at_site", '"x"', '"y"'):
        assert banned not in text, banned


def test_hidden_state_invariance():
    """Changing things a scout has no way to know leaves its observation and candidates byte-identical."""
    w = world()
    s = w.scouts[0]
    a, b = w.sites[0], w.sites[1]
    inspect(w, s, a.label)
    before = (O.state_json(O.observe(w, s)), json.dumps(O.candidates(w, s)))
    b.quality = 0.01            # a site it never visited
    a.quality = 0.99            # truth changed after its inspection: its estimate must not move
    w.scouts[5].energy = 0.0    # another scout's body
    after = (O.state_json(O.observe(w, s)), json.dumps(O.candidates(w, s)))
    assert before == after


def test_labels_carry_no_quality_information():
    best_labels = {max(world(seed=k).sites, key=lambda x: x.quality).label for k in range(12)}
    assert len(best_labels) >= 3, best_labels


def test_candidate_eligibility():
    w = world()
    s = w.scouts[0]
    c = O.candidates(w, s)
    assert set(c) == {"WAIT", "EXPLORE"}  # knows nothing, sees no dances
    best = max(w.sites, key=lambda x: x.quality)
    inspect(w, s, best.label)
    c = O.candidates(w, s)
    assert f"INSPECT_{best.label}" in c and f"ADVERTISE_{best.label}" in c
    s.energy = 0.0
    c = O.candidates(w, s)
    assert set(c) <= {"WAIT", f"ADVERTISE_{best.label}", "STOP_ADVERTISING"}


def test_poor_site_gets_no_dance():
    w = world(quality_noise=0.0)
    s = w.scouts[0]
    worst = min(w.sites, key=lambda x: x.quality)
    inspect(w, s, worst.label)
    assert f"ADVERTISE_{worst.label}" not in O.candidates(w, s)


def test_dance_attrition():
    w = world(quality_noise=0.0)
    s = w.scouts[0]
    best = max(w.sites, key=lambda x: x.quality)
    inspect(w, s, best.label)
    seq = []
    while f"ADVERTISE_{best.label}" in O.candidates(w, s):
        seq.append(w.circuits_for(s, best.label))
        w.apply(s, f"ADVERTISE_{best.label}")
        while s.state != "idle":
            w.advance(1.0)
    assert len(seq) >= 2 and all(x > y for x, y in zip(seq, seq[1:])), seq


def test_follow_needs_a_seen_live_dance():
    w = world(dance_bandwidth=50.0)
    dancer, watcher = w.scouts[0], w.scouts[1]
    best = max(w.sites, key=lambda x: x.quality)
    inspect(w, dancer, best.label)
    watcher.state = "idle"
    assert not any(k.startswith("FOLLOW_DANCE_") for k in O.candidates(w, watcher))
    w.apply(dancer, f"ADVERTISE_{best.label}")
    w.advance(1.0)
    assert f"FOLLOW_DANCE_{best.label}" in O.candidates(w, watcher)


def test_quorum_triggers_liftoff():
    w = world(liftoff_delay_min=10.0)
    site = w.sites[0]
    Q = quorum_count(w.cfg)
    for s in w.scouts[:Q]:
        w._start_trip(s, site, "inspect")
    while w.outcome is None and w.t < 200:
        w.advance(1.0)
    assert w.outcome and w.outcome["chosen"] == site.label
    assert w.outcome["t"] == w.quorum_t[site.label] + 10.0


def test_distribution_normalization():
    c = {"WAIT": "", "EXPLORE": ""}
    p = P.normalize({"WAIT": 3, "EXPLORE": 1, "BOGUS": 5}, c)
    assert abs(sum(p.values()) - 1) < 1e-9 and set(p) == set(c) and abs(p["WAIT"] - 0.75) < 1e-9
    try:
        P.normalize({"BOGUS": 1}, c)
        raise AssertionError("expected failure")
    except P.LLMError:
        pass


def test_stubborn_scouts_never_follow():
    e = Engine({"policy": "local_rule", "stubborn_frac": 1.0, "n_scouts": 20, "max_hours": 3, "seed": 2},
               realtime=False, log=False)
    e.run_all()
    for rec in e.last.values():
        assert not rec["applied"].startswith("FOLLOW_DANCE_")
        assert rec["source"] == "stubborn"


def test_same_seed_same_run():
    a = Engine({"policy": "local_rule", "seed": 3}, realtime=False, log=False).run_all()
    b = Engine({"policy": "local_rule", "seed": 3}, realtime=False, log=False).run_all()
    assert a["outcome"] == b["outcome"] and a["inference"]["decisions"] == b["inference"]["decisions"]


def test_replay_equivalence():
    """A sampled run with a live intervention replays exactly from its decision log."""
    tmp = tempfile.mkdtemp()
    try:
        e = Engine({"policy": "random", "seed": 4, "n_scouts": 30, "max_hours": 4}, realtime=False, runs_dir=tmp)
        for _ in range(40):
            e.tick()
        e._intervene({"op": "fake_dances", "site": e.world.sites[0].label, "n": 4})
        e.run_all()
        src = os.path.basename(e.run_dir)
        r = Engine({"policy": "replay", "replay_run": src}, realtime=False, runs_dir=tmp)
        r.run_all()
        assert r.summary["outcome"] == e.summary["outcome"]
        assert r.stats["by_source"].get("fallback", 0) == 0
        assert r.summary["inference"]["decisions"] == e.summary["inference"]["decisions"]
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as ex:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(ex).__name__, ex)
    sys.exit(1 if fails else 0)
