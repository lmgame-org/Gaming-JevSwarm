"""Offline checks (no model calls): python3 -m pytest tests  or  python3 tests/test_checks.py"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(os.path.dirname(HERE)), "common")]

from cpudebug.case import Case  # noqa: E402
from cpudebug.engine import Engine  # noqa: E402
from cpudebug.isa import golden, assemble, load_tests  # noqa: E402
from cpudebug.netlist import CPU, all_faults, build_cpu, run_test  # noqa: E402


def test_netlist_size_and_clean_cpu_passes():
    blocks = build_cpu()
    assert 90 <= len(blocks) <= 110
    cpu = CPU(blocks)
    for t in load_tests():
        ok, tr = run_test(cpu, t)
        assert ok, t["name"]
        assert len(tr.retire()) == len(t["golden"]["retire"])


def test_golden_interpreter():
    g = golden(assemble("LDI r1, 9\nLDI r2, 0\nl: ADD r2, r2, r1\nADDI r1, r1, -1\nBNE r1, r0, l\nHALT"))
    assert g["halted"] and g["regs"][2] == 45


HARD = {"window": 2, "noise": 0.05, "rare_frac": 0.4, "double_frac": 0.2, "failure_info": "final",
        "test_pick": "longest"}


def test_every_seed_has_a_failing_test_and_a_slice():
    for s in range(1, 13):
        c = Case(dict(HARD, seed=s))
        assert any(not r["ok"] for r in c.results)
        assert c.starts and c.diff is not None
        assert c.fit(c.fault["block"], []) == []
        assert c.brief()["first_bad_cycle"] is None  # hardened: final state only


def test_fault_fit_and_grading():
    c = Case({"seed": 2, "window": 4})
    b = c.fault["block"]
    rows = []
    for k in ("sweep", "corner", "boundary", "random"):
        rows += c.drive(b, k)["rows"]
    fits = c.fit(b, rows)
    assert any(f["key"] == c.fault["key"] for f in fits)
    good = c.grade({"fixes": [{"block": f["block"], "port": f["port"], "type": f["type"], "key": f["key"]}
                              for f in c.faults]})
    assert good["fix_ok"] and good["location_ok"] and good["type_ok"]
    bad = c.grade({"fixes": [{"block": "alu_and", "port": "out", "type": "stuck_at", "key": "stuck:out:0"}]})
    assert not bad["fix_ok"] and not bad["block_ok"]


def test_double_bug_needs_both_fixes():
    for s in range(1, 30):
        c = Case(dict(HARD, seed=s))
        if len(c.faults) == 2:
            one = c.grade({"fixes": [dict(c.faults[0])]})
            both = c.grade({"fixes": [dict(f) for f in c.faults]})
            assert not one["fix_ok"] and both["fix_ok"]
            return
    raise AssertionError("no double-bug case in seeds 1-29")


def test_notebook_glitch_does_not_confirm():
    from cpudebug.kb import Notebook
    c = Case(dict(HARD, seed=4, noise=0.0))
    innocent = "alu_and"
    p = c.check(innocent, c.n - 2)
    r = dict(p["rows"][0])
    r["out"] = {"out": r["out"]["out"] ^ 1}
    r["ok"] = False
    nb = Notebook(c, owner=1, need_sources=2)
    nb.add_probe(dict(p, rows=[r]), 7, 1, first_hand=False)
    assert nb.block_view(innocent)["suspect"] and not nb.block_view(innocent)["confirmed"]


def test_families_run_offline_and_respect_budgets():
    for cfg in ({"mode": "solo", "solo_policy": "rule"}, {"mode": "solo", "solo_policy": "random"},
                {"mode": "leader", "holmes": "rule", "boy_policy": "rule"},
                {"mode": "leader", "holmes": "rule", "boy_policy": "rule", "wiggins": False},
                {"mode": "swarm", "swarm_policy": "rule", "n_agents": 40}):
        for s in (1, 2):
            e = Engine(dict(cfg, seed=s), realtime=False, log=False)
            e.run()
            sm = e.summary
            assert not sm["errors"], sm["errors"]
            assert sm["inference"]["calls"] == 0
            assert sm["ticks"] <= e.deadline + 1
            if cfg["mode"] == "solo":
                assert sm["probes"] <= e.cfg["probe_budget"]
            json.dumps(e.frame(), default=str)


def test_easy_setting_is_easy():
    solved = 0
    for s in range(1, 6):
        e = Engine({"preset": "easy", "mode": "leader", "holmes": "rule", "boy_policy": "rule", "seed": s},
                   realtime=False, log=False)
        e.run()
        solved += e.summary["result"]["block_ok"]
    assert solved >= 4


def test_catalogue_detection_rate():
    blocks, tests = build_cpu(), load_tests()
    faults = [f for f in all_faults(blocks) if f["type"] != "stuck_at"]
    caught = sum(1 for f in faults if any(not run_test(CPU(blocks, f), t)[0] for t in tests))
    assert caught >= len(faults) - 2


class FakeJev:
    """Stands in for the Jev client: always picks the first option."""

    def ask(self, state, questions, retries=0):
        ans = {}
        for k, q in questions.items():
            ans[k] = {"choice": next(iter(q["criteria"]))} if q["type"] == "choice" else {"noul": 0.5}
        return ans, {"usage": {"input_tokens": 10, "output_tokens": 2, "cost": 1e-6}, "model": "fake"}


def test_jev_paths_with_a_fake_model():
    for cfg in ({"mode": "solo", "solo_policy": "jev"}, {"mode": "leader", "holmes": "rule", "boy_policy": "jev"},
                {"mode": "swarm", "swarm_policy": "jev", "n_agents": 30},
                {"mode": "swarm", "swarm_policy": "hybrid", "n_agents": 30}):
        e = Engine(dict(cfg, seed=3, deadline_hours=2), realtime=False, log=False)
        g = e.game
        for attr in ("jev",):
            if hasattr(g, attr):
                setattr(g, attr, FakeJev())
        e.run()
        sm = e.summary
        assert not sm["errors"], sm["errors"]
        assert sm["inference"]["calls"] > 0


def test_v3_chip_case_and_grading():
    from cpudebug.chip import ChipCase
    from cpudebug.config import coerce
    for s in (1, 2, 3, 6):
        c = ChipCase(coerce({"seed": s, "tier": "v3"}))
        assert len(c.blocks) > 1000 and any(not r["ok"] for r in c.results)
        bad = [k for k in range(c.n_cores) if c.trace.core_sigs[k] != c.trace.golden.core_sigs[k]]
        assert {f["core"] for f in c.faults if f.get("core") is not None} <= set(bad)
        right = c.grade({"fixes": [dict(f) for f in c.faults]})
        assert right["fix_ok"] and right["innocent_fixes"] == 0
        extra = c.grade({"fixes": [dict(f) for f in c.faults] + [{"block": "c0.alu_and", "key": "stuck:out:0"}]})
        assert not extra["fix_ok"] and extra["innocent_fixes"] == 1   # an innocent fix is penalised


def test_v3_wire_fault_is_invisible_to_block_checks():
    from cpudebug.chip import ChipCase
    from cpudebug.config import coerce
    for s in range(1, 40):
        c = ChipCase(coerce({"seed": s, "tier": "v3", "noise": 0.0, "double_frac": 0.0}))
        f = c.faults[0]
        if not f.get("wire"):
            continue
        lk = c.by[f["block"]]
        cyc = c.slice_cycles().get(f["block"])
        if not cyc:
            continue
        caught = any(c.check(f["block"], x)["mismatch"] for x in cyc)
        ends = [lk.src[0], lk.dst[0]]
        blk = [b for b in ends if not c.by[b].trusted]
        assert caught
        assert not any(c.check(b, x)["mismatch"] for b in blk for x in cyc[:4])
        return
    raise AssertionError("no wire bug in seeds 1-39")


def test_v3_families_run_offline():
    for cfg in ({"mode": "solo", "solo_policy": "rule"}, {"mode": "leader", "holmes": "rule", "boy_policy": "rule"},
                {"mode": "swarm", "swarm_policy": "rule"}):
        e = Engine(dict(cfg, seed=4, tier="v3"), realtime=False, log=False)
        e.run()
        assert not e.summary["errors"], e.summary["errors"]
        json.dumps(e.frame(), default=str)
        json.dumps(e.static(), default=str)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
