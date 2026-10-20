"""Stage 1, Terrain (Task 24; spec 3, Step B).

The contract against the official IR (parameters, the scene reads, the kept write and the three native per-point
nodes, the Python pins), empty inputs on both Python nodes, every Python step against the official taps
(`Tools/pypcg/data/s01_fixture.json`, distilled by `Tools/pypcg/s01_fixture.py` from the official graph run as a
tap graph), the task's invariants as s01.md 5 corrects them (with planted faults), V1's partial replay offline, and
the seeded repeat (the stage draws nothing: `RANDOM = False`). Offline there is no engine boolean, so the square
less the circle uses `BoxHoleOps` below (a box, and a ring inside it as its hole); the real booleans are checked
live by V1 and by the slim tap graph (s01.md 6)."""
import json
import os

import pytest

from pypcg import geo, stage_api
from pypcg.checks import s01 as K
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import ground as G
from pypcg.stages import s01_terrain as S
from pypcg.stages import s01_terrain_blend as B

REPO = stage_api.REPO
DATA = os.path.join(REPO, "Tools", "pypcg", "data")


def official_ir():
    with open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_1_1_Terrain.json"), encoding="utf-8") as fh:
        return json.load(fh)


def official(name):
    return next(n for n in official_ir()["nodes"] if n["name"] == name)


def fixture():
    with open(os.path.join(REPO, "Tools", "pypcg", "data", "s01_fixture.json"), encoding="utf-8") as fh:
        return json.load(fh)


class BoxHoleOps:
    """Offline booleans for this stage's shapes only: `offset` grows a box, `difference` cuts rings lying inside the
    subject out as holes, `intersection` keeps a ring inside the clip box whole (and clips a box to a box)."""

    @staticmethod
    def _box(ring):
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        return min(xs), min(ys), max(xs), max(ys)

    def offset(self, rings, distance, join="square", miter_limit=2.0):
        x0, y0, x1, y1 = self._box(rings[0])
        d = distance
        return [Polygon([(x0 - d, y0 - d), (x1 + d, y0 - d), (x1 + d, y1 + d), (x0 - d, y1 + d)])]

    def difference(self, rings_a, rings_b):
        bx = self._box(rings_a[0])
        holes = [list(reversed(geo.ccw(r))) for r in rings_b
                 if bx[0] <= self._box(r)[0] and self._box(r)[2] <= bx[2] and bx[1] <= self._box(r)[1]
                 and self._box(r)[3] <= bx[3]]
        return [Polygon(list(rings_a[0]), list(rings_a[1:]) + holes)]

    def intersection(self, rings_a, rings_b):
        cx = self._box(rings_b[0])
        out = []
        for r in rings_a:
            b = self._box(r)
            if cx[0] <= b[0] and b[2] <= cx[2] and cx[1] <= b[1] and b[3] <= cx[3]:
                out.append(Polygon(geo.ccw(r)))
        return out


def params(module, **kw):
    p = stage_api.defaults(module)
    p.update(kw)
    return p


def _spline(d, cls=Spline):
    return cls([tuple(p) for p in d["points"]], closed=d["closed"], linear=d["linear"],
               tangents=[(tuple(a), tuple(b)) for a, b in d["tangents"]] if d.get("tangents") else None,
               polyline=[tuple(p) for p in d["polyline"]] if d.get("polyline") else None)


def _edge_points(fx):
    f = fx["extract"]["fields"]
    p = Points()
    for loc in fx["extract"]["edge"]:
        p.add(tuple(loc), rot=tuple(f["rot"][0]), scale=tuple(f["scale"][0]), bounds_min=tuple(f["bounds_min"][0]),
              bounds_max=tuple(f["bounds_max"][0]), color=tuple(f["color"][0]), density=f["density"][0],
              steepness=f["steepness"][0])
    return p


def first_inputs(fx=None):
    fx = fx or fixture()
    return {"MeshTerrain": [(_edge_points(fx), frozenset(["Type:Point"]))],
            "TerrainShaping": [(_spline(fx["circle"]["t07"]), frozenset(["Terrain_shaping_1"]))],
            "City": [(_spline(fx["city"]["t11"]), frozenset(["City"]))]}


def _points(locs, sp=None):
    p = Points()
    if sp is not None:
        p.declare("SourcePositions", "Vector")
    for i, loc in enumerate(locs):
        kw = {"SourcePositions": tuple(sp[i])} if sp is not None else {}
        p.add(tuple(loc), **kw)
    return p


def blend_inputs(fx=None):
    s = (fx or fixture())["sample"]
    return {"Hills": [(_points(s["flat"], s["source_positions"]), frozenset())],
            "City": [(_points(s["city"], s["source_positions"]), frozenset())]}


# ---- contract -------------------------------------------------------------------------------------------------
def _graph():
    from pypcg import graphs, ir
    from pypcg.profiles import official as prof
    doc = graphs.graph(1).to_ir(prof)                     # raises on an unwired Python input pin
    by = {x["name"]: x for x in doc["nodes"]}
    py = {x["title"]: x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE}
    return doc, by, py


def _feeds(node, by):
    return {p["label"]: [(by[e[0]], e[1]) for e in p["edges"]] for p in node["inputs"]}


def _titled(doc, name):
    return next(x for x in doc["nodes"] if x.get("title") == official(name)["title"])


def _param(name):
    return next(p for p in official_ir()["params"] if p["name"] == name)


def test_contract_parameters():
    assert {p["name"] for p in official_ir()["params"]} == {"CityFlatness", "HillsHeight"}
    p = B.PARAMS["CityFlatness"]
    assert (p.type, p.default) == (_param("CityFlatness")["type"], _param("CityFlatness")["value"])
    assert p.tooltip == _param("CityFlatness")["meta"]["ToolTip"]
    assert S.PARAMS == {} and list(B.PARAMS) == ["CityFlatness"] and not S.RANDOM and not B.RANDOM
    doc, _by, _py = _graph()
    got = [(q["name"], q["type"], q["value"]) for q in doc["params"]]
    assert got == [(stage_api.SEED, "Int32", stage_api.SEED_DEFAULT),
                   ("CityFlatness", "Float", 0.5), ("HillsHeight", "Float", 7001)]


def test_contract_reads_write_and_native_nodes_as_officially_set():
    doc, _by, _py = _graph()

    def key(n):
        return (n.get("subgraph"), json.dumps(n.get("overrides") or {}, sort_keys=True), n.get("title") or "")
    names = ("GetMeshTerrain_0", "ExtractMeshTerrainPoints_0", "GetActorData_TerrainShaping1", "Subgraph_3",
             "SpatialNoise_Hills", "FlattenProject_AroundCircle", "Subgraph_5", "WriteMeshTerrain_0")
    for name in names:
        assert key(official(name)) in [key(x) for x in doc["nodes"] if x["class"] == "PCGSubgraphSettings"], name
    assert len([x for x in doc["nodes"] if x["class"] == "PCGSubgraphSettings"]) == len(names)
    # the ten mask and blend nodes are gone into Python; the official getters are the slim graph's own
    for name in ("Subgraph_0", "Subgraph_1", "Subgraph_2", "Subgraph_4", "Subgraph_6", "TraceBoundFootprint_TerrainShaping1",
                 "ComposeExclusion_SquareMinusCircle", "AttributeMathsOp_0", "AttributeMathsOp_1", "AttributeMathsOp_2"):
        assert official(name)["title"] not in [x.get("title") for x in doc["nodes"]] or official(name)["title"] == "", name


def test_contract_python_inputs_and_outputs_are_wired():
    doc, by, py = _graph()
    assert set(py) == {"Python: s01_terrain", "Python: s01_terrain_blend"}
    a, b = py["Python: s01_terrain"], py["Python: s01_terrain_blend"]
    fa = _feeds(a, by)
    for pin, name in (("MeshTerrain", "ExtractMeshTerrainPoints_0"), ("TerrainShaping", "GetActorData_TerrainShaping1"),
                      ("City", "Subgraph_3")):
        assert [n["title"] for n, _p in fa[pin]] == [official(name)["title"]], pin
    extract = _titled(doc, "ExtractMeshTerrainPoints_0")
    assert [n["title"] for n, _p in _feeds(extract, by)["PrimaryInput"]] == [official("GetMeshTerrain_0")["title"]]
    noise = _titled(doc, "SpatialNoise_Hills")
    fn = _feeds(noise, by)
    assert [n["name"] for n, _p in fn["PrimaryInput"]] == [extract["name"]]
    assert [p for _n, p in fn["NoiseAmplitude"]] == ["HillsHeight"]
    flat, city = _titled(doc, "FlattenProject_AroundCircle"), _titled(doc, "Subgraph_5")
    ff, fc = _feeds(flat, by), _feeds(city, by)
    assert [n["name"] for n, _p in ff["PrimaryInput"]] == [noise["name"]]
    assert [(n["title"], p) for n, p in ff["SecondaryInput"]] == [("Python: s01_terrain", "FlattenArea")]
    assert [n["name"] for n, _p in fc["PrimaryInput"]] == [flat["name"]]
    assert [(n["title"], p) for n, p in fc["SecondaryInput"]] == [("Python: s01_terrain", "CityFlatZone")]
    fb = _feeds(b, by)
    assert [n["name"] for n, _p in fb["Hills"]] == [flat["name"]] and [n["name"] for n, _p in fb["City"]] == [city["name"]]
    assert "CityFlatness" in [p for _n, p in fb["Params"]]
    write = _titled(doc, "WriteMeshTerrain_0")
    assert [(n["title"], p) for n, p in _feeds(write, by)["PrimaryInput"]] == [("Python: s01_terrain_blend", "Terrain")]
    out = by["DefaultOutputNode"]
    assert [(by[e[0]]["name"], e[1]) for p in out["inputs"] for e in p["edges"]] == [(write["name"], "Out")]
    # the official chain these replace, read from the IR (so a changed official graph fails here)
    assert [e[0] for e in official("SpatialNoise_Hills")["inputs"][0]["edges"]] == ["ExtractMeshTerrainPoints_0"]
    ofl = {p["label"]: [e[0] for e in p["edges"]] for p in official("FlattenProject_AroundCircle")["inputs"]}
    assert ofl["PrimaryInput"] == ["SpatialNoise_Hills"] and ofl["SecondaryInput"] == ["ComposeExclusion_SquareMinusCircle"]
    oc = {p["label"]: [e[0] for e in p["edges"]] for p in official("Subgraph_5")["inputs"]}
    assert oc["PrimaryInput"] == ["FlattenProject_AroundCircle"] and oc["SecondaryInput"] == ["Subgraph_4"]
    ol = {p["label"]: [e[0] for e in p["edges"]] for p in official("AttributeMathsOp_0")["inputs"]}
    assert ol == {**ol, "InA": ["FlattenProject_AroundCircle"], "InB": ["Subgraph_5"], "Ratio": ["AttributeMathsOp_1"]}


def test_contract_constants_are_the_official_ones():
    assert official("Subgraph_2")["overrides"]["Expand"] == S.EXPAND_CM
    for name in ("Subgraph_0", "Subgraph_6"):
        o = official(name)["overrides"]
        assert o["offset"] == {"X": 0, "Y": 0, "Z": S.DOWN_CM} and o["PerPoints"] is False
    assert official("Subgraph_4")["overrides"]["offset"] == {"X": 0, "Y": 0, "Z": S.CITY_UP_CM}
    t = official("TraceBoundFootprint_TerrainShaping1")["overrides"]
    assert t["PlanarSurface"] == "Top" and t["ScaleFactor"] == {"X": 1, "Y": 1, "Z": 1} and G.PLANE_TOP == 1.0
    a2 = official("AttributeMathsOp_2")
    assert a2["settings"]["Operation"] == "Set" and a2["settings"]["InputSource1"] == "PCGBegin($Position.Z)PCGEnd"
    assert [d["prop"] for d in a2["pin_defaults"]] == ["DefaultValue2"] and S.CITY_Z_CM == 0.0
    assert official("AttributeMathsOp_1")["settings"]["Operation"] == "OneMinus"
    a0 = official("AttributeMathsOp_0")["settings"]
    assert (a0["Operation"], a0["InputSource1"], a0["InputSource2"]) == ("Lerp", "PCGBegin($Position)PCGEnd",
                                                                         "PCGBegin($Position)PCGEnd")


# ---- empty inputs --------------------------------------------------------------------------------------------
def test_empty_inputs_first_node():
    out, ctx = stage_api.execute(S, {"MeshTerrain": [], "TerrainShaping": [], "City": []}, params(S), BoxHoleOps())
    assert out == {"FlattenArea": [], "CityFlatZone": []}
    assert any("no terrain points" in n for n in ctx.notes)


def test_empty_inputs_second_node():
    out, ctx = stage_api.execute(B, {"Hills": [], "City": []}, params(B), BoxHoleOps())
    assert out == {"Terrain": []}
    out, _ctx = stage_api.execute(B, {"Hills": blend_inputs()["Hills"], "City": []}, params(B), BoxHoleOps())
    assert out == {"Terrain": []}


def test_no_terrain_no_area_but_the_city_zone_still_goes_out():
    ins = first_inputs()
    ins["MeshTerrain"] = []
    out, _ctx = stage_api.execute(S, ins, params(S), BoxHoleOps())
    assert out["FlattenArea"] == [] and len(out["CityFlatZone"]) == 1


def test_no_shaping_circle_flattens_the_whole_square():
    ins = first_inputs()
    ins["TerrainShaping"] = []
    out, _ctx = stage_api.execute(S, ins, params(S), BoxHoleOps())
    (p, _t), = out["FlattenArea"]
    assert p.holes == [] and p.z == -599.0 + S.DOWN_CM


# ---- every Python step against the official taps ---------------------------------------------------------------
def test_footprint_is_the_official_one_bit_for_bit():
    fx = fixture()
    x0, y0, x1, y1, z = S.footprint([_edge_points(fx)])
    corners = {(p[0], p[1]) for p in fx["footprint"]["t04"]["points"]}
    assert corners == {(x0, y0), (x1, y0), (x1, y1), (x0, y1)}
    assert {p[2] for p in fx["footprint"]["t04"]["points"]} == {z} == {-599.0}
    assert fx["footprint"]["t03_bounds"] == [[(x0 + x1) / 2, (y0 + y1) / 2, -600.0]]


def test_bounds_footprint_planes_are_the_tables_rows():
    p = Points()
    p.add((0.0, 0.0, 10.0), bounds_min=(-1.0, -2.0, -3.0), bounds_max=(1.0, 2.0, 5.0))
    assert G.bounds_footprint([p], G.PLANE_BOTTOM) == (-1.0, -2.0, 1.0, 2.0, 7.0)
    assert G.bounds_footprint([p], G.PLANE_CENTER) == (-1.0, -2.0, 1.0, 2.0, 11.0)
    assert G.bounds_footprint([p], G.PLANE_TOP) == (-1.0, -2.0, 1.0, 2.0, 15.0)
    assert G.bounds_footprint([]) is None


def test_flatten_area_is_the_grown_lowered_square_less_the_circle():
    fx = fixture()
    out, _ctx = stage_api.execute(S, first_inputs(fx), params(S), BoxHoleOps())
    (p, tags), = out["FlattenArea"]
    assert tags == ["FlattenArea"] and p.z == fx["annulus"]["z"] == fx["footprint"]["t06"]["z"]
    xs, ys = [q[0] for q in p.outer], [q[1] for q in p.outer]
    want = [[min(q[0] for q in fx["annulus"]["outer"]), min(q[1] for q in fx["annulus"]["outer"])],
            [max(q[0] for q in fx["annulus"]["outer"]), max(q[1] for q in fx["annulus"]["outer"])]]
    assert max(abs(a - b) for a, b in zip([min(xs), min(ys), max(xs), max(ys)], want[0] + want[1])) < 1e-6
    assert len(p.holes) == 1 and len(p.holes[0]) == len(fx["annulus"]["holes"][0]) == 1185
    # the hole is the circle's polyline; the official one is CreatePolygon2D's: the same outline to 0.11 cm
    hole = {(round(q[0], 0), round(q[1], 0)) for q in p.holes[0]}
    near = sum(1 for q in fx["annulus"]["holes"][0] if (round(q[0], 0), round(q[1], 0)) in hole)
    assert near > 0.5 * len(hole)
    assert abs(geo.area_m2(p) - fx["stats"]["annulus_area_m2"]) < 1.0
    assert K.check_masks(S.footprint([_edge_points(fx)]), first_inputs(fx)["TerrainShaping"], [p], BoxHoleOps()) == []


def test_city_flat_zone_is_the_official_one():
    fx = fixture()
    zone = S.city_flat_zone(first_inputs(fx)["City"])
    (s,) = zone
    assert [list(q) for q in s.points] == fx["city"]["t13"]["points"]
    assert s.closed and not s.linear
    # the official Set $Position.Z re-writes the tangents through the world accessor: <= 5e-7 cm off the input's
    off = max(abs(a[k] - b[k]) for (ta, tb) in zip(s.tangents, fx["city"]["t13"]["tangents"])
              for a, b in ((ta[0], tb[0]), (ta[1], tb[1])) for k in range(3))
    assert off < 1e-6
    assert K.check_zone(first_inputs(fx)["City"], zone) == []


def test_blend_is_the_official_lerp_bit_for_bit():
    fx = fixture()
    ins = blend_inputs(fx)
    out, ctx = stage_api.execute(B, ins, params(B, CityFlatness=0.6000000238418579), BoxHoleOps())
    (p, tags), = out["Terrain"]
    assert tags == ["Terrain"] and [list(q) for q in p.loc] == fx["sample"]["final"]
    assert p.attrs["SourcePositions"] == [tuple(q) for q in fx["sample"]["source_positions"]]
    assert B.ratio(0.6000000238418579) == fx["ratio"]["None"] and ctx.notes[0] == "ratio %r" % fx["ratio"]["None"]
    assert K.check_blend(ins["Hills"][0][0], ins["City"][0][0], p, 0.6000000238418579) == []


def test_city_flatness_one_keeps_the_hills_and_zero_flattens():
    ins = blend_inputs()
    hills, city = ins["Hills"][0][0], ins["City"][0][0]
    (keep,), _n = B.blend(ins["Hills"], ins["City"], 1.0)
    (flat,), _n = B.blend(ins["Hills"], ins["City"], 0.0)
    assert keep.loc == hills.loc and flat.loc == city.loc


def test_blend_broadcasts_one_city_point_and_refuses_a_mismatch():
    hills = _points([(0.0, 0.0, 0.0), (1.0, 0.0, 10.0)])
    (out,), _n = B.blend([(hills, frozenset())], [(_points([(0.0, 0.0, 100.0)]), frozenset())], 0.5)
    assert [q[2] for q in out.loc] == [50.0, 55.0]
    res, notes = B.blend([(hills, frozenset())], [(_points([(0.0, 0.0, 1.0)] * 3), frozenset())], 0.5)
    assert res == [] and any("cannot pair" in n for n in notes)


# ---- the task's invariants (s01.md 5) with planted faults ------------------------------------------------------
def _terrain_case(fx):
    s = fx["sample"]
    final = [q[2] for q in s["final"]]
    hills = [q[2] for q in s["flat"]]
    flat = [q[2] for q in s["city"]]
    ring = [(q[0], q[1]) for q in fx["city"]["t13"]["polyline"]]
    inside = [i for i, q in enumerate(s["final"]) if geo.inside((q[0], q[1]), ring)]
    r = [((q[0] ** 2 + q[1] ** 2) ** 0.5) for q in s["final"]]
    core = [i for i, d in enumerate(r) if d < 50000.0]
    outer = [i for i, d in enumerate(r) if d > 140000.0]
    return final, hills, flat, inside, core, outer


def test_terrain_invariants_hold_on_the_official_sample():
    fx = fixture()
    final, hills, flat, inside, core, outer = _terrain_case(fx)
    assert len(inside) > 50 and core and outer
    assert K.check_terrain(len(final), final, hills, flat, inside, 0.6000000238418579, core, outer) == []
    st = fx["stats"]
    assert st["counts"]["t16_lerp"] == st["counts"]["t01_extract"] == fx["step_a_plus"]["stage_points"] == 261312
    assert st["core_mean_z"] - st["outer_ring_mean_z"] > K.OUTER_RING_GAP_CM
    lo, hi, _m = st["city_flat_z"]
    assert abs(lo - 3000.0) < K.CITY_PLANE_TOL_CM and abs(hi - 3000.0) < K.CITY_PLANE_TOL_CM
    # the brief's "spread under 500 cm" is false officially: the spread is CityFlatness x the hills'
    z_lo, z_hi, z_mean = st["city_z"]
    h_lo, h_hi, h_mean = st["city_hills_z"]
    assert z_hi - z_lo > 4000.0 and abs((z_hi - z_lo) - 0.6 * (h_hi - h_lo)) < 5.0
    assert abs(z_mean - (0.6000000238418579 * h_mean + 0.3999999761581421 * st["city_flat_z"][2])) < 0.01


@pytest.mark.parametrize("fault", ["count", "not_blended", "plane", "flat_outer_ring"])
def test_terrain_invariants_catch_planted_faults(fault):
    fx = fixture()
    final, hills, flat, inside, core, outer = _terrain_case(fx)
    n = len(final)
    if fault == "count":
        n += 1
    elif fault == "not_blended":
        final = list(final)
        final[inside[0]] += 1e-9 * max(1.0, abs(final[inside[0]]))
    elif fault == "plane":
        flat = list(flat)
        flat[inside[0]] = 3010.0
    elif fault == "flat_outer_ring":
        final = list(final)
        for i in outer:
            final[i] = sum(final[j] for j in core) / len(core)
    assert K.check_terrain(n, final, hills, flat, inside, 0.6000000238418579, core, outer) != []


@pytest.mark.parametrize("fault", ["moved", "wrong_ratio", "attribute"])
def test_blend_check_catches_planted_faults(fault):
    ins = blend_inputs()
    hills, city = ins["Hills"][0][0], ins["City"][0][0]
    (out,), _n = B.blend(ins["Hills"], ins["City"], 0.6000000238418579)
    cf = 0.6000000238418579
    if fault == "moved":
        out.loc[3] = (out.loc[3][0], out.loc[3][1], out.loc[3][2] + 0.001)
    elif fault == "wrong_ratio":
        cf = 0.4
    elif fault == "attribute":
        out.attrs["SourcePositions"][0] = (0.0, 0.0, 0.0)
    assert K.check_blend(hills, city, out, cf) != []


@pytest.mark.parametrize("fault", ["z", "not_grown", "no_hole"])
def test_mask_check_catches_planted_faults(fault):
    fx = fixture()
    ins = first_inputs(fx)
    fp = S.footprint([_edge_points(fx)])
    (p,) = S.flatten_area(fp, ins["TerrainShaping"], BoxHoleOps())
    if fault == "z":
        p = Polygon(p.outer, p.holes, p.z + 1.0)
    elif fault == "not_grown":
        p = Polygon([(q[0] * 0.99, q[1] * 0.99) for q in p.outer], p.holes, p.z)
    elif fault == "no_hole":
        p = Polygon(p.outer, [], p.z)
    assert K.check_masks(fp, ins["TerrainShaping"], [p], BoxHoleOps()) != []


def test_zone_check_catches_a_city_left_at_ground_level():
    ins = first_inputs()
    (s,) = S.city_flat_zone(ins["City"])
    s.points[0] = (s.points[0][0], s.points[0][1], 0.0)
    assert K.check_zone(ins["City"], [s]) != []


# ---- V1 offline: the partial replay ------------------------------------------------------------------------------
def _record(fx):
    ins = first_inputs(fx)
    out, ctx = stage_api.execute(S, ins, params(S), BoxHoleOps())
    return {"stage": 1, "params": params(S), "notes": ctx.notes,
            "inputs": {pin: [[geo.to_json(v), sorted(t)] for v, t in items] for pin, items in ins.items()},
            "outputs": {pin: [[geo.to_json(v), list(t)] for v, t in items] for pin, items in out.items()}}


def test_v1_partial_replay_passes_on_a_record():
    rec = json.loads(json.dumps(_record(fixture())))
    assert K.footprint_of(rec["notes"]) == S.footprint([_edge_points(fixture())])
    assert K.check_record(rec, BoxHoleOps()) == []


@pytest.mark.parametrize("fault", ["area", "zone", "no_footprint"])
def test_v1_partial_replay_catches_planted_faults(fault):
    rec = json.loads(json.dumps(_record(fixture())))
    if fault == "area":
        rec["outputs"]["FlattenArea"][0][0]["z"] += 1.0
    elif fault == "zone":
        rec["outputs"]["CityFlatZone"][0][0]["points"][0][2] = 0.0
    elif fault == "no_footprint":
        rec["notes"] = [n for n in rec["notes"] if not n.startswith("footprint ")]
    assert K.check_record(rec, BoxHoleOps()) != []


# ---- the tap comparison's committed evidence (Task 24 fix round 1) -------------------------------------------
def _data(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def test_tap_comparison_is_bit_exact():
    """The comparison s01.md 6 rests on: the official tap and the slim tap of stage 1, every point position of the
    hills, the flattened set, the city projection and the final write, and the `SourcePositions` the terrain writer
    reads (four sets of 261 312 points each). `Tools/pypcg/s01_compare.py` distils it; the taps themselves are
    committed gzipped beside it (`s01_tap_official.json.gz`, `s01_tap_slim.json.gz`). If any position ever differs
    this test fails with the numbers rather than claiming zero."""
    c = _data("s01_tap_comparison.json")
    s = c["summary"]
    assert s["point_sets"] == 4 and set(s["contained_in"]) == {"t09_annulus", "t13_city_up"}
    assert s["positions_compared"] == 4 * 261312 == s["positions_equal"], (
        "%d of %d positions equal, max difference %r cm" % (s["positions_equal"], s["positions_compared"],
                                                           s["max_abs_cm"]))
    assert s["max_abs_cm"] == 0.0
    assert s["source_positions_compared"] == 4 * 261312 == s["source_positions_equal"]
    for tag, row in c["pairs"].items():
        assert row.get("loc", {}).get("max_abs") in (0.0, None), tag
        assert row.get("loc", {}).get("equal") == row.get("loc", {}).get("compared"), tag
        if row.get("plain_attributes"):
            assert row["plain_attributes_equal"], tag
    # the shapes: the same area to 2e-4 cm2, the same outer bounds to 2.4e-10 cm, the hole (1 185 vertices) to
    # 0.11 cm, the city control points equal and the tangents within 5e-7 cm (s01.md 3)
    a = c["pairs"]["t09_annulus"]
    assert a["z"][0] == a["z"][1] and a["holes"][0] == a["holes"][1] == [1185]
    assert a["outer_area_abs_diff"] < 1e-3 and a["outer_bounds_max_abs"] < 1e-9 and a["hole_bounds_max_abs"] < 0.2
    z = c["pairs"]["t13_city_up"]
    assert z["points_equal"] and z["tangents_max_abs"] < 1e-6 and z["polyline"]["max_abs"] < 1e-6
    # the taps are committed, and the summary says where it came from
    for name in ("s01_tap_official.json.gz", "s01_tap_slim.json.gz"):
        assert os.path.getsize(os.path.join(DATA, name)) > 1000, name
    assert "pypcg_s01_taps.py" in c["source"]


def test_tap_comparison_sample_repeats_the_summary():
    """The every-40th-point sample of the same taps (committed with its own comparison): an offline replay of the
    comparison on 26 132 positions, all equal."""
    c = _data("s01_tap_sample.json")
    s = c["summary"]
    assert s["point_sets"] == 4 and s["positions_compared"] == 4 * len(range(0, 261312, 40))
    assert s["positions_equal"] == s["positions_compared"] and s["max_abs_cm"] == 0.0
    assert s["source_positions_equal"] == s["source_positions_compared"]


def test_native_measurements_hold_the_step_f_thresholds():
    """s01.md 0's reason for keeping three nodes native: the blur takes 445 s and each projection 36 s in Python. A
    re-measure that halves either must fail here instead of leaving the note stale; Step F's budget is 60 s."""
    m = _data("s01_native_measurements.json")
    assert m["blur"]["seconds_two_iterations"] > 60.0
    assert m["project"]["python_seconds_per_projection"] > 10.0
    p = m["project"]
    assert p["bit_exact"] < p["points"] and p["max_abs_cm"] < 0.01     # the GPU's distance is not reproducible
    assert set(p["ulp_offsets_of_the_rest"]) <= {"1", "-1", "2", "-2", "3", "-3", "None"}
    assert m["lerp"]["bit_exact"] == m["lerp"]["components"] == 3 * 261312


def test_the_offline_measure_is_not_in_the_test_tree():
    """`s01_measure_offline.py` needs numpy; only the measurement tool imports it, never a stage or a test. The test
    run is `pytest Tools/pypcg/tests`, whose glob is `test_*.py` under this directory: the tool is not there under
    either name, and no module of the tree imports it."""
    tool = os.path.join(REPO, "Tools", "pypcg", "s01_measure_" + "offline.py")
    assert os.path.exists(tool)
    here = os.path.dirname(os.path.abspath(__file__))
    assert os.path.dirname(tool) != here
    stem = os.path.basename(tool)[:-3]
    assert not [n for n in os.listdir(here) if n.startswith(stem)]
    for name in os.listdir(here):
        if name.endswith(".py"):
            with open(os.path.join(here, name), encoding="utf-8") as fh:
                assert ("import " + stem) not in fh.read(), name
    for name in ("s01_terrain.py", "s01_terrain_blend.py"):
        with open(os.path.join(REPO, "Content", "Python", "pypcg", "stages", name), encoding="utf-8") as fh:
            assert "numpy" not in fh.read(), name


# ---- seeded runs ---------------------------------------------------------------------------------------------------
def test_seeded_runs_repeat_and_draw_nothing():
    """`RANDOM = False`: the same inputs give the same outputs, whatever the seed (the native noise draws from its
    own node seed, not from the Python one)."""
    a, _ = stage_api.execute(S, first_inputs(), params(S, Seed=7), BoxHoleOps())
    b, _ = stage_api.execute(S, first_inputs(), params(S, Seed=7), BoxHoleOps())
    c, _ = stage_api.execute(S, first_inputs(), params(S, Seed=13), BoxHoleOps())
    j = [{k: [geo.to_json(v) for v, _t in items] for k, items in o.items()} for o in (a, b, c)]
    assert j[0] == j[1] == j[2]
    x, _ = stage_api.execute(B, blend_inputs(), params(B, Seed=7), BoxHoleOps())
    y, _ = stage_api.execute(B, blend_inputs(), params(B, Seed=977), BoxHoleOps())
    assert x["Terrain"][0][0].loc == y["Terrain"][0][0].loc
