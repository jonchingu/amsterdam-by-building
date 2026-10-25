"""Checks for pipeline/quest_routes.py on made-up buildings. Runs with pytest, or on its own:

    uv run python tests/test_quest_routes.py
"""
import math
import sys
from pathlib import Path

import numpy as np
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import quest_routes as qr  # noqa: E402


def heights(blocks):
    """Heights from boxes in the local frame: [(bag, cx, cz, w, d, top)]."""
    return qr.Heights([shapely.box(cx - w / 2, cz - d / 2, cx + w / 2, cz + d / 2) for _, cx, cz, w, d, _ in blocks],
                      [b[5] for b in blocks], [b[0] for b in blocks])


def street(extra=()):
    """A row of 15 m houses along z = 0 with three quest buildings and anything extra."""
    blocks = [(f"h{i}", x, 30.0, 7, 12, 15.0) for i, x in enumerate(range(-600, 601, 9))]
    blocks += [("a", -500, -40, 20, 30, 30.0), ("b", 0, -40, 12, 12, 12.0), ("c", 500, -40, 40, 40, 60.0)]
    return heights(blocks + list(extra))


def test_curve_matches_three():
    # Values from three.js r186: new CatmullRomCurve3([...], false, 'centripetal').getPoint(t)
    P = [[0, 0, 0], [10, 5, 0], [20, 0, 10], [40, 10, 10]]
    got = qr.curve_points(P, [0, 1 / 3, 0.5, 2 / 3, 0.9, 1])
    assert np.allclose(got[[0, 1, 3, 5]], np.array(P), atol=1e-9)        # passes through every anchor
    js = {0.5: [14.7470666, 2.4815488, 4.8919846], 0.9: [33.7301850, 6.4422330, 10.4228595]}
    assert np.allclose(got[2], js[0.5], atol=1e-4) and np.allclose(got[4], js[0.9], atol=1e-4), got


def test_plan_is_clear_and_frames_each_building():
    H = street()
    route = qr.plan([["a"], ["b"], ["c"]], H)
    assert not qr.clips(route, H)
    stops = [a for a in route if "step" in a]
    assert [a["step"] for a in stops] == [0, 1, 2]
    for a, bag in zip(stops, "abc"):
        b = H.building([bag])
        assert math.hypot(a["target"][0] - b["x"], a["target"][2] - b["z"]) < 1
        yaw, pitch = qr.look(a["p"], a["target"])
        assert qr.angdiff(yaw, a["yaw"]) < 0.2 and a["pitch"] <= -8 and a["hold"] > 0
        assert 1 <= a["zoom"] <= 1.8
    assert route[0]["p"] == route[-1]["p"] and route[-1]["speed"] == 0
    assert all(a["speed"] > 0 for a in route[:-1])


def test_deterministic():
    assert qr.plan([["a"], ["b"], ["c"]], street()) == qr.plan([["a"], ["b"], ["c"]], street())


def tower_between(first, second, top, extra=()):
    """Heights with a 50 m tower of the given height right between the two framings planned without it."""
    free = qr.plan([[first], [second]], street(extra))
    pa, pb = (np.array(a["p"]) for a in free if "step" in a)
    mx, mz = (pa[[0, 2]] + pb[[0, 2]]) / 2
    return free, street(list(extra) + [("t", mx, mz, 50, 50, top)]), (mx, mz)


def assert_clear_of(route, H, at, top):
    assert not qr.clips(route, H)
    P = [r["p"] for r in route]
    for leg in range(len(P) - 1):
        q, _ = qr.leg_samples(P, leg)
        inside = (np.abs(q[:, 0] - at[0]) < 25 + qr.CLEAR) & (np.abs(q[:, 2] - at[1]) < 25 + qr.CLEAR)
        assert (q[inside, 1] >= top + qr.CLEAR).all()


def test_a_long_hop_cruises_over_a_tower():
    free, H, at = tower_between("a", "b", 300.0)
    route = qr.plan([["a"], ["b"]], H)
    assert_clear_of(route, H, at, 300.0)
    assert max(a["p"][1] for a in route[1:-1]) > max(a["p"][1] for a in free[1:-1])


def test_a_short_hop_is_bent_or_lifted_round_a_tower():
    near = [("d", 220, -40, 12, 12, 12.0)]
    free, H, at = tower_between("b", "d", 120.0, near)
    assert sum("step" not in a for a in free) == 2, "no transit points on a short hop"
    route = qr.plan([["b"], ["d"]], H)
    assert len(route) > len(free), "the planner should add a detour"
    assert_clear_of(route, H, at, 120.0)


def test_detour_inserts_an_anchor():
    H = street([("t", -250, -150, 40, 40, 150.0)])
    a = qr.anchor([-500, 100, -150], [-500, 15, -40])
    b = qr.anchor([0, 100, -150], [0, 6, -40])
    assert qr.clips([a, b], H), "the straight leg should hit the tower"
    leg, q, hit = qr.clips([a, b], H)[0]
    cands = qr.detour([a, b], leg, q, hit, H)
    assert any(not qr.clips([a, *cs, b], H) for cs in cands)


def test_unfixable_route_fails():
    _, H, _ = tower_between("b", "d", 120.0, [("d", 220, -40, 12, 12, 12.0)])
    try:
        qr.plan([["b"], ["d"]], H, max_fixes=0)
    except RuntimeError as e:
        assert "passes through a building" in str(e)
    else:
        raise AssertionError("expected the plan to fail")


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print("ok", name)
