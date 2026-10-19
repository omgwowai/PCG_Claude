"""Stage 13, LeftOverLots (Task 18; spec 3, Step B).

The invariants are the task brief's:
  - the areas are inside their source lot and shrunk, never grown;
  - the plaza / tree split is on items and matches `Ratio_Plaza_vs_Trees` within 0.10;
  - tree points are on the terrain within 5 cm (when a terrain input exists);
  - the node TITLED "Only unbuildable lots" (`Subgraph_36`) filters `LargeBuildingSkirt`: the skirt areas are
    the ones fitted, not the unbuildable lots;
  - the official graph publishes only the plaza lots its second draw did not keep (`Reroute_4`);
  - empty inputs -> every output empty, on all three Python nodes.

Offline the booleans are `fakes.RibbonOps` (axis-aligned boxes; the in-frame setback turns a box by 90 deg,
which keeps it a box), so the fixture is a field of box lots."""
import json
import math
import os
import random

import pytest

from fakes import FlatTerrain, RibbonOps
from pypcg import geo, stage_api
from pypcg.checks import s13 as C
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import assets as AS
from pypcg.geo import ground as G
from pypcg.stages import s13_leftover_lots as S
from pypcg.stages import s13_leftover_plazas as P
from pypcg.stages import s13_leftover_trees as T

REPO = stage_api.REPO


def official_ir():
    with open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_2_2_LeftOverLots.json"), encoding="utf-8") as fh:
        return json.load(fh)


def official(name):
    return next(n for n in official_ir()["nodes"] if n["name"] == name)


class MeshOps(RibbonOps):
    """`ctx.ops.assets` offline: every path is a 300 x 300 x 20 cm static mesh."""

    def assets(self, paths):
        out = []
        for path in paths:
            pts = Points()
            pts.declare("Mesh", "SoftObjectPath")
            b = ((0.0, 0.0, -20.0), (300.0, 300.0, 0.0))
            pts.add((0.0, 0.0, 0.0), bounds_min=b[0], bounds_max=b[1], Mesh=path)
            out.append({"path": path, "points": pts, "bounds": b, "size": AS.size_of(b), "note": ""})
        return out


OPS = MeshOps()


def box(x0, y0, x1, y1, z=0.0):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [], z)


def closed(p):
    return Spline([(x, y, 0.0) for x, y in p.outer], closed=True, polyline=[(x, y, 0.0) for x, y in p.outer])


def reserved_lots(n, size=3000.0, gap=1000.0):
    return [box(i * (size + gap), 0.0, i * (size + gap) + size, size) for i in range(n)]


RESERVED = reserved_lots(12)
UNBUILDABLE = [box(0, 10000, 2000, 12000), box(3000, 10000, 4000, 11000)]
SKIRT = [box(10000, 10000, 12000, 11000), box(13000, 10000, 15000, 11000)]
UNDER = [box(20000, 10000, 26000, 14000)]
SMALL_YARDS = [box(30000, 10000, 34000, 14000)]
MEDIUM_YARDS = [box(40000, 10000, 46000, 16000)]
UNDIVIDABLE = box(0, 20000, 10000, 30000)
ROAD = box(-1000, 18000, 60000, 19000)
HIGHWAY = box(5000, 25000, 7000, 40000)
TOWER = box(8000, 22000, 9000, 23000)
PARK = box(-5000, 20000, -1000, 25000)
SMALL_PARK = box(50000, 0, 52000, 2000)


def lots_items(reserved=RESERVED):
    items = [(box(-2000, -2000, 60000, 18000), frozenset({"Lots"}))]
    items += [(p, frozenset({"reservedLots"})) for p in reserved]
    items += [(UNBUILDABLE[0], frozenset({"unbuildableLots"})), (UNBUILDABLE[1], frozenset({"UnbuildableFootprints"}))]
    items += [(p, frozenset({"LargeBuildingSkirt"})) for p in SKIRT]
    items += [(p, frozenset({"UnderHighway"})) for p in UNDER]
    items += [(p, frozenset({"Small Courtyards"})) for p in SMALL_YARDS]
    items += [(p, frozenset({"Medium Courtyards"})) for p in MEDIUM_YARDS]
    return items


def inputs(**over):
    ins = {"Lots": lots_items(),
           "Districts": [(UNDIVIDABLE, frozenset({"UndividableDistricts"})), (box(0, 0, 9e4, 9e4), frozenset({"SmallDistricts"}))],
           "Roads": [(ROAD, frozenset({"RoadFootprints"})), (Spline([(0, 0, 0), (100, 0, 0)]), frozenset({"Roads"}))],
           "Highways": [(HIGHWAY, frozenset({"Highway"}))],
           "MainTower": [(TOWER, frozenset())],
           "CentralParkFootprint": [(PARK, frozenset())],
           "LandmarkPark": [(closed(SMALL_PARK), frozenset({"LandmarkPark"}))],
           "MeshTerrain": [(FlatTerrain(25.0), frozenset())]}
    ins.update(over)
    return ins


def params(**kw):
    p = dict(stage_api.defaults(S))
    p.update(kw)
    return p


def run(ins=None, seed=42, ops=OPS, **kw):
    out, _ctx = stage_api.execute(S, inputs() if ins is None else ins, dict(params(**kw), Seed=seed), ops)
    return out


def values(out, pin):
    return [v for v, _t in out[pin]]


# ---- contract ---------------------------------------------------------------------------------------
def test_contract_parameters_are_the_official_kept_ones():
    off = {p["name"]: p for p in official_ir()["params"]}
    assert set(off) == {"Ratio_Plaza_vs_Trees", "Partitioned", "PartitionGridSize", "UseMegaplantsTrees"}
    assert S.PARAMS["Ratio_Plaza_vs_Trees"].default == off["Ratio_Plaza_vs_Trees"]["value"] == 0.5
    assert S.PARAMS["Ratio_Plaza_vs_Trees"].type == off["Ratio_Plaza_vs_Trees"]["type"] == "Double"
    for m in (T, P):
        assert m.PARAMS["UseMegaplantsTrees"].default is off["UseMegaplantsTrees"]["value"] is False
        assert m.PARAMS["UseMegaplantsTrees"].type == "Bool"
    from pypcg import graphs
    from pypcg.profiles import official as prof
    names = [p["name"] for p in graphs.graph(13).to_ir(prof)["params"]]
    assert names == [stage_api.SEED, "Ratio_Plaza_vs_Trees", "UseMegaplantsTrees"]      # Partitioned* dropped


def _graph():
    from pypcg import graphs, ir
    from pypcg.profiles import official as prof
    doc = graphs.graph(13).to_ir(prof)                 # raises on an unwired Python input pin
    by = {x["name"]: x for x in doc["nodes"]}
    py = {x["title"]: x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE}
    return doc, by, py


def _feeds(node, by):
    return {p["label"]: [by[e[0]] for e in p["edges"]] for p in node["inputs"]}


def test_contract_scene_reads_feed_the_python_nodes_by_name():
    _doc, by, py = _graph()
    assert set(py) == {"Python: s13_leftover_lots", "Python: s13_leftover_trees", "Python: s13_leftover_plazas"}
    feeds = _feeds(py["Python: s13_leftover_lots"], by)
    assert set(S.INPUTS) | {stage_api.PARAMS_PIN} == set(feeds)
    titles = {"Lots": "Get Lots", "Districts": "Get Districts", "Roads": "Get Roads", "Highways": "Get Highway",
              "MainTower": "Get Landmark", "CentralParkFootprint": "Central Park", "LandmarkPark": "Landmark Small Park"}
    for pin, title in titles.items():
        assert [x["title"] for x in feeds[pin]] == [title], pin
    terrain = feeds["MeshTerrain"]
    assert [x["subgraph"].rsplit("/", 1)[-1] for x in terrain] == ["Get_MeshTerrain.Get_MeshTerrain"]
    assert terrain[0]["overrides"]["MeshPartitionQueryType"] == "Final"
    pf = _feeds(py["Python: s13_leftover_plazas"], by)
    assert [x["title"] for x in pf["Highways"]] == ["Get Highway"]
    assert [x["title"] for x in pf["Plazas"]] == [official(n)["title"] for n in
                                                  ("Subgraph_2", "Subgraph_23", "Subgraph_31", "Subgraph_53", "Subgraph_38")]
    tf = _feeds(py["Python: s13_leftover_trees"], by)
    assert [x["title"] for x in tf["TreePoints"]] == ["Write Tree Species Index From Noise Texture"]


def test_contract_every_output_pin_is_wired_as_officially():
    doc, by, py = _graph()
    edges = {(e[0], e[1], x["name"], p["label"]) for x in doc["nodes"] for p in x["inputs"] for e in p["edges"]}
    lots = py["Python: s13_leftover_lots"]["name"]
    out = [x for x in doc["nodes"] if x["name"] == "DefaultOutputNode"][0]
    assert [e for p in out["inputs"] for e in p["edges"]] == [[lots, "PlazaLots"]]      # only Reroute_4's lots
    targets = {"ReservedPlazaAreas": "Fill Reserved Lots with Medium Plazas",
               "MediumCourtyardAreas": "Fill Medium Courtyards with Large Plazas",
               "SmallCourtyardAreas": "Fill Small Courtyards with Small Plazas",
               "UnderHighwayAreas": "Fill Under- Highway Lots with Storage Plazas",
               "SkirtAreas": "Fill Building skirt With Small Plazas", "GroundTiles": "Spawn ground tiles",
               "TreePoints": "Write Tree Scale From Noise Texture"}
    for pin, title in targets.items():
        hits = [by[t]["title"] for s, sp, t, _l in edges if s == lots and sp == pin]
        assert hits == [title], pin
    trees, plazas = py["Python: s13_leftover_trees"]["name"], py["Python: s13_leftover_plazas"]["name"]
    assert [by[t]["title"] for s, sp, t, _l in edges if s == trees] == ["Spawn Outer Forest Trees"]
    assert [by[t]["title"] for s, sp, t, _l in edges if s == plazas] == ["Spawn Plaza"]


def test_contract_fixed_settings_are_the_official_overrides():
    assert official("Subgraph_10")["overrides"]["RandomPerDataset"] is True
    assert official("Subgraph_0")["overrides"] == {"Ratio": S.PLAZA_CULL_RATIO}
    for name in ("Subgraph_13", "Subgraph_52", "Subgraph_30", "Subgraph_21"):
        assert official(name)["overrides"] == {"Contract": S.PLAZA_SETBACK_CM, "UnionBeforeOutputting": False}
    for name in ("Subgraph_9", "Subgraph_54", "Subgraph_32", "Subgraph_25", "Subgraph_37"):
        assert official(name)["overrides"]["offset"]["Z"] == S.PLAZA_LIFT_CM
    assert official("Subgraph_48")["overrides"]["offset"]["Z"] == S.TILE_LIFT_CM
    assert official("Subgraph_34")["overrides"]["PointExtents"] == S.TILE_EXTENT_CM
    assert official("Subgraph_1")["overrides"]["PointsPerSquaredMeter"] == S.TREES_PER_M2
    assert [official("Subgraph_%d" % k)["overrides"]["Ratio"] for k in range(59, 65)] == list(S.TILE_RATIOS)
    for k, (letter, path) in zip(range(65, 72), S.TILE_CALLS):
        ov = official("Subgraph_%d" % k)["overrides"]
        assert ov["Assets"] == [path] and ov["PositionOffset"] == {"X": -150, "Y": -150, "Z": 0}
    gather = [e[0] for p in official("Gather_1")["inputs"] for e in p["edges"]]
    assert gather == ["Subgraph_%d" % k for k in range(65, 72)]
    assert official("Subgraph_36")["title"] == "Only unbuildable lots"
    assert official("Subgraph_36")["overrides"]["FilteredInputTags"] == "LargeBuildingSkirt"
    assert official("Subgraph_5")["overrides"]["FilteredInputTags"] == "unbuildableLots, UnbuildableFootprints"
    assert S.READS["skirt"] == ("LargeBuildingSkirt",)
    assert S.READS["unbuildable"] == ("unbuildableLots", "UnbuildableFootprints")


def test_contract_tree_calls_are_the_official_ones():
    for name, paths, settings in (("Subgraph_26", T.FOREST, T.FOREST_SETTINGS), ("Subgraph_14", T.MEGA, T.MEGA_SETTINGS),
                                  ("Subgraph_73", P.TREES, P.TREES_SETTINGS), ("Subgraph_12", P.MEGA, P.MEGA_SETTINGS)):
        ov = dict(official(name)["overrides"])
        assert ov.pop("Assets") == list(paths), name
        keys = {"IndexAttribute": "index_attribute", "UseIndexattribute": "use_index_attribute",
                "RandomRotationRange": "random_rotation_range", "RandomScaleRange": "random_scale_range",
                "ScaleOffset": "scale_offset", "ExtentsScale": "extents_scale"}
        assert {keys[k]: v for k, v in ov.items()} == settings, name
    for name, word in (("AttributeFilter_0", "Tree_Birch"), ("AttributeFilter_1", "plane"), ("AttributeFilter_2", "sidewalk"),
                       ("AttributeFilter_4", "border"), ("AttributeFilter_5", "cone")):
        s = official(name)["settings"]
        assert s["Operator"] == "Substring" and s["AttributeTypes"]["StringValue"] == word
        assert word.lower() in (P.BIRCH, P.PLANE) + P.KEPT_AS_IS
    assert official("Subgraph_55")["overrides"]["PointExtents"] == P.HIGHWAY_TILE_EXTENT_CM


# ---- empty inputs (Review Focus 1) ---------------------------------------------------------------------
def test_empty_inputs_main_node():
    out = run({pin: [] for pin in S.INPUTS})
    assert all(out[pin] == [] for pin in S.OUTPUTS)


def test_empty_inputs_trees_and_plazas_nodes():
    for m in (T, P):
        out, _ctx = stage_api.execute(m, {pin: [] for pin in m.INPUTS}, dict(stage_api.defaults(m)), OPS)
        assert all(out[pin] == [] for pin in m.OUTPUTS)


def test_no_terrain_places_no_tiles_and_no_trees():
    out = run(inputs(MeshTerrain=[]))
    assert out["GroundTiles"] == [] and out["TreePoints"] == []
    assert values(out, "SkirtAreas")


# ---- invariants ----------------------------------------------------------------------------------------
def test_setback_areas_are_inside_their_source_and_smaller():
    out = run()
    for pin, sources in (("UnderHighwayAreas", UNDER), ("SmallCourtyardAreas", SMALL_YARDS),
                         ("MediumCourtyardAreas", MEDIUM_YARDS), ("ReservedPlazaAreas", RESERVED)):
        areas = values(out, pin)
        if pin != "ReservedPlazaAreas":
            assert len(areas) == len(sources), pin
        for a in areas:
            own = [s for s in sources if C._inside(a, s)]
            assert own, pin
            assert geo.area_m2(a) < geo.area_m2(own[0]), pin
            assert a.z == own[0].z + S.PLAZA_LIFT_CM
            (x0, y0), (x1, y1) = geo.bbox(a.outer)
            (s0, t0), (s1, t1) = geo.bbox(own[0].outer)
            assert x0 == pytest.approx(s0 + S.PLAZA_SETBACK_CM) and x1 == pytest.approx(s1 - S.PLAZA_SETBACK_CM)
    assert C.check(inputs(), params(), out, OPS) == []


def test_skirt_areas_are_the_large_building_skirt_not_the_unbuildable_lots():
    """`Subgraph_36` is titled "Only unbuildable lots" but filters `LargeBuildingSkirt`."""
    out = run()
    skirt = values(out, "SkirtAreas")
    assert [p.outer for p in skirt] == [p.outer for p in SKIRT]
    assert all(p.z == S.PLAZA_LIFT_CM for p in skirt)
    assert not any(p.outer == u.outer for p in skirt for u in UNBUILDABLE)
    bad = dict(out, SkirtAreas=[(S.lift(u, S.PLAZA_LIFT_CM), ["SkirtAreas"]) for u in UNBUILDABLE])
    assert any("skirt" in f for f in C.check(inputs(), params(), bad, OPS))


def test_split_is_on_items_and_matches_the_ratio():
    lots = reserved_lots(400, size=1500.0, gap=200.0)
    ins = inputs(Lots=lots_items(lots), MeshTerrain=[])
    for ratio in (0.5, 0.2, 0.8):
        shares = []
        for seed in range(5):
            kept, published, trees = S.split(S.read(ins), {"Ratio_Plaza_vs_Trees": ratio}, S.Draws(random.Random(seed)))
            assert sorted(map(id, kept + published + trees)) == sorted(map(id, S.read(ins)["reserved"])) or \
                len(kept) + len(published) + len(trees) == len(lots)
            shares.append((len(kept) + len(published)) / float(len(lots)))
        assert abs(sum(shares) / len(shares) - ratio) <= 0.10, ratio


def test_published_are_the_plaza_lots_the_cull_did_not_keep():
    out = run(seed=3)
    published = values(out, "PlazaLots")
    assert all(any(p.outer == r.outer and p.z == r.z for r in RESERVED) for p in published)
    src = S.read(inputs())
    kept, pub, trees = S.split(src, params(), S.Draws(stage_api.Ctx(13, 3, OPS).rng))
    assert [p.outer for p in published] == [p.outer for p in pub]
    assert all(t for _p, t in out["PlazaLots"])
    assert len(values(out, "ReservedPlazaAreas")) == len(kept)


def test_tree_points_lie_on_the_terrain():
    out = run()
    pts = values(out, "TreePoints")
    assert pts and sum(len(p) for p in pts) > 10
    for p in pts:
        assert all(abs(q[2] - 25.0) <= C.ON_SURFACE_CM for q in p.loc)


def test_tree_areas_exclude_the_highway_and_include_the_small_park():
    src = S.read(inputs())
    areas = S.tree_areas(src, [], OPS)
    for a in areas:
        (x0, y0), (x1, y1) = geo.bbox(a.outer)
        assert x1 <= 5000 or x0 >= 7000 or y1 <= 25000 or y0 >= 40000          # outside the highway box
    assert any(geo.bbox(a.outer) == geo.bbox(SMALL_PARK.outer) for a in areas)
    assert all(a.z == 0.0 for a in areas if geo.bbox(a.outer) == geo.bbox(SMALL_PARK.outer))


def test_ground_tiles_one_plaza_mesh_per_set():
    out = run()
    for pts, tags in out["GroundTiles"]:
        letter = [t for t in tags if t.startswith("SM_Plaza_Square_")][0][-1]
        assert set(pts.attrs["Asset"]) == {S._MESH % (letter, letter)}
        # on the flat terrain, the +15 cm lift kept (the projector adds the stored z back)
        assert all(abs(q[2] - (25.0 + S.TILE_LIFT_CM)) < 1e-9 for q in pts.loc)


def test_seeded_runs_repeat_and_differ():
    a = [[geo.to_json(v), list(t)] for pin in S.OUTPUTS for v, t in run(seed=1)[pin]]
    b = [[geo.to_json(v), list(t)] for pin in S.OUTPUTS for v, t in run(seed=1)[pin]]
    c = [[geo.to_json(v), list(t)] for pin in S.OUTPUTS for v, t in run(seed=2)[pin]]
    assert a == b
    assert a != c


def test_check_record_replays_a_record():
    out, ctx = stage_api.execute(S, inputs(), dict(params(), Seed=5), OPS)
    rec = {"params": dict(params(), Seed=5),
           "inputs": {pin: [[geo.to_json(v), sorted(t)] for v, t in items] for pin, items in inputs().items()},
           "outputs": {pin: [[geo.to_json(v), list(t)] for v, t in items] for pin, items in out.items()}}
    assert C.check_record(rec, OPS) == []
    rec["outputs"]["PlazaLots"] = rec["outputs"]["PlazaLots"][1:] if rec["outputs"]["PlazaLots"] else \
        [[geo.to_json(RESERVED[0]), ["reservedLots"]]]
    assert any("PlazaLots" in f for f in C.check_record(rec, OPS))


# ---- the shared helpers ----------------------------------------------------------------------------------
def test_fill_random_follows_the_sampler_grid():
    p = box(0, 0, 100000, 100000)
    locs = G.fill_random(p, 0.02, random.Random(1))
    cell = math.sqrt(1e4 / 0.02)
    assert abs(len(locs) - (100000 / cell) ** 2) <= 2 * (100000 / cell) + 2
    assert all(geo.inside(q[:2], p.outer) for q in locs)
    assert G.fill_random(p, 0.0, random.Random(1)) == []


def test_project_point_miss_keeps_the_point_and_doubles_z():
    class Nowhere:
        def height(self, x, y):
            return None
    loc, rot, hit = G.project_point((10.0, 20.0, 842.0), (0.0, 30.0, 0.0), (-1, -1, -1), (1, 1, 1), Nowhere())
    assert not hit and loc == (10.0, 20.0, 1684.0) and rot == (0.0, 30.0, 0.0)


def test_project_tile_places_the_corners_with_the_point_scale():
    class Slope:
        def height(self, x, y):
            return 0.1 * x
    one = G.project_tile((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (-10, -10, -10), (10, 10, 10), Slope())
    two = G.project_tile((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (-10, -10, -10), (10, 10, 10), Slope(), scale=(2.0, 2.0, 2.0))
    assert one[1] == pytest.approx(two[1])          # a plane: the tilt does not depend on the corner spread
    class Bump:
        def height(self, x, y):
            return 0.0 if x < 15.0 else 100.0
    flat = G.project_tile((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (-10, -10, -10), (10, 10, 10), Bump())
    wide = G.project_tile((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (-10, -10, -10), (10, 10, 10), Bump(), scale=(2.0, 1.0, 1.0))
    assert flat[1][0] == pytest.approx(0.0) and abs(wide[1][0]) > 1.0      # scale 2 reaches the bump


def test_difference_binary_removes_only_what_a_live_tile_overlaps():
    q = (0.0, 0.0, 0.0, 1.0)
    tiles = [((0.0, 0.0, 0.0), q, (1.0, 1.0, 1.0), (-300, -300, -300), (300, 300, 300), 1.0),
             ((5000.0, 0.0, 0.0), q, (1.0, 1.0, 1.0), (-300, -300, -300), (300, 300, 300), 0.0)]
    src = [((100.0, 0.0, 0.0), q, (1.0, 1.0, 1.0), (-50, -50, 0), (50, 50, 500), 1.0),       # under the live tile
           ((5000.0, 0.0, 0.0), q, (1.0, 1.0, 1.0), (-50, -50, 0), (50, 50, 500), 1.0),     # under the dead tile
           ((1000.0, 0.0, 0.0), q, (1.0, 1.0, 1.0), (-50, -50, 0), (50, 50, 500), 1.0),     # clear
           ((320.0, 0.0, 0.0), q, (1.0, 1.0, 1.0), (-50, -50, 0), (50, 50, 500), 1.0)]      # overlaps the edge
    assert G.difference_binary(src, tiles) == [1, 2]
    touching = [((350.0, 0.0, 0.0), q, (1.0, 1.0, 1.0), (-50, -50, 0), (50, 50, 500), 1.0)]
    assert G.volume_overlap(tiles[0][:5], ((400.0, 0.0, 0.0),) + touching[0][1:5]) == 0.0


def test_split_ways_matches_stage_10s_chain():
    from pypcg.stages import s10_ground as S10
    assert G.split_ways(50, S10.SPLIT_RATIOS, random.Random(7)) == S10.split_seven(50, random.Random(7))


# ---- the plaza node ---------------------------------------------------------------------------------------
def _kit(assets, z=0.0, scale=1.0):
    pts = Points()
    pts.declare("Asset", "SoftObjectPath")
    for i, a in enumerate(assets):
        pts.add((100.0 * i, 0.0, z), rot=(5.0, 10.0 * i, 3.0), scale=(scale, scale, scale),
                bounds_min=(-20, -20, 0), bounds_max=(20, 20, 50), Asset=a)
    return pts


class Slope:
    def height(self, x, y):
        return 10.0 + 0.2 * y


def test_plazas_split_drop_and_keep_by_asset_name():
    kit = _kit(["/G/SM_Tree_Birch_a.SM_Tree_Birch_a", "/G/Airplane_Prop.Airplane_Prop", "/G/SM_Sidewalk_A.SM_Sidewalk_A",
                "/G/Border_B.Border_B", "/G/SM_Cone_C.SM_Cone_C", "/G/SM_Bench.SM_Bench"])
    proj = P.project(kit, Slope())
    birch, rest, side, border, cone = P.split(proj)
    assert (birch, rest, side, border, cone) == ([0], [5], [2], [3], [4])     # the plane prop is dropped
    pts, _notes = P.plazas([kit], [], Slope(), False, random.Random(1), OPS.assets)
    names = [str(a).rsplit("/", 1)[-1] for p in pts for a in p.attrs["Asset"]]
    assert "Airplane_Prop.Airplane_Prop" not in names and "SM_Tree_Birch_a.SM_Tree_Birch_a" not in names
    rest_pts = pts[0]
    assert rest_pts.rot[0][0] == 0.0 and rest_pts.rot[0][2] == 0.0          # upright
    side_pts = pts[1]
    assert abs(side_pts.rot[0][0]) + abs(side_pts.rot[0][2]) > 1.0          # kept as projected (tilted)
    assert sum(1 for n in names if "BlackAlder" in n) == 1                    # the birch re-assigned
    assert all(abs(q[2] - (10.0 + 0.2 * q[1])) < 1e-9 for p in pts[:-1] for q in p.loc)


def test_plazas_birch_under_a_highway_tile_is_removed():
    kit = _kit(["/G/SM_Tree_Birch_a.SM_Tree_Birch_a"])
    hw = [box(-1000, -1000, 1000, 1000)]
    pts, notes = P.plazas([kit], hw, FlatTerrain(0.0), False, random.Random(1), OPS.assets)
    assert pts == [] and "0 left" in notes[0]
    far = [box(50000, 50000, 52000, 52000)]
    pts, _ = P.plazas([kit], far, FlatTerrain(0.0), True, random.Random(1), OPS.assets)
    assert [str(a) for a in pts[-1].attrs["Asset"]][0] in P.MEGA            # UseMegaplantsTrees -> Subgraph_12


# ---- the trees node -----------------------------------------------------------------------------------------
def test_trees_upright_and_assigned_by_texture_index():
    pts = Points()
    pts.declare("index", "Double")
    for i, v in enumerate([0.5, 3.2, 8.4, 7.9]):
        pts.add((100.0 * i, 0.0, 0.0), rot=(4.0, 20.0, -3.0), index=v)
    ins = {"TreePoints": [(pts, frozenset())]}
    out, _ctx = stage_api.execute(T, ins, dict(stage_api.defaults(T)), OPS)
    trees = values(out, "Trees")[-1]
    assert [str(a) for a in trees.attrs["Asset"]] == [T.FOREST[0], T.FOREST[3], T.FOREST[0], T.FOREST[7]]
    assert all(abs(r[0]) <= 2.0 + 1e-6 and abs(r[2]) <= 2.0 + 1e-6 for r in trees.rot)     # upright +- the range
    out, _ctx = stage_api.execute(T, ins, dict(stage_api.defaults(T), UseMegaplantsTrees=True), OPS)
    assert str(values(out, "Trees")[-1].attrs["Asset"][1]) == T.MEGA[3]
