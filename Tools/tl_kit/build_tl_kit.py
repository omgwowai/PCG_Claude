"""build_tl_kit.py -- Blender 5.2 headless. Builds the TL modular kit from the spec.

    blender -b -P Tools/tl_kit/build_tl_kit.py -- --spec Tools/tl_kit/tl_kit_spec.json \
            --out E:/Blender/TL_Kit [--preview]

Style: a brick commercial block. Red brick walls, a limestone ground-floor
base and trim, black-painted window frames, glass. Every part is built from
axis-aligned boxes (glass panes are single quads), one object per part,
exported as its own FBX. --preview also assembles a building corner from the
parts the way the grammar places them and renders it to TL_Kit_preview.png.

FRAME. All geometry is written in UE coordinates; `Builder.ue()` converts to
Blender on the way in. UE's FBX importer flips Y (FbxUtilsImport.cpp:68), so
the Blender frame is the UE frame mirrored in Y:

    UE (after import)              Blender
    x  outward (exterior +X)       x
    y  run in [0, w]               -y
    z  up, base at 0               z

The facade plane is x = 0. Relief (pilasters, sills, cornices, mullions)
projects to x > 0; reveals go to x < 0; the wall slab spans x in [-WALL_D, 0].

CORNERS (UE frame, measured from CHA in the city output):
  * exterior corner C_E/C_CE: wing A along +Y (the wall leaving the corner),
    wing B along -X (the wall arriving), outer faces on x = 0 and y = 0.
  * interior corner C_I: wings along +Y and +X from the origin, exterior faces
    on x = 0 (wing A) and y = 0 (wing B).
  * half pieces C_SL/C_SR/C_IL/C_IR: a straight run with a stone strip at one
    end. The BDF route did not place them in the measured city run.

UVs: world-space box projection at UV_PER_M (CHA's L1 wall measures ~0.34 UV
per metre).
"""
import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_common

import bmesh
import bpy

UV_PER_M = 0.5
WALL_D = 0.30
HALF_STUB = 0.45          # half a corner's own wing, sized so one wall turn covers it
SLOTS = ("TL_Brick", "TL_Stone", "TL_Glass", "TL_Metal")
PREVIEW_COLORS = {"TL_Brick": (0.45, 0.13, 0.08, 1), "TL_Stone": (0.78, 0.72, 0.60, 1),
                  "TL_Glass": (0.10, 0.16, 0.22, 1), "TL_Metal": (0.04, 0.04, 0.04, 1)}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", action="store_true")
    return ap.parse_args(argv)


class Builder:
    """Accumulates boxes and quads into one bmesh. Coordinates are UE-frame and
    pass through an optional placement (offset + yaw in 90-degree steps), which
    is how --preview assembles parts without separate objects."""

    def __init__(self):
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new("UVMap")
        self.panes = set()
        self.mirror_w = None
        self.place(0.0, 0.0, 0.0, 0)

    def place(self, ox, oy, oz, yaw_deg):
        self.o = (ox, oy, oz)
        q = int(round(yaw_deg / 90.0)) % 4
        self.c, self.s = ((1, 0), (0, 1), (-1, 0), (0, -1))[q]

    def mirror(self, w):
        """Mirror the part's run (y -> w - y) until mirror(None). Used to build
        the end-of-run half corners from their start-of-run twins. Boxes only:
        panes are wound for an unmirrored frame."""
        self.mirror_w = w

    def xf(self, x, y, z):
        """Placement in the UE frame, then the UE -> Blender Y flip."""
        if self.mirror_w is not None:
            y = self.mirror_w - y
        rx = self.c * x - self.s * y + self.o[0]
        ry = self.s * x + self.c * y + self.o[1]
        return (rx, -ry, z + self.o[2])

    def _face(self, verts, slot):
        f = self.bm.faces.new(verts)
        f.material_index = SLOTS.index(slot)
        return f

    def box(self, x0, x1, y0, y1, z0, z1, slot):
        if x1 - x0 < 1e-4 or y1 - y0 < 1e-4 or z1 - z0 < 1e-4:
            return
        c = {}
        for i, x in enumerate((x0, x1)):
            for j, y in enumerate((y0, y1)):
                for k, z in enumerate((z0, z1)):
                    c[i, j, k] = self.bm.verts.new(self.xf(x, y, z))
        quads = [((1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)),
                 ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)),
                 ((0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)),
                 ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)),
                 ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)),
                 ((0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0))]
        faces = [self._face([c[v] for v in q], slot) for q in quads]
        bmesh.ops.recalc_face_normals(self.bm, faces=faces)

    def pane(self, x, y0, y1, z0, z1, slot="TL_Glass"):
        """One quad facing local +X. Wound explicitly: it is single-sided."""
        if y1 - y0 < 1e-4 or z1 - z0 < 1e-4:
            return
        v = [self.bm.verts.new(self.xf(x, y, z)) for (y, z) in
             ((y0, z0), (y1, z0), (y1, z1), (y0, z1))]
        f = self._face([v[0], v[3], v[2], v[1]], slot)
        self.panes.add(f)

    def finish(self, name):
        bm = self.bm
        for f in bm.faces:
            if f in self.panes:
                # window shaders map one 0-1 tile per pane; the pane may be
                # rotated by place(), so measure it along its own horizontal
                pts = [l.vert.co for l in f.loops]
                horiz = max(range(2), key=lambda i: max(p[i] for p in pts) - min(p[i] for p in pts))
                hs = [p[horiz] for p in pts]
                zs = [p.z for p in pts]
                for loop in f.loops:
                    p = loop.vert.co
                    loop[self.uv].uv = ((p[horiz] - min(hs)) / (max(hs) - min(hs)),
                                        (p.z - min(zs)) / (max(zs) - min(zs)))
                continue
            n = f.normal
            ax = max(range(3), key=lambda i: abs(n[i]))
            for loop in f.loops:
                p = loop.vert.co
                u, v = ((p.y, p.z), (p.x, p.z), (p.x, p.y))[ax]
                loop[self.uv].uv = (u * UV_PER_M, v * UV_PER_M)
        mesh = bpy.data.meshes.new(name)
        bm.to_mesh(mesh)
        bm.free()
        for s in SLOTS:
            mesh.materials.append(material(s))
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def material(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.diffuse_color = PREVIEW_COLORS[name]
    return m


# ---------------------------------------------------------------- facade pieces
# Ground floor (5.0 m): stone plinth to 0.45, shopfront glass to 3.55, stone
# fascia 3.60-4.30, brick above. Upper floors (3.0 m): sill 0.85, head 2.45,
# a stone string course at the top of each floor.

def wall_slab(b, w, h, slot="TL_Brick", y0=0.0, depth=WALL_D):
    b.box(-depth, 0.0, y0, y0 + w, 0.0, h, slot)


def wall_with_opening(b, w, h, oy0, oy1, oz0, oz1, slot="TL_Brick", reveal=0.12):
    """A slab with a rectangular opening recessed by `reveal`. The slab is made
    deep enough to give the reveal side walls."""
    depth = max(WALL_D, reveal + 0.06)
    b.box(-depth, 0.0, 0.0, oy0, 0.0, h, slot)
    b.box(-depth, 0.0, oy1, w, 0.0, h, slot)
    b.box(-depth, 0.0, oy0, oy1, 0.0, oz0, slot)
    b.box(-depth, 0.0, oy0, oy1, oz1, h, slot)
    b.box(-depth, -reveal, oy0, oy1, oz0, oz1, slot)


def window(b, oy0, oy1, oz0, oz1, reveal=0.12, mullions=1, transom=None):
    fr = 0.06
    b.pane(-reveal + 0.005, oy0 + fr, oy1 - fr, oz0 + fr, oz1 - fr)
    fx0, fx1 = -reveal, -reveal + 0.05
    b.box(fx0, fx1, oy0, oy1, oz0, oz0 + fr, "TL_Metal")
    b.box(fx0, fx1, oy0, oy1, oz1 - fr, oz1, "TL_Metal")
    b.box(fx0, fx1, oy0, oy0 + fr, oz0, oz1, "TL_Metal")
    b.box(fx0, fx1, oy1 - fr, oy1, oz0, oz1, "TL_Metal")
    for i in range(1, mullions + 1):
        y = oy0 + (oy1 - oy0) * i / (mullions + 1)
        b.box(fx0, fx1 + 0.01, y - 0.03, y + 0.03, oz0, oz1, "TL_Metal")
    if transom is not None:
        b.box(fx0, fx1 + 0.01, oy0, oy1, transom - 0.03, transom + 0.03, "TL_Metal")


def sill(b, oy0, oy1, z):
    b.box(0.0, 0.07, oy0 - 0.08, oy1 + 0.08, z - 0.08, z, "TL_Stone")


def lintel(b, oy0, oy1, z, depth=0.04, height=0.22):
    b.box(0.0, depth, oy0 - 0.12, oy1 + 0.12, z, z + height, "TL_Stone")


def string_course(b, w, z, h=0.18, proj=0.08, y0=0.0):
    b.box(0.0, proj, y0, y0 + w, z, z + h, "TL_Stone")


def ground_base(b, w, y0=0.0):
    b.box(0.0, 0.06, y0, y0 + w, 0.0, 0.45, "TL_Stone")
    b.box(0.0, 0.10, y0, y0 + w, 3.60, 4.30, "TL_Stone")
    b.box(0.0, 0.16, y0, y0 + w, 4.18, 4.30, "TL_Stone")


def frieze(b, y0, y1):
    b.box(0.0, 0.05, y0, y1, 2.55, 2.82, "TL_Stone")


# ---------------------------------------------------------------- foundation
# LV0 is the below-grade strip between the terrain and the ground floor: the
# RULE places it at the base of the building, hanging h below z = 0. It is a
# plain in-situ wall -- a slightly proud footing with chunky steps, not brick --
# and its pivot is the strip's centre, so the mesh runs over y in [-w/2, w/2].
#
# The corner pieces use the interior-corner convention (both wings on the +X
# and -Y side of the origin), which is what the borrowed NY foundation corners
# look like in their own local frame: SM_BLDG_NY_L0_A_CornerEx_01_N1 measures
# x in [-42, 0], y in [0, 40]. That is the opposite of the L1-L4 kit, so the
# corner meshes here are built flipped rather than reusing corner_ex.
FOUNDATION_D = 0.45
FOUNDATION_STEP = 0.60


def _foundation_run(b, y0, y1, h):
    """One straight run of foundation wall, y0..y1, from -h up to 0. Exterior
    face at x = 0, thickness into -x."""
    b.box(-FOUNDATION_D, 0.0, y0, y1, -h, 0.0, "TL_Stone")
    y = y0 + 0.10
    while y < y1 - 0.10:                                       # vertical joints
        b.box(0.0, 0.04, y, y + 0.06, -h + 0.40, -0.30, "TL_Stone")
        y += 0.55
    z = -h + FOUNDATION_STEP
    k = 1
    while z < -0.40:                                           # stepped footing
        b.box(0.0, 0.07 if k % 2 else 0.04, y0, y1, z - 0.12, z, "TL_Stone")
        z += FOUNDATION_STEP
        k += 1


def build_foundation(b, w, h):
    _foundation_run(b, -w / 2.0, w / 2.0, h)


def _foundation_corner(b, wing, h, interior):
    """Fill block where two foundation runs meet, sized and placed exactly like
    the NY corner pieces every sibling style uses (measured in UE:
    SM_BLDG_NY_L0_A_CornerEx_01_N1 x [-42, 0], y [0, 40];
    SM_BLDG_NY_L0_A_CornerIn_01_N1 x [-30, 10], y [-32, 10]), so the shared
    level-0 corner profile (C_E 40 cm, C_I 10 cm) keeps holding for TL."""
    if interior:
        b.box(-0.30, 0.10, -0.32, 0.10, -h, 0.0, "TL_Stone")
    else:
        b.box(-0.42, 0.0, 0.0, wing, -h, 0.0, "TL_Stone")
        b.box(0.0, 0.04, 0.0, wing, -h + 0.40, -0.30, "TL_Stone")


def build_shopfront(b, w, h):
    oy0, oy1 = 0.25, w - 0.25
    wall_with_opening(b, w, h, oy0, oy1, 0.45, 3.55, reveal=0.20)
    window(b, oy0, oy1, 0.45, 3.55, reveal=0.20, mullions=1, transom=2.75)
    b.box(-0.20, -0.02, oy0, oy1, 0.45, 0.62, "TL_Stone")          # stall riser
    ground_base(b, w)


def build_filler(b, w, h, level):
    """Plain wall that tolerates stretching along the run: horizontal trim only."""
    if level == 0:
        build_foundation(b, w, h)
        return
    if level == 4:
        cornice(b, w, h)
        return
    wall_slab(b, w, h)
    if level == 1:
        ground_base(b, w)
    else:
        string_course(b, w, h - 0.18)
        if level == 3:
            frieze(b, 0.0, w)


def build_entrance(b, w, h):
    oy0, oy1 = 0.45, w - 0.45
    rv = 0.60
    wall_with_opening(b, w, h, oy0, oy1, 0.0, 3.30, slot="TL_Stone", reveal=rv)
    mid = (oy0 + oy1) / 2.0
    b.box(-rv, -rv + 0.05, oy0, oy1, 0.0, 2.65, "TL_Metal")         # door leaf back
    b.pane(-rv + 0.06, oy0 + 0.10, mid - 0.04, 0.12, 2.55)
    b.pane(-rv + 0.06, mid + 0.04, oy1 - 0.10, 0.12, 2.55)
    b.box(-rv + 0.05, -rv + 0.10, mid - 0.04, mid + 0.04, 0.0, 2.65, "TL_Metal")
    b.box(-rv + 0.05, -rv + 0.10, oy0, oy1, 2.65, 2.75, "TL_Metal")
    b.pane(-rv + 0.06, oy0 + 0.06, oy1 - 0.06, 2.75, 3.24)          # fanlight
    b.box(0.0, 0.10, oy0 - 0.20, oy0, 0.45, 3.30, "TL_Stone")       # jambs
    b.box(0.0, 0.10, oy1, oy1 + 0.20, 0.45, 3.30, "TL_Stone")
    b.box(0.0, 0.14, oy0 - 0.20, oy1 + 0.20, 3.30, 3.55, "TL_Stone")
    b.box(0.14, 0.20, mid - 0.18, mid + 0.18, 3.20, 3.55, "TL_Stone")  # keystone
    b.box(0.16, 1.10, oy0 - 0.10, oy1 + 0.10, 3.62, 3.72, "TL_Metal")  # canopy
    ground_base(b, w)


def build_pilaster(b, w, h, level):
    if level == 4:
        cornice(b, w, h)
        b.box(0.0, 0.18, 0.20, w - 0.20, 0.48, h + 0.25, "TL_Stone")  # pier cap
        return
    wall_slab(b, w, h, "TL_Stone" if level == 1 else "TL_Brick")
    if level == 1:
        b.box(0.0, 0.18, 0.15, w - 0.15, 0.0, 3.60, "TL_Stone")
        b.box(0.0, 0.24, 0.10, w - 0.10, 0.0, 0.55, "TL_Stone")
        ground_base(b, w)
    else:
        b.box(0.0, 0.14, 0.20, w - 0.20, 0.0, h - 0.18, "TL_Brick")
        string_course(b, w, h - 0.18, proj=0.18)
        if level == 3:
            b.box(0.0, 0.20, 0.15, w - 0.15, 2.45, 2.82, "TL_Stone")


def build_thin_pilaster(b, w, h):
    wall_slab(b, w, h)
    b.box(0.0, 0.10, 0.02, w - 0.02, 0.0, h, "TL_Stone")


def build_window_bay(b, w, h, level):
    oy0, oy1 = 0.55, w - 0.55
    oz0, oz1 = 0.85, 2.45
    wall_with_opening(b, w, h, oy0, oy1, oz0, oz1)
    window(b, oy0, oy1, oz0, oz1, mullions=1, transom=2.05)
    sill(b, oy0, oy1, oz0)
    if level == 2:
        lintel(b, oy0, oy1, oz1)
    else:
        lintel(b, oy0, oy1, oz1, depth=0.06, height=0.10)
        frieze(b, 0.0, w)
    string_course(b, w, h - 0.18)


def build_feature_bay(b, w, h, level):
    """The bay above an entrance: a wide window with a stone surround."""
    oy0, oy1 = 0.40, w - 0.40
    oz0, oz1 = 0.55, (2.45 if level == 3 else 2.55)
    wall_with_opening(b, w, h, oy0, oy1, oz0, oz1)
    window(b, oy0, oy1, oz0, oz1, mullions=2, transom=(2.15 if level == 2 else None))
    b.box(0.0, 0.08, oy0 - 0.14, oy0, oz0, oz1, "TL_Stone")
    b.box(0.0, 0.08, oy1, oy1 + 0.14, oz0, oz1, "TL_Stone")
    b.box(0.0, 0.12, oy0 - 0.20, oy1 + 0.20, oz0 - 0.12, oz0, "TL_Stone")
    if level == 2:
        b.box(0.0, 0.10, oy0 - 0.20, oy1 + 0.20, oz1, oz1 + 0.25, "TL_Stone")
        b.box(0.05, 0.40, oy0, oy1, oz0 - 0.10, oz0, "TL_Stone")     # balcony slab
        for i in range(9):
            y = oy0 + 0.05 + i * (oy1 - oy0 - 0.10) / 8.0
            b.box(0.33, 0.37, y - 0.015, y + 0.015, oz0, oz0 + 0.95, "TL_Metal")
        b.box(0.32, 0.38, oy0, oy1, oz0 + 0.92, oz0 + 0.98, "TL_Metal")
    else:
        b.box(0.0, 0.10, oy0 - 0.20, oy1 + 0.20, oz1, oz1 + 0.10, "TL_Stone")
        frieze(b, 0.0, oy0 - 0.20)
        frieze(b, oy1 + 0.20, w)
    string_course(b, w, h - 0.18)


# ---------------------------------------------------------------- cornice

CORNICE_TIERS = ((0.00, 0.15, 0.08),    # (z0, z1, projection): fascia
                 (0.28, 0.46, 0.34))    # corona
DENTIL = (0.15, 0.28, 0.18)              # z0, z1, projection


def cornice(b, w, h, y0=0.0, y1=None):
    """Stone cornice at the base of the topper, brick parapet, stone coping."""
    y1 = w if y1 is None else y1
    b.box(-WALL_D, 0.0, y0, y1, 0.0, h - 0.12, "TL_Brick")
    for z0, z1, p in CORNICE_TIERS:
        b.box(0.0, p, y0, y1, z0, z1, "TL_Stone")
    b.box(0.0, 0.06, y0, y1, DENTIL[0], DENTIL[1], "TL_Stone")
    k = 0
    y = y0 + 0.08
    while y + 0.14 <= y1 - 0.02:
        b.box(0.06, DENTIL[2], y, y + 0.14, DENTIL[0], DENTIL[1], "TL_Stone")
        y += 0.30
        k += 1
    b.box(-WALL_D - 0.04, 0.06, y0, y1, h - 0.12, h, "TL_Stone")


def cornice_wing_b(b, wing, h, exterior):
    """The cornice on the second wing of a corner. `exterior` True: wing along
    -X with its outer face at y = 0 (exterior corner); False: wing along +X
    with its outer face at y = 0 facing +Y (interior corner)."""
    if exterior:
        xs, sgn = (-wing, 0.0), -1.0
        slab = (0.0, WALL_D)
    else:
        xs, sgn = (0.0, wing), 1.0
        slab = (-WALL_D, 0.0)
    b.box(xs[0], xs[1], slab[0], slab[1], 0.0, h - 0.12, "TL_Brick")
    for z0, z1, p in CORNICE_TIERS + ((DENTIL[0], DENTIL[1], 0.06),):
        y0, y1 = sorted((0.0, sgn * p))
        b.box(xs[0], xs[1], y0, y1, z0, z1, "TL_Stone")
    y0, y1 = sorted((sgn * -(WALL_D + 0.04), sgn * 0.06))
    b.box(xs[0], xs[1], y0, y1, h - 0.12, h, "TL_Stone")
    if exterior:
        # fill the outside corner square for each tier and the coping
        for z0, z1, p in CORNICE_TIERS + ((DENTIL[0], DENTIL[1], 0.06),):
            b.box(0.0, p, -p, 0.0, z0, z1, "TL_Stone")
        b.box(0.0, 0.06, -0.06, 0.0, h - 0.12, h, "TL_Stone")


# ---------------------------------------------------------------- corners

def corner_ex(b, wing, h, level):
    if level == 0:
        _foundation_corner(b, wing, h, interior=False)
        return
    if level == 4:
        cornice(b, wing, h)
        cornice_wing_b(b, wing, h, exterior=True)
        return
    slot = "TL_Stone" if level == 1 else "TL_Brick"
    b.box(-WALL_D, 0.0, 0.0, wing, 0.0, h, slot)                   # wing A
    b.box(-wing, 0.0, 0.0, WALL_D, 0.0, h, slot)                   # wing B
    top = 3.60 if level == 1 else h - 0.18
    step = 0.30
    i = 0
    z = 0.45 if level == 1 else 0.0
    while z + step <= top + 1e-6:                                  # quoins
        long, short = (0.60, 0.35) if i % 2 == 0 else (0.35, 0.60)
        b.box(0.0, 0.05, -0.05, long, z, z + step - 0.02, "TL_Stone")
        b.box(-short, 0.0, -0.05, 0.0, z, z + step - 0.02, "TL_Stone")
        z += step
        i += 1
    if level == 1:
        ground_base(b, wing)
        for z0, z1, p in ((0.0, 0.45, 0.06), (3.60, 4.30, 0.10), (4.18, 4.30, 0.16)):
            b.box(-wing, 0.0, -p, 0.0, z0, z1, "TL_Stone")
            b.box(0.0, p, -p, 0.0, z0, z1, "TL_Stone")
    else:
        string_course(b, wing, h - 0.18)
        b.box(-wing, 0.08, -0.08, 0.0, h - 0.18, h, "TL_Stone")
        if level == 3:
            frieze(b, 0.0, wing)
            b.box(-wing, 0.05, -0.05, 0.0, 2.55, 2.82, "TL_Stone")


def corner_in(b, wing, h, level):
    if level == 0:
        _foundation_corner(b, wing, h, interior=True)
        return
    if level == 4:
        cornice(b, wing, h)
        cornice_wing_b(b, wing, h, exterior=False)
        return
    slot = "TL_Stone" if level == 1 else "TL_Brick"
    b.box(-WALL_D, 0.0, -WALL_D, wing, 0.0, h, slot)               # wing A
    b.box(0.0, wing, -WALL_D, 0.0, 0.0, h, slot)                   # wing B
    if level == 1:
        ground_base(b, wing)
        for z0, z1, p in ((0.0, 0.45, 0.06), (3.60, 4.30, 0.10), (4.18, 4.30, 0.16)):
            b.box(0.0, wing, 0.0, p, z0, z1, "TL_Stone")
    else:
        string_course(b, wing, h - 0.18)
        b.box(0.0, wing, 0.0, 0.08, h - 0.18, h, "TL_Stone")
        if level == 3:
            frieze(b, 0.0, wing)
            b.box(0.0, wing, 0.0, 0.05, 2.55, 2.82, "TL_Stone")


def corner_half(b, wing, h, level, part):
    """Half of an exterior or interior corner: the corner itself plus one 45 cm
    wall stub, sized so that one 90-degree wall turn placed at the corner point
    covers the missing half. The BDF route places the whole corner piece (C_E /
    C_I) at every building corner and never asks for these; the SGD route has no
    corner support and leaves the turn open, so an L-shaped building uses these
    instead (see tl_make_sgd.py)."""
    if part in ("CornerExL_01", "CornerExR_01"):
        corner_ex(b, HALF_STUB, h, level)
        if part == "CornerExR_01":                             # R: run, then stub
            b.mirror(wing)
        build_filler(b, wing, h, level)
        b.mirror(None)
        return
    # The interior corner's second wing runs along +X, which is not the wall
    # direction, so both halves are the same straight run with the corner at one
    # end; the mirror only decides which end that is.
    corner_in(b, HALF_STUB, h, level)
    if part == "CornerInR_01":
        b.mirror(wing)
    build_filler(b, wing, h, level)
    b.mirror(None)


BUILDERS = {
    "foundation": lambda b, p: build_foundation(b, p["width_m"], p["height_m"]),
    "foundation_corner": lambda b, p: (corner_ex if p["part"] == "CornerEx_01"
                                       else corner_in)(b, p["width_m"], p["height_m"], 0),
    "shopfront": lambda b, p: build_shopfront(b, p["width_m"], p["height_m"]),
    "filler": lambda b, p: build_filler(b, p["width_m"], p["height_m"], p["level"]),
    "entrance": lambda b, p: build_entrance(b, p["width_m"], p["height_m"]),
    "pilaster": lambda b, p: build_pilaster(b, p["width_m"], p["height_m"], p["level"]),
    "pilaster_thin": lambda b, p: build_thin_pilaster(b, p["width_m"], p["height_m"]),
    "window": lambda b, p: build_window_bay(b, p["width_m"], p["height_m"], p["level"]),
    "window_top": lambda b, p: build_window_bay(b, p["width_m"], p["height_m"], p["level"]),
    "feature_window": lambda b, p: build_feature_bay(b, p["width_m"], p["height_m"], p["level"]),
    "feature_window_top": lambda b, p: build_feature_bay(b, p["width_m"], p["height_m"], p["level"]),
    "cornice": lambda b, p: cornice(b, p["width_m"], p["height_m"]),
    "cornice_pier": lambda b, p: build_pilaster(b, p["width_m"], p["height_m"], 4),
    "corner_ex": lambda b, p: corner_ex(b, p["width_m"], p["height_m"], p["level"]),
    "cornice_corner_ex": lambda b, p: corner_ex(b, p["width_m"], p["height_m"], 4),
    "corner_in": lambda b, p: corner_in(b, p["width_m"], p["height_m"], p["level"]),
    "cornice_corner_in": lambda b, p: corner_in(b, p["width_m"], p["height_m"], 4),
    "corner_half": lambda b, p: corner_half(b, p["width_m"], p["height_m"], p["level"], p["part"]),
    "cornice_half": lambda b, p: corner_half(b, p["width_m"], p["height_m"], 4, p["part"]),
}


def build_into(b, part):
    fn = BUILDERS.get(part["kind"])
    if fn is None:
        raise SystemExit("unknown part kind %r for %s" % (part["kind"], part["mesh_name"]))
    fn(b, part)


def build_part(part):
    b = Builder()
    build_into(b, part)
    return b.finish(part["mesh_name"])


# ---------------------------------------------------------------- preview

def preview(spec, out_dir):
    """One building corner per the F1 grammar: facade A leaves an exterior
    corner along +Y, facade B arrives along +X; storeys L1, L2, L2, L3, L4."""
    by = {(p["level"], kit_common.PART_TO_SYMBOL[p["part"]]): p for p in spec["parts"]}
    seq = [t for t in kit_common.GRAMMAR_F1.replace("]+", "]").replace("[", " ")
           .replace("]", " ").replace(",", " ").split() if t not in ("FC", "LC")]
    storeys = [1, 2, 2, 3, 4]
    b = Builder()
    z = 0.0
    for lv in storeys:
        h = spec["levels"][str(lv)]["height_m"]
        syms = [s if (lv, s) in by else "W1" for s in seq]
        syms = ["W1" if (lv == 4 and s == "E1") else s for s in syms]
        if (lv, "WS1") not in by:
            syms = ["W1" if s == "WS1" else s for s in syms]
        corner = by[(lv, "C_CE")]
        b.place(0.0, 0.0, z, 0)
        build_into(b, corner)
        y = corner["width_m"]
        for s in syms:                                             # facade A
            p = by[(lv, s)]
            b.place(0.0, y, z, 0)
            build_into(b, p)
            y += p["width_m"]
        x = -corner["width_m"]
        for s in reversed(syms):                                   # facade B
            p = by[(lv, s)]
            x -= p["width_m"]
            b.place(x, 0.0, z, -90)
            build_into(b, p)
        z += h
    b.finish("TL_preview")
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.display.shading.show_shadows = True
    scene.render.resolution_x, scene.render.resolution_y = 1800, 1100
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    target = (-7.0, -7.0, 6.0)            # Blender coords (y flipped)
    cam.location = (19.0, 19.0, 11.0)
    d = [target[i] - cam.location[i] for i in range(3)]
    yaw = math.atan2(d[1], d[0]) - math.pi / 2
    pitch = math.atan2(d[2], math.hypot(d[0], d[1]))
    cam.rotation_euler = (math.pi / 2 + pitch, 0.0, yaw)
    cam.data.lens = 28
    path = os.path.join(out_dir, "TL_Kit_preview.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def export(obj, out_dir, name):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path = os.path.join(out_dir, name + ".fbx")
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, global_scale=1.0, apply_unit_scale=True,
        axis_forward="-Y", axis_up="Z", object_types={"MESH"}, mesh_smooth_type="FACE")
    return path


def ue_bounds(obj):
    xs, ys, zs = zip(*[v.co for v in obj.data.vertices])
    return ((round(min(xs), 3), round(-max(ys), 3), round(min(zs), 3)),
            (round(max(xs), 3), round(-min(ys), 3), round(max(zs), 3)))


def glass_facing(obj):
    """Glass faces whose normal does not point to UE +X (Blender +X)."""
    gi = SLOTS.index("TL_Glass")
    bad = [p for p in obj.data.polygons if p.material_index == gi and p.normal.x < 0.5]
    return len([p for p in obj.data.polygons if p.material_index == gi]), len(bad)


def main():
    args = parse_args()
    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    if len(spec["parts"]) != kit_common.EXPECTED_PART_COUNT:
        raise SystemExit("tl_kit_spec.json has %d parts, expected %d"
                         % (len(spec["parts"]), kit_common.EXPECTED_PART_COUNT))
    if spec.get("lods") != kit_common.LODS_PRODUCED:
        raise SystemExit("tl_kit_spec.json declares lods=%r, this script builds %r"
                         % (spec.get("lods"), kit_common.LODS_PRODUCED))
    fb_dir = os.path.join(args.out, "FBX_Export")
    os.makedirs(fb_dir, exist_ok=True)
    report = []
    for part in spec["parts"]:
        clear_scene()
        obj = build_part(part)
        glass, glass_bad = glass_facing(obj)
        report.append({"name": part["mesh_name"], "verts": len(obj.data.vertices),
                       "faces": len(obj.data.polygons),
                       "slots_used": sorted({SLOTS[p.material_index] for p in obj.data.polygons}),
                       "glass_faces": glass, "glass_facing_wrong": glass_bad,
                       "ue_bounds_m": ue_bounds(obj)})
        export(obj, fb_dir, part["mesh_name"])
    clear_scene()
    x = 0.0
    for part in spec["parts"]:
        b = Builder()
        b.place(0.0, x, 0.0, 0)
        build_into(b, part)
        b.finish(part["mesh_name"])
        x += part["width_m"] + 1.0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(args.out, "TL_Kit.blend"))
    if args.preview:
        clear_scene()
        print("###PREVIEW###", preview(spec, args.out))
    print("###EXPORTED###", len(report))
    print("###REPORT###" + json.dumps(report))


main()
