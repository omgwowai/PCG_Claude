import math

from pypcg.geo import Polygon
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
    areas = [v for v, t in out["Areas"] if "Footprint" in t]
    assert all(isinstance(a, Polygon) for a in areas) and len(areas) == s["buildings"]
    assert len(out["Parts"][0][0]) > 0                           # street paths and plaza tiles
    assert "FootprintsLow" not in out                            # the template grammar is gone (2026-10-27)


def test_buildings_are_kit_modules_with_their_colours():
    """建筑模块: every building is built from the Megascans kit by the style database -- a Modules point set (one point
    per module: Mesh, Mat0) for the native mesh spawner."""
    from pypcg.world import kit as K
    out = _run([(0.0, 3000.0, "Village", 14000.0)])
    s = out["Summary"][0][0].values
    mods = out["Modules"][0][0]
    assert {"Mesh", "Mat0"} <= set(mods.attrs) and mods.types["Mat0"] == "SoftObjectPath"
    assert len(mods) > 40 * s["buildings"] and s["modules"] == len(mods)
    assert any(m.startswith(K.KIT) for m in mods.attrs["Mesh"])
    assert any(m.startswith(K.TOWN) for m in mods.attrs["Mat0"])           # tinted facades and roofs
    assert s["doors_front"] == s["buildings"]                               # a door on every street side
    assert s["bay_scale_min"] >= 0.8 and s["bay_scale_max"] <= 1.25


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


def test_every_lot_fits_a_style_of_its_archetype():
    """The facade grammar needs the style's minimum wall (BDF MinWallWidth): every lot size of every building type
    leaves at least one style of its archetype in every zone it is drawn in."""
    from pypcg.world import bdf, rules
    for b in rules.BUILDINGS:
        arch = rules.ARCHETYPES[b["kind"]]
        for zone in b["weights"]:
            w = rules.frontage(b, zone)
            ok = [st for st, _wt in rules.styles_for(arch, zone, "Town") if bdf.STYLES[st]["min_wall"] <= min(w[0], b["d"][0])]
            assert ok, (b["kind"], zone)
    for b in rules.LANDMARKS + [rules.TOWER]:
        assert min(b["w"], b["d"]) >= bdf.STYLES["LSA"]["min_wall"], b["kind"]


def test_a_town_has_rows_variety_and_a_taller_centre():
    """City Sample-style rules at town scale: at least five style codes, terraces in the core (buildings touching a
    neighbour), more storeys in the core than at the edge (the height noise per zone), shops with awnings."""
    out = _run([(0.0, 3000.0, "Town", 22000.0)])
    s = out["Summary"][0][0].values
    assert s["styles"] >= 5 and s["attached"] >= 10, s
    assert s["floors_core_mean"] > s["floors_outskirts_mean"] + 0.5, s
    assert s["shops"] >= 4 and s["awnings"] >= s["shops"], s
    rows = WP_rows(out["Buildings"])
    assert {"Style", "Floors", "Tint", "Roof", "Shop", "Height"} <= set(rows[0])
    assert all(r["Height"] > 400.0 for r in rows)


def WP_rows(items):
    from pypcg.world import points as WP
    return [r for v, _t in items for r in WP.rows_of(v)]


def test_a_village_stands_a_storey_lower_than_a_town():
    """The settlement's rank sets its skyline (City Sample: a height band per district): the houses of a village's
    (or hamlet's) core and residential zone are a storey lower than a town's; the outskirts' farms and the
    landmarks are the same everywhere."""
    import random
    from pypcg.world import rules

    def mean(kind, zone, settlement):
        rng = random.Random(5)
        fl = [rules.dress(kind, zone, settlement, x * 900.0, y * 900.0, 3, 1000.0, 1000.0, rng)["floors"]
              for x in range(20) for y in range(20)]
        return sum(fl) / len(fl)
    for small in ("Village", "Hamlet"):
        assert mean("House", "core", small) <= mean("House", "core", "Town") - 0.6
        assert mean("House", "residential", small) <= mean("House", "residential", "Town") - 0.3
        assert mean("House", "outskirts", small) == mean("House", "outskirts", "Town")
        assert mean("Church", "core", small) == mean("Church", "core", "Town")


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


def test_no_building_is_buried_or_left_hanging():
    """Final review (2026-10-22): the road corridor restore pulled road-facing pads back towards the road. 2026-10-27:
    the ground at a wall is interpolated from vertices up to a cell diagonal (8.3 m) away, so a pad cannot hold every
    corner at the floor; W6 now cuts the ground above each floor within that reach (台地切挖) -- no wall is buried
    and lower ground stays within the plinth. Within a vertex cell of a street the sidewalk (kept at the street's
    height, not cut) lifts the ground at the facade's foot: a level floor on a sloping street meets it higher at its
    uphill corner (slope x half the frontage), as in a real town -- measured there up to 40 cm on the valley data."""
    from pypcg.world import VERTEX_CM, settle
    from pypcg.world.grid import Lattice
    for slope in (0.025, 0.07):
        out, _ = run_stage(S, {"Terrain": [(terrain(lambda x, y: 1000.0 + slope * y), frozenset())],
                               "Upstream": [_locs([(0.0, 3000.0, "Town", 22000.0)]), _road()]})
        lat, _ks = Lattice.from_locs(out["Terrain"][0][0].loc, VERTEX_CM)
        walks = geom.SegmentIndex(2000.0)
        for v, t in out["Streets"]:
            walks.add_polyline([p[:2] for p in v.loc])
        buried = hanging = 0.0
        for v, t in out["Areas"]:
            if "Footprint" in t:
                for x, y in geom.probe_points(v.outer, 200.0):
                    h = lat.height(x, y)
                    if h is None:
                        continue
                    hanging = max(hanging, v.z - h)
                    if walks.nearest(x, y, settle.STREET_HW + settle.SIDEWALK + VERTEX_CM) is None:
                        buried = max(buried, h - v.z)
        assert buried <= 25.0 and hanging < S.PLINTH, (slope, buried, hanging)


def test_church_at_a_crossroads():
    """Final-review regression: with plots kept out of road corridors (16 m), a town whose two roads cross at its
    centre had no room for the church within 1.6 m of its first spot; the landmark tries further out."""
    import random
    from pypcg.world import settle
    roads = [{"pts": [(x, 0.0, 1000.0) for x in range(-23000, 23001, 500)], "hw": 400.0},
             {"pts": [(0.0, y, 1000.0) for y in range(-23000, 23001, 500)], "hw": 400.0}]
    site = settle.Site(roads, [], geom.RingIndex())
    plan = settle.layout({"id": 0, "kind": "Town", "x": 0.0, "y": 0.0, "radius": 22000.0}, random.Random(3), site)
    kinds = [b["kind"] for b in plan["buildings"]]
    assert kinds.count("Church") == 1 and kinds.count("TownHall") == 1


def _town_plan(seed=5, kind="Town", radius=22000.0):
    import random
    from pypcg.world import settle
    road = {"pts": [(x, 0.08 * x + 1500.0 * math.sin(x / 9000.0), 1000.0) for x in range(-30000, 30001, 500)],
            "hw": 400.0}
    site = settle.Site([road], [], geom.RingIndex())
    return settle.layout({"id": 0, "kind": kind, "x": 0.0, "y": 0.0, "radius": radius}, random.Random(seed), site), site


def test_streets_grow_organically_not_as_a_wheel():
    """用户：道路的分布太均匀、太规则. No ring street and no evenly spaced straight spokes: streets wander, branch off
    each other and end on another street or road (T junctions)."""
    from pypcg.world import shape
    for seed in (1, 5, 9):
        plan, site = _town_plan(seed)
        streets = plan["streets"]
        assert len(streets) >= 6, seed
        total = sum(geom.length(s) for s in streets)
        straight = sum(sum(shape.straight_runs(s)) for s in streets)
        assert straight / total < 0.5, (seed, straight / total)
        for s in streets:
            assert not (geom.length(s) > 6000.0 and geom.dist2d(s[0], s[-1]) < 3000.0), seed      # no closed ring
        tees = 0
        for i, s in enumerate(streets):
            others = geom.SegmentIndex(2000.0)
            for j, o in enumerate(streets):
                if j != i:
                    others.add_polyline(o)
            for rd in site.roads:
                others.add_polyline([p[:2] for p in rd["pts"]])
            tees += any(others.nearest(e[0], e[1], 100.0) is not None for e in (s[0], s[-1]))
        assert tees >= 4, (seed, tees)


def test_a_town_still_gets_its_buildings_on_organic_streets():
    out = _run([(0.0, 3000.0, "Town", 22000.0)])
    s = out["Summary"][0][0].values
    assert s["town_min"] >= 60 and s["overlaps"] == 0 and s["on_road"] == 0 and s["churches_min"] == 1


def test_leftover_lots_get_outbuildings_and_kitchen_gardens():
    """City Sample's leftover lots (stage 13): behind the street houses, outbuildings facing their house and kitchen
    gardens (Field areas: W7 hedges them, W9 digs them) -- block interiors are not empty meadows."""
    out = _run([(0.0, 3000.0, "Town", 22000.0)])
    s = out["Summary"][0][0].values
    rows = WP_rows(out["Buildings"])
    assert sum(r["Kind"] == "Outbuilding" for r in rows) >= 5 and s["gardens"] >= 5, s
    assert s["overlaps"] == 0 and s["on_road"] == 0 and s["doors_front"] == s["buildings"]
    gardens = [v for v, t in out["Areas"] if "Garden" in t]
    assert len(gardens) == s["gardens"] and all("Field" in t for v, t in out["Areas"] if "Garden" in t)


def test_doors_move_towards_street_level(monkeypatch):
    """建筑入口贴近街道高度: a street house's floor moves up to STREET_PULL from the ground under it towards its
    street's height (City Sample fits each footprint to the terrain); on a 6 % slope that halves the step between the
    street and the door."""
    def run(pull):
        monkeypatch.setattr(S, "STREET_PULL", pull)
        out, _ = run_stage(S, {"Terrain": [(terrain(lambda x, y: 1000.0 + 0.06 * x), frozenset())],
                               "Upstream": [_locs([(0.0, 3000.0, "Village", 14000.0)]), _road()]})
        return out["Summary"][0][0].values
    pull = S.STREET_PULL
    before, after = run(0.0), run(pull)
    assert after["street_fronts"] >= 10, after
    assert after["street_level_err_mean"] < 0.6 * before["street_level_err_mean"], (before, after)
    assert after["street_level_err_max"] <= before["street_level_err_max"] - 20.0, (before, after)


def test_raised_doors_get_steps(monkeypatch):
    """Hochparterre: where a floor stands over the ground in front of its door (here: floors left on their own ground
    on a 6 % slope), W6 measures the door's rise and the building gets entrance steps; the Summary counts the flights
    and reports the largest rise."""
    from pypcg.world import building
    monkeypatch.setattr(S, "STREET_PULL", 0.0)
    out, _ = run_stage(S, {"Terrain": [(terrain(lambda x, y: 1000.0 + 0.06 * x), frozenset())],
                           "Upstream": [_locs([(0.0, 3000.0, "Village", 14000.0)]), _road()]})
    s = out["Summary"][0][0].values
    assert s["door_rise_max"] >= building.STEP_MIN and 0 < s["steps"] <= s["buildings"], s


def test_an_outbuilding_left_hanging_is_dropped():
    """A neighbour's 台地切挖 can take the ground from under a backyard outbuilding (one stood 3.3 m over its ground on
    the real valley, the door 4 m up): it is left out and its leftover lot stays a yard. Houses are never dropped."""
    def bld(kind, z):
        return {"kind": kind, "x": 0.0, "y": 0.0, "z": z, "ring": geom.rect(0.0, 0.0, 500.0, 500.0, 0.0)}
    plans = [{"buildings": [bld("Outbuilding", 1300.0), bld("Outbuilding", 1100.0), bld("House", 1400.0)]}]
    assert S.drop_hanging(plans, lambda x, y: 1000.0) == 1
    assert [b["kind"] for b in plans[0]["buildings"]] == ["Outbuilding", "House"]
    assert S.drop_hanging(plans, lambda x, y: None) == 0


def test_door_rise_is_measured_in_front_of_the_door():
    """The rise a door's steps climb: its floor over the ground DOOR_PROBE out from its front's middle (the front
    grammar centres the door), read from the ground it is given (W6 gives the engine's triangulated surface)."""
    b = {"x": 0.0, "y": 0.0, "z": 1000.0, "w": 1000.0, "d": 800.0, "yaw": 0.0, "front": 2}
    seen = []

    def ground(x, y):
        seen.append((round(x, 6), round(y, 6)))
        return 940.0
    assert S.door_rise(b, ground) == 60.0
    assert seen == [(0.0, -400.0 - S.DOOR_PROBE)]                    # edge 2 is the -d side, its outside is -y
    assert S.door_rise(b, lambda x, y: None) == 0.0


def test_streets_get_pavers_and_sidewalks_by_zone():
    """街道断面 (City Sample's sidewalk kit): stone pavers on the carriageway, raised sidewalks from its edge to the
    facades in the core and residential zones (none at the outskirts), a paved plaza; the Streets table carries the
    paved width so the vegetation keeps off it."""
    from pypcg.world import kit as K, settle
    out = _run([(0.0, 3000.0, "Village", 14000.0)])
    meshes = out["Parts"][0][0].attrs["Mesh"]
    assert any(m == K.PAVER for m in meshes) and any(m == K.SIDEWALK for m in meshes)
    assert any(m == K.PLAZA_STONE for m in meshes)
    paved = [r["Paved"] for v, _t in out["Streets"] for r in WP_rows([(v, ())])]
    assert set(paved) <= {2.0 * settle.STREET_HW, 2.0 * (settle.STREET_HW + settle.SIDEWALK)}
    assert 2.0 * (settle.STREET_HW + settle.SIDEWALK) in paved
    assert settle.STREET_HW + settle.SIDEWALK < settle.STREET_HW + settle.SETBACK["street"]   # short of the facades


def test_vegetation_keeps_off_the_sidewalks():
    from pypcg.world import scatter, points as WP2
    st = WP2.table_points([{"loc": (float(x), 0.0, 0.0), "Width": 400.0, "Paved": 860.0, "S": float(x)}
                           for x in range(0, 5001, 500)], {"Width": "Double", "Paved": "Double", "S": "Double"})
    ex = scatter.upstream_exclusions([(st, frozenset(["Street"]))])
    assert ex.line_gap(2500.0, 400.0) < 0.0 and ex.line_gap(2500.0, 500.0) > 0.0


def test_the_setts_are_seated_on_the_ground():
    """The pads' blends (6 m) used to lift the ground over the street's setts and the 5.86 m vertex grid bulges
    between vertices: every slab is now seated on the final ground -- the engine's own triangulated surface
    (Lattice.tri_height; the bilinear height is up to ~16 cm off it on a twisted cell, and the ground showed through
    the setts across a steep street) -- following the street's slope, lifted so no ground under it comes through its
    top, and never floating more than its lift cap plus its block's depth (the 4.2 cm skin scaled S.SETTS_Z)."""
    from pypcg.world import VERTEX_CM, kit as K
    from pypcg.world.grid import Lattice
    road = table([{"loc": (x, 0.0, 1000.0 + 0.03 * x), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": False,
                   "S": x + 23000.0} for x in range(-23000, 23001, 500)], RT, ["Road", "Main"])   # graded on the slope
    out, _ = run_stage(S, {"Terrain": [(terrain(lambda x, y: 1000.0 + 0.05 * y + 0.03 * x), frozenset())],
                           "Upstream": [_locs([(0.0, 3000.0, "Town", 22000.0)]), road]})
    lat, _ks = Lattice.from_locs(out["Terrain"][0][0].loc, VERTEX_CM)
    parts = out["Parts"][0][0]
    over = under = 0.0
    n = 0
    for i, m in enumerate(parts.attrs["Mesh"]):
        if m != K.PAVER:
            continue
        (px, py, pz), (pitch, yaw, roll), (sx, sy, sz) = parts.loc[i], parts.rot[i], parts.scale[i]
        ux, uy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        nx, ny = -uy, ux
        L, W = sx * K.SLAB / 1.03, sy * K.SLAB
        for t in [q / 12.0 for q in range(13)]:
            for w in [q / 12.0 for q in range(13)]:
                x, y = px + ux * L * t + nx * W * w, py + uy * L * t + ny * W * w
                h = lat.tri_height(x, y)
                if h is None:
                    continue
                top = pz + 20.0 * sz + L * t * math.tan(math.radians(pitch)) - W * w * math.tan(math.radians(roll))
                n += 1
                over, under = max(over, h - top), max(under, top - h)
    # (a slab lifts at most S.LIFT_MAX: on a junction's embankment the ground may show through a few setts)
    assert n > 3000 and under <= S.LIFT_MAX + 4.2 * S.SETTS_Z, (n, over, under)
    assert over <= 0.5, over
