# pyworld_probe_bldg_props.py -- READ-ONLY: bounds and materials of City Sample's facade props that suit a village
# (awnings, shop boards, banners, plaques, wall lamps, window boxes), so the town rules can place them.
# Writes Saved/Reports/pyworld_bldg_props.json.
import json
import os

import unreal

AR = unreal.AssetRegistryHelpers.get_asset_registry()
OUT = os.path.join(unreal.Paths.project_saved_dir(), "Reports", "pyworld_bldg_props.json")
SM = unreal.TopLevelAssetPath("/Script/Engine", "StaticMesh")
KEYS = ("Awning", "BoardM", "Banner_A", "Plaque", "Lamp_Wall", "Flower", "Planter", "Shutter", "Sign_B", "Ceiling")
out = {}
for a in AR.get_assets(unreal.ARFilter(package_paths=["/Game/Prop/BLDG"], recursive_paths=True, class_paths=[SM])):
    n = str(a.asset_name)
    if not any(k in n for k in KEYS):
        continue
    pkg = str(a.package_name)
    m = unreal.load_asset(pkg)
    b = m.get_bounding_box()
    out[pkg] = {"min": [round(b.min.x, 1), round(b.min.y, 1), round(b.min.z, 1)],
                "max": [round(b.max.x, 1), round(b.max.y, 1), round(b.max.z, 1)],
                "tris": m.get_num_triangles(0),
                "mats": [(s.get_editor_property("material_interface").get_path_name().rsplit("/", 1)[-1]
                          if s.get_editor_property("material_interface") else None)
                         for s in m.get_editor_property("static_materials")]}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as fh:
    json.dump(out, fh, indent=1)
print(json.dumps({"props": len(out)}))
