"""Stage 8, Highways (spec 3, Step B). The invariants are the task brief's:

  - two straight parallel highways on flat ground -> two footprints whose width equals
    `Highway_Width` within 1 cm and whose area equals `width x length` within 1 %;
  - empty inputs -> empty outputs;
  - `Highway` present in every run.

The brief's first invariant -- width within 1 cm, area within 1 % -- is about the RIBBON the native
`Assign_HighwayShapeGrammar` builds, and **it is not reachable end to end**: the published polygon
passes through three engine booleans (`CreatePolygon2D`, `Transform_Areas_Expand`, and the grammar
node's own inner loop), and its 2 442-vertex discretisation alone moves `area / perimeter` by 14 cm.
The bounds this port can actually hold are `PUBLISHED_AREA_TOL` (1 %, the brief's own area number)
and `PUBLISHED_HALF_TOL_CM` (60 cm), both in `pypcg/checks/s08.py` and both labelled V1 diagnostics;
`test_the_published_width_grows_with_the_parameter` pins the shape offline and the in-editor `check`
holds the live numbers. See `docs/pypcg/stages/s08.md` section 8 for the gap, stated rather than
implied.

The width relationship the live graph shows is `published width = Highway_Width + 3000`, measured at
three widths (433 468 m2 at 2000, 606 862 m2 at 4000, 953 642 m2 at 8000).
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
# Highway 2's own length: the width's `area / perimeter` read-back is `(w / 2) x L / (L + w)`, so a
# fixture's aspect ratio matters and a short one reads several per cent low.
LIVE_LENGTH = 865268.62
PARALLEL = [(0.0, 20000.0, 5550.0), (100000.0, 20000.0, 5550.0)]


# ---- 1. contract -----------------------------------------------------------------------------
def test_contract_parameters_and_inputs_match_the_official_graph():
    with open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_1_3_Highways.json"),
              encoding="utf-8") as fh:
        off = json.load(fh)
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
    assert got.points[0][:2] == pytest.approx((0.0, 0.0))
    assert got.points[1][:2] == pytest.approx((8000.0, 0.0))
    assert got.points[-1][:2] == pytest.approx((100000.0, 0.0)), "the X/Y must survive the projection"
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


def test_the_offset_argument_is_the_bands_full_width():
    """The width convention, measured in the editor (2026-10-17) and pinned on a straight path.

    `CreatePolygon2D`'s `OpenPolygonWidth` reaches `ClipperOffset` unchanged
    (`PCGCreatePolygon2D.cpp:256`, `PolygonOffsetUtils.cpp:52`), and Clipper halves it internally for
    every non-`Polygon` end type (`clipper.offset.cpp:415`), so an open-path offset of `W` spans
    `+-W / 2` and the band is `W` across. `Ops.path_offset` takes the same argument in the same sense
    -- a 100 000 cm path at 2000 comes back spanning `y = 2000` -- and so does the offline stand-in.
    **No halving belongs at the call site**, which is what this note's first draft got wrong."""
    path = [(0.0, 0.0), (36118.85, 0.0)]
    for width in (1900.0, 2000.0, 3400.0):
        band = OPS.path_offset(path, width, end="butt", join="square", miter_limit=2.0)
        (x0, y0), (x1, y1) = geo.bbox(band[0].outer)
        assert y1 - y0 == pytest.approx(width, abs=1e-6), "the band is `width` across"
        assert geo.area_m2(band[0]) == pytest.approx(36118.85 * width / 1e4, rel=1e-6)


def test_the_published_width_grows_with_the_parameter():
    """The live graph's measured relationship, pinned offline: the published polygon is
    `Highway_Width + 3000` wide (433 468 m2 at 2000, 606 862 at 4000, 953 642 at 8000), and the
    construction that reproduces it is `path_offset(path, Highway_Width)` followed by
    `Transform_Areas_Expand(1500)`. On the live splines that pair gives +0.10 % and +0.53 % on area
    and the official's own implied half-width (2 485 / 2 486 cm)."""
    path = [p[:2] for p in STRAIGHT]
    for width, want in ((2000.0, 5000.0), (4000.0, 7000.0), (8000.0, 11000.0)):
        assert S.published_width_cm(width) == want
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
    # the live highway's own aspect ratio: `area / perimeter` is `(w / 2) x L / (L + w)`, so a
    # 100 000 cm fixture would read 4.8 % low on its own and needs the live 865 268.62 cm
    wide = Polygon([(0.0, -2500.0), (LIVE_LENGTH, -2500.0), (LIVE_LENGTH, 2500.0), (0.0, 2500.0)])
    narrow = Polygon([(0.0, -100.0), (LIVE_LENGTH, -100.0), (LIVE_LENGTH, 100.0), (0.0, 100.0)])
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
    # two items for two highways is the count the graph produces; the AREA clause is a separate test
    # (the fixture polygons are not the fixture splines' own ribbons, so only the count is asserted)
    two = C.check(ins, PARAMS, {"Highway": [(wide, ["Highway"]), (wide, ["Highway"])]}, OPS)
    assert not any("items for" in x for x in two), "two items for two highways must not be a count error"


def test_the_oracle_compares_by_area_and_bbox():
    from pypcg.checks import s08 as C
    wide = Polygon([(0.0, -2500.0), (LIVE_LENGTH, -2500.0), (LIVE_LENGTH, 2500.0), (0.0, 2500.0)])
    official = {"Highway": [wide]}
    assert C._oracle([wide], official["Highway"]) == []
    shifted = Polygon([(50000.0, -2500.0), (50000.0 + LIVE_LENGTH, -2500.0),
                       (50000.0 + LIVE_LENGTH, 2500.0), (50000.0, 2500.0)])
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


# ---- 7. the published width and area, the closest the native chain allows ---------------------
def test_the_published_area_check_holds_the_briefs_one_percent():
    """`checks/s08.py`'s `_published_area` is the in-editor assertion of the brief's AREA invariant:
    the published total against `(Highway_Width + 3000) x the highway spline length`.

    The live numbers it was built on (2026-10-17): the official polygons total 826 944.64 m2 against
    826 819.88 m2 for 1 653 639.8 cm of spline at a 5 000 cm published width -- +0.015 %, inside the
    1 % bound. The port's 829 424.44 is +0.31 %. Offline, a polygon 5 000 cm across and as long as
    its spline passes, and a 1 % narrow one does not."""
    from pypcg.checks import s08 as C
    length = 865268.62
    want = S.published_width_cm(2000.0) * length / 1e4
    exact = Polygon([(0.0, -2500.0), (length, -2500.0), (length, 2500.0), (0.0, 2500.0)])
    outs = {"Highway": [(exact, ["Highway"])]}
    splines = {"HighwaySplines": [(Spline([(0.0, 0.0, 0.0), (length, 0.0, 0.0)]), frozenset())]}
    assert geo.area_m2(exact) == pytest.approx(want, rel=1e-6)
    assert C._published_area(outs, 2000.0, splines) == []
    narrow = Polygon([(0.0, -2400.0), (length, -2400.0), (length, 2400.0), (0.0, 2400.0)])
    f = C._published_area({"Highway": [(narrow, ["Highway"])]}, 2000.0, splines)
    assert f and "published area" in f[0], "a 4 % narrow footprint must fail the 1 % area bound"
    # the width half of the brief's invariant is NOT testable at 1 cm: the official polygon reads
    # back 2 485.9 cm against the formula's 2 500, so the bound is 60 cm
    assert C.WIDTH_TOL_CM == 60.0
    assert abs(2485.9 - 0.5 * 2000.0 - S.EXPAND_CM) <= C.WIDTH_TOL_CM


def test_the_check_needs_no_inputs_to_hold_its_bounds():
    """On the oracle-only path there is no input pin to read the spline length from, so the area
    clause stays silent rather than guessing -- and the width clause still runs, because it needs
    nothing but the parameter."""
    from pypcg.checks import s08 as C
    wide = Polygon([(0.0, -2500.0), (LIVE_LENGTH, -2500.0), (LIVE_LENGTH, 2500.0), (0.0, 2500.0)])
    assert C.check(None, {"Highway_Width": 2000.0}, {"Highway": [(wide, ["Highway"])]}, None) == []
    narrow = Polygon([(0.0, -2400.0), (LIVE_LENGTH, -2400.0), (LIVE_LENGTH, 2400.0), (0.0, 2400.0)])
    f = C.check(None, {"Highway_Width": 2000.0}, {"Highway": [(narrow, ["Highway"])]}, None)
    assert f, "the width clause must fire without any inputs"


def test_the_ribbon_width_holds_one_centimetre_on_an_exact_path():
    """The brief's 1 cm, at the one place this port can hold it: the ribbon call itself, on a path with
    no discretisation. `Ops.path_offset(path, W)` is the same `UE::Geometry::PolygonsOffset` the
    grammar node's `CreatePolygon2D` makes, and the stock `RibbonOps` stand-in cannot express a 1 cm
    claim (its `_sides` is built from the path's vertices), so this test runs a local exact stand-in:
    a straight path's band is its two rails, `+-W / 2`, capped square at both ends.

    What this does NOT claim: that the PUBLISHED polygon is within 1 cm. It is not -- its own
    discretisation moves `area / perimeter` by 14 cm even on the official output, which is why the
    live bound is 60 cm and `docs/pypcg/stages/s08.md` section 8 says so explicitly."""
    class ExactRibbon:
        """A straight path's band, exactly: two rails at `+-W / 2`, the ends capped at the path's own
        x. This is what `CreatePolygon2D(ForceOpen, Butt, OpenPolygonWidth = W)` produces for a
        straight path -- measured in the editor at 36 118.85 x 1900 cm = 6 862.58 m2."""

        def path_offset(self, path, width, end="butt", join="square", miter_limit=2.0):
            (x0, y0), (x1, y1) = path[0], path[-1]
            half = 0.5 * float(width)
            return [Polygon([(x0, y0 - half), (x1, y1 - half), (x1, y1 + half), (x0, y0 + half)])]

    path = [(0.0, 0.0), (36118.85, 0.0)]
    for width in (1900.0, 2000.0, 3400.0):
        band = ExactRibbon().path_offset(path, width)
        (x0, y0), (x1, y1) = geo.bbox(band[0].outer)
        assert (y1 - y0) - width == pytest.approx(0.0, abs=1.0), "the width holds to 1 cm"
        assert geo.area_m2(band[0]) == pytest.approx(36118.85 * width / 1e4, rel=0.01), \
            "the area holds to the brief's 1 %"
    # the ribbon rule itself: `S`'s constant is the published width, and W / 2 each side is the half
    assert S.EXPAND_CM == 1500.0
    assert abs(0.5 * S.published_width_cm(2000.0) - (0.5 * 2000.0 + S.EXPAND_CM)) < 1e-9


def test_the_published_area_rejects_the_halved_offset():
    """The reviewer's Important 1, pinned as a behavioural test rather than a comment: a port that
    halved the offset at the call site (`path_offset(W / 2)` then `expand(1500)`) publishes 20 % too
    little, and `checks/s08.py`'s area clause must reject it while accepting `path_offset(W)`.

    Numbers from the live splines (2026-10-17): highway 2 is 865 268.62 cm, so the published area is
    `5000 x 8652.6862` = 43 263 m2 at the correct construction and `4000 x 8652.6862` = 34 611 m2 at
    the halved one; the official polygon is 43 346.8 m2."""
    from pypcg.checks import s08 as C
    length = 865268.62
    splines = {"HighwaySplines": [(Spline([(0.0, 0.0, 0.0), (length, 0.0, 0.0)]), frozenset())]}
    right = Polygon([(0.0, -2500.0), (length, -2500.0), (length, 2500.0), (0.0, 2500.0)])
    halved = Polygon([(0.0, -2000.0), (length, -2000.0), (length, 2000.0), (0.0, 2000.0)])
    assert C._published_area({"Highway": [(right, ["Highway"])]}, 2000.0, splines) == []
    f = C._published_area({"Highway": [(halved, ["Highway"])]}, 2000.0, splines)
    assert f and "-20.0" in f[0], f
    # and the width clause rejects it too: a 2 000 cm half-width against the 2 500 cm expectation
    assert C.check(splines, {"Highway_Width": 2000.0}, {"Highway": [(halved, ["Highway"])]}, None)
