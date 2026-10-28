# pyworld_probe_megascans_kit.py -- READ-ONLY: every static mesh of the Megascans "Modular_Building" kit
# (/Game/Megascans/3D_Assets/Modular_Building_*): bounds, triangle count, Nanite, material slots. The town's building
# modules come from this kit. Writes Saved/Reports/pyworld_megascans_kit.json.
import json
import os

import unreal

AR = unreal.AssetRegistryHelpers.get_asset_registry()
OUT = os.path.join(unreal.Paths.project_saved_dir(), "Reports", "pyworld_megascans_kit.json")
SM = unreal.TopLevelAssetPath("/Script/Engine", "StaticMesh")
out = {}
for a in AR.get_assets(unreal.ARFilter(package_paths=["/Game/Megascans/3D_Assets"], recursive_paths=True, class_paths=[SM])):
    pkg = str(a.package_name)
    if "/Modular_Building" not in pkg:
        continue
    m = unreal.load_asset(pkg)
    b = m.get_bounding_box()
    nanite = None
    try:
        nanite = bool(m.get_editor_property("nanite_settings").get_editor_property("enabled"))
    except Exception:
        pass
    mats = []
    for s in m.get_editor_property("static_materials"):
        mi = s.get_editor_property("material_interface")
        mats.append(mi.get_path_name() if mi else None)
    out[pkg] = {"min": [round(b.min.x, 1), round(b.min.y, 1), round(b.min.z, 1)],
                "max": [round(b.max.x, 1), round(b.max.y, 1), round(b.max.z, 1)],
                "tris": m.get_num_triangles(0), "nanite": nanite, "mats": mats}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as fh:
    json.dump(out, fh, indent=1)
print(json.dumps({"meshes": len(out)}))
