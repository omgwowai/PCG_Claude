"""Stage 12, Rooftops (Task 21; spec 3, Step B).

The invariants are the task brief's:
  - every placement area is inside a rooftop polygon;
  - the small / WFC / skyscraper sets do not overlap -- read as the brief means it on this graph (s12.md 5.2): the
    WFC, skyscraper and vent ROOFTOPS are disjoint, and no WFC assembly mesh that survives the difference overlaps a
    small-assembly mesh;
  - the `Average` (not max) z reduction is what the note describes and the code does;
  - empty inputs -> no outputs, on both Python nodes.

Bit-for-bit pins come from `Tools/pypcg/data/s12_fixture.json` (eight official rooftops with the official polygons,
offsets and heights; one official WFC item, the small points near it and what the official difference kept), made
by `Tools/pypcg/s12_measure_offline.py --fixture` from the official taps."""
import json
import math
import os

from fakes import FakeOps
from pypcg import geo, stage_api
from pypcg.checks import s12 as C
from pypcg.geo import Points, Polygon, Spline
from pypcg.geo import frames as F
from pypcg.geo import ground as G
from pypcg.stages import s12_rooftops as S
from pypcg.stages import s12_rooftops_assemblies as A

REPO = stage_api.REPO
OPS = FakeOps()


def official_ir():
    with open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_3_3_2_Rooftops.json"), encoding="utf-8") as fh:
        return json.load(fh)


def official(name):
    return next(n for n in official_ir()["nodes"] if n["name"] == name)


def fixture():
    with open(os.path.join(REPO, "Tools", "pypcg", "data", "s12_fixture.json"), encoding="utf-8") as fh:
        return json.load(fh)


def roof(x0, y0, w, h, z, tag, extra=()):
    pts = [(x0, y0, z), (x0 + w, y0, z), (x0 + w, y0 + h, z), (x0, y0 + h, z)]
    return Spline(pts, closed=True, linear=True), frozenset({tag, "Type:ClosedSpline", *extra})


def m2(side_m):
    return side_m * 100.0


# one rooftop of every kind, side lengths in metres (area = side^2)
ROOFS = [roof(0, 0, m2(20), m2(20), 3000.0, "SmallRooftops"),                  # 400 m2 > 300: WFC
         roof(5000, 0, m2(15), m2(15), 3000.0, "SmallRooftops"),               # 225 m2: vents
         roof(10000, 0, m2(30), m2(30), 4000.0, "MediumRooftops"),             # 900 m2 > 800: small assemblies only
         roof(15000, 0, m2(25), m2(25), 4000.0, "MediumRooftops"),             # 625 m2: vents
         roof(20000, 0, m2(20), m2(20), 9000.0, "LargeRooftops"),              # 400 m2 <= 500: WFC
         roof(25000, 0, m2(25), m2(25), 6000.0, "LargeRooftops"),              # 625 m2, 60 m: WFC
         roof(30000, 0, m2(25), m2(25), 9000.0, "LargeRooftops")]              # 625 m2, 90 m: skyscraper


def run(items=None):
    out, _ctx = stage_api.execute(S, {"Rooftops": ROOFS if items is None else items}, {stage_api.SEED: 42}, OPS)
    return out


# ---- contract ---------------------------------------------------------------------------------------
def test_contract_no_parameters_of_its_own():
    assert {p["name"] for p in official_ir()["params"]} == {"Partitioned"}
    assert S.PARAMS == {} and A.PARAMS == {}
    from pypcg import graphs
    from pypcg.profiles import official as prof
    assert [p["name"] for p in graphs.graph(12).to_ir(prof)["params"]] == [stage_api.SEED]   # Partitioned dropped


def _graph():
    from pypcg import graphs, ir
    from pypcg.profiles import official as prof
    doc = graphs.graph(12).to_ir(prof)                 # raises on an unwired Python input pin
    by = {x["name"]: x for x in doc["nodes"]}
    py = {x["title"]: x for x in doc["nodes"] if x["class"] == ir.PYTHON_NODE}
    return doc, by, py


def _feeds(node, by):
    return {p["label"]: [(by[e[0]], e[1]) for e in p["edges"]] for p in node["inputs"]}


def test_contract_scene_read_feeds_the_python_node_by_name():
    _doc, by, py = _graph()
    assert set(py) == {"Python: s12_rooftops", "Python: s12_rooftops_assemblies"}
    main = _feeds(py["Python: s12_rooftops"], by)
    assert set(S.INPUTS) | {stage_api.PARAMS_PIN} == set(main)
    [(read, _pin)] = main["Rooftops"]
    assert read["title"] == "Get Building Rooftop Polygons"
    assert read["overrides"]["ActorReferences"] == official("Subgraph_0")["overrides"]["ActorReferences"]


def test_contract_the_kept_nodes_are_fed_as_officially():
    doc, by, py = _graph()
    kept = {x["title"]: x for x in doc["nodes"] if x["class"] == "PCGSubgraphSettings"}
    for pin, name in (("SmallAssemblyAreas", "Subgraph_2"), ("WfcAreas", "Subgraph_7"),
                      ("SkyscraperAreas", "Subgraph_3"), ("VentAreas", "Subgraph_11")):
        node = kept[official(name)["title"]]
        assert node["overrides"] == official(name)["overrides"]            # assets, overlap, SpawnAssets false
        [(src, out)] = _feeds(node, by)["PrimaryInput"]
        assert (src["title"], out) == ("Python: s12_rooftops", pin)
    asm = _feeds(py["Python: s12_rooftops_assemblies"], by)
    assert [(x["title"], p) for x, p in asm["WfcPoints"]] == [(official("Subgraph_7")["title"], "Out")]
    assert [(x["title"], p) for x, p in asm["SmallPoints"]] == [(official("Subgraph_2")["title"], "Out")]
    # Subgraph_12 reads Subgraph_7 as Primary and Subgraph_2 as Secondary
    d = {p["label"]: p["edges"] for p in official("Subgraph_12")["inputs"]}
    assert d["PrimaryInput"] == [["Subgraph_7", "Out"]] and d["SecondaryInput"] == [["Subgraph_2", "Out"]]
    # the spawner: Branch_1's In order (Subgraph_12, 11, 3, 2)
    spawn = kept["Spawn All Rooftop Assemblies"]
    order = [(x["title"], p) for x, p in _feeds(spawn, by)["PrimaryInput"]]
    assert [e[0] for p in official("Branch_1")["inputs"] if p["label"] == "In" for e in p["edges"]] == \
        ["Subgraph_12", "Subgraph_11", "Subgraph_3", "Subgraph_2"]
    assert order == [("Python: s12_rooftops_assemblies", "Points"), (official("Subgraph_11")["title"], "Out"),
                     (official("Subgraph_3")["title"], "Out"), (official("Subgraph_2")["title"], "Out")]
    out = next(x for x in doc["nodes"] if x["name"] == "DefaultOutputNode")
    assert not any(p["edges"] for p in out["inputs"])                     # publishes nothing


def test_contract_constants_are_the_official_settings():
    for tag, node in zip(S.CLASS_TAGS, ("FilterDataByTag_0", "FilterDataByTag_2", "FilterDataByTag_3")):
        assert official(node)["settings"]["SelectedTags"] == tag
    for tag, node in (("SmallRooftops", "Subgraph_9"), ("MediumRooftops", "Subgraph_6"), ("LargeRooftops", "Subgraph_5")):
        assert official(node)["overrides"] == {"Operator": "Greater", "Size": S.SIZE_M2[tag]}
        assert C.SIZE_M2[tag] == S.SIZE_M2[tag]
    assert official("Subgraph_8")["overrides"]["offset"] == {"X": 0, "Y": 0, "Z": S.SMALL_OFFSET_CM}
    assert official("Subgraph_10")["overrides"]["offset"] == {"X": 0, "Y": 0, "Z": S.SKYSCRAPER_OFFSET_CM}
    f = official("FilterDataByAttribute_1")["settings"]
    assert f["Attribute"] == "@data.height" and f["Threshold"]["AttributeTypes"]["DoubleValue"] == S.SKYSCRAPER_Z_CM
    assert "FilterOperator" not in f                                       # the default: Greater (probed 2026-10-20)
    # the reduce sets no Operation: the default, Average (probed), whatever its title says
    r = official("AttributeReduce_0")
    assert "Operation" not in r["settings"] and r["title"] == "Reduce Z To Max Height Per Building"
    diff = official("Subgraph_12")
    assert diff["subgraph"].endswith("Compose_Points_Difference.Compose_Points_Difference") and diff["overrides"] == {}


# ---- empty inputs -----------------------------------------------------------------------------------
def test_empty_inputs_main_node():
    for items in ([], [(Spline([(0, 0, 0), (1, 0, 0)], closed=False), frozenset({"SmallRooftops"}))]):
        out = run(items)
        assert all(out[pin] == [] for pin in S.OUTPUTS)


def test_empty_inputs_assemblies_node():
    out, _ctx = stage_api.execute(A, {"WfcPoints": [], "SmallPoints": []}, {stage_api.SEED: 42}, OPS)
    assert out == {"Points": []}
    wfc = _pts([((0.0, 0.0, 0.0), 50.0)])
    out, _ctx = stage_api.execute(A, {"WfcPoints": [(wfc, frozenset())], "SmallPoints": []}, {stage_api.SEED: 42}, OPS)
    assert [v for v, _t in out["Points"]] == [wfc]                         # no differences: through untouched


# ---- invariants -------------------------------------------------------------------------------------
def test_every_placement_area_is_inside_its_rooftop():
    out = run()
    assert C.check({"Rooftops": ROOFS}, {}, out, None) == []
    for pin in S.OUTPUTS:
        for v, _t in out[pin]:
            pts = C._area_points(v)
            assert any(all(geo.inside(p[:2], [q[:2] for q in r.points]) or C._dist_to_ring(p[:2], [q[:2] for q in r.points]) < 1e-6
                           for p in pts) for r, _t in ROOFS)


def test_wfc_skyscraper_and_vent_rooftops_do_not_overlap():
    out = run()
    owners = {pin: {C._owner(v, [C._roof(r) for r, _t in ROOFS], C.LOWER_CM[pin]) for v, _t in out[pin]}
              for pin in S.OUTPUTS}
    assert owners["WfcAreas"] == {0, 4, 5}
    assert owners["SkyscraperAreas"] == {6}
    assert owners["VentAreas"] == {1, 3}
    assert owners["SmallAssemblyAreas"] == {0, 1, 2, 4, 5, 6}               # every rooftop but the medium <= 800 m2
    assert not (owners["WfcAreas"] & owners["SkyscraperAreas"] or owners["WfcAreas"] & owners["VentAreas"]
                or owners["SkyscraperAreas"] & owners["VentAreas"])


def test_the_height_split_is_the_average_z_not_the_max():
    # a large rooftop tilted from 6 000 to 8 500 cm: its max is above 70 m, its vertex average is not
    tilted = Spline([(0, 0, 6000.0), (2500, 0, 6000.0), (2500, 2500, 8500.0), (0, 2500, 6000.0)], closed=True)
    item = (tilted, frozenset({"LargeRooftops"}))
    r = S.Roof(tilted, item[1])
    zs = [v[2] for v in r.poly.vertices]
    assert max(zs) > S.SKYSCRAPER_Z_CM > S.average_z(r)
    assert abs(S.average_z(r) - sum(zs) / len(zs)) < 1e-9
    out = run([item])
    assert out["SkyscraperAreas"] == [] and [v for v, _t in out["WfcAreas"]] == [tilted]
    # and above the line by average: lift the three low corners
    high = Spline([(0, 0, 7100.0), (2500, 0, 7100.0), (2500, 2500, 6900.0), (0, 2500, 7100.0)], closed=True)
    out = run([(high, frozenset({"LargeRooftops"}))])
    assert len(out["SkyscraperAreas"]) == 1 and out["WfcAreas"] == []


def test_average_z_is_sum_times_float_reciprocal():
    r = S.Roof(*roof(0, 0, 3000, 3000, 7000.3, "LargeRooftops"))
    zs = [v[2] for v in r.poly.vertices]
    s = 0.0
    for z in zs:
        s += z
    assert S.average_z(r) == s * F.f32(1.0 / len(zs))


def test_offsets_lower_by_the_official_amounts():
    out = run()
    small = out["SmallAssemblyAreas"]
    assert [type(v).__name__ for v, _t in small] == ["Polygon"] * 4 + ["Spline"] * 2   # polygons first, then splines
    by_z = sorted({round(p[2], 6) for v, _t in small for p in C._area_points(v)})
    assert by_z == [2992.0, 3992.0, 5992.0, 8992.0]
    assert all(abs(p[2] - 8980.0) < 1e-9 for v, _t in out["SkyscraperAreas"] for p in C._area_points(v))
    # the forwarded ones are the very input splines
    assert all(any(v is r for r, _t in ROOFS) for pin in ("WfcAreas", "VentAreas") for v, _t in out[pin])


def test_forwarded_rooftops_reach_the_fitting_nodes_as_the_engine_objects():
    out = run()
    registry = {}
    for k, (v, _t) in enumerate(ROOFS):
        v.source = k
        registry[k] = ("object %d" % k, stage_api.snapshot(v))
    try:
        for pin in ("WfcAreas", "VentAreas"):
            assert all(stage_api.unchanged(v, registry) is not None for v, _t in out[pin])
        assert all(stage_api.unchanged(v, registry) is None for v, _t in out["SmallAssemblyAreas"])
    finally:
        for v, _t in ROOFS:
            v.source = None
    assert S.FORWARD_SPLINES is True and A.EXACT_ROTATIONS is True


# ---- bit for bit against the official taps (fixture) ------------------------------------------------
def _fixture_roof(r):
    return S.Roof(Spline([tuple(p) for p in r["points"]], closed=True, linear=True, frame=((0.0, 0.0, 0.0),
                  (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0))), frozenset(r["tags"]))


def test_fixture_polygons_frames_and_heights_bit_for_bit():
    fx = fixture()
    assert {r["kind"] for r in fx["roofs"]} >= {"small>300", "medium>800", "medium<=800", "large<=500",
                                                "large>500 low", "large>500 high"}
    for r in fx["roofs"]:
        ro = _fixture_roof(r)
        t, q = ro.poly.frame
        assert (list(t), list(q)) == (r["official_polygon"]["t"], r["official_polygon"]["q"]), r["kind"]
        assert [list(v) for v in ro.poly.vertices] == r["official_polygon"]["vp"], r["kind"]
        if r["official_height"] is not None:
            assert S.average_z(ro) == r["official_height"]
            assert (S.average_z(ro) > S.SKYSCRAPER_Z_CM) == (r["kind"] == "large>500 high")


def test_fixture_offsets_bit_for_bit():
    for r in fixture()["roofs"]:
        ro = _fixture_roof(r)
        for key, dz in (("official_offset8", S.SMALL_OFFSET_CM), ("official_offset20", S.SKYSCRAPER_OFFSET_CM)):
            off = r[key]
            if off is None:
                continue
            if "control" in off:
                assert [list(p) for p in S.offset_spline(ro, dz).points] == off["control"]
                continue
            poly = S.offset_polygon(ro, dz)
            pos, _rot, (t, q) = F.rebuilt_vertices([(x, y, z) for (x, y), z in zip(poly.outer, poly.zs)])
            assert (list(t), list(q)) == (off["t"], off["q"]), (r["kind"], key)
            assert [list(v) for v in pos] == off["vp"], (r["kind"], key)


def _pts_from(d):
    p = Points()
    for name, t in d["types"].items():
        p.declare(name, t)
    for i in range(len(d["loc"])):
        p.add(tuple(d["loc"][i]), scale=tuple(d["scale"][i]), bounds_min=tuple(d["bounds_min"][i]),
              bounds_max=tuple(d["bounds_max"][i]), density=d["density"][i], steepness=d["steepness"][i],
              seed=d["seed"][i], **{k: v[i] for k, v in d["attrs"].items()})
    p.quat = [tuple(q) for q in d["quat"]]
    return p


def test_fixture_difference_keeps_what_the_official_kept():
    d = fixture()["difference"]
    wfc, small = _pts_from(d["wfc"]), _pts_from(d["small_near"])
    [kept], removed = A.difference([wfc], [small])
    assert [list(v) for v in kept.loc] == d["official_kept_loc"]
    assert [list(q) for q in kept.quat] == d["official_kept_quat"]
    assert removed == len(wfc) - len(d["official_kept_loc"]) > 0


# ---- the difference's own rules ----------------------------------------------------------------------
def _pts(rows, steepness=0.5, density=1.0):
    p = Points()
    p.declare("Asset", "SoftObjectPath")
    for loc, half in rows:
        p.add(loc, bounds_min=(-half, -half, 0.0), bounds_max=(half, half, 2 * half), steepness=steepness,
              density=density, Asset="/Game/M.M")
    p.quat = [(0.0, 0.0, 0.0, 1.0)] * len(p)
    return p


def test_difference_uses_the_small_points_density_box():
    wfc = _pts([((0.0, 0.0, 0.0), 50.0)])
    # a small point 120 cm away with half-size 50: its bounds stop at 70 cm, its density box (x 1.5) at 45 cm
    near = _pts([((120.0, 0.0, 0.0), 50.0)])
    assert A.difference([wfc], [near])[0] == []
    far = _pts([((160.0, 0.0, 0.0), 50.0)])                                 # density box from 85 cm: misses
    assert len(A.difference([wfc], [far])[0][0]) == 1
    flat = _pts([((120.0, 0.0, 0.0), 50.0)], steepness=1.0)                  # steepness 1: the bounds themselves
    assert len(A.difference([wfc], [flat])[0][0]) == 1


def test_difference_rules_touching_dead_and_empty_points():
    wfc = _pts([((0.0, 0.0, 0.0), 50.0), ((1000.0, 0.0, 0.0), 50.0)])
    touching = _pts([((150.0, 0.0, 0.0), 50.0)], steepness=1.0)             # faces meet: no volume, nothing removed
    assert len(A.difference([wfc], [touching])[0][0]) == 2
    dead = _pts([((0.0, 0.0, 0.0), 50.0)], density=0.0)                     # a density-0 small point removes nothing
    assert len(A.difference([wfc], [dead])[0][0]) == 2
    hit = _pts([((1000.0, 0.0, 0.0), 10.0)])
    [kept], removed = A.difference([wfc], [hit])
    assert removed == 1 and kept.loc == [(0.0, 0.0, 0.0)]
    gone = _pts([((0.0, 0.0, 0.0), 10.0), ((1000.0, 0.0, 0.0), 10.0)])
    assert A.difference([wfc], [gone]) == ([], 2)                           # an emptied item is dropped
    zero = _pts([((0.0, 0.0, 0.0), 50.0)], density=0.0)                      # a source of density 0 goes with any diffs
    assert A.difference([zero], [_pts([((5000.0, 0.0, 0.0), 1.0)])]) == ([], 1)


def test_difference_overlap_ratio_counts_a_flat_axis_as_one():
    # the engine's ComputeOverlapRatio: an axis on which the denominator has no extent counts 1, not 0
    flat = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0), (-10.0, -10.0, 0.0), (10.0, 10.0, 0.0))
    box = ((5.0, 0.0, -5.0), (0.0, 0.0, 0.0, 1.0), (1.0, 1.0, 1.0), (-10.0, -10.0, 0.0), (10.0, 10.0, 10.0))
    assert G.volume_overlap(box, flat) > 0.0


def test_difference_broad_phase_matches_the_pairwise_test():
    import random
    rng = random.Random(7)
    def rand_pts(n, spread):
        p = Points()
        p.declare("Asset", "SoftObjectPath")
        quats = []
        for _ in range(n):
            a = rng.uniform(-math.pi, math.pi)
            quats.append((0.0, 0.0, math.sin(a / 2), math.cos(a / 2)))
            h = rng.uniform(5, 120)
            p.add((rng.uniform(0, spread), rng.uniform(0, spread), rng.uniform(0, 30)),
                  bounds_min=(-h, -h * 0.5, 0.0), bounds_max=(h, h * 0.7, h), steepness=0.5, Asset="/Game/M.M")
        p.quat = quats
        return p
    wfc, small = rand_pts(150, 3000), rand_pts(150, 3000)
    [kept], removed = A.difference([wfc], [small])
    brute = [i for i, r in enumerate(A.rows(wfc))
             if not any(G.volume_overlap(d[:5], r[:5], d[6]) > 0 for d in A.rows(small))]
    assert kept.loc == [wfc.loc[i] for i in brute] and removed == len(wfc) - len(brute) > 0


def test_kept_points_keep_their_engine_quaternions():
    wfc = _pts([((0.0, 0.0, 0.0), 50.0), ((1000.0, 0.0, 0.0), 50.0)])
    wfc.quat = [(1e-9, -2e-9, -0.9670166737402451, 0.2547130791858797), (0.0, 0.0, 0.0, 1.0)]
    [kept], _r = A.difference([wfc], [_pts([((1000.0, 0.0, 0.0), 10.0)])])
    assert kept.quat == [(1e-9, -2e-9, -0.9670166737402451, 0.2547130791858797)]


# ---- determinism (RANDOM is False) ----------------------------------------------------------------------
def test_seeded_runs_repeat_and_differ():
    assert S.RANDOM is False and A.RANDOM is False
    a = stage_api.execute(S, {"Rooftops": ROOFS}, {stage_api.SEED: 42}, OPS)[0]
    b = stage_api.execute(S, {"Rooftops": ROOFS}, {stage_api.SEED: 7}, OPS)[0]
    assert a == b                                                           # no draws: the seed changes nothing


def test_check_assemblies_on_a_record(tmp_path):
    wfc = _pts([((0.0, 0.0, 0.0), 50.0), ((1000.0, 0.0, 0.0), 50.0), ((2000.0, 0.0, 0.0), 50.0)])
    small = _pts([((1000.0, 0.0, 0.0), 10.0)])
    [kept], _r = A.difference([wfc], [small])

    def write(points):
        rec = {"params": {stage_api.SEED: 42},
               "inputs": {"WfcPoints": [[geo.to_json(wfc), []]], "SmallPoints": [[geo.to_json(small), []]]},
               "outputs": {"Points": [[geo.to_json(p), []] for p in points]}}
        path = tmp_path / "s12_assemblies.json"
        path.write_text(json.dumps(rec), encoding="utf-8")
        return str(path)
    assert C.check_assemblies(write([kept])) == []
    assert C.check_assemblies(write([wfc]))                                  # the overlapped point kept: caught
    assert C.check_assemblies(write([A.take(kept, [0])]))                   # a free point dropped: caught


def test_output_tags_do_not_depend_on_set_order():
    # V1 replays a record whose tags came in another frozenset order (the editor's): every output tag list is sorted
    many = [(r, frozenset(sorted(t, reverse=True)) | {"Building_ID:%d" % k, "PCG_GridSize_0", "Primitive:X"})
            for k, (r, t) in enumerate(ROOFS)]
    for pin, items in run(many).items():
        assert all(list(t) == sorted(t) for _v, t in items), pin


def test_check_catches_a_misplaced_area():
    out = run()
    bad = dict(out)
    bad["VentAreas"] = list(out["VentAreas"]) + [out["WfcAreas"][0]]
    assert any("both WfcAreas and VentAreas" in f for f in C.check({"Rooftops": ROOFS}, {}, bad, None))
    sky = dict(out)
    v, t = out["SkyscraperAreas"][0]
    sky["SkyscraperAreas"] = [(Polygon(v.outer, [], v.z + 12.0, zs=[z + 12.0 for z in v.zs]), t)]
    assert C.check({"Rooftops": ROOFS}, {}, sky, None)
