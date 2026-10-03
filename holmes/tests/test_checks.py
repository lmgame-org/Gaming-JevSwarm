"""Correctness checks for The Irregulars. Offline, no API calls.

Run:  python3 tests/test_checks.py      (or: python3 -m pytest tests)
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import irregulars  # noqa: E402,F401  (puts common/ on the path)
from irregulars.case import Case  # noqa: E402
from irregulars.config import coerce  # noqa: E402
from irregulars.engine import Engine  # noqa: E402
from irregulars.solo import SoloGame  # noqa: E402
from irregulars.swarm import SwarmGame  # noqa: E402


def test_case_is_reproducible():
    a, b = Case(coerce({"seed": 7})), Case(coerce({"seed": 7}))
    assert a.truth == b.truth and a.leads == b.leads and a.edges == b.edges
    assert Case(coerce({"seed": 8})).leads != a.leads


def test_every_address_has_one_lead_and_map_is_connected():
    for n in (20, 40, 100, 200):
        c = Case(coerce({"seed": 3, "n_addresses": n}))
        assert set(c.leads) == set(c.by_id)
        assert len(c.path_len(c.addresses[0]["id"])) == len(c.addresses)


def test_default_cases_are_solvable_by_counting():
    for seed in range(1, 31):
        assert all(Case(coerce({"seed": seed})).solvable.values()), seed


def test_lies_are_single_and_contradict_key_facts():
    c = Case(coerce({"seed": 4, "lie_rate": 0.3}))
    lies = [l for l in c.leads.values() if l["lie"]]
    assert lies
    truth_facts = {tuple(f) for f in c.key_facts}
    for l in lies:
        assert tuple(l["fact"]) not in truth_facts


def test_solo_observation_hides_truth_and_facts():
    c = Case(coerce({"seed": 2}))
    g = SoloGame(c, coerce({"seed": 2}))
    g.visit(sorted(g.reachable())[0])
    text = json.dumps(g.observation())
    for banned in ('"fact"', '"lie"', '"truth"', "hide_found", "hide_not", '"culprit"'):
        assert banned not in text, banned
    assert c.suspect(c.truth["culprit"])["name"] in text  # it is listed, but only as one suspect among many


def test_swarm_observation_is_local():
    cfg = coerce({"seed": 2, "mode": "swarm"})
    g = SwarmGame(Case(cfg), cfg)
    a = g.irr[0]
    text = json.dumps(g.observation(a))
    for banned in ('"fact"', '"fake"', '"truth"', "liar", "frame_up"):
        assert banned not in text, banned
    assert len(g.observation(a)["my_leads"]) <= cfg["memory_cap"]


def test_rule_beats_random_solo():
    rule = sum(Engine({"seed": s, "policy": "rule"}, realtime=False, log=False).run_all()["parts"] for s in range(1, 11))
    rnd = sum(Engine({"seed": s, "policy": "random"}, realtime=False, log=False).run_all()["parts"] for s in range(1, 11))
    assert rule > rnd + 8, (rule, rnd)


def test_solo_respects_budget_and_deadline():
    for s in range(1, 6):
        e = Engine({"seed": s, "policy": "random", "visit_budget": 7, "deadline_hours": 3}, realtime=False, log=False)
        sm = e.run_all()
        assert sm["visits"] <= 7 and sm["minutes"] <= 180 + 1e-6


def test_swarm_quorum_closes_case():
    e = Engine({"seed": 2, "mode": "swarm", "swarm_policy": "rule"}, realtime=False, log=False)
    g = e.game
    t = e.case.truth_ids()
    for a in g.irr[:g.quorum_need()]:
        a.vote = dict(t)
    g.end_tick()
    assert g.ended and g.outcome["quorum"] and g.outcome["solved"]


def test_liars_push_one_wrong_answer():
    e = Engine({"seed": 3, "mode": "swarm", "swarm_policy": "rule", "liar_frac": 0.2}, realtime=False, log=False)
    g = e.game
    liars = [a for a in g.irr if a.liar]
    assert len(liars) == 20 and all(a.vote == g.frame_up for a in liars)
    assert g.frame_up["culprit"] != e.case.truth["culprit"]


def test_stubborn_vote_locks():
    e = Engine({"seed": 1, "mode": "swarm", "swarm_policy": "rule", "stubborn_frac": 1.0}, realtime=False, log=False)
    g = e.game
    a = g.irr[0]
    g.apply(a, "WAIT", {"culprit": "S1", "motive": "M1", "hideout": "H1"})
    g.apply(a, "WAIT", {"culprit": "S2", "motive": "M2", "hideout": "H2"})
    assert a.vote["culprit"] == "S1" and a.locked


def test_run_logs_and_no_keys_written():
    d = tempfile.mkdtemp()
    try:
        e = Engine({"seed": 1, "policy": "rule"}, realtime=False, runs_dir=d)
        e.run_all()
        files = os.listdir(e.run_dir)
        assert {"config.json", "case.json", "decisions.jsonl", "events.jsonl", "summary.json"} <= set(files)
        cfg = json.load(open(os.path.join(e.run_dir, "config.json")))["cfg"]
        assert not any(k.endswith("_key") for k in cfg)
        for name in files:
            assert "sk-" not in open(os.path.join(e.run_dir, name)).read()
    finally:
        shutil.rmtree(d)


def test_swarm_rule_solves_some_honest_cases():
    solved = sum(Engine({"seed": s, "mode": "swarm", "swarm_policy": "rule"}, realtime=False, log=False)
                 .run_all()["solved"] for s in range(1, 11))
    assert solved >= 4, solved


def test_defence_rejects_far_first_hand_claims_and_contradictions():
    e = Engine({"seed": 1, "mode": "swarm", "swarm_policy": "rule"}, realtime=False, log=False)
    g = e.game
    a, b = g.irr[0], g.irr[1]
    far = max(g.case.by_id, key=lambda x: g.case.hops(a.at)[x])
    a.at = b.at  # make sure b can hear a
    g._shout(a, {"address": far, "text": "made up", "fact": ["motive", "debt"], "via": a.i, "fake": True})
    rec = b.inbox[-1]
    assert rec.get("implausible") and not b.remember(rec, 16, True) and a.i in b.distrust
    c = g.irr[2]
    own = next(iter(c.own))
    assert not c.remember({"address": own, "text": "something else", "fact": ["motive", "debt"], "via": 7}, 16, True)
    assert 7 in c.distrust and c.refute


def test_defence_off_keeps_old_behaviour():
    e = Engine({"seed": 1, "mode": "swarm", "swarm_policy": "rule", "corroboration": "none"}, realtime=False, log=False)
    c = e.game.irr[2]
    own = next(iter(c.own))
    assert c.remember({"address": own, "text": "something else", "fact": ["motive", "debt"], "via": 7}, 16, False)


class _WaitPolicy:
    """Stand-in for Jev in offline tests: always waits."""
    name, remote = "jev", True

    def decide(self, game, a, cands):
        return "WAIT", {"culprit": "S1", "motive": "M1", "hideout": "H1"}, {"cost": 0.0}


def test_hybrid_votes_come_from_counting():
    e = Engine({"seed": 2, "mode": "swarm", "swarm_policy": "hybrid"}, realtime=False, log=False)
    e.policy = _WaitPolicy()
    e.step()
    g = e.game
    for a in g.irr[:20]:
        expect = g.reflex(a, g.candidates(a))[1]
        assert a.vote == expect or a.liar, (a.vote, expect)


def test_yard_hub_collects_and_closes():
    e = Engine({"seed": 2, "mode": "swarm", "swarm_policy": "hybrid_genius", "comm_range": 200}, realtime=False,
               log=False)
    e.policy = _WaitPolicy()
    g = e.game
    yard = g.case.specials["yard"]
    a = g.irr[0]
    a.at = yard
    g._shout(a, {"address": a.at, "text": "test lead", "fact": ["bland"], "via": a.i, "fake": False})
    assert any(r["text"] == "test lead" for r in g.hub)
    t = g.case.truth_ids()
    g.hub_answer = {**t, "confident": True}
    g.end_tick()
    assert g.ended and g.outcome["solved"] and g.outcome["closed_by"] == "hub"


def _baker(**over):
    return Engine({"preset": "baker_street_counting", "boy_policy": "rule", "seed": 2, **over}, realtime=False,
                  log=False)


def test_baker_street_reports_travel_back_before_holmes_sees_them():
    e = _baker(wiggins=False)
    g = e.game
    e.step()  # Holmes plans, boys scatter
    assert not g.notebook and all(b.state == "out" for b in g.boys if b.assignment)
    seen = 0
    while not g.notebook and not e.ended:
        e.step()
        seen += 1
    first = g.notebook[0]
    assert first["reached_holmes_tick"] > first["seen_tick"] or first["address"] == g.baker


def test_baker_street_conflicting_reports_are_contested():
    e = _baker()
    g = e.game
    addr = sorted(g.case.by_id)[5]
    g.notebook = [{"address": addr, "text": "one story", "fact": ["motive", "debt"], "boy": 1, "seen_tick": 0},
                  {"address": addr, "text": "another story", "fact": ["motive", "revenge"], "boy": 2, "seen_tick": 0}]
    facts, contested, distrust = g.holmes_facts()
    assert addr in contested and not facts
    g.notebook.append({"address": addr, "text": "one story", "fact": ["motive", "debt"], "boy": 3, "seen_tick": 1})
    facts, contested, distrust = g.holmes_facts()
    assert 2 in distrust and len(facts) == 1


def test_baker_street_bribed_boys_report_fakes():
    e = _baker(liar_frac=0.5)
    g = e.game
    liar = next(b for b in g.boys if b.liar)
    liar.at = g.baker
    rec = g._report(liar, sorted(g.case.by_id)[3])
    assert rec["fake"]


def test_baker_street_random_boys_run_offline():
    e = _baker(boy_policy="random", seed=4)
    s = e.run_all()
    assert s["outcome"] is not None and set(s["inference"]["by_source"]) <= {"random", "liar"}


def test_baker_street_rule_holmes_solves_most():
    solved = sum(_baker(seed=s).run_all()["solved"] for s in range(1, 11))
    assert solved >= 7, solved


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)
