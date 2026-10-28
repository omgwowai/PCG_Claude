# pyworld_probe_town_materials.py -- READ-ONLY: the candidate materials for the town's building kit: full paths, parent,
# and their scalar / vector / texture parameter names (tiling, tint), so the kit builder can pick and tint them.
# Writes Saved/Reports/pyworld_town_materials.json.
import json
import os

import unreal

AR = unreal.AssetRegistryHelpers.get_asset_registry()
OUT = os.path.join(unreal.Paths.project_saved_dir(), "Reports", "pyworld_town_materials.json")
WANT = ("MI_Bldg_BrickOffset_", "MI_Bldg_Block_Limestone", "M_Bldg_paintedstone_white", "MI_Bldg_Wood_", "MI_Rooftop_RoofTile",
        "MI_Rooftop_", "Modular_Building_", "MI_Bldg_PaintedMetal_Roof", "M_Window", "MI_Bldg_Stucco", "MI_Bldg_Plaster",
        "MI_Bldg_PaintedStone", "MI_Bldg_Concrete", "M_Roof", "MI_Roof", "MI_Bldg_Wood")
MATS = [unreal.TopLevelAssetPath("/Script/Engine", "MaterialInstanceConstant"), unreal.TopLevelAssetPath("/Script/Engine", "Material")]
MEL = unreal.MaterialEditingLibrary
out = {}
for cls in MATS:
    for a in AR.get_assets(unreal.ARFilter(package_paths=["/Game"], recursive_paths=True, class_paths=[cls])):
        n = str(a.asset_name)
        if not any(n.startswith(w) for w in WANT):
            continue
        pkg = str(a.package_name)
        if n in out:
            continue
        m = unreal.load_asset(pkg)
        row = {"path": pkg}
        try:
            if isinstance(m, unreal.MaterialInstanceConstant):
                p = m.get_editor_property("parent")
                row["parent"] = p.get_path_name() if p else None
                row["scalars"] = [str(x) for x in MEL.get_scalar_parameter_names(m)][:30]
                row["vectors"] = [str(x) for x in MEL.get_vector_parameter_names(m)][:20]
                row["textures"] = [str(x) for x in MEL.get_texture_parameter_names(m)][:20]
            else:
                row["scalars"] = [str(x) for x in MEL.get_scalar_parameter_names(m)][:30]
                row["vectors"] = [str(x) for x in MEL.get_vector_parameter_names(m)][:20]
        except Exception as e:
            row["err"] = str(e)[:120]
        out[n] = row
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as fh:
    json.dump(out, fh, indent=1)
print(json.dumps(sorted(out), indent=0)[:3000])
