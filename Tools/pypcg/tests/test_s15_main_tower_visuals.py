"""Stage 15, MainTowerVisuals (Task 22; spec 3, Step B).

The contract against the official IR (parameters, the three scene reads, the 30 kept generation nodes with their
official settings, no published output), empty inputs, the invariants of `pypcg.checks.s15`, and the seeded
repeat / differ of the one random part (the tree kit and scale). Geometry pins come from
`Tools/pypcg/data/s15_fixture.json` (the official graph's taps, 2026-10-20).

Offline there is no engine boolean: `ConvexOps` offsets convex rings exactly (each edge moved, neighbours
intersected -- a regular hexagon's contract and expand, which is all the main node asks of it) and `FakeOps`
cuts convex rings with straight lines. Neither reproduces Clipper's start vertex, so the arm sectors are pinned
as vertex SETS here; their order is the editor's, checked live by V1's replay (`checks.s15.replay`).
"""
import json
import math
import os

import pytest

from fakes import FakeOps, FlatTerrain
from pypcg import geo, stage_api
from pypcg.checks import s15 as C
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import assets as AS
from pypcg.stages import s15_main_tower_visuals as S
from pypcg.stages import s15_tower_level1 as L1
from pypcg.stages import s15_tower_level2 as L2
from pypcg.stages import s15_tower_level3 as L3
from pypcg.stages import s15_tower_rings as R
from pypcg.stages import s15_tower_sidewalk as W
from pypcg.stages import s15_tower_top as T

REPO = stage_api.REPO
PIVOT = (-613.8667464186474, 142.0539320733078)
KEPT = {"AssignBuilding", "SpawnPlaza", "SpawnTrees", "Subgraph_1", "Subgraph_12", "Subgraph_13", "Subgraph_14",
        "Subgraph_16", "Subgraph_21", "Subgraph_24", "Subgraph_25", "Subgraph_3", "Subgraph_32", "Subgraph_4",
        "Subgraph_40", "Subgraph_41", "Subgraph_46", "Subgraph_48", "Subgraph_50", "Subgraph_51", "Subgraph_53",
        "Subgraph_55", "Subgraph_57", "Subgraph_58", "Subgraph_6", "Subgraph_60", "Subgraph_62", "Subgraph_64",
        "Subgraph_66", "Subgraph_8"}
READS = {"Subgraph_0", "Subgraph_26", "Subgraph_35"}


def official_ir():
    with open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_4_1_MainTower_Visuals.json"), encoding="utf-8") as fh:
        return json.load(fh)


def official(name):
    return next(n for n in official_ir()["nodes"] if n["name"] == name)


def fixture():
    with open(os.path.join(REPO, "Tools", "pypcg", "data", "s15_fixture.json"), encoding="utf-8") as fh:
        return json.load(fh)


class ConvexOps(FakeOps):
    """Exact offsets of a convex ring (miter: each edge moved by `distance`, neighbours intersected); union is
    the identity on disjoint rings; difference returns the subject (the notches are measured live)."""

    def offset(self, rings, distance, join="square", miter_limit=2.0):
        r = list(geo.ccw(rings[0]))
        n = len(r)
        lines = []
        for i in range(n):
            a, b = r[i], r[(i + 1) % n]
            L = math.dist(a, b)
            d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
            lines.append(((a[0] + d[1] * distance, a[1] - d[0] * distance), d))
        out = []
        for i in range(n):
            (p1, d1), (p2, d2) = lines[i - 1], lines[i]
            den = d1[0] * d2[1] - d1[1] * d2[0]
            t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
            out.append((p1[0] + t * d1[0], p1[1] + t * d1[1]))
        return [Polygon(out)] if geo.signed_area(out) > 0 else []

    def union(self, rings):
        return [Polygon(list(r)) for r in rings]

    def difference(self, rings_a, rings_b):
        return [Polygon(list(rings_a[0]))]


class LoaderOps(ConvexOps):
    """ConvexOps plus `assets`: one static-mesh entry per path (a 2 x 2 x 10 m box)."""

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


def demo_inputs(z_terrain=2041.2605147304):
    fx = fixture()
    shape = [(p[0], p[1], 4.9e-13) for p in fx["rings"]["aligned"]]
    return {"Volume": [(Spline(shape, closed=True, linear=True), frozenset())],
            "MeshTerrain": [(FlatTerrain(z_terrain), frozenset())]}


def run_main(seed=42, ops=None, inputs=None, mega=False):
    out, ctx = stage_api.execute(S, demo_inputs() if inputs is None else inputs,
                                 {stage_api.SEED: seed, "UseMegaplantsTrees": mega}, ops or LoaderOps())
    return out, ctx


def ring(v):
    return [tuple(p[:2]) for p in (v.points if isinstance(v, Spline) else v.outer)]


def set_dist(a, b):
    return max(min(math.dist(p, q) for q in a) for p in b)


# ---- contract -------------------------------------------------------------------------------------------
def _graph():
    from pypcg import graphs, ir
    from pypcg.profiles import official as prof
    doc = graphs.graph(15).to_ir(prof)                      # raises on an unwired Python input pin
    by = {x["name"]: x for x in doc["nodes"]}
    py = {x["title"]: x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE}
    return doc, by, py


def _feeds(node, by):
    return {p["label"]: [(by[e[0]], e[1]) for e in p["edges"]] for p in node["inputs"]}


def test_contract_parameters():
    assert {p["name"] for p in official_ir()["params"]} == {"RectWidth", "RectLength", "NewProperty",
                                                            "UseMegaplantsTrees"}
    assert list(S.PARAMS) == ["UseMegaplantsTrees"] and S.PARAMS["UseMegaplantsTrees"].default is False
    doc, _by, _py = _graph()
    assert [p["name"] for p in doc["params"]] == [stage_api.SEED, "UseMegaplantsTrees"]   # three dropped


def test_contract_keeps_the_30_generation_nodes_and_the_3_reads_as_officially_set():
    doc, _by, _py = _graph()

    def key(n):
        return (n.get("subgraph"), json.dumps(n.get("overrides") or {}, sort_keys=True), n.get("title") or "")
    kept = sorted(key(n) for n in doc["nodes"] if n["class"] == "PCGSubgraphSettings")
    from pypcg.profiles import official as prof
    want = []
    for name in sorted(KEPT | READS):
        n = dict(official(name))
        if "ActorReferences" in (n.get("overrides") or {}):
            from pypcg import dsl
            n["overrides"] = dict(n["overrides"], ActorReferences=[prof.ROLES[r] for r in dsl.roles_of(n["overrides"]["ActorReferences"])])
        want.append(key(n))
    assert len(KEPT) == 30 and kept == sorted(want)


def test_contract_publishes_nothing():
    doc, by, _py = _graph()
    out = next(n for n in doc["nodes"] if n["name"] == "DefaultOutputNode")
    assert all(not p["edges"] for p in out["inputs"])
    assert all(not p["edges"] for p in official("DefaultOutputNode")["inputs"])


def test_contract_python_nodes_and_their_feeds():
    _doc, by, py = _graph()
    assert set(py) == {"Python: s15_main_tower_visuals", "Python: s15_tower_level1", "Python: s15_tower_level2",
                       "Python: s15_tower_level3", "Python: s15_tower_top", "Python: s15_tower_sidewalk"}
    main = _feeds(py["Python: s15_main_tower_visuals"], by)
    assert set(S.INPUTS) | {stage_api.PARAMS_PIN} == set(main)
    assert [n["title"] for n, _p in main["Volume"]] == [official("Subgraph_35")["title"]]
    assert [n["title"] for n, _p in main["MeshTerrain"]] == [official("Subgraph_26")["title"]]
    assert not any(n["class"] == "PCGDataFromActorSettings" for n in by.values())     # no read of its own
    # Subgraph_1 reads all 15 tower rooftops; Subgraph_21 the selected rooftop then the skyscraper's
    roofs = next(n for n in by.values() if n.get("title") == "All Building Rooftop Geo")
    assert [p for _n, p in _feeds(roofs, by)["PrimaryInput"]] == ["Rooftops Footprints"] * 15
    asm = next(n for n in by.values() if n.get("title") == "Place  Rooftop Assemblies ")
    assert [(n["title"], p) for n, p in _feeds(asm, by)["PrimaryInput"]] == [
        ("Python: s15_tower_level3", "Assemblies"), (official("Subgraph_66")["title"], "Rooftops Footprints")]


# ---- empty inputs -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("module", [S, L1, L2, L3, T, W])
def test_empty_inputs_give_no_outputs(module):
    params = {stage_api.SEED: 42}
    params.update({k: (v.default if hasattr(v, "default") else v) for k, v in module.PARAMS.items()})
    out, _ctx = stage_api.execute(module, {pin: [] for pin in module.INPUTS}, params, LoaderOps())
    assert all(not items for items in out.values())


# ---- the geometry against the taps ------------------------------------------------------------------------
def test_arm_sectors_are_the_tapped_sectors():
    """From the tapped outer ring: centre slice -> 90 m, -120 arm -> 80 m, +120 arm -> 70 m, every vertex to
    1e-9 cm, wound as the engine winds them (negative standard area)."""
    fx = fixture()
    outer = [tuple(p) for p in fx["rings"]["outer30_vertices"]]
    shape = [tuple(p) for p in fx["rings"]["aligned"]]
    secs = S.arms(outer, shape, PIVOT, FakeOps())
    taps = {"Sector90": fx["rings"]["sectors"][2], "Sector80": fx["rings"]["sectors"][1],
            "Sector70": fx["rings"]["sectors"][0]}
    for pin, tap in taps.items():
        got = [p[:2] for p in secs[pin]]
        assert set_dist(got, [tuple(p[:2]) for p in tap]) <= 1e-9, pin
        assert geo.signed_area(got) < 0, pin


def test_the_set_align_cancels_the_turns_pivot():
    """Officially the turns are about the volume's location; after the set align any pivot gives the same
    sectors (1.4e-12 cm), so the port needs no read of its own volume. Aligning ONE piece instead of the set
    -- the draft's rule -- does not."""
    fx = fixture()
    outer = [tuple(p) for p in fx["rings"]["outer30_vertices"]]
    shape = [tuple(p) for p in fx["rings"]["aligned"]]
    a, b = S.arms(outer, shape, PIVOT, FakeOps()), S.arms(outer, shape, (0.0, 0.0), FakeOps())
    assert all(max(math.dist(p[:2], q[:2]) for p, q in zip(a[k], b[k])) <= 1e-9 for k in a)
    one = S._align_set([S.F.rotate_in_frame(h, -60.0, PIVOT) for h in [fx["rings"]["center_halves"][0]]], shape)[0]
    assert set_dist([p[:2] for p in one], [tuple(p[:2]) for p in fx["rings"]["sectors"][2]]) > 100.0


def test_frame_edge_takes_the_first_of_tied_edges():
    fx = fixture()
    outer = [tuple(p[:2]) for p in fx["rings"]["outer30_vertices"]]
    assert geo.plane.longest(outer) == 2                     # Python's last bits pick edge 2 ...
    assert S.frame_edge(outer) == 0                          # ... the tapped bands are cut along edge 0
    assert S.frame_edge([(0, 0), (10, 0), (10, 1), (0, 1)]) == 0


def test_hexagons_are_the_tapped_hexagons_in_order():
    fx = fixture()
    inner = [tuple(p) for p in fx["rings"]["inner32_level"]]
    hexes = S.hexagons(inner)
    assert len(hexes) == 6
    for got, tap in zip(hexes, fx["copy"]["hex"]):
        assert max(math.dist(a[:2], tuple(b)) for a, b in zip(got, tap)) <= 1e-9
        assert all(p[2] == inner[0][2] for p in got)


def test_main_node_on_the_demo_shape():
    out, ctx = run_main()
    fx = fixture()
    for pin, tap in (("Sector90", 2), ("Sector80", 1), ("Sector70", 0)):        # the whole chain, from the shape
        assert set_dist(ring(out[pin][0][0]), [tuple(p[:2]) for p in fx["rings"]["sectors"][tap]]) <= 1e-9, pin
    trees = [p for v, _t in out["TreeBases"] for p in v.loc]
    assert max(math.dist(a[:2], tuple(b[:2])) for a, b in zip(trees, fx["trees"]["points"])) <= 0.005
    assert set_dist(ring(out["InnerRing"][0][0]), [tuple(p[:2]) for p in fx["rings"]["inner32_level"]]) <= 1e-9
    assert out["InnerRing"][0][0].points[0][2] == pytest.approx(2041.2605147304)
    assert len(out["Hexagons"]) == 6 and [len(out[p]) for p in ("Sector90", "Sector80", "Sector70")] == [1, 1, 1]
    assert sum(len(v) for v, _t in out["Trees"]) == sum(len(v) for v, _t in out["TreeBases"]) == 44
    assert len(out["PlazaTiles"][0][0]) == 1871
    assert all(v.attrs[AS.ASSET_ATTR] == [S.PLAZA_MESH] * len(v) for v, _t in out["PlazaTiles"])
    assert all(r[0] == 0.0 and r[2] == 0.0 for v, _t in out["Trees"] for r in v.rot)       # roll, pitch 0
    assert all(s == (1.0, 1.0, 1.0) for v, _t in out["TreeBases"] for s in v.scale)       # scale 1
    assert C.check(demo_inputs(), {}, out, None) == []


# ---- the invariants ----------------------------------------------------------------------------------------
def test_check_finds_a_tree_off_the_ring():
    out, _ctx = run_main()
    pts = out["Trees"][0][0]
    pts.loc[3] = (pts.loc[3][0], pts.loc[3][1] + 50.0, pts.loc[3][2])
    assert any("off the 500 cm band" in f for f in C.check(demo_inputs(), {}, out, None))


def test_check_finds_overlapping_hexagons_and_a_lost_tree():
    out, _ctx = run_main()
    out["Hexagons"][1] = (Spline([(p[0] + 500.0, p[1], p[2]) for p in out["Hexagons"][0][0].points],
                                 closed=True, linear=True), ["Hexagons"])
    fails = C.check(demo_inputs(), {}, out, None)
    assert any("overlap" in f for f in fails) and any("off every inner-ring vertex" in f for f in fails)
    out, _ctx = run_main()
    out["TreeBases"][0][0].loc.pop()
    assert any("want int(" in f for f in C.check(demo_inputs(), {}, out, None))


def test_check_on_empty_inputs():
    assert C.check({"Volume": []}, {}, {pin: [] for pin in S.OUTPUTS}, None) == []
    assert C.check({"Volume": []}, {}, {"Hexagons": [(Spline([(0, 0, 0), (1, 0, 0), (0, 1, 0)], closed=True), ["x"])]},
                   None) == ["no input shape but outputs on ['Hexagons']"]


def test_contracted_rings_nest_inside_their_rooftops():
    roof = [(1000.0 * math.cos(math.radians(a)), 1000.0 * math.sin(math.radians(a)), 8800.0) for a in range(0, 360, 72)]
    item = (Spline(roof, closed=True, linear=True), frozenset())
    out, _ctx = stage_api.execute(L2, {"Chj1Roofs": [item], "Arm90Roofs": [item], "Arm80Roofs": [], "Arm70Roofs": []},
                                  {stage_api.SEED: 42}, ConvexOps())
    for pin, d in (("Chj2", 400.0), ("Arm90", 150.0)):
        [(poly, tags)] = out[pin]
        assert isinstance(poly, Polygon) and poly.z == 8800.0 and tags == [pin]
        assert all(C.inside(p, [q[:2] for q in roof]) for p in poly.outer)
        assert min(C.dist_to_ring(p, [q[:2] for q in roof]) for p in poly.outer) == pytest.approx(d)


def test_level3_forwards_the_selected_rooftop_and_contracts_the_skyscraper():
    big = [(x * 3000.0, y * 3000.0, 24156.26) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]       # 3600 m2
    small = [(x * 1000.0, y * 1000.0, 24156.26) for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1))]     # 400 m2
    a, b = Spline(big, closed=True, linear=True), Spline(small, closed=True, linear=True)
    out, _ctx = stage_api.execute(L3, {"Chj2Roofs": [(a, frozenset()), (b, frozenset())], "Arm90Roofs": [],
                                       "Arm80Roofs": [], "Arm70Roofs": []}, {stage_api.SEED: 42}, ConvexOps())
    assert [v for v, _t in out["Assemblies"]] == [a]            # the very object: forwarded unchanged
    assert len(out["Skyscraper"]) == 1                          # the 20 m square contracts 10 m to nothing


def test_courtyard_at_z_0_in_the_union_order():
    """AttributeMathsOp_1 sets Z from an unwired input: 0 (taps u33 / u27 / u28), and the union hands the six
    pieces back in descending x, then ascending y."""
    fx = fixture()
    hexes = [[(p[0], p[1], 2041.26) for p in h] for h in fx["copy"]["hex"]]
    grown, lifted = R.courtyard(hexes, ConvexOps())
    assert [p.z for p in grown] == [0.0] * 6 and [p.z for p in lifted] == [40.0] * 6
    cents = [tuple(round(c, 1) for c in (sum(q[0] for q in p.outer) / 6, sum(q[1] for q in p.outer) / 6)) for p in grown]
    assert cents == [(4247.2, 0.0), (2123.6, -3678.2), (2123.6, 3678.2), (-2123.6, -3678.2), (-2123.6, 3678.2),
                     (-4247.2, 0.0)]
    assert all(area / 1e4 == pytest.approx(710.8847, abs=1e-3) for area in (C.area(p.outer) for p in grown))


def test_antenna_turns_along_the_rooftops_first_edge():
    r = 1585.6385
    roof = [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), 43756.26) for a in (180, 120, 60, 0, -60, -120)]
    (loc, yaw) = R.centre_point(roof)
    assert loc[:2] == pytest.approx((0.0, 0.0), abs=1e-9) and loc[2] == 43756.26 and yaw == pytest.approx(60.0)


def test_outline_squares_on_the_chc_rooftop():
    """Subgraph_17 / 18 / 9 on a CHC-like rooftop (apothem 3598.2032): six centres, each square turned yaw - 90."""
    R_ = 3598.2032 / math.cos(math.radians(30))
    roof = [(R_ * math.cos(math.radians(a)), R_ * math.sin(math.radians(a)), 6556.26) for a in (180, 120, 60, 0, -60, -120)]
    pts = R.outline_points(roof)
    assert len(pts) == 6 and all(math.hypot(x, y) == pytest.approx(3598.2032, abs=1e-3) for x, y, _z, _w in pts)
    for sq, (x, y, _z, yaw) in zip(R.squares(pts), pts):
        assert (sum(p[0] for p in sq) / 4, sum(p[1] for p in sq) / 4) == pytest.approx((x, y))


# ---- randomness ---------------------------------------------------------------------------------------------
def _trees(out):
    return [geo.to_json(v) for v, _t in out["Trees"]]


def test_same_seed_repeats_and_another_seed_differs():
    a, _ = run_main(42)
    b, _ = run_main(42)
    c, _ = run_main(7)
    assert _trees(a) == _trees(b)
    assert _trees(a) != _trees(c)
    for key in ("InnerRing", "Hexagons", "Sector90", "PlazaTiles"):                 # the draws touch only the trees
        assert [geo.to_json(v) for v, _t in a[key]] == [geo.to_json(v) for v, _t in c[key]]


def test_megaplants_switch_changes_the_kit():
    out, _ = run_main(mega=True)
    names = {n for v, _t in out["Trees"] for n in v.attrs.get(AS.ASSET_ATTR, [])}
    assert names and all("Megaplants" in n for n in names)
