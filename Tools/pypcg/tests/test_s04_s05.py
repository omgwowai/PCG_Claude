"""Stages 4 and 5, the landmark footprints (Task 13). Both publish a shape from the volume's own
transform and take no scene reads, so every test is about one value: the closed spline, its vertex
order, its winding and its size.

The two fixtures are the demo level's own output, read 2026-10-17 by `pyg_probe_t13_read.py`: the
hero volume sits at the origin with yaw 0 and its hexagon's vertices are (4000, -6928.2032) ..; the
park volume sits at (60150, 57100, 9950) with yaw 34.222659 deg and its rectangle's corners are
(13182.9849, 37248.0607) ..."""
import json
import math
import os

import pytest

from fakes import FakeOps
from pypcg import geo, graphs, stage_api
from pypcg.geo import Points, Spline
from pypcg.profiles import official
from pypcg.stages import s04_main_tower_footprint as S4
from pypcg.stages import s05_central_park_footprint as S5

REPO = stage_api.REPO
HEX_OFFICIAL = [(4000.0, -6928.2032), (-4000.0, -6928.2032), (-8000.0, 0.0),
                (-4000.0, 6928.2032), (4000.0, 6928.2032), (8000.0, 0.0)]
PARK_OFFICIAL = [(13182.9849, 37248.0607), (95868.8065, 93489.1036),
                 (107117.0151, 76951.9393), (24431.1935, 20710.8964)]
PARK_AT = (60150.0, 57100.0, 9950.0)
PARK_YAW = 34.222659453871444


def volume(loc=(0.0, 0.0, 0.0), yaw=0.0, n=1):
    p = Points()
    for _ in range(n):
        p.add(loc, rot=(0.0, yaw, 0.0))
    return {"Volume": [(p, frozenset())]}


def pts_of(out, pin="Footprint"):
    return out[pin][0][0]


def xy(spline):
    return [(p[0], p[1]) for p in spline.points]


def signed(spline):
    return geo.signed_area(xy(spline))


def params(module, **kw):
    p = stage_api.defaults(module)
    p.pop(stage_api.SEED)
    p.update(kw)
    return p


# ---- contract -------------------------------------------------------------------------------------
@pytest.mark.parametrize("n,module", [(4, S4), (5, S5)])
def test_contract_matches_the_official_graph(n, module):
    name = "PCG_2_%d_%s" % (n - 3, "MainTower_Footprint" if n == 4 else "CentralPark_Footprint")
    off = json.load(open(os.path.join(REPO, "Tools", "pypcg", "official_ir", name + ".json"),
                         encoding="utf-8"))
    defaults = {p["name"]: p["value"] for p in off["params"]}
    # Both stage parameters are Float in the official graph (stage 4's own pair; stage 5's node
    # override is an integer literal, so its exposed copy is declared Float for the same reason).
    assert set(module.PARAMS) == {"RectWidth", "RectLength"}
    assert all(p.type == "Float" for p in module.PARAMS.values())
    if n == 4:
        # Stage 4's parameters are the official ones, values and all; `NewProperty` is dropped
        # because no getter reads it (the brief's row).
        assert all(float(module.PARAMS[k].default) == float(defaults[k]) for k in module.PARAMS)
        assert "NewProperty" not in module.PARAMS and "NewProperty" in defaults
    else:
        # Stage 5's official graph declares NO parameter: its size is fixed inside the node
        # (`Width` 100000, `Length` 20000 in the overrides). The stage's defaults are those numbers,
        # not the brief's row (which reads 16000/16000 and is the stage-4 row copied across): see
        # `docs/pypcg/stages/s05.md` section 3.
        assert defaults == {}
        assert module.PARAMS["RectWidth"].default == 100000.0
        assert module.PARAMS["RectLength"].default == 20000.0
        ov = [x for x in off["nodes"] if x["name"] == "Park_Footprint"][0]["overrides"]
        assert (module.PARAMS["RectWidth"].default, module.PARAMS["RectLength"].default) == \
            (float(ov["Width"]), float(ov["Length"]))
    assert module.INPUTS == {"Volume": "points"} and module.OUTPUTS == ("Footprint",)


@pytest.mark.parametrize("module", [S4, S5])
def test_graph_wires_the_volume_point_and_the_footprint(module):
    ir = graphs.graph(module.STAGE).to_ir(official)
    py = [x for x in ir["nodes"] if x["class"] == "PCGPythonDataProcessorSettings"][0]
    srcs = {p["label"]: [e[0] for e in p["edges"]] for p in py["inputs"]}
    self_nodes = [x for x in ir["nodes"] if x["class"] == "PCGDataFromActorSettings"]
    assert len(self_nodes) == 1 and self_nodes[0]["settings"] == {"Mode": "GetSinglePoint"}
    assert srcs["Volume"] == [self_nodes[0]["name"]]
    assert len(srcs["Params"]) == 3                          # Seed + RectWidth + RectLength
    assert ir["params"][0]["name"] == stage_api.SEED
    used = {(s, pin) for x in ir["nodes"] for p in x.get("inputs", []) for s, pin in p["edges"]}
    assert (py["name"], "Footprint") in used                  # the output node reads it


# ---- empty inputs (Review Focus 1) ----------------------------------------------------------------
@pytest.mark.parametrize("module", [S4, S5])
def test_empty_inputs_give_empty_outputs(module):
    out, _ = stage_api.execute(module, {"Volume": []}, stage_api.defaults(module), FakeOps())
    assert out["Footprint"] == []
    out, _ = stage_api.execute(module, volume(n=0), stage_api.defaults(module), FakeOps())
    assert out["Footprint"] == []


# ---- the measured fixtures --------------------------------------------------------------------------
def test_hexagon_matches_the_demo_to_a_tenth_of_a_centimetre():
    spl = pts_of(S4.run(volume(), params(S4), None))
    assert len(spl.points) == 6 and spl.closed and spl.linear
    assert all(math.dist(p[:2], q) < 0.1 for p, q in zip(xy(spl), HEX_OFFICIAL))


# The official vertices at full precision (pyg_probe_t13_delta.py, 2026-10-17). Round 2 measured that
# stage 15 reads their LAST BITS: the same hexagon 2.9e-12 cm off gave 35 008 instances, these exact
# doubles give the official 35 239.
HEX_OFFICIAL_BITS = [(3999.999999999998, -6928.20323027551), (-4000.000000000001, -6928.203230275509),
                     (-8000.0, 0.0), (-4000.000000000001, 6928.203230275509),
                     (3999.999999999998, 6928.20323027551), (8000.0, 9.797174393178826e-13)]


def test_hexagon_matches_the_demo_bit_for_bit():
    spl = pts_of(S4.run(volume(), params(S4), None))
    assert xy(spl) == HEX_OFFICIAL_BITS
    assert all(p[2] == 0.0 for p in spl.points)


def test_hexagon_vertices_carry_the_official_point_rotations():
    """The official spline points carry yaw 30, -30, -90, -150, 150, 90 (pitch and roll 0): the
    sphere's tangential orientation. A turned volume adds its yaw."""
    spl = pts_of(S4.run(volume(), params(S4), None))
    assert [r[1] for r in spl.rotations] == pytest.approx([30.0, -30.0, -90.0, -150.0, 150.0, 90.0])
    assert all(r[0] == 0.0 and r[2] == 0.0 for r in spl.rotations)
    turned = pts_of(S4.run(volume(yaw=40.0), params(S4), None))
    assert [r[1] for r in turned.rotations] == pytest.approx([70.0, 10.0, -50.0, -110.0, -170.0, 130.0])


def test_spline_rotations_round_trip_and_stay_out_of_old_records():
    """`rotations` is written to a run record only when set, so records made before the field (stages
    6-8) still replay equal."""
    spl = pts_of(S4.run(volume(), params(S4), None))
    back = geo.from_json(geo.to_json(spl))
    assert back.rotations == spl.rotations and back.points == spl.points
    assert "rotations" not in geo.to_json(Spline([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)]))


def test_park_matches_the_demo_to_half_a_centimetre():
    spl = pts_of(S5.run(volume(PARK_AT[:2], PARK_YAW), params(S5), None))
    assert len(spl.points) == 4 and spl.closed and spl.linear
    assert all(math.dist(p[:2], q) < 0.5 for p, q in zip(xy(spl), PARK_OFFICIAL))


def test_hexagon_area_is_the_analytic_one():
    spl = pts_of(S4.run(volume(), params(S4), None))
    want = -3.0 * math.sqrt(3.0) / 2.0 * 8000.0 ** 2
    assert signed(spl) == pytest.approx(want, rel=1e-9)
    assert abs(signed(spl)) / 1e4 == pytest.approx(16627.687752661222, rel=1e-9)


def test_park_area_is_the_analytic_one():
    spl = pts_of(S5.run(volume(PARK_AT[:2], PARK_YAW), params(S5), None))
    assert signed(spl) == pytest.approx(-100000.0 * 20000.0, rel=1e-9)
    assert abs(signed(spl)) / 1e4 == pytest.approx(200000.0, rel=1e-9)


@pytest.mark.parametrize("module", [S4, S5])
def test_signed_area_is_negative_in_the_official_order(module):
    """traps.md 41: the official order is Clockwise in UE's sense, which is a NEGATIVE standard
    shoelace area. Later stages read these vertices; the sign is part of the contract."""
    spl = pts_of(module.run(volume(), params(module), None))
    assert signed(spl) < 0.0
    assert geo.signed_area(list(reversed(xy(spl)))) > 0.0        # the test can tell the orders apart


# ---- the volume's transform -----------------------------------------------------------------------
def test_a_moved_volume_moves_the_shape():
    for module, move in ((S4, (12345.0, -6789.0)), (S5, (1000.0, 2000.0))):
        base = pts_of(module.run(volume(), params(module), None))
        moved = pts_of(module.run(volume((move[0], move[1], 0.0)), params(module), None))
        assert all(abs(a[0] + move[0] - b[0]) < 1e-9 and abs(a[1] + move[1] - b[1]) < 1e-9
                   for a, b in zip(xy(base), xy(moved)))


def test_a_rotated_volume_rotates_the_shape():
    for module in (S4, S5):
        base = pts_of(module.run(volume(), params(module), None))
        turned = pts_of(module.run(volume(yaw=90.0), params(module), None))
        assert all(math.dist((-a[1], a[0]), b) < 1e-6 for a, b in zip(xy(base), xy(turned)))
        assert signed(turned) == pytest.approx(signed(base), rel=1e-12)


def test_the_volume_yaw_is_rot_index_one():
    """`convert._points_of` stores a rotator as (pitch, yaw, roll); the stage reads index 1. A pitch
    of 30 deg must change nothing."""
    p = Points()
    p.add((0.0, 0.0, 0.0), rot=(30.0, 0.0, 0.0))
    pitched = pts_of(S5.run({"Volume": [(p, frozenset())]}, params(S5), None))
    base = pts_of(S5.run(volume(), params(S5), None))
    assert xy(pitched) == xy(base)


def test_z_comes_from_the_volume_in_stage_4_and_is_zero_in_stage_5():
    """The hero volume sits at Z 0 in the demo and the stage keeps the volume's Z; the park volume
    sits at Z 9950 and the official graph pins `$Position.Z` to 0 after the shape is built."""
    a = pts_of(S4.run(volume((0.0, 0.0, 5550.0)), params(S4), None))
    assert all(p[2] == 5550.0 for p in a.points)
    b = pts_of(S5.run(volume((0.0, 0.0, 9950.0)), params(S5), None))
    assert all(p[2] == 0.0 for p in b.points)


def test_a_length_over_width_ratio_stretches_the_hexagon_along_its_own_y():
    """`MakeVectorAttribute_1`'s scale is (1, Length / Width, 1), so Length changes only the local Y
    extent: RectLength 32000 doubles every Y and leaves every X."""
    a = pts_of(S4.run(volume(), params(S4), None))
    b = pts_of(S4.run(volume(), params(S4, RectLength=32000.0), None))
    assert all(abs(p[0] - q[0]) < 1e-9 and abs(2.0 * p[1] - q[1]) < 1e-9
               for p, q in zip(xy(a), xy(b)))


def test_rect_corner_order_is_the_official_one():
    """The corner sequence is (-1, 1), (1, 1), (1, -1), (-1, -1) about the local axes: the demo's
    four corners, element for element. Any other order fails by a side length."""
    corners = S5.rectangle((0.0, 0.0), 100000.0, 20000.0, 0.0)
    assert corners == [(-50000.0, 10000.0), (50000.0, 10000.0), (50000.0, -10000.0),
                       (-50000.0, -10000.0)]


def test_the_two_vertex_radii_follow_the_width_and_length_ratio():
    """`S4.radii` is derived, not read back from the builder. At ratio 2 the local Y stretch puts the
    four off-axis vertices at R sqrt(1/4 + 3/4 x 4) = R sqrt(13)/2, not at R x ratio."""
    R = 8000.0
    assert S4.radii(16000.0, 16000.0) == [R] * 6
    far = R * (0.25 + 0.75 * 4.0) ** 0.5
    assert S4.radii(16000.0, 32000.0) == [far, far, R, far, far, R]
    assert far == pytest.approx(8000.0 * (13 ** 0.5) / 2.0, rel=1e-12)       # 14422.205 cm
    assert far != pytest.approx(R * 2.0)                                     # the old claim
    # and the builder agrees with the derivation, vertex for vertex
    ring = S4.hexagon((0.0, 0.0), 16000.0, 32000.0, 0.0)
    assert all(abs(math.dist((x, y), (0.0, 0.0)) - want) < 1e-9
               for (x, y), want in zip(ring, S4.radii(16000.0, 32000.0)))


def test_v1_size_clause_fires_at_a_non_unit_ratio():
    """The review's Important 1: the old clause compared min/max radii to Width/2 and
    Width/2 x Length/Width, so it read 14422.21 cm against 16000 and failed on a CORRECT port."""
    from pypcg.checks import s04 as C4
    p = params(S4, RectLength=32000.0)
    vin = volume()
    assert C4.check(vin, p, S4.run(vin, p, None), FakeOps()) == []
    # a footprint built for the unit ratio while the parameters say 2:1 must fail
    wrong = S4.run(vin, params(S4), None)
    assert any("put it at" in x for x in C4.check(vin, p, wrong, FakeOps()))


def test_v1_yaw_clause_fires_on_a_wrong_rotation():
    """The review's Important 3: side lengths and area are rotation-invariant, so only the corner
    measure can see a wrong yaw. A 5-degree error moves a corner ~4400 cm off its local corner."""
    from pypcg.checks import s05 as C5
    built = S5.run(volume(PARK_AT[:2], PARK_YAW), params(S5), None)       # the right yaw
    assert C5.check(volume(PARK_AT[:2], PARK_YAW), params(S5), built, FakeOps()) == []
    f = C5.check(volume(PARK_AT[:2], PARK_YAW + 5.0), params(S5), built, FakeOps())
    assert any("turned back by the volume's yaw" in x for x in f)
    # the modulo-90 property itself, on a square. (Through check() a wrong yaw also trips the
    # "where the volume puts it" clause first, so the bounds are tested on the measure directly.)
    square = S5.rectangle((0.0, 0.0), 10000.0, 10000.0, 30.0)
    assert C5._corners_at_yaw(square, 30.0, 10000.0, 10000.0) == []
    assert C5._corners_at_yaw(square, 120.0, 10000.0, 10000.0) == []          # +90: same shape
    assert C5._corners_at_yaw(square, 75.0, 10000.0, 10000.0) != []           # +45: not
    rect = S5.rectangle((0.0, 0.0), 100000.0, 20000.0, PARK_YAW)
    assert C5._corners_at_yaw(rect, PARK_YAW + 0.0004, 100000.0, 20000.0) == []   # 0.35 cm
    assert C5._corners_at_yaw(rect, PARK_YAW + 0.001, 100000.0, 20000.0) != []    # 0.87 cm


def test_volume_point_is_one_shared_helper():
    """The read is machinery now, not two copies: `stage_api.volume_point` is what both stages and
    both checks import, and it handles the empty pin."""
    from pypcg import stage_api
    assert S4.volume_point is stage_api.volume_point and S5.volume_point is stage_api.volume_point
    assert stage_api.volume_point({"Volume": []}) == (None, 0.0)
    assert stage_api.volume_point({}) == (None, 0.0)
    from pypcg.checks import s04 as C4
    from pypcg.checks import s05 as C5
    assert C4.volume_point is stage_api.volume_point and C5.volume_point is stage_api.volume_point


# ---- determinism -----------------------------------------------------------------------------------
@pytest.mark.parametrize("module", [S4, S5])
def test_the_stage_is_deterministic_across_repeats(module):
    """RANDOM = False: the shape is a function of the volume's transform and the parameters, so the
    seed changes nothing and two runs are identical field for field."""
    def run(seed):
        return stage_api.execute(module, volume(), dict(stage_api.defaults(module), Seed=seed),
                                 FakeOps())[0]["Footprint"][0][0].points
    assert run(7) == run(7) == run(42)


# ---- V1 checks -------------------------------------------------------------------------------------
def test_v1_checks_pass_on_the_measured_output():
    from pypcg.checks import s04 as C4
    from pypcg.checks import s05 as C5
    vin = volume()
    assert C4.check(vin, params(S4), S4.run(vin, params(S4), None), FakeOps()) == []
    vin5 = volume(PARK_AT[:2], PARK_YAW)
    assert C5.check(vin5, params(S5), S5.run(vin5, params(S5), None), FakeOps()) == []


def test_v1_checks_catch_a_wrong_winding_and_a_wrong_size():
    from pypcg.checks import s04 as C4
    from pypcg.checks import s05 as C5
    vin = volume()
    out = S4.run(vin, params(S4), None)
    flipped = Spline(list(reversed(out["Footprint"][0][0].points)), closed=True, linear=True)
    f = C4.check(vin, params(S4), {"Footprint": [(flipped, ["Footprint"])]}, FakeOps())
    assert any("signed area" in x and "positive" in x for x in f)
    big = S5.run(volume(), params(S5, RectWidth=120000.0), None)
    assert C5.check(volume(), params(S5), big, FakeOps()) != []


def test_v1_oracle_compares_the_official_vertices():
    from pypcg.checks import s04 as C4
    vin = volume()
    mine = S4.run(vin, params(S4), None)
    official = {"Footprint": [Spline([(x, y, 0.0) for x, y in HEX_OFFICIAL], closed=True)]}
    assert C4.check(vin, params(S4), mine, FakeOps(), official) == []
    moved = Spline([(x + 5000.0, y, 0.0) for x, y in HEX_OFFICIAL], closed=True)
    assert any("oracle" in x for x in C4.check(vin, params(S4), mine, FakeOps(),
                                               {"Footprint": [moved]}))


# ---- round 2b: the engine's quaternion composition ---------------------------------------------------
# The stage-5 volume's own quaternion and the official park's world corners, at full precision
# (pyg_probe_t13_quat.py, 2026-10-19). UE's rotator -> quaternion does not give these bits back, so
# the stage reads `Points.quat`.
PARK_QUAT = (-6.195738473838943e-17, -1.2093979544242493e-16, 0.2942293189855836, 0.9557348522729927)
PARK_OFFICIAL_BITS = [(13182.984920770628, 37248.0606854786), (95868.80649062656, 93489.1036284926),
                      (107117.01507922937, 76951.9393145214), (24431.193509373436, 20710.896371507413)]


def test_park_matches_the_demo_bit_for_bit_with_the_volume_quaternion():
    vin = volume(PARK_AT, PARK_YAW)
    vin["Volume"][0][0].quat = [PARK_QUAT]
    spl = pts_of(S5.run(vin, params(S5), None))
    assert xy(spl) == PARK_OFFICIAL_BITS


def test_one_placement_serves_both_shapes():
    """Stage 4 at a non-zero yaw goes through the same `geo.place` as stage 5: a hexagon turned by the
    park's quaternion is the park quaternion applied to the local hexagon, and at the identity
    quaternion the placement is exact (the demo tower)."""
    local = S4.hexagon((0.0, 0.0), 16000.0, 16000.0, 0.0, (0.0, 0.0, 0.0, 1.0))
    turned = S4.hexagon((10.0, 20.0), 16000.0, 16000.0, 0.0, PARK_QUAT)
    assert turned == geo.place(local, PARK_QUAT, (10.0, 20.0))
    assert all(math.dist(a, geo.rotate(b, PARK_YAW)) < 1e-8 for a, b in
               zip(S4.hexagon((0.0, 0.0), 16000.0, 16000.0, 0.0, PARK_QUAT), local))


def test_volume_quat_prefers_the_engine_quaternion_and_round_trips():
    from pypcg import stage_api
    vin = volume(PARK_AT, PARK_YAW)
    assert stage_api.volume_quat(vin) == geo.quat_from_yaw(PARK_YAW)          # fixture: no engine quat
    vin["Volume"][0][0].quat = [PARK_QUAT]
    assert stage_api.volume_quat(vin) == PARK_QUAT
    back = geo.from_json(geo.to_json(vin["Volume"][0][0]))
    assert back.quat == [PARK_QUAT]
    assert "quat" not in geo.to_json(volume()["Volume"][0][0])               # older records unchanged
    assert stage_api.volume_quat({"Volume": []}) is None


def test_adding_a_point_drops_the_engine_quaternions():
    """`Points.quat` belongs to the points `convert` read; a later `add` would leave it shorter than
    `loc`, so `add` clears it and `volume_quat` falls back to the yaw."""
    from pypcg import stage_api
    vin = volume(PARK_AT, PARK_YAW)
    pts = vin["Volume"][0][0]
    pts.quat = [PARK_QUAT]
    pts.add((0.0, 0.0, 0.0))
    assert pts.quat is None and len(pts) == 2
    assert stage_api.volume_quat(vin) == geo.quat_from_yaw(PARK_YAW)
