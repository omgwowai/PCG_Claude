"""Stage 17, CityEdge (Task 15): the sea filter, the convex hull, the dock pick and the first stage
assignment through `pypcg.geo.assets`.

The fixture `Tools/pypcg/data/s17_fixture.json` is the official chain tapped node by node on the
demo level's stage 17 volume (seed 42, 2026-10-19): the 57 hull vertices with their yaws and seeds, the
30 docks the official `RandomChoice_0` kept, the `Warehouse_C_PCG` kit as `pypcg.ue.assets.load` reads
it, and the official `Assign_Assets` output for that kit (1 480 copies) and for the docks themselves."""
import json
import math
import os
import random

import pytest

from pypcg import geo, graphs, stage_api
from pypcg.checks import s17 as C
from pypcg.geo import Points
from pypcg.geo import assets as A
from pypcg.profiles import official
from pypcg.stages import s17_city_edge as S

REPO = stage_api.REPO
FIXTURE = os.path.join(REPO, "Tools", "pypcg", "data", "s17_fixture.json")


def fx():
    return json.load(open(FIXTURE, encoding="utf-8"))


def official_ir():
    return json.load(open(os.path.join(REPO, "Tools", "pypcg", "official_ir", "PCG_5_1_CityEdge.json"),
                          encoding="utf-8"))


def node(ir, name):
    return [x for x in ir["nodes"] if x["name"] == name][0]


def params(**kw):
    p = stage_api.defaults(S)
    p.update(kw)
    return p


def kit(path, n=3, mesh="/G/SM_%s.SM_%s"):
    """A small synthetic kit: n points along local X, each with its own mesh."""
    p = Points()
    p.declare("Mesh", "SoftObjectPath")
    tag = path.rsplit("/", 1)[-1].split(".")[0]
    for j in range(n):
        p.add((100.0 * j, 10.0, 0.0), seed=j + 1, bounds_min=(-50.0, -50.0, 0.0), bounds_max=(50.0, 50.0, 20.0),
              Mesh=mesh % (tag + str(j), tag + str(j)))
    b = A.bounds_of(p)
    return {"path": path, "points": p, "bounds": b, "size": A.size_of(b), "note": ""}


class KitOps:
    """`ctx.ops.assets` offline: synthetic kits, or the fixture's real Warehouse_C kit for every path."""

    def __init__(self, table=None):
        self.table = table
        self.asked = []

    def assets(self, paths):
        self.asked.append(list(paths))
        return [self.table[p] if self.table else kit(p) for p in paths]


def warehouse_c():
    d = fx()["warehouse_c"]
    p = Points()
    p.declare("Mesh", "SoftObjectPath")
    for i in range(len(d["loc"])):
        p.add(d["loc"][i], rot=tuple(d["rot"][i]), scale=tuple(d["scale"][i]), seed=d["seed"][i],
              bounds_min=tuple(d["bounds_min"][i]), bounds_max=tuple(d["bounds_max"][i]),
              Mesh=d["meshes"][d["mesh"][i]])
    b = A.bounds_of(p)
    return {"path": d["path"], "points": p, "bounds": b, "size": A.size_of(b), "note": ""}


def terrain(ring, inside=400, below=200, seed=3, sea=S.PARAMS["SeaLevel"].default):
    """The ring's vertices, `inside` random points strictly inside it (above the sea) and `below` sea
    points anywhere -- including OUTSIDE the ring, which the sea filter must drop -- shuffled."""
    rng = random.Random(seed)
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    pts = [tuple(p) for p in ring]
    for _ in range(inside):
        a = ring[rng.randrange(len(ring))]
        b = ring[rng.randrange(len(ring))]
        t, u = rng.uniform(0.05, 0.9), rng.random()
        x = cx + t * ((a[0] + u * (b[0] - a[0])) - cx)
        y = cy + t * ((a[1] + u * (b[1] - a[1])) - cy)
        pts.append((x, y, rng.uniform(sea + 1.0, 2000.0)))
    for _ in range(below):
        pts.append((rng.uniform(min(xs) * 1.5, max(xs) * 1.5), rng.uniform(min(ys) * 1.5, max(ys) * 1.5),
                    rng.uniform(-3000.0, sea)))
    rng.shuffle(pts)
    p = Points()
    for q in pts:
        p.add(q)
    return p


def run(inputs, ops=None, **kw):
    return stage_api.execute(S, inputs, params(**kw), ops if ops is not None else KitOps())


def official_inputs():
    return {"MeshTerrain": [(terrain(fx()["hull"]), frozenset())]}


# ---- contract -------------------------------------------------------------------------------------
def test_contract_parameters_are_the_official_values():
    off = official_ir()
    flt = node(off, "AttributeFilter_0")["settings"]
    assert flt["TargetAttribute"] == "PCGBegin($Position.Z)PCGEnd" and flt["bUseConstantThreshold"]
    assert flt["AttributeTypes"]["Type"] == "Double"
    assert S.PARAMS["SeaLevel"].default == flt["AttributeTypes"]["DoubleValue"] == -72.639648
    choice = node(off, "RandomChoice_0")["settings"]
    assert not choice["bFixedMode"]
    assert S.PARAMS["DockRatio"].default == choice["Ratio"] == 0.5152000188827515
    assign = node(off, "Subgraph_2")
    assert assign["subgraph"].endswith("Assign_Assets.Assign_Assets")
    assert tuple(assign["overrides"]["Assets"]) == S.ASSETS
    po = assign["overrides"]["PositionOffset"]
    assert (po["X"], po["Y"], po["Z"]) == S.POSITION_OFFSET
    ro = assign["overrides"]["RotationOffset"]
    assert (ro["Pitch"], ro["Yaw"], ro["Roll"]) == S.ROTATION_OFFSET
    spline = node(off, "CreateSpline_0")["settings"]
    assert spline["bClosedLoop"] and spline["bLinear"]
    for name, sel in (("AttributeMathsOp_3", "$Rotation.Roll"), ("AttributeMathsOp_4", "$Rotation.Pitch")):
        s = node(off, name)["settings"]
        assert s["Operation"] == "Set" and s["InputSource1"] == "PCGBegin(%s)PCGEnd" % sel
    assert S.INPUTS == {"MeshTerrain": "points"} and S.OUTPUTS == ("Docks",) and S.RANDOM
    assert [p["name"] for p in off["params"]] == ["Partitioned", "PartitionGridSize"]   # both dropped


def test_contract_MeshTerrain_is_the_kept_terrain_read():
    ir = graphs.graph(17).to_ir(official)
    py = [x for x in ir["nodes"] if x["class"] == "PCGPythonDataProcessorSettings"][0]
    edges = {(x["name"], p["label"]): [tuple(e) for e in p["edges"]] for x in ir["nodes"] for p in x["inputs"]}
    get = [x for x in ir["nodes"] if x.get("subgraph", "").endswith("Get_MeshTerrain.Get_MeshTerrain")]
    ext = [x for x in ir["nodes"] if x.get("subgraph", "").endswith("Extract_MeshTerrainPoints.Extract_MeshTerrainPoints")]
    assert len(get) == 1 and len(ext) == 1
    assert get[0]["overrides"] == node(official_ir(), "Subgraph_9")["overrides"]
    assert get[0]["overrides"]["MeshPartitionQueryType"] == "Final"
    assert edges[(ext[0]["name"], "PrimaryInput")] == [(get[0]["name"], "Out")]
    assert edges[(py["name"], "MeshTerrain")] == [(ext[0]["name"], "Out")]


def test_contract_Docks_feeds_the_kept_spawner_and_the_output():
    ir = graphs.graph(17).to_ir(official)
    py = [x for x in ir["nodes"] if x["class"] == "PCGPythonDataProcessorSettings"][0]
    edges = {(x["name"], p["label"]): [tuple(e) for e in p["edges"]] for x in ir["nodes"] for p in x["inputs"]}
    spawn = [x for x in ir["nodes"] if x.get("subgraph", "").endswith("Spawn_Assets.Spawn_Assets")]
    assert len(spawn) == 1 and spawn[0]["title"] == "Spawn Pier & Warehouse Assemblies"
    assert spawn[0]["overrides"] == node(official_ir(), "Subgraph_0")["overrides"]
    assert edges[(spawn[0]["name"], "PrimaryInput")] == [(py["name"], "Docks")]
    assert edges[("DefaultOutputNode", "Out")] == [(py["name"], "Docks")]
    assert len(edges[(py["name"], stage_api.PARAMS_PIN)]) == 1 + len(S.PARAMS)
    assert [p["name"] for p in ir["params"]] == ["Seed", "SeaLevel", "DockRatio"]


# ---- empty inputs (Review Focus 1) ----------------------------------------------------------------
def test_empty_inputs_give_empty_docks():
    ops = KitOps()
    assert run({"MeshTerrain": []}, ops)[0] == {"Docks": []}
    assert run({"MeshTerrain": [(Points(), frozenset())]}, ops)[0] == {"Docks": []}
    assert ops.asked == [], "no docks, so no kit is loaded"


def test_empty_inputs_no_terrain_above_sea_level_gives_no_docks():
    t = terrain(fx()["hull"])
    out, _ = run({"MeshTerrain": [(t, frozenset())]}, SeaLevel=1e9)
    assert out == {"Docks": []}
    assert C.check({"MeshTerrain": [(t, frozenset())]}, params(SeaLevel=1e9), out, None) == []


def test_empty_inputs_without_an_asset_loader_publish_nothing_and_say_so():
    out, ctx = stage_api.execute(S, official_inputs(), params(), None)
    assert out == {"Docks": []}
    assert any("asset loader" in n for n in ctx.notes)


# ---- the convex hull (geo.convex_hull) ------------------------------------------------------------
def test_convex_hull_reproduces_the_official_57_vertices_in_the_official_order():
    """The official `FindConvexHull2D_0` on 100 666 above-sea points gave these 57 vertices in this
    order (counter-clockwise from the lowest X). Burying them among random interior points and sea
    points must give back exactly the same list."""
    hull = [tuple(p) for p in fx()["hull"]]
    t = terrain(hull, inside=3000, below=1000)
    kept = S.above(t, S.PARAMS["SeaLevel"].default)
    assert S.hull_ring(kept) == hull


def test_convex_hull_is_convex_and_contains_every_kept_point():
    t = terrain(fx()["hull"], seed=11)
    kept = S.above(t, S.PARAMS["SeaLevel"].default)
    ring = S.hull_ring(kept)
    assert C._convex_ccw(ring)
    assert all(C._within(p, [(q[0], q[1]) for q in ring]) for p in kept)


def test_convex_hull_drops_collinear_points_and_keeps_tiny_inputs_as_they_are():
    sq = [(0, 0), (2, 0), (2, 2), (0, 2), (1, 0), (2, 1), (1, 1)]
    assert [sq[i] for i in geo.convex_hull(sq)] == [(0, 0), (2, 0), (2, 2), (0, 2)]
    assert geo.convex_hull([(5, 5), (1, 1), (3, 0)]) == [0, 1, 2]           # <= 3: input order
    assert geo.convex_hull([]) == []


def test_sea_filter_is_strictly_greater_than_the_threshold():
    p = Points()
    for z in (-100.0, -72.639648, -72.6, 0.0):
        p.add((0.0, 0.0, z))
    assert [q[2] for q in S.above(p, -72.639648)] == [-72.6, 0.0]


# ---- the docks --------------------------------------------------------------------------------------
def test_control_points_face_the_next_hull_vertex_with_the_engines_seed():
    d = fx()
    cp = S.control_points([tuple(p) for p in d["hull"]])
    assert [tuple(l) for l in cp.loc] == [tuple(p) for p in d["hull"]]
    # modulo 360: an edge running due -X is +180 on one side and -180 on the other, the same facing
    assert max(abs(((a[1] - b + 180.0) % 360.0) - 180.0) for a, b in zip(cp.rot, d["hull_yaw"])) < 1e-9
    assert all(r[0] == 0.0 and r[2] == 0.0 for r in cp.rot)
    assert list(cp.seed) == d["hull_seed"]


@pytest.mark.parametrize("seed", [7, 13, 101, 977, 42])
def test_dock_count_is_the_ratio_of_the_hull_rounded_up(seed):
    """`RandomChoice` keeps `CeilToInt(n x Ratio)` (PCGRandomChoice.cpp): 30 of 57 at 0.5152, which the
    official run kept; the brief's `round` would keep 29."""
    out, _ = run(official_inputs(), Seed=seed)
    docks = out["Docks"][-1][0]
    assert len(docks) == math.ceil(57 * S.PARAMS["DockRatio"].default) == 30 == len(fx()["chosen"])


@pytest.mark.parametrize("seed", [7, 13, 101, 977, 42])
def test_every_dock_has_an_asset_and_sits_on_a_hull_vertex(seed):
    inp = official_inputs()
    out, _ = run(inp, Seed=seed)
    docks = out["Docks"][-1][0]
    assert all(a in S.ASSETS for a in docks.attrs["Asset"])
    hull = [tuple(p) for p in fx()["hull"]]
    for v in C.unmoved(docks):
        assert min(math.dist(v, h) for h in hull) < 1e-6
    assert C.check(inp, params(Seed=seed), out, None) == []
    assert C.check(None, params(Seed=seed), out, None) == []


def test_docks_are_moved_inland_along_their_own_facing():
    """The kept offset (0, -492.541261, 0) moves each dock along ITS OWN local -Y, i.e. to the right of
    the hull edge it faces along -- inland for a counter-clockwise hull. The official docks moved
    492.541260 cm (a float offset), each 90 degrees clockwise of its facing."""
    out, _ = run(official_inputs())
    docks = out["Docks"][-1][0]
    for v, m, r in zip(C.unmoved(docks), docks.loc, docks.rot):
        d = (m[0] - v[0], m[1] - v[1])
        assert math.hypot(*d) == pytest.approx(492.541260, abs=1e-5)
        heading = math.degrees(math.atan2(d[1], d[0]))
        assert ((heading - (r[1] - 90.0) + 180.0) % 360.0) - 180.0 == pytest.approx(0.0, abs=1e-6)


def test_the_output_is_the_primitives_items_in_order():
    """One item per kit (first-picked order), then the docks carrying their kit path; every copy item is
    a whole number of copies of its kit, source-major."""
    ops = KitOps()
    out, _ = run(official_inputs(), ops)
    items = [v for v, _ in out["Docks"]]
    docks = items[-1]
    picks = docks.attrs["Asset"]
    order = []
    for p in picks:
        if p not in order:
            order.append(p)
    assert len(items) == len(order) + 1
    for item, path in zip(items, order):
        k = picks.count(path)
        assert len(item) == 3 * k
        tag = path.rsplit("/", 1)[-1].split(".")[0]
        assert item.attrs["Asset"] == [m for j in range(3) for m in ["/G/SM_%s%d.SM_%s%d" % (tag, j, tag, j)] * k]
    assert all(t == ["Docks"] for _, t in out["Docks"])
    assert ops.asked == [list(S.ASSETS)]


def test_seeded_runs_repeat_and_differ():
    a = [geo.to_json(v) for v, _ in run(official_inputs(), Seed=7)[0]["Docks"]]
    b = [geo.to_json(v) for v, _ in run(official_inputs(), Seed=7)[0]["Docks"]]
    c = [geo.to_json(v) for v, _ in run(official_inputs(), Seed=8)[0]["Docks"]]
    assert a == b and a != c


def test_check_catches_a_dock_off_the_hull_and_a_tilted_dock():
    inp = official_inputs()
    out, _ = run(inp)
    docks = out["Docks"][-1][0]
    x, y, z = docks.loc[3]
    docks.loc[3] = (x - 20000.0, y + 20000.0, z)
    f = C.check(inp, params(), out, None)
    assert any("convex" in m for m in f) and any("hull vertex" in m for m in f)
    out, _ = run(inp)
    out["Docks"][-1][0].rot[0] = (5.0, 10.0, 0.0)
    assert any("pitch" in m for m in C.check(None, params(), out, None))


# ---- the assignment against the official primitive -------------------------------------------------
def official_targets():
    t = fx()["targets"]
    p = Points()
    for i in range(len(t["loc"])):
        p.add(t["loc"][i], rot=tuple(t["rot"][i]), scale=tuple(t["scale"][i]), seed=t["seed"][i], steepness=1.0)
    p.quat = [tuple(q) for q in t["quat"]]
    return p, t["asset"]


def test_assign_reproduces_the_official_primitive_on_stage_17():
    """The official `Subgraph_2 Assign_Assets` call, given the official 30 docks and its own picks: the
    Warehouse_C kit's 1 480 copies (first-picked, so item 0) and the 30 moved docks. Measured offline
    on the full tap (all five kits, 9 843 copies): counts, `Asset`, seeds and boxes exact, positions
    to 7e-12 cm. Here: the Warehouse_C item and the docks."""
    d = fx()
    targets, picks = official_targets()
    wc = warehouse_c()
    table = [wc if p == wc["path"] else kit(p) for p in S.ASSETS]
    items = A.expand_items(targets, table, [S.ASSETS.index(p) for p in picks], dict(S.ASSIGN_PARAMS))
    assert [len(i) for i in items][0] == d["item_points"][0] == 1480
    copies, want = items[0], d["warehouse_c_copies"]
    assert copies.attrs["Asset"] == [d["warehouse_c"]["meshes"][m] for m in want["mesh"]]
    assert list(copies.seed) == want["seed"]
    worst = max(max(abs(a - b) for a, b in zip(x, y)) for x, y in zip(copies.loc, want["loc"]))
    assert worst < 1e-9
    qd = max(min(max(abs(a - b) for a, b in zip(x, y)), max(abs(a + b) for a, b in zip(x, y)))
             for x, y in zip(copies.quat, want["quat"]))
    assert qd < 1e-6
    moved = items[-1]
    assert [tuple(l) for l in moved.loc] == [tuple(l) for l in d["moved"]["loc"]]     # bit for bit
    assert moved.attrs["Asset"] == picks


def test_the_official_instance_count_is_both_halves_of_the_primitive_output():
    """19 626 official instances = 2 x (9 843 copies - 30 copies whose `Mesh` is the null path): the
    kept spawner spawns every meshed copy, and spawns each dock's kit again from the docks item. The
    port publishes both halves, so the slim graph spawns the same way."""
    d = fx()
    copies = sum(d["item_points"][:-1])
    assert copies == 9843 and d["official_instances"] == 2 * (copies - 30)
