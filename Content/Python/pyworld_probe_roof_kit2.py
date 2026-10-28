# pyworld_probe_roof_kit2.py -- READ-ONLY: what the assets under Modular_Roof_Kit_00 / Gable_Kit_00 (the "Foliage"
# subfolders) are, and their bounds and materials when they are static meshes. Prints JSON.
import json

import unreal

AR = unreal.AssetRegistryHelpers.get_asset_registry()
AR.scan_paths_synchronous(["/Game/Megascans/3D_Assets/Modular_Roof_Kit_00", "/Game/Megascans/3D_Assets/Gable_Kit_00"],
                          True, False)
out = {}
for folder in ("/Game/Megascans/3D_Assets/Modular_Roof_Kit_00", "/Game/Megascans/3D_Assets/Gable_Kit_00"):
    for a in AR.get_assets(unreal.ARFilter(package_paths=[folder], recursive_paths=True)):
        pkg = str(a.package_name)
        row = {"class": str(a.asset_class_path.asset_name)}
        m = unreal.load_asset(pkg)
        mesh = m if isinstance(m, unreal.StaticMesh) else None
        if mesh is None:
            try:
                mesh = m.get_editor_property("mesh")
            except Exception:
                mesh = None
        if isinstance(mesh, unreal.StaticMesh):
            b = mesh.get_bounding_box()
            row.update({"mesh": mesh.get_path_name(),
                        "min": [round(b.min.x, 1), round(b.min.y, 1), round(b.min.z, 1)],
                        "max": [round(b.max.x, 1), round(b.max.y, 1), round(b.max.z, 1)],
                        "tris": mesh.get_num_triangles(0),
                        "mats": [(s.get_editor_property("material_interface").get_path_name()
                                  if s.get_editor_property("material_interface") else None)
                                 for s in mesh.get_editor_property("static_materials")]})
        out[pkg] = row
print(json.dumps(out, indent=1))
