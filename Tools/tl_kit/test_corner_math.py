import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corner_math as cm
import kit_common


def regular(n, r=3000.0):
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def poly_with_corner(interior_deg, arm=4000.0):
    """A counter-clockwise quad whose vertex 0 has the given interior angle."""
    h = math.radians(interior_deg) / 2
    return [(0.0, 0.0), (arm * math.cos(h), -arm * math.sin(h)),
            (arm * 1.6, 0.0), (arm * math.cos(h), arm * math.sin(h))]


def rect(w, d):
    return [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]


def test_square_both_windings():
    sq = rect(6000, 3000)
    for pts in (sq, sq[::-1]):
        c = cm.classify(pts)
        assert all(v["convex"] and not v["acute"] for v in c)
        assert all(abs(abs(v["turn"]) - 90) < 1e-9 for v in c)
        f = cm.fan(pts, 0)
        assert len(f) == 9
        assert all(abs(s["sx"] - 1) < 1e-12 and abs(s["sy"] - 1) < 1e-12 for s in f)
        assert {s["kind"] for s in f} == {"front"}


def test_hexagon_slices_are_full_size():
    pts = regular(6)
    for i in range(6):
        f = cm.fan(pts, i)
        assert len(f) == 6
        assert all(abs(s["a"] - 5) < 1e-9 for s in f)


def test_slices_tile_the_turn_exactly():
    for interior in (15, 20, 30, 45, 60, 89, 91, 120, 150, 178):
        pts = poly_with_corner(interior)
        f = cm.fan(pts, 0)
        c = cm.classify(pts)[0]
        assert abs(sum(2 * s["a"] for s in f) - abs(c["turn"])) < 1e-9
        for s0, s1 in zip(f, f[1:]):          # neighbours abut edge to edge
            gap = abs(cm.wrap(s1["yaw"] - s0["yaw"])) - (s0["a"] + s1["a"])
            assert abs(gap) < 1e-9
        assert all(s["a"] <= cm.SLICE_HALF_DEG + 1e-12 for s in f)
        assert len(f) <= cm.MAX_FAN_SLICES


def test_slice_scale_matches_its_half_angle():
    pts = poly_with_corner(135)               # turn 45 -> 5 slices of 9 deg
    f = cm.fan(pts, 0)
    assert len(f) == 5
    a = math.radians(4.5)
    assert abs(f[0]["sx"] - math.cos(a) / math.cos(math.radians(5))) < 1e-12
    assert abs(f[0]["sy"] - math.sin(a) / math.sin(math.radians(5))) < 1e-12


def test_acute_threshold():
    assert cm.classify(poly_with_corner(89))[0]["acute"]
    assert not cm.classify(poly_with_corner(90.5))[0]["acute"]
    assert cm.classify(poly_with_corner(15))[0]["acute"]


def test_l_shape_has_one_concave_back_fan():
    L = [(0, 0), (6000, 0), (6000, 3000), (3000, 3000), (3000, 6000), (0, 6000)]
    for pts in (L, L[::-1]):
        c = cm.classify(pts)
        assert sum(not v["convex"] for v in c) == 1
        i = next(k for k, v in enumerate(c) if not v["convex"])
        assert {s["kind"] for s in cm.fan(pts, i)} == {"back"}
        assert not c[i]["acute"]


def test_collinear_vertices_are_dropped():
    pts = [(0, 0), (3000, 0), (6000, 30), (6000, 3000), (0, 3000)]   # 0.57 deg kink
    assert len(cm.clean(pts)) == 4
    pts = [(0, 0), (3000, 0), (6000, 80), (6000, 3000), (0, 3000)]   # 1.53 deg kink
    cleaned = cm.clean(pts)
    assert len(cleaned) == 5 and len(cm.fan(cleaned, 1)) == 1


def test_fan_directions_do_not_depend_on_winding():
    pts = regular(5)
    a = sorted(round(s["yaw"], 6) for i in range(5) for s in cm.fan(pts, i))
    r = pts[::-1]
    b = sorted(round(s["yaw"], 6) for i in range(5) for s in cm.fan(r, i))
    assert a == b


def test_fan_sweeps_from_incoming_to_outgoing_normal():
    sq = rect(6000, 3000)                      # CCW: exterior right of travel
    f = cm.fan(sq, 1)                          # the corner at (6000, 0)
    assert abs(f[0]["yaw"] - (-85.0)) < 1e-9   # from -90, the bottom edge's normal
    assert abs(f[-1]["yaw"] - (-5.0)) < 1e-9   # to 0, the right edge's normal


def test_storey_edge_grammar_bands():
    f0, f1, f2 = kit_common.level_grammars(1)
    for length, want in ((624.9, None), (625.0, "[EL][WS1][ER]"), (949.0, "[EL][WS1][ER]"),
                         (950.0, f0), (3725.0, f1), (5400.0, f2)):
        p = cm.edge_plan(rect(length, 4000), 0, 1)
        if want is None:
            assert p["short"] and p["symbol"] == "WS1"
            assert abs(p["scale"] - length / 325.0) < 1e-12
        else:
            assert not p["short"]
            assert p["grammar"] == want.replace("[FC", "[EL").replace("[LC", "[ER"), (length, p)


def test_foundation_edges_have_no_piers():
    p = cm.edge_plan(rect(6000, 4000), 0, 0)
    assert p["grammar"] == "[FS2]+"
    short = cm.edge_plan(rect(150, 4000), 0, 0)
    assert short["short"] and short["symbol"] == "FS2" and abs(short["scale"] - 0.75) < 1e-12


def test_acute_ends_use_the_acute_piers():
    pts = poly_with_corner(30)
    assert cm.edge_plan(pts, 0, 1)["grammar"].startswith("[EAL]")
    assert cm.edge_plan(pts, 3, 1)["grammar"].endswith("[EAR]")
    assert cm.edge_plan(pts, 1, 1)["grammar"].startswith("[EL]")


def test_cornice_level_uses_its_own_grammar():
    g = cm.edge_plan(rect(6000, 4000), 0, 4)["grammar"]
    assert "[E1]" not in g and g.startswith("[EL]") and g.endswith("[ER]")
