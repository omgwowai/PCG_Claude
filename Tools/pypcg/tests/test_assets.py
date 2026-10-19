"""The Assign_Assets helper: the pure choice, the expansion, and the interfaces the brief fixes.

The primitive is /PCGPrimitives/Primitives/Assign/Assign_Assets; its computation is the subgraph
Assign_Assets_CoreProcess (dump of 2026-10-16 in Saved/graph_dumps/), and its copy step is the
engine's own CopyPoints. The transform rule, the seed mix and the bounds rule asserted here were
MEASURED in the editor on 2026-10-16 against the real primitive (pyg_probe_t12_case.py and
pyg_probe_t12_one.py, recorded in task-12-report.md).

`test_assign_calls_maps_the_graph_pin_names_onto_expands_keys` closes the seam between the recorded
graph and `expand`: it loads `pypcg_v1_editor.py` with a stub `unreal` and drives `assign_calls` on a
synthetic IR node, so a pin name the graph writes arrives at `expand` under a key it reads.
"""
import inspect
import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".." / ".." / "Content" / "Python"))

from pypcg import geo  # noqa: E402
from pypcg.geo import Points  # noqa: E402
from pypcg.geo import assets as A  # noqa: E402

# Four real points of /CitySamplePCG/PCG/DataAssets/Plazas/Plaza_Small_A_PCG, read from the asset:
# (loc, rot, scale, seed).
MESH_POINTS = [
    ((-500.0, -400.0, -303.79074597358704), (0.0, 0.0, 0.0), (10.0, 8.0, 10.0), -2111086339),
    ((235.54061889648438, 99.33786010742188, -303.9906437397003), (0.0, -179.99971313206382, 0.0),
     (0.9999999404078892, 0.9999999404078892, 1.0), -1759265780),
    ((-306.45941162109375, 114.19580078125, -303.9906437397003), (0.0, 85.3147757072082, 0.0),
     (1.000000019706748, 1.000000019706748, 1.0), -1613868329),
    ((69.54051208496094, 161.33660888671875, -303.9906437397003), (0.0, 0.0002288113371942108, 0.0),
     (1.000000000007974, 1.000000000007974, 1.0), -895864832),
]
MESH_BOUNDS = ((-500.0, -500.0, 0.0), (500.0, 500.0, 100.0))


def mesh_points(bounds=MESH_BOUNDS, subset=None):
    p = Points()
    for loc, rot, scale, seed in (MESH_POINTS if subset is None else subset):
        p.add(loc, rot=rot, scale=scale, seed=seed, bounds_min=bounds[0], bounds_max=bounds[1])
    return p


def asset(path="/G/Plaza.Plaza", points=None, bounds=MESH_BOUNDS):
    pts = mesh_points(bounds) if points is None else points
    b = A.bounds_of(pts)
    return {"path": path, "points": pts, "bounds": b, "size": A.size_of(b), "note": ""}


def targets(specs):
    """specs: [(loc, rot, scale, seed)] on the standard box."""
    t = Points()
    for loc, rot, scale, seed in specs:
        t.add(loc, rot=rot, scale=scale, seed=seed, bounds_min=MESH_BOUNDS[0], bounds_max=MESH_BOUNDS[1])
    return t


# ---- choose: the random pick (MatchAndSetAttributes_0) -------------------------------------------
def test_choose_gives_one_index_per_point():
    rng = random.Random(7)
    idx = A.choose(5, ["a", "b", "c"], rng)
    assert len(idx) == 5
    assert all(i in (0, 1, 2) for i in idx)
    assert len(set(idx)) > 1, "a uniform draw over three assets should not always pick the same one"


def test_choose_is_seed_deterministic():
    a = A.choose(50, ["a", "b", "c"], random.Random("1:7"))
    b = A.choose(50, ["a", "b", "c"], random.Random("1:7"))
    c = A.choose(50, ["a", "b", "c"], random.Random("2:7"))
    assert a == b
    assert a != c


def test_choose_of_no_assets_is_all_minus_one():
    assert A.choose(3, [], random.Random(1)) == [-1, -1, -1]
    assert A.choose(0, ["a"], random.Random(1)) == []


def test_choose_covers_every_asset_given_enough_points():
    rng = random.Random(3)
    assert set(A.choose(200, ["a", "b", "c", "d"], rng)) == {0, 1, 2, 3}


def test_choose_weights_bias_the_draw():
    rng = random.Random(5)
    idx = A.choose(400, ["a", "b"], rng, weights=[9.0, 1.0])
    assert idx.count(0) > idx.count(1) * 3


# ---- bounds and sizes (BoundsFromMesh, AttributeMathsOp_6/7, _4/_16) -----------------------------
def test_bounds_of_is_the_union_of_the_point_bounds():
    p = mesh_points()
    assert A.bounds_of(p) == ([-500.0, -500.0, 0.0], [500.0, 500.0, 100.0])
    assert A.size_of(A.bounds_of(p)) == (1000.0, 1000.0, 100.0)


def test_bounds_of_empty_points_is_none_and_size_zero():
    assert A.bounds_of(Points()) is None
    assert A.size_of(None) == (0.0, 0.0, 0.0)


def test_fit_ratio_is_own_size_over_mesh_size():
    own = ([-500.0, -250.0, 0.0], [500.0, 250.0, 100.0])            # 1000 x 500 x 100
    assert A.fit_ratio(own, (200.0, 200.0, 20.0), False) == (5.0, 2.5, 5.0)


def test_fit_ratio_uniform_uses_x_for_all_three():
    own = ([-500.0, -250.0, 0.0], [500.0, 250.0, 100.0])
    assert A.fit_ratio(own, (200.0, 200.0, 20.0), True) == (5.0, 5.0, 5.0)


def test_fit_ratio_leaves_a_zero_mesh_axis_alone():
    """A zero-thickness axis must not divide by zero: the ratio stays 1."""
    own = ([-500.0, -500.0, 0.0], [500.0, 500.0, 100.0])
    assert A.fit_ratio(own, (200.0, 200.0, 0.0), False) == (5.0, 5.0, 1.0)


def test_fit_ratio_is_reported_but_not_applied():
    """Measured 2026-10-16: an input box ten times the mesh's left the output scale at 1."""
    one = mesh_points(subset=MESH_POINTS[:1])
    table = [asset(points=one)]
    t = Points()
    t.add((0.0, 0.0, 0.0), bounds_min=(-5000.0, -2500.0, 0.0), bounds_max=(5000.0, 2500.0, 500.0))
    out = A.expand(t, table, [0], {"uniform_scale": False})
    assert out.scale[0] == (10.0, 8.0, 10.0), "the mesh keeps its own scale"
    assert out.attrs["$Scale"] == [(10.0, 5.0, 5.0)]    # 10000/1000, 5000/1000, 500/100


# ---- expand: the copy (CopyPoints) ---------------------------------------------------------------
def test_expand_reproduces_the_primitive_identity_case():
    """One real input point (yaw 0, scale 1, offset 0) against the primitive's own output, byte for
    byte on loc, and exactly on rot, scale and seed."""
    table = [asset()]
    t = targets([((10000.0, 20000.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 42)])
    out = A.expand(t, table, [0], {})
    assert len(out) == len(MESH_POINTS)
    official_loc = [(9500.0, 19600.0, -303.79074597358704),
                    (10235.540618896484, 20099.337860107422, -303.9906437397003),
                    (9693.540588378906, 20114.19580078125, -303.9906437397003),
                    (10069.540512084961, 20161.33660888672, -303.9906437397003)]
    official_seed = [-455695611, 1072875822, 100085031, -353494110]
    official_rot = [(0.0, 0.0, 0.0), (0.0, -179.99971313206382, 0.0), (0.0, 85.3147757072082, 0.0),
                    (0.0, 0.0002288113371942108, 0.0)]
    for i, want in enumerate(official_loc):
        assert out.loc[i] == pytest.approx(want, abs=1e-6)
    assert out.seed == official_seed
    for i, want in enumerate(official_rot):
        assert out.rot[i] == pytest.approx(want, abs=1e-6)
    assert [tuple(s) for s in out.scale] == [(10.0, 8.0, 10.0),
                                             (0.9999999404078892, 0.9999999404078892, 1.0),
                                             (1.000000019706748, 1.000000019706748, 1.0),
                                             (1.000000000007974, 1.000000000007974, 1.0)]
    assert out.attrs["Asset"] == ["/G/Plaza.Plaza"] * 4, "no per-point Mesh: the assigned path stands in"


def test_expand_rotates_the_mesh_into_the_input_frame():
    """The primitive's own output for the same input with yaw 90: the mesh's local point
    (-500, -400, -303.79) lands at (10400, 19500, -303.79), i.e. (+400, -500) from the input point
    (the measured `yaw90` case of pyg_probe_t12_one.py)."""
    table = [asset(points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((10000.0, 20000.0, 0.0), (0.0, 90.0, 0.0), (1.0, 1.0, 1.0), 42)])
    out = A.expand(t, table, [0], {})
    assert out.loc[0] == pytest.approx((10400.0, 19500.0, -303.79074597358704), abs=1e-3)
    assert out.rot[0] == pytest.approx((0.0, 90.0, 0.0), abs=1e-3)
    assert out.scale[0] == (10.0, 8.0, 10.0)


def test_expand_rotates_and_scales_the_position_together():
    """The measured `yaw90_scale2` case: the same yaw 90 with an input scale of (2, 1, 1) -- the input
    scale multiplies the mesh point BEFORE the rotation."""
    table = [asset(points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 90.0, 0.0), (2.0, 1.0, 1.0), 42)])
    out = A.expand(t, table, [0], {})
    assert out.loc[0] == pytest.approx((400.0, -1000.0, -303.79074597358704), abs=1e-3)
    assert out.scale[0] == (20.0, 8.0, 10.0)


def test_expand_multiplies_the_input_scale_into_the_point_and_the_position():
    """The measured `scale2` case: the input point's scale multiplies the mesh point's position and its
    scale (CopyPoints' Relative inheritance)."""
    table = [asset(points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (2.0, 1.0, 1.0), 42)])
    out = A.expand(t, table, [0], {})
    assert out.loc[0] == pytest.approx((-1000.0, -400.0, -303.79074597358704), abs=1e-3)
    assert out.scale[0] == (20.0, 8.0, 10.0)


def test_expand_composes_the_rotations():
    """OutRotation = TargetRotation * SourceRotation, not a sum of Euler angles."""
    q = A._qmul(A.quat_of(0.0, 90.0, 0.0), A.quat_of(0.0, -179.99971313206382, 0.0))
    assert tuple(A.rotator_of(q)) == pytest.approx((0.0, -89.99971313206382, 0.0), abs=1e-6)
    table = [asset(points=mesh_points(subset=MESH_POINTS[1:2]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 90.0, 0.0), (1.0, 1.0, 1.0), 42)])
    out = A.expand(t, table, [0], {})
    assert out.rot[0] == pytest.approx((0.0, -89.99971313206382, 0.0), abs=1e-6)


def test_expand_writes_the_asset_path_and_the_bounds():
    """UseMeshBounds puts the asset's whole box on the copy, and `AttributeMathsOp_14` then multiplies
    the point's `$Extents` (its HALF-size) by `ExtentsScale` about the box centre -- the CoreProcess
    dump's `InputSource1 = $Extents, Operation = Multiply`, and on stage 17 (scale 1) the rewrite as
    centre +- half-size reproduced all 9 843 official boxes exactly (2026-10-19). (Task 12 asserted the
    unscaled box here; that was never measured with a scale other than 1.)"""
    table = [asset("/G/SM_A.SM_A", points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((5.0, 6.0, 7.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 7)])
    out = A.expand(t, table, [0], {"use_mesh_bounds": True, "extents_scale": (2.0, 2.0, 2.0)})
    assert out.attrs["Asset"] == ["/G/SM_A.SM_A"]
    assert out.attrs["$Size"] == [(2000.0, 2000.0, 200.0)]       # report: full size x ExtentsScale
    assert tuple(out.bounds_min[0]) == (-1000.0, -1000.0, -50.0)   # the asset's box, doubled about its centre
    assert tuple(out.bounds_max[0]) == (1000.0, 1000.0, 150.0)
    out = A.expand(t, table, [0], {"use_mesh_bounds": True})
    assert tuple(out.bounds_min[0]) == (-500.0, -500.0, 0.0)       # UseMeshBounds alone: the asset's own box
    assert tuple(out.bounds_max[0]) == (500.0, 500.0, 100.0)


def test_expand_without_use_mesh_bounds_keeps_the_assembly_point_bounds():
    """Measured twice on 2026-10-16: the copied point keeps the ASSET point's own bounds, not the
    input box's (the lane mesh's 200x200x20 and the plaza point's came through against a
    -500..500 x -500..500 x 0..100 input box)."""
    narrow = ((-7.0, -8.0, -9.0), (1.0, 2.0, 3.0))
    table = [asset(points=mesh_points(narrow, subset=MESH_POINTS[:1]), bounds=narrow)]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    out = A.expand(t, table, [0], {})
    assert tuple(out.bounds_min[0]) == (-7.0, -8.0, -9.0)
    assert tuple(out.bounds_max[0]) == (1.0, 2.0, 3.0)


def test_expand_offset_moves_the_target_along_its_own_rotation():
    """`TransformPoints_1` runs on the TARGETS (`FilterDataByType_4 -> TransformPoints_1 ->
    TransformPoints_2 -> Reroute_0 -> AttributePartition_1 -> CopyPoints_0.Target`), with a non-absolute
    offset rotated by the target's own rotation and held as a float. Measured 2026-10-19 on stage 17's
    official call: every one of the 30 targets came out at `RotateVector(q, float(0, -492.541261, 0))`
    from its hull vertex, to 2e-13 cm, and every copy hangs off the MOVED target. (Task 12 rotated the
    offset by the assembly point's own rotation; on a target at yaw 0 with an assembly point at yaw
    ~180 that sends the copy the other way.)"""
    table = [asset(points=mesh_points(subset=MESH_POINTS[1:2]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    out = A.expand(t, table, [0], {"position_offset": (0.0, -492.541261, 0.0)})
    f = A._f32(-492.541261)
    assert out.loc[0][1] == pytest.approx(99.33786010742188 + f, abs=1e-9)
    assert out.loc[0][0] == pytest.approx(235.54061889648438, abs=1e-9)
    # a target at yaw 90 carries its local -Y offset to world +X
    t = targets([((0.0, 0.0, 0.0), (0.0, 90.0, 0.0), (1.0, 1.0, 1.0), 0)])
    items = A.expand_items(t, table, [0], {"position_offset": (0.0, -492.541261, 0.0)})
    moved = items[-1]
    assert moved.loc[0] == pytest.approx((-f, 0.0, 0.0), abs=1e-9)


def test_expand_multiplies_the_scale_offset_and_adds_the_rotation_offset():
    table = [asset(points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    out = A.expand(t, table, [0], {"scale_offset": (2.0, 1.0, 0.5), "rotation_offset": (0.0, 30.0, 0.0),
                                   "uniform_scale": False})
    assert out.scale[0] == (20.0, 8.0, 5.0)
    assert out.rot[0] == pytest.approx((0.0, 30.0, 0.0), abs=1e-6)


def test_expand_defaults_are_the_primitives_uniform_scale_and_mesh_bounds():
    """`Assign_Assets`' own user-parameter defaults (read 2026-10-19) are `UniformScale` TRUE and
    `UseMeshBounds` TRUE. Measured on stage 17's oracle with `ScaleOffset` (0.2, 1, 1) and the default
    `UniformScale`: every dock came out at scale (0.2, 0.2, 0.2) -- `TransformPoints` draws X only."""
    assert A.DEFAULT_UNIFORM_SCALE is True and A.DEFAULT_USE_MESH_BOUNDS is True
    table = [asset(points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    out = A.expand(t, table, [0], {"scale_offset": (0.2, 1.0, 1.0)})
    assert out.scale[0] == pytest.approx((2.0, 1.6, 2.0))           # (10, 8, 10) x 0.2 on every axis
    assert out.loc[0] == pytest.approx((-100.0, -80.0, -303.79074597358704 * 0.2))


def test_expand_multiple_targets_stay_contiguous_in_target_order():
    table = [asset("/G/SM_A.SM_A", points=mesh_points(subset=MESH_POINTS[:2])),
             asset("/G/SM_B.SM_B", points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((100.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0),
                 ((200.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    out = A.expand(t, table, [0, 1], {})
    assert len(out) == 3
    assert out.attrs["Asset"] == ["/G/SM_A.SM_A", "/G/SM_A.SM_A", "/G/SM_B.SM_B"]
    # target 0 at x 100 carries mesh points at x -500 and +236; target 1 at x 200 carries the first
    assert [round(l[0]) for l in out.loc] == [-400, 336, -300]


def test_expand_copies_source_major_within_one_asset():
    """Inside one asset's output set the copies run SOURCE-major: assembly point 0 on every target of
    that asset, then point 1, ... Measured 2026-10-19 on stage 17 (five kits, 3 to 10 targets each):
    source-major reproduces all 9 843 official copies to 7e-12 cm, target-major is 2.9 km off. (Task 12
    asserted target-major; its measurements had one target per call, where the two agree.)"""
    table = [asset(points=mesh_points(subset=MESH_POINTS[:3]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0),
                 ((1000.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    out = A.expand(t, table, [0, 0], {})
    assert len(out) == 6
    assert [round(l[0]) for l in out.loc] == [-500, 500, 236, 1236, -306, 694]


def test_expand_carries_the_input_point_attributes_onto_every_copied_point():
    table = [asset(points=mesh_points(subset=MESH_POINTS[:2]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    t.declare("local_Width", "Double", 1900.0)
    out = A.expand(t, table, [0], {})
    assert out.attrs["local_Width"] == [1900.0, 1900.0]


def test_expand_seed_is_the_engines_own_mix_of_source_and_input_seed():
    """`CopyPoints`' Relative seed inheritance is `PCGHelpers::ComputeSeed(source, target)`
    (`PCGHelpers.cpp:40-43`). Measured in the editor on 2026-10-16: the plaza's first point (seed
    -2111086339) with an input point seeded 42 gave -455695611, and with 7 gave 258744612."""
    assert A.compute_seed(-2111086339, 42) == -455695611
    assert A.compute_seed(-2111086339, 7) == 258744612
    table = [asset(points=mesh_points(subset=MESH_POINTS[:2]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 42)])
    assert A.expand(t, table, [0], {}).seed == [-455695611, 1072875822]


def test_expand_declares_Asset_Size_and_Scale_even_when_nothing_is_picked():
    out = A.expand(targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)]), [asset()], [-1], {})
    assert len(out) == 0
    assert out.types.get("Asset") == "SoftObjectPath"
    for name in ("$Size", "$Scale", "$BoundsMin", "$BoundsMax"):
        assert name in out.attrs


def test_expand_uses_mesh_attribute_when_asked():
    table = [asset("/G/SM_A.SM_A", points=mesh_points(subset=MESH_POINTS[:1])),
             asset("/G/SM_B.SM_B", points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    t.declare("Mesh", "SoftObjectPath", "/G/SM_B.SM_B")
    out = A.expand(t, table, None, {"use_mesh_attribute": True})
    assert out.attrs["Asset"] == ["/G/SM_B.SM_B"]


def test_expand_mesh_attribute_names_the_attribute_to_read():
    table = [asset("/G/SM_A.SM_A", points=mesh_points(subset=MESH_POINTS[:1])),
             asset("/G/SM_B.SM_B", points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    t.declare("KitMesh", "SoftObjectPath", "/G/SM_B.SM_B")
    out = A.expand(t, table, None, {"use_mesh_attribute": True, "mesh_attribute": "KitMesh"})
    assert out.attrs["Asset"] == ["/G/SM_B.SM_B"]


def test_expand_with_an_unknown_mesh_attribute_drops_the_point_rather_than_raising():
    table = [asset("/G/SM_A.SM_A", points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    t.declare("Mesh", "SoftObjectPath", "/G/SM_ZZZ.SM_ZZZ")
    assert len(A.expand(t, table, None, {"use_mesh_attribute": True})) == 0


def test_expand_random_position_range_draws_from_the_rng_and_repeats():
    table = [asset(points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    params = {"random_position_range": ((0.0, -100.0, 0.0), (0.0, 100.0, 0.0))}
    a = A.expand(t, table, [0], dict(params, rng=random.Random("1:12")))
    b = A.expand(t, table, [0], dict(params, rng=random.Random("1:12")))
    c = A.expand(t, table, [0], dict(params, rng=random.Random("2:12")))
    assert a.loc == b.loc
    assert a.loc != c.loc
    assert -100.0 + MESH_POINTS[0][0][1] <= a.loc[0][1] <= 100.0 + MESH_POINTS[0][0][1]


def test_expand_random_scale_range_multiplies_the_scale():
    """TransformPoints_2's scale is multiplicative; min = max draws that one value."""
    table = [asset(points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    out = A.expand(t, table, [0], {"random_scale_range": (0.1, 0.1, 0.1), "rng": random.Random(1)})
    assert out.scale[0] == pytest.approx((1.0, 0.8, 1.0))
    out = A.expand(t, table, [0], {"random_scale_range": (0.1, 0.1, 0.1),
                                   "scale_offset": (2.0, 2.0, 2.0), "rng": random.Random(1)})
    assert out.scale[0] == pytest.approx((2.0, 1.6, 2.0))


def test_expand_uniform_random_scale_draws_one_number():
    table = [asset(points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    out = A.expand(t, table, [0], {"random_scale_range": (0.0, 0.5, 0.0), "uniform_scale": True,
                                   "rng": random.Random(4)})
    assert out.scale[0][0] == out.scale[0][2], "UniformScale draws one number for all three axes"


# ---- the empty forms (Review Focus 1) ------------------------------------------------------------
def test_expand_with_no_targets_is_empty():
    assert len(A.expand(Points(), [asset()], [], {})) == 0


def test_expand_with_no_assets_is_empty():
    assert len(A.expand(targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)]), [], [], {})) == 0


def test_expand_with_an_empty_assembly_skips_that_point():
    empty = {"path": "/G/SM_A.SM_A", "points": Points(), "bounds": None, "size": (0.0, 0.0, 0.0), "note": ""}
    assert len(A.expand(targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)]), [empty], [0], {})) == 0


def test_expand_indices_shorter_than_the_targets_drops_the_rest():
    table = [asset(points=mesh_points(subset=MESH_POINTS[:1]))]
    t = targets([((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0),
                 ((10.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), 0)])
    assert len(A.expand(t, table, [0], {})) == 1


# ---- the interfaces the brief fixes --------------------------------------------------------------
def test_the_three_names_the_brief_fixes_exist_with_their_signatures():
    assert list(inspect.signature(A.choose).parameters)[:3] == ["n", "assets", "rng"]
    assert list(inspect.signature(A.expand).parameters) == ["targets", "table", "indices", "params"]
    src = (Path(A.__file__)).read_text(encoding="utf-8")
    assert "import unreal" not in src, "pypcg.geo is pure: the loader belongs in pypcg.ue"


def test_geo_assets_choose_is_not_geo_choose():
    """The package's `choose` is Filter_RandomChoice's ratio pick; the asset pick is a different
    function and must not shadow it (stage 18 calls both)."""
    assert geo.choose is not geo.assets.choose
    assert geo.choose(10, 0.5, random.Random(1)) == sorted(geo.choose(10, 0.5, random.Random(1)))


def test_points_extend_declares_missing_attributes():
    a = Points()
    a.declare("Mesh", "SoftObjectPath")
    a.add((0.0, 0.0, 0.0), Mesh="/G/A.A")
    b = Points()
    b.declare("Mesh", "SoftObjectPath")
    b.declare("Material", "SoftObjectPath")
    b.add((1.0, 0.0, 0.0), Mesh="/G/B.B", Material="/G/M.M")
    a.extend(b)
    assert len(a) == 2
    assert a.types["Material"] == "SoftObjectPath"
    assert a.attrs["Material"] == [None, "/G/M.M"]


# ---- the seam between the recorded graph and expand (Task 12 review, finding 1) -------------------
def _v1_editor():
    """`pypcg_v1_editor.py` loaded offline, with a stub `unreal` module.

    The file is an editor bridge script: it imports `unreal` at module level. `assign_calls` — the
    function under test here — touches no engine API, so a stub is enough, and the stub is inserted
    and removed around the load so no other test ever sees it."""
    import importlib.util
    import types
    root = Path(__file__).resolve().parents[3]
    path = root / "Content" / "Python" / "pypcg_v1_editor.py"
    stub = types.ModuleType("unreal")

    class _Paths(object):
        """The two module-level calls the file makes at import time."""

        @staticmethod
        def project_content_dir():
            return str(root / "Content") + "/"

        @staticmethod
        def project_dir():
            return str(root) + "/"

        @staticmethod
        def convert_relative_path_to_full(p):
            return p

    stub.Paths = _Paths
    # The file purges and re-imports every `pypcg*` module on load, which would give the rest of the
    # suite a second copy of `pypcg.stage_api` (and so two distinct `Param` classes). Snapshot the
    # whole table and put it back: this test wants `assign_calls`, nothing else.
    saved_modules = dict(sys.modules)
    saved_path = list(sys.path)
    sys.modules["unreal"] = stub
    try:
        spec = importlib.util.spec_from_file_location("_pypcg_v1_editor_under_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.modules.clear()
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path
    return mod


def _assign_ir(overrides):
    """A one-node graph IR holding an Assign_Assets subgraph node with the given overrides."""
    return {"nodes": [{"name": "Subgraph_1", "title": "Assign", "class": "PCGSubgraphSettings",
                       "subgraph": "/PCGPrimitives/Primitives/Assign/Assign_Assets.Assign_Assets",
                       "settings": {}, "overrides": dict(overrides)}]}


def test_assign_calls_maps_the_graph_pin_names_onto_expands_keys():
    """The seam. `assign_calls` receives the graph's own spellings (`ScaleOffset`) and must hand
    `expand` the keys `expand` reads (`scale_offset`); without the mapping every parameter recorded
    from the graph is silently replaced by its default."""
    mod = _v1_editor()
    calls = mod.assign_calls(_assign_ir({
        "Assets": ["/G/SM_A.SM_A"],
        "ScaleOffset": {"X": 2.0, "Y": 1.0, "Z": 0.5},
        "PositionOffset": {"X": 0.0, "Y": -492.541261, "Z": 22.0},
        "UniformScale": True,
        "UseMeshBounds": True,
        "MeshAttribute": "Mesh",
        "MatchScaleToInputBounds": True,
        "UseIndexattribute": False,
        "IndexAttribute": "ind",
        "Seed": 12345,
    }))
    assert len(calls) == 1
    params = calls[0]["params"]
    assert params["scale_offset"] == {"X": 2.0, "Y": 1.0, "Z": 0.5}
    assert params["position_offset"]["Y"] == -492.541261
    assert params["uniform_scale"] is True
    assert params["use_mesh_bounds"] is True
    assert params["mesh_attribute"] == "Mesh"
    # the pins expand does not read are reported, not silently dropped
    assert set(calls[0]["unhonoured"]) == {"MatchScaleToInputBounds", "UseIndexattribute",
                                           "IndexAttribute"}
    # ... and no graph spelling survives into `params`
    assert not (set(params) & set(mod.ASSIGN_PARAM_KEYS))


def test_assign_calls_reports_random_calls_only_when_a_range_is_non_zero():
    """A call whose random range is all zero draws nothing, so its output is reproducible without an
    rng; a non-zero range is not, and the phase must say so rather than report a clean pass."""
    mod = _v1_editor()
    zero = mod.assign_calls(_assign_ir({
        "Assets": ["/G/A.A"],
        "RandomPositionRange": {"X": 0.0, "Y": 0.0, "Z": 0.0},
        "RandomScaleRange": {"X": 0.0, "Y": 0.0, "Z": 0.0},
    }))[0]
    assert zero["random"] is False
    live = mod.assign_calls(_assign_ir({
        "Assets": ["/G/A.A"],
        "RandomScaleRange": {"X": 0.2, "Y": 0.0, "Z": 0.0},
    }))[0]
    assert live["random"] is True
    assert live["params"]["random_scale_range"]["X"] == 0.2


def test_assign_calls_skips_nodes_that_are_not_the_primitive():
    mod = _v1_editor()
    ir = {"nodes": [{"name": "Other", "class": "PCGSubgraphSettings",
                     "subgraph": "/PCGPrimitives/Primitives/Filter/Filter_RandomChoice.Filter_RandomChoice",
                     "settings": {}, "overrides": {"Ratio": 0.5}}]}
    assert mod.assign_calls(ir) == []


def test_assign_param_keys_cover_every_pin_expand_reads():
    """`expand`'s documented params must all be reachable from a graph pin, or a later stage would
    have no way to pass one in."""
    mod = _v1_editor()
    mapped = {v for v in mod.ASSIGN_PARAM_KEYS.values() if v is not None}
    doc = A.expand.__doc__
    for key in ("position_offset", "rotation_offset", "scale_offset", "extents_scale", "uniform_scale",
                "use_mesh_bounds", "use_mesh_attribute", "mesh_attribute", "random_position_range",
                "random_rotation_range", "random_scale_range"):
        assert key in mapped, "%s is read by expand but no graph pin maps to it" % key
        assert key in doc, "%s is not documented on expand" % key
    assert "rng" not in mapped, "rng is the stage's, not a graph pin"


# ---- the oracle evidence (Task 15 fix round 2) ------------------------------------------------------
def test_the_recorded_oracle_rows_back_every_measured_setting():
    """`Tools/pypcg/data/assign_oracle_rows.json`: the primitive's tapped output against `expand_items`,
    written by the oracle itself (`pypcg_v1_editor.py {"assign": {"stage": n, "label": ...}}`). Every
    deterministic row agrees on item sizes, `Asset` and seed for every point, scale and bounds exactly,
    location within 1e-9 cm and the quaternion within 1e-12; the random row agrees on sizes, order and
    `Asset`. Between them the rows cover each setting the docstring calls MEASURED."""
    import json
    path = Path(__file__).resolve().parents[1] / "data" / "assign_oracle_rows.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    covered = set()
    for r in rows:
        assert r["items"] == r["python_items"], r["run"]
        if r["random"]:
            assert r["equal"] == {"items": True, "Asset": True}, r["run"]
            covered.add("random_compare")
            continue
        assert r["equal"]["Asset"] == r["equal"]["seed"] == r["points"], r["run"]
        assert r["max_diff"]["scale"] == 0.0 and r["max_diff"]["bounds"] == 0.0, r["run"]
        assert r["max_diff"]["loc"] <= 1e-9 and r["max_diff"]["quat"] <= 1e-12, r["run"]
        st = r["settings"]
        for key in ("position_offset", "rotation_offset", "scale_offset", "extents_scale"):
            v = st.get(key)
            if v and any(abs(float(x) - (1.0 if key in ("scale_offset", "extents_scale") else 0.0)) > 0
                         for x in v.values()):
                covered.add(key)
        covered.add("uniform_%s" % st.get("uniform_scale", A.DEFAULT_UNIFORM_SCALE))
        covered.add("mesh_bounds_%s" % st.get("use_mesh_bounds", A.DEFAULT_USE_MESH_BOUNDS))
        if len(r["items"]) == 1:
            covered.add("static_mesh_no_copy_item")
    assert covered >= {"position_offset", "rotation_offset", "scale_offset", "extents_scale", "uniform_True",
                       "uniform_False", "mesh_bounds_True", "mesh_bounds_False", "static_mesh_no_copy_item",
                       "random_compare"}
