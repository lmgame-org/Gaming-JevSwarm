"""Required correctness checks from the design doc. Offline, no API calls.

Run:  python3 tests/test_checks.py      (or: python3 -m pytest tests)
"""
import copy
import json
import math
import os
import shutil
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jevswarm import candidates as C  # noqa: E402
from jevswarm import controller as ctl  # noqa: E402
from jevswarm import policies  # noqa: E402
from jevswarm.config import coerce  # noqa: E402
from jevswarm.engine import Engine  # noqa: E402
from jevswarm.sensors import Tracker, perceive  # noqa: E402
from jevswarm.world import World  # noqa: E402


def make_world(fish, preds=(), rocks=(), noise=False, size=(400.0, 400.0), **over):
    """fish: list of (x, y, heading_rad). Fish 0 is the focal fish."""
    cfg = coerce({"n_fish": len(fish), "world_w": size[0], "world_h": size[1], "n_rocks": 0, "n_food": 0, **over})
    if not noise:
        cfg.update(range_noise=0.0, bearing_noise_deg=0.0, dropout=0.0)
    w = World(cfg, np.random.default_rng(0))
    w.fish_pos = np.array([[x, y] for x, y, _ in fish], float)
    w.fish_h = np.array([h for _, _, h in fish], float)
    w.fish_v = np.full(len(fish), cfg["cruise"])
    w.fish_e = np.ones(len(fish))
    w.alive = np.ones(len(fish), bool)
    w.rocks = list(rocks)
    for (x, y, h) in preds:
        w.add_predator((x, y), h)
    w.grid.build(w.fish_pos, w.alive)
    return w, cfg


def obs_of(w, cfg, i=0, t=0.0, tracker=None):
    fr = perceive(w, i, t, np.random.default_rng(42), tracker or Tracker(), "ALIGN", cfg)
    return fr


def test_blind_sector_and_range():
    # 240 deg FOV: bearings beyond +-120 deg are blind
    w, cfg = make_world([(200, 200, 0.0), (205, 200, 0.0), (195, 200, 0.0), (200 + 11.9, 205, 0.0),
                         (200 + 12.2, 200, 0.0), (200 - 3 * math.cos(math.radians(50)), 200 + 3 * math.sin(math.radians(50)), 0.0)],
                        occlusion=False)
    fr = obs_of(w, cfg)
    seen = {k[1] for k in fr.fish_keys}
    assert 1 in seen, "fish ahead must be visible"
    assert 2 not in seen, "fish directly behind is in the blind sector"
    assert 4 not in seen, "fish beyond 12 BL must not be visible"
    # bearing 130 deg from forward -> blind (|b| > 120)
    assert 5 not in seen, "fish at 130 deg bearing is in the blind sector"
    d3 = math.hypot(11.9, 5)
    assert (3 in seen) == (d3 <= 12.0)


def test_occlusion_by_rock_and_body():
    # predator directly behind a rock
    w, cfg = make_world([(200, 200, 0.0)], preds=[(210, 200, math.pi)], rocks=[(205, 200, 2.0)])
    assert obs_of(w, cfg).obs["visible_predators"] == [], "predator behind a rock must be hidden"
    w.rocks = []
    assert len(obs_of(w, cfg).obs["visible_predators"]) == 1
    # nearest-neighbour hidden behind another body: tiny far fish exactly behind a near fish
    w, cfg = make_world([(200, 200, 0.0), (201, 200, 0.0), (203.0, 200, 0.0)], silhouette_samples=1)
    seen = {k[1] for k in obs_of(w, cfg).fish_keys}
    assert 1 in seen and 2 not in seen, "a fish directly behind another body is occluded (1 sample)"
    # own body never occludes
    w, cfg = make_world([(200, 200, 0.0), (206, 200, 0.0)])
    assert len(obs_of(w, cfg).fish_keys) == 1


def test_rotation_translation_invariance():
    base = [(200, 200, 0.3), (204, 201, 0.5), (198, 206, -1.0), (207, 195, 2.0)]
    pred = [(206, 204, -2.0)]
    w, cfg = make_world(base, preds=pred)
    a = obs_of(w, cfg).state_json()
    rot, tx, ty = 1.1, 37.0, -21.0

    def tf(x, y, h):
        dx, dy = x - 200, y - 200
        return (200 + tx + dx * math.cos(rot) - dy * math.sin(rot),
                200 + ty + dx * math.sin(rot) + dy * math.cos(rot), h + rot)
    w2, cfg2 = make_world([tf(*f) for f in base], preds=[tf(*p) for p in pred])
    b = obs_of(w2, cfg2).state_json()
    assert a == b, "observation must be invariant to rotation and translation of the scene"


def test_hidden_state_invariance():
    """Changing an unseen predator or fish leaves observation bytes, candidates and controller output identical."""
    scene = [(200, 200, 0.0), (204, 202, 0.1), (203, 197, -0.2), (190, 200, 0.0)]  # fish 3 is behind (blind)
    w, cfg = make_world(scene, preds=[(185, 201, 0.0)], noise=True)                  # predator behind (blind)
    tr1 = Tracker()
    f1 = obs_of(w, cfg, tracker=tr1)
    w2, _ = make_world(scene, preds=[(188, 190, 2.0)], noise=True)
    w2.fish_pos[3] = (192, 203)
    w2.fish_h[3] = 2.5
    w2.grid.build(w2.fish_pos, w2.alive)
    f2 = obs_of(w2, cfg, tracker=Tracker())
    assert f1.state_json() == f2.state_json(), "hidden changes leaked into the observation"
    assert C.criteria(C.build(f1.obs)) == C.criteria(C.build(f2.obs))
    for cid in C.build(f1.obs):
        spec = C.build(f1.obs)[cid]
        a1 = ctl.apply(cid, spec, f1, 0.0, 0.0, "t")
        a2 = ctl.apply(cid, spec, f2, 0.0, 0.0, "t")
        d1 = ctl.desired(a1, f1, w.fish_pos[0], 0.0, cfg, 0.0)
        d2 = ctl.desired(a2, f2, w2.fish_pos[0], 0.0, cfg, 0.0)
        assert d1 == d2, f"controller output differs for {cid}"


def test_request_fields_are_local_only():
    e = Engine({"policy": "local_rule", "seed": 3, "n_fish": 16}, realtime=False, log=False)
    for _ in range(60 * 22):
        e.tick()
    allowed_top = {"self", "vision", "visible_fish", "visible_predators", "visible_obstacles", "visible_food",
                   "visible_fish_summary"}
    allowed_item = {"slot", "range", "bearing_deg", "heading_relative_deg", "speed_estimate",
                    "turn_rate_estimate_deg_s", "kind", "radius"}
    for i, fr in e.frames.items():
        o = fr.obs
        assert set(o) <= allowed_top, set(o) - allowed_top
        for k in ("visible_fish", "visible_predators", "visible_obstacles", "visible_food"):
            for it in o[k]:
                assert set(it) <= allowed_item, set(it) - allowed_item
        txt = fr.state_json()
        for bad in ("pos", "\"x\"", "\"y\"", "id\"", "school", "polarization", "alive", "captur", "attack"):
            assert bad not in txt, f"forbidden field {bad} in request"


def test_motion_unknown_then_estimated():
    w, cfg = make_world([(200, 200, 0.0), (204, 200, 0.0)])
    tr = Tracker()
    f = obs_of(w, cfg, t=0.0, tracker=tr)
    assert f.obs["visible_fish"][0]["speed_estimate"] is None, "first sample: motion must be unknown"
    w.fish_pos[1] = (205, 200)
    f = obs_of(w, cfg, t=0.3, tracker=tr)
    assert abs(f.obs["visible_fish"][0]["speed_estimate"] - 1 / 0.3) < 0.05
    # after losing sight, the track is dropped (no memory of hidden objects)
    w.fish_pos[1] = (190, 200)
    w.grid.build(w.fish_pos, w.alive)
    obs_of(w, cfg, t=0.4, tracker=tr)
    assert ("f", 1) not in tr.tracks


def test_follow_stops_tracking_hidden_target():
    w, cfg = make_world([(200, 200, 0.0), (204, 201, 0.0)])
    f0 = obs_of(w, cfg)
    cands = C.build(f0.obs)
    a = ctl.apply("FOLLOW_n0", cands["FOLLOW_n0"], f0, 0.0, 0.0, "t")
    h_visible, _ = ctl.desired(a, f0, w.fish_pos[0], 0.0, cfg, 0.0)
    # target moves into the blind sector: follower must hold last heading, then CONTINUE, never track it
    w.fish_pos[1] = (190, 190)
    w.grid.build(w.fish_pos, w.alive)
    f1 = obs_of(w, cfg, t=0.1)
    h1, _ = ctl.desired(a, f1, w.fish_pos[0], 0.0, cfg, 0.1)
    assert abs(h1 - h_visible) < 1e-9, "must hold last heading, not steer toward the hidden target"
    ctl.desired(a, f1, w.fish_pos[0], 0.0, cfg, 0.7)
    assert a.kind == "CONTINUE"


def test_candidates_and_distribution():
    w, cfg = make_world([(200, 200, 0.0)] + [(203 + k, 200 + k, 0.0) for k in range(5)], preds=[(206, 195, 2.0)])
    o = obs_of(w, cfg).obs
    c = C.build(o)
    assert "CONTINUE" in c and "SCAN_L" in c and "SCAN_R" in c
    assert sum(k.startswith("FOLLOW_") for k in c) == 3, "FOLLOW limited to the 3 closest"
    assert {k for k in c if k.startswith("ESCAPE_")} == {"ESCAPE_L", "ESCAPE_S", "ESCAPE_R"}
    for v in c.values():
        assert set(v) <= {"kind", "desc", "slot", "turn", "offset", "dir"}, "no scores or recommendations"
    p = policies.normalize({"CONTINUE": 2, "ALIGN": 2, "BOGUS": 5}, c)
    assert abs(sum(p.values()) - 1) < 1e-9 and "BOGUS" not in p
    w0, cfg0 = make_world([(200, 200, 0.0)])
    c0 = C.build(obs_of(w0, cfg0).obs)
    assert not any(k.startswith(("ALIGN", "COHERE", "FOLLOW", "ESCAPE")) for k in c0), "needs visible evidence"


def test_per_fish_rng_independence():
    import random
    r = [random.Random(1 * 1_000_003 + 7919 * i + 17) for i in range(3)]
    probs = {"A": 0.3, "B": 0.3, "C": 0.4}
    seq_a = [policies.sample(probs, r[2]) for _ in range(20)]
    r = [random.Random(1 * 1_000_003 + 7919 * i + 17) for i in range(3)]
    for _ in range(50):
        policies.sample(probs, r[1])        # other fish sample a lot
    seq_b = [policies.sample(probs, r[2]) for _ in range(20)]
    assert seq_a == seq_b


def test_stale_result_rejected():
    e = Engine({"policy": "local_rule", "seed": 4, "n_fish": 8}, realtime=False, log=False)
    for _ in range(30):
        e.tick()
    i = 0
    fr = e.frames[i]
    cands = C.build(fr.obs)
    probs = policies.one_hot(cands, "SCAN_L")
    e.seq[i] = 5
    before = e.stats["stale"]
    e._handle_result((i, 5, 0, e.t - 0.9, fr, cands, probs, {"latency": 0.1}, None))
    assert e.stats["stale"] == before + 1
    e._handle_result((i, 4, 0, e.t, fr, cands, probs, {"latency": 0.1}, None))
    assert e.stats["superseded"] == 1
    assert e.actions[i].cid != "SCAN_L" or e.actions[i].source != "policy"


def test_replay_equivalence():
    tmp = tempfile.mkdtemp()
    try:
        cfg = {"policy": "random", "mode": "controlled", "seed": 7, "n_fish": 12, "episode_s": 30, "attack_s": 5}
        e1 = Engine(cfg, realtime=False, run_root=tmp)
        e1.command({"op": "false_alarm", "fish": 3})
        e1.run_headless()
        pos1 = e1.world.fish_pos.copy()
        alive1 = e1.world.alive.copy()
        e2 = Engine({"policy": "replay", "replay_run": os.path.basename(e1.run_dir), "speed": 1}, realtime=False,
                    run_root=tmp)
        e2.run_headless()
        assert (alive1 == e2.world.alive).all()
        assert np.allclose(pos1, e2.world.fish_pos), "replay diverged from the recorded run"
        assert e2.stats["policy_applied"] > 0 and e2.stats["requests"] == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_branch_prefix_matches_source():
    """Source finds a witness; permit and suppress branches both run from the same replayed prefix."""
    from jevswarm.causal import run_branch, run_source
    tmp = tempfile.mkdtemp()
    try:
        cfg = {"policy": "local_react", "seed": 2, "scenario": "flank", "mode": "controlled", "n_fish": 16,
               "attack_s": 5}
        found, table = run_source(dict(cfg), tmp)
        assert found, "expected a local escape"
        w, K, _ = found
        A = run_branch(dict(cfg), table, K, w, False, 1.0, tmp)
        B = run_branch(dict(cfg), table, K, w, True, 1.0, tmp)
        assert A["naive_fish"] == B["naive_fish"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as ex:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(ex).__name__}: {ex}")
    sys.exit(1 if fails else 0)
