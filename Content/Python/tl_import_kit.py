# tl_import_kit.py -- import the TL FBX kit into /Game/Building/TL.
#
# Legacy FBX import only. Interchange crashes the editor from Python on this
# engine (TaskGraph RecursionGuard assert), so the project disables it by
# cvar in Config/DefaultEngine.ini under [ConsoleVariables]:
#     Interchange.FeatureFlags.Import.FBX=False
# That entry was added and the editor restarted (Task 3 Step 2) before this
# script was ever run against a real FBX -- verified live via
# SystemLibrary.get_console_variable_int_value(...) == 0 post-restart.
#
# Two things are asserted rather than assumed, because both fail silently:
#   * imported bounds match the spec in CENTIMETERS (catches a 100x scale
#     error from global_scale/apply_unit_scale double-applying)
#   * the material slot is not WorldGridMaterial (catches the
#     TArray<struct>-copy trap: iterating static_materials and mutating an
#     element in place is a silent no-op)
#
# AXIS NOTE (measured live, corrects the plan brief's draft script): a single
# test import of SM_BLDG_TL_L01_A_Wall_01_N1 (spec: width_m=3.25, height_m=5.0,
# depth=0.30 fixed) came back with box_extent = (15.0, 162.5, 250.0) cm and
# box_origin = (0.0, 162.5, 250.0) cm. That means:
#   X = depth (half of 30cm = 15.0)      -- NOT width
#   Y = width (half of 325cm = 162.5)    -- matches tl_kit_spec.json's stated
#                                            "y in [-width, 0]" convention
#   Z = height (half of 500cm = 250.0)
# The brief's draft script asserted width against ext.x*2; that would have
# checked the depth (always 30cm) against each part's width and failed (or
# passed by accident only when width_m happened to equal 0.30, never in this
# kit). This script checks ext.y*2 against width_m*100, as the measured data
# requires.

import json
import os

R = {"imported": [], "errors": []}
args = mcp_args or {}

SPEC_PATH = args.get("spec", "E:/PCG_Claude/Tools/tl_kit/tl_kit_spec.json")
FBX_DIR = args.get("fbx_dir", "E:/Blender/TL_Kit/FBX_Export")
DEST = "/Game/Building/TL/A"

with open(SPEC_PATH, encoding="utf-8") as f:
    spec = json.load(f)

EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()


def dest_folder(part):
    return "%s/Kit_Bldg_TL_L%d_A" % (DEST, part["level"])


for part in spec["parts"]:
    name = part["mesh_name"]
    fbx = os.path.join(FBX_DIR, name + ".fbx")
    folder = dest_folder(part)
    rec = {"name": name, "folder": folder}
    if not os.path.isfile(fbx):
        rec["error"] = "missing fbx"
        R["errors"].append(rec)
        continue

    task = unreal.AssetImportTask()
    task.set_editor_property("filename", fbx)
    task.set_editor_property("destination_path", folder + "/Mesh")
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    # legacy FBX factory explicitly, so Interchange is never in the path
    task.set_editor_property("factory", unreal.FbxFactory())
    try:
        AT.import_asset_tasks([task])
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
        R["errors"].append(rec)
        continue

    # ---- verify the scale, in cm ----------------------------------------
    mesh_path = "%s/Mesh/%s" % (folder, name)
    mesh = EAL.load_asset(mesh_path)
    if mesh is None:
        rec["error"] = "not loadable at %s" % mesh_path
        R["errors"].append(rec)
        continue
    try:
        b = mesh.get_bounds()
        ext = b.get_editor_property("box_extent")
        origin = b.get_editor_property("origin")
        rec["extent_cm"] = [round(ext.x, 2), round(ext.y, 2), round(ext.z, 2)]
        rec["origin_cm"] = [round(origin.x, 2), round(origin.y, 2), round(origin.z, 2)]
        # width is the Y extent (measured live; see module docstring). The
        # mesh spans y in [-width, 0], so box_extent.y == width/2.
        want_w = part["width_m"] * 100.0
        got_w = round(ext.y * 2.0, 1)
        rec["want_width_cm"] = want_w
        rec["got_width_cm"] = got_w
        rec["scale_ok"] = abs(got_w - want_w) < 2.0
        if not rec["scale_ok"]:
            rec["error"] = "width %s != %s" % (got_w, want_w)
            R["errors"].append(rec)

        # ---- pivot check: origin at the BASE, not the centre -------------
        # A corner-base pivot means the bounds centre (origin) sits at
        # z = +extent.z above the mesh's local z=0 (the base), not at z ~ 0.
        want_h = part["height_m"] * 100.0
        got_h = round(ext.z * 2.0, 1)
        rec["want_height_cm"] = want_h
        rec["got_height_cm"] = got_h
        rec["height_ok"] = abs(got_h - want_h) < 2.0
        rec["pivot_ok"] = abs(origin.z - ext.z) < 1.0
        if not rec["pivot_ok"]:
            rec.setdefault("error", "pivot not at base: origin.z=%s extent.z=%s" % (origin.z, ext.z))
            R["errors"].append(rec)
    except Exception as e:
        rec["bounds_err"] = "%s: %s" % (type(e).__name__, e)

    # ---- verify the material slot is real --------------------------------
    try:
        mats = mesh.get_editor_property("static_materials")
        rec["slot_count"] = len(mats)
        rec["slot0"] = str(mats[0].get_editor_property("material_interface")) if mats else None
        rec["slot_ok"] = bool(mats) and "WorldGrid" not in str(rec["slot0"])
    except Exception as e:
        rec["slot_err"] = "%s: %s" % (type(e).__name__, e)

    R["imported"].append(rec)

# ---------- material slot assignment (the TArray<struct> trap) -------------
# static_materials yields struct COPIES: mutating an element in place silently
# does nothing. Build a fresh list and set it whole, then read it back.
MI_ROOT = "/Game/Building/Material"
TL_MATERIAL_PATH = MI_ROOT + "/MI_Bldg_Stone_TL"
FALLBACK_MATERIAL_PATH = "/Game/Building/CH/A/Material/MI_Bldg_Block_Limestone_Beige"

tl_material_exists = EAL.does_asset_exist(TL_MATERIAL_PATH)
R["tl_material_exists"] = tl_material_exists
if not tl_material_exists:
    R["material_note"] = (
        "MI_Bldg_Stone_TL does not exist yet (no TL materials have been "
        "authored) -- every mesh's slot was assigned the CH fallback "
        "%s instead." % FALLBACK_MATERIAL_PATH
    )

fixed = []
for rec in R["imported"]:
    if rec.get("error"):
        continue
    mesh_path = "%s/Mesh/%s" % (rec["folder"], rec["name"])
    mesh = EAL.load_asset(mesh_path)
    if mesh is None:
        continue
    base = EAL.load_asset(TL_MATERIAL_PATH)
    used_fallback = False
    if base is None:
        # fall back to an existing CH material so the slot is never WorldGrid
        base = EAL.load_asset(FALLBACK_MATERIAL_PATH)
        used_fallback = True
    if base is None:
        fixed.append({"name": rec["name"], "err": "no fallback material"})
        continue
    sm = unreal.StaticMaterial()
    sm.set_editor_property("material_interface", base)
    sm.set_editor_property("material_slot_name", "Default")
    try:
        mesh.set_editor_property("static_materials", [sm])
        EAL.save_loaded_asset(mesh)
    except Exception as e:
        fixed.append({"name": rec["name"], "err": "%s: %s" % (type(e).__name__, e)})
        continue
    # read back: the only honest confirmation
    back = EAL.load_asset(mesh_path).get_editor_property("static_materials")
    ok = bool(back) and "WorldGrid" not in str(back[0].get_editor_property("material_interface"))
    fixed.append({
        "name": rec["name"],
        "slot_ok": ok,
        "material_used": str(base.get_path_name()),
        "used_fallback": used_fallback,
    })
R["material_fixups"] = fixed
R["material_failures"] = [f for f in fixed if not f.get("slot_ok")]

print(json.dumps({
    "imported": len(R["imported"]),
    "errors": R["errors"],
    "scale_failures": [r for r in R["imported"] if r.get("scale_ok") is False],
    "pivot_failures": [r for r in R["imported"] if r.get("pivot_ok") is False],
    "material_failures": R["material_failures"],
    "tl_material_exists": R["tl_material_exists"],
}, indent=1, default=str))
mcp_result = R
