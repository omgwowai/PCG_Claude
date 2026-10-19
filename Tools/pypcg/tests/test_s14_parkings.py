"""Stage 14, Parkings (Task 19; spec 3, Step B).

The invariants are the task brief's:
  - every space centre is inside the footprint;
  - the number of spaces is the number of 350 cm segments of the space lines (the brief's "+-10 % of
    area / space area" is corrected in s14.md 5.1: the official graph has 57 m2 of lot per space);
  - cars only sit on occupied spaces and face one of the two ways;
  - the entrance cut leaves at least one boundary gap;
  - empty inputs -> no outputs, on both Python nodes.

Offline the booleans are `fakes.RibbonOps` (axis-aligned boxes) with `fakes.FakeOps.cut_with_paths`, so the
fixture is a few box lots; the engine's booleans are measured in the editor
(`Tools/pypcg/data/s14_official_measurements.json`)."""
import json
import math
import os

from fakes import FakeOps, FlatTerrain, RibbonOps
from pypcg import geo, stage_api
from pypcg.checks import s14 as C
from pypcg.geo import Points, Polygon
from pypcg.geo import areas as A
from pypcg.geo import assets as AS
from pypcg.geo import splines as SP
from pypcg.stages import s14_parkings as S
from pypcg.stages import s14_parkings_finish as F

REPO = stage_api.REPO


def official_ir():
    with open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_2_3_Parkings.json"), encoding="utf-8") as fh:
        return json.load(fh)


def official(name):
    return next(n for n in official_ir()["nodes"] if n["name"] == name)


class ParkOps(RibbonOps):
    """Box booleans, `FakeOps`' convex cut, and every asset a 400 x 200 x 150 cm static mesh."""

    cut_with_paths = FakeOps.cut_with_paths

    def assets(self, paths):
        out = []
        for path in paths:
            pts = Points()
            pts.declare("Mesh", "SoftObjectPath")
            b = ((-200.0, -100.0, 0.0), (200.0, 100.0, 150.0))
            pts.add((0.0, 0.0, 0.0), bounds_min=b[0], bounds_max=b[1], Mesh=path)
            out.append({"path": path, "points": pts, "bounds": b, "size": AS.size_of(b), "note": ""})
        return out


OPS = ParkOps()


def box(x0, y0, x1, y1, z=0.0):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [], z)


LOTS = [box(0, 0, 10500, 8500), box(20000, 0, 22000, 2500), box(30000, 0, 48000, 10000)]


def inputs(lots=LOTS):
    return {"ParkingFootprint": [(p, frozenset({"reservedLots"})) for p in lots]}


def run(ins=None, seed=42, ops=OPS):
    out, _ctx = stage_api.execute(S, inputs() if ins is None else ins, {stage_api.SEED: seed}, ops)
    return out


def values(out, pin):
    return [v for v, _t in out[pin]]


# ---- contract ---------------------------------------------------------------------------------------
def test_contract_no_parameters_of_its_own():
    assert {p["name"] for p in official_ir()["params"]} == {"Partitioned", "PartitionGridSize"}
    assert S.PARAMS == {} and F.PARAMS == {}
    from pypcg import graphs
    from pypcg.profiles import official as prof
    assert [p["name"] for p in graphs.graph(14).to_ir(prof)["params"]] == [stage_api.SEED]   # Partitioned* dropped


def _graph():
    from pypcg import graphs, ir
    from pypcg.profiles import official as prof
    doc = graphs.graph(14).to_ir(prof)                 # raises on an unwired Python input pin
    by = {x["name"]: x for x in doc["nodes"]}
    py = {x["title"]: x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE}
    return doc, by, py


def _feeds(node, by):
    return {p["label"]: [(by[e[0]], e[1]) for e in p["edges"]] for p in node["inputs"]}


def test_contract_scene_reads_feed_the_python_nodes_by_name():
    _doc, by, py = _graph()
    assert set(py) == {"Python: s14_parkings", "Python: s14_parkings_finish"}
    main = _feeds(py["Python: s14_parkings"], by)
    assert set(S.INPUTS) | {stage_api.PARAMS_PIN} == set(main)
    [(lots, _pin)] = main["ParkingFootprint"]
    assert lots["title"] == "Get Parking Lot Footprint"
    assert lots["overrides"]["ActorReferences"] == official("Subgraph_0")["overrides"]["ActorReferences"]
    fin = _feeds(py["Python: s14_parkings_finish"], by)
    assert set(F.INPUTS) | {stage_api.PARAMS_PIN} == set(fin)
    [(terrain, _pin)] = fin["MeshTerrain"]
    assert terrain["subgraph"].rsplit("/", 1)[-1] == "Get_MeshTerrain.Get_MeshTerrain"
    assert terrain["overrides"] == official("Subgraph_1")["overrides"]
    # Subgraph_3's In Points order: Subgraph_7, 53, 54, the tiles, the arrows, the forward and reverse cars
    order = [(x["title"], pin) for x, pin in fin["Points"]]
    main_title = "Python: s14_parkings"
    assert order == [(main_title, "Lines"), ("Assign Concrete Barrier Grammar", "Out"),
                     ("Assign Chain-Link Fence Grammar", "Out"), (main_title, "Tiles"), (main_title, "Arrows"),
                     (main_title, "ForwardCars"), (main_title, "ReverseCars")]
    off = [e[0] for p in official("Subgraph_3")["inputs"] if p["label"] == "In Points" for e in p["edges"]]
    assert off == ["Subgraph_7", "Subgraph_53", "Subgraph_54", "NamedRerouteUsage_1", "NamedRerouteUsage_6",
                   "NamedRerouteUsage_7", "NamedRerouteUsage_8"]


def test_contract_publishes_nothing_and_feeds_the_kept_generation_nodes():
    doc, by, py = _graph()
    out = by["DefaultOutputNode"]
    assert not [e for p in out["inputs"] for e in p["edges"]]
    assert not [e for p in official("DefaultOutputNode")["inputs"] for e in p["edges"]]
    main = py["Python: s14_parkings"]["name"]
    feeds = {x["title"]: _feeds(x, by) for x in doc["nodes"] if x.get("title")}
    assert [(n["name"], pin) for n, pin in feeds["Assign Concrete Barrier Grammar"]["PrimaryInput"]] == \
        [(main, "CentralLines"), (main, "Border")]                           # NamedRerouteUsage_9, then _13
    assert [(n["name"], pin) for n, pin in feeds["Assign Chain-Link Fence Grammar"]["PrimaryInput"]] == [(main, "Border")]
    assert [(n["title"], pin) for n, pin in feeds["Spawn All Parking Lot Assets"]["PrimaryInput"]] == \
        [("Python: s14_parkings_finish", "Points")]
    kept = {x["title"] for x in doc["nodes"] if x["class"] == "PCGSubgraphSettings"}
    assert kept == {official(n)["title"] for n in ("Subgraph_0", "Subgraph_1", "Subgraph_53", "Subgraph_54", "Subgraph_13")}


def test_contract_fixed_settings_are_the_official_overrides():
    ov = lambda n: official(n)["overrides"]     # noqa: E731
    assert ov("Subgraph_29") == {"Contract": S.OUTER_CONTRACT_CM}
    assert ov("Subgraph_33") == {"Contract": S.INNER_CONTRACT_CM}
    assert ov("Subgraph_30") == {"Contract": S.AISLE_CONTRACT_CM}
    assert ov("Subgraph_32") == {"GridLength": S.GRID_LENGTH_CM, "GridWidth": S.GRID_WIDTH_CM}
    assert ov("Subgraph_35") == {"SubdivLength": S.CENTRAL_SUBDIV[1], "SubdivWidth": S.CENTRAL_SUBDIV[0],
                                 "UseSubdivisionInsteadOfSizes": True}
    assert ov("Subgraph_55") == {"SubdivLength": S.MEDIAN_SUBDIV[1], "SubdivWidth": S.MEDIAN_SUBDIV[0],
                                 "UseSubdivisionInsteadOfSizes": True}
    assert ov("Subgraph_56") == {"Expand": S.MEDIAN_EXPAND_CM}
    assert ov("Subgraph_57") == {"Width": S.MEDIAN_WIDTH_CM}
    assert ov("Subgraph_36") == ov("Subgraph_59") == {"CutAngleThreshold": S.CUT_ANGLE_DEG}
    assert ov("Subgraph_38") == {}                                    # CutAngleThreshold 0: every segment
    assert ov("Subgraph_43") == {"EndOffset": S.OUTER_TRUNC_CM, "StartOffset": S.OUTER_TRUNC_CM}
    assert ov("Subgraph_63") == {"EndOffset": S.MEDIAN_TRUNC_CM, "StartOffset": S.MEDIAN_TRUNC_CM}
    assert ov("Subgraph_44")["SamplingMode"] == "NumberOfSamples"
    for n in ("Subgraph_45", "Subgraph_62"):
        assert ov(n) == {"Distance": S.SPACE_CM, "FitToCurve": True, "SamplingMode": "Distance"}
    assert ov("Subgraph_58") == {"SamplingMode": "Subdivision", "Subdivision": S.BORDER_SUBDIV}
    assert ov("Subgraph_46")["offset"] == {"X": 0, "Y": S.ROW_OFFSET_CM, "Z": 0}
    assert ov("Subgraph_47")["offset"] == {"X": 0, "Y": -S.ROW_OFFSET_CM, "Z": 0}
    assert (ov("Subgraph_66")["offset"]["X"], ov("Subgraph_66")["offset"]["Y"]) == S.ARROW_OFFSETS[0]
    assert (ov("Subgraph_67")["offset"]["X"], ov("Subgraph_67")["offset"]["Y"]) == S.ARROW_OFFSETS[1]
    assert ov("Subgraph_65") == {"UseExistingControlPoints": True}    # Facing: the default, inward
    assert ov("Subgraph_52") == {"Facing": "tangent", "FitToCurve": False, "UseExistingControlPoints": True}
    assert ov("Subgraph_48") == {"RandomPerDataset": False, "Ratio": S.OCCUPANCY, "Seed": 1}
    assert ov("Subgraph_49") == {"RandomPerDataset": False, "Ratio": S.REVERSED, "Seed": 2}
    assert ov("Subgraph_10") == {"asset": S.TILE_MESH}
    assert ov("Subgraph_11")["offset"]["Z"] == S.TILE_LIFT_CM


def test_contract_assign_calls_are_the_official_ones():
    keys = {"PositionOffset": "position_offset", "RotationOffset": "rotation_offset", "ScaleOffset": "scale_offset",
            "ExtentsScale": "extents_scale", "UniformScale": "uniform_scale", "UseMeshBounds": "use_mesh_bounds",
            "RandomPositionRange": "random_position_range", "RandomRotationRange": "random_rotation_range"}
    for name, paths, settings in (("Subgraph_7", [S.LINE_MESH], S.LINE_SETTINGS), ("Subgraph_8", [S.ARROW_MESH], S.ARROW_SETTINGS),
                                  ("Subgraph_4", list(S.CARS), S.FORWARD_SETTINGS),
                                  ("Subgraph_5", list(S.CARS), S.REVERSE_SETTINGS)):
        ov = dict(official(name)["overrides"])
        assert ov.pop("Assets") == paths, name
        assert {keys[k]: v for k, v in ov.items()} == settings, name


def test_contract_finish_settings_are_the_official_ones():
    s = official("FilterDataByAttribute_1")["settings"]
    assert s["FilterOperator"] == "Substring" and s["Threshold"]["AttributeTypes"]["StringValue"] == F.VEHICLE
    pairs = []
    for n in ("AttributeStringOp_1", "AttributeStringOp_2"):
        d = {x["prop"]: x["value"] for x in official(n)["pin_defaults"]}
        pairs.append((d["DefaultValue2"], d["DefaultValue3"]))
    assert tuple(pairs) == F.REPLACES
    assert official("Subgraph_9")["overrides"]["offset"]["Z"] == F.LIFT_CM
    gather = [e for p in official("Gather_0")["inputs"] for e in p["edges"]]
    assert gather == [["FilterDataByAttribute_1", "InsideFilter"], ["FilterDataByAttribute_1", "OutsideFilter"],
                      ["AttributeCast_0", "Out"]]


# ---- empty inputs (Review Focus 1) ---------------------------------------------------------------------
def test_empty_inputs_main_node():
    out = run({pin: [] for pin in S.INPUTS})
    assert all(out[pin] == [] for pin in S.OUTPUTS)


def test_empty_inputs_finish_node():
    out, _ctx = stage_api.execute(F, {pin: [] for pin in F.INPUTS}, dict(stage_api.defaults(F)), OPS)
    assert all(out[pin] == [] for pin in F.OUTPUTS)


def test_no_asset_loader_assigns_nothing_but_keeps_lines_and_tiles():
    class NoAssets(RibbonOps):
        cut_with_paths = FakeOps.cut_with_paths
    out = run(ops=NoAssets())
    assert out["Lines"] == [] and out["Arrows"] == [] and out["ForwardCars"] == [] and out["ReverseCars"] == []
    assert out["Tiles"] and out["CentralLines"] and out["Border"]


# ---- the task's invariants -----------------------------------------------------------------------------
def test_run_meets_the_invariants():
    ins = inputs()
    out = run(ins)
    rec = {pin: [(v, t) for v, t in out[pin]] for pin in S.OUTPUTS}
    assert C.check(ins, {}, rec, OPS) == []
    lots, rows, spaces, _bands = C.rebuild(ins, OPS)
    assert len(spaces) > 100 and rows


def test_space_centres_lie_inside_the_footprint():
    lots, _rows, spaces, _bands = C.rebuild(inputs(), OPS)
    assert len(spaces)
    for p in spaces.loc:
        assert any(geo.inside(p[:2], q.outer) for q in lots), p


def test_space_count_is_the_segments_of_the_space_lines():
    _lots, rows, spaces, _bands = C.rebuild(inputs(), OPS)
    assert len(spaces) == sum(int(SP.length(r) / S.SPACE_CM + 1e-6) - 1 for r in rows)
    # the inner rows are the 35 m aisle centre lines +-300 cm: 10 points, 9 spaces of 388.9 cm each
    assert all(abs(math.dist(r[0][:2], r[1][:2]) - SP.length(r) / (len(r) - 1)) < 1e-6 for r in rows)


def test_cars_sit_on_occupied_spaces_and_face_one_of_two_ways():
    out = run()
    fwd, rev = C._cars(out, "ForwardCars"), C._cars(out, "ReverseCars")
    assert len(fwd) and len(rev)
    _lots, _rows, spaces, _bands = C.rebuild(inputs(), OPS)
    for cars, sign in ((fwd, 90.0), (rev, -90.0)):
        for loc, rot in zip(cars.loc, cars.rot):
            i = min(range(len(spaces)), key=lambda k: math.dist(spaces.loc[k][:2], loc[:2]))
            assert math.dist(spaces.loc[i][:2], loc[:2]) <= 50.0 + 1e-6
            assert C._angle(rot[1], spaces.rot[i][1] + sign) <= 5.0 + 1e-6
    # 80 % occupied, half reversed, on 600+ spaces
    assert abs((len(fwd) + len(rev)) / len(spaces) - S.OCCUPANCY) < 0.06
    assert abs(len(fwd) / (len(fwd) + len(rev)) - S.REVERSED) < 0.08


def test_check_catches_a_car_off_its_space_and_a_closed_border():
    ins = inputs()
    out = run(ins)
    rec = {pin: list(out[pin]) for pin in S.OUTPUTS}
    cars = C._cars(rec, "ForwardCars")
    cars.loc[0] = (cars.loc[0][0] + 500.0, cars.loc[0][1], cars.loc[0][2])
    rec["Border"] = [(geo.Spline([(x, y, 0.0) for x, y in p.outer + [p.outer[0]]]), ["Border"]) for p in LOTS]
    fails = C.check(ins, {}, rec, OPS)
    assert any("ForwardCars 0" in f for f in fails)
    assert any("no entrance gap" in f for f in fails)


def test_the_entrance_cut_leaves_a_gap_in_every_crossed_lot():
    out = run()
    border = values(out, "Border")
    for lot in (LOTS[0], LOTS[2]):
        perim = geo.path_length(lot.outer + [lot.outer[0]])
        mine = [s for s in border if C._in_lots(s.points[0], [lot], 10.0)]
        assert len(mine) > 4 and sum(SP.length(s.points) for s in mine) < perim - 1000.0


def test_seeded_runs_repeat_and_differ():
    a, b, c = run(seed=7), run(seed=7), run(seed=8)
    dump = lambda o: json.dumps({p: [[geo.to_json(v), list(t)] for v, t in o[p]] for p in S.OUTPUTS})   # noqa: E731
    assert dump(a) == dump(b)
    assert dump(a) != dump(c)
    assert [geo.to_json(v) for v in values(a, "Tiles")] == [geo.to_json(v) for v in values(c, "Tiles")]


def test_outputs_are_tagged_splines_and_points():
    out = run()
    for pin in ("CentralLines", "Border"):
        for v, t in out[pin]:
            assert isinstance(v, geo.Spline) and v.linear and not v.closed and t == [pin]
            assert v.rotations and len(v.rotations) == len(v.points)
    for pin in ("Lines", "Tiles", "Arrows", "ForwardCars", "ReverseCars"):
        assert all(isinstance(v, geo.Points) and len(v) for v, _t in out[pin]), pin
    assert {a for v, _t in out["Tiles"] for a in v.attrs[AS.ASSET_ATTR]} == {S.TILE_MESH}


# ---- the steps -----------------------------------------------------------------------------------------
def test_outer_and_inner_areas_follow_their_subjects():
    outer = S.outer_areas(LOTS, OPS)
    assert len(outer) == 3
    for o, lot in zip(outer, LOTS):
        assert geo.area_m2(o) < geo.area_m2(lot)
        assert math.dist(o.outer[0], (lot.outer[0][0] + 300.0, lot.outer[0][1] + 300.0)) < 1e-9
    inner = S.inner_areas(outer, OPS)
    assert len(inner) == 2                        # the 20 x 25 m lot has no room for the inner rows


def test_central_lines_run_down_each_aisle():
    outer = S.outer_areas(LOTS, OPS)
    cells = S.grid_cells(S.inner_areas(outer, OPS), OPS)
    aisles = S.aisles(cells, OPS)
    lines = S.central_lines(aisles)
    assert len(lines) == len(aisles)
    for line, a in zip(lines, aisles):
        mid = SP.center([line[0], line[-1]])[0]
        assert geo.inside(mid[:2], a.outer)


def test_medians_cross_each_grown_lot_twice_and_their_bands_are_8m():
    med = S.medians(LOTS, OPS)
    assert len(med) == 2 * len(LOTS)
    bands = S.median_bands(med, OPS)
    for line, band in zip(med, bands):
        assert abs(geo.area_m2(band) - SP.length(line) * S.MEDIAN_WIDTH_CM / 1e4) < 1e-6


def test_arrows_sit_beside_the_shortened_medians():
    med = S.medians(LOTS, OPS)
    side_a, side_b = S.arrow_lines(med)
    for m, a, b in zip(med, side_a, side_b):
        assert abs(SP.length(a) - (SP.length(m) - 2 * S.MEDIAN_TRUNC_CM)) < 1e-6
        # Transform_Truncate reverses: side A starts near the median's END
        assert math.dist(a[0][:2], m[-1][:2]) < S.MEDIAN_TRUNC_CM + 300.0
        assert math.dist(b[-1][:2], m[-1][:2]) < S.MEDIAN_TRUNC_CM + 300.0


# ---- geo.splines ---------------------------------------------------------------------------------------
def test_truncate_cuts_both_ends_and_reverses():
    path = [(0.0, 0.0, 0.0), (1000.0, 0.0, 0.0), (1000.0, 1000.0, 0.0)]
    out = SP.truncate(path, 500.0, 300.0)
    assert out == [(1000.0, 700.0, 0.0), (1000.0, 0.0, 0.0), (500.0, 0.0, 0.0)]
    # a path not longer than an offset keeps that side (the measured 978 cm run: 478 cm left)
    assert SP.truncate([(0.0, 0.0, 0.0), (978.0, 0.0, 0.0)], 500.0, 500.0) == [(978.0, 0.0, 0.0), (500.0, 0.0, 0.0)]
    assert SP.truncate([(0.0, 0.0, 0.0), (400.0, 0.0, 0.0)], 500.0, 500.0) == [(400.0, 0.0, 0.0), (0.0, 0.0, 0.0)]


def test_resample_fit_drops_lines_under_two_samples():
    line = lambda L: [(0.0, 0.0, 0.0), (L, 0.0, 0.0)]     # noqa: E731
    assert SP.resample_fit(line(349.0), 350.0) == []
    assert SP.resample_fit(line(699.0), 350.0) == []                       # one sample: no spline
    assert [p[0] for p in SP.resample_fit(line(899.0), 350.0)] == [0.0, 899.0]
    pts = SP.resample_fit(line(3499.0), 350.0)
    assert len(pts) == 9 and abs(pts[1][0] - 3499.0 / 8) < 1e-9
    assert len(SP.resample_fit(line(3500.0), 350.0)) == 10


def test_chord_subdivide_offset_pairs_center():
    path = [(0.0, 0.0, 0.0), (300.0, 0.0, 0.0), (600.0, 10.0, 0.0)]
    assert SP.chord(path) == [(0.0, 0.0, 0.0), (600.0, 10.0, 0.0)]
    sub = SP.subdivide([(0.0, 0.0, 0.0), (600.0, 0.0, 0.0)], 5)
    assert [p[0] for p in sub] == [0.0, 100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
    off = SP.offset_local([(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)], -100.0, 200.0)
    assert all(abs(a - b) < 1e-9 for p, q in zip(off, [(-100.0, 200.0, 0.0), (0.0, 200.0, 0.0)]) for a, b in zip(p, q))
    assert SP.pairs(path) == [[path[0], path[1]], [path[1], path[2]]]
    loc, yaw = SP.center([(0.0, 0.0, 0.0), (0.0, 350.0, -2.0)])
    assert loc == (0.0, 175.0, -1.0) and abs(yaw - 90.0) < 1e-12
    assert SP.control_yaws([(0.0, 0.0), (0.0, 1.0), (-1.0, 1.0)]) == [90.0, 180.0, 180.0]


def test_follow_subjects_orders_and_restarts_the_rings():
    subjects = [box(0, 0, 10, 10), box(100, 0, 110, 10)]
    shrunk = [Polygon([(101, 9), (101, 1), (109, 1), (109, 9)]), Polygon([(9, 1), (9, 9), (1, 9), (1, 1)])]
    out = A.follow_subjects(shrunk, subjects)
    assert [p.outer[0] for p in out] == [(1, 1), (101, 1)]
    assert out[0].outer == [(1, 1), (9, 1), (9, 9), (1, 9)] or out[0].outer[0] == (1, 1)


# ---- the finish node -----------------------------------------------------------------------------------
def test_finish_lifts_projects_and_twins_every_vehicle():
    car, tile = Points(), Points()
    for p in (car, tile):
        p.declare("Asset", "SoftObjectPath")
    car.add((0.0, 0.0, 5.0), rot=(0.0, 30.0, 0.0), Asset=S.CARS[0])
    tile.add((100.0, 0.0, -19.0), Asset=S.TILE_MESH)
    out, notes = F.finish([tile, car], FlatTerrain(1000.0))
    assert [len(p) for p in out] == [1, 1, 1]                 # the vehicles, the rest, the twins
    veh, rest, twin = out
    assert veh.attrs["Asset"] == [S.CARS[0]] and rest.attrs["Asset"] == [S.TILE_MESH]
    assert twin.attrs["Asset"] == ["/Game/Vehicle/vehCar_vehicle02/Mesh/Transparent/SM_All_Trans_vehCar_vehicle02."
                                   "SM_All_Trans_vehCar_vehicle02"]
    assert twin.attrs["AssetString"] == twin.attrs["Asset"]
    assert veh.loc[0] == (0.0, 0.0, 1000.0 + 5.0 + F.LIFT_CM) == twin.loc[0]
    assert rest.loc[0][2] == 1000.0 - 19.0 + F.LIFT_CM
    assert abs(veh.rot[0][1] - 30.0) < 1e-9


def test_finish_lifts_along_the_tilted_up_axis():
    class Slope:                                   # z = x tan(10 deg): a tile tilts 10 deg about Y
        def height(self, x, y):
            return x * math.tan(math.radians(10.0))
    p = Points()
    p.declare("Asset", "SoftObjectPath")
    p.add((0.0, 0.0, 0.0), bounds_min=(-100.0, -100.0, -10.0), bounds_max=(100.0, 100.0, 10.0), Asset=S.TILE_MESH)
    out, _ = F.finish([p], Slope())
    x, y, z = out[0].loc[0]
    s = math.sin(math.radians(10.0)) * F.LIFT_CM
    assert abs(x + s) < 1e-6 and abs(y) < 1e-6 and abs(z - math.cos(math.radians(10.0)) * F.LIFT_CM) < 1e-6


def test_finish_miss_keeps_the_point_at_density_zero():
    class Hole:
        def height(self, x, y):
            return None
    p = Points()
    p.declare("Asset", "SoftObjectPath")
    p.add((0.0, 0.0, 10.0), Asset=S.LINE_MESH)
    out, _ = F.finish([p], Hole())
    assert out[0].density == [0.0] and out[0].loc[0][2] == 20.0 + F.LIFT_CM
