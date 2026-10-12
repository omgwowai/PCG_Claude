import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_geometry as kg

# The L1 filler as build_tl_kit.build_filler(level=1) emits it for w = 1.5:
# brick slab, then ground_base's three stone strips, plus one short ornament.
L1 = [(-0.30, 0.0, 0.0, 1.5, 0.0, 5.0, "TL_Brick"),
      (0.0, 0.06, 0.0, 1.5, 0.0, 0.45, "TL_Stone"),
      (0.0, 0.10, 0.0, 1.5, 3.60, 4.30, "TL_Stone"),
      (0.0, 0.16, 0.0, 1.5, 4.18, 4.30, "TL_Stone"),
      (0.02, 0.05, 0.10, 0.20, 1.0, 1.1, "TL_Stone")]


def _signed_area(pts):
    n = len(pts)
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))


def test_section_keeps_only_continuous_boxes():
    sec = kg.section(L1, 0.75)
    assert len(sec) == 4
    assert all(len(s) == 5 for s in sec)


def test_front_depth_per_band():
    sec = kg.section(L1, 0.75)
    assert kg.front_at(sec, 0.0, 0.45) == 0.06
    assert kg.front_at(sec, 1.0, 3.0) == 0.0
    assert kg.front_at(sec, 4.18, 4.30) == 0.16


def test_acute_clip_thins_the_body_to_the_front_depth():
    sec = kg.section(L1, 0.75)
    out = kg.acute_clip(L1, sec)
    body = [b for b in out if b[0] < 0]
    for x0, x1, y0, y1, z0, z1, slot in body:
        want = max(kg.front_at(sec, z0, z1), kg.ACUTE_MIN_BODY_M)
        assert abs(-x0 - want) < 1e-9, (z0, z1, x0)
    spans = sorted((b[4], b[5]) for b in body)
    assert spans[0][0] == 0.0 and spans[-1][1] == 5.0
    assert all(abs(a[1] - b[0]) < 1e-9 for a, b in zip(spans, spans[1:]))
    assert [b for b in out if b[0] >= 0] == [b for b in L1 if b[0] >= 0]


def test_fan_rings_split_front_and_back():
    sec = kg.section(L1, 0.75)
    front = kg.fan_rings(sec, "front")
    back = kg.fan_rings(sec, "back")
    assert sorted(r[1] for r in front) == [0.06, 0.10, 0.16]
    assert back == [(0.0, 0.30, 0.0, 5.0, "TL_Brick")]


def test_sector_edges_lie_on_the_5_degree_rays():
    for kind in ("front", "back"):
        for r0, r1 in ((0.0, 0.34), (0.06, 0.16)):
            pts = kg.ring_sector_xy(r0, r1, kind)
            assert _signed_area(pts) > 0
            for x, y in pts:
                if math.hypot(x, y) < 1e-9:
                    continue
                ang = math.degrees(math.atan2(y, x if kind == "front" else -x))
                assert abs(abs(ang) - 5.0) < 1e-9, (kind, x, y)
                assert min(abs(math.hypot(x, y) - r0), abs(math.hypot(x, y) - r1)) < 1e-9
