"""build_tl_kit.py -- Blender 5.2 headless. Builds the TL modular kit from the spec.

    blender -b -P Tools/tl_kit/build_tl_kit.py -- --spec Tools/tl_kit/tl_kit_spec.json \
            --out E:/Blender/TL_Kit

Each part becomes ONE object with a CORNER/BASE pivot -- this matches CHA's
measured convention (Tools/tl_kit/tl_facts.json, Task 1), not a "centre"
pivot the original plan brief described. The object's local origin (0,0,0)
sits at the BOTTOM of the piece in Z and at ONE END of the wall run in Y:

    x in [-depth/2, depth/2]   (facade depth/thickness axis)
    y in [-width_m, 0]         (the wall run; origin at the y=0 end)
    z in [0, height_m]         (up; origin at the bottom)

This is exactly CHA's measured L1 wall footprint pattern (y in [-325, 0],
z in [0, 500], origin at (0,0,0)), scaled to each part's own width/height.
CHA compensates with a per-module PivotOffset of (0, +width/2, -height/2)
(magnitude confirmed, sign unconfirmed -- see tl_facts.json); TL relies on
the same external compensation being applied downstream, unchanged.

Blender is Z-up and UE is Z-up, so no axis flip is needed in-engine; the FBX
exporter's own axis settings are set explicitly below (see the real,
version-probed keyword arguments in export()) so the exported file's stated
up/forward axes are unambiguous for the importer.

A single LOD is shipped (no LOD1 mesh is generated): the plan brief's
`build_part(part, lod)` carried a `lod` parameter whose two branches
produced IDENTICAL geometry (a vestigial `segs = 1 if lod == 0 else 1`) and
only renamed the object with a "_LOD1" suffix without changing the mesh.
Shipping that as if it were a real LOD1 would be actively misleading, so the
parameter has been dropped entirely and this script generates LOD0 only.
"""
import argparse
import json
import os
import sys

# kit_common has no bpy dependency (it's shared with test_kit_spec.py, which
# runs outside Blender), but running this file via `blender -b -P script.py`
# doesn't reliably put the script's own directory on sys.path the way a
# normal `python script.py` invocation does, so add it explicitly before
# importing.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_common

import bpy


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    return ap.parse_args(argv)


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def material(name):
    """One flat placeholder material per spec entry; real texturing is out of scope."""
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.62, 0.60, 0.56, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.7
    return m


def build_part(part):
    """A box for the part's footprint and height, origin at the BASE CORNER.

    PIVOT (measured from CHA by Task 1 -- do not "improve" this to centre):
    the box is centred in X (the facade depth axis), extends in NEGATIVE Y
    (the wall run) from the origin, and upward in Z from the origin. So the
    origin sits at (x-centre, y = near end of the run, z = bottom) -- CHA's
    L1 wall spans exactly y in [-325, 0] and z in [0, 500] with its origin
    at (0,0,0). CHA compensates with a per-module PivotOffset of half-width
    and half-height; TL matches CHA so the same compensation applies
    unchanged downstream.
    """
    w, h = part["width_m"], part["height_m"]
    depth = 0.30  # facade thickness; the grammar only uses width and height
    # place so that after scaling the box spans x:[-d/2,d/2] y:[-w,0] z:[0,h]
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0.0, -w / 2.0, h / 2.0))
    obj = bpy.context.active_object
    obj.name = part["mesh_name"]
    obj.scale = (depth / 2.0, w / 2.0, h / 2.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # origin to the WORLD origin, which is the base corner of the box above
    bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    obj.data.materials.append(material(part["material"]))
    return obj


def export(obj, out_dir, name):
    """Export `obj` as its own FBX.

    The keyword arguments below were verified against THIS Blender build
    (5.2.1 LTS) at runtime via
    `bpy.ops.export_scene.fbx.get_rna_type().properties` (see
    Tools/tl_kit/_probe_fbx_export.py / _probe_fbx_enums.py, run once as a
    throwaway headless probe) rather than written from memory, per the
    coordinator's instruction that the FBX exporter's arguments have moved
    across Blender versions. Every keyword used here (use_selection,
    global_scale, apply_unit_scale, axis_forward, axis_up, object_types)
    exists on this build's operator with the exact identifiers below, and
    "-Y"/"Z" and {"MESH"} are valid enum values for axis_forward/axis_up/
    object_types respectively -- confirmed, not assumed.
    """
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path = os.path.join(out_dir, name + ".fbx")
    bpy.ops.export_scene.fbx(
        filepath=path,
        use_selection=True,
        global_scale=1.0,
        apply_unit_scale=True,
        axis_forward="-Y",
        axis_up="Z",
        object_types={"MESH"},
    )
    return path


def main():
    args = parse_args()
    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)

    # Fail loudly on a truncated or malformed spec instead of silently
    # exporting a partial kit and printing "###EXPORTED### N" as if N were
    # the intended count. This is the same silent-partial-kit failure mode
    # the "lods" mismatch below guards against, just at the parts level.
    part_count = len(spec["parts"])
    if part_count != kit_common.EXPECTED_PART_COUNT:
        raise SystemExit(
            f"tl_kit_spec.json has {part_count} parts, expected "
            f"{kit_common.EXPECTED_PART_COUNT}. Refusing to build a "
            f"partial/oversized kit -- fix the spec (or kit_common."
            f"EXPECTED_PART_COUNT if the kit's shape has genuinely changed)."
        )

    # Guard the "lods" field against drifting from what this script actually
    # builds. build_tl_kit.py only ever produces kit_common.LODS_PRODUCED;
    # if the spec advertises more (or different) LODs than that, a
    # downstream consumer (e.g. the Task 3 importer) could go looking for
    # FBX files that were never exported.
    declared_lods = spec.get("lods")
    if declared_lods != kit_common.LODS_PRODUCED:
        raise SystemExit(
            f"tl_kit_spec.json declares lods={declared_lods!r}, but this "
            f"script only builds/exports lods={kit_common.LODS_PRODUCED!r}. "
            f"Update tl_kit_spec.json's \"lods\" field (or this script, if "
            f"more LODs are now genuinely authored) so the two agree."
        )

    fb_dir = os.path.join(args.out, "FBX_Export")
    os.makedirs(fb_dir, exist_ok=True)

    made = []
    dims = []
    pivots = []
    for part in spec["parts"]:
        clear_scene()
        obj = build_part(part)
        # dimensions are read post-transform_apply, so this is the true
        # exported bounding box in Blender units (meters)
        dims.append((part["mesh_name"], tuple(round(v, 4) for v in obj.dimensions)))
        # bound_box is in OBJECT-LOCAL space; since origin_set(ORIGIN_CURSOR)
        # just baked the object's origin into (0,0,0) of its own mesh data,
        # this local bbox is exactly what CHA's measured origin/bounds_min/
        # bounds_max facts describe -- report it per part so the pivot claim
        # is checked for every part, not just spot-checked.
        bbox = [tuple(c) for c in obj.bound_box]
        xs, ys, zs = zip(*bbox)
        pivots.append((
            part["mesh_name"],
            (round(min(xs), 4), round(min(ys), 4), round(min(zs), 4)),
            (round(max(xs), 4), round(max(ys), 4), round(max(zs), 4)),
        ))
        made.append(export(obj, fb_dir, part["mesh_name"]))
    # save the working file for hand edits (last part's object only --
    # clear_scene() wipes the prior part before each new one is built, by
    # design, so this .blend is a template/reference for the pattern, not an
    # archive of all 29 objects)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(args.out, "TL_Kit.blend"))
    print("###EXPORTED###", len(made))
    for p in made:
        print("  ", p)
    print("###DIMENSIONS_M###")
    for name, d in dims:
        print("  ", name, d)
    print("###PIVOT_BOUNDS_M###  (mesh-local bounds_min, bounds_max; origin is always (0,0,0))")
    for name, bmin, bmax in pivots:
        print("  ", name, "min=", bmin, "max=", bmax)


main()
