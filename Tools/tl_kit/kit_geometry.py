"""kit_geometry.py -- pure-Python geometry for the spline building's new kit
pieces (end piers, acute end piers, front / back fans). No bpy: build_tl_kit.py
collects the boxes a facade builder emits, hands them here, and turns the
returned boxes / sectors into mesh. Tested by test_kit_geometry.py.

Frames are the kit's UE frame: x outward (facade plane x = 0, relief x > 0,
body x < 0), y along the run, z up. Lengths are metres, like build_tl_kit.py.
A box is (x0, x1, y0, y1, z0, z1, slot); a section box drops y:
(x0, x1, z0, z1, slot).
"""
import math

FAN_HALF_DEG = 5.0          # every fan mesh is a +-5 deg wedge about local +X
ACUTE_MIN_BODY_M = 0.01     # an acute pier keeps at least 1 cm of body


def section(boxes, y_probe):
    """The cross-section of a straight run at y = y_probe: every box whose
    run spans y_probe, with y dropped. Boxes that do not span it (dentils,
    joints, short ornaments) are not part of the continuous profile."""
    return [(b[0], b[1], b[4], b[5], b[6]) for b in boxes if b[2] < y_probe < b[3]]


def z_breaks(sec):
    return sorted({z for s in sec for z in (s[2], s[3])})


def front_at(sec, z0, z1):
    """Largest projection in front of the facade over the band [z0, z1]."""
    return max([s[1] for s in sec if s[1] > 0.0 and s[2] < z1 and s[3] > z0] + [0.0])


def acute_clip(boxes, sec):
    """The acute end pier: every box keeps its front part, and its part behind
    the facade is cut to max(front depth of that height band, 1 cm). Boxes are
    split at the section's z breaks so each piece sees one band."""
    zs = z_breaks(sec)
    out = []
    for x0, x1, y0, y1, z0, z1, slot in boxes:
        if x0 >= 0.0:
            out.append((x0, x1, y0, y1, z0, z1, slot))
            continue
        cuts = [z for z in zs if z0 < z < z1]
        for a, b in zip([z0] + cuts, cuts + [z1]):
            depth = max(front_at(sec, a, b), ACUTE_MIN_BODY_M)
            nx0 = max(x0, -depth)
            if x1 - nx0 > 1e-6:
                out.append((nx0, x1, y0, y1, a, b, slot))
    return out


def fan_rings(sec, kind):
    """Annular rings to revolve for a fan: (r0, r1, z0, z1, slot). 'front'
    takes the part of each section box in front of the facade (x > 0);
    'back' takes the part behind it, with r measured from the facade."""
    rings = []
    for x0, x1, z0, z1, slot in sec:
        if kind == "front" and x1 > 0.0:
            rings.append((max(x0, 0.0), x1, z0, z1, slot))
        elif kind == "back" and x0 < 0.0:
            rings.append((max(-x1, 0.0), -x0, z0, z1, slot))
    return rings


def ring_sector_xy(r0, r1, kind, half_deg=FAN_HALF_DEG):
    """Plan-view outline (counter-clockwise, UE frame) of one ring revolved
    over +-half_deg about local +X. A front ring sits at +X, a back ring at -X
    (the mesh's local +X stays the slice's exterior direction). r0 == 0 gives
    a triangle with its apex on the vertex."""
    h = math.radians(half_deg)
    sgn = 1.0 if kind == "front" else -1.0

    def p(r, a):
        return (sgn * r * math.cos(a), sgn * r * math.sin(a))
    pts = [p(r1, -h), p(r1, h)]
    pts += [p(r0, h), p(r0, -h)] if r0 > 1e-9 else [(0.0, 0.0)]
    # the back ring is the front ring turned 180 deg, which keeps the winding
    return pts
