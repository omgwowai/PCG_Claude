# tl_kit_rebuild_meshes.py -- replace TL kit meshes in place with the FBX
# geometry while keeping every asset path and the objects that reference them.
#
# Reimporting with the legacy FBX factory over an existing mesh appends new
# material slots instead of reusing matching ones, and deleting the mesh first
# force-nulls the references BDF_WithTL, RULE_TL_* and the Lvl_TL_Building PCG
# output hold. So each part is imported into a scratch folder, both meshes are
# given the spec's four material slots, and the scratch LOD0 is copied onto
# the existing asset with StaticMeshEditorSubsystem.set_lod_from_static_mesh
# (reuse_existing_material_slots=True, which matches slots by material). The
# scratch assets are then deleted.
#
# Args: {"only": [...mesh names...]}. Requires the FBX files from
# Tools/tl_kit/build_tl_kit.py in E:/Blender/TL_Kit/FBX_Export.
import json
import os

args = mcp_args or {}
SPEC_PATH = args.get("spec", "E:/PCG_Claude/Tools/tl_kit/tl_kit_spec.json")
FBX_DIR = args.get("fbx_dir", "E:/Blender/TL_Kit/FBX_Export")
ONLY = set(args.get("only") or [])
DEST = "/Game/Building/TL/A"
SCRATCH = "/Game/Building/TL/_ImportScratch"
TOL_CM = 0.5
CORNER_KINDS = ("corner_ex", "cornice_corner_ex", "corner_in", "cornice_corner_in",
                "corner_half", "cornice_half", "foundation_corner", "roof_corner",
                "fan_front", "fan_back")
# Kinds that do not sit on z = 0: the foundation hangs below the ground floor
# and the roof deck sits just under the cornice coping.
BELOW_GRADE_KINDS = ("foundation", "foundation_corner", "roof_deck", "roof_corner")
# The foundation is centred on its slot (the frame of the NY foundation it
# replaces), so its run is [-w/2, w/2] instead of [0, w].
CENTRED_KINDS = ("foundation",)


def import_fbx(fbx, folder, name):
    opts = unreal.FbxImportUI()
    opts.set_editor_property("import_mesh", True)
    opts.set_editor_property("import_materials", True)
    opts.set_editor_property("import_textures", False)
    opts.set_editor_property("import_as_skeletal", False)
    smd = opts.get_editor_property("static_mesh_import_data")
    smd.set_editor_property("combine_meshes", True)
    smd.set_editor_property("auto_generate_collision", True)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", fbx)
    task.set_editor_property("destination_path", folder)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    task.set_editor_property("factory", unreal.FbxFactory())
    task.set_editor_property("options", opts)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    return unreal.EditorAssetLibrary.load_asset("%s/%s" % (folder, name))


def spec_slots(spec, mats):
    out = []
    for name in spec["materials"]:
        sm = unreal.StaticMaterial()
        sm.set_editor_property("material_interface", mats[name])
        sm.set_editor_property("material_slot_name", name)
        out.append(sm)
    return out


def rebind_by_slot_name(mesh, mats):
    """Point each slot at the material its name says, keeping slot order (and
    therefore every section's slot index)."""
    new = []
    for s in mesh.get_editor_property("static_materials"):
        ns = s.copy()
        name = str(s.get_editor_property("material_slot_name"))
        if name in mats:
            ns.set_editor_property("material_interface", mats[name])
        new.append(ns)
    mesh.set_editor_property("static_materials", new)


def section_slot_names(mesh):
    SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    names = [str(s.get_editor_property("material_slot_name")) for s in mesh.get_editor_property("static_materials")]
    return [names[SMES.get_lod_material_slot(mesh, 0, i)] for i in range(mesh.get_num_sections(0))]


def main():
    with open(SPEC_PATH, encoding="utf-8") as f:
        spec = json.load(f)
    EAL = unreal.EditorAssetLibrary
    SMES = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    mats = {k: EAL.load_asset(v) for k, v in spec["materials"].items()}
    order = list(spec["materials"])
    out = {"parts": [], "errors": []}
    for p in spec["parts"]:
        name = p["mesh_name"]
        if ONLY and name not in ONLY:
            continue
        rec = {"name": name}
        dest_path = "%s/Kit_Bldg_TL_L%d_A/Mesh/%s" % (DEST, p["level"], name)
        src = import_fbx(os.path.join(FBX_DIR, name + ".fbx"), SCRATCH, name)
        if src is None:
            out["errors"].append("%s: scratch import failed" % name)
            continue
        rebind_by_slot_name(src, mats)
        rec["src_sections"] = section_slot_names(src)

        dest = EAL.load_asset(dest_path)
        rec["created"] = dest is None
        if dest is None:
            dest = EAL.duplicate_loaded_asset(src, dest_path)
            if dest is None:
                out["errors"].append("%s: could not create %s" % (name, dest_path))
                continue
        else:
            dest.set_editor_property("static_materials", spec_slots(spec, mats))
            lod = SMES.set_lod_from_static_mesh(dest, 0, src, 0, True)
            if lod != 0:
                out["errors"].append("%s: set_lod_from_static_mesh returned %s" % (name, lod))
                continue
        rec["sections"] = section_slot_names(dest)
        slot_names = [str(s.get_editor_property("material_slot_name")) for s in dest.get_editor_property("static_materials")]
        bb = dest.get_bounding_box()
        rec["bounds_cm"] = [[round(bb.min.x, 1), round(bb.min.y, 1), round(bb.min.z, 1)],
                            [round(bb.max.x, 1), round(bb.max.y, 1), round(bb.max.z, 1)]]
        rec["verts"] = SMES.get_number_verts(dest, 0)
        errs = []
        if (not rec["created"] and slot_names != order) or not set(slot_names) <= set(order):
            errs.append("slots %s" % slot_names)
        if sorted(rec["sections"]) != sorted(rec["src_sections"]):
            errs.append("sections %s != source %s" % (rec["sections"], rec["src_sections"]))
        w = p["width_m"] * 100.0
        h = p["height_m"] * 100.0
        below = p["kind"] in BELOW_GRADE_KINDS or (p["kind"].startswith("fan_") and p["level"] == 0)
        if below:
            if bb.max.z > TOL_CM:
                errs.append("top z %.1f above 0" % bb.max.z)
        elif p["kind"].startswith("fan_"):
            # Corner fans above the ground floor can start above the storey
            # base (e.g. above a string course or frieze), so only require
            # the mesh to lie within the storey's own height span.
            if bb.min.z < -TOL_CM or bb.max.z > h + TOL_CM:
                errs.append("fan z [%.1f, %.1f] outside [0, %.1f]" % (bb.min.z, bb.max.z, h))
        elif abs(bb.min.z) > TOL_CM:
            errs.append("base z %.1f" % bb.min.z)
        y0, y1 = (-w / 2.0, w / 2.0) if p["kind"] in CENTRED_KINDS else (0.0, w)
        if p["kind"] not in CORNER_KINDS and (abs(bb.min.y - y0) > TOL_CM or abs(bb.max.y - y1) > TOL_CM):
            errs.append("run y [%.1f, %.1f] != [%.1f, %.1f]" % (bb.min.y, bb.max.y, y0, y1))
        if not EAL.save_asset(dest_path, only_if_is_dirty=False):
            errs.append("save failed")
        if errs:
            rec["error"] = "; ".join(errs)
            out["errors"].append("%s: %s" % (name, rec["error"]))
        out["parts"].append(rec)
    leftovers = []
    if EAL.does_directory_exist(SCRATCH):
        for a in EAL.list_assets(SCRATCH, recursive=True, include_folder=False):
            if not EAL.delete_asset(a.split(".")[0]):
                leftovers.append(a)
        EAL.delete_directory(SCRATCH)
    out["scratch_leftovers"] = leftovers
    meshes = [a for a in EAL.list_assets(DEST, recursive=True, include_folder=False)
              if a.split(".")[0].split("/")[-1].startswith("SM_BLDG_TL_")]
    out["meshes_on_disk"] = len(meshes)
    out["ok"] = not out["errors"] and not leftovers
    return out


R = main()
print(json.dumps({"errors": R["errors"], "ok": R["ok"], "n": len(R["parts"]),
                  "meshes_on_disk": R["meshes_on_disk"], "leftovers": R["scratch_leftovers"]}, indent=1))
mcp_result = json.loads(json.dumps(R, default=str))
