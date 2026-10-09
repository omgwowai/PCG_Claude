"""render_elevation.py -- Blender 5.2 headless. A front elevation of one TL
facade (F1 grammar, one repeat of each "+") for every storey L0..L4, rendered
orthographic, plus a JSON of each module's pixel box and grammar symbol so the
document can label it. Also an axonometric of the same stack with the next
facade turning the corner.

    blender -b --factory-startup -P Tools/tl_kit/render_elevation.py -- \
        --spec Tools/tl_kit/tl_kit_spec.json --out Saved/kit_catalog
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bpy
import mathutils
from bpy_extras.object_utils import world_to_camera_view

_src = open(os.path.join(HERE, "build_tl_kit.py"), encoding="utf-8").read().replace("\nmain()\n", "\n")
tlkit = type(sys)("tlkit")
tlkit.__dict__["__file__"] = os.path.join(HERE, "build_tl_kit.py")
exec(compile(_src, "build_tl_kit.py", "exec"), tlkit.__dict__)
kit_common = tlkit.kit_common


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def tokens(grammar):
    """F1 with each '+' taken once, corner tokens dropped, [A,B] flattened."""
    g = grammar.replace("]+", "]")
    return [t for t in g.replace("[", " ").replace("]", " ").replace(",", " ").split()
            if t not in ("FC", "LC")]


def shading(scene):
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.show_object_outline = True
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (0.97, 0.97, 0.98)


def build_stack(spec, b, with_side=False):
    """Lay out L0..L4 of one facade; returns per-module records (UE metres)."""
    by = {(p["level"], kit_common.PART_TO_SYMBOL[p["part"]]): p for p in spec["parts"]}
    seq = tokens(kit_common.GRAMMAR_F1)
    corner_w = by[(1, "C_CE")]["width_m"]
    run = sum(by[(1, s)]["width_m"] for s in seq)
    total = corner_w * 2 + run
    recs = []
    z = 0.0
    for lv in (1, 2, 3, 4):
        h = spec["levels"][str(lv)]["height_m"]
        syms = ["W1" if (lv == 4 and s == "E1") else s for s in seq]
        if (lv, "WS1") not in by:
            syms = ["W1" if s == "WS1" else s for s in syms]
        # first corner (FC) at y=0, last corner (LC) at y=total, turned 90
        b.place(0.0, 0.0, z, 0)
        tlkit.build_into(b, by[(lv, "C_CE")])
        recs.append({"lv": lv, "sym": "C_CE", "y0": 0.0, "y1": corner_w, "z0": z, "z1": z + h})
        y = corner_w
        for s in syms:
            p = by[(lv, s)]
            b.place(0.0, y, z, 0)
            tlkit.build_into(b, p)
            recs.append({"lv": lv, "sym": s, "y0": y, "y1": y + p["width_m"], "z0": z, "z1": z + h})
            y += p["width_m"]
        b.place(0.0, total, z, 90)
        tlkit.build_into(b, by[(lv, "C_CE")])
        recs.append({"lv": lv, "sym": "C_CE", "y0": total - corner_w, "y1": total, "z0": z, "z1": z + h})
        if with_side:
            x = -corner_w
            for s in reversed(syms):
                p = by[(lv, s)]
                x -= p["width_m"]
                b.place(x, 0.0, z, -90)
                tlkit.build_into(b, p)
        z += h
    # L0: foundation strip below grade along the same run
    fs = by[(0, "FS2")]
    n = int(math.ceil(total / fs["width_m"]))
    k = total / (n * fs["width_m"])
    for i in range(n):
        yc = (i + 0.5) * fs["width_m"] * k
        b.place(0.0, yc, 0.0, 0)
        b.mirror(None)
        tlkit.build_into(b, dict(fs, width_m=fs["width_m"] * k))
    recs.append({"lv": 0, "sym": "FS2 ×%d" % n, "y0": 0.0, "y1": total,
                 "z0": -spec["levels"]["0"]["height_m"], "z1": 0.0})
    return recs, total, z


def elevation(spec, out_dir):
    tlkit.clear_scene()
    scene = bpy.context.scene
    shading(scene)
    b = tlkit.Builder()
    recs, total, top = build_stack(spec, b)
    obj = b.finish("elevation")
    bottom = -spec["levels"]["0"]["height_m"]
    pad = 0.8
    w_m, h_m = total + 2 * pad, (top - bottom) + 2 * pad
    ppm = 52
    scene.render.resolution_x, scene.render.resolution_y = int(w_m * ppm), int(h_m * ppm)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(w_m, h_m)
    # Blender frame: facade faces +X, UE +Y is Blender -Y
    cam.location = (40.0, -total / 2.0, (top + bottom) / 2.0)
    cam.rotation_euler = mathutils.Vector((-1.0, 0.0, 0.0)).to_track_quat("-Z", "Y").to_euler()
    path = os.path.join(out_dir, "elevation_F1.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    for r in recs:
        pts = []
        for yy in (r["y0"], r["y1"]):
            for zz in (r["z0"], r["z1"]):
                c = world_to_camera_view(scene, cam, mathutils.Vector((0.3, -yy, zz)))
                pts.append((c.x * rx, (1 - c.y) * ry))
        r["px"] = [min(p[0] for p in pts), min(p[1] for p in pts),
                   max(p[0] for p in pts), max(p[1] for p in pts)]
    with open(os.path.join(out_dir, "elevation_F1.json"), "w", encoding="utf-8") as f:
        json.dump({"size": [rx, ry], "modules": recs, "total_m": total}, f, indent=1)
    return path


def axo(spec, out_dir):
    tlkit.clear_scene()
    scene = bpy.context.scene
    shading(scene)
    scene.display.shading.show_shadows = True
    b = tlkit.Builder()
    recs, total, top = build_stack(spec, b, with_side=True)
    b.finish("axo")
    scene.render.resolution_x, scene.render.resolution_y = 1800, 1150
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 32
    target = mathutils.Vector((-6.0, -12.0, 6.0))
    cam.location = mathutils.Vector((30.0, 8.0, 17.0))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    path = os.path.join(out_dir, "axo_stack.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def main():
    args = parse_args()
    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    os.makedirs(args.out, exist_ok=True)
    print("###ELEV###", elevation(spec, args.out))
    print("###AXO###", axo(spec, args.out))


main()
