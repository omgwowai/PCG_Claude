"""Stage 18, OuterForest (Task 23; spec 3, Step B).

The contract against the official IR (parameters, the scene reads, the kept spawner and the native texture writes,
no published output), empty inputs on both Python nodes, every deterministic step against the official taps
(`Tools/pypcg/data/s18_fixture.json`, distilled by `Tools/pypcg/s18_fixture.py` from the official graph and its
substitute-texture oracle), the task's invariants as s18.md 5 corrects them (with planted faults), V1's partial
replay offline, and the seeded repeat / differ of both nodes. Offline there is no engine boolean, so the areas use
`fakes.RibbonOps` (boxes); the real booleans are covered live by V1 and the areas probe (s18.md 7)."""
import json
import math
import os
import random

import pytest

from fakes import FlatTerrain, RibbonOps
from pypcg import geo, stage_api
from pypcg.checks import s18 as K
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import assets as AS
from pypcg.geo import distance as D
from pypcg.geo import ground as G
from pypcg.stages import s13_leftover_trees as T13
from pypcg.stages import s18_outer_forest as S
from pypcg.stages import s18_outer_forest_trees as T

REPO = stage_api.REPO
TEXTURE = "/Game/Textures/Noise/T_CloudNoise_4k.T_CloudNoise_4k"


def official_ir():
    with open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_5_2_OuterForest.json"), encoding="utf-8") as fh:
        return json.load(fh)


def official(name):
    return next(n for n in official_ir()["nodes"] if n["name"] == name)


def fixture():
    with open(os.path.join(REPO, "Tools", "pypcg", "data", "s18_fixture.json"), encoding="utf-8") as fh:
        return json.load(fh)


class Ops(RibbonOps):
    """Box booleans plus `assets` (one static-mesh entry per path, as `pypcg.ue.assets` loads a mesh)."""

    def assets(self, paths):
        out = []
        for p in paths:
            pts = Points()
            pts.declare(AS.MESH_ATTR, "SoftObjectPath")
            pts.add((0.0, 0.0, 0.0), bounds_min=(-300.0, -300.0, 0.0), bounds_max=(300.0, 300.0, 2000.0),
                    **{AS.MESH_ATTR: p})
            b = AS.bounds_of(pts)
            out.append({"path": p, "points": pts, "bounds": b, "size": AS.size_of(b), "note": ""})
        return out


class SlopeTerrain:
    """A plane rising with x: z = (x - x0) / 100, so the west is under water and the east on land."""

    def __init__(self, x0=0.0):
        self.x0 = x0

    def height(self, x, y):
        return (x - self.x0) / 100.0


def box(x0, y0, x1, y1, z=0.0):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [], z)


def terrain_points(x0, y0, x1, y1, z0=-500.0, z1=500.0):
    p = Points()
    for x, y, z in ((x0, y0, z0), (x1, y0, z1), (x1, y1, z1), (x0, y1, z0)):
        p.add((x, y, z), bounds_min=(-1.0, -1.0, -1.0), bounds_max=(1.0, 1.0, 1.0))
    return p


def first_inputs(half=60000.0, city=20000.0, park=None, highway=None, artery=3400.0):
    """A square terrain of side 2 x `half` with a square city in the middle; optional park and highway boxes."""
    c = Spline([(-city, -city, 0.0), (city, -city, 0.0), (city, city, 0.0), (-city, city, 0.0)], closed=True,
               linear=True)
    ins = {"MeshTerrain": [(terrain_points(-half, -half, half, half), frozenset())],
           "City": [(c, frozenset(["City"]))], "CentralParkFootprint": [], "Highways": [], "ArteryWidth": []}
    if park is not None:
        ins["CentralParkFootprint"] = [(Spline([(q[0], q[1], 0.0) for q in park.outer], closed=True, linear=True),
                                        frozenset())]
    if highway is not None:
        ins["Highways"] = [(highway, frozenset(["Highway"]))]
    if artery is not None:
        ins["ArteryWidth"] = [(geo.ParamSet({"ArteryWidth": artery}, {"ArteryWidth": "Double"}), frozenset())]
    return ins


def params(module, **kw):
    p = stage_api.defaults(module)
    p.update(kw)
    return p


def run1(ins, **kw):
    out, ctx = stage_api.execute(S, ins, params(S, **kw), Ops())
    return out, ctx


def forest_points(sets, index=None):
    """The texture writes' output as the second node sees it: `$Scale` (s, s, s) and a Double `index`."""
    out = []
    rng = random.Random(3)
    for s in sets:
        p = Points()
        p.declare("index", "Double")
        for j in range(len(s)):
            sc = 0.6 + 1.4 * rng.random()
            p.add(s.loc[j], scale=(sc, sc, sc), bounds_min=s.bounds_min[j], bounds_max=s.bounds_max[j],
                  steepness=1.0, seed=s.seed[j], index=1.0 + 8.0 * rng.random() if index is None else index)
        out.append((p, frozenset(["ForestPoints"])))
    return out


# ---- contract -------------------------------------------------------------------------------------------------
def _graph():
    from pypcg import graphs, ir
    from pypcg.profiles import official as prof
    doc = graphs.graph(18).to_ir(prof)                    # raises on an unwired Python input pin
    by = {x["name"]: x for x in doc["nodes"]}
    py = {x["title"]: x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE}
    return doc, by, py


def _feeds(node, by):
    return {p["label"]: [(by[e[0]], e[1]) for e in p["edges"]] for p in node["inputs"]}


def _users(doc, name):
    return [(n, p["label"], e[1]) for n in doc["nodes"] for p in n["inputs"] for e in p["edges"] if e[0] == name]


def _param(name):
    return next(p for p in official_ir()["params"] if p["name"] == name)


def test_contract_parameters():
    names = {p["name"] for p in official_ir()["params"]}
    assert names == {"TreeDensity", "ScaleMin", "ScaleMax", "CityEdgeBuffer", "ParkBuffer", "Partitioned",
                     "PartitionGridSize", "UseMegaPlantsTrees"}
    for module, name in ((S, "TreeDensity"), (S, "CityEdgeBuffer"), (S, "ParkBuffer"), (T, "UseMegaPlantsTrees")):
        p = module.PARAMS[name]
        assert (p.type, p.default) == (_param(name)["type"], _param(name)["value"]), name
    assert list(S.PARAMS) == ["TreeDensity", "CityEdgeBuffer", "ParkBuffer"] and list(T.PARAMS) == ["UseMegaPlantsTrees"]
    doc, _by, _py = _graph()
    got = [(p["name"], p["type"], p["value"]) for p in doc["params"]]
    assert got[0][0] == stage_api.SEED
    want = [(n, _param(n)["type"], _param(n)["value"]) for n in ("TreeDensity", "CityEdgeBuffer", "ParkBuffer",
                                                                  "UseMegaPlantsTrees", "ScaleMin", "ScaleMax")]
    assert got[1:] == want


def test_contract_reads_spawner_and_texture_writes_as_officially_set():
    doc, _by, _py = _graph()
    from pypcg import dsl
    from pypcg.profiles import official as prof

    def key(n):
        ov = dict(n.get("overrides") or {})
        return (n.get("subgraph"), json.dumps(ov, sort_keys=True), n.get("title") or "")
    for name in ("GetMeshTerrain_0", "Subgraph_7", "Subgraph_6", "Subgraph_16", "Subgraph_0", "Subgraph_4",
                 "Subgraph_13", "Subgraph_12", "Subgraph_2", "SpawnForest_0"):
        n = json.loads(json.dumps(official(name)))
        if "ActorReferences" in (n.get("overrides") or {}):
            n["overrides"]["ActorReferences"] = [prof.ROLES[r] for r in dsl.roles_of(n["overrides"]["ActorReferences"])]
        assert key(n) in [key(x) for x in doc["nodes"] if x["class"] == "PCGSubgraphSettings"], name
    for name in ("FilterDataByTag_0", "ExtractAttributeAtIndex_0", "CreateConstant_3"):
        o = official(name)
        x = next(x for x in doc["nodes"] if x.get("title") == o["title"])
        assert x["class"] == o["class"]
        assert {k: v for k, v in x["settings"].items() if k != "Seed"} == {k: v for k, v in o["settings"].items()
                                                                          if k != "Seed"}, name
    for name in ("Subgraph_12", "Subgraph_2"):                       # the SHIPPED graph reads the official texture
        x = next(x for x in doc["nodes"] if x.get("title") == official(name)["title"])
        assert x["overrides"]["Texture"] == TEXTURE


def test_contract_python_inputs_and_outputs_are_wired():
    doc, by, py = _graph()
    assert set(py) == {"Python: s18_outer_forest", "Python: s18_outer_forest_trees"}
    a, b = py["Python: s18_outer_forest"], py["Python: s18_outer_forest_trees"]
    fa = _feeds(a, by)
    for pin, name in (("MeshTerrain", "Subgraph_7"), ("City", "Subgraph_6"), ("CentralParkFootprint", "Subgraph_16"),
                      ("Highways", "Subgraph_0"), ("ArteryWidth", "ExtractAttributeAtIndex_0")):
        assert [n["title"] for n, _p in fa[pin]] == [official(name)["title"]], pin
    (extract, _p), = fa["ArteryWidth"]
    (tag, pin), = _feeds(extract, by)["In"]
    assert tag["title"] == official("FilterDataByTag_0")["title"] and pin == "InsideFilter"
    assert [n["title"] for n, _p in _feeds(tag, by)["In"]] == [official("Subgraph_4")["title"]]
    (terrain, _p), = _feeds(fa["MeshTerrain"][0][0], by)["PrimaryInput"]
    assert terrain["title"] == official("GetMeshTerrain_0")["title"]
    fb = _feeds(b, by)
    assert [n["title"] for n, _p in fb["MeshTerrain"]] == [official("GetMeshTerrain_0")["title"]]
    (species, _p), = fb["ForestPoints"]
    assert species["title"] == official("Subgraph_2")["title"]
    fs = _feeds(species, by)
    (scale, _p), = fs["PrimaryInput"]
    assert scale["title"] == official("Subgraph_12")["title"]
    assert [n["title"] for n, _p in fs["RemapValueOutHigh"]] == [official("CreateConstant_3")["title"]]
    fsc = _feeds(scale, by)
    assert [(n["title"], p) for n, p in fsc["PrimaryInput"]] == [("Python: s18_outer_forest", "ForestPoints")]
    assert [p for _n, p in fsc["RemapValueOutLow"]] == ["ScaleMin"] and [p for _n, p in fsc["RemapValueOutHigh"]] == ["ScaleMax"]
    spawn = next(n for n in doc["nodes"] if n.get("title") == official("SpawnForest_0")["title"])
    assert [(n["title"], p) for n, p in _feeds(spawn, by)["PrimaryInput"]] == [("Python: s18_outer_forest_trees", "Trees")]
    layout = next(n for n in doc["nodes"] if n.get("title") == official("Subgraph_13")["title"])
    assert not _users(doc, layout["name"]) and not any(e for nn in official_ir()["nodes"] for p in nn["inputs"]
                                                       for e in p["edges"] if e[0] == "Subgraph_13")


def test_contract_publishes_nothing():
    doc, _by, _py = _graph()
    out = next(n for n in doc["nodes"] if n["name"] == "DefaultOutputNode")
    assert all(not p["edges"] for p in out["inputs"])
    assert all(not p["edges"] for p in official("DefaultOutputNode")["inputs"])


def _const(name):
    t = official(name)["settings"]["AttributeTypes"]
    return t[t["Type"] + "Value"]


def test_contract_constants_are_the_official_ones():
    from pypcg.geo.frames import f32
    assert T.INDEX_JITTER == f32(_const("CreateConstant_2")) and T.SHORE_NOISE == f32(_const("CreateConstant_0"))
    assert T.DEEP_NOISE == f32(_const("CreateConstant_1")) and T.INDEX_OUT_MAX == _const("CreateConstant_3") + 1.0
    assert "AttributeTypes" not in official("AttributeFilter_0")["settings"] and T.WATER_LEVEL_CM == 0.0
    assert _const("AttributeFilter_2") == T.SHORE_KEEP and _const("AttributeFilter_3") == T.CUT_Z_CM
    assert official("AttributeRemap_0")["settings"]["OutRangeMin"] == T.SCALE_FLOOR
    for node, mx, remap in (("Subgraph_11", T.SHORE_MAX_CM, T.SHORE_REMAP), ("Subgraph_14", T.DEEP_MAX_CM, T.DEEP_REMAP)):
        ov = official(node)["overrides"]
        assert (ov["MaximumDistance"], (ov["RemapOutputMin"], ov["RemapOutputMax"])) == (mx, remap)
        assert ov["ComputeIn2D"] and ov["Normalized"] and ov["UseRemap"]
    assert official("Subgraph_3")["overrides"]["Expand"] == S.CITY_EXPAND_DEFAULT_CM
    assert official("Subgraph_2")["overrides"]["Attribute"] == T.INDEX_ATTR
    # the two assignments are stage 13's two calls (reused, not copied)
    for node, paths, settings in (("Subgraph_15", T13.FOREST, T13.FOREST_SETTINGS), ("Subgraph_18", T13.MEGA,
                                                                                     T13.MEGA_SETTINGS)):
        ov = official(node)["overrides"]
        assert tuple(ov["Assets"]) == paths
        assert ov["UseIndexattribute"] and ov["IndexAttribute"] == settings["index_attribute"]
        assert ov["RandomRotationRange"] == settings["random_rotation_range"]
        assert ov["RandomScaleRange"] == settings["random_scale_range"]
        assert ov.get("ScaleOffset") == settings.get("scale_offset")


# ---- empty inputs ----------------------------------------------------------------------------------------------
def test_empty_inputs_first_node():
    out, ctx = stage_api.execute(S, {pin: [] for pin in S.INPUTS}, params(S), Ops())
    assert out == {"ForestPoints": []}
    assert any("no terrain points" in n for n in ctx.notes)


def test_empty_inputs_second_node():
    out, ctx = stage_api.execute(T, {pin: [] for pin in T.INPUTS}, params(T), Ops())
    assert out == {"Trees": []}


def test_empty_terrain_places_nothing_even_with_a_city():
    ins = first_inputs()
    ins["MeshTerrain"] = []
    out, _ctx = run1(ins)
    assert out["ForestPoints"] == []


def test_missing_texture_output_places_nothing():
    """On the demo level the texture writes output nothing (trap 66): the second node gets an empty pin."""
    out, ctx = stage_api.execute(T, {"ForestPoints": [], "MeshTerrain": [(FlatTerrain(10.0), frozenset())]},
                                 params(T), Ops())
    assert out["Trees"] == [] and ctx.notes == ["trees: no points after the texture writes"]


# ---- the footprint and the scatter against the official taps ---------------------------------------------------
def _fixture_terrain(fx):
    f = fx["footprint"]["points"]
    p = Points()
    for c in ("loc", "rot", "scale", "bounds_min", "bounds_max"):
        setattr(p, c, [tuple(x) for x in f[c]])
    n = len(p.loc)
    for c in ("density", "color", "steepness", "seed"):
        setattr(p, c, [Points.DEFAULTS[c]] * n)
    p.quat = [tuple(q) for q in f["quat"]]
    return p


def test_footprint_is_the_official_one_bit_for_bit():
    fx = fixture()
    fp = S.footprint([_fixture_terrain(fx)])
    corners = fx["footprint"]["corners"]
    xs, ys = sorted({c[0] for c in corners}), sorted({c[1] for c in corners})
    assert fp == (xs[0], ys[0], xs[1], ys[1], corners[0][2])
    assert fp[4] == fx["footprint"]["bounds"]["loc"][0][2]


def test_footprint_uses_each_points_own_rotated_box():
    p = Points()
    p.add((0.0, 0.0, 0.0), bounds_min=(-1.0, -1.0, -1.0), bounds_max=(1.0, 1.0, 1.0))
    p.add((100.0, 50.0, 10.0), rot=(0.0, 45.0, 0.0), bounds_min=(-1.0, -1.0, -1.0), bounds_max=(1.0, 1.0, 1.0))
    x0, y0, x1, y1, z = S.footprint([p])
    assert (x0, y0) == (-1.0, -1.0) and abs(x1 - (100.0 + math.sqrt(2.0))) < 1e-12 and abs(y1 - (50.0 + math.sqrt(2.0))) < 1e-12
    assert z == 5.0
    assert S.footprint([]) is None and S.footprint([Points()]) is None


def test_city_buffer_is_half_the_artery_plus_the_edge_buffer_or_the_nodes_own_3400():
    fx = fixture()["areas"]
    assert S.city_buffer(fx["artery"], params(S)) == fx["city_expand"] == 1800.0
    assert S.city_buffer(None, params(S)) == 3400.0


def test_fill_random_banded_equals_the_full_containment_test():
    """`geo.ground.fill_random` tests each point only against its row's edges; the result must be the full
    `geo.plane.inside` test's, point for point, holes included."""
    ring = [(0.0, 0.0), (9000.0, 300.0), (12000.0, 7000.0), (4000.0, 11000.0), (-2000.0, 6000.0)]
    hole = [(3000.0, 3000.0), (3000.0, 6000.0), (7000.0, 6000.0), (7000.0, 3000.0)]
    poly = Polygon(ring, [hole], 12.5)
    got = G.fill_random(poly, 0.05, random.Random(11))
    rng = random.Random(11)
    cell = math.sqrt(1e4 / 0.05)
    want = []
    for j in range(math.ceil(0.0 / cell), math.floor(11000.0 / cell) + 1):
        for i in range(math.ceil(-2000.0 / cell), math.floor(12000.0 / cell) + 1):
            x, y = i * cell + rng.random() * (cell - 2.0), j * cell + rng.random() * (cell - 2.0)
            if geo.inside((x, y), ring) and not geo.inside((x, y), hole):
                want.append((x, y, 12.5))
    assert got == want and len(got) > 300


def test_scatter_matches_density_times_the_official_area():
    """The official scatter is TreeDensity x area to 0.04 % (one point per grid cell): s18.md 5.3."""
    fx = fixture()["areas"]
    got = sum(fx["scatter"])
    want = sum(fx["official_m2"]) * fx["tree_density"]
    assert abs(got - want) <= 0.01 * want
    assert abs(got - want) / want < 5e-4


# ---- the task's invariants (corrected) with planted faults -----------------------------------------------------
def _scatter_case(**kw):
    park = box(30000.0, 30000.0, 40000.0, 40000.0)
    highway = box(-60000.0, -50000.0, 60000.0, -45000.0, 800.0)
    ins = first_inputs(park=park, highway=highway, **kw)
    out, ctx = run1(ins, TreeDensity=0.02)
    src = S.read(ins)
    fp = S.footprint(src["terrain"])
    areas, city, grown_park = S.forest_areas(fp, src, params(S, TreeDensity=0.02), Ops())
    sets = [v for v, _t in out["ForestPoints"]]
    return fp, areas, city, grown_park, src, sets, ins, out, ctx


def test_no_scattered_point_in_the_city_the_park_or_the_highway():
    fp, areas, city, park, src, sets, _ins, _out, _ctx = _scatter_case()
    assert sum(len(s) for s in sets) > 1000
    assert K.check_scatter(fp, areas, city, park, src["highway"], sets, params(S, TreeDensity=0.02)) == []
    # the grown city is the city plus 1 800 cm, the park plus 1 900
    (cx0, cy0), (cx1, cy1) = geo.bbox(city[0].outer)                  # grown in the outline's own frame
    assert max(abs(cx0 + 21800.0), abs(cy0 + 21800.0), abs(cx1 - 21800.0), abs(cy1 - 21800.0)) < 1e-9
    assert geo.bbox(park[0].outer) == ((28100.0, 28100.0), (41900.0, 41900.0))
    for s in sets:
        assert all(not (-21800.0 < p[0] < 21800.0 and -21800.0 < p[1] < 21800.0) for p in s.loc)


@pytest.mark.parametrize("fault", ["in_city", "in_park", "in_highway", "outside", "height", "count", "box"])
def test_scatter_checks_catch_planted_faults(fault):
    fp, areas, city, park, src, sets, _ins, _out, _ctx = _scatter_case()
    s = sets[0]
    z = fp[4]
    if fault == "in_city":
        s.loc[0] = (0.0, 0.0, z)
    elif fault == "in_park":
        s.loc[0] = (35000.0, 35000.0, z)
    elif fault == "in_highway":
        s.loc[0] = (0.0, -47000.0, z)
    elif fault == "outside":
        s.loc[0] = (fp[2] + 10.0, 0.0, z)
    elif fault == "height":
        s.loc[0] = (s.loc[0][0], s.loc[0][1], z + 1.0)
    elif fault == "box":
        s.bounds_max[0] = (20.0, 10.0, 10.0)
    elif fault == "count":
        big = max(sets, key=len)
        for k in range(len(big.loc) // 2):
            big.loc.pop()
            big.bounds_min.pop()
            big.bounds_max.pop()
    assert K.check_scatter(fp, areas, city, park, src["highway"], sets, params(S, TreeDensity=0.02))


def test_v1_partial_replay_reproduces_the_run_and_catches_a_changed_record():
    _fp, _a, _c, _p, _s, _sets, ins, out, ctx = _scatter_case()
    rec = {"stage": 18, "params": params(S, TreeDensity=0.02), "notes": list(ctx.notes),
           "inputs": {pin: [[geo.to_json(v), sorted(t)] for v, t in items] for pin, items in ins.items()},
           "outputs": {pin: [[geo.to_json(v), list(t)] for v, t in items] for pin, items in out.items()}}
    rec = json.loads(json.dumps(rec))
    assert K.check_record(rec, Ops()) == []
    bad = json.loads(json.dumps(rec))
    bad["params"]["Seed"] = 43                                            # a different stream: other points
    assert K.check_record(bad, Ops())
    bad = json.loads(json.dumps(rec))
    bad["outputs"]["ForestPoints"][0][0]["loc"][3][0] += 0.5
    assert K.check_record(bad, Ops())
    bad = json.loads(json.dumps(rec))
    bad["notes"] = [n for n in bad["notes"] if not n.startswith("footprint")]
    assert K.check_record(bad, Ops()) == ["the run noted no footprint"]


def test_v1_reads_a_truncated_record_by_size_and_bounds():
    _fp, _a, _c, _p, _s, _sets, ins, out, ctx = _scatter_case()
    rec = {"stage": 18, "params": params(S, TreeDensity=0.02), "notes": list(ctx.notes),
           "inputs": {pin: [[geo.to_json(v), sorted(t)] for v, t in items] for pin, items in ins.items()},
           "outputs": {"ForestPoints": []}}
    for v, t in out["ForestPoints"]:
        xs, ys, zs = zip(*v.loc)
        rec["outputs"]["ForestPoints"].append([{"kind": "points", "n": len(v), "types": {}, "truncated": True,
                                                "bbox": [[min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)]]},
                                               list(t)])
    rec = json.loads(json.dumps(rec))
    assert K.check_record(rec, Ops()) == []
    rec["outputs"]["ForestPoints"][1][0]["n"] += 1
    assert K.check_record(rec, Ops())


# ---- the second node against the official taps (the substitute-texture oracle) --------------------------------
def test_index_jitter_stays_within_half_a_species():
    sets = [p for p, _t in forest_points([Points()])]
    pts = Points()
    pts.declare("index", "Double")
    for k in range(2000):
        pts.add((k, 0.0, 0.0), index=4.0)
    T.jitter_index([pts], random.Random(1))
    d = [v - 4.0 for v in pts.attrs["index"]]
    assert -0.5 <= min(d) < -0.49 and 0.49 < max(d) <= 0.5
    lo, hi = fixture()["index"]["jitter_range"]
    assert -0.5 <= lo and hi <= 0.5
    assert sets[0].attrs == {"index": []}


def test_index_normalisation_is_the_official_one_bit_for_bit():
    fx = fixture()["index"]
    # the fixture's points span the official min and max only together with the rest: plant the extremes
    pts = Points()
    pts.declare("index", "Double")
    for v in [fx["min"], fx["max"]] + [b for _si, b, _a in fx["points"]]:
        pts.add((0.0, 0.0, 0.0), index=v)
    assert T.normalise_index([pts]) == (fx["min"], fx["max"])
    assert pts.attrs["index"][2:] == [a for _si, _b, a in fx["points"]]
    assert pts.attrs["index"][:2] == [0.0, 10.0]


def test_water_split_is_strictly_above_zero():
    fx = fixture()["water"]
    pts = Points()
    for loc, _above in fx["points"]:
        pts.add(tuple(loc))
    (above, below), = T.split_water([pts])
    assert [j in above for j in range(len(pts))] == [a for _l, a in fx["points"]]
    assert set(above) | set(below) == set(range(len(pts))) and not set(above) & set(below)
    edge = Points()
    edge.add((0.0, 0.0, 0.0))
    edge.add((0.0, 0.0, 1e-9))
    assert T.split_water([edge]) == [([1], [0])]


@pytest.mark.parametrize("which,remap", [("shore", T.SHORE_REMAP), ("deep", T.DEEP_REMAP)])
def test_distance_weights_are_the_official_ones_bit_for_bit(which, remap):
    fx = fixture()[which]
    reach = T.SHORE_MAX_CM if which == "shore" else T.DEEP_MAX_CM
    targets = [D.target_centre(t["loc"], t["scale"], t["bounds_min"], t["bounds_max"]) for t in fx["targets"]]
    near = D.Nearest2D(targets, reach)
    lo, hi = fx["raw_range"]
    raw = [near.distance(s["loc"][0], s["loc"][1]) / reach for s in fx["sources"]]
    got = D.remap(raw, lo, hi, *remap)
    assert got == [s["value"] for s in fx["sources"]]
    assert len({round(v, 3) for v in got}) > 20                          # the window has real gradients
    # the targets' own locations instead of their box centres are NOT always the official bits (s18.md 6)
    assert fx["official_min"] == 0.0 and fx["official_max"] == 1.0


def test_distance_without_targets_is_the_maximum_and_a_point_range_remaps_to_the_middle():
    vals = D.distance_from([[(0.0, 0.0), (5.0, 5.0)]], [], 5000.0, 1.0, 0.0)
    assert vals == [[0.5, 0.5]]
    assert D.Nearest2D([], 100.0).distance(0.0, 0.0) == 100.0
    assert D.Nearest2D([(30.0, 40.0)], 100.0).distance(0.0, 0.0) == 50.0
    assert D.Nearest2D([(100.0, 0.0)], 100.0).distance(0.0, 0.0) == 100.0        # not strictly inside the reach
    with pytest.raises(ValueError):
        D.Nearest2D([], 100.0, cell=50.0)


def test_target_centre_is_the_box_centre_round_trip():
    c = D.target_centre((1.1, 2.2, 3.3), (1.4698423602466122,) * 3, (-10.0,) * 3, (10.0,) * 3)
    e = 10.0 * 1.4698423602466122
    assert c == (((1.1 - e) + (1.1 + e)) * 0.5, ((2.2 - e) + (2.2 + e)) * 0.5)
    r = D.target_centre((0.0, 0.0, 0.0), (1.0,) * 3, (0.0, 0.0, 0.0), (20.0, 0.0, 0.0), AS.quat_of(0.0, 90.0, 0.0))
    assert abs(r[0]) < 1e-9 and abs(r[1] - 10.0) < 1e-9


def test_scale_floor_and_scale_are_the_official_ones_bit_for_bit():
    from pypcg.geo.frames import f32
    slope = (1.0 - T.SCALE_FLOOR) / (1.0 - 0.0)
    for before, after, scale, scaled in fixture()["floor"]:
        assert f32(slope * (before - 0.0) + T.SCALE_FLOOR) == after
        assert [c * after for c in scale] == scaled


def test_species_picks_are_the_official_ones():
    fx = fixture()["assign"]
    pts = Points()
    pts.declare("index", "Double")
    for v, _a in fx["points"]:
        pts.add((0.0, 0.0, 0.0), index=v)
    picks = AS.index_picks(pts, T13.FOREST_SETTINGS["index_attribute"], len(T13.FOREST))
    assert [T13.FOREST[k] for k in picks] == [a for _v, a in fx["points"]]
    assert any(v >= 8.0 for v, _a in fx["points"])                       # unmatched indices take entry 0
    lo, hi = K.scale_bounds({"ScaleMin": _param("ScaleMin")["value"], "ScaleMax": _param("ScaleMax")["value"]}, False)
    assert lo <= fx["scale_range"][0] and fx["scale_range"][1] <= hi and fx["pitch_roll_max"] <= 2.0


# ---- the second node end to end, with planted faults ------------------------------------------------------------
def _trees_case(seed=42, mega=False):
    """The first node's scatter on a terrain sloping out of the sea (west under water), then the second node."""
    ins = first_inputs(half=30000.0, city=5000.0)
    out, _ctx = run1(ins, TreeDensity=0.01, Seed=seed)
    sets = [v for v, _t in out["ForestPoints"]]
    surface = SlopeTerrain(x0=0.0)
    p = params(T, Seed=seed, UseMegaPlantsTrees=mega)
    res, ctx = stage_api.execute(T, {"ForestPoints": forest_points(sets), "MeshTerrain": [(surface, frozenset())]},
                                 p, Ops())
    return res, ctx, surface, sets


def test_trees_stand_on_the_terrain_near_the_shore_and_inside_the_scale_bound():
    res, ctx, surface, sets = _trees_case()
    (trees, tags), = res["Trees"]
    assert tags == ["Trees"] and len(trees) > 100
    p = {"ScaleMin": _param("ScaleMin")["value"], "ScaleMax": _param("ScaleMax")["value"]}
    assert K.check_trees(trees, p, surface) == []
    assert all(t[2] == surface.height(t[0], t[1]) for t in trees.loc)        # z is the terrain height, exactly
    # the sea is the west: no tree farther than 50 m + the noise's reach out from the shore line x = 0
    assert min(t[0] for t in trees.loc) > -6000.0
    assert all(t[2] > T.CUT_Z_CM for t in trees.loc)
    assert "index range" in ctx.notes[0] and "near the shore" in ctx.notes[0]


@pytest.mark.parametrize("fault", ["asset", "scale", "tilt", "low", "terrain"])
def test_tree_checks_catch_planted_faults(fault):
    res, _ctx, surface, _sets = _trees_case()
    trees = res["Trees"][0][0]
    p = {"ScaleMin": _param("ScaleMin")["value"], "ScaleMax": _param("ScaleMax")["value"]}
    if fault == "asset":
        trees.attrs["Asset"][0] = T13.MEGA[0]
    elif fault == "scale":
        trees.scale[0] = (2.0, 2.0, 2.0)
    elif fault == "tilt":
        trees.rot[0] = (3.0, 0.0, 0.0)
    elif fault == "low":
        trees.loc[0] = (trees.loc[0][0], trees.loc[0][1], -500.0)
    elif fault == "terrain":
        trees.loc[0] = (trees.loc[0][0], trees.loc[0][1], trees.loc[0][2] + 6.0)
    assert K.check_trees(trees, p, surface)


def test_megaplants_switch():
    res, _ctx, surface, _sets = _trees_case(mega=True)
    trees = res["Trees"][0][0]
    assert set(trees.attrs["Asset"]) <= set(T13.MEGA)
    p = {"ScaleMin": _param("ScaleMin")["value"], "ScaleMax": _param("ScaleMax")["value"]}
    assert K.check_trees(trees, p, surface, mega=True) == []


def test_without_land_no_tree_survives_the_shore_filter():
    """No point above water: every shore weight is the remap's middle, 0.5 +- 0.3 never passes 0.8."""
    ins = first_inputs(half=20000.0, city=3000.0)
    out, _ctx = run1(ins, TreeDensity=0.01)
    sea = FlatTerrain(-100.0)
    res, ctx = stage_api.execute(T, {"ForestPoints": forest_points([v for v, _t in out["ForestPoints"]]),
                                     "MeshTerrain": [(sea, frozenset())]}, params(T), Ops())
    assert res["Trees"] == [] or len(res["Trees"][-1][0]) == 0
    assert "near the shore 0" in ctx.notes[0]


# ---- seeds -------------------------------------------------------------------------------------------------------
def _dump(out):
    return json.dumps({pin: [[geo.to_json(v), list(t)] for v, t in items] for pin, items in out.items()}, sort_keys=True)


def test_seeded_runs_repeat_and_differ():
    assert S.RANDOM and T.RANDOM
    ins = first_inputs(half=30000.0, city=5000.0)
    a, _ = run1(ins, TreeDensity=0.01, Seed=5)
    b, _ = run1(ins, TreeDensity=0.01, Seed=5)
    c, _ = run1(ins, TreeDensity=0.01, Seed=6)
    assert _dump(a) == _dump(b) and _dump(a) != _dump(c)
    ta, _c1, _s1, _x1 = _trees_case(seed=9)
    tb, _c2, _s2, _x2 = _trees_case(seed=9)
    tc, _c3, _s3, _x3 = _trees_case(seed=10)
    assert _dump(ta) == _dump(tb) and _dump(ta) != _dump(tc)


def test_merge_targets_keeps_rotations_unless_upright_and_adds_the_data_index_to_the_seed():
    a, b = Points(), Points()
    a.add((0.0, 0.0, 0.0), rot=(1.0, 2.0, 3.0), seed=10)
    b.add((1.0, 0.0, 0.0), rot=(4.0, 5.0, 6.0), seed=2 ** 31 - 1)
    m = AS.merge_targets([(a, ()), (b, ()), ("not points", ())])
    assert m.rot == [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)] and m.seed == [10, -2 ** 31] and m.quat is None
    u = AS.merge_targets([(a, ()), (b, ())], upright=True)
    assert u.rot == [(0.0, 2.0, 0.0), (0.0, 5.0, 0.0)]
    assert T13.upright([(a, ()), (b, ())]).rot == u.rot
