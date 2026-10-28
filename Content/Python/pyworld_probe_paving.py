# pyworld_probe_paving.py -- READ-ONLY: bounds and materials of City Sample's sidewalk / plaza / curb meshes
# (/Game/Road/Kit_Sidewalk_A, Kit_Small_Curb_A, Kit_City_Road) for the town's street cross-section. Prints JSON.
import json

import unreal

AR = unreal.AssetRegistryHelpers.get_asset_registry()
SM = unreal.TopLevelAssetPath("/Script/Engine", "StaticMesh")
out = {}
for folder in ("/Game/Road/Kit_Sidewalk_A/Mesh", "/Game/Road/Kit_Small_Curb_A/Mesh", "/Game/Road/Kit_City_Road"):
    for a in AR.get_assets(unreal.ARFilter(package_paths=[folder], recursive_paths=True, class_paths=[SM])):
        n = str(a.asset_name)
        if "Col" in n or "Collision" in n:
            continue
        m = unreal.load_asset(str(a.package_name))
        b = m.get_bounding_box()
        out[str(a.package_name).replace("/Game/Road/", "")] = [
            [round(b.min.x), round(b.min.y), round(b.min.z)], [round(b.max.x), round(b.max.y), round(b.max.z)],
            [(s.get_editor_property("material_interface").get_name() if s.get_editor_property("material_interface")
              else None) for s in m.get_editor_property("static_materials")]]
print(json.dumps(out))
