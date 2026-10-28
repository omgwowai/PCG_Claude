from pypcg.stages import w04_roads as S
from world_fixtures import run_stage, table, terrain

FLAT = lambda x, y: 1000.0
LOC_T = {"Id": "Int32", "Kind": "String", "Radius": "Double", "Slope": "Double"}


def _up(locs, exits, river=None):
    up = [table([{"loc": (x, y, 1000.0), "Id": i, "Kind": k, "Radius": r, "Slope": 0.0}
                 for i, (x, y, k, r) in enumerate(locs)], LOC_T, ["Location"]),
          table([{"loc": (x, y, 1000.0), "Id": i} for i, (x, y) in enumerate(exits)], {"Id": "Int32"}, ["RoadExit"])]
    if river:
        up.append(table([{"loc": (x, y, w), "Width": wd, "WaterZ": w, "BedZ": w - 150.0, "S": s}
                         for x, y, w, wd, s in river], {"Width": "Double", "WaterZ": "Double", "BedZ": "Double",
                                                         "S": "Double"}, ["River"]))
    return up


def test_network_is_connected_and_bridges_respect_grade():
    river = [(0.0, y, 900.0, 1000.0, y + 23000.0) for y in range(-23000, 23001, 1000)]
    up = _up([(-10000.0, 5000.0, "Town", 22000.0), (10000.0, -5000.0, "Village", 14000.0),
              (-12000.0, -15000.0, "Hamlet", 7000.0)], [(-20000.0, -1000.0), (20000.0, 1000.0)], river)
    out, _ = run_stage(S, {"Terrain": [(terrain(FLAT), frozenset())], "Upstream": up})
    s = out["Summary"][0][0].values
    # the trunk doubles back at the village and the town (exit W -> village E -> town W -> exit E): three legs
    assert s["connected"] and s["unreachable"] == 0 and s["main_roads"] == 3 and s["secondary_roads"] == 1
    assert s["max_grade_main"] <= 0.10 + 1e-9 and s["bridge_samples"] > 0
    roads = S.road_rows(out["Roads"])
    for rd in roads:
        for (x, y, z), br in zip(rd["pts"], rd["bridge"]):
            if br:
                assert z >= 900.0 + 250.0 - 1e-6
    assert len(out["Modules"][0][0]) > 0


def test_blocked_location():
    cliff = lambda x, y: 9000.0 if (x - 12000.0) ** 2 + (y - 12000.0) ** 2 < 4000.0 ** 2 else 1000.0
    up = _up([(-10000.0, 0.0, "Town", 22000.0), (12000.0, 12000.0, "Hamlet", 2000.0)],
             [(-20000.0, -1000.0), (20000.0, 1000.0)])
    out, _ = run_stage(S, {"Terrain": [(terrain(cliff), frozenset())], "Upstream": up})
    s = out["Summary"][0][0].values
    assert s["unreachable"] == 1 and not s["connected"]


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Roads"] == [] and out["Summary"][0][0].values["roads"] == 0


def test_lane_modules_sit_on_the_final_terrain():
    """Every lane module off a bridge rests on the written terrain (+8 cm), also where a branch's corridor meets the
    trunk's: a module under the ground is invisible in the editor. It may float a little where the ground bends."""
    from pypcg.world import VERTEX_CM
    from pypcg.world.grid import Lattice
    river = [(0.0, y, 900.0, 1000.0, y + 23000.0) for y in range(-23000, 23001, 1000)]
    up = _up([(-10000.0, 5000.0, "Town", 22000.0), (10000.0, -5000.0, "Village", 14000.0),
              (-12000.0, -15000.0, "Hamlet", 7000.0)], [(-20000.0, -1000.0), (20000.0, 1000.0)], river)
    hilly = lambda x, y: 1000.0 + 300.0 * ((x / 7000.0) ** 2 - (y / 9000.0) ** 2)
    out, _ = run_stage(S, {"Terrain": [(terrain(hilly), frozenset())], "Upstream": up})
    lat, _ks = Lattice.from_locs(out["Terrain"][0][0].loc, VERTEX_CM)
    low, high = 0.0, 0.0
    for (x, y, z) in out["Modules"][0][0].loc:
        if abs(x) < 1500.0:                       # bridge spans over the river keep their own height
            continue
        d = z - (lat.height(x, y) + 8.0)
        low, high = min(low, d), max(high, d)
    assert low > -1.0 and high < 50.0, (low, high)


def _network(fn=FLAT):
    river = [(0.0, y, 900.0, 1000.0, y + 23000.0) for y in range(-23000, 23001, 1000)]
    up = _up([(-10000.0, 5000.0, "Town", 22000.0), (10000.0, -5000.0, "Village", 14000.0),
              (-12000.0, -15000.0, "Hamlet", 7000.0)], [(-20000.0, -1000.0), (20000.0, 1000.0)], river)
    out, _ = run_stage(S, {"Terrain": [(terrain(fn), frozenset())], "Upstream": up})
    return out


def test_roads_are_smooth_curves_without_kinks():
    from pypcg.world import shape
    for rd in S.road_rows(_network()["Roads"]):
        st = shape.stats(rd["pts"])
        assert st["max_turn_deg"] < 10.0, (rd["id"], st)


def test_roads_never_run_on_top_of_each_other():
    """A route that meets the network joins it (a T or Y junction) instead of running along it: two roads share at
    most a junction's worth of length."""
    from pypcg.world import shape
    roads = S.road_rows(_network()["Roads"])
    for i, a in enumerate(roads):
        for b in roads[i + 1:]:
            tol = 0.5 * (a["width"] + b["width"])
            assert shape.overlap_length(a["pts"], b["pts"], tol) <= 3000.0, (a["id"], b["id"])


def test_branches_end_on_the_road_they_join():
    from pypcg.world import geom
    roads = S.road_rows(_network()["Roads"])
    for rd in roads:
        if rd["cls"] != "Secondary":
            continue
        end = rd["pts"][-1]
        best = None
        for other in roads:
            if other is rd:
                continue
            idx = geom.SegmentIndex(2000.0)
            for a, b in zip(other["pts"], other["pts"][1:]):
                idx.add(a[:2], b[:2], (a[2], b[2]))
            hit = idx.nearest(end[0], end[1], 2000.0)
            if hit is not None and (best is None or hit[0] < best[0]):
                za, zb = idx.payload(hit[1])
                best = (hit[0], za + (zb - za) * hit[2])
        assert best is not None and best[0] < 50.0 and abs(best[1] - end[2]) < 5.0, (rd["id"], best, end)


def test_a_road_over_a_flat_floor_wanders():
    """On flat ground A* draws a ruler-straight line; a low-frequency preference field (soil, fields, property lines)
    bends real country roads. 用户：道路的分布太规则."""
    from pypcg.world import shape
    up = _up([], [(0.0, -50000.0), (0.0, 50000.0)])
    out, _ = run_stage(S, {"Terrain": [(terrain(FLAT, 90), frozenset())], "Upstream": up})
    roads = S.road_rows(out["Roads"])
    assert len(roads) == 1
    st = shape.stats(roads[0]["pts"])
    assert st["sinuosity"] > 1.01 and st["straight_share"] < 0.5 and st["max_turn_deg"] < 10.0, st


def test_the_trunk_flows_through_the_places_it_links():
    """The trunk's legs (exit -> town -> village -> exit) are one road smoothed as a whole, so it curves through each
    place instead of meeting itself at a corner there."""
    from pypcg.world import shape
    up = _up([(0.0, 0.0, "Village", 14000.0)], [(-20000.0, -30000.0), (20000.0, 30000.0)])
    out, _ = run_stage(S, {"Terrain": [(terrain(FLAT, 60), frozenset())], "Upstream": up})
    mains = [rd for rd in S.road_rows(out["Roads"]) if rd["cls"] == "Main"]
    assert len(mains) == 1
    assert shape.stats(mains[0]["pts"])["max_turn_deg"] < 10.0
