"""Stage 16, CentralParkVisuals (Task 22; spec 3, Step B).

The contract against the official IR (parameters, the scene reads, the 13 kept generation nodes, the native
lake-bed / grass / post-grammar nodes, no published output), empty inputs on both Python nodes, the geometry
against the official taps (`Tools/pypcg/data/s16_fixture.json`, distilled by `Tools/pypcg/s16_fixture.py`), the
task's invariants as `pypcg.checks.s16` states them (with planted faults), and the seeded repeat / differ of the
vegetation node. Offline there is no engine boolean, so the polygon booleans are covered live by V1's partial
replay (`checks.s16.check`); here they are either not needed or stood in by `PassOps`.
"""
import json
import math
import os
import random

import pytest

from fakes import FlatTerrain
from pypcg import geo, stage_api
from pypcg.checks import s16 as K
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import assets as AS
from pypcg.geo import curves as C
from pypcg.stages import s16_central_park_visuals as S
from pypcg.stages import s16_park_geometry as G

REPO = stage_api.REPO
GENERATION = {"Spawn_Border_Road", "Spawn_Transverse_Roads", "Spawn_Intersections", "Subgraph_5", "Subgraph_14",
              "Subgraph_19", "Spawn_Met_Building", "Met_Rooftop_Mesh", "Met_Rooftops", "Lake_Mesh", "Subgraph_53",
              "Subgraph_6", "Subgraph_66"}
READS = {"Get_Footprint_Actor", "Get_Drawn_Splines", "Get_Lake", "Get_Forest_Exclusion", "Subgraph_1", "Subgraph_50",
         "Subgraph_51", "Subgraph_52", "Subgraph_57"}


def official_ir():
    with open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_4_2_CentralPark_Visuals.json"),
              encoding="utf-8") as fh:
        return json.load(fh)


def official(name):
    return next(n for n in official_ir()["nodes"] if n["name"] == name)


def fixture():
    with open(os.path.join(REPO, "Tools", "pypcg", "data", "s16_fixture.json"), encoding="utf-8") as fh:
        return json.load(fh)


def spline(d):
    return geo.from_json({k: v for k, v in d.items() if k in ("kind", "points", "closed", "linear", "tangents",
                                                              "polyline", "frame")})


class PassOps:
    """No engine booleans: an offset/difference/union that hands the subject back (enough for the Met's
    exclusion polygon and for empty clip sets), plus `assets` (one static-mesh entry per path)."""

    def offset(self, rings, distance, join="square", miter_limit=2.0):
        return [Polygon(list(rings[0]))]

    def difference(self, rings_a, rings_b):
        return [Polygon(list(rings_a[0]))]

    def union(self, rings):
        return [Polygon(list(r)) for r in rings]

    def path_offset(self, path, distance, end="butt", join="square", miter_limit=2.0):
        return []

    def assets(self, paths):
        out = []
        for p in paths:
            pts = Points()
            pts.declare(AS.MESH_ATTR, "SoftObjectPath")
            pts.add((0.0, 0.0, 0.0), bounds_min=(-100.0, -100.0, 0.0), bounds_max=(100.0, 100.0, 1000.0),
                    **{AS.MESH_ATTR: p})
            b = AS.bounds_of(pts)
            out.append({"path": p, "points": pts, "bounds": b, "size": AS.size_of(b), "note": ""})
        return out


class TapTerrain:
    """Heights by XY lookup from tapped points (a vertical-ray stand-in that reproduces the official samples)."""

    def __init__(self, points):
        self.z = {(round(p[0], 6), round(p[1], 6)): p[2] for p in points}

    def height(self, x, y):
        return self.z.get((round(x, 6), round(y, 6)))


def _close(a, b, tol):
    return all(max(abs(p[k] - q[k]) for k in range(len(q))) <= tol for p, q in zip(a, b)) and len(a) == len(b)


# ---- contract -------------------------------------------------------------------------------------------------
def _graph():
    from pypcg import graphs, ir
    from pypcg.profiles import official as prof
    doc = graphs.graph(16).to_ir(prof)                    # raises on an unwired Python input pin
    by = {x["name"]: x for x in doc["nodes"]}
    py = {x["title"]: x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE}
    return doc, by, py


def _feeds(node, by):
    return {p["label"]: [(by[e[0]], e[1]) for e in p["edges"]] for p in node["inputs"]}


def _users(doc, name):
    return [(n, p["label"], e[1]) for n in doc["nodes"] for p in n["inputs"] for e in p["edges"] if e[0] == name]


def test_contract_parameters():
    assert {p["name"] for p in official_ir()["params"]} == {"Partitioned", "PartitionGridSize", "UseMegaplantsTrees"}
    assert list(S.PARAMS) == ["UseMegaplantsTrees"] and S.PARAMS["UseMegaplantsTrees"].default is False
    assert G.PARAMS == {}
    doc, _by, _py = _graph()
    assert [p["name"] for p in doc["params"]] == [stage_api.SEED, "UseMegaplantsTrees"]


def test_contract_keeps_the_13_generation_nodes_and_the_reads_as_officially_set():
    doc, _by, _py = _graph()
    from pypcg import dsl
    from pypcg.profiles import official as prof

    def key(n):
        ov = dict(n.get("overrides") or {})
        return (n.get("subgraph"), json.dumps(ov, sort_keys=True), n.get("title") or "",
                (n.get("settings") or {}).get("bEnabled", True))
    want = []
    for name in sorted(GENERATION | READS):
        n = json.loads(json.dumps(official(name)))
        if "ActorReferences" in (n.get("overrides") or {}):
            n["overrides"]["ActorReferences"] = [prof.ROLES[r] for r in dsl.roles_of(n["overrides"]["ActorReferences"])]
        want.append(key(n))
    have = [key(n) for n in doc["nodes"] if n["class"] == "PCGSubgraphSettings"]
    for k in want:
        assert k in have, k
    transverse = next(n for n in doc["nodes"] if n.get("title") == official("Spawn_Transverse_Roads")["title"])
    assert transverse["settings"].get("bEnabled") is False and all(not p["edges"] for p in transverse["inputs"])
    roads = next(n for n in doc["nodes"] if n.get("title") == official("Subgraph_52")["title"])
    assert not _users(doc, roads["name"])                          # read and unused, as officially


def test_contract_publishes_nothing():
    doc, _by, _py = _graph()
    out = next(n for n in doc["nodes"] if n["name"] == "DefaultOutputNode")
    assert all(not p["edges"] for p in out["inputs"])
    assert all(not p["edges"] for p in official("DefaultOutputNode")["inputs"])


def test_contract_python_inputs_and_outputs_are_wired():
    doc, by, py = _graph()
    assert set(py) == {"Python: s16_central_park_visuals", "Python: s16_park_geometry"}
    geo_node, veg = py["Python: s16_park_geometry"], py["Python: s16_central_park_visuals"]
    feeds = _feeds(geo_node, by)
    for pin, name in (("Footprint", "Get_Footprint_Actor"), ("DrawnSplines", "Get_Drawn_Splines"), ("Lake", "Get_Lake"),
                      ("ForestExclusion", "Get_Forest_Exclusion"), ("MeshTerrain", "Subgraph_1")):
        assert [n["title"] for n, _p in feeds[pin]] == [official(name)["title"]], pin
    vf = _feeds(veg, by)
    assert [(n["title"], p) for n, p in vf["RoadFootprints"]] == [(official("Spawn_Border_Road")["title"], "Footprints")]
    assert [(n["title"], p) for n, p in vf["MetRoofs"]] == [(official("Spawn_Met_Building")["title"], "Rooftops Footprints")]
    assert [p for _n, p in vf["ParkAreas"]] == ["ParkAreas"] and [p for _n, p in vf["Exclusions"]] == ["Exclusions"]
    for node, module in ((geo_node, G), (veg, S)):
        for pin in module.OUTPUTS:
            assert any(e[0] == node["name"] and e[1] == pin for n in doc["nodes"] for p in n["inputs"] for e in p["edges"]), pin
    # the lake writer: the terrain points onto the Python lake bed (native Subgraph_55), then Write_MeshTerrain
    writer = next(n for n in doc["nodes"] if n.get("title") == official("Subgraph_53")["title"])
    (proj, _pin), = _feeds(writer, by)["PrimaryInput"]
    pf = _feeds(proj, by)
    assert proj["title"] == official("Subgraph_55")["title"]
    assert [(n["title"], p) for n, p in pf["SecondaryInput"]] == [("Python: s16_park_geometry", "LakeBed")]
    assert [n["title"] for n, _p in pf["PrimaryInput"]] == [official("Subgraph_51")["title"]]


def test_contract_the_spawner_reads_what_gather_3_gathered():
    doc, by, _py = _graph()
    spawn = next(n for n in doc["nodes"] if n.get("title") == official("Subgraph_6")["title"])
    srcs = [(n.get("subgraph") or n["class"], n["title"], p) for n, p in _feeds(spawn, by)["PrimaryInput"]]

    def off(name, pin):
        n = official(name)
        return (n.get("subgraph") or n["class"], n.get("title", ""), pin)
    py = (dsl_python_class(), "Python: s16_central_park_visuals", "Trees")
    # Gather_3's order: Sidewalks (Gather_2: the transparent copies, the vehicles, the rest), lake edges, trees,
    # wild grass (Gather_1: dense, sparse), zone grass, walkpath, road
    assert srcs == [off("AttributeCast_0", "Out"), off("FilterDataByAttribute_5", "InsideFilter"),
                    off("FilterDataByAttribute_5", "OutsideFilter"), off("Subgraph_46", "Out"), py,
                    off("Subgraph_63", "Out"), off("Subgraph_64", "Out"), off("Subgraph_65", "Out"),
                    off("Subgraph_42", "Out"), off("Subgraph_48", "Out")]


def dsl_python_class():
    from pypcg import ir
    return ir.PYTHON_NODE


# ---- empty inputs ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("module", [G, S])
def test_empty_inputs_give_no_outputs(module):
    params = {stage_api.SEED: 42}
    params.update({k: v.default for k, v in module.PARAMS.items()})
    out, _ctx = stage_api.execute(module, {pin: [] for pin in module.INPUTS}, params, PassOps())
    assert all(not items for items in out.values())


def test_empty_park_with_everything_else_present_gives_no_outputs():
    fx = fixture()
    inputs = {"Footprint": [], "DrawnSplines": [(spline(d), frozenset()) for d in fx["drawn"]],
              "Lake": [(spline(d), frozenset()) for d in fx["lakes"]], "MeshTerrain": [(FlatTerrain(0.0), frozenset())],
              "ForestExclusion": [(spline(d), frozenset()) for d in fx["forest_exclusion"]]}
    out, _ctx = stage_api.execute(G, inputs, {stage_api.SEED: 42}, PassOps())
    assert all(not items for items in out.values())


# ---- the geometry against the taps ------------------------------------------------------------------------------
def test_centre_and_lines_match_the_taps():
    """The centre's rotator is the polygon point's at its first longest edge (yaw 34.22265945387145); the
    engine's own `FRotator::Quaternion` of it is the tapped quaternion bit for bit (probed live); offline the
    Python sin/cos is used, so the lines are within 1.5e-11 cm."""
    fx = fixture()
    loc, q = G.centre(spline(fx["footprint"]))
    assert list(loc) == fx["centre"]["loc"]
    assert max(abs(a - b) for a, b in zip(q, fx["centre"]["quat"])) <= 1e-15
    for got, want in zip(G.lines(loc, q), fx["lines"]):
        assert _close(got, want, 2e-11)
    # with the engine's quaternion (what ops.rotator_quat returns live) two lines are bit for bit
    exact = G.lines(loc, tuple(fx["centre"]["quat"]))
    assert [tuple(p) for p in exact[0]] == [tuple(p) for p in fx["lines"][0]]


def test_tied_longest_edge_takes_the_first():
    """A rectangle's opposite edges tie; the strict rule on Python's bits turned the park 180 degrees."""
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0)]
    assert G.first_longest(ring) == 0
    assert G.first_longest([(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (-1e-9, 4.0)]) == 0


def test_border_segments_are_one_per_control_point_edge():
    fx = fixture()
    polys = [geo.from_json(d) for d in fx["outlines"]]
    segs = G.edge_segments(polys)
    assert len(segs) == len(fx["border_segments"]) == 28
    assert all(_close([p[:2] for p in a], [p[:2] for p in b], 1e-10) for a, b in zip(segs, fx["border_segments"]))


def test_met_footprint_and_its_rotations_match_the_taps():
    fx = fixture()
    loc, _q = G.centre(spline(fx["footprint"]))
    q = tuple(fx["centre"]["quat"])
    (building, rotations), grown, rect = G.met(loc, q, TapTerrain(fx["met_projected"]), PassOps())
    assert [tuple(p) for p in rect] == [tuple(p) for p in fx["met_shape"]]
    assert [tuple(p) for p in building] == [tuple(p) for p in fx["met_spline"]["points"]]
    assert all(max(abs(a - b) for a, b in zip(r, w)) <= 1e-12 for r, w in zip(rotations, fx["met_spline"]["rotations"]))
    assert len(grown) == 1 and grown[0].z == 100.0


def test_lake_chain_matches_the_taps():
    fx = fixture()
    projected = [p for d in fx["lake_projected"] for p in d["points"]]
    terrain = TapTerrain(projected)
    for raw, edge, proj, level, bed in zip(fx["lakes"], fx["lake_edge"], fx["lake_projected"], fx["lake_level"],
                                           fx["lake_bed"]):
        e = G.lake_edge(spline(raw))
        assert _close(e.points, edge["points"], 1e-10)
        assert all(_close(a, b, 1e-6) for a, b in zip(e.tangents, edge["tangents"]))
        water, lake_bed = G.lake_levels(spline(raw), terrain)
        # the +20 offset runs in the lake's own (yawed) frame officially, in the world here: XY to 2e-11 cm
        assert _close(water.points, level["points"], 2e-11)
        assert all(_close([t[1]], [w[1]], 1e-9) for t, w in zip(water.tangents, proj["tangents"]))   # auto tangents
        # on the tapped projected points themselves the auto tangents are the engine's bit for bit
        assert [tuple(t) for t in C.auto_tangents(proj["points"], True)] == [tuple(t[1]) for t in proj["tangents"]]
        assert _close(lake_bed.points, bed["points"], 2e-11) and lake_bed.tangents is None
        assert [tuple(t) for t in C.auto_tangents(bed["points"], True)] == [tuple(t[1]) for t in bed["tangents"]]


def test_walkpaths_split_the_drawn_splines_like_the_taps():
    fx = fixture()
    drawn = [G.flattened(spline(d)) for d in fx["drawn"]]
    rings = [geo.from_json(d) for d in fx["contracted"]]
    walks = G.walkpaths(drawn, rings, None)
    assert len(walks) == len(fx["walk"]) == 10
    for got, want in zip(walks, fx["walk"]):
        assert len(got.points) == len(want["points"])
        assert _close(got.points, want["points"], 0.01)        # the engine's nearest key is a float


def test_curve_helpers_reverse_and_offset():
    fx = fixture()
    for lifted, edge in zip(fx["lake_lifted"], fx["lake_edge"]):
        p, t = C.reverse(lifted["points"], lifted["tangents"])
        assert [tuple(x) for x in p] == [tuple(x) for x in edge["points"]]
        assert [tuple(map(tuple, x)) for x in t] == [tuple(map(tuple, x)) for x in edge["tangents"]]
    bed = C.offset_points(fx["lake_level"][0]["points"], fx["lake_projected"][0]["tangents"], True, (0.0, 0.0, -50.0))[0]
    assert _close(bed, fx["lake_bed"][0]["points"], 2e-11)


# ---- invariants -----------------------------------------------------------------------------------------------
def test_invariant_lake_water_area_within_1_percent_of_the_lake_polygon():
    fx = fixture()
    terrain = TapTerrain([p for d in fx["lake_projected"] for p in d["points"]])
    for raw in fx["lakes"]:
        lk = spline(raw)
        water, _bed = G.lake_levels(lk, terrain)
        want = abs(geo.signed_area(K.ring_of(lk))) / 1e4
        assert abs(K.curve_area_m2(water) - want) <= 0.01 * want


def test_invariant_met_inside_the_park():
    """`G.met` itself (the tapped terrain samples under the corners), not the fixture's answer."""
    fx = fixture()
    loc, q = G.centre(spline(fx["footprint"]))
    (building, _rot), grown, _rect = G.met(loc, q, TapTerrain(fx["met_projected"]), PassOps())
    park = [tuple(p[:2]) for p in fx["footprint"]["points"]]
    assert len(building) == 4 and all(geo.inside(tuple(p[:2]), park) for p in building)
    assert all(geo.inside(tuple(p[:2]), park) for g in grown for p in g.outer)


def test_brief_invariant_correction_official_trees_stand_within_the_jitter():
    """The OFFICIAL trees break "no vegetation inside": 39 of 2 198 stand inside an exclusion / lake / Met / road
    footprint (9 in a lake), the deepest 175 cm -- inside the fill's 283 cm jitter reach, which the check uses."""
    t = fixture()["official_trees_inside"]
    assert t["inside"] > 0 and t["deepest_cm"] < K.JITTER_REACH_CM


def _veg_record(seed=42):
    areas = [Polygon([(0.0, 0.0), (20000.0, 0.0), (20000.0, 20000.0), (0.0, 20000.0)]),
             Polygon([(30000.0, 0.0), (50000.0, 0.0), (50000.0, 20000.0), (30000.0, 20000.0)])]
    roof = Spline([(0.0, 0.0, 3000.0), (100.0, 0.0, 3000.0), (100.0, 100.0, 3000.0)], closed=True, linear=True)
    inputs = {"ParkAreas": [(a, frozenset()) for a in areas], "Exclusions": [], "RoadFootprints": [],
              "MetRoofs": [(roof, frozenset())], "MeshTerrain": [(FlatTerrain(10.0), frozenset())]}
    out, _ctx = stage_api.execute(S, inputs, {stage_api.SEED: seed, "UseMegaplantsTrees": False}, PassOps())
    return inputs, out


def test_vegetation_passes_its_checks_and_planted_faults_fire():
    inputs, out = _veg_record()
    ins = {k: v for k, v in inputs.items() if k != "MeshTerrain"}
    params = {"UseMegaplantsTrees": False}
    assert K.check(ins, params, out, None) == []
    trees = out["Trees"][0][0]
    assert len(trees) > 0 and all(r[0] == 0.0 and r[2] == 0.0 for r in trees.rot)
    # a tree deep inside an exclusion polygon
    ins2 = dict(ins, Exclusions=[(Polygon([(5000.0, 5000.0), (15000.0, 5000.0), (15000.0, 15000.0), (5000.0, 15000.0)]),
                                  frozenset())])
    trees.loc[0] = (10000.0, 10000.0, trees.loc[0][2])
    assert any("deeper than" in x for x in K.check(ins2, params, out, None))
    # a tilted tree, a foreign asset, a tree far from its side's areas
    trees.rot[1] = (3.0, trees.rot[1][1], 0.0)
    trees.attrs["Asset"][2] = "/Game/Elsewhere.Elsewhere"
    trees.loc[3] = (90000.0, 90000.0, trees.loc[3][2])
    fails = " ".join(K.check(ins, params, out, None))
    assert "not upright" in fails and "outside their side's kit" in fails and "farther than" in fails


def test_lowered_met_roof_check_fires():
    inputs, out = _veg_record()
    ins = {k: v for k, v in inputs.items() if k != "MeshTerrain"}
    (low, _t), = out["MetRoofsLowered"]
    assert all(q[2] == p[2] - 10.0 for p, q in zip(inputs["MetRoofs"][0][0].points, low.points))
    low.points[0] = (low.points[0][0], low.points[0][1], low.points[0][2] - 5.0)
    assert any("10 cm lower" in x for x in K.check(ins, {"UseMegaplantsTrees": False}, out, None))


def test_geometry_checks_fire_on_a_moved_met_and_a_shrunk_lake():
    fx = fixture()
    terrain = TapTerrain([p for d in fx["lake_projected"] for p in d["points"]])
    water = [G.lake_levels(spline(raw), terrain)[0] for raw in fx["lakes"]]
    rec = {"inputs": {"Footprint": [[fx["footprint"], []]], "Lake": [[d, []] for d in fx["lakes"]]},
           "outputs": {"Lake": [[geo.to_json(w), []] for w in water],
                       "MetFootprint": [[geo.to_json(Spline([tuple(p) for p in fx["met_spline"]["points"]], closed=True)), []]]}}
    assert K.check_geometry(rec) == []
    moved = Spline([(p[0] + 200000.0, p[1], p[2]) for p in fx["met_spline"]["points"]], closed=True)
    rec["outputs"]["MetFootprint"] = [[geo.to_json(moved), []]]
    fails = " ".join(K.check_geometry(rec))
    assert "not inside the park" in fails and "over 1 %" not in fails
    rec["outputs"]["MetFootprint"] = []

    def scaled(w, area_factor):
        # points AND tangents scaled about the centroid: the enclosed area scales by area_factor exactly
        s_ = math.sqrt(area_factor)
        cx = sum(p[0] for p in w.points) / len(w.points)
        cy = sum(p[1] for p in w.points) / len(w.points)
        pts = [(cx + (p[0] - cx) * s_, cy + (p[1] - cy) * s_, p[2]) for p in w.points]
        tans = [(tuple(c * s_ for c in a), tuple(c * s_ for c in b)) for a, b in w.tangents]
        return Spline(pts, closed=True, linear=False, tangents=tans)
    rec["outputs"]["Lake"][0] = [geo.to_json(scaled(water[0], 0.995)), []]      # 0.5 % smaller: inside 1 %
    assert K.check_geometry(rec) == []
    rec["outputs"]["Lake"][0] = [geo.to_json(scaled(water[0], 0.982)), []]      # 1.8 % smaller: over it
    assert any("over 1 %" in x for x in K.check_geometry(rec))


class RectOps(PassOps):
    """Real booleans on AXIS-ALIGNED rectangles (what the planted-clip tests use): `offset` grows a rectangle's
    box, `difference` cuts the subject box by the clip boxes on their shared grid and returns the free cells
    merged per row -- exact areas, no Clipper."""

    @staticmethod
    def _box(r):
        xs, ys = [p[0] for p in r], [p[1] for p in r]
        return min(xs), min(ys), max(xs), max(ys)

    def offset(self, rings, distance, join="square", miter_limit=2.0):
        x0, y0, x1, y1 = self._box(rings[0])
        d = float(distance)
        return [Polygon([(x0 - d, y0 - d), (x1 + d, y0 - d), (x1 + d, y1 + d), (x0 - d, y1 + d)])]

    def difference(self, rings_a, rings_b):
        sx0, sy0, sx1, sy1 = self._box(rings_a[0])
        cuts = [self._box(r) for r in rings_b]
        xs = sorted({sx0, sx1} | {min(max(c[k], sx0), sx1) for c in cuts for k in (0, 2)})
        ys = sorted({sy0, sy1} | {min(max(c[k], sy0), sy1) for c in cuts for k in (1, 3)})
        out = []
        for j in range(len(ys) - 1):
            for i in range(len(xs) - 1):
                cx, cy = 0.5 * (xs[i] + xs[i + 1]), 0.5 * (ys[j] + ys[j + 1])
                if xs[i + 1] - xs[i] <= 0 or ys[j + 1] - ys[j] <= 0:
                    continue
                if any(c[0] < cx < c[2] and c[1] < cy < c[3] for c in cuts):
                    continue
                out.append(Polygon([(xs[i], ys[j]), (xs[i + 1], ys[j]), (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1])]))
        return out


def _clipped_record(seed=42, ops=None):
    """One 200 x 200 m area with a 20 m road footprint across its middle (y 9 000 .. 11 000): the stage grows
    it 8 m and cuts the area; the trees must keep off it."""
    area = Polygon([(0.0, 0.0), (20000.0, 0.0), (20000.0, 20000.0), (0.0, 20000.0)])
    road = Polygon([(-500.0, 9000.0), (20500.0, 9000.0), (20500.0, 11000.0), (-500.0, 11000.0)])
    inputs = {"ParkAreas": [(area, frozenset())], "Exclusions": [], "RoadFootprints": [(road, frozenset())],
              "MetRoofs": [], "MeshTerrain": [(FlatTerrain(10.0), frozenset())]}
    out, _ctx = stage_api.execute(S, inputs, {stage_api.SEED: seed, "UseMegaplantsTrees": False}, ops or RectOps())
    return {k: v for k, v in inputs.items() if k != "MeshTerrain"}, out


def test_trees_keep_off_a_real_road_clip_and_the_check_rebuilds_it_independently():
    ins, out = _clipped_record()
    params = {"UseMegaplantsTrees": False}
    assert K.check(ins, params, out, RectOps()) == []
    forest = [v for pin in ("Selected", "Unselected") for v, _t in out[pin]]
    assert abs(sum(geo.area_m2(p) for p in forest) - 200.0 * (200.0 - 36.0)) <= 1e-6      # 20 m + 2 x 8 m cut
    grown = Polygon([(-1300.0, 8200.0), (21300.0, 8200.0), (21300.0, 11800.0), (-1300.0, 11800.0)])
    trees = [p for v, _t in out["Trees"] for p in v.loc]
    assert trees and max(K.depth_inside(p[:2], grown) for p in trees) <= K.JITTER_REACH_CM
    # planted fault 1: a tree in the middle of the road
    out["Trees"][0][0].loc[0] = (10000.0, 10000.0, 10.0)
    assert any("deeper than" in x for x in K.check(ins, params, out, RectOps()))


def test_a_wrong_road_growth_in_the_stage_is_caught_by_the_check(monkeypatch):
    """The check grows the footprints by the OFFICIAL 800 cm itself: a stage that grew them 425 (the node's
    title) hands it areas that do not partition its rebuild."""
    monkeypatch.setattr(S, "ROAD_EXPAND_CM", 425.0)
    ins, out = _clipped_record()
    assert any("does not partition" in x for x in K.check(ins, {"UseMegaplantsTrees": False}, out, RectOps()))


def test_a_dropped_clip_set_in_the_stage_is_caught_by_the_check(monkeypatch):
    monkeypatch.setattr(S, "road_footprints", lambda polys, ops: [])
    ins, out = _clipped_record()
    assert any("does not partition" in x for x in K.check(ins, {"UseMegaplantsTrees": False}, out, RectOps()))


# ---- randomness -------------------------------------------------------------------------------------------------
def test_seeded_runs_repeat_and_differ():
    def snap(out):
        return [[geo.to_json(v), t] for pin in S.OUTPUTS for v, t in out.get(pin, [])]
    a, b, c = _veg_record(42)[1], _veg_record(42)[1], _veg_record(7)[1]
    assert snap(a) == snap(b)
    assert snap(a) != snap(c)


def test_split_is_one_bernoulli_per_area():
    rng = random.Random(1)
    areas = [Polygon([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]) for _ in range(400)]
    sel, uns = S.split(areas, rng)
    assert len(sel) + len(uns) == 400 and 160 <= len(sel) <= 240


def test_tree_density_follows_the_sampler_grid_and_the_noise():
    """0.05 /m2 on 4 ha -> ~2 000 cells (a 447 cm grid: 45 x 45), ~60 % above the 0.4 density threshold."""
    rng = random.Random(3)
    poly = Polygon([(0.0, 0.0), (20000.0, 0.0), (20000.0, 20000.0), (0.0, 20000.0)])
    pts = S.scatter(poly, "Unselected", rng)
    assert 1900 <= len(pts) <= 2100
    kept = S.dense_enough(pts, rng)
    assert 0.45 <= len(kept) / len(pts) <= 0.75
    assert all(d > S.DENSITY_THRESHOLD for d in kept.density)
    assert all(abs(b[0]) == 50.0 for b in kept.bounds_min) and all(0.75 <= s[0] <= 1.25 for s in kept.scale)
