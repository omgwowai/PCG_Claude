"""PyInterior multi-storey (spec 2026-10-29): floors from the house's splines, clipping, terraces, the building loop."""
import random
import time

import pytest

from pypcg.interior import demo
from pypcg.interior import layout as L
from pypcg.interior import storeys as S


def box(w, h, x0=0.0, y0=0.0):
    """World points (z 0) of a local box for an actor at the origin, yaw 0 (local y = 0 is the front)."""
    from test_interior_footprint import world_of
    return world_of([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)], (0, 0, 0), 0.0)


def with_z(pts, z):
    return [(x, y, z) for x, y, _ in pts]


def test_levels_group_splines_by_height():
    lv = S.levels([box(1000, 800), with_z(box(1000, 800), 300.0)], 0.0, 270.0, 0)
    assert len(lv.outlines) == 2 and all(o is not None for o in lv.outlines) and not lv.notes


def test_floors_param_copies_the_floor_below():
    lv = S.levels([box(900, 800)], 0.0, 270.0, 2)
    assert len(lv.outlines) == 2 and lv.outlines[1] is None


def test_lowest_spline_becomes_the_ground_floor():
    lv = S.levels([with_z(box(900, 800), 300.0), with_z(box(900, 800), 600.0)], 0.0, 270.0, 0)
    assert len(lv.outlines) == 2 and lv.notes


def test_two_splines_on_one_level_keep_the_largest():
    lv = S.levels([box(900, 800), box(600, 500)], 0.0, 270.0, 0)
    assert len(lv.outlines) == 1 and lv.notes and len(lv.outlines[0]) == 4
    assert max(p[0] for p in lv.outlines[0]) - min(p[0] for p in lv.outlines[0]) > 700.0


def test_at_most_three_floors():
    lv = S.levels([box(900, 800)], 0.0, 270.0, 5)
    assert len(lv.outlines) == 3 and lv.notes


def test_upper_floor_is_clipped_and_raised():
    lv = S.levels([box(1000, 800), with_z(box(1400, 600), 300.0)], 0.0, 270.0, 0)
    fps, dropped = S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)
    assert len(fps) == 2 and not dropped
    assert fps[1].cells <= fps[0].cells and fps[1].cells != fps[0].cells
    assert fps[1].to_world(0, 0, 0)[2] == 300.0 and fps[0].to_world(0, 0, 0)[2] == 0.0


def test_too_small_upper_floor_is_dropped():
    lv = S.levels([box(1000, 800), with_z(box(400, 400), 300.0)], 0.0, 270.0, 0)
    fps, dropped = S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)
    assert len(fps) == 1 and dropped


def test_terraces_are_the_uncovered_roof():
    lv = S.levels([box(1000, 900), with_z(box(1000, 600, y0=300), 300.0)], 0.0, 270.0, 0)
    fps, _ = S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)
    rects = S.terrace_rects(fps)[1]
    assert sum(r.area for r in rects) == 1000 * 300 and all(r.y1 <= 300 for r in rects)


# ---------------------------------------------------------------- the building loop

PARAMS = {"WallHeight": 270.0, "ExteriorWall": 25.0, "InteriorWall": 12.0, "Grid": 50.0, "Floors": 0,
          "StairType": "Auto", "Mirror": False, "Furnish": True}
EXPECTED_FLOORS = {"House_11_TwoStorey": 2, "House_12_FrontTerrace": 2, "House_13_LTerrace": 2, "House_14_Townhouse": 3,
                   "House_15_Stepped": 3, "House_16_OneSpline": 2, "House_17_LongStair": 2}


def splines_of(outlines, loc=(0.0, 0.0, 0.0), yaw=0.0, H=300.0):
    """World splines for local outlines per floor (None: no spline on that floor), floor k raised k x H."""
    from test_interior_footprint import world_of
    return [[(x, y, z + k * H) for x, y, z in world_of(o, loc, yaw)] for k, o in enumerate(outlines) if o is not None]


def plan_demo(house, seed=None, loc=(0.0, 0.0, 0.0), yaw=0.0, **over):
    _name, outlines, floors, stair_type, _style, hseed = house
    params = dict(PARAMS, Floors=floors, StairType=stair_type, **over)
    return S.plan_building(splines_of(outlines, loc, yaw), loc, yaw, params, random.Random(hseed if seed is None else seed))


@pytest.mark.parametrize("house", demo.STOREYS, ids=[h[0] for h in demo.STOREYS])
def test_demo_storey_houses_plan_clean(house):
    t = time.perf_counter()
    b = plan_demo(house)
    dt = time.perf_counter() - t
    print("%s: %d floors, %.2f s" % (house[0], len(b.floors), dt))
    assert len(b.floors) == EXPECTED_FLOORS[house[0]], (b.notes, b.dropped)
    assert not S.validate(b), S.validate(b)
    assert sum(1 for f in b.floors for r in f.plan.rooms if r.type == "Master") == 1
    assert dt < 1.5


def test_the_census_worst_case_plans_in_time():
    """Spec §1.7: at most 1.5 s a building. The census's slowest house (16 x 11 m, the upper floor 200 cm short of the
    back: a 16 x 2 m terrace) took 1.1-1.6 s with the machine's load -- its terrace's table set was tried at every 10 cm
    of the deck for each of the 6 stair places, and every place checked the floor's room sizes afresh. The better of two
    runs of its two slowest seeds (a busy machine slows a run, not the work)."""
    lower, upper = [(0, 0), (1600, 0), (1600, 1100), (0, 1100)], [(0, 0), (1600, 0), (1600, 900), (0, 900)]
    for seed in (2, 3):
        dts = []
        for _ in range(2):
            t = time.perf_counter()
            b = S.plan_building(splines_of([lower, upper]), (0.0, 0.0, 0.0), 0.0, PARAMS, random.Random(seed))
            dts.append(time.perf_counter() - t)
        assert len(b.floors) == 2 and min(dts) < 1.5, (seed, [round(x, 2) for x in dts])


def test_the_stair_places_share_a_floors_room_checks(monkeypatch):
    """Final review (spec §1.7): each of the 6 stair places tried checked the same rooms of a floor again
    (layout._sizes_ok). A room's size check depends on the floor and the room alone, so a floor checks each room
    rectangle once however many places it is planned around."""
    from collections import Counter
    seen = Counter()
    real = L._sizes_ok

    def counting(rooms, fp, walls):
        seen.update((id(fp), t, r) for t, r in rooms)
        return real(rooms, fp, walls)
    monkeypatch.setattr(L, "_sizes_ok", counting)
    lower, upper = [(0, 0), (1600, 0), (1600, 1100), (0, 1100)], [(0, 0), (1600, 0), (1600, 900), (0, 900)]
    b = S.plan_building(splines_of([lower, upper]), (0.0, 0.0, 0.0), 0.0, PARAMS, random.Random(1))
    assert len(b.floors) == 2 and seen
    assert max(seen.values()) == 1, seen.most_common(3)


def test_stair_is_aligned_on_every_floor():
    for house in demo.STOREYS:
        b = plan_demo(house)
        for f in b.floors:
            st = [r for r in f.plan.rooms if r.type == "Stair"]
            assert len(st) == 1 and st[0].rect == b.stair.rect and f.plan.stair is b.stair and f.plan.level == f.level


SERVICE_MAX = {"WC": 4.5, "Laundry": 8.0, "Bath": 9.0}      # m2 of clear floor


def test_service_rooms_keep_their_size():
    """The blocks around the stair are fixed, so a block given only a WC used to be one 8 m2 WC (House_13's ground
    floor: a 12.5 m2 laundry, an 8 m2 WC): a block that is much larger than its rooms takes a storage room as well."""
    big = []
    for house in demo.STOREYS:
        b = plan_demo(house)
        for f in b.floors:
            for r in f.plan.rooms:
                if r.type in SERVICE_MAX:
                    c = L.clear_rect(r.rect, f.fp, f.plan.walls)
                    if c.w * c.h / 1e4 > SERVICE_MAX[r.type]:
                        big.append((house[0], f.level, r.type, round(c.w * c.h / 1e4, 1)))
    assert not big, big


def test_upper_floors_keep_the_bath_and_the_ground_the_front_door():
    for house in demo.STOREYS:
        b = plan_demo(house)
        for f in b.floors:
            kinds = [d.kind for d in f.doors]
            assert (kinds.count("front") == 1) == (f.level == 0)
            if any(r.type in ("Master", "Bedroom") for r in f.plan.rooms):
                assert any(r.type == "Bath" for r in f.plan.rooms)


def test_awkward_setbacks_plan_clean_or_drop_with_a_note():
    """Review Focus 1: an L-shaped upper floor, an upper floor 5 m wide, a setback right beside the best stair place --
    every floor that is kept plans clean, a floor that cannot be planned is dropped with a report."""
    cases = [
        [[(0, 0), (1200, 0), (1200, 1000), (0, 1000)], [(0, 0), (1200, 0), (1200, 500), (600, 500), (600, 1000), (0, 1000)]],
        [[(0, 0), (1000, 0), (1000, 900), (0, 900)], [(0, 0), (500, 0), (500, 900), (0, 900)]],
        [[(0, 0), (1000, 0), (1000, 800), (0, 800)], [(0, 0), (1000, 0), (1000, 450), (0, 450)]],
        [[(0, 0), (1000, 0), (1000, 800), (0, 800)], [(0, 0), (1000, 0), (1000, 800), (520, 800), (520, 650), (0, 650)]],
    ]
    for outlines in cases:
        b = S.plan_building(splines_of(outlines), (0.0, 0.0, 0.0), 0.0, PARAMS, random.Random(1))
        assert not S.validate(b), (outlines, S.validate(b))
        assert len(b.floors) == 2 or (len(b.floors) <= 1 and b.dropped), (outlines, b.dropped)


def test_a_shallow_upper_floor_keeps_its_stair_only_along_the_back():
    """Guide §8.6 (final review): an upper floor 5 m on its short side holds no U or L stair beside a 250 cm block, only a
    straight one -- along the back wall it plans (a loft), at the front the floor goes with a report; 5.5 m holds a U."""
    g = [(0, 0), (1000, 0), (1000, 900), (0, 900)]

    def plan(upper):
        return S.plan_building(splines_of([g, upper]), (0.0, 0.0, 0.0), 0.0, PARAMS, random.Random(1))
    back = plan([(0, 400), (1000, 400), (1000, 900), (0, 900)])
    assert len(back.floors) == 2 and back.stair.type == "Straight" and not S.validate(back)
    assert back.floors[1].plan.program.name == "Upper_S"
    front = plan([(0, 0), (1000, 0), (1000, 500), (0, 500)])
    assert not front.floors and front.dropped == ("2F: no stair place plans every floor",)
    deeper = plan([(0, 0), (1000, 0), (1000, 550), (0, 550)])
    assert len(deeper.floors) == 2 and deeper.stair.type == "U" and not S.validate(deeper)


def test_every_tree_passage_finds_its_door():
    """A corridor and a WC sharing 120 cm at an outside corner: enough wall for connect, not for a door between the jambs
    (14 x 6 m, two floors, the census found the upper floor without a door into its WC). A layout whose passage has no
    door is no layout."""
    rect = [(0, 0), (1400, 0), (1400, 600), (0, 600)]
    b = S.plan_building(splines_of([rect, rect]), (0.0, 0.0, 0.0), 0.0, PARAMS, random.Random(1))
    assert len(b.floors) == 2 and not S.validate(b), S.validate(b)


def test_three_floors_on_a_small_house_drop_with_notes():
    """Review Focus 5: Floors 3 on a 6 x 6 m house: no stair leaves usable blocks there, the upper floors go, reported."""
    b = S.plan_building(splines_of([[(0, 0), (600, 0), (600, 600), (0, 600)]]), (0.0, 0.0, 0.0), 0.0,
                        dict(PARAMS, Floors=3), random.Random(1))
    assert len(b.floors) <= 1 and len(b.dropped) == 2 and b.stair is None


def test_deterministic():
    """Review Focus 5: the same splines and seed give the same rooms, doors and furniture on every floor."""
    def sig(b):
        return [(f.level, [(r.type, r.rect) for r in f.plan.rooms], [(d.kind, d.axis, d.c, d.s0, d.s1) for d in f.doors],
                 [(p.item, round(p.x, 3), round(p.y, 3), p.yaw) for p in f.places],
                 [(t.rect, [(p.item, round(p.x, 3), round(p.y, 3)) for p in t.places]) for t in f.terraces]) for f in b.floors]
    house = demo.STOREYS[1]
    assert sig(plan_demo(house, seed=5)) == sig(plan_demo(house, seed=5))


def test_room_rows_carry_the_floor():
    b = plan_demo(demo.STOREYS[4])
    rows = S.room_rows(b)
    assert {r["Floor"] for r in rows} == {0, 1, 2}
    assert sum(1 for r in rows if r["Type"] == "Stair") == 3 and any(r["Type"] == "Terrace" for r in rows)
    H = S.floor_height(PARAMS["WallHeight"])
    for r in rows:
        assert r["loc"][2] == pytest.approx(r["Floor"] * H + 5.0)


# ---------------------------------------------------------------- the demo street

def _box_of(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return L.Rect(min(xs), min(ys), max(xs), max(ys))


def test_storey_demo_houses_sit_on_the_second_street():
    """Spec §10.1: the seven houses on a second street south of the first, 11-14 north of it and 15-17 south of it, each
    facing it, none on another house or on the first street's houses."""
    first = [_box_of(demo.world_points(shape, loc, yaw)) for _n, shape, loc, yaw, _s, _d in demo.houses()]
    second = []
    names = []
    for name, outlines, loc, yaw, floors, stair, style, seed in demo.storeys():
        pts = demo.floor_points(outlines[0], loc, yaw, 0, 300.0)
        box = _box_of(pts)
        north = int(name.split("_")[1]) <= 14
        street = demo.STREET2 + (demo.FRONT if north else -demo.FRONT)
        assert yaw == (-90.0 if north else 90.0)
        assert (box.y0 >= street - 1e-6) if north else (box.y1 <= street + 1e-6), name
        assert min(abs(p[1] - street) for p in pts) < 1e-6                     # its front on the street
        second.append(box)
        names.append(name)
    assert names == [h[0] for h in demo.STOREYS]
    assert not [(a, b) for a in second for b in first if a.overlaps(b)]
    assert not [(a, b) for i, a in enumerate(second) for b in second[i + 1:] if a.overlaps(b)]


def test_floor_points_are_raised():
    name, outlines, loc, yaw, *_rest = demo.storeys()[4]
    for k, o in enumerate(outlines):
        pts = demo.floor_points(o, loc, yaw, k, 300.0)
        assert all(p[2] == pytest.approx(loc[2] + 300.0 * k) for p in pts)
        assert [p[:2] for p in pts] == pytest.approx([p[:2] for p in demo.floor_points(o, loc, yaw, 0, 300.0)])


def test_summary_names_every_floor():
    b = plan_demo(demo.STOREYS[4])
    s = S.summary(b, [], [])
    assert s["floors"] == 3 and s["program"].count("/") == 2 and s["stair"] == "U" and s["terraces"] >= 2


# ---------------------------------------------------------------- the parts

H = S.floor_height(PARAMS["WallHeight"])


def parts_of(house, loc=(0.0, 0.0, 0.0), yaw=0.0, **over):
    b = plan_demo(house, loc=loc, yaw=yaw)
    params = dict(PARAMS, Style=house[4], WallCut=0.0, ShowFloors=0, RealMeshes=True)
    params.update(over)
    return b, S.parts(b, params, random.Random(house[5]))


def test_floors_stack_at_floor_height():
    """Every part of floor k lies between its slab (k H - 30) and the next floor (the flights climb to it; their handrails
    end RAIL_UP above its level)."""
    from pypcg.interior import stairs as ST
    for house in demo.STOREYS:
        b, items = parts_of(house)
        assert {i["floor"] for i in items} == set(range(len(b.floors)))
        for i in items:
            z = i["loc"][2]
            hi = (i["floor"] + 1) * H + (ST.RAIL_UP if i["role"] == "handrail" else 0.0)
            assert i["floor"] * H - S.SLAB - 1e-6 <= z <= hi + 1e-6, (house[0], i["role"], z)


def test_slab_leaves_the_stair_open():
    """Floor k >= 1 stands on a 30 cm slab over its own outline, open over the stair room, with no floor or skirting in
    the stair room; the ground floor's foundation runs under the stair."""
    for house in demo.STOREYS:
        b, items = parts_of(house)
        for f in b.floors:
            own = [i for i in items if i["floor"] == f.level]
            if f.level == 0:
                found = [i["local"][0] for i in own if i["role"] == "foundation"]
                assert sum(r.area for r in found) == pytest.approx(f.fp.area)
                assert any(r.overlaps(b.stair.rect) for r in found)
                continue
            slabs = [i["local"] for i in own if i["role"] == "slab"]
            assert slabs and all(z0 == pytest.approx(-S.SLAB) and z1 == pytest.approx(0.0) for _r, z0, z1 in slabs)
            assert not any(r.overlaps(b.stair.rect) for r, _z0, _z1 in slabs)
            assert sum(r.area for r, _z0, _z1 in slabs) == pytest.approx(f.fp.area - b.stair.rect.area)
            assert not [i for i in own if i["role"] in ("floor", "skirting") and i["local"][0].overlaps(b.stair.rect)]


def test_terrace_railing_on_outer_edges_only():
    """The front terrace of House_12: slab and deck over the terrace, a railing along its three open edges, none along
    the upper floor's wall; posts at most 150 apart."""
    from pypcg.interior import terrace as T
    b, items = parts_of(demo.STOREYS[1])
    f = b.floors[1]
    t = f.terraces[0]
    own = [i for i in items if i["floor"] == 1]
    assert {i["local"][0] for i in own if i["role"] == "terrace_deck"} == {t.rect}
    rails = [i for i in own if i["role"] == "railing" and i["local"][0].overlaps(t.rect)]     # not the stair's guard rail
    assert rails

    def band(axis, c, lo, hi, out):
        d = -out * T.RAIL_IN * 2
        return L.Rect(lo, min(c, c + d), hi, max(c, c + d)) if axis == "y" else L.Rect(min(c, c + d), lo, max(c, c + d), hi)
    bands = [band(*r) for r in t.rails]
    assert all(any(i["local"][0].inside(bd) for bd in bands) for i in rails if "local" in i)
    posts = sorted(i["local"][0].cx for i in rails if i.get("part") == "post" and i["local"][0].cy < 20)
    assert posts and max(b - a for a, b in zip(posts, posts[1:])) <= T.POST + 1e-6


def test_show_floors_bounds():
    """ShowFloors 1: the ground floor alone, nothing above its walls; 5 on two floors: everything; WallCut lowers the
    walls of the top shown floor only."""
    house = demo.STOREYS[0]
    _b, one = parts_of(house, ShowFloors=1)
    assert {i["floor"] for i in one} == {0} and max(i["loc"][2] for i in one) <= PARAMS["WallHeight"] + 1e-6
    _b, every = parts_of(house, ShowFloors=0)
    _b, five = parts_of(house, ShowFloors=5)
    assert len(five) == len(every) and {i["floor"] for i in five} == {0, 1}
    _b, cut = parts_of(house, ShowFloors=2, WallCut=100.0)
    tops = {k: max(i["local"][2] for i in cut if i["floor"] == k and i["role"] == "wall") for k in (0, 1)}
    assert tops[0] == pytest.approx(PARAMS["WallHeight"]) and tops[1] == pytest.approx(100.0)


def test_walls_never_overlap_on_any_floor():
    from pypcg.interior import assemble as A
    for house in demo.STOREYS:
        b = plan_demo(house)
        for f in b.floors:
            rects = [r for r, _k, _a, _c in A.wall_plan(f.plan)]
            assert not [(a, c) for i, a in enumerate(rects) for c in rects[i + 1:] if a.overlaps(c)]


def test_the_stair_keeps_out_of_thick_walls():
    """Final review: the stair room takes the stage's ExteriorWall / InteriorWall as every other room does -- it read the
    25 / 12 cm defaults, so at 40 / 20 cm its treads and landing reached 15 cm into the outer wall, with no failure."""
    rect = [(0, 0), (1000, 0), (1000, 800), (0, 800)]
    params = dict(PARAMS, ExteriorWall=40.0, InteriorWall=20.0)
    b = S.plan_building(splines_of([rect, rect]), (0.0, 0.0, 0.0), 0.0, params, random.Random(1))
    assert len(b.floors) == 2 and not S.validate(b), (b.dropped, S.validate(b))
    items = S.parts(b, dict(params, Style="Scandi", WallCut=0.0, ShowFloors=0, RealMeshes=True), random.Random(1))
    for f in b.floors:
        clear = L.clear_rect(b.stair.rect, f.fp, f.plan.walls)
        blocks = [i["local"][0] for i in items if i["floor"] == f.level and i["role"] in ("tread", "landing")]
        assert bool(blocks) == (f.level == 0)
        assert all(r.inside(clear) for r in blocks), (f.level, clear, b.stair.clear)


@pytest.mark.parametrize("yaw", [30.0, 90.0, 217.0])
def test_a_turned_building_is_the_same_building_turned(yaw):
    """Review Focus 2: the stepped house turned about its actor: the same floors, stair and terraces in its own frame,
    every part turned with it and stacked at the actor's z + k H."""
    from pypcg.interior import footprint as F
    house = demo.STOREYS[4]
    loc = (300.0, -200.0, 50.0)
    b0, p0 = parts_of(house, loc=loc, yaw=0.0)
    b1, p1 = parts_of(house, loc=loc, yaw=yaw)
    assert [[(r.type, r.rect) for r in f.plan.rooms] for f in b0.floors] == \
        [[(r.type, r.rect) for r in f.plan.rooms] for f in b1.floors]
    assert b0.stair.rect == b1.stair.rect and [[t.rect for t in f.terraces] for f in b0.floors] == \
        [[t.rect for t in f.terraces] for f in b1.floors]
    fr0, fr1 = F.Frame(loc, 0.0), F.Frame(loc, yaw)
    assert len(p0) == len(p1)
    for a, c in zip(p0, p1):
        assert (a["role"], a["mesh"], a["floor"]) == (c["role"], c["mesh"], c["floor"])
        assert fr0.local(a["loc"]) == pytest.approx(fr1.local(c["loc"]), abs=1e-6)
        assert a["loc"][2] == pytest.approx(c["loc"][2]) and a["rot"][0] == pytest.approx(c["rot"][0], abs=1e-6)
        assert ((c["rot"][1] - a["rot"][1] - yaw + 180.0) % 360.0) - 180.0 == pytest.approx(0.0, abs=1e-6)
