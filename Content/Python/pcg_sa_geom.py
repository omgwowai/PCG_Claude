# Content/Python/pcg_sa_geom.py
# Pure geometry for the small-area run. No `unreal` import: this module is
# imported by the editor-side scripts inside the editor's embedded Python, and
# it is also imported by pytest on the system interpreter. Anything that needs
# the engine belongs in pcg_sa_shape.py / pcg_sa_run.py instead.
#
# The transform is a single similarity: scale about `src_center`, then move that
# centre to `dst_center`. Used identically for spline points, camera positions and
# volume locations, so the whole scene shrinks coherently.

import math


def bbox_of_points(points):
    """(min_xyz, max_xyz) as plain float lists for a list of 3-element points."""
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    zs = [float(p[2]) for p in points]
    return ([min(xs), min(ys), min(zs)], [max(xs), max(ys), max(zs)])


def city_bbox_from_splines(splines):
    """Union bbox over a list of {"points": [[x,y,z], ...]} dicts."""
    pts = []
    for sp in splines:
        pts.extend(sp["points"])
    return bbox_of_points(pts)


def scale_for_target(city_bbox, target_cm):
    """Scale making the bbox's LONGER horizontal side equal target_cm.

    Horizontal only: Z must not drive the scale, or a tall thin city would be
    shrunk by its height."""
    mn, mx = city_bbox
    span = max(float(mx[0]) - float(mn[0]), float(mx[1]) - float(mn[1]))
    if span <= 0.0:
        raise ValueError("degenerate city bbox: horizontal span is 0")
    return float(target_cm) / span


def map_point(p, scale, src_center, dst_center):
    """Similarity map: p -> dst_center + scale * (p - src_center)."""
    return [float(dst_center[i]) + float(scale) * (float(p[i]) - float(src_center[i]))
            for i in range(3)]


def map_tangent(v, scale):
    """Tangents are directions: they scale but never translate."""
    return [float(scale) * float(v[i]) for i in range(3)]


def orbit_camera(center, radius_cm, az_deg, elev_deg, dist_mult, min_height):
    """A camera pose looking down at `center` from a bearing.

    `radius_cm` is the subject's horizontal radius; the distance is
    dist_mult * radius_cm so the subject fills a reasonable part of the frame.
    Returns ([x,y,z], [pitch,yaw,roll]) with roll always 0.

    Why compute this at all, when the 09-23 run had to use the level's own cine
    cameras: those were authored for a 2 km city whose stage 3 vista sits 10 M
    units out, so bounds-derived poses flew away. Here the subject is 600 m of
    our own freshly-generated geometry, so a computed orbit is both safe and
    exactly framed. The cine cameras are still used as a fallback.
    """
    dist = float(dist_mult) * float(radius_cm)
    az = math.radians(float(az_deg))
    elev = math.radians(float(elev_deg))
    horiz = dist * math.cos(elev)
    x = float(center[0]) + horiz * math.cos(az)
    y = float(center[1]) + horiz * math.sin(az)
    z = float(center[2]) + dist * math.sin(elev)
    if z < float(min_height):
        z = float(min_height)
    # UE pitch is negative when looking down.
    pitch = -math.degrees(math.atan2(z - float(center[2]), horiz)) if horiz > 0 else -90.0
    yaw = math.degrees(math.atan2(float(center[1]) - y, float(center[0]) - x))
    return [x, y, z], [pitch, yaw, 0.0]
