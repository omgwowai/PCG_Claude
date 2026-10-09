"""render_kit_catalog.py -- Blender 5.2 headless. One Workbench thumbnail per
TL kit part, plus one "exploded" storey row per level, for the build-up
document (docs/tl-building-guide.html).

    blender -b --factory-startup -P Tools/tl_kit/render_kit_catalog.py -- \
        --spec Tools/tl_kit/tl_kit_spec.json --out Saved/kit_catalog

Reuses build_tl_kit.py's builders (geometry is identical to the exported FBX),
so it is imported as a module: its main() only runs when it is the script
Blender was started with.
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

# build_tl_kit.main() runs at import; neutralise it by pretending to be imported
_argv = sys.argv
sys.argv = [sys.argv[0]]
import importlib.util
_spec = importlib.util.spec_from_file_location("tlkit", os.path.join(HERE, "build_tl_kit.py"))
tlkit = importlib.util.module_from_spec(_spec)
_src = open(os.path.join(HERE, "build_tl_kit.py"), encoding="utf-8").read()
_src = _src.replace("\nmain()\n", "\n")
exec(compile(_src, "build_tl_kit.py", "exec"), tlkit.__dict__)
sys.argv = _argv


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def setup_scene(res=(520, 520)):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.show_shadows = False
    scene.display.shading.show_object_outline = True
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("w") if not bpy.data.worlds else bpy.data.worlds[0]
    scene.world = world
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (0.94, 0.95, 0.97)
    return scene


def frame_camera(scene, objs, view=(1.0, -1.0, 0.55), lens=50, margin=1.15):
    pts = []
    for o in objs:
        pts += [o.matrix_world @ mathutils.Vector(c) for c in o.bound_box]
    lo = mathutils.Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = mathutils.Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    centre = (lo + hi) / 2
    radius = (hi - lo).length / 2 * margin
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = lens
    d = mathutils.Vector(view).normalized()
    fov = 2 * math.atan(18.0 / lens)
    dist = radius / math.sin(fov / 2)
    cam.location = centre + d * dist
    look = (centre - cam.location).normalized()
    cam.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()
    return cam


def render(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def part_thumb(part, out_dir):
    tlkit.clear_scene()
    scene = setup_scene()
    obj = tlkit.build_part(part)
    # Blender-frame: the facade (UE +X) faces Blender +X, the run is Blender -Y.
    # View the facade from front-right-above.
    frame_camera(scene, [obj], view=(1.0, -0.55, 0.42))
    path = os.path.join(out_dir, "part_%s.png" % part["mesh_name"])
    render(path)
    return path


def level_row(spec, level, out_dir):
    """All of one level's parts side by side, labelled by order in the spec."""
    tlkit.clear_scene()
    scene = setup_scene(res=(1400, 420))
    parts = [p for p in spec["parts"] if p["level"] == level]
    objs = []
    y = 0.0
    for p in parts:
        b = tlkit.Builder()
        w = p["width_m"]
        # corner pieces stick out along -X; give them room
        b.place(0.0, y + (1.6 if "orner" in p["part"] else 0.0), 0.0, 0)
        tlkit.build_into(b, p)
        objs.append(b.finish(p["mesh_name"]))
        y += w + 2.2 + (1.6 if "orner" in p["part"] else 0.0)
    frame_camera(scene, objs, view=(1.0, -0.25, 0.30), lens=45, margin=1.02)
    path = os.path.join(out_dir, "level_L%02d.png" % level)
    render(path)
    return path, [p["part"] for p in parts]


def main():
    args = parse_args()
    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    os.makedirs(args.out, exist_ok=True)
    out = {"parts": [], "levels": {}}
    for p in spec["parts"]:
        out["parts"].append(part_thumb(p, args.out))
    for lv in sorted({p["level"] for p in spec["parts"]}):
        path, order = level_row(spec, lv, args.out)
        out["levels"][lv] = {"path": path, "order": order}
    print("###CATALOG###" + json.dumps(out))


main()
