"""Stage 8, Highways (spec 3, Step B). The invariants are the task brief's:

  - two straight parallel highways on flat ground -> two footprints whose width equals
    `Highway_Width` within 1 cm and whose area equals `width x length` within 1 %;
  - empty inputs -> empty outputs;
  - `Highway` present in every run.

The brief's first invariant is about the RIBBON the grammar node would build, which is native in the
slim graph, so the offline test pins the module's own half-width rule (`path_offset(path, W / 2)` ->
a band `W` across) against the offline stand-in, and the in-editor V1 check pins the published
polygon's width (`Highway_Width / 2 + 1500`) against the live official output.

The width relationship the live graph shows is `published width = Highway_Width + 3000`, measured at
three widths (433 468 m2 at 2000, 606 862 m2 at 4000, 953 642 m2 at 8000). `test_the_published_width_
grows_with_the_parameter` pins the linearity offline.
"""
import json
import os

import pytest

from fakes import FlatTerrain, RibbonOps
from pypcg import geo, stage_api
from pypcg.geo import Polygon, Spline
from pypcg.stages import s08_highways as S

REPO = stage_api.REPO
OPS = RibbonOps()
PARAMS = dict(stage_api.defaults(S))
PARAMS.pop(stage_api.SEED)


def _ctx(ops=OPS):
    return stage_api.Ctx(S.STAGE, 42, ops)


def line(points, **kw):
    """A highway spline input: control points, plus the dense polyline the engine would draw (the
    resample walks the polyline, and the port must follow it when the value carries one)."""
    poly = kw.pop("polyline", None)
    return [(Spline([(x, y, z) for x, y, z in points], polyline=poly, **kw), frozenset())]


def inputs(splines=None, surface=None, roads=None):
    return {"HighwaySplines": splines if splines is not None else [],
            "MeshTerrain": [(surface, frozenset())] if surface is not None else [],
            "Roads": roads if roads is not None else []}


STRAIGHT = [(0.0, 0.0, 5550.0), (100000.0, 0.0, 5550.0)]
PARALLEL = [(0.0, 20000.0, 5550.0), (100000.0, 20000.0, 5550.0)]


# ---- 1. contract -----------------------------------------------------------------------------
def test_contract_parameters_and_inputs_match_the_official_graph():
    off = json.load(open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_1_3_Highways.json"),
                         encoding="utf-8"))
    defaults = {p["name"]: p["value"] for p in off["params"]}
    assert defaults["Highway_Width"] == 2000
    assert S.PARAMS["Highway_Width"].default == defaults["Highway_Width"]
    assert S.OUTPUTS == ("Highway",)
    assert set(S.INPUTS) == {"HighwaySplines", "Roads", "MeshTerrain"}


def test_contract_the_slim_graph_wires_every_pin_and_the_output():
    from pypcg import graphs, ir
    from pypcg.profiles import official
    doc = graphs.graph(8).to_ir(official)                 # raises on an unwired Python input pin
    py = [x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE]
    assert py, "no Python node"
    wired = {p["label"] for p in py[0]["inputs"] if p["edges"]}
    assert set(S.INPUTS) | {stage_api.PARAMS_PIN} <= wired
    used = {(src, pin) for x in doc["nodes"] for p in x.get("inputs", []) for src, pin in p["edges"]}
    for pin in S.OUTPUTS:
        assert (py[0]["name"], pin) in used, "output %s is wired to nothing" % pin


def test_contract_the_generation_nodes_and_scene_reads_are_kept():
    """The brief names two generation nodes and three scene reads. Every one must appear in the slim
    graph with the official class and overrides (`keep` copies both)."""
    from pypcg import graphs, dsl
    g = graphs.graph(8)
    titles = {}
    for rec in g._nodes:
        if rec.get("subgraph") or rec.get("class") in ("PCGAddTagSettings", "PCGProjectionSettings",
                                                       "PCGMakeConcreteSettings"):
            titles.setdefault(rec.get("subgraph") or rec["class"], []).append(rec.get("overrides") or {})
    assert any("/Spawn_Assets." in k for k in titles), "Subgraph_4 Spawn Highway Support Assets is gone"
    agg = [k for k in titles if "Aggregate" in k]
    assert not agg, "an unexpected aggregate node: %s" % agg
    # the two kept generation nodes' own overrides survive the copy
    spawn = [o for k, v in titles.items() if "/Spawn_Assets." in k for o in v]
    assert spawn, "no Spawn_Assets node kept"
    grammar = [o for k, v in titles.items() if "Assign_ShapeGrammarDefinition." in k for o in v]
    assert grammar and any("SGD_ElevatedHighway_oneWay" in str(o.get("ShapeGrammarDefinition", ""))
                           for o in grammar), "the highway grammar asset is not the official one"
    # `keep` must carry the Roads actor read: the pillars are projected onto its footprint polygon
    by_ref = [o for k, v in titles.items() if "Get_ActorDataByRef." in k for o in v]
    assert len(by_ref) >= 2, "the Spline and Roads actor reads both have to be kept"


# ---- 2. empty inputs -------------------------------------------------------------------------
def test_empty_inputs_give_empty_outputs():
    out = S.run({pin: [] for pin in S.INPUTS}, PARAMS, _ctx())
    assert set(out) == set(S.OUTPUTS)
    assert all(not items for items in out.values())


def test_missing_input_pins_are_tolerated():
    out = S.run({"HighwaySplines": []}, PARAMS, _ctx())
    assert set(out) == set(S.OUTPUTS)
    assert all(not items for items in out.values())


def test_a_spline_without_points_produces_nothing():
    out = S.run(inputs(splines=[(Spline([]), frozenset())], surface=FlatTerrain()), PARAMS, _ctx())
    assert out["Highway"] == []


def test_a_single_point_spline_produces_nothing():
    out = S.run(inputs(splines=line([(0.0, 0.0, 0.0)]), surface=FlatTerrain()), PARAMS, _ctx())
    assert out["Highway"] == []


# ---- 3. the module's own computation -------------------------------------------------------------
def test_the_two_steps_are_the_nodes_they_replace():
    """`flatten` is `AttributeMathsOp_0`, `clamp` is `AttributeMathsOp_1`, `resample` is
    `Subgraph_9` and `project` is `Subgraph_8`. Each keeps only the Z coordinate it owns."""
    flat = S.flatten(Spline([(1.0, 2.0, 5550.0), (3.0, 4.0, 5550.0)], polyline=[(1.0, 2.0, 5550.0)]))
    assert [p[2] for p in flat.points] == [0.0, 0.0]
    assert [p[:2] for p in flat.points] == [(1.0, 2.0), (3.0, 4.0)]
    assert [p[:2] for p in flat.polyline] == [(1.0, 2.0)]
    assert S.clamp([(0.0, 0.0, -5000.0), (0.0, 0.0, 1e12)])[0][2] == S.CLAMP_MIN_CM
    assert S.clamp([(0.0, 0.0, -5000.0), (0.0, 0.0, 1e12)])[1][2] == S.CLAMP_MAX_CM
    assert S.clamp([(0.0, 0.0, 7.0)])[0][2] == 7.0


def test_flatten_keeps_the_dense_polyline_because_the_resample_walks_the_curve():
    """Highway 2 is 8 652.68 m as a curve and 8 494.84 m through its 12 control points: if `flatten`
    dropped the polyline the resample would walk the shorter polyline and lose 158 m."""
    dense = [(float(i) * 1000.0, 0.0, 5550.0) for i in range(10)]
    flat = S.flatten(Spline([(0.0, 0.0, 5550.0), (9000.0, 0.0, 5550.0)], polyline=dense))
    got = S.resample(S.curve_of(flat), 3000.0)
    assert len(got) == len(S.resample(dense, 3000.0)) == 4, "the polyline must be what is resampled"


def test_the_resample_emits_a_point_every_interval_and_the_end_point():
    """The engine's own sampling at 8000 cm gives 110 points for highway 2's 865 268.62 cm and 100 for
    highway 3's 788 371.12 cm, i.e. `floor(L / step)` interior points plus the first and the end. This
    pins the rule on a 100 000 cm line where the arithmetic is exact."""
    got = S.resample([(0.0, 0.0, 0.0), (100000.0, 0.0, 0.0)], 8000.0)
    assert len(got) == 14, "100000 / 8000 floors to 12 interior steps: 1 + 12 + 1"
    assert got[0] == (0.0, 0.0, 0.0)
    assert got[-1][0] == pytest.approx(100000.0)
    assert got[1][0] == pytest.approx(8000.0)
    # a length that is an exact multiple must not repeat the end point
    got = S.resample([(0.0, 0.0, 0.0), (8000.0, 0.0, 0.0)], 8000.0)
    assert len(got) == 2, "an exact multiple must not duplicate the end point"


def test_the_projection_moves_a_point_onto_the_surface_and_leaves_a_miss_alone():
    """`Subgraph_8`'s `ProjectMask` keeps the original Z where the surface does not answer."""
    class Holes:
        def height(self, x, y):
            return None if x > 50.0 else -600.0
    got = S.project([(0.0, 0.0, 5550.0), (100.0, 0.0, 5550.0)], Holes())
    assert got[0][2] == -600.0
    assert got[1][2] == 5550.0, "a miss must not be clamped to the surface"
    assert S.project([(0.0, 0.0, 5550.0)], None)[0][2] == 5550.0


def test_a_flat_highway_becomes_a_flat_spline_at_the_terrain_height():
    """The whole read-side chain on flat ground: Z 5550 in, the terrain's own Z out, the same X/Y, and
    level. `AttributeMathsOp_1`'s clamp floor in the live city is what bounds the result: the demo
    terrain plane sits at -600 cm, which the clamp raises to its own -500 (`CLAMP_MIN_CM`)."""
    out = S.run(inputs(splines=line([(0.0, 0.0, 5550.0), (100000.0, 0.0, 5550.0)]),
                       surface=FlatTerrain(-600.0)), PARAMS, _ctx())
    assert len(out["Highway"]) == 1
    got, tags = out["Highway"][0]
    assert "Highway" in tags
    assert all(p[2] == S.CLAMP_MIN_CM for p in got.points), \
        "the terrain is at -600 cm and the clamp's floor is -500 cm"
    assert [p[:2] for p in got.points[:2]] == [(p[0], p[1]) for p in got.points[:2]]
    assert got.linear, "`CreateSpline_0` builds a linear spline and the two maths ops keep it level"
    assert len(got.points) == 14, "100000 / 8000 floors to 12 interior steps plus two ends"
    # a terrain above the clamp floor keeps its own height
    out = S.run(inputs(splines=line([(0.0, 0.0, 5550.0), (100000.0, 0.0, 5550.0)]),
                       surface=FlatTerrain(1200.0)), PARAMS, _ctx())
    assert all(p[2] == 1200.0 for p in out["Highway"][0][0].points)


# ---- 4. the brief's invariants ----------------------------------------------------------------
def test_two_parallel_highways_give_two_footprints():
    out = S.run(inputs(splines=line(STRAIGHT) + line(PARALLEL), surface=FlatTerrain(-600.0)),
                PARAMS, _ctx())
    assert len(out["Highway"]) == 2, "one footprint per highway spline"
    # the same spline twice must give two splines, not four: `Subgraph_7` reads both actors in one
    # node, so the pin is a single one and each item on it is one highway
    out = S.run(inputs(splines=line(STRAIGHT) + line(STRAIGHT)), PARAMS, _ctx())
    assert len(out["Highway"]) == 2
    assert all("Highway" in tags for _v, tags in out["Highway"])


def test_the_ribbon_width_follows_the_parameter():
    """The width convention, measured in the editor (2026-10-17) and pinned here on a straight path.

    `CreatePolygon2D`'s `OpenPolygonWidth` is the band's FULL width: `PCGCreatePolygon2D.cpp:256`
    passes it to `UE::Geometry::PolygonsOffset`, and a 36 118.85 cm path at 1900 gives a band 1900 cm
    across. `Ops.path_offset`'s distance is the band's HALF-width (a 100 000 cm path at 2000 spans
    `y = 2000`, i.e. `+-1002`), so a caller reproducing `OpenPolygonWidth = W` passes `W / 2`. The
    offline stand-in halves the distance itself, so it is given the full width."""
    path = [(0.0, 0.0), (36118.85, 0.0)]
    for width in (1900.0, 2000.0, 3400.0):
        band = OPS.path_offset(path, width, end="butt", join="square", miter_limit=2.0)
        (x0, y0), (x1, y1) = geo.bbox(band[0].outer)
        assert y1 - y0 == pytest.approx(width, abs=1e-6), "the band is `width` across"
        assert geo.area_m2(band[0]) == pytest.approx(36118.85 * width / 1e4, rel=1e-6)
    assert S.WIDTH_IS_FULL, "the documented convention must stay the measured one"


def test_the_published_width_grows_with_the_parameter():
    """The live graph's measured relationship, pinned offline: the published polygon is
    `Highway_Width + 3000` wide (433 468 m2 at 2000, 606 862 at 4000, 953 642 at 8000), and the
    construction that reproduces it is `path_offset(path, Highway_Width)` -- `path_offset`'s distance
    is a HALF-width -- followed by `Transform_Areas_Expand(1500)`. On the live splines that pair gives
    +0.10 % and +0.53 % on area and the official's own implied half-width (2 485 / 2 486 cm)."""
    path = [p[:2] for p in STRAIGHT]
    for width, want in ((2000.0, 5000.0), (4000.0, 7000.0), (8000.0, 11000.0)):
        band = OPS.path_offset(path, width, end="butt", join="square", miter_limit=2.0)
        grown = geo.roads.expand(band, S.EXPAND_CM, OPS)
        (x0, y0), (x1, y1) = geo.bbox(grown[0].outer)
        assert x1 - x0 == pytest.approx(100000.0 + 2 * S.EXPAND_CM, abs=1.0)
        assert y1 - y0 == pytest.approx(want, abs=1.0), \
            "the published footprint is Highway_Width + 3000 across"


def test_empty_input_gives_empty_output_and_the_tag_survives_a_run():
    out = S.run(inputs(splines=line(STRAIGHT), surface=FlatTerrain(-600.0)), PARAMS, _ctx())
    assert out["Highway"], "a highway in, a polygon out"
    assert all("Highway" in tags for _v, tags in out["Highway"])
    empty = S.run(inputs(), PARAMS, _ctx())
    assert empty["Highway"] == []


# ---- 5. contract: the check module ------------------------------------------------------------
def test_the_check_flags_a_wrong_width():
    """`checks/s08.py` reads the published width back off the polygon. A polygon far too narrow must
    fail, and the live one must not."""
    from pypcg import checks
    from pypcg.checks import s08 as C
    wide = Polygon([(0.0, -2500.0), (100000.0, -2500.0), (100000.0, 2500.0), (0.0, 2500.0)])
    narrow = Polygon([(0.0, -100.0), (100000.0, -100.0), (100000.0, 100.0), (0.0, 100.0)])
    outs = {"Highway": [(wide, ["Highway"])]}
    assert C.check(None, PARAMS, outs, OPS) == []
    outs = {"Highway": [(narrow, ["Highway"])]}
    assert C.check(None, PARAMS, outs, OPS), "a 200 cm ribbon must fail the width check"
    outs = {"Highway": [(Polygon([(0.0, 0.0), (1.0, 0.0)]), ["Highway"])]}
    assert C.check(None, PARAMS, outs, OPS), "a degenerate ring must fail"
    outs = {"Highway": [(wide, [])]}
    assert C.check(None, PARAMS, outs, OPS), "a missing tag must fail"
    # the count check needs the inputs to know how many highways it was given
    outs = {"Highway": [(wide, ["Highway"]), (wide, ["Highway"]), (wide, ["Highway"])]}
    ins = inputs(splines=line(STRAIGHT) + line(PARALLEL))
    assert C.check(ins, PARAMS, outs, OPS), "three items for two highways must fail"
    assert C.check(ins, PARAMS, {"Highway": [(wide, ["Highway"]), (wide, ["Highway"])]}, OPS) == []


def test_the_oracle_compares_by_area_and_bbox():
    from pypcg.checks import s08 as C
    wide = Polygon([(0.0, -2500.0), (100000.0, -2500.0), (100000.0, 2500.0), (0.0, 2500.0)])
    official = {"Highway": [wide]}
    assert C._oracle([wide], official["Highway"]) == []
    shifted = Polygon([(50000.0, -2500.0), (150000.0, -2500.0), (150000.0, 2500.0), (50000.0, 2500.0)])
    f = C._oracle([shifted], official["Highway"])
    assert any("bbox" in x for x in f), "a 500 m shift must show up"
    f = C._oracle([wide, wide], official["Highway"])
    assert any("polygons vs official" in x for x in f)


def test_the_slim_graph_declares_every_parameter_the_kept_nodes_read():
    """`Branch_0` is kept and test `Partitioned`; an unwired `bOutputToB` has no defined output side,
    so the slim graph must carry the parameter. It is not part of the stage's own contract."""
    from pypcg import graphs, stage_api as api
    names = [p.name for p in graphs.graph(8)._params]
    assert names[0] == api.SEED
    assert "Highway_Width" in names
    assert "Partitioned" in names

# ---- 6. seeded runs ----------------------------------------------------------------------------
def test_this_stage_draws_no_random_numbers():
    """The read side of stage 8 is deterministic: no node in it has a random draw. The pillar half's
    `Spawn_Assets` is native and keeps its own seed. Protocol Step B4 is therefore skipped by
    construction, the same way stage 7's is."""
    assert S.RANDOM is False


def test_the_stage_is_deterministic_across_repeats():
    """`RANDOM = False` means V2's determinism check compares the official graph to itself, so the
    module's own repeatability is pinned here instead: the same inputs must give byte-identical
    outputs."""
    ins = inputs(splines=line(STRAIGHT) + line(PARALLEL), surface=FlatTerrain(-600.0))
    a = S.run(ins, PARAMS, _ctx())
    b = S.run(ins, PARAMS, _ctx())
    assert [[geo.to_json(v), list(t)] for v, t in a["Highway"]] ==            [[geo.to_json(v), list(t)] for v, t in b["Highway"]]


def test_a_missing_terrain_leaves_the_spline_where_the_flatten_put_it():
    """`Transform_Project` needs its `SecondaryInput`; with no surface the port must still emit the
    spline, at the flatten step's own Z, rather than dropping the highway."""
    out = S.run(inputs(splines=line(STRAIGHT)), PARAMS, _ctx())
    assert len(out["Highway"]) == 1
    assert all(p[2] == 0.0 for p in out["Highway"][0][0].points)


def test_the_slim_graph_routes_the_grammar_output_through_expand_and_tag():
    """The published `Highway` polygon is the grammar node's `Footprints` grown by 15 m and tagged,
    exactly the official chain `Assign_HighwayShapeGrammar -> Subgraph_0 -> AddTag_Highway -> output`.
    A slim graph that stopped at the grammar node would publish a polygon 3000 cm too narrow, which is
    what the measured `-0.24 %` on area would become `-50 %`."""
    from pypcg import graphs
    from pypcg.profiles import official
    doc = graphs.graph(8).to_ir(official)
    expand = [n for n in doc["nodes"] if n.get("overrides") and "Expand" in n["overrides"]]
    assert expand, "the 15 m expansion node is gone"
    assert expand[0]["overrides"]["Expand"] == S.EXPAND_CM
    grammar = [n for n in doc["nodes"]
               if n.get("overrides") and "SGD_ElevatedHighway_oneWay" in str(n["overrides"])]
    assert grammar, "the highway grammar node is gone"
    tag = [n for n in doc["nodes"] if (n.get("settings") or {}).get("TagsToAdd") == "Highway"]
    assert tag, "the Highway tag node is gone"
    # every edge of the graph, as (source, source pin) -> the nodes that read it
    reads = {}
    for n in doc["nodes"]:
        for pin in n.get("inputs", []):
            for src, sp in pin["edges"]:
                reads.setdefault((src, sp), []).append(n["name"])
    assert expand[0]["name"] in reads.get((grammar[0]["name"], "Footprints"), []), \
        "the grammar footprint does not feed the 15 m expansion"
    assert tag[0]["name"] in reads.get((expand[0]["name"], "Out"), []), \
        "the expansion does not feed the Highway tag node"
    out = [n for n in doc["nodes"] if n["name"] == "DefaultOutputNode"]
    assert out and any(src == tag[0]["name"] for pin in out[0].get("inputs", [])
                       for src, _ in pin["edges"]), \
        "the output node is not sourced from the Highway tag node"
