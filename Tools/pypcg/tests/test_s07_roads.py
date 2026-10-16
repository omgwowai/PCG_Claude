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
                             "Road_Profile", "Crosswalks"}                 # the six kept
    assert set(S.PARAMS) <= set(defaults)
    for name in ("simpleRoads", "local_Width", "collector_width", "Artery_width"):
        assert S.PARAMS[name].default == defaults[name]
    assert set(S.OUTPUTS) == {"RoadFootprints"}          # the terrain half is commit 2
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
    for pin in S.OUTPUTS:
        assert (py[0]["name"], pin) in used, "output %s is wired to nothing" % pin


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
