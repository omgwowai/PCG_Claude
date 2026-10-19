"""Stages 2 and 3, the background (Task 14).

Stage 2 scatters the skyline points over a square ring with Python's own random numbers (a new layout,
spec E2), so its tests are about the ring, the grid, the yaw and the cull. Stage 3 stamps the
`VistaCliffs_PCG` points onto one anchor; its fixture is that data asset's 60 points, read
2026-10-19 by `pyg_probe_t14_fixture.py` into `Tools/pypcg/data/s03_vista_cliffs.json`."""
import json
import math
import os

import pytest

from pypcg import geo, graphs, stage_api
from pypcg.checks import s02 as C2
from pypcg.checks import s03 as C3
from pypcg.geo import Points
from pypcg.profiles import official
from pypcg.stages import s02_bg_buildings as S2
from pypcg.stages import s03_bg_mountains as S3

REPO = stage_api.REPO


def official_ir(name):
    return json.load(open(os.path.join(REPO, "Tools", "pypcg", "official_ir", name + ".json"), encoding="utf-8"))


def node(ir, name):
    return [x for x in ir["nodes"] if x["name"] == name][0]


def params(module, **kw):
    p = stage_api.defaults(module)
    p.update(kw)
    return p


def run(module, inputs, **kw):
    return stage_api.execute(module, inputs, params(module, **kw), None)


def cliffs():
    doc = json.load(open(os.path.join(REPO, "Tools", "pypcg", "data", "s03_vista_cliffs.json"), encoding="utf-8"))
    return {"Cliffs": [(geo.from_json(v), frozenset(t)) for v, t in doc["Cliffs"]]}


def wiring(n):
    ir = graphs.graph(n).to_ir(official)
    py = [x for x in ir["nodes"] if x["class"] == "PCGPythonDataProcessorSettings"][0]
    edges = {(x["name"], p["label"]): [tuple(e) for e in p["edges"]] for x in ir["nodes"] for p in x["inputs"]}
    return ir, py, edges


# ---- contract -------------------------------------------------------------------------------------
def test_contract_stage2_parameters_are_the_official_values():
    off = official_ir("PCG_1_2_BG_Buildings")
    assert off["params"] == []                                    # the official graph exposes none
    outer = node(off, "Subgraph_4")["overrides"]
    assert S2.PARAMS["OuterSize"].default == float(outer["Width"]) == float(outer["Length"])
    # The centre square's Width and Length overrides (300000) are dead: both pins are wired to
    # CreateConstant_0, whose Float value is the size the graph really uses (~4.12 km).
    centre = node(off, "Subgraph_5")
    assert {p["label"]: p["edges"] for p in centre["inputs"]}["Width"] == [["CreateConstant_0", "Out"]]
    assert {p["label"]: p["edges"] for p in centre["inputs"]}["Length"] == [["CreateConstant_0", "Out"]]
    const = node(off, "CreateConstant_0")["settings"]["AttributeTypes"]
    assert const["Type"] == "Float" and S2.PARAMS["CenterSize"].default == const["FloatValue"] == 411769.84375
    scatter = node(off, "ScatterPoints")["overrides"]
    assert S2.PARAMS["PointsPerSquaredMeter"].default == scatter["PointsPerSquaredMeter"]
    assert S2.PARAMS["MaxYaw"].default == float(scatter["RotationRange"]["Yaw"])
    assert scatter["RotationRange"]["Pitch"] == scatter["RotationRange"]["Roll"] == 0
    assert S2.PARAMS["KeepRatio"].default == node(off, "Subgraph_6")["overrides"]["Ratio"]
    assert S2.INPUTS == {} and S2.OUTPUTS == ("Points",) and S2.RANDOM


def test_contract_stage2_points_feed_the_kept_spawner_and_the_spawner_is_the_output():
    ir, py, edges = wiring(2)
    spawn = [x for x in ir["nodes"] if x.get("subgraph", "").endswith("Spawn_Assets.Spawn_Assets")]
    assert len(spawn) == 1
    assert spawn[0]["overrides"] == node(official_ir("PCG_1_2_BG_Buildings"), "SpawnAssets")["overrides"]
    assert edges[(spawn[0]["name"], "PrimaryInput")] == [(py["name"], "Points")]
    assert edges[("DefaultOutputNode", "Out")] == [(spawn[0]["name"], "Out")]
    assert {p["label"] for p in py["inputs"]} == {stage_api.PARAMS_PIN}
    assert len(edges[(py["name"], stage_api.PARAMS_PIN)]) == 1 + len(S2.PARAMS)


def test_contract_stage3_parameters_are_the_official_values():
    off = official_ir("PCG_1_3_BG_Mountains")
    assert off["params"] == []
    t = node(off, "CreatePoints_0")["settings"]["PointsToCreate"][0]["Transform"]
    assert t["Rotation"] == {"W": 1, "X": 0, "Y": 0, "Z": 0}
    assert (t["Translation"]["X"], t["Translation"]["Y"]) == (0, 0)
    assert S3.PARAMS["AnchorZ"].default == float(t["Translation"]["Z"]) == -50000.0
    assert S3.PARAMS["AnchorScaleXY"].default == t["Scale3D"]["X"] == t["Scale3D"]["Y"] == 1.75
    assert S3.PARAMS["AnchorScaleZ"].default == t["Scale3D"]["Z"] == 0.5
    pd = {d["index"]: d["value"] for d in node(off, "AttributeMathsOp_2")["pin_defaults"]}
    assert node(off, "AttributeMathsOp_2")["settings"]["Operation"] == "Clamp"
    assert (S3.PARAMS["ZMin"].default, S3.PARAMS["ZMax"].default) == (float(pd[1]), float(pd[2]))
    assert node(off, "CopyPoints_0")["settings"]["AttributeInheritance"] == "SourceOnly"
    assert S3.INPUTS == {"Cliffs": "points"} and S3.OUTPUTS == ("Points",) and not S3.RANDOM


def test_contract_stage3_reads_the_data_asset_and_feeds_the_kept_spawner():
    ir, py, edges = wiring(3)
    load = [x for x in ir["nodes"] if x["class"] == "PCGLoadDataAssetSettings"]
    spawner = [x for x in ir["nodes"] if x["class"] == "PCGStaticMeshSpawnerSettings"]
    assert len(load) == 1 and len(spawner) == 1
    assert load[0]["settings"]["Asset"] == "/CitySamplePCG/PCG/DataAssets/VistaCliffs_PCG.VistaCliffs_PCG"
    assert spawner[0]["settings"]["MeshSelectorParameters"]["AttributeName"] == S3.MESH_ATTR
    assert edges[(py["name"], "Cliffs")] == [(load[0]["name"], "Out")]
    assert edges[(spawner[0]["name"], "In")] == [(py["name"], "Points")]
    assert edges[("DefaultOutputNode", "Out")] == [(py["name"], "Points")]


# ---- empty inputs (Review Focus 1) ----------------------------------------------------------------
def test_empty_inputs_stage3_gives_empty_points():
    out, _ = run(S3, {"Cliffs": []})
    assert out["Points"] == []
    out, _ = run(S3, {"Cliffs": [(Points(), frozenset())]})
    assert out["Points"] == []


@pytest.mark.parametrize("kw", [{"PointsPerSquaredMeter": 0.0}, {"CenterSize": 2500000.0},
                                {"OuterSize": 0.0}, {"KeepRatio": 0.0}])
def test_empty_inputs_stage2_degenerate_parameters_give_no_points(kw):
    """Stage 2 has no input pin; the empty cases are a ring with no area, no density or no keep."""
    out, _ = run(S2, {}, **kw)
    assert out["Points"] == []


# ---- stage 2 invariants -----------------------------------------------------------------------------
@pytest.mark.parametrize("seed", [7, 13, 101, 977, 42])
def test_ring_every_point_is_outside_the_centre_and_inside_the_outer_square(seed):
    out, ctx = run(S2, {}, Seed=seed)
    pts = out["Points"][0][0]
    outer, inner = S2.halves(params(S2))
    assert all(abs(x) <= outer and abs(y) <= outer for x, y, _ in pts.loc)
    assert not any(abs(x) < inner and abs(y) < inner for x, y, _ in pts.loc)
    assert all(z == 0.0 for _, _, z in pts.loc)
    assert C2.check(None, params(S2), out, None, notes=ctx.notes) == []
    assert C2.check(None, params(S2), out, None) == []


@pytest.mark.parametrize("seed", [7, 13, 101, 977, 42])
def test_yaw_is_within_max_yaw_and_pitch_and_roll_are_zero(seed):
    pts = run(S2, {}, Seed=seed, MaxYaw=30.0)[0]["Points"][0][0]
    assert all(abs(r[1]) <= 30.0 and r[0] == 0.0 and r[2] == 0.0 for r in pts.rot)
    assert max(abs(r[1]) for r in pts.rot) > 20.0                 # the range is used, not just 0


@pytest.mark.parametrize("seed", [7, 13, 101, 977, 42])
def test_count_is_the_cull_of_what_was_sampled(seed):
    out, ctx = run(S2, {}, Seed=seed)
    sampled = int(ctx.notes[0].split()[1])
    assert len(out["Points"][0][0]) == int(round(sampled * S2.PARAMS["KeepRatio"].default))
    # The sampler is the official grid: one candidate per ~1 km cell. Only the edge cells are random,
    # each a Bernoulli draw with its own chance, so `sampled` has sd = sqrt(sum p (1 - p)) = 3.62 at the
    # demo values (a 1 % band would be 1.6 sd and could flip when rng consumption changes). 4 sd is
    # the bound here; the exact 1 % expectation is asserted on a 20-seed mean below, where the noise
    # of a single run is gone.
    sd = S2.sampled_sd(params(S2))
    assert sd == pytest.approx(3.618, abs=0.01)
    assert abs(sampled - S2.expected_sampled(params(S2))) <= 4.0 * sd


def test_count_matches_the_ring_area_times_density_times_keep_ratio_on_the_grid():
    """The brief's invariant, on the area the sampler can reach: the ring clipped to the cells' jitter
    squares (cells -12 .. 12 cover -12 .. 13 km, so the band 12.5 .. 13 km is off the square). The
    unclipped ring is 608.0 points' worth; the official sampler, like this port, reaches 583.3."""
    p = params(S2)
    outer, inner = S2.halves(p)
    cell = S2.cell_size(p["PointsPerSquaredMeter"])
    ring_m2 = ((2 * outer) ** 2 - (2 * inner) ** 2) / 1e4
    assert ring_m2 * p["PointsPerSquaredMeter"] == pytest.approx(608.045, abs=1e-3)
    lo = math.ceil(-outer / cell) * cell                           # -1 200 000: the first cell's edge
    reach_m2 = ((outer - lo) ** 2 - (2 * inner) ** 2) / 1e4
    assert S2.expected_sampled(p) == pytest.approx(reach_m2 * p["PointsPerSquaredMeter"], rel=1e-4)
    kept = [len(run(S2, {}, Seed=s)[0]["Points"][0][0]) for s in range(20)]
    mean = sum(kept) / len(kept)
    assert mean == pytest.approx(reach_m2 * p["PointsPerSquaredMeter"] * p["KeepRatio"], rel=0.01)


def test_points_start_at_the_samplers_first_cell():
    """The official output (2026-10-19, 394 points) spans X -1 199 538 .. 1 248 371 and Y -1 197 847 ..
    1 245 074: the grid starts at ceil(-12.5) = cell -12, so nothing lies below -1 200 000. A uniform
    scatter over the square would reach -1 250 000, 500 m outside the official bounds (V2's margin is
    200 m)."""
    for seed in (7, 13):
        pts = run(S2, {}, Seed=seed)[0]["Points"][0][0]
        assert min(min(x, y) for x, y, _ in pts.loc) >= -1200000.0
        assert max(max(x, y) for x, y, _ in pts.loc) <= 1250000.0


def test_point_properties_are_the_fill_primitives_outputs():
    pts = run(S2, {})[0]["Points"][0][0]
    assert set(pts.bounds_min) == {(-10.0, -10.0, -10.0)} and set(pts.bounds_max) == {(10.0, 10.0, 10.0)}
    assert set(pts.scale) == {(1.0, 1.0, 1.0)} and set(pts.steepness) == {1.0}
    assert all(0.0 < d <= 1.0 for d in pts.density)
    assert len(set(pts.seed)) == len(pts)                          # the spawner picks a mesh per seed


def test_seeded_runs_repeat_and_differ():
    a = geo.to_json(run(S2, {}, Seed=7)[0]["Points"][0][0])
    b = geo.to_json(run(S2, {}, Seed=7)[0]["Points"][0][0])
    c = geo.to_json(run(S2, {}, Seed=8)[0]["Points"][0][0])
    assert a == b and a != c


def test_check_stage2_catches_a_point_in_the_centre():
    out, _ = run(S2, {})
    pts = out["Points"][0][0]
    pts.loc[0] = (0.0, 0.0, 0.0)
    assert any("off the ring" in x for x in C2.check(None, params(S2), out, None))


# ---- stage 3 invariants -----------------------------------------------------------------------------
def test_stamp_count_equals_the_assets_point_count():
    inp = cliffs()
    out, _ = run(S3, inp)
    assert len(out["Points"]) == 1 and len(out["Points"][0][0]) == len(inp["Cliffs"][0][0]) == 60


def test_stamp_z_is_source_z_times_scale_plus_anchor_clamped():
    inp = cliffs()
    src = inp["Cliffs"][0][0]
    pts = run(S3, inp)[0]["Points"][0][0]
    clamped = 0
    for (x, y, z), (a, b, c) in zip(src.loc, pts.loc):
        raw = z * 0.5 - 50000.0
        assert c == max(-100000.0, min(raw, 100000.0))
        assert (a, b) == (x * 1.75, y * 1.75)
        clamped += raw != c
    assert clamped > 0                                             # the fixture exercises the clamp
    assert C3.check(inp, params(S3), {"Points": [(pts, ["Points"])]}, None) == []


def test_stamp_pitch_and_roll_are_zero_and_scale_is_multiplied():
    inp = cliffs()
    src = inp["Cliffs"][0][0]
    pts = run(S3, inp)[0]["Points"][0][0]
    assert any(r[0] != 0.0 or r[2] != 0.0 for r in src.rot)       # the fixture has tilted cliffs
    assert all(r[0] == 0.0 and r[2] == 0.0 for r in pts.rot)
    assert [r[1] for r in pts.rot] == [r[1] for r in src.rot]
    assert pts.scale == [(a * 1.75, b * 1.75, c * 0.5) for a, b, c in src.scale]


def test_mesh_attribute_survives_the_round_trip():
    inp = cliffs()
    src = inp["Cliffs"][0][0]
    pts = run(S3, inp)[0]["Points"][0][0]
    assert src.types[S3.MESH_ATTR] == "SoftObjectPath"
    assert pts.types == src.types and pts.attrs == src.attrs
    back = geo.from_json(geo.to_json(pts))                         # what the run record replays
    assert back.attrs[S3.MESH_ATTR] == src.attrs[S3.MESH_ATTR]
    assert sum(1 for m in back.attrs[S3.MESH_ATTR] if m.endswith("SM_GiganticSandstoneTerrain_01")) > 0


def test_check_stage3_catches_a_lost_mesh():
    inp = cliffs()
    pts = run(S3, inp)[0]["Points"][0][0]
    pts.attrs[S3.MESH_ATTR] = ["None"] * len(pts)
    assert any("Mesh" in x for x in C3.check(inp, params(S3), {"Points": [(pts, ["Points"])]}, None))


def test_stage3_is_deterministic():
    inp = cliffs()
    a = geo.to_json(run(S3, inp, Seed=7)[0]["Points"][0][0])
    b = geo.to_json(run(S3, inp, Seed=8)[0]["Points"][0][0])
    assert a == b


def test_stamp_matches_the_official_spawners_instances():
    """The offline oracle: the 59 transforms the official graph's `StaticMeshSpawner_0` placed, read
    2026-10-19 by `Content/Python/pypcg_cliffs_fixture.py` (regenerate that file, then this fixture).
    The instance transform is the point's own -- location, rotator, scale -- so the stamp must equal it
    without the Python write path in between: location to the last bit, scale to 1e-9, yaw to 1e-6 deg
    (the fixtures' rotators carry float precision)."""
    doc = json.load(open(os.path.join(REPO, "Tools", "pypcg", "data", "s03_official_instances.json"),
                         encoding="utf-8"))
    assert doc["graph"].endswith("PCG_1_3_BG_Mountains.PCG_1_3_BG_Mountains")
    spec = json.load(open(os.path.join(REPO, "Tools", "pypcg", "data", "s03_vista_cliffs.json"), encoding="utf-8"))
    assert doc["read_by"] == "Content/Python/pypcg_cliffs_fixture.py" and spec["read_by"] == doc["read_by"]
    pts = run(S3, cliffs())[0]["Points"][0][0]
    mine = sorted([(pts.attrs[S3.MESH_ATTR][i], tuple(pts.loc[i]), pts.rot[i], tuple(pts.scale[i]))
                   for i in range(len(pts)) if pts.attrs[S3.MESH_ATTR][i] != "None"], key=lambda r: (r[0], r[1]))
    theirs = sorted([(r[0], tuple(r[1]), tuple(r[2]), tuple(r[3])) for r in doc["instances"]],
                    key=lambda r: (r[0], r[1]))
    assert len(mine) == len(theirs) == 59
    for a, b in zip(mine, theirs):
        assert a[0] == b[0]
        assert a[1] == b[1]                                       # location, bit for bit
        assert abs(((a[2][1] - b[2][1] + 180.0) % 360.0) - 180.0) <= 1e-6
        assert max(abs(x - y) for x, y in zip(a[3], b[3])) <= 1e-9
