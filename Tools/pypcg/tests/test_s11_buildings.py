"""Stage 11, Buildings (Task 20; spec 3, Step B).

The invariants are the task brief's, corrected where the official graph says otherwise (s11.md 5):
  - every footprint's TEXTURE height (the native write's output) is inside its class's range; the heights
    the building nodes receive are not (the HighRise factor reaches 5, the complex shapes x2 / x1.3);
  - a footprint inside the HighRise zone gets a factor >= 1 (taller than the same footprint outside it);
  - every footprint reaches exactly one building node (the rooftop count is the native node's);
  - the TL style code stays in the medium class's BuildingsStyles (traps.md 34), untouched;
  - empty inputs -> every output empty, on all three Python nodes.

Offline the booleans are `fakes.FakeOps` (convex rings) and the terrain `fakes.FlatTerrain`."""
import json
import math
import os
import random

import pytest

from fakes import FakeOps, FlatTerrain
from pypcg import geo, stage_api
from pypcg.geo import ParamSet, Polygon, Spline
from pypcg.geo import frames as F
from pypcg.stages import s11_buildings as S
from pypcg.stages import s11_buildings_lots as L
from pypcg.stages import s11_buildings_rooftops as R

REPO = stage_api.REPO
OPS = FakeOps()


def official_ir():
    with open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_3_1_Buildings.json"), encoding="utf-8") as fh:
        return json.load(fh)


def official(name):
    return next(n for n in official_ir()["nodes"] if n["name"] == name)


def box(x0, y0, x1, y1, z=0.0):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [], z)


def zone(x0, y0, x1, y1, z=24610.0):
    pts = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
    return Spline(pts, closed=True, linear=True, polyline=list(pts))


def height_set(h):
    return ParamSet({"MaxHeight": h}, {"MaxHeight": "Double"})


ZONE = zone(0.0, 0.0, 20000.0, 20000.0)
# small: two lots outside the zone; medium: two inside, a big square, a big oblong and a small one outside;
# large: a big square inside
SMALL = [box(30000, 0, 32000, 2000), box(33000, 0, 35000, 1500)]
MEDIUM = [box(1000, 1000, 3000, 3000), box(5000, 5000, 9000, 8000), box(40000, 0, 43500, 3500),
          box(40000, 5000, 46000, 7000), box(50000, 0, 52000, 2000)]
LARGE = [box(10000, 10000, 13000, 13000)]


def inputs(**over):
    ins = {"SmallLots": [(p, frozenset({"SmallDistrictsBldgFootprints"})) for p in SMALL],
           "MediumLots": [(p, frozenset({"MediumDistrictsBldgFootprints"})) for p in MEDIUM],
           "LargeLots": [(p, frozenset({"LargeDistrictsBldgFootprints"})) for p in LARGE],
           "SmallHeights": [(height_set(h), frozenset()) for h in (1600.0, 2700.0)],
           "MediumHeights": [(height_set(h), frozenset()) for h in (2000.0, 3000.0, 3800.0, 3900.0, 1600.0)],
           "LargeHeights": [(height_set(h), frozenset()) for h in (6000.0,)],
           "HighRise": [(ZONE, frozenset({"HighRise"}))],
           "MeshTerrain": [(FlatTerrain(500.0), frozenset())]}
    ins.update(over)
    return ins


def params(**kw):
    p = dict(stage_api.defaults(S))
    p.update(kw)
    return p


def run(ins=None, seed=42, **kw):
    out, _ctx = stage_api.execute(S, inputs() if ins is None else ins, dict(params(**kw), Seed=seed), OPS)
    return out


def values(out, pin):
    return [v for v, _t in out[pin]]


def hs(out, pin):
    return [v.values["MaxHeight"] for v in values(out, pin + "Heights")]


# ---- contract ---------------------------------------------------------------------------------------
def test_contract_parameters_are_the_official_kept_ones():
    off = {p["name"]: p for p in official_ir()["params"]}
    kept = [n for n in off if n not in ("Debug", "Partitioned")]
    assert list(S.PARAMS) == kept
    for name in kept:
        assert S.PARAMS[name].default == off[name]["value"], name
        assert S.PARAMS[name].type == off[name]["type"], name
    from pypcg import graphs
    from pypcg.profiles import official as prof
    names = [p["name"] for p in graphs.graph(11).to_ir(prof)["params"]]
    assert names == [stage_api.SEED] + kept                                      # Debug, Partitioned dropped


def _graph():
    from pypcg import graphs, ir
    from pypcg.profiles import official as prof
    doc = graphs.graph(11).to_ir(prof)                 # raises on an unwired Python input pin
    by = {x["name"]: x for x in doc["nodes"]}
    py = {x["title"]: x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE}
    return doc, by, py


def _feeds(node, by):
    return {p["label"]: [by[e[0]] for e in p["edges"]] for p in node["inputs"]}


def _edges(doc):
    return {(e[0], e[1], x["name"], p["label"]) for x in doc["nodes"] for p in x["inputs"] for e in p["edges"]}


def test_contract_scene_reads_feed_the_python_nodes_by_name():
    _doc, by, py = _graph()
    assert set(py) == {"Python: s11_buildings_lots", "Python: s11_buildings", "Python: s11_buildings_rooftops"}
    lf = _feeds(py["Python: s11_buildings_lots"], by)
    assert [x["title"] for x in lf["Lots"]] == ["Get Lots"]
    assert lf["Lots"][0]["overrides"]["ActorReferences"] == official("Subgraph_1")["overrides"]["ActorReferences"]
    mf = _feeds(py["Python: s11_buildings"], by)
    assert set(S.INPUTS) | {stage_api.PARAMS_PIN} == set(mf)
    assert [x["title"] for x in mf["HighRise"]] == ["HighRise Zone"]
    assert mf["HighRise"][0]["overrides"] == {"ActorTag": "HighRise"}
    assert [x["title"] for x in mf["MeshTerrain"]] == ["Get Final Mesh Terrain"]
    assert mf["MeshTerrain"][0]["overrides"]["MeshPartitionQueryType"] == "Final"
    for cls in S.CLASSES:
        assert [x["title"] for x in mf[cls + "Lots"]] == [official("Subgraph_2_%sDistrict" % cls)["title"]]
        x = mf[cls + "Heights"][0]
        assert x["class"] == "PCGExtractAttributeSettings" and x["settings"]["InputSource"] == "PCGBegin(@data.MaxHeight)PCGEnd"
    city = [x for x in by.values() if x.get("subgraph", "").endswith("LoadCitySampleData.LoadCitySampleData")]
    assert len(city) == 1                                                          # one, shared


def test_contract_texture_writes_are_native_with_the_height_getters():
    doc, by, py = _graph()
    getters = {x["name"]: x["getter_param"] for x in doc["nodes"] if x.get("getter_param")}
    for cls in S.CLASSES:
        tex = next(x for x in by.values() if x["title"] == official("Subgraph_2_%sDistrict" % cls)["title"])
        assert tex["overrides"] == official("Subgraph_2_%sDistrict" % cls)["overrides"]
        assert tex["overrides"]["Texture"].endswith("T_Noises_Grunge_4k_.T_Noises_Grunge_4k_")
        f = _feeds(tex, by)
        assert [getters[x["name"]] for x in f["RemapValueOutLow"]] == ["MinHeight%sDistrict" % cls]
        assert [getters[x["name"]] for x in f["RemapValueOutHigh"]] == ["MaxHeight%sDistrict" % cls]
        assert [x["title"] for x in f["PrimaryInput"]] == ["Python: s11_buildings_lots"]


def test_contract_building_nodes_keep_their_official_settings():
    doc, by, py = _graph()
    for name in ("Subgraph_3", "Subgraph_40", "Subgraph_41", "Loop_1", "Loop_2", "Subgraph_33", "Subgraph_36",
                 "Loop_3", "Loop_4", "Loop_5"):
        mine = [x for x in by.values() if x["title"] == official(name)["title"] and x.get("subgraph") == official(name)["subgraph"]
                and x.get("overrides") == official(name)["overrides"]]
        assert len(mine) == 1, name
    # traps.md 34: the five style-code lists exactly as shipped -- TL in the medium class only
    assert "TL" in official("Subgraph_40")["overrides"]["BuildingsStyles"].split(",")
    for name in ("Subgraph_3", "Subgraph_41"):
        assert "TL" not in official(name)["overrides"]["BuildingsStyles"].split(",")
    for name in ("Subgraph_33", "Subgraph_36"):
        assert "TL" not in official(name)["overrides"]["BuildingStyles"].split(",")


def test_contract_every_output_pin_is_wired_as_officially():
    doc, by, py = _graph()
    edges = _edges(doc)
    main = py["Python: s11_buildings"]["name"]
    roofs = py["Python: s11_buildings_rooftops"]["name"]
    out = [x for x in doc["nodes"] if x["name"] == "DefaultOutputNode"][0]
    assert [e for p in out["inputs"] for e in p["edges"]] == [[roofs, "SmallRooftops"], [roofs, "MediumRooftops"],
                                                              [roofs, "LargeRooftops"]]
    targets = {"SmallFootprints": ("Subgraph_3", "BuildingsFootprints"), "MediumFootprints": ("Subgraph_40", "BuildingsFootprints"),
               "LargeFootprints": ("Subgraph_41", "BuildingsFootprints"), "MediumComplex": ("Loop_2", "In"),
               "LargeComplex": ("Loop_1", "In"), "SmallCollision": ("Loop_5", "In"), "MediumCollision": ("Loop_4", "In"),
               "LargeCollision": ("Loop_3", "In")}
    for stream, (node, pin) in targets.items():
        writer = [by[t] for s, sp, t, l in edges if s == main and sp == stream]
        assert len(writer) == 1 and writer[0]["class"] == "PCGCopyAttributesSettings", stream
        assert writer[0]["settings"]["OutputTarget"] == "PCGBegin(@data.MaxHeight)PCGEnd"
        assert [(s, sp) for s, sp, t, l in edges if t == writer[0]["name"] and l == "Source"] == [(main, stream + "Heights")]
        hit = [(by[t]["title"], l) for s, sp, t, l in edges if s == writer[0]["name"]]
        assert hit == [(official(node)["title"], pin)], stream
    spawn = sorted(by[t]["title"] for s, sp, t, l in edges if s == main and sp == "SpawnMeshes")
    assert spawn == sorted(official(n)["title"] for n in ("Subgraph_3", "Subgraph_40", "Subgraph_41"))
    rf = _feeds(py["Python: s11_buildings_rooftops"], by)
    assert [x["title"] for x in rf["MediumRoofs"]] == [official("Subgraph_36")["title"], official("Subgraph_40")["title"]]
    assert [x["title"] for x in rf["LargeRoofs"]] == [official("Subgraph_33")["title"], official("Subgraph_41")["title"]]
    for mesh, pin in R.MESHES:
        hit = [by[t]["title"] for s, sp, t, l in edges if s == roofs and sp == pin]
        assert hit == [official(mesh)["title"]], pin


def test_contract_fixed_settings_are_the_official_overrides():
    for name in ("Subgraph_7", "Subgraph_43", "Subgraph_45"):
        ov = official(name)["overrides"]
        assert ov["MaximumDistance"] == S.MAX_DISTANCE_CM and (ov["RemapOutputMin"], ov["RemapOutputMax"]) == S.REMAP
        assert ov["UseRemap"] is True
    assert official("Subgraph_37")["overrides"] == {"Operator": "Greater", "Size": S.SIZE_M2["Medium"]}
    assert official("Subgraph_34")["overrides"] == {"Operator": "Greater", "Size": S.SIZE_M2["Large"]}
    for name in ("Subgraph_35", "Subgraph_32"):
        assert official(name)["overrides"] == {"ratioLimit": S.SQUARE_RATIO}
    assert official("FilterDataByAttribute_0")["settings"]["Threshold"]["AttributeTypes"]["DoubleValue"] == S.TALL["Medium"]
    assert official("FilterDataByAttribute_1")["settings"]["Threshold"]["AttributeTypes"]["DoubleValue"] == S.TALL["Large"]
    ov = official("Subgraph_38")["overrides"]
    assert (ov["NoiseMin"], ov["NoiseMax"], ov["AttributeOperation"]) == (S.NOISE[0], S.NOISE[1], "Set")
    assert official("AttributeMathsOp_2")["pin_defaults"][0]["value"] == S.SCALE["Medium"]
    assert official("AttributeMathsOp_1")["pin_defaults"][0]["value"] == S.SCALE["Large"]
    for node, ratio, mesh, mat in R.CHAIN:
        assert official(node)["overrides"]["Ratio"] == ratio
        assert official(mesh)["overrides"]["Material"].endswith("MI_Rooftop_%s" % mat)
    assert official(R.LAST[0])["overrides"]["Material"].endswith("MI_Rooftop_%s" % R.LAST[1])
    for c, tag in L.CLASS_TAGS:
        name = {"SmallLots": "FilterTags_SmallDistricts", "MediumLots": "FilterTags_MediumDistricts",
                "LargeLots": "FilterTags_LargeDistricts"}[c]
        assert official(name)["overrides"] == {"FilteredInputTags": tag}


# ---- empty inputs -------------------------------------------------------------------------------------
def test_empty_inputs_main_node():
    out = run({pin: [] for pin in S.INPUTS})
    assert all(out[pin] == [] for pin in S.OUTPUTS if pin != "SpawnMeshes")


def test_empty_inputs_lots_and_rooftops_nodes():
    out, _ = stage_api.execute(L, {"Lots": []}, {stage_api.SEED: 42}, OPS)
    assert all(v == [] for v in out.values())
    out, _ = stage_api.execute(R, {pin: [] for pin in R.INPUTS}, {stage_api.SEED: 42}, OPS)
    assert all(v == [] for v in out.values())


# ---- invariants -----------------------------------------------------------------------------------------
def test_lots_split_by_exact_class_tag_and_forwarded_as_read():
    items = [(SMALL[0], frozenset({"SmallDistrictsBldgFootprints", "Selected"})),
             (MEDIUM[0], frozenset({"MediumDistrictsBldgFootprints"})),
             (LARGE[0], frozenset({"LargeDistrictsBldgFootprintsX"})),
             (zone(0, 0, 1, 1), frozenset({"SmallDistrictsBldgFootprints"}))]
    out, _ = stage_api.execute(L, {"Lots": items}, {stage_api.SEED: 42}, OPS)
    assert [v for v, _t in out["SmallLots"]] == [SMALL[0]] and out["SmallLots"][0][0] is SMALL[0]
    assert "Selected" not in out["SmallLots"][0][1]
    assert [v for v, _t in out["MediumLots"]] == [MEDIUM[0]] and out["LargeLots"] == []


def test_texture_heights_inside_the_class_range_and_footprints_on_the_terrain():
    out = run()
    p = params()
    # the inputs here play the native texture write: inside [Min, Max] of the demo overrides' classes
    for v, _t in inputs()["SmallHeights"]:
        assert 1500.0 <= v.values["MaxHeight"] <= 3000.0
    for pin in ("SmallFootprints", "LargeComplex"):
        for v in values(out, pin):
            zs = {q[2] for q in v.points} if isinstance(v, Spline) else {v.z}
            assert zs == {500.0}, pin                              # levelled at the terrain's lowest point
    assert p["MinHeightSmallDistrict"] == 2000.0


def test_highrise_factor_is_at_least_one_and_grows_inward():
    out = run(ComplexBuildingShapes=False)
    base = {round(p.outer[0][0]): h for p, h in zip(MEDIUM, (2000.0, 3000.0, 3800.0, 3900.0, 1600.0))}
    got = {round(v.points[0][0]): h for v, h in zip(values(out, "MediumFootprints"), hs(out, "MediumFootprints"))}
    inside = [x for x in (1000, 5000)]
    for x in inside:
        assert got[x] >= base[x]
    assert got[40000] == base[40000] and got[50000] == base[50000]         # outside: untouched
    # the deeper lot (5000..9000) is the farther one from the zone's edge: the larger factor
    assert got[5000] / base[5000] > got[1000] / base[1000]
    # selected first (Gather_0), then the rest in input order
    assert [round(v.points[0][0]) for v in values(out, "MediumFootprints")] == [1000, 5000, 40000, 40000, 50000]


def test_distance_factor_is_the_remapped_mean():
    rings = [[(0.0, 0.0, 0.0), (10.0, 0.0, 0.0)], [(30.0, 0.0, 0.0)]]
    samples = [(-10.0, 0.0, 0.0)]
    f = S.distance_factors(rings, samples)                     # distances 10, 20 | 40 -> 1, 2.333 | 5
    assert f[0] == pytest.approx((1.0 + (1.0 + 4.0 / 3.0)) / 2, abs=1e-6) and f[1] == pytest.approx(5.0)
    assert S.distance_factors([[(0.0, 0.0, 0.0)]], samples) == [3.0]          # one value: the mid range


def test_every_footprint_reaches_exactly_one_building_node():
    for complex_ in (False, True):
        out = run(ComplexBuildingShapes=complex_)
        n = {cls: len(out[cls + "Footprints"]) + len(out.get(cls + "Complex", [])) for cls in S.CLASSES}
        assert n == {"Small": len(SMALL), "Medium": len(MEDIUM), "Large": len(LARGE)}
        for s in S.STREAMS:
            assert len(out[s]) == len(out[s + "Heights"])
        assert [v.values for v in values(out, "SpawnMeshes")] == [{"SpawnMeshes": True}]


def test_complex_split_sizes_squares_and_heights():
    out = run(ComplexBuildingShapes=True)
    med = values(out, "MediumFootprints")
    # the two lots of 400 m2 (not over 800) as polygons first, then the 60 x 20 m oblong (ratio 3) as a spline
    assert [type(v).__name__ for v in med] == ["Polygon", "Polygon", "Spline"]
    assert [round(v.outer[0][0]) for v in med[:2]] == [1000, 50000]          # Gather_0 order kept
    assert med[2].points[0][:2] == (40000.0, 5000.0) and len(med[2].points) == 4
    # the 40 x 30 m lot in the zone (3000 x factor) and the 35 x 35 m square (3800) are square and over 2500
    assert len(values(out, "MediumComplex")) == 2
    assert all(2 * S.NOISE[0] <= h <= 2 * S.NOISE[1] for h in hs(out, "MediumComplex"))     # Write_Noise x 2
    assert hs(out, "LargeComplex") == [pytest.approx(hs(run(ComplexBuildingShapes=False), "LargeFootprints")[0] * 1.3)]


def test_square_rejects_by_count_angle_and_ratio():
    q = lambda yaw: F.make_from_xz((math.cos(math.radians(yaw)), math.sin(math.radians(yaw)), 0.0), F.UP)
    pts = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (0.0, 10.0, 0.0)]
    assert S.square(pts, [q(0), q(90), q(180), q(270)]) is None
    assert S.square(pts[:3], [q(0), q(135), q(225)]) == "count"
    assert S.square(pts, [q(0), q(91), q(180), q(270)]) == "angle"
    long = [(0.0, 0.0, 0.0), (30.0, 0.0, 0.0), (30.0, 10.0, 0.0), (0.0, 10.0, 0.0)]
    assert S.square(long, [q(0), q(90), q(180), q(270)]) == "ratio"


def test_clean_spline_drops_a_collinear_point_and_a_duplicate():
    pts = [(0.0, 0.0, 0.0), (5.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (10.0, 10.0, 0.0), (0.0, 10.0, 0.0)]
    qs = [(0.0, 0.0, 0.0, 1.0)] * len(pts)
    out, rots = S.clean(pts, qs)
    assert out == [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (0.0, 10.0, 0.0)] and len(rots) == 4


def test_collision_streams_only_with_collision_geometry():
    assert all(run()[c + "Collision"] == [] for c in S.CLASSES)
    out = run(CollisionGeometry=True)
    assert [len(out[c + "Collision"]) for c in S.CLASSES] == [len(SMALL), len(MEDIUM), len(LARGE)]


def test_rooftops_tagged_by_class_and_each_given_one_material():
    roof = lambda x: Spline([(x, 0.0, 9.0), (x + 1, 0.0, 9.0), (x, 1.0, 9.0)], closed=True)
    ins = {"SmallRoofs": [(roof(0), frozenset({"Building_ID:0"}))],
           "MediumRoofs": [(roof(i), frozenset()) for i in range(10, 40)],
           "LargeRoofs": [(roof(i), frozenset()) for i in range(100, 150)]}
    out, _ = stage_api.execute(R, ins, {stage_api.SEED: 7}, OPS)
    assert out["SmallRooftops"] == [(ins["SmallRoofs"][0][0], ["Building_ID:0", "SmallRooftops"])]
    assert out["SmallRooftops"][0][0] is ins["SmallRoofs"][0][0]                # the very spline (FORWARD_SPLINES)
    assert len(out["MediumRooftops"]) == 30 and len(out["LargeRooftops"]) == 50
    meshes = [v for _m, pin in R.MESHES for v, _t in out[pin]]
    assert len(meshes) == 81 and len({id(v) for v in meshes}) == 81


def test_rooftop_chain_is_a_bernoulli_per_rooftop():
    roof = Spline([(0, 0, 0), (1, 0, 0), (0, 1, 0)], closed=True)
    counts = [0] * len(R.MESHES)
    for seed in range(40):
        out, _ = stage_api.execute(R, {"SmallRoofs": [(roof, frozenset())] * 130, "MediumRoofs": [], "LargeRoofs": []},
                                   {stage_api.SEED: seed}, OPS)
        for i, (_m, pin) in enumerate(R.MESHES):
            counts[i] += len(out[pin])
    share = [c / (130 * 40) for c in counts]
    assert all(abs(s - 1 / 13) < 0.02 for s in share)                    # 1/13 .. 1/2 of the rest: 1/13 each


def test_seeded_runs_repeat_and_differ():
    a = run(seed=7, ComplexBuildingShapes=True)
    b = run(seed=7, ComplexBuildingShapes=True)
    c = run(seed=8, ComplexBuildingShapes=True)
    assert hs(a, "MediumComplex") == hs(b, "MediumComplex") != hs(c, "MediumComplex")


def test_oracle_draws_replace_the_noise(tmp_path, monkeypatch):
    path = tmp_path / "noise.json"
    path.write_text(json.dumps({"noise": [3000.0, 3500.0]}))
    monkeypatch.setenv(S.ORACLE_ENV, str(path))
    assert hs(run(ComplexBuildingShapes=True), "MediumComplex") == [6000.0, 7000.0]
    path.write_text(json.dumps({"noise": [3000.0]}))
    with pytest.raises(ValueError):
        run(ComplexBuildingShapes=True)


def test_official_noise_evidence_is_on_disk():
    doc = json.load(open(os.path.join(REPO, "Tools", "pypcg", "data", "s11_official_noise.json"), encoding="utf-8"))
    assert len(doc["noise"]) == 16 and all(S.NOISE[0] <= v <= S.NOISE[1] for v in doc["noise"])


# ---- engine arithmetic (pypcg.geo.frames) -------------------------------------------------------------
def test_polygon_frame_is_the_yaw_minus_90_frame_at_the_vertex_mean():
    t, q = F.polygon_frame([(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (0.0, 10.0, 0.0)])
    assert t == (5.0, 5.0, 0.0)
    assert q == (-0.0, 0.0, -0.7071067811865475, 0.7071067811865476)


def test_rebuilt_vertices_round_trip_and_orient():
    ring = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (0.0, 10.0, 0.0)]
    pos, rot, (t, q) = F.rebuilt_vertices(ring[::-1])                       # clockwise in -> reversed back
    assert [tuple(round(c, 9) for c in p[:2]) for p in pos] == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert [round(F.rotator_of(r)[1], 9) for r in rot] == [0.0, 90.0, 180.0, -90.0]


def test_spline_sampler_fits_the_curve_by_distance():
    pts = [(0.0, 0.0, 0.0), (1000.0, 0.0, 0.0), (1000.0, 1000.0, 0.0), (0.0, 1000.0, 0.0)]
    c = F.SplineCurve(pts, [(0, 0, 0)] * 4, [(0, 0, 0)] * 4, [True] * 4, True)
    assert c.length() == 4000.0
    s = c.sample_distance(100.0)
    assert len(s) == 40 and s[0] == (0.0, 0.0, 0.0) and s[10] == (1000.0, 0.0, 0.0)
    assert F.create_polygon_points(c) == pts


def _record(ins, seed=42, **kw):
    p = dict(params(**kw), Seed=seed)
    out, _ = stage_api.execute(S, ins, p, OPS)
    return {"params": p,
            "inputs": {pin: [[geo.to_json(v), sorted(t)] for v, t in items] for pin, items in ins.items()},
            "outputs": {pin: [[geo.to_json(v), list(t)] for v, t in items] for pin, items in out.items()}}


def _with_vertices(ins):
    for cls in S.CLASSES:
        ins[cls + "Lots"] = [(Polygon(v.outer, v.holes, v.z, vertices=[(x, y, v.z) for x, y in v.outer]), t)
                             for v, t in ins[cls + "Lots"]]
    return ins


DEMO = {"MinHeightSmallDistrict": 1500.0, "MaxHeightSmallDistrict": 2800.0, "MinHeightMediumDistrict": 1500.0,
        "MaxHeightMediumDistrict": 4000.0, "MinHeightLargeDistrict": 3000.0, "MaxHeightLargeDistrict": 7000.0}


def test_check_record_replays_a_record():
    from pypcg.checks import s11 as C
    ins = _with_vertices(inputs())
    rec = _record(ins, ComplexBuildingShapes=True, **DEMO)
    assert C.check_record(json.loads(json.dumps(rec)), OPS) == []
    tampered = json.loads(json.dumps(rec))
    tampered["outputs"]["MediumComplexHeights"][0][0]["values"]["MaxHeight"] = 1.0
    assert any("partial replay: MediumComplexHeights" in x for x in C.check_record(tampered, OPS))
    assert any("MediumComplex: 1 heights outside" in x for x in C.check_record(tampered, OPS))


def test_check_flags_a_texture_height_outside_its_class():
    from pypcg.checks import s11 as C
    ins = inputs(SmallHeights=[(height_set(h), frozenset()) for h in (1600.0, 9000.0)])
    out = run(ins)
    p = {k: v for k, v in params().items()}
    p.update(MinHeightSmallDistrict=1500.0, MaxHeightSmallDistrict=2800.0)
    assert any("Small: 1 texture heights outside" in x for x in C.check(ins, p, out, OPS))
