"""Terrain edits on a Lattice (视频：河道下切、路基、平台、垫平). Each returns how many vertices it changed."""
import math

from . import ROAD_BLEND, ROAD_INNER, geom


def smoothstep(e0, e1, x):
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def _index(samples):
    idx = geom.SegmentIndex(2000.0)
    for a in range(len(samples) - 1):
        idx.add(samples[a], samples[a + 1], a)
    return idx


def _box(samples, reach):
    return (min(s[0] for s in samples) - reach, min(s[1] for s in samples) - reach,
            max(s[0] for s in samples) + reach, max(s[1] for s in samples) + reach)


def carve_river(lat, samples, depth=150.0, bank_slope=0.5, reach=2000.0):
    """samples [(x, y, water_z, width)]. Inside half the width the bed is a parabola `depth` below the water at the
    centre line; outside, the bank rises from the water line at `bank_slope`. A vertex only ever goes down."""
    if len(samples) < 2:
        return 0
    idx = _index(samples)
    far = 0.5 * max(s[3] for s in samples) + reach
    changed = 0
    for k in list(lat.cells_in_box(*_box(samples, far))):
        x, y = lat.xy(k)
        hit = idx.nearest(x, y, far)
        if hit is None:
            continue
        d, a, t = hit
        s0, s1 = samples[a], samples[a + 1]
        water = s0[2] + (s1[2] - s0[2]) * t
        half = 0.5 * (s0[3] + (s1[3] - s0[3]) * t)
        if d > half + reach:
            continue
        target = water - depth * (1.0 - (d / half) ** 2) if d <= half else water + bank_slope * (d - half)
        if target < lat.z[k]:
            lat.z[k] = target
            changed += 1
    return changed


def carve_channel(lat, samples, depth=150.0, reach=2000.0):
    """A meander's cross sections (视频 + Peytavie 2019 河道断面：弯道外侧深切、内侧点沙坝). samples [(x, y, water_z, width,
    bend, bar)]: `bend` in -1..1 is the signed tightness of the bend (> 0: its centre lies to the left of the flow),
    `bar` the point bar's width (cm) on the inner bank. Inside the channel the bed is a parabola whose deepest point
    moves 0.4 x the half width towards the outer bank, 0.8 x depth deep on a straight riffle, 1.4 x in a tight bend's
    pool. Outside, the outer bank rises at 0.5 + 0.6 |bend|, the inner bank first as a bar 6 cm per m above the water,
    then at 0.5 - 0.4 |bend|. A vertex only ever goes down."""
    if len(samples) < 2:
        return 0
    idx = _index(samples)
    far = 0.5 * max(s[3] for s in samples) + reach
    changed = 0
    for k in list(lat.cells_in_box(*_box(samples, far))):
        x, y = lat.xy(k)
        hit = idx.nearest(x, y, far)
        if hit is None:
            continue
        d, a, t = hit
        s0, s1 = samples[a], samples[a + 1]
        water = s0[2] + (s1[2] - s0[2]) * t
        half = 0.5 * (s0[3] + (s1[3] - s0[3]) * t)
        bend = s0[4] + (s1[4] - s0[4]) * t
        bar = s0[5] + (s1[5] - s0[5]) * t
        if d > half + reach:
            continue
        left = (s1[0] - s0[0]) * (y - s0[1]) - (s1[1] - s0[1]) * (x - s0[0]) > 0.0
        lat_off = d if left else -d                       # signed: + to the left of the flow
        if d <= half:
            th = -0.4 * bend * half                       # the thalweg, towards the outer bank
            u = (lat_off - th) / (half - th) if lat_off >= th else (lat_off - th) / (half + th)
            target = water - depth * (0.8 + 0.6 * abs(bend)) * (1.0 - u * u)
        else:
            out = d - half
            inner = bend != 0.0 and (lat_off > 0.0) == (bend > 0.0)
            if inner:
                target = water + 0.06 * out if out <= bar else water + 0.06 * bar + (0.5 - 0.4 * abs(bend)) * (out - bar)
            else:
                target = water + (0.5 + 0.6 * abs(bend)) * out
        if target < lat.z[k]:
            lat.z[k] = target
            changed += 1
    return changed


def flatten_corridor(lat, samples, inner=ROAD_INNER, blend=ROAD_BLEND):
    """samples [(x, y, z, half_width, skip)] along one road: flat at the road's height to half width + inner, eased
    back to the ground over `blend`; a segment with a skipped end (a bridge span) leaves the ground alone."""
    if len(samples) < 2:
        return 0
    idx = _index(samples)
    far = max(s[3] for s in samples) + inner + blend
    changed = 0
    for k in list(lat.cells_in_box(*_box(samples, far))):
        x, y = lat.xy(k)
        hit = idx.nearest(x, y, far)
        if hit is None:
            continue
        d, a, t = hit
        s0, s1 = samples[a], samples[a + 1]
        if s0[4] or s1[4]:
            continue
        hw = s0[3] + (s1[3] - s0[3]) * t
        w = 1.0 if d <= hw + inner else 1.0 - smoothstep(hw + inner, hw + inner + blend, d)
        if w <= 0.0:
            continue
        zr = s0[2] + (s1[2] - s0[2]) * t
        lat.z[k] = lat.z[k] + (zr - lat.z[k]) * w
        changed += 1
    return changed


def fit_plane(lat, cx, cy, r, max_slope_deg=4.0):
    """Least-squares plane z = a (x - cx) + b (y - cy) + c over the vertices within r, its slope clamped."""
    pts = []
    for k in lat.cells_in_box(cx - r, cy - r, cx + r, cy + r):
        x, y = lat.xy(k)
        if math.hypot(x - cx, y - cy) <= r:
            pts.append((x - cx, y - cy, lat.z[k]))
    if not pts:
        h = lat.height(cx, cy)
        return 0.0, 0.0, (h if h is not None else 0.0)
    n = float(len(pts))
    mx, my, mz = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    sxz = sum((p[0] - mx) * (p[2] - mz) for p in pts)
    syz = sum((p[1] - my) * (p[2] - mz) for p in pts)
    det = sxx * syy - sxy * sxy
    a, b = (0.0, 0.0) if abs(det) < 1e-9 else ((sxz * syy - syz * sxy) / det, (syz * sxx - sxz * sxy) / det)
    g, lim = math.hypot(a, b), math.tan(math.radians(max_slope_deg))
    if g > lim:
        a, b = a * lim / g, b * lim / g
    return a, b, mz - a * mx - b * my


def plane_z(plane, cx, cy, x, y):
    return plane[0] * (x - cx) + plane[1] * (y - cy) + plane[2]


def platform(lat, cx, cy, r, plane, keep=None, core=0.75, outer=1.15):
    """Pull the ground to the plane: fully inside core x r, easing out by outer x r; keep(x, y) in 0..1 scales it
    (1 = full platform, 0 = leave alone: roads and the river)."""
    changed = 0
    for k in list(lat.cells_in_box(cx - outer * r, cy - outer * r, cx + outer * r, cy + outer * r)):
        x, y = lat.xy(k)
        w = 1.0 - smoothstep(core * r, outer * r, math.hypot(x - cx, y - cy))
        if keep is not None and w > 0.0:
            w *= keep(x, y)
        if w <= 0.0:
            continue
        lat.z[k] = lat.z[k] + (plane_z(plane, cx, cy, x, y) - lat.z[k]) * w
        changed += 1
    return changed


def pad(lat, ring, z, margin=200.0, blend=400.0):
    """Level the ground at z under a footprint ring and `margin` around it, easing out over `blend`."""
    reach = margin + blend
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    changed = 0
    for k in list(lat.cells_in_box(min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach)):
        x, y = lat.xy(k)
        d = 0.0 if geom.point_in_ring(x, y, ring) else geom.ring_distance(x, y, ring)
        w = 1.0 if d <= margin else 1.0 - smoothstep(margin, reach, d)
        if w <= 0.0:
            continue
        lat.z[k] = lat.z[k] + (z - lat.z[k]) * w
        changed += 1
    return changed


def cut(lat, ring, z, reach, keep=None):
    """Bring every vertex within `reach` of a footprint ring (inside included) that stands above z down to z -- a level
    cut round a building so no corner of it is buried (the terrain is interpolated from vertices up to a cell diagonal
    away); lower ground stays (the plinth covers it), and so does ground where keep(x, y) is False (streets, roads)."""
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    changed = 0
    for k in list(lat.cells_in_box(min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach)):
        if lat.z[k] <= z:
            continue
        x, y = lat.xy(k)
        if not geom.point_in_ring(x, y, ring) and geom.ring_distance(x, y, ring) > reach:
            continue
        if keep is not None and not keep(x, y):
            continue
        lat.z[k] = z
        changed += 1
    return changed
