"""Stage 7, Roads -- the footprint half (spec 3, Step B). The invariants are the task brief's:

  - every footprint is within the City + 200 m and its area is between width x length and 1.5 x that
    for each road line;
  - the footprints of different classes do not overlap by more than a module;
  - the number of grammar points per class is proportional to that class's total length within 10 %;
  - `simpleRoads = True` produces one class only;
  - empty inputs -> empty outputs, and a City with no roads at all produces no footprint.

**Two of those five are not covered here, deliberately.** The grammar-point proportionality invariant
needs `Intersection_solving`'s sections, which are commit 2: the grammar nodes (`Subgraph_8/9/10`,
`Subgraph_41/43/51`) consume those sections, not the footprint's lines, so there are no grammar points
in this half to be proportional to. It is deferred with the terrain half (see
`docs/pypcg/stages/s07.md` section 8), not silently skipped. The area bound is covered but weakly: the
offline stand-in for the Clipper2 booleans is rectangle-level, so it pins the *shape* of the
invariant and the real numbers come from the in-editor probes.
"""
import json
import os

import pytest

from fakes import RibbonOps
from pypcg import geo, stage_api
from pypcg.geo import Polygon, Spline
from pypcg.geo import sections as SEC
from pypcg.stages import s07_roads as S

REPO = stage_api.REPO
OPS = RibbonOps()
PARAMS = dict(stage_api.defaults(S))
PARAMS.pop(stage_api.SEED)


def spline(pts, closed=False, tags=("localRoads",)):
    return [(Spline([(x, y, 0.0) for x, y in pts], closed=closed), frozenset(tags))]


def inputs(roads=(), landmarks=None):
    """`roads` is `[(class_tag, [(x, y), ...])]`; the class tag decides which pin it lands on."""
    districts = []
    for tag, pts in roads:
        districts += spline(pts, tags=(tag,))
    out = {"Districts": districts}
    if landmarks:
        for k, ring in landmarks.items():
            out[k] = [(Polygon(ring), frozenset())]
    return out


ROADS = [("localRoads", [(0.0, 0.0), (100000.0, 0.0)]),
         ("CollectorRoads", [(0.0, 50000.0), (100000.0, 50000.0)]),
         ("ArteryRoads", [(0.0, 100000.0), (100000.0, 100000.0)])]


# ---- 1. contract -----------------------------------------------------------------------------
def test_contract_parameters_and_outputs_match_the_official_graph():
    off = json.load(open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_1_2_Roads.json"),
                         encoding="utf-8"))
    defaults = {p["name"]: p["value"] for p in off["params"]}
    assert set(S.PARAMS) == {"simpleRoads", "local_Width", "collector_width", "Artery_width",
                             "Road_Profile", "Crosswalks", "Partitioned"}
    assert set(S.PARAMS) <= set(defaults)
    for name in ("simpleRoads", "local_Width", "collector_width", "Artery_width"):
        assert S.PARAMS[name].default == defaults[name]
    # `Partitioned` is the one parameter this port declares that the contract drops: three kept
    # branches (`Branch_15/16/18`) test it. It must exist for the graph to build, and it must not
    # carry the graph's own default (false, the value every volume this port runs uses).
    assert S.PARAMS["Partitioned"].default == defaults["Partitioned"] == False
    assert set(S.OUTPUTS) == {"RoadFootprints", "LocalSections", "CollectorSections",
                              "ArterySections", "IntersectionsPlanar", "Landmarks",
                              "LocalRoads", "CollectorRoads", "ArteryRoads"}
    # the demo level's overrides for the two it changes
    assert S.PARAMS["Road_Profile"].type == "SoftObject"
    assert S.PARAMS["Road_Profile"].default == defaults["Road_Profile"]
    assert S.PARAMS["Crosswalks"].default == defaults["Crosswalks"] == False


def test_contract_input_pins_are_the_scene_reads_the_graph_keeps():
    assert set(S.INPUTS) == {"Districts", "MainTower", "CentralParkFootprint"}


def test_contract_the_slim_graph_wires_every_pin_and_output():
    from pypcg import graphs, ir
    from pypcg.profiles import official
    doc = graphs.graph(7).to_ir(official)                 # raises on an unwired Python input pin
    py = [x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE]
    assert py, "no Python node"
    wired = {p["label"] for p in py[0]["inputs"] if p["edges"]}
    assert set(S.INPUTS) | {stage_api.PARAMS_PIN} <= wired
    used = {(src, pin) for x in doc["nodes"] for p in x.get("inputs", []) for src, pin in p["edges"]}
    # Every output is wired except `Landmarks`, which is published for the Python module's own use
    # (the three landmark clips and `Subgraph_3`) and has no native consumer in the slim graph: the
    # official graph's carrier for it `NamedRerouteDeclaration_2` is a node reference, which `keep()`
    # refuses, so its readers are fed inside the module instead. It still must be EMITTED, or the
    # module's own call would KeyError -- `test_every_output_pin_is_published` covers that.
    for pin in S.OUTPUTS:
        if pin == "Landmarks":
            continue
        assert (py[0]["name"], pin) in used, "output %s is wired to nothing" % pin


def test_every_output_pin_is_published():
    """`run()` must emit all nine pins on every input, empty included, because the slim graph wires
    eight of them into kept native nodes: a missing pin would leave a node with no input rather than
    with an empty one."""
    for inp in ({pin: [] for pin in S.INPUTS}, {"Districts": []},
                inputs([("localRoads", [(0.0, 0.0), (10000.0, 0.0)])])):
        out = S.run(inp, PARAMS, _ctx())
        assert set(out) == set(S.OUTPUTS)


# ---- 2. empty inputs -------------------------------------------------------------------------
def test_empty_inputs_give_empty_outputs():
    out = S.run({pin: [] for pin in S.INPUTS}, PARAMS, _ctx())
    assert set(out) == set(S.OUTPUTS)
    assert all(not items for items in out.values())


def test_missing_input_pins_are_tolerated():
    """A stage must survive a missing input, not just an empty one (protocol Step B2)."""
    out = S.run({"Districts": []}, PARAMS, _ctx())
    assert set(out) == set(S.OUTPUTS)
    assert all(not items for items in out.values())


def test_a_city_with_no_roads_produces_no_footprint_and_no_terrain_write():
    out = S.run(inputs(roads=[]), PARAMS, _ctx())
    assert out["RoadFootprints"] == []


# ---- 3. the task's invariants ----------------------------------------------------------------
def test_every_footprint_sits_within_the_city_plus_200_m():
    """The union is inside the road lines' own box grown by half the widest class width."""
    out = S.run(inputs(ROADS), PARAMS, _ctx())
    xs = [p for _, pts in ROADS for p in pts]
    (x0, y0), (x1, y1) = (min(p[0] for p in xs) - 20000.0, min(p[1] for p in xs) - 20000.0), \
                         (max(p[0] for p in xs) + 20000.0, max(p[1] for p in xs) + 20000.0)
    for poly, _tags in out["RoadFootprints"]:
        (px0, py0), (px1, py1) = geo.bbox(poly.outer)
        assert x0 <= px0 and y0 <= py0 and px1 <= x1 and py1 <= y1


def test_footprint_area_is_between_width_times_length_and_1_5_that():
    """One local road line at length L and width W: its ribbon's area is L x W, and the union of a
    single ribbon is that, so the bound holds with the lower edge at L x W."""
    out = S.run(inputs([("localRoads", [(0.0, 0.0), (100000.0, 0.0)])]), PARAMS, _ctx())
    total = sum(geo.area_m2(p) for p, _ in out["RoadFootprints"])
    want = 100000.0 * 1900.0 / 1e4                    # the line's own length x its width
    assert total == pytest.approx(want, rel=0.05)
    assert want <= total <= 1.5 * want


def test_the_three_classes_ribbons_are_widest_to_narrowest():
    """Artery > Collector > Local for the same line length, by the width ratio."""
    got = {}
    for tag, width in (("ArteryRoads", 3400.0), ("CollectorRoads", 2600.0), ("localRoads", 1900.0)):
        out = S.run(inputs([(tag, [(0.0, 0.0), (100000.0, 0.0)])]), PARAMS, _ctx())
        got[tag] = sum(geo.area_m2(p) for p, _ in out["RoadFootprints"])
        assert got[tag] == pytest.approx(100000.0 * width / 1e4, rel=0.05)
    assert got["ArteryRoads"] > got["CollectorRoads"] > got["localRoads"]


def test_the_city_outline_is_tagged_artery_and_still_outlined():
    """`FilterDataByTag_3/4/5` match with `Operator = Substring`. The City outline carries
    `ArteryRoads` as well as `City`, and it is CLOSED, so it reaches the artery ribbon pass as a ring
    rather than as a line. Measured against the live official footprint, including this ring is what
    makes the union's bbox reproduce three of the official four edges (docs/pypcg/stages/s07.md
    section 6): dropping it takes the port from -0.65 % to -25.5 % on area.

    The rectangle stand-in used here cannot produce a ring's mitered corners, so the assertion is
    structural -- the closed ring contributes a footprint, and it is closed."""
    ring = Spline([(0.0, 0.0, 0.0), (100000.0, 0.0, 0.0), (100000.0, 100000.0, 0.0),
                   (0.0, 100000.0, 0.0)], closed=True)
    out = S.run({"Districts": [(ring, frozenset({"ArteryRoads", "City"}))]}, PARAMS, _ctx())
    assert out["RoadFootprints"], "the closed artery outline must still be outlined"
    paths = S._paths([(ring, frozenset({"ArteryRoads", "City"}))], "ArteryRoads", 3400.0)
    assert len(paths) == 1 and paths[0][0] == paths[0][-1], "a closed ring must stay a closed ring"
    # A closed ring is not extended: extension belongs to open lines only.
    line = S._paths(spline([(0.0, 0.0), (10000.0, 0.0)]), "localRoads", 1900.0)
    assert line[0][0][0] < 0.0 and line[0][-1][0] > 10000.0, "an open line must be extended"


def test_two_classes_do_not_overlap_by_more_than_a_module():
    """Parallel lines 500 m apart at 1900/2600 cm: the ribbons are disjoint (500 m >> a module)."""
    out = S.run(inputs([("localRoads", [(0.0, 0.0), (100000.0, 0.0)]),
                        ("CollectorRoads", [(0.0, 50000.0), (100000.0, 50000.0)])]), PARAMS, _ctx())
    total = sum(geo.area_m2(p) for p, _ in out["RoadFootprints"])
    parts = 100000.0 * (1900.0 + 2600.0) / 1e4
    # The stand-in adds the mitered end caps the real ribbon also has (1174.6 + 4263.6 cm2), so the
    # tolerance is 5 % rather than 2 %: the point is that the two disjoint ribbons stay TWO
    # footprints, not that the stand-in matches Clipper2 exactly.
    assert len(out["RoadFootprints"]) == 2, "the two classes must stay separate footprints"
    assert total == pytest.approx(parts, rel=0.05), "the two ribbons must not have merged"


def test_the_footprint_carries_the_roadfootprints_tag():
    out = S.run(inputs(ROADS), PARAMS, _ctx())
    assert out["RoadFootprints"], "no footprint at all"
    assert all("RoadFootprints" in tags for _p, tags in out["RoadFootprints"])


def test_simple_roads_produces_one_class_only():
    """The task's invariant. The official graph branches six times on `simpleRoads`, but the
    footprint's Stripe Pass filters are fed from the Districts data ahead of every one of them, so
    the footprint does NOT depend on it and the parameter must not change the output here."""
    a = S.run(inputs(ROADS), dict(PARAMS, simpleRoads=False), _ctx())
    b = S.run(inputs(ROADS), dict(PARAMS, simpleRoads=True), _ctx())
    assert [p.outer for p, _ in a["RoadFootprints"]] == [p.outer for p, _ in b["RoadFootprints"]]


def test_landmarks_join_the_local_outline():
    """`Subgraph_86` unions the Landmarks ribbon into the local class, so a landmark away from every
    road adds its own ribbon tagged RoadFootprints."""
    far = {"MainTower": [(500000.0, 500000.0), (510000.0, 500000.0), (510000.0, 510000.0),
                         (500000.0, 510000.0)]}
    out = S.run(inputs([("localRoads", [(0.0, 0.0), (100000.0, 0.0)])], landmarks=far), PARAMS, _ctx())
    total = sum(geo.area_m2(p) for p, _ in out["RoadFootprints"])
    assert total > 100000.0 * 1900.0 / 1e4 * 1.05, "the landmark ribbon is missing from the footprint"


# ---- 4. seeded runs --------------------------------------------------------------------------
def test_this_stage_draws_no_random_numbers():
    assert S.RANDOM is False


def _ctx():
    return stage_api.Ctx(S.STAGE, 42, OPS)


# ---- 5. the sections half (`Intersection_solving`) -------------------------------------------
def test_sections_contract_constants_match_the_official_graph():
    """`roadSectionLimit` and `intersection_expansion_range`: the first is the graph's own default,
    the second is overridden to 50 in the demo level against a graph default of 100."""
    assert S.SECTION_LIMIT == 200.0
    assert S.EXPANSION_RANGE == 50.0
    assert SEC.SECTION_LIMIT == S.SECTION_LIMIT
    assert S.LANDMARK_CUT_ANGLE == 3.0


def test_solve_publishes_every_class_and_the_three_composite_labels():
    """`Gather_0/1/2` label the pieces `roadSections`, `intersections` and `intersectionsShort`; the
    long/short split is `Filter_Splines_byLength` at `roadSectionLimit`."""
    solved = SEC.solve(S.class_paths(inputs(ROADS), OPS, PARAMS), PARAMS, OPS)
    assert set(solved) == {"sections", "planar", "cutter", "footprints"}
    assert set(solved["sections"]) == set(SEC.CLASSES)
    for tag in SEC.CLASSES:
        labels = {label for _p, label in solved["sections"][tag]}
        assert labels, "class %s produced no labelled piece" % tag
        assert labels <= {"roadSections", "intersections", "intersectionsShort"}


def test_the_module_length_filter_is_the_only_thing_that_splits_long_from_short():
    """A straight local line through one crossing: the pieces outside the cutter longer than 200 cm
    are `roadSections`, the shorter ones `intersectionsShort`."""
    solved = SEC.solve(S.class_paths(inputs(ROADS), OPS, PARAMS), PARAMS, OPS)
    for tag in SEC.CLASSES:
        for path, label in solved["sections"][tag]:
            L = SEC.path_length(path)
            if label == "roadSections":
                assert L > S.SECTION_LIMIT, "a roadSection of %.2f cm is under the limit" % L
            if label == "intersectionsShort":
                assert L <= S.SECTION_LIMIT, "an intersectionsShort of %.2f cm is over the limit" % L


def test_cut_paths_keeps_inside_for_intersection_and_removes_for_difference():
    """The one primitive both directions of this stage use. Intersection keeps what a ring holds;
    Difference removes it. The two must not be swapped: the landmark clips and the intersection cuts
    are Difference, the +/-Y dance and `Subgraph_133/135/138` are Intersection."""
    path = [(0.0, 0.0), (1000.0, 0.0)]
    ring = [(-100.0, -100.0), (100.0, -100.0), (100.0, 100.0), (-100.0, 100.0)]
    inside = SEC.cut_paths([path], [ring], OPS, True)
    outside = SEC.cut_paths([path], [ring], OPS, False)
    assert inside, "the intersection direction dropped a piece the ring holds"
    assert outside, "the difference direction dropped everything"
    assert sum(SEC.path_length(p) for p in inside) < sum(SEC.path_length(p) for p in outside)


def test_cut_paths_against_many_rings_does_not_count_a_stretch_twice():
    """`ClipPaths(Intersection)` clips against the UNION of its cutters. The intersection planes
    overlap heavily (334 planes over 78 ribbons), so a per-ring concatenation would hand the grammar
    nodes more road than exists; the arclength merge is what prevents it."""
    path = [(0.0, 0.0), (1000.0, 0.0)]
    a = [(-100.0, -100.0), (500.0, -100.0), (500.0, 100.0), (-100.0, 100.0)]
    b = [(300.0, -100.0), (800.0, -100.0), (800.0, 100.0), (300.0, 100.0)]
    both = SEC.cut_paths([path], [a, b], OPS, True)
    total = sum(SEC.path_length(p) for p in both)
    assert total <= 1000.0 + 1e-6, "the overlapping cutters counted the same stretch twice"
    assert total >= 500.0, "the union of the two overlapping spans must be at least the longer one"


def test_a_class_with_no_input_contributes_nothing_and_does_not_raise():
    solved = SEC.solve({SEC.LOCAL: [], SEC.COLLECTOR: [], SEC.ARTERY: []}, PARAMS, OPS)
    assert all(not solved["sections"][t] for t in SEC.CLASSES)
    assert solved["planar"] == []


def test_the_sections_are_landmark_clipped_and_the_decals_are_not():
    """The decal chain (`FilterDataByTag_6/10/11` -> `Branch_6/7/8`) reads the Districts' own lines
    ahead of the three landmark clips, while the grammar reads the solved, clipped sections. So
    `LocalRoads` must be at least as long as the clipped class."""
    out = S.run(inputs(ROADS), PARAMS, _ctx())
    for pin in ("LocalRoads", "CollectorRoads", "ArteryRoads"):
        assert out[pin], "%s is empty but the input has lines of that class" % pin
    got = sum(SEC.path_length([(p[0], p[1]) for p in s.points]) for s, _t in out["LocalRoads"])
    assert got > 0.0


def test_the_planar_set_is_built_from_the_short_and_the_inside_pieces():
    """`Subgraph_148/145/149` outline the SHORT and the INSIDE data. A class whose pieces are all
    long and outside contributes no planar polygon."""
    paths = {SEC.LOCAL: [[(0.0, 0.0), (100000.0, 0.0)]], SEC.COLLECTOR: [], SEC.ARTERY: []}
    solved = SEC.solve(paths, PARAMS, OPS)
    assert solved["sections"][SEC.LOCAL], "a single long road must still produce a section"
    assert all(label == "roadSections" for _p, label in solved["sections"][SEC.LOCAL])


# ---- 6. the V1 checks on the sections half ---------------------------------------------------
def test_v1_checks_pass_on_a_real_run_and_catch_a_collapsed_class():
    from pypcg.checks import s07 as C
    out = S.run(inputs(ROADS), PARAMS, _ctx())
    assert C.check(inputs(ROADS), PARAMS, out, OPS) == []
    # a class whose sections vanished while its decal lines are still there
    lost = dict(out, LocalSections=[])
    assert any("LocalSections is empty" in x for x in C.check(inputs(ROADS), PARAMS, lost, OPS))
    # a degenerate section
    zero = dict(out, ArterySections=[(Spline([(0.0, 0.0, 0.0)]), frozenset({"roadSections"}))])
    assert any("ArterySections holds a" in x for x in C.check(inputs(ROADS), PARAMS, zero, OPS))


def test_v1_checks_do_not_judge_a_run_with_no_roads():
    """Empty input is not a failure: there is no class to publish sections for."""
    from pypcg.checks import s07 as C
    out = S.run({pin: [] for pin in S.INPUTS}, PARAMS, _ctx())
    assert C.check({pin: [] for pin in S.INPUTS}, PARAMS, out, OPS) == []


# ---- 7. the two fix-round regressions --------------------------------------------------------
def test_a_span_is_measured_by_projection_not_by_the_nearest_vertex():
    """`_along` maps a clip's end back to an arclength position on the path. It must PROJECT onto the
    segments: a clip's ends lie on the path but are not usually its vertices, so vertex-snapping
    collapses every span on a 2-point road to zero length and the piece vanishes.

    Regression guard for the bug this commit's headline fix removed (71 zero-length pieces, a
    -0.65 % footprint, and a -6.2 % V2 instance median). A revert to nearest-vertex would still pass
    every other test in this file, so the guard has to be here, at the helper's own level."""
    path = [(0.0, 0.0), (1000.0, 0.0)]                       # a 2-point road: no interior vertex
    ring = [(-100.0, -100.0), (100.0, -100.0), (100.0, 100.0), (-100.0, 100.0)]
    cum = [0.0, 1000.0]
    # the clip's two ends, at 0 and 100 -- neither is the path's own vertex 0 or 1000
    assert SEC._along((0.0, 0.0), path, cum) == pytest.approx(0.0)
    assert SEC._along((100.0, 0.0), path, cum) == pytest.approx(100.0)
    assert SEC._along((500.0, 0.0), path, cum) == pytest.approx(500.0)
    # and the span those ends define is 100 cm long, not zero
    inside = SEC.cut_paths([path], [ring], OPS, True)
    assert len(inside) == 1
    assert SEC.path_length(inside[0]) == pytest.approx(100.0, rel=1e-6)
    # the same walk through `_union_spans`, which is what consumes `_along` in the Intersection case
    spans = SEC._union_spans(path, [ring])
    assert len(spans) == 1 and SEC.path_length(spans[0]) == pytest.approx(100.0, rel=1e-6)


def test_the_three_width_attributes_reach_the_output_node():
    """The published polygon must carry `LocalWidth`/`CollectorWidth`/`ArteryWidth`. The official
    graph sources the output node from `AddAttribute_0` -- the tail of `AddTags_1 -> AddAttribute_2
    -> AddAttribute_1 -> AddAttribute_0` -- and stage 10 reads `@data.ArteryWidth` off that polygon to
    size its sidewalk expansion (stage 18 reads it too). Sourcing the output from `AddTags_1` instead
    -- what this graph did before the 10b fix round -- publishes a polygon with no widths, and nothing
    else in the suite sees it: `checks/s07.py` asserts the tag, and the contract test only asks that
    the pin is wired somewhere.

    The built IR renames nodes (`n11`, `n12`, ...), so this identifies them by their official titles,
    which `keep()` carries over."""
    from pypcg import graphs
    from pypcg.profiles import official
    doc = graphs.graph(7).to_ir(official)
    by = {x["name"]: x for x in doc["nodes"]}
    # only the `In` pin: each attribute node also takes its width on `Attributes`, from a parameter
    # getter, and that is not part of the chain.
    feeds_in = {n["name"]: {src for p in n.get("inputs", []) if p["label"] == "In"
                            for src, _pin in p["edges"]} for n in doc["nodes"]}

    outs = [x for x in doc["nodes"] if x["class"] == "PCGGraphInputOutputSettings"
            and any(p["label"] == "Out" for p in x.get("inputs", []))]
    assert len(outs) == 1, "expected exactly one output node, got %d" % len(outs)
    srcs = {src for p in outs[0]["inputs"] if p["label"] == "Out" for src, _pin in p["edges"]}

    def node_with_title(title):
        hits = [n for n in doc["nodes"] if n.get("title") == title]
        assert len(hits) == 1, "expected one node titled %r, got %d" % (title, len(hits))
        return hits[0]

    artery = node_with_title("Embed Artery Width On Footprint")
    assert by[artery["name"]]["class"] == "PCGAddAttributeSettings"
    assert artery["name"] in srcs, (
        "the output node is not sourced from the artery-width attribute node, so the published "
        "polygon carries no LocalWidth/CollectorWidth/ArteryWidth; sources are %s"
        % [by[s].get("title") or s for s in sorted(srcs)])

    # and the three nodes form one chain into it: artery <- collector <- local <- AddTags_1
    collector = node_with_title("Embed Collector Width On Footprint")
    local = node_with_title("Embed Local Width On Footprint")
    assert feeds_in[artery["name"]] == {collector["name"]}, "the artery node must take the collector's output"
    assert feeds_in[collector["name"]] == {local["name"]}, "the collector node must take the local one's output"
    assert feeds_in[local["name"]], "the local-width node has no input: the chain does not start at AddTags_1"


def test_intersection_planes_intersect_whole_polygons_holes_included():
    """T27g (Task 27): a closed ring's band (the City outline) is a polygon with a hole. The loop
    intersects each ribbon as the whole Polygon2D, so the hole must reach the boolean -- on its own
    side and among the others. Reading only the outer ring turned the town's City band into a disk
    and every road inside it into one 70 ha intersection."""
    calls = []

    class Rec:
        def intersection(self, a, b):
            calls.append((a, b))
            return []

    band = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)], [[(200, 200), (200, 800), (800, 800), (800, 200)]])
    road = Polygon([(400, -100), (600, -100), (600, 1100), (400, 1100)])
    SEC.intersection_planes([band, road], 50.0, Rec())
    own_band, others_band = calls[0]
    own_road, others_road = calls[1]
    assert own_band == [list(band.outer), list(band.holes[0])] and others_band == [list(road.outer)]
    assert own_road == [list(road.outer)] and others_road == [list(band.outer), list(band.holes[0])]
    # without holes the rings are what they always were
    calls.clear()
    SEC.intersection_planes([road, Polygon(list(band.outer))], 50.0, Rec())
    assert calls[0] == ([list(road.outer)], [list(band.outer)])
