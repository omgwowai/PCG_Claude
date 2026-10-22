"""Stage 10, Ground (Task 17; spec 3, Step B).

The invariants are the task brief's, with the corrections `docs/pypcg/stages/s10.md` section 5 records:
  - the tile centres lie in the pedestrian area (the City grown by half the artery width) and outside the
    excluded areas -- outside by the official 150 cm "coverage" growth, which reaches into them;
  - every sidewalk segment runs along its source edge (midpoint within 1 m of a lot ring, of the grown City
    ring or of the contracted landmark ring);
  - the seven tile meshes are all used across a run;
  - no tile centre lies inside the landmark footprint (the lots' own building footprints are tiled under);
  - empty inputs -> no outputs and no exception.

Offline the booleans are `fakes.RibbonOps` (axis-aligned boxes), so the fixture is a city of boxes: a
120 x 60 m City, a 34 m artery width, lots as boxes, one undividable district, a reserved lot, a small
landmark park, a landmark and a central park that cuts the boundary."""
import json
import math
import os

import pytest

from fakes import FlatTerrain, RibbonOps
from pypcg import geo, stage_api
from pypcg.checks import s10 as C
from pypcg.geo import ParamSet, Points, Polygon, Spline
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.geo import ground as G
from pypcg.stages import s10_ground as S

REPO = stage_api.REPO
OPS = RibbonOps()


def official_ir():
    return json.load(open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_2_1_Ground.json"),
                          encoding="utf-8"))


def box(x0, y0, x1, y1, z=0.0):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [], z)


def closed(p):
    return Spline([(x, y, 0.0) for x, y in p.outer], closed=True, polyline=[(x, y, 0.0) for x, y in p.outer])


class MeshOps(RibbonOps):
    """`ctx.ops.assets` offline: every path is a 300 x 300 x 20 cm static mesh (the plaza tiles' shape)."""

    def __init__(self):
        self.loaded = []

    def assets(self, paths):
        out = []
        for path in paths:
            self.loaded.append(path)
            pts = Points()
            pts.declare("Mesh", "SoftObjectPath")
            b = ((0.0, 0.0, -20.0), (300.0, 300.0, 0.0))
            pts.add((0.0, 0.0, 0.0), bounds_min=b[0], bounds_max=b[1], Mesh=path)
            out.append({"path": path, "points": pts, "bounds": b, "size": AS.size_of(b), "note": ""})
        return out


LOTS = [box(1000 + 2000 * i, 1000 + 2000 * j, 2600 + 2000 * i, 2600 + 2000 * j) for i in range(5) for j in range(2)]
RESERVED = [LOTS[3]]
UNDIVIDABLE = box(8800, 2800, 11500, 5500)          # holds the two lots LOTS[8], LOTS[9]
SMALL_PARK = box(5200, 1200, 5800, 1800)            # inside LOTS[4]
TOWER = box(3000, 4800, 4400, 5800)                 # between lots
PARK = box(11400, -1000, 13500, 7000)               # crosses the boundary on its east side
CITY = box(0, 0, 12000, 6000)


def inputs(**over):
    lots = [(p, frozenset({"Lots"})) for p in LOTS] + [(p, frozenset({"reservedLots"})) for p in RESERVED]
    lots += [(box(0, 0, 10, 10), frozenset({"UnbuildableFootprints"}))]
    ins = {"Lots": lots,
           "Districts": [(UNDIVIDABLE, frozenset({"UndividableDistricts", "City"})),
                         (box(0, 0, 8000, 6000), frozenset({"SmallDistricts"}))],
           "ArteryWidth": [(ParamSet({"ArteryWidth": 3400.0}, {"ArteryWidth": "Double"}), frozenset({"RoadFootprints"}))],
           "City": [(closed(CITY), frozenset({"City"}))],
           "MainTower": [(TOWER, frozenset())],
           "LandmarkPark": [(SMALL_PARK, frozenset({"LandmarkPark"}))],
           "CentralParkFootprint": [(PARK, frozenset())],
           "MeshTerrain": [(FlatTerrain(25.0), frozenset())]}
    ins.update(over)
    return ins


def run(ins=None, seed=42, ops=None):
    out, ctx = stage_api.execute(S, inputs() if ins is None else ins, {stage_api.SEED: seed},
                                 MeshOps() if ops is None else ops)
    return out, ctx


# ---- contract ---------------------------------------------------------------------------------------
def test_contract_no_parameters_of_its_own():
    off = {p["name"] for p in official_ir()["params"]}
    assert off == {"debug", "Partitioned", "PartitionGridSize"}
    assert S.PARAMS == {}
    assert [s[0] for s in stage_api.param_specs(S)] == [stage_api.SEED]


def test_contract_scene_reads_feed_the_python_node_by_name():
    from pypcg import graphs, ir
    from pypcg.graphs import s10_ground as GR
    from pypcg.profiles import official
    doc = graphs.graph(10).to_ir(official)            # raises on an unwired Python input pin
    by = {x["name"]: x for x in doc["nodes"]}
    py = [x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE]
    assert len(py) == 1
    feeds = {p["label"]: [by[e[0]] for e in p["edges"]] for p in py[0]["inputs"]}
    assert set(S.INPUTS) | {stage_api.PARAMS_PIN} == set(feeds)
    titles = {"Lots": "Get Lots", "Districts": "Get Districts", "City": "Get City Shape",
              "MainTower": "Get Landmark", "LandmarkPark": "Landmark Small Park",
              "CentralParkFootprint": "Get Central Park"}
    for pin, title in titles.items():
        assert [x["title"] for x in feeds[pin]] == [title], pin
    assert [x["subgraph"].rsplit("/", 1)[-1] for x in feeds["MeshTerrain"]] == ["Get_MeshTerrain.Get_MeshTerrain"]
    # the artery width: Get Roads -> FilterDataByTag_4 (tags containing "Polygon") -> ExtractAttribute_1
    ext = feeds["ArteryWidth"]
    assert [x["title"] for x in ext] == ["Extract ArteryWidth From Road Polygon"]
    filt = by[ext[0]["inputs"][0]["edges"][0][0]]
    assert filt["settings"]["SelectedTags"] == "Polygon" and filt["settings"]["Operator"] == "Substring"
    assert by[filt["inputs"][0]["edges"][0][0]]["title"] == "Get Roads"
    # Get Base Terrain is kept and, as in the official graph, feeds nothing
    base = [x for x in doc["nodes"] if x["title"] == "Get Base Terrain"]
    assert len(base) == 1
    assert not any(e[0] == base[0]["name"] for x in doc["nodes"] for p in x["inputs"] for e in p["edges"])
    off = {x["name"]: x for x in official_ir()["nodes"]}
    assert not any(e[0] == "Subgraph_44" for x in off.values() for p in x.get("inputs", []) for e in p["edges"])
    assert set(GR.READS.values()) <= set(off)


def test_contract_publishes_nothing_and_feeds_the_kept_generation_nodes():
    from pypcg import graphs, ir
    from pypcg.profiles import official
    doc = graphs.graph(10).to_ir(official)
    by = {x["name"]: x for x in doc["nodes"]}
    out = by["DefaultOutputNode"]
    assert not any(p["edges"] for p in out["inputs"])
    off = {x["name"]: x for x in official_ir()["nodes"]}
    assert not any(p["edges"] for p in off["DefaultOutputNode"].get("inputs", []))
    py = [x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE][0]["name"]
    reads = {}
    for x in doc["nodes"]:
        for p in x["inputs"]:
            for src, pin in p["edges"]:
                if src == py:
                    reads.setdefault(pin, set()).add(x["title"])
    assert reads == {"GroundTiles": {"Spawn ground tiles"}, "SidewalkSegments": {"Assign Sidewalks"},
                     "CornerShapes": {"Assign Corners"}, "RailingZones": {"Assign Railing And Fence Grammar"}}
    titles = {x["title"] for x in doc["nodes"]}
    assert {"Spawn Sidewalk Assets", "Spawn Fence Assets", "Zero Roll On Street Props",
            "Zero Pitch On Street Props", "Filter: vehicles"} <= titles


def test_contract_fixed_settings_are_the_official_overrides():
    ov = {x["name"]: x.get("overrides") or {} for x in official_ir()["nodes"]}
    assert ov["Subgraph_10"]["Expand"] == S.GROUND_EXPAND_CM
    assert ov["Subgraph_9"]["PointExtents"] == S.TILE_EXTENT_CM
    assert ov["Subgraph_33"]["offset"] == {"X": 0, "Y": 0, "Z": S.TILE_LIFT_CM}
    assert ov["Subgraph_19"]["offset"] == {"X": 0, "Y": 0, "Z": S.RAILING_LIFT_CM}
    assert ov["Subgraph_52"]["Expand"] == S.PARK_BUFFER_CM
    assert ov["Subgraph_46"]["Contract"] == S.LANDMARK_SETBACK_CM
    assert ov["Subgraph_8"]["CutAngleThreshold"] == S.LOT_CUT_DEG
    assert ov["Subgraph_4"]["CutAngleThreshold"] == S.LANDMARK_CUT_DEG
    assert [ov["FC_RandomChoice_%d" % k]["Ratio"] for k in range(1, 7)] == list(S.SPLIT_RATIOS)
    for k, (letter, path) in enumerate(S.TILE_CALLS):
        o = ov["AssignGroundTiles_" + letter]
        assert o["Assets"] == [path]
        assert o["PositionOffset"] == {"X": -150, "Y": -150, "Z": 0}
        assert set(o) == {"Assets", "PositionOffset"}          # every other setting at its default
    nodes = {x["name"]: x for x in official_ir()["nodes"]}
    gather = [e[0][-1] for e in nodes["Gather_0"]["inputs"][0]["edges"]]
    assert "".join(gather) == S.GATHER_ORDER


# ---- empty inputs -------------------------------------------------------------------------------------
def test_empty_inputs_give_no_outputs_and_no_exception():
    empty = {pin: [] for pin in S.INPUTS}
    out, _ = run(empty)
    assert all(out[pin] == [] for pin in S.OUTPUTS)


def test_empty_inputs_one_pin_at_a_time():
    for pin in S.INPUTS:
        out, _ = run(inputs(**{pin: []}))
        assert set(out) == set(S.OUTPUTS)
    out, _ = run(inputs(Lots=[]))
    assert out["GroundTiles"] == [] and out["RailingZones"] == []
    # no surface: the official projector emits nothing (PCGProjectionElement returns with no target)
    out, _ = run(inputs(MeshTerrain=[]))
    assert out["GroundTiles"] == [] and len(out["SidewalkSegments"]) > 0


def test_no_asset_loader_assigns_nothing():
    out, ctx = stage_api.execute(S, inputs(), {stage_api.SEED: 1}, RibbonOps())
    assert out["GroundTiles"] == []
    assert any("no asset loader" in n for n in ctx.notes)


# ---- Fill_Areas_Uniformly ----------------------------------------------------------------------------
def test_fill_is_a_half_open_lattice_in_the_frame_of_the_longest_edge():
    locs, yaw = G.fill_uniform(box(0, 0, 1500, 900).outer, 0.0, 150.0)
    assert yaw == 0.0
    assert sorted((round(p[0]), round(p[1])) for p in locs) == sorted(
        (x, y) for x in (0, 300, 600, 900, 1200) for y in (0, 300, 600))
    # a 30 degree turned rectangle: the lattice turns with its longest edge, about the WORLD origin
    a = math.radians(30.0)
    ring = [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))
            for x, y in [(310, 10), (1810, 10), (1810, 910), (310, 910)]]
    locs, yaw = G.fill_uniform(ring, 5.0, 150.0)
    assert abs(yaw - 30.0) < 1e-9
    for p in locs:
        lx = p[0] * math.cos(-a) - p[1] * math.sin(-a)
        ly = p[0] * math.sin(-a) + p[1] * math.cos(-a)
        assert abs(lx / 300.0 - round(lx / 300.0)) < 1e-9 and abs(ly / 300.0 - round(ly / 300.0)) < 1e-9
        assert 310 < lx < 1810 and 10 < ly < 910 and p[2] == 5.0
    assert len(locs) == 5 * 3


def test_fill_takes_the_first_longest_segment():
    assert G.longest_segment([(0, 0), (10, 0), (10, 10), (0, 10)]) == 0
    assert G.longest_segment([(0, 0), (5, 0), (5, 10), (0, 10)]) == 1


def test_tile_points_carry_the_sampler_box_and_the_lift():
    pts = S.tile_points(box(0, 0, 900, 900, z=3.0))
    assert len(pts) == 9
    assert set(pts.bounds_min) == {(-150.0, -150.0, -150.0)} and set(pts.bounds_max) == {(150.0, 150.0, 150.0)}
    assert set(p[2] for p in pts.loc) == {3.0 + S.TILE_LIFT_CM}
    assert set(pts.steepness) == {1.0}


# ---- Custom_Projector_with_rotation_fix ----------------------------------------------------------------
class Plane:
    def __init__(self, a, b, c):
        self.a, self.b, self.c = a, b, c

    def height(self, x, y):
        return self.a * x + self.b * y + self.c


def test_projector_on_a_flat_surface_keeps_the_yaw_and_adds_the_stored_height():
    loc, rot = G.project_tile((100.0, 200.0, 15.0), (0.0, 35.0, 0.0), (-150, -150, -150), (150, 150, 150), Plane(0, 0, 7.0))
    assert loc == (100.0, 200.0, 22.0)
    assert abs(rot[0]) < 1e-12 and abs(rot[1] - 35.0) < 1e-9 and abs(rot[2]) < 1e-12


def test_projector_tilts_the_tile_to_the_surface():
    s = 0.1
    loc, rot = G.project_tile((0.0, 0.0, 15.0), (0.0, 0.0, 0.0), (-150, -150, -150), (150, 150, 150), Plane(s, 0.0, 0.0))
    assert abs(rot[0] - math.degrees(math.atan(s))) < 1e-9          # pitch up the +X slope
    assert abs(rot[1]) < 1e-9 and abs(rot[2]) < 1e-9
    loc, rot = G.project_tile((0.0, 0.0, 15.0), (0.0, 0.0, 0.0), (-150, -150, -150), (150, 150, 150), Plane(0.0, s, 0.0))
    assert abs(abs(rot[2]) - math.degrees(math.atan(s))) < 1e-9     # roll across the +Y slope
    assert loc[2] == 15.0


def test_projector_miss_returns_none():
    class Miss:
        def height(self, x, y):
            return None
    assert G.project_tile((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (-1, -1, -1), (1, 1, 1), Miss()) is None


def test_rot_from_xy():
    p, y, r = G.rot_from_xy((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0))
    assert abs(p) < 1e-12 and abs(y - 90.0) < 1e-12 and abs(r) < 1e-12


# ---- the split and the assignment ---------------------------------------------------------------------
def test_split_seven_is_one_seventh_each_on_average():
    import random
    n, counts = 7000, [0] * 7
    for w in S.split_seven(n, random.Random(3)):
        counts[w] += 1
    for c in counts:
        assert abs(c / n - 1.0 / 7.0) < 0.02


def test_assign_moves_each_tile_to_its_corner_in_its_own_frame():
    pts = Points()
    pts.add((1000.0, 2000.0, 15.0), rot=(0.0, 90.0, 0.0), bounds_min=(-150, -150, -150), bounds_max=(150, 150, 150))
    table = MeshOps().assets([p for _k, p in S.TILE_CALLS])
    out = S.assign_tiles([pts], [2], table)
    assert list(out) == ["C"]
    t = out["C"]
    assert abs(t.loc[0][0] - 1150.0) < 1e-9 and abs(t.loc[0][1] - 1850.0) < 1e-9 and t.loc[0][2] == 15.0
    assert t.attrs["Asset"] == [S._MESH % ("C", "C")]
    assert (t.bounds_min[0], t.bounds_max[0]) == ((0.0, 0.0, -20.0), (300.0, 300.0, 0.0))


# ---- the run and its invariants -------------------------------------------------------------------------
def test_run_meets_the_invariants():
    out, ctx = run()
    assert len(out["GroundTiles"]) >= 1
    assert C.check(inputs(), {}, out, OPS) == []


def test_tiles_avoid_the_excluded_areas_and_the_landmark():
    out, _ = run()
    centres = []
    off = tuple(AS._f32(x) for x in S.TILE_OFFSET)
    for v, _t in out["GroundTiles"]:
        for i in range(len(v)):
            d = geo.quat_rotate(tuple(v.quat[i]), off)
            centres.append((v.loc[i][0] - d[0], v.loc[i][1] - d[1]))
    assert centres
    for c in centres:
        assert not geo.contains(TOWER, c)
        for ex in (RESERVED[0], UNDIVIDABLE, SMALL_PARK):
            if geo.contains(ex, c):
                assert C.dist_to_ring(c, ex.outer) <= S.GROUND_EXPAND_CM + 1e-6
    # tiles sit on the surface (25 cm) plus the lift
    assert {round(v.loc[i][2], 9) for v, _ in out["GroundTiles"] for i in range(len(v))} == {25.0 + S.TILE_LIFT_CM}


def test_the_seven_tile_meshes_are_all_used_across_a_run():
    lots = [(box(1000 * i, 1000 * j, 1000 * i + 700, 1000 * j + 700), frozenset({"Lots"}))
            for i in range(12) for j in range(6)]
    out, _ = run(inputs(Lots=lots, Districts=[], LandmarkPark=[], MainTower=[]))
    used = {t for _v, tags in out["GroundTiles"] for t in tags if t.startswith("SM_Plaza_Square_")}
    assert used == {"SM_Plaza_Square_" + k for k in "ABCDEFG"}


def test_sidewalk_segments_run_along_their_sources():
    out, _ = run()
    segs = [v for v, _ in out["SidewalkSegments"]]
    # four sides per lot, the landmark's four sides, and the boundary pieces' runs
    assert len(segs) >= 4 * len(LOTS) + 4
    for s in segs:
        assert all(p[2] == 0.0 for p in s.points)
    assert C.check(inputs(), {}, out, OPS) == []


def test_the_boundary_is_the_grown_city_reversed_and_cut_by_the_grown_park():
    src = S.read(inputs())
    bound = S.boundary(src, OPS)
    assert len(bound) == 1 and not bound[0][1]                  # one open piece: the park cut the loop
    path = bound[0][0]
    for p in path:
        assert C.dist_to_ring(p, [(-1700, -1700), (13700, -1700), (13700, 7700), (-1700, 7700)]) < 1e-6
        assert not (PARK.outer[0][0] - S.PARK_BUFFER_CM < p[0] < 13500 + S.PARK_BUFFER_CM
                    and -1000 - S.PARK_BUFFER_CM < p[1] < 7000 + S.PARK_BUFFER_CM)
    # reversed: the CCW city ring runs clockwise
    assert geo.signed_area(path) < 0


def test_without_a_park_cut_the_boundary_stays_one_closed_ring():
    src = S.read(inputs(CentralParkFootprint=[]))
    bound = S.boundary(src, OPS)
    assert len(bound) == 1 and bound[0][1]


def test_corner_shapes_are_the_boundary_the_lots_and_the_contracted_landmark():
    out, _ = run()
    corners = [v for v, _ in out["CornerShapes"]]
    assert isinstance(corners[0], Spline)
    assert [c for c in corners if isinstance(c, Polygon)][:len(LOTS)] == LOTS
    lm = corners[-1]
    (x0, y0), (x1, y1) = geo.bbox(lm.outer)
    assert (round(x0), round(y0), round(x1), round(y1)) == (3300, 5100, 4100, 5500)


def test_railing_zones_are_the_lots_inside_undividable_districts_less_the_landmark_lifted_21():
    out, _ = run()
    zones = [v for v, _ in out["RailingZones"]]
    boxes = sorted(tuple(round(c) for c in sum(geo.bbox(z.outer), ())) for z in zones)
    assert boxes == [(9000, 3000, 10600, 4600)]
    assert {z.z for z in zones} == {S.RAILING_LIFT_CM}


def test_check_catches_a_tile_in_the_landmark_and_a_stray_segment():
    out, _ = run()
    v = out["GroundTiles"][0][0]
    v.loc[0] = (3500.0 - 150.0, 5000.0 - 150.0, v.loc[0][2])
    v.quat = None
    v.rot[0] = (0.0, 0.0, 0.0)
    f = C.check(inputs(), {}, out, OPS)
    assert any("in the landmark" in x for x in f)
    out, _ = run()
    out["SidewalkSegments"].append((Spline([(6000.0, 3500.0, 0.0), (6100.0, 3500.0, 0.0)]), ["SidewalkSegments"]))
    f = C.check(inputs(), {}, out, OPS)
    assert any("do not run along" in x for x in f)


def test_open_segments_keep_both_ends():
    path = [(0, 0), (100, 0), (200, 1), (200, 100), (300, 100)]
    runs = G.extract_open_segments(path, 20.0)
    assert runs == [[(0, 0), (100, 0), (200, 1)], [(200, 1), (200, 100)], [(200, 100), (300, 100)]]
    assert G.extract_open_segments([(0, 0)], 20.0) == []


def test_in_frame_keeps_the_geometry():
    p = box(100, 200, 900, 700)
    res = A.in_frame(p, lambda q: A.expand([q], 50.0, OPS))
    assert len(res) == 1
    (x0, y0), (x1, y1) = geo.bbox(res[0].outer)
    assert max(abs(a - b) for a, b in zip((x0, y0, x1, y1), (50, 150, 950, 750))) < 1e-9


# ---- seeds ------------------------------------------------------------------------------------------------
def _sig(out):
    return {pin: [[geo.to_json(v), list(t)] for v, t in items] for pin, items in out.items()}


def test_seeded_runs_repeat_and_differ():
    lots = [(box(1000 * i, 1000 * j, 1000 * i + 700, 1000 * j + 700), frozenset({"Lots"}))
            for i in range(12) for j in range(6)]
    ins = inputs(Lots=lots)
    a, _ = run(ins, seed=5)
    b, _ = run(ins, seed=5)
    c, _ = run(ins, seed=6)
    assert _sig(a) == _sig(b)
    assert _sig(a)["GroundTiles"] != _sig(c)["GroundTiles"]
    for pin in ("SidewalkSegments", "CornerShapes", "RailingZones"):     # the seed moves only the split
        assert _sig(a)[pin] == _sig(c)[pin]


def test_check_record_replays_a_recorded_run():
    ins = inputs()
    out, ctx = run(ins, seed=9)
    rec = {"params": {stage_api.SEED: 9},
           "inputs": {pin: [[geo.to_json(v), sorted(t)] for v, t in items] for pin, items in ins.items()},
           "outputs": {pin: [[geo.to_json(v), list(t)] for v, t in items] for pin, items in out.items()}}
    assert C.check_record(rec, MeshOps()) == []
    rec["outputs"]["RailingZones"] = []
    assert any("RailingZones differs" in x for x in C.check_record(rec, MeshOps()))


def test_boundary_points_keep_the_yaw_of_their_counter_clockwise_edge():
    """The corner grammar reads the control points' own rotations: a vertex keeps the yaw of its
    outgoing edge on the counter-clockwise grown ring (against the reversed spline's travel), a cut
    point takes the direction of travel."""
    src = S.read(inputs())
    path, closed, _z, yaws = S.boundary(src, OPS)[0]
    assert len(yaws) == len(path)
    for k in range(1, len(path) - 1):
        ccw_next = path[k - 1]                      # the reversed ring's previous point is the CCW next
        want = math.degrees(math.atan2(ccw_next[1] - path[k][1], ccw_next[0] - path[k][0]))
        assert abs(yaws[k] - want) < 1e-9
    travel = math.degrees(math.atan2(path[1][1] - path[0][1], path[1][0] - path[0][0]))
    assert abs(yaws[0] - travel) < 1e-9
    out, _ = run()
    piece = out["CornerShapes"][0][0]
    assert piece.rotations == [(0.0, y, 0.0) for y in yaws]
    seg = out["SidewalkSegments"][0][0]
    assert seg.rotations is None                    # the sidewalk segments: measured equal without them


def test_check_flags_tiles_under_a_landmark_that_overlaps_a_lot():
    """The demo fixture's landmark lies between lots, so the landmark clause cannot fail on it; here the
    landmark covers part of a lot, the stage tiles under it (as the official graph would), and the check
    must flag those tiles."""
    tower = box(1200, 1200, 2000, 2000)                       # inside LOTS[0]
    ins = inputs(MainTower=[(tower, frozenset())])
    out, _ = run(ins)
    f = C.check(ins, {}, out, OPS)
    assert any("in the landmark" in x for x in f), f


def test_corner_shapes_hand_back_the_input_lot_objects():
    """The lots in `CornerShapes` must BE the `Lots` input objects: the host forwards an input polygon handed
    back unchanged as the engine's own data (Task 18, s13.md 4.6), and a copy would silently stop that."""
    ins = inputs()
    out, _ctx = run(ins)
    lot_ids = {id(v) for v, t in ins["Lots"] if "Lots" in t}
    corners = [v for v, _t in out["CornerShapes"]]
    forwarded = [v for v in corners if id(v) in lot_ids]
    assert len(forwarded) == len(LOTS)
    assert all(isinstance(v, Polygon) for v in forwarded)
