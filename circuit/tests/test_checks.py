"""Offline checks (no model calls): python3 -m pytest tests  or  python3 tests/test_checks.py"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(os.path.dirname(HERE)), "common")]

from cpudebug import agents as A  # noqa: E402
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


def test_every_seed_has_a_failing_test_and_a_slice():
    for s in range(1, 13):
        c = Case({"seed": s, "window": 4})
        assert any(not r["ok"] for r in c.results)
        assert c.diff is not None and c.starts
        assert c.fit(c.fault["block"], []) == []  # no rows, no fit
        # the faulty block lies in the back-slice of the failure
        anc = set()
        for st in c.starts:
            anc |= {n[0] for n in c.ancestors(st)}
        assert c.fault["block"] in anc, (s, c.fault)


def test_fault_fit_and_grading():
    c = Case({"seed": 2, "window": 4})
    b = c.fault["block"]
    rows = []
    for k in ("sweep", "corner", "boundary", "random"):
        rows += c.drive(b, k)["rows"]
    fits = c.fit(b, rows)
    assert any(f["key"] == c.fault["key"] for f in fits)
    good = c.grade({"block": b, "port": c.fault["port"], "type": c.fault["type"], "key": c.fault["key"]})
    assert good["fix_ok"] and good["location_ok"] and good["type_ok"]
    bad = c.grade({"block": "alu_and", "port": "out", "type": "stuck_at", "key": "stuck:out:0"})
    assert not bad["fix_ok"] and not bad["block_ok"]


def test_catalogue_detection_rate():
    blocks, tests = build_cpu(), load_tests()
    faults = [f for f in all_faults(blocks) if f["type"] != "stuck_at"]
    caught = sum(1 for f in faults if any(not run_test(CPU(blocks, f), t)[0] for t in tests))
    assert caught >= len(faults) - 2


def test_exact_modes_run_offline_and_respect_budget():
    for mode in ("cone", "rule_swarm"):
        solved = 0
        for s in range(1, 5):
            e = Engine({"mode": mode, "seed": s, "probe_budget": 40}, realtime=False, log=False)
            e.run()
            sm = e.summary
            assert sm["probes"] <= 40 and not sm["errors"]
            assert sm["inference"]["calls"] == 0
            solved += sm["result"]["fix_ok"]
            json.dumps(e.frame(), default=str)
        assert solved >= 2, mode


class FakeJev:
    """Stands in for the Jev client: picks the first option, says 'broken' only when out != spec_out."""

    def ask(self, state, questions, retries=0):
        st = json.loads(state)
        ans = {}
        for k, q in questions.items():
            if q["type"] == "choice":
                ans[k] = {"choice": next(iter(q["criteria"]))}
            else:
                seen = st.get("seen") or [{"rows": s.get("rows", [])} for s in st.get("suspects", [])]
                bad = any(r["out"] != r["spec_out"] for p in seen for r in p["rows"])
                ans[k] = {"noul": 0.9 if bad else 0.1}
        return ans, {"usage": {"input_tokens": 10, "output_tokens": 2, "cost": 1e-6}, "model": "fake"}


def test_jev_swarm_with_a_fake_model():
    e = Engine({"mode": "jev", "seed": 1}, realtime=False, log=False)
    e.irr.client = FakeJev()
    e.holmes.client = FakeJev()
    e.run()
    sm = e.summary
    assert sm["probes"] <= e.cfg["probe_budget"]
    assert sm["inference"]["calls"] > 0 and sm["answer"] is not None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
