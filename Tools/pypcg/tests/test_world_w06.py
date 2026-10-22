from pypcg.geo import Polygon, Spline
from pypcg.stages import w06_settlements as S
from pypcg.world import geom
from world_fixtures import run_stage, table, terrain

LOC_T = {"Id": "Int32", "Kind": "String", "Radius": "Double", "Slope": "Double"}
RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}


def _locs(rows):
    return table([{"loc": (x, y, 1000.0), "Id": i, "Kind": k, "Radius": r, "Slope": 0.0}
                  for i, (x, y, k, r) in enumerate(rows)], LOC_T, ["Location"])


def _road():
    return table([{"loc": (x, 0.0, 1000.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": False,
                   "S": x + 23000.0} for x in range(-23000, 23001, 500)], RT, ["Road", "Main"])


def _run(locs, seed=42):
    out, _ = run_stage(S, {"Terrain": [(terrain(lambda x, y: 1000.0 + 0.01 * y), frozenset())],
                           "Upstream": [_locs(locs), _road()]}, Seed=seed)
    return out


def test_village_follows_the_rules():
    out = _run([(0.0, 3000.0, "Village", 14000.0)])
    s = out["Summary"][0][0].values
    assert s["buildings"] >= 20 and s["village_min"] >= 20 and s["churches_min"] == 1
    assert s["overlaps"] == 0 and s["on_road"] == 0 and s["plazas"] == 1
    feet = [v for pin in ("FootprintsLow", "FootprintsMid", "FootprintsHigh", "FootprintsTower") for v, _t in out[pin]]
    assert len(feet) == s["buildings"] and all(isinstance(f, Spline) and f.closed and f.linear for f in feet)
    areas = [v for v, t in out["Areas"] if "Footprint" in t]
    assert all(isinstance(a, Polygon) for a in areas) and len(areas) == s["buildings"]
    assert len(out["Parts"][0][0]) > s["buildings"]


def test_two_close_settlements_never_overlap():
    out = _run([(-6000.0, 4000.0, "Town", 22000.0), (12000.0, -6000.0, "Village", 14000.0)])
    s = out["Summary"][0][0].values
    assert s["overlaps"] == 0 and s["on_road"] == 0 and s["buildings"] > 40


def test_same_seed_same_layout():
    a = _run([(0.0, 3000.0, "Village", 14000.0)], 7)
    b = _run([(0.0, 3000.0, "Village", 14000.0)], 7)
    assert [v.loc for v, _t in a["Buildings"]] == [v.loc for v, _t in b["Buildings"]]


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Summary"][0][0].values["buildings"] == 0


def test_landmarks_find_room_when_the_widest_gap_is_blocked():
    """A river along the widest gap must not leave the town without its church and town hall: the landmark
    tries the directions and distances around the gap."""
    import random
    from pypcg.world import settle
    road = {"pts": [(x, 0.0, 1000.0) for x in range(-23000, 23001, 500)], "hw": 400.0}
    river = [(0.0, y, 900.0, 1200.0) for y in range(-30000, 30001, 1000)]
    site = settle.Site([road], river, geom.RingIndex())
    plan = settle.layout({"id": 0, "kind": "Town", "x": 0.0, "y": 0.0, "radius": 22000.0}, random.Random(1), site)
    kinds = [b["kind"] for b in plan["buildings"]]
    assert kinds.count("Church") == 1 and kinds.count("TownHall") == 1


def test_every_footprint_fits_the_building_grammar():
    """The grammar fails a whole node ("Grammar does not fit for this spline") when one footprint edge is shorter than
    its modules (measured in the editor: the 5-7 m sheds and the 6 m bell tower). Every building type stays at or
    above rules.MIN_EDGE on both sides."""
    from pypcg.world import rules
    for b in rules.BUILDINGS:
        assert min(b["w"][0], b["d"][0]) >= rules.MIN_EDGE, b["kind"]
    for b in rules.LANDMARKS:
        assert min(b["w"], b["d"]) >= rules.MIN_EDGE, b["kind"]
    assert min(rules.TOWER["w"], rules.TOWER["d"]) >= rules.MIN_EDGE


def test_every_church_gets_its_bell_tower():
    out = _run([(0.0, 3000.0, "Village", 14000.0)])
    kinds = [k for v, _t in out["Buildings"] for k in v.attrs["Kind"]]
    assert kinds.count("Church") == 1 and kinds.count("BellTower") == 1


def test_overlapping_settlements_streets_avoid_earlier_buildings():
    """Final review: when two radii overlap, the later settlement's streets used to run through the earlier one's
    buildings while the Summary said on_road 0. Streets stop short of placed buildings, and on_road counts streets
    and the river too."""
    from pypcg.stages.w03_river import river_rows
    from pypcg.world import settle
    for seed in (1, 2, 3, 42):
        out = _run([(0.0, 0.0, "Town", 22000.0), (14000.0, 9000.0, "Village", 14000.0)], seed)
        s = out["Summary"][0][0].values
        assert s["on_road"] == 0 and s["overlaps"] == 0, (seed, s)
        streets = [[p[:2] for p in v.loc] for v, t in out["Streets"]]
        idx = geom.SegmentIndex(2000.0)
        for st in streets:
            idx.add_polyline(st, settle.STREET_HW)
        for v, t in out["Areas"]:
            if "Footprint" in t:
                for x, y in geom.probe_points(v.outer, 400.0):
                    hit = idx.nearest(x, y, 1000.0)
                    assert hit is None or hit[0] >= settle.STREET_HW, (seed, x, y)


def test_road_facing_buildings_are_not_buried_by_the_corridor_restore():
    """Final review: the road corridor restore ran after the pads and pulled road-facing pads back towards the road
    (59 cm on a 2.5 % cross slope). Every building's ground stays within 25 cm of its pad: what remains is the vertex
    grid itself (5.86 m; a corner is interpolated from vertices up to 8.3 m away, 2.5 % x 8.3 m = 21 cm)."""
    from pypcg.world import VERTEX_CM
    from pypcg.world.grid import Lattice
    out, _ = run_stage(S, {"Terrain": [(terrain(lambda x, y: 1000.0 + 0.025 * y), frozenset())],
                           "Upstream": [_locs([(0.0, 3000.0, "Town", 22000.0)]), _road()]})
    lat, _ks = Lattice.from_locs(out["Terrain"][0][0].loc, VERTEX_CM)
    worst = 0.0
    for v, t in out["Areas"]:
        if "Footprint" in t:
            for x, y in v.outer:
                h = lat.height(x, y)
                if h is not None:
                    worst = max(worst, abs(h - v.z))
    assert worst <= 25.0, worst
