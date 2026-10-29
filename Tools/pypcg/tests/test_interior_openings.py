"""PyInterior windows: the wall grammar on exterior walls (spec 2026-10-28 §4.6)."""
import random

import pytest

from pypcg.interior import doors as D
from pypcg.interior import layout as L
from pypcg.interior import openings as O
from pypcg.interior import program as P

from test_interior_layout import SWEEP, fp_of


def cases():
    out = []
    for k, pts in enumerate(SWEEP):
        fp = fp_of(pts)
        if fp is None:
            continue
        plan = L.plan(fp, P.choose(fp.area_m2), random.Random(1))
        doors = D.connect(plan, random.Random(1))
        out.append((k, plan, doors, O.windows(plan, doors, random.Random(1))))
    return out


CASES = cases()


@pytest.mark.parametrize("k, plan, doors, wins", CASES, ids=[str(c[0]) for c in CASES])
def test_window_invariants(k, plan, doors, wins):
    fp = plan.footprint
    by = {r.id: r for r in plan.rooms}
    for w in wins:
        r = by[w.room]
        # on an exterior stretch of one of the room's sides
        side = [e for e in r.rect.edges() if e[0] == w.axis and abs(e[1] - w.c) < 1e-6 and e[4] == w.outward]
        assert side, w
        parts = L.exterior_parts(fp, w.axis, w.c, side[0][2], side[0][3], w.outward)
        assert any(a - 1e-6 <= w.s0 and w.s1 <= b + 1e-6 for a, b in parts), w
        # clear of the room's corners and of doors on the same wall
        cr = L.clear_rect(r.rect, fp, plan.walls)
        lo, hi = (cr.y0, cr.y1) if w.axis == "x" else (cr.x0, cr.x1)
        assert w.s0 >= lo + L.WINDOW_CORNER - 1e-6 and w.s1 <= hi - L.WINDOW_CORNER + 1e-6
        for d in doors:
            if d.axis == w.axis and abs(d.c - w.c) < 1e-6:
                assert w.s1 <= d.s0 - O.DOOR_CLEAR + 1e-6 or w.s0 >= d.s1 + O.DOOR_CLEAR - 1e-6, (w, d)
        kind = P.ROOMS[r.type].window
        assert w.kind == kind and (w.sill, w.height) == O.WINDOWS[kind][1:3]
    # no two windows overlap
    for i, a in enumerate(wins):
        for b in wins[i + 1:]:
            if a.axis == b.axis and abs(a.c - b.c) < 1e-6:
                assert a.s1 <= b.s0 + 1e-6 or b.s1 <= a.s0 + 1e-6
    # every habitable room has a window; a wet room's window is high
    have = {w.room for w in wins}
    for r in plan.rooms:
        if r.type in L.HABITABLE:
            assert r.id in have, r.type
    for w in wins:
        if by[w.room].type in ("Bath", "WC", "Laundry"):
            assert w.sill >= 150.0


def test_long_walls_get_more_windows():
    plan = L.plan(fp_of([(0, 0), (2000, 0), (2000, 1000), (0, 1000)]), P.choose(200.0), random.Random(1))
    doors = D.connect(plan, random.Random(1))
    wins = O.windows(plan, doors, random.Random(1))
    living = next(r for r in plan.rooms if r.type == "Living")
    lw = [w for w in wins if w.room == living.id]
    assert len(lw) >= 2
