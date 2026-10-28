# pyworld_probe_building_kits.py -- READ-ONLY: Megascans / other modular building meshes and their sizes (the
# Modular_Building_* materials suggest a kit), plus the bounds of the PCGPrimitives grammar kit and of one City Sample
# style's level-1 modules, for choosing the town's building kit. Writes Saved/Reports/pyworld_building_kits.json.
import json
import os

import unreal

AR = unreal.AssetRegistryHelpers.get_asset_registry()
OUT = os.path.join(unreal.Paths.project_saved_dir(), "Reports", "pyworld_building_kits.json")
SM = unreal.TopLevelAssetPath("/Script/Engine", "StaticMesh")


def meshes(path, recursive=True):
    return AR.get_assets(unreal.ARFilter(package_paths=[path], recursive_paths=recursive, class_paths=[SM]))


def size(pkg):
    m = unreal.load_asset(pkg)
    if m is None:
        return None
    b = m.get_bounding_box()
    mats = [str(s.get_editor_property("material_interface").get_name()) if s.get_editor_property("material_interface") else None
            for s in m.get_editor_property("static_materials")]
    return {"min": [round(b.min.x), round(b.min.y), round(b.min.z)], "max": [round(b.max.x), round(b.max.y), round(b.max.z)],
            "mats": mats[:6], "tris": m.get_num_triangles(0) if hasattr(m, "get_num_triangles") else None}


out = {"modular": {}, "prim": {}, "sf_l1": {}, "folders": []}
for a in meshes("/Game"):
    n = str(a.asset_name)
    if any(k in n.lower() for k in ("modular", "building", "house", "roof", "chimney", "balcon", "shutter", "dormer")):
        pkg = str(a.package_name)
        if pkg.startswith("/Game/Building/"):
            continue
        out["folders"].append(pkg)
out["folders"] = sorted(out["folders"])[:200]
for pkg in out["folders"][:80]:
    out["modular"][pkg] = size(pkg)
for a in meshes("/PCGPrimitives/Meshes"):
    if str(a.asset_name).startswith(("SM_Bldg", "L1_", "L2_", "L3_", "Frame")):
        out["prim"][str(a.asset_name)] = size(str(a.package_name))
for a in sorted(meshes("/Game/Building/SF"), key=lambda a: str(a.asset_name)):
    n = str(a.asset_name)
    if n.startswith("SM_BLDG_SFA_L1_A_") and "decal" not in n.lower():
        out["sf_l1"][n] = size(str(a.package_name))
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as fh:
    json.dump(out, fh, indent=1)
print(json.dumps({"modular_found": len(out["folders"]), "first": out["folders"][:30], "prim": len(out["prim"]),
                  "sf_l1": len(out["sf_l1"])}, indent=1))
