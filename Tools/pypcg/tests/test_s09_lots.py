"""Stage 9, Lots (Task 16; spec 3, Step B).

The invariants are the task brief's:
  - every lot lies inside its district and outside roads, landmarks, parks and highways;
  - the class of each building footprint matches the class of the lot it came from;
  - `UnderHighway` is non-empty exactly when a highway crosses a district;
  - the KEPT share is within 0.10 of `PlazaReservationRatio`, measured on items (one draw per lot --
    the brief's "reserved share" is read as the share `Subgraph_3` selects, which is what the ratio
    sets; the reserved share is its complement);
  - the outputs account for the prepared lots' area within 1 %;
  - empty inputs -> all eleven outputs empty.

Offline the booleans are `BoxOps`: axis-aligned boxes (`fakes.RibbonOps`) plus the convex
`cut_with_paths` of `fakes.FakeOps`. The fixture is a 600 x 100 m city with four 20 m roads across
it, so every lot, split, courtyard and grammar band stays a box and the box booleans are exact."""
import json
import os
import random

import pytest

from fakes import FakeOps, RibbonOps
from pypcg import geo, stage_api
from pypcg.checks import s09 as C
from pypcg.geo import Polygon, Spline
from pypcg.geo import areas as A
from pypcg.stages import s09_lots as S

REPO = stage_api.REPO


class BoxOps(RibbonOps):
    cut_with_paths = FakeOps.cut_with_paths


OPS = BoxOps()


def params(**kw):
    p = dict(stage_api.defaults(S))
    p.pop(stage_api.SEED)
    p.update(kw)
    return p


def box(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def closed(p):
    return Spline([(x, y, 0.0) for x, y in p.outer], closed=True, polyline=[(x, y, 0.0) for x, y in p.outer])


ROADS = [box(12000 + 12000 * k, -1000, 14000 + 12000 * k, 11000) for k in range(4)]
LOTS = [(0, 12000), (14000, 24000), (26000, 36000), (38000, 48000), (50000, 60000)]
DISTRICTS = {"SmallDistricts": box(0, 0, 25000, 10000), "MediumDistricts": box(25000, 0, 49000, 10000),
             "LargeDistricts": box(49000, 0, 60000, 10000)}
HIGHWAY = box(-5000, 4000, 65000, 5000)


def inputs(highway=True, undividable=None, **over):
    d = [(p, frozenset({t, "City"})) for t, p in DISTRICTS.items()]
    if undividable is not None:
        d.append((undividable, frozenset({"UndividableDistricts"})))
    ins = {"City": [(closed(box(0, 0, 60000, 10000)), frozenset({"City"}))],
           "Districts": d,
           "RoadFootprints": [(r, frozenset({"RoadFootprints"})) for r in ROADS],
           "MainTower": [], "CentralParkFootprint": [], "LandmarkPark": [],
           "Highway": [(HIGHWAY, frozenset({"Highway"}))] if highway else []}
    ins.update(over)
    return ins


def run(ins, seed=42, ops=OPS, **kw):
    out, _ctx = stage_api.execute(S, ins, dict(params(**kw), Seed=seed), ops)
    return out


def by_tag(out):
    return C._by_tag(out)


def overlap_m2(p, q):
    (a0, a1), (b0, b1) = geo.bbox(p.outer), geo.bbox(q.outer)
    w, h = min(a1[0], b1[0]) - max(a0[0], b0[0]), min(a1[1], b1[1]) - max(a0[1], b0[1])
    return w * h / 1e4 if w > 0 and h > 0 else 0.0


def official_ir():
    with open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_1_4_Lots.json"), encoding="utf-8") as fh:
        return json.load(fh)


# ---- 1. contract -----------------------------------------------------------------------------
DROPPED = {"debug", "Debug_DistrictCategories", "Partitioned", "PartitionGridSize", "PlazaReservationSeed"}


def test_contract_parameters_are_the_official_ones_less_the_dropped_and_the_merged_seed():
    off = {p["name"]: p for p in official_ir()["params"]}
    assert set(S.PARAMS) == set(off) - DROPPED
    for name, p in S.PARAMS.items():
        assert p.default == off[name]["value"], name
        assert p.type == off[name]["type"] == "Float", name


def test_contract_inputs_are_the_seven_scene_reads_and_the_graph_wires_them():
    from pypcg import graphs, ir
    from pypcg.profiles import official
    g = graphs.graph(9)
    doc = g.to_ir(official)                      # raises on an unwired Python input pin
    py = [x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE]
    assert len(py) == 1
    wired = {p["label"] for p in py[0]["inputs"] if p["edges"]}
    assert set(S.INPUTS) | {stage_api.PARAMS_PIN} <= wired
    assert set(S.INPUTS) == {"City", "Districts", "RoadFootprints", "MainTower", "CentralParkFootprint",
                             "LandmarkPark", "Highway"}
    titles = {x["title"] for x in doc["nodes"]}
    for t in ("Get City Shape", "Get Districts", "Get Roads", "Filter Road Footprints", "Get Landmark",
              "Get Central_Park", "Landmark Small Park", "Get Highway"):
        assert t in titles, t


def test_contract_every_contract_output_reaches_the_graph_output_and_the_grid_reaches_the_grammar():
    from pypcg import graphs, ir
    from pypcg.profiles import official
    doc = graphs.graph(9).to_ir(official)
    py = [x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE][0]
    outnode = [x for x in doc["nodes"] if x["name"] == "DefaultOutputNode"][0]
    into_out = {(src, pin) for p in outnode["inputs"] for src, pin in p["edges"]}
    for pin in S.OUTPUTS:
        if pin in S.INTERNAL:
            assert (py["name"], pin) not in into_out
        else:
            assert (py["name"], pin) in into_out, pin
    grammar = [x for x in doc["nodes"] if x["title"] == "Assign Road Grammar To Grid Splines"][0]
    assert (py["name"], "GridSplines") in {(s, p) for i in grammar["inputs"] for s, p in i["edges"]}
    assert "Spawn Road Grammar Assets" in {x["title"] for x in doc["nodes"]}
    assert set(S.TAGS.values()) == {"Lots", "reservedLots", "unbuildableLots", "UnbuildableFootprints",
                                    "SmallDistrictsBldgFootprints", "MediumDistrictsBldgFootprints",
                                    "LargeDistrictsBldgFootprints", "Small Courtyards", "Medium Courtyards",
                                    "UnderHighway", "LargeBuildingSkirt"}


def test_contract_the_fixed_settings_are_the_official_overrides():
    nodes = {n["name"]: n for n in official_ir()["nodes"]}
    ov = lambda n: nodes[n].get("overrides") or {}
    assert (ov("Subgraph_30")["Iterations"], ov("Subgraph_30")["MaxSplitDistancFromCenter"]) == S.LOT_SPLIT["Small"][:2]
    assert (ov("Subgraph_28")["Iterations"], ov("Subgraph_28")["MaxSplitDistancFromCenter"]) == S.LOT_SPLIT["Medium"][:2]
    assert ov("Subgraph_64")["Contract"] == S.COURTYARD_CM["Small"]
    assert ov("Subgraph_66")["Contract"] == S.COURTYARD_CM["Medium"]
    assert (ov("Subgraph_6_SmallDistrict")["Iterations"], ov("Subgraph_6_SmallDistrict")["MinAreaSize"]) == (3, 1000)
    assert ov("Subgraph_6_MediumDistrict") == {"Iterations": 1, "MaxSplitDistancFromCenter": 0.3, "MinAreaSize": 1500}
    assert ov("Subgraph_6_LargeDistrict") == {"Iterations": 2, "MaxSplitDistancFromCenter": 0.2, "MinAreaSize": 2000}
    assert ov("Subgraph_25") == {"Iterations": 2, "MaxSplitDistancFromCenter": 0.05, "MinAreaSize": 300}
    assert [ov(n)["Threshold"] for n in ("Subgraph_31", "Subgraph_29", "Subgraph_32")] == \
        [S.SIDE_MIN_CM[c] for c in ("Small", "Medium", "Large")]
    assert ov("Subgraph_75")["Ratio"] == S.MEDIUM_KEEP
    assert ov("Subgraph_68")["Size"] == S.LARGE_PAD_MIN_M2 and ov("Subgraph_70")["Contract"] == S.LARGE_PAD_CONTRACT_CM
    assert ov("Subgraph_57") == {"SubdivLength": 2, "UseSubdivisionInsteadOfSizes": True}
    assert ov("Subgraph_58")["Size"] == S.GRAMMAR_WIDTH_CM


# ---- 2. empty inputs -------------------------------------------------------------------------
def test_empty_inputs_give_all_outputs_empty():
    out = run({pin: [] for pin in S.INPUTS})
    assert set(out) == set(S.OUTPUTS)
    assert all(not items for items in out.values())


def test_missing_input_pins_give_all_outputs_empty():
    out = S.run({}, params(), stage_api.Ctx(S.STAGE, 42, OPS))
    assert set(out) == set(S.OUTPUTS) and all(not v for v in out.values())


def test_a_city_without_districts_publishes_lots_only():
    out = by_tag(run(inputs(Districts=[])))
    assert len(out["Lots"]) == 5
    for t in S.TAGS.values():
        if t not in ("Lots", "reservedLots"):
            assert not out.get(t), t


# ---- 3. invariants -----------------------------------------------------------------------------
def test_the_lots_are_the_city_less_the_roads_and_the_landmarks():
    tower = box(1000, 1000, 3000, 3000)
    out = by_tag(run(inputs(MainTower=[(closed(tower), frozenset())])))
    assert sum(geo.area_m2(p) for p in out["Lots"]) == pytest.approx(12000 + 4 * 10000 - 400, abs=1e-6)
    assert all(overlap_m2(p, tower) == 0.0 for p in out["Lots"])
    assert all(overlap_m2(p, r) == 0.0 for p in out["Lots"] for r in ROADS)
    plain = by_tag(run(inputs()))
    assert sorted(geo.bbox(p.outer)[0][0] for p in plain["Lots"]) == [x for x, _ in LOTS]


def test_every_footprint_lies_in_its_own_class_and_off_roads_and_highway():
    for seed in (1, 2, 3):
        out = by_tag(run(inputs(), seed=seed, PlazaReservationRatio=1.0))
        for cls in S.CLASSES:
            fps = out.get(S.TAGS[cls + "Footprints"], [])
            assert fps, cls
            own = DISTRICTS[cls + "Districts"]
            for p in fps:
                assert overlap_m2(p, own) == pytest.approx(geo.area_m2(p)), cls
                assert overlap_m2(p, HIGHWAY) < 1.0
                assert all(overlap_m2(p, r) < 1.0 for r in ROADS)


def test_under_highway_is_non_empty_exactly_when_a_highway_crosses():
    assert by_tag(run(inputs(), PlazaReservationRatio=1.0)).get("UnderHighway")
    assert not by_tag(run(inputs(highway=False), PlazaReservationRatio=1.0)).get("UnderHighway")
    far = box(-5000, 50000, 65000, 51000)
    assert not by_tag(run(inputs(Highway=[(far, frozenset())]), PlazaReservationRatio=1.0)).get("UnderHighway")


def test_the_kept_share_is_an_item_ratio_within_ten_points():
    flags = [f for s in range(20) for f in geo.keep_each(50, 0.9, random.Random(s))]
    assert abs(sum(flags) / float(len(flags)) - 0.9) < 0.02
    big = [box(0, 0, 1, 1)] * 200
    kept = S.Draws(random.Random(5)).keep("plaza", big, 0.9)
    assert abs(sum(kept) / 200.0 - 0.9) <= C.SHARE_TOL
    assert geo.keep_each(10, 1.0, random.Random(0)) == [True] * 10
    assert geo.keep_each(10, 0.0, random.Random(0)) == [False] * 10


def test_the_outputs_account_for_the_prepared_lots():
    ins = inputs()
    for seed in (4, 5):
        out = run(ins, seed=seed)
        by = by_tag(out)
        pieces = C.pieces_of(ins, OPS)
        whole = sum(geo.area_m2(p) for p in pieces)
        parts = sum(geo.area_m2(p) for t in ("reservedLots", "unbuildableLots", "Small Courtyards",
                                             "Medium Courtyards", "UnderHighway") + C.FOOTPRINT_TAGS
                    for p in by.get(t, []))
        bands = sum(geo.area_m2(p) for p in A.intersection(
            S.grammar_bands([s.points for s in by.get("GridSplines", [])], OPS), pieces, OPS))
        assert whole - parts - bands == pytest.approx(0.0, abs=0.01 * whole)


def test_the_check_passes_on_a_run_and_flags_a_footprint_in_the_wrong_class():
    ins = inputs()
    out = run(ins, PlazaReservationRatio=1.0)
    assert C.check(ins, params(PlazaReservationRatio=1.0), out, OPS) == []
    wrong = dict(out)
    wrong["SmallFootprints"] = out["SmallFootprints"] + [(box(55000, 6000, 58000, 9000), ["SmallDistrictsBldgFootprints"])]
    assert any("outside the Small districts" in f for f in C.check(ins, params(PlazaReservationRatio=1.0), wrong, OPS))


def test_the_undividable_districts_are_kept_out():
    out = by_tag(run(inputs(undividable=box(0, 0, 12000, 10000)), PlazaReservationRatio=1.0))
    for t in S.TAGS.values():
        if t != "Lots":
            assert all(geo.bbox(p.outer)[0][0] >= 12000 - 1e-6 for p in out.get(t, [])), t


# ---- 4. seeds ------------------------------------------------------------------------------------
def _sig(out):
    return {pin: [geo.to_json(v) for v, _ in items] for pin, items in out.items()}


def test_seeded_runs_repeat_and_differ():
    ins = inputs()
    a, b, c = run(ins, seed=3), run(ins, seed=3), run(ins, seed=4)
    assert _sig(a) == _sig(b)
    assert _sig(a) != _sig(c)


# ---- 5. the helpers -------------------------------------------------------------------------------
def test_area_filters_are_strict_and_lesser_keeps_the_small_side():
    a, b = box(0, 0, 10000, 10000), box(0, 0, 10000, 20000)          # 10 000 and 20 000 m2
    assert A.by_size([a, b], 10000) == ([b], [a])
    assert A.by_size([a, b], 20000, greater=False) == ([a], [b])


def test_compose_with_no_clip_passes_the_subjects_through():
    a = box(0, 0, 100, 100)
    assert A.exclusion([a], [], OPS) == [a]
    assert A.intersection([a], [], OPS) == [a]


def test_min_side_is_the_shortest_run_between_corners_over_twenty_degrees():
    r = Polygon([(0, 0), (1000, 0), (2000, 50), (2000, 400), (0, 400)])     # a 2.9 deg kink on the bottom
    assert A.min_side(r) == pytest.approx(350.0)
    assert A.by_edge_length([r], 300.0) == ([r], [])
    assert A.by_edge_length([r], 400.0) == ([], [r])
    tiny = Polygon([(0, 0), (5, 0), (1000, 0.1), (1000, 500), (0, 500)])     # a 5 cm stub is fused away
    assert A.min_side(tiny) == pytest.approx(500.0, abs=0.2)


def test_the_subdivision_grid_draws_one_line_down_the_middle():
    ring = box(0, 0, 10000, 4000).outer
    lines = geo.grid_lines(ring, 0.0, 0.0, S.GRID_EXTEND_CM, S.GRID_SUBDIV)
    assert len(lines) == 1
    axis, seg = lines[0]
    assert axis == "Y"
    assert seg[0][1] == pytest.approx(2000.0, abs=1.5) and seg[-1][1] == pytest.approx(2000.0, abs=1.5)
    assert geo.path_length(seg) == pytest.approx(10000.0, abs=1e-6)
    full = geo.grid_lines(ring, 0.0, 0.0, S.GRID_EXTEND_CM, S.GRID_SUBDIV, clipped=False)
    assert len(full) == 1 and geo.path_length(full[0][1]) > 2 * S.GRID_EXTEND_CM


def test_the_size_grid_is_unchanged():
    ring = box(0, 0, 10000, 4000).outer
    lines = geo.grid_lines(ring, 3000.0, 1500.0)
    assert sorted(round(seg[0][0]) for a, seg in lines if a == "X") == [2999, 5999, 8999]
    assert len([1 for a, _ in lines if a == "Y"]) == 2


def test_a_large_lot_loses_its_grammar_band_and_the_band_is_the_full_width():
    out = run(inputs(), PlazaReservationRatio=1.0)
    lines = [s for s, _ in out["GridSplines"]]
    assert len(lines) == 1
    band = S.grammar_bands([lines[0].points], OPS)
    (x0, y0), (x1, y1) = geo.bbox(band[0].outer)
    assert y1 - y0 == pytest.approx(S.GRAMMAR_WIDTH_CM)


def test_the_oracle_draw_reserves_exactly_the_official_lots():
    pieces = [box(0, 0, 100, 100), box(200, 0, 300, 100), box(400, 0, 600, 100)]
    d = C.OfficialPlaza(random.Random(0), [box(200, 0, 300, 100)])
    assert d.keep("plaza", pieces, 0.9) == [True, False, True]


def _strip_city(n):
    """A city of n 100 x 100 m lots in a row, split by n - 1 roads 20 m wide, all one small district."""
    w = 12000.0
    roads = [box(w * k - 2000, -1000, w * k, 11000) for k in range(1, n)]
    city = box(0, 0, w * n - 2000, 10000)
    return {"City": [(closed(city), frozenset({"City"}))],
            "Districts": [(city, frozenset({"SmallDistricts"}))],
            "RoadFootprints": [(r, frozenset()) for r in roads],
            "MainTower": [], "CentralParkFootprint": [], "LandmarkPark": [], "Highway": []}


def test_the_stage_reserves_one_minus_the_ratio_of_its_lots_on_average():
    ins = _strip_city(25)
    pieces = C.pieces_of(ins, OPS)
    assert len(pieces) == 25                       # above the check's 20-lot guard
    shares = []
    for seed in range(60):
        raw = S.lots(ins, params(), OPS, S.Draws(random.Random(seed)))
        shares.append(len(raw["ReservedLots"]) / float(len(pieces)))
    mean = sum(shares) / len(shares)
    assert mean == pytest.approx(1.0 - params()["PlazaReservationRatio"], abs=0.02)
    out = run(ins, seed=3)
    assert not [f for f in C.check(ins, params(), out, OPS) if "kept share" in f]
    skewed = dict(out, ReservedLots=[(p, ["reservedLots"]) for p in pieces[:10]])
    assert any("kept share" in f for f in C.check(ins, params(), skewed, OPS))


def test_a_zero_grid_size_still_fails_loudly_outside_subdivision_mode():
    with pytest.raises(ZeroDivisionError):
        geo.grid_lines(box(0, 0, 10000, 4000).outer, 0.0, 1500.0)


def test_the_check_cache_keys_on_content_not_identity():
    a, b = inputs(), inputs(highway=False)
    assert C._key(a) == C._key(inputs()) and C._key(a) != C._key(b)
    off1 = {"Lots": [box(0, 0, 1, 1)]}
    off2 = {"Lots": [box(0, 0, 2, 2)]}
    assert C._key(a, off1) != C._key(a, off2)
