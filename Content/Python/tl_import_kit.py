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
#
# TRANSIENT PLACEHOLDER MATERIALS (fixed after Task 3 review):
# build_tl_kit.py embeds one flat placeholder Material per part, named after
# part["material"] (always "TL_Stone" in this kit), into every part's FBX.
# Legacy FBX import auto-creates that Material as a registry-visible asset
# under each level's Mesh folder (one shared object per folder, since every
# part in a level names it the same) but never writes it to disk -- it has no
# .uasset file. The first run of this script left those 3 assets behind and
# they were deleted by hand outside this script, which the review correctly
# flagged: a manual step is exactly the kind of thing a later re-run (e.g. for
# a scale fix) would rediscover the hard way. This script now removes them
# itself, after the material-fixup loop has already pointed every mesh's slot
# somewhere else, and reports how many it removed. It is idempotent: every
# run re-creates the placeholder during import (FBX always embeds it) and
# then removes it again during cleanup, so the script always ends at the same
# state -- 29 meshes, 0 stray materials -- and says so explicitly rather than
# silently accumulating or staying quiet about an already-clean state.
#
# EditorAssetLibrary.delete_asset() can return False for an asset that is
# still resident in memory even though nothing references it on disk (a
# pattern seen elsewhere in this project). If that happens here, after
# confirming get_referencers() is empty, the package file is removed directly
# from disk via the path PackageTools.package_name_to_filename() resolves.

import json
import os

# Scale tolerance is relative (1% of the spec dimension), not a flat cm value.
# A flat 2.0cm tolerance was reviewed and found to be 8% of the smallest part
# (Column_02, 25cm) but only 0.6% of the largest (325cm) -- disproportionate
# even though every measured delta in practice was 0.0cm. 1% keeps the same
# strictness at every scale; it is looser than 2.0cm only above 200cm and
# tighter below it, which is the intended fix for the disproportion.
SCALE_TOLERANCE_PCT = 0.01

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
        rec["scale_ok"] = abs(got_w - want_w) <= max(want_w * SCALE_TOLERANCE_PCT, 0.05)
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
        rec["height_ok"] = abs(got_h - want_h) <= max(want_h * SCALE_TOLERANCE_PCT, 0.05)
        rec["pivot_ok"] = abs(origin.z - ext.z) < 1.0
        if not rec["pivot_ok"]:
            pivot_msg = "pivot not at base: origin.z=%s extent.z=%s" % (origin.z, ext.z)
            if rec.get("error"):
                rec["error"] = rec["error"] + "; " + pivot_msg
            else:
                rec["error"] = pivot_msg
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
        fixed.append({"name": rec["name"], "error": "no fallback material"})
        continue
    sm = unreal.StaticMaterial()
    sm.set_editor_property("material_interface", base)
    sm.set_editor_property("material_slot_name", "Default")
    try:
        mesh.set_editor_property("static_materials", [sm])
        EAL.save_loaded_asset(mesh)
    except Exception as e:
        fixed.append({"name": rec["name"], "error": "%s: %s" % (type(e).__name__, e)})
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

# ---------- placeholder-material cleanup (idempotent) -----------------------
# Every FBX in this kit embeds a flat placeholder Material named after the
# spec's "material" field (always "TL_Stone"). Legacy FBX import auto-creates
# it as a registry asset under <folder>/Mesh alongside the mesh, once per
# distinct destination folder. By this point every real mesh's material slot
# has already been repointed above, so nothing should still reference these
# placeholders -- they exist only because the importer put them there. This
# step deletes them and reports exactly how many were found and removed, on
# every run, so idempotence is visible rather than assumed: a clean second
# run reports 0 found / 0 removed instead of staying silent about it.
PLACEHOLDER_NAMES = sorted(set(part["material"] for part in spec["parts"]))
ar = unreal.AssetRegistryHelpers.get_asset_registry()
dep_opts = unreal.AssetRegistryDependencyOptions()

stray = []
seen_folders = set()
for part in spec["parts"]:
    folder = dest_folder(part) + "/Mesh"
    if folder in seen_folders:
        continue
    seen_folders.add(folder)
    for mat_name in PLACEHOLDER_NAMES:
        mat_path = "%s/%s" % (folder, mat_name)
        if EAL.does_asset_exist(mat_path):
            stray.append(mat_path)

cleanup = {"found": stray, "removed": [], "failed": []}
for mat_path in stray:
    refs = list(ar.get_referencers(unreal.Name(mat_path), dep_opts) or [])
    if refs:
        cleanup["failed"].append({"path": mat_path, "error": "still referenced by %s" % [str(r) for r in refs]})
        continue
    deleted = EAL.delete_asset(mat_path)
    if deleted:
        cleanup["removed"].append(mat_path)
        continue
    # Known project pattern: delete_asset can return False for an asset that
    # is still resident in memory even though it has no on-disk referencers.
    # Fall back to removing the package file directly, having just confirmed
    # above that nothing references it.
    still_exists = EAL.does_asset_exist(mat_path)
    if not still_exists:
        # delete_asset actually worked despite reporting False.
        cleanup["removed"].append(mat_path)
        continue
    filename = unreal.PackageTools.package_name_to_filename(mat_path, ".uasset")
    disk_removed = False
    if filename and os.path.isfile(filename):
        try:
            os.remove(filename)
            disk_removed = True
        except OSError as e:
            cleanup["failed"].append({"path": mat_path, "error": "delete_asset False, disk remove failed: %s" % e})
            continue
    if disk_removed or not filename or not os.path.isfile(filename):
        # Either we removed the file on disk, or there never was one (the
        # placeholder is registry-only and was never saved) -- in the latter
        # case delete_asset's False is spurious and the in-memory entry is
        # gone once the transient object is garbage-collected. Re-check.
        if not EAL.does_asset_exist(mat_path):
            cleanup["removed"].append(mat_path)
        else:
            cleanup["failed"].append({"path": mat_path, "error": "delete_asset False, still resident after disk removal attempt"})
    else:
        cleanup["failed"].append({"path": mat_path, "error": "delete_asset False, no package file found on disk"})

R["placeholder_cleanup"] = cleanup

# ---------- idempotence proof: final state of the destination tree ---------
final_assets = [str(a) for a in EAL.list_assets(DEST, recursive=True, include_folder=False)]
final_stray = [a for a in final_assets if any(a.split("/")[-1].split(".")[0] == n for n in PLACEHOLDER_NAMES)]
R["final_mesh_count"] = len(final_assets)
R["final_stray_materials"] = final_stray
R["idempotent_clean"] = (len(final_assets) == len(spec["parts"])) and not final_stray

print(json.dumps({
    "imported": len(R["imported"]),
    "errors": R["errors"],
    "scale_failures": [r for r in R["imported"] if r.get("scale_ok") is False],
    "pivot_failures": [r for r in R["imported"] if r.get("pivot_ok") is False],
    "material_failures": R["material_failures"],
    "tl_material_exists": R["tl_material_exists"],
    "placeholder_cleanup_found": len(cleanup["found"]),
    "placeholder_cleanup_removed": len(cleanup["removed"]),
    "placeholder_cleanup_failed": cleanup["failed"],
    "final_mesh_count": R["final_mesh_count"],
    "final_stray_materials": R["final_stray_materials"],
    "idempotent_clean": R["idempotent_clean"],
}, indent=1, default=str))
mcp_result = R
