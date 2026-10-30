"""PyInterior stairs (spec 2026-10-29 §6): types, the stair room's candidates, its openings, its parts."""
import pytest

from pypcg.interior import stairs as ST
from pypcg.interior import storeys as S

from test_interior_storeys import box


def two_floors(w, h, n=2):
    lv = S.levels([box(w, h)], 0.0, 270.0, n)
    return S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)[0]


def test_types():
    assert ST.TYPES["U"].max_floors == 3 and ST.TYPES["L"].max_floors == 2 and ST.TYPES["Straight"].max_floors == 2


def test_candidates_stay_inside_and_on_an_outer_wall():
    fps = two_floors(1000, 800)
    cands, _ = ST.candidates(fps)
    assert cands
    for s in cands:
        assert s.cells(50.0) <= fps[-1].cells
        r = s.rect
        assert abs(r.x0) < 1e-6 or abs(r.x1 - 1000) < 1e-6 or abs(r.y0) < 1e-6 or abs(r.y1 - 800) < 1e-6   # on an outer wall
        for role in ("ground", "top"):
            axis, c, s0, s1 = s.access(role)
            assert 0 < c < (1000 if axis == "x" else 800)            # never on the outline


def test_every_candidate_holds_its_flights():
    for s in ST.candidates(two_floors(1200, 900))[0]:
        t = ST.TYPES[s.type]
        w, l = sorted((s.clear.w, s.clear.h))
        assert w >= min(t.clear_w, t.clear_l) - 1e-6 and l >= max(t.clear_w, t.clear_l) - 1e-6
        assert s.rect.x0 <= s.clear.x0 and s.clear.x1 <= s.rect.x1 and s.rect.y0 <= s.clear.y0 and s.clear.y1 <= s.rect.y1


def test_three_floors_use_u_only():
    cands, notes = ST.candidates(two_floors(600, 1100, 3), "Straight")
    assert cands and {s.type for s in cands} == {"U"} and notes


def test_a_forced_type_is_kept_when_allowed():
    cands, notes = ST.candidates(two_floors(650, 1300), "Straight")
    assert cands and {s.type for s in cands} == {"Straight"} and not notes


def test_access_spans():
    s = next(c for c in ST.candidates(two_floors(1000, 800))[0] if c.type == "U")
    g, t = s.access("ground"), s.access("top")
    assert abs((g[3] - g[2]) - 110.0) < 1e-6 and abs((t[3] - t[2]) - 220.0) < 1e-6 and s.void("top") is not None
    assert s.void("ground") is None


def test_first_candidate_keeps_off_the_front():
    s = ST.candidates(two_floors(1000, 800))[0][0]
    assert s.rect.y0 > 1e-6


def test_candidates_leave_usable_blocks_on_every_floor():
    """Spec §6.2: a stair place that cuts a block narrower than 250 cm out of any floor is not a candidate."""
    from pypcg.interior import floorplan as FP
    for w, h, n in ((800, 700, 2), (1000, 700, 2), (550, 1100, 3)):
        fps = two_floors(w, h, n)
        cands = ST.candidates(fps)[0]
        assert cands and all(FP.pieces_options(fp, s.rect) for s in cands for fp in fps)


PAL = {"wood": "Oak", "wood_dark": "Walnut", "steel": "Steel", "facade": "Plaster_White", "glass": "Glass"}
H = 300.0


def stair_items(s, fps):
    """{level: [item]} of the stair's parts on every floor, each floor showing the one above."""
    from pypcg.interior import assemble as A
    n = len(fps)
    out = {}
    for lv in range(n):
        o = A._Out(fps[lv], None)
        ST.parts(s, o, lv, lv + 1 < n, lv == n - 1, H, PAL)
        out[lv] = o.items
    return out


@pytest.mark.parametrize("kind, w, h, n", [("U", 1000, 800, 3), ("L", 1000, 800, 2), ("Straight", 650, 1300, 2)])
def test_stair_parts(kind, w, h, n):
    """17 risers a floor (rise H / 17): on every floor but the top, 16 blocks -- treads and the U's and L's landing --
    whose tops are the 16 riser heights below the next floor, all inside the stair room's clear floor; a handrail along
    each flight; the U's top floor a guard rail over the open half; stacked U flights keep 200 cm and more between them."""
    fps = two_floors(w, h, n)
    s = next(c for c in ST.candidates(fps, kind)[0] if c.type == kind)
    items = stair_items(s, fps)
    rise = H / 17
    for lv in range(n - 1):
        blocks = [i for i in items[lv] if i["role"] in ("tread", "landing")]
        tops = sorted(round(i["local"][2] / rise, 6) for i in blocks)
        assert tops == list(range(1, 17)), tops
        assert all(i["local"][0].inside(s.clear) for i in blocks)
        assert sum(1 for i in blocks if i["role"] == "landing") == (0 if kind == "Straight" else 1)
        assert sum(1 for i in items[lv] if i["role"] == "handrail") >= (1 if kind == "Straight" else 2)
    assert not [i for i in items[n - 1] if i["role"] in ("tread", "landing")]
    assert bool([i for i in items[n - 1] if i["role"] == "railing"]) == (kind == "U")
    if n == 3:
        lower = [(i["local"][0], i["local"][2]) for i in items[0] if i["role"] in ("tread", "landing")]
        upper = [(i["local"][0], H + i["local"][1]) for i in items[1] if i["role"] in ("tread", "landing")]
        gaps = [z0 - z1 for r1, z1 in lower for r0, z0 in upper if r1.overlaps(r0)]
        assert gaps and min(gaps) >= 200.0
