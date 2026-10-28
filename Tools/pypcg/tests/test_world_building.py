import math

import pytest

from pypcg.world import bdf, building as B, kit as K


def bld(style="PLA", floors=3, w=1150.0, d=1000.0, yaw=30.0, use="house", special=None, front=2, **kw):
    b = {"x": 1000.0, "y": -500.0, "z": 250.0, "w": w, "d": d, "yaw": yaw, "style": style, "floors": floors,
         "front": front, "tint": "Base", "roof_tint": "Slate", "use": use, "special": special, "seed": 7}
    b.update(kw)
    return b


def coverage_gaps(spans, length):
    """Holes and overlaps (cm) when the [x0, x1] spans should tile [0, length]."""
    spans = sorted(spans)
    holes = overlaps = 0.0
    x = 0.0
    for a, b in spans:
        if a > x:
            holes += a - x
        else:
            overlaps += x - a
        x = max(x, b)
    return holes + max(0.0, length - x), overlaps


@pytest.mark.parametrize("style", sorted(bdf.STYLES))
@pytest.mark.parametrize("dims", [(1150.0, 1000.0), (700.0, 1300.0), (2050.0, 900.0), (1525.0, 1525.0)])
def test_every_level_of_every_wall_is_closed(style, dims):
    w, d = dims
    out = B.assemble(bld(style, bdf.STYLES[style]["floors"][1], w, d))
    lengths = [w, d, w, d]
    for (edge, level), spans in out["walls"].items():
        holes, overlaps = coverage_gaps([(a, b) for a, b, _s in spans], lengths[edge])
        assert holes < 1.0 and overlaps < 1.0, (style, dims, edge, level, holes, overlaps, spans)


def test_facades_face_outwards():
    out = B.assemble(bld())
    for m in out["instances"]:
        if m["role"] in ("bay", "pier", "corner", "door"):
            yaw = math.radians(m["rot"][1])
            n = (-math.sin(yaw), math.cos(yaw))
            mid = (m["loc"][0] + math.cos(yaw) * 10.0 - 1000.0, m["loc"][1] + math.sin(yaw) * 10.0 + 500.0)
            assert n[0] * mid[0] + n[1] * mid[1] > 0.0, m


@pytest.mark.parametrize("style", sorted(bdf.STYLES))
@pytest.mark.parametrize("front", [0, 1, 2, 3])
def test_one_door_on_the_street_side(style, front):
    out = B.assemble(bld(style, front=front))
    doors = [m for m in out["instances"] if m["role"] == "door"]
    assert len(doors) == 1 and out["stats"]["door_edge"] == front, (style, front, out["stats"])


def test_four_corners_per_level():
    out = B.assemble(bld("PLA", 4))
    levels = bdf.levels("PLA", 4)
    corners = [m for m in out["instances"] if m["role"] == "corner"]
    assert len(corners) == 4 * len(levels)


def test_heights_follow_the_levels_and_the_roof_rises_above():
    b = bld("PLB", 4)
    out = B.assemble(b)
    fam = K.FAMILIES["F02"]
    assert abs(out["wall_top"] - (b["z"] + sum(fam["levels"][c]["h"] for c in bdf.levels("PLB", 4)))) < 1e-6
    assert out["ridge"] > out["wall_top"] + 150.0


def test_hip_roof_covers_the_footprint():
    """Roof_Kit_00 measured through its vertices (pyworld_probe_roof_geometry.py): `_01` is the hip corner (eaves along
    both edges through its pivot, the ridge end at (-600, -600)), `_02` a valley; a run has its eave on its pivot line
    and its ridge at y -600. Corners sit on the roof rectangle's corners turned 90 degrees, runs on the eaves."""
    out = B.assemble(bld(w=1600.0, d=1000.0, yaw=0.0))
    roof = [m for m in out["instances"] if m["role"] in ("roof_corner", "roof_run", "dormer")]
    corners = [m for m in roof if m["role"] == "roof_corner"]
    assert len(corners) == 4 and all(m["mesh"] == K.ROOF["corner"]["mesh"] for m in corners)
    assert K.ROOF["corner"]["mesh"].endswith("_01_LOD0")
    over = bdf.STYLES["PLA"]["roof"]["over"]
    hx, hy = 0.5 * (1600.0 + 2 * over), 0.5 * (1000.0 + 2 * over)
    for m in corners:
        assert abs(abs(m["loc"][0] - 1000.0) - hx) < 1e-6 and abs(abs(m["loc"][1] + 500.0) - hy) < 1e-6
    runs = [m for m in roof if m["role"] != "roof_corner"]
    covered = sum(m["scale"][0] * K.ROOF["run"]["w"] for m in runs)
    assert abs(covered - 2 * (1600.0 - 1000.0)) < 1e-6          # both long sides between the hips
    assert all(abs(abs(m["loc"][1] + 500.0) - hy) < 1e-6 for m in runs)   # on the eaves


def test_square_tower_gets_a_pyramid():
    out = B.assemble(bld("LSA", 5, 900.0, 900.0, special="BellTower"))
    roles = [m["role"] for m in out["instances"]]
    assert roles.count("roof_corner") == 4 and roles.count("roof_run") == roles.count("dormer") == 0


def test_stone_bays_line_up_from_the_base_to_the_top():
    out = B.assemble(bld("LSA", 4, 1750.0, 1300.0))
    for edge in range(4):
        rows = {lv: [(round(a, 3), round(b, 3)) for a, b, s in spans if s in ("W", "N", "O", "V", "DOOR")]
                for (e, lv), spans in out["walls"].items() if e == edge and lv in ("FND", "L1", "L2", "L3")}
        first = next(iter(rows.values()))
        assert all(r == first for r in rows.values()), (edge, rows)


def test_shop_gets_awnings_over_its_windows():
    out = B.assemble(bld("PLA", 3, use="shop"))
    front = [s for s in out["walls"][(2, "G")] if s[2] == "S"]
    awnings = [m for m in out["instances"] if m["role"] == "awning"]
    assert len(awnings) == len(front) > 0
    assert len([m for m in out["instances"] if m["role"] == "sign"]) == 1


def test_landmarks():
    hall = B.assemble(bld("LSA", 3, 1800.0, 1300.0, special="TownHall", front=0))
    roles = [m["role"] for m in hall["instances"]]
    assert roles.count("door") == 1 and any(m["mesh"] == K.GATE["mesh"] for m in hall["instances"])
    assert roles.count("plaque") >= 1 and roles.count("balcony") == 0         # the gate has its own balcony
    church = B.assemble(bld("LSA", 2, 2500.0, 1400.0, special="Church", front=3))
    assert church["stats"]["levels"] == ["FND", "L1", "T1", "L3", "CR"]


def test_plinth_blocker_and_chimneys():
    out = B.assemble(bld("BRA", 2, 1100.0, 900.0, seed=3))
    roles = [m["role"] for m in out["instances"]]
    assert roles.count("plinth") == 1 and roles.count("blocker") == 1
    for m in out["instances"]:
        if m["role"] == "chimney":
            assert m["loc"][2] + 50.0 * m["scale"][2] > out["ridge"]


def test_tints_reach_the_materials():
    out = B.assemble(bld("PLA", 3, tint="Ochre", roof_tint="Terracotta"))
    walls = [m for m in out["instances"] if m["role"] == "bay"]
    assert walls and all(m["mat"].endswith("_Ochre") for m in walls)
    roofs = [m for m in out["instances"] if m["role"].startswith("roof")]
    assert roofs and all(m["mat"] == K.tinted("Roof_Kit_00", "Terracotta") for m in roofs)


def test_same_seed_same_building():
    assert B.assemble(bld()) == B.assemble(bld())
    assert B.assemble(bld()) != B.assemble(bld(seed=8))


@pytest.mark.parametrize("style", sorted(bdf.STYLES))
def test_a_raised_door_gets_steps_down_to_the_ground(style):
    """Hochparterre: a door standing `door_rise` over the ground in front of it gets a flight of stone steps from its
    sill down to the ground -- equal rises of at most 25 cm, each tread further out from the facade, the last rise
    landing on the ground."""
    b = bld(style, bdf.STYLES[style]["floors"][0], door_rise=70.0)
    out = B.assemble(b)
    steps = [m for m in out["instances"] if m["role"] == "step"]
    assert len(steps) >= 2, style
    door = next(m for m in out["instances"] if m["role"] == "door")
    yaw = math.radians(door["rot"][1])
    n = (-math.sin(yaw), math.cos(yaw))
    flight = []
    for m in steps:
        top = m["loc"][2] + 50.0 * m["scale"][2]
        out_cm = (m["loc"][0] - door["loc"][0]) * n[0] + (m["loc"][1] - door["loc"][1]) * n[1]
        assert b["z"] - 70.0 < top < b["z"] and out_cm > 0.0, (style, top, out_cm)
        flight.append((out_cm, top))
    flight.sort()
    tops = [t for _o, t in flight]
    assert tops == sorted(tops, reverse=True)                                  # lower further out
    rises = [b["z"] - tops[0]] + [a - c for a, c in zip(tops, tops[1:])]
    assert max(rises) - min(rises) < 1e-6 and max(rises) <= 25.0, rises
    assert abs(tops[-1] - rises[0] - (b["z"] - 70.0)) < 1e-6                 # the last rise lands on the ground


def test_a_door_at_ground_level_gets_no_steps():
    for kw in ({}, {"door_rise": 0.0}, {"door_rise": 12.0}, {"door_rise": -40.0}):
        assert not [m for m in B.assemble(bld(**kw))["instances"] if m["role"] == "step"], kw


def test_a_very_high_door_gets_at_most_six_steps_of_25_cm():
    """A door 4 m over the ground (an outbuilding over a cut, measured on the real valley) keeps walkable steps: six
    at most, none higher than 25 cm, the flight's blocks reaching down to the ground."""
    b = bld(door_rise=400.0)
    steps = [m for m in B.assemble(b)["instances"] if m["role"] == "step"]
    assert len(steps) == B.STEP_MAX
    tops = sorted((m["loc"][2] + 50.0 * m["scale"][2] for m in steps), reverse=True)
    assert all(abs(a - c - B.STEP_H_MAX) < 1e-6 for a, c in zip([b["z"]] + tops, tops)), tops
    assert all(m["loc"][2] - 50.0 * m["scale"][2] <= b["z"] - 400.0 for m in steps)
