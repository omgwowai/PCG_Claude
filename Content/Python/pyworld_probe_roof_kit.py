# pyworld_probe_roof_kit.py -- READ-ONLY: the two roof / gable kits outside the Modular_Building_* folders
# (Modular_Roof_Kit_00, Gable_Kit_00), the chimney-like roof props and the tileable candidates for procedural roof and
# wall surfaces: bounds, slots and their materials, and for materials the parent and the texture / world-space hints.
# Writes Saved/Reports/pyworld_roof_kit.json.
import json
import os

import unreal

AR = unreal.AssetRegistryHelpers.get_asset_registry()
OUT = os.path.join(unreal.Paths.project_saved_dir(), "Reports", "pyworld_roof_kit.json")
SM = unreal.TopLevelAssetPath("/Script/Engine", "StaticMesh")
MEL = unreal.MaterialEditingLibrary
out = {"meshes": {}, "materials": {}}
for folder in ("/Game/Megascans/3D_Assets/Modular_Roof_Kit_00", "/Game/Megascans/3D_Assets/Gable_Kit_00",
               "/Game/Prop/Kit_roof_brick_RR", "/Game/Prop/Kit_roof_exhaust_RR", "/Game/Prop/Kit_roof_Exhaust_A",
               "/Game/Prop/Kit_Railing_A", "/Game/Prop/BLDG/Kit_Prop_Lamp", "/Game/Prop/BLDG/Kit_Prop_Plaque",
               "/Game/Prop/BLDG/Kit_Prop_AC"):
    for a in AR.get_assets(unreal.ARFilter(package_paths=[folder], recursive_paths=True, class_paths=[SM])):
        pkg = str(a.package_name)
        m = unreal.load_asset(pkg)
        b = m.get_bounding_box()
        mats = []
        for s in m.get_editor_property("static_materials"):
            mi = s.get_editor_property("material_interface")
            mats.append(mi.get_path_name() if mi else None)
        out["meshes"][pkg] = {"min": [round(b.min.x, 1), round(b.min.y, 1), round(b.min.z, 1)],
                              "max": [round(b.max.x, 1), round(b.max.y, 1), round(b.max.z, 1)],
                              "tris": m.get_num_triangles(0), "mats": mats}
WANT = ["/Game/Environment/RoofTop/Material/MI/MI_Rooftop_RoofTile", "/Game/Building/Material/Roof/M_Roof",
        "/Game/Building/Material/MI/Brick/MI_Bldg_BrickOffset_Red", "/Game/Building/Material/MI/Wood/MI_Bldg_Wood_Cedar",
        "/Game/Building/SF/D/Material/MI_Bldg_PaintedStone_White", "/Game/Building/CH/A/Material/MI_Bldg_Block_Limestone_Beige",
        "/Game/Megascans/Surfaces/Stucco_Wall_2x2_M_00", "/Game/Megascans/Surfaces/Damaged_Wall_Plaster_00",
        "/Game/Megascans/Surfaces/Stone_Tiles_Facade_2x2_M_00", "/Game/Megascans/Surfaces/Wooden_Planks_tixjedrbw",
        "/Game/Megascans/3D_Assets/Modular_Building_Roof_Kit_01/Modular_Building_Roof_Kit_01_inst",
        "/Game/Megascans/3D_Assets/Modular_Building_Roof_Kit_00/Modular_Building_Roof_Kit_00_inst"]
MATS = [unreal.TopLevelAssetPath("/Script/Engine", "MaterialInstanceConstant"),
        unreal.TopLevelAssetPath("/Script/Engine", "Material")]
for path in WANT:
    found = []
    if unreal.EditorAssetLibrary.does_directory_exist(path):
        found = [str(a.package_name) for a in AR.get_assets(unreal.ARFilter(package_paths=[path], recursive_paths=True,
                                                                            class_paths=MATS))]
    elif unreal.EditorAssetLibrary.does_asset_exist(path):
        found = [path]
    if not found:
        out["materials"][path] = {"missing": True}
    for pkg in found:
        m = unreal.load_asset(pkg)
        row = {"class": m.get_class().get_name()}
        try:
            if isinstance(m, unreal.MaterialInstanceConstant):
                p = m.get_editor_property("parent")
                row["parent"] = p.get_path_name() if p else None
                row["textures"] = {}
                for n in MEL.get_texture_parameter_names(m):
                    t = MEL.get_material_instance_texture_parameter_value(m, n)
                    row["textures"][str(n)] = t.get_path_name() if t else None
                row["scalars"] = {str(n): MEL.get_material_instance_scalar_parameter_value(m, n)
                                  for n in MEL.get_scalar_parameter_names(m)
                                  if any(k in str(n) for k in ("Tex Size", "Tiling", "World", "Proj", "Scale"))}
                row["vectors"] = {}
                for n in MEL.get_vector_parameter_names(m):
                    if "Tint" in str(n):
                        c = MEL.get_material_instance_vector_parameter_value(m, n)
                        row["vectors"][str(n)] = [round(c.r, 3), round(c.g, 3), round(c.b, 3), round(c.a, 3)]
        except Exception as e:
            row["err"] = str(e)[:200]
        out["materials"][pkg] = row
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as fh:
    json.dump(out, fh, indent=1)
print(json.dumps({"meshes": len(out["meshes"]), "materials": len(out["materials"])}))
