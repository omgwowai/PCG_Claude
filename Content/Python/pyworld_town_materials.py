# pyworld_town_materials.py -- builds the town's facade and roof colours: one MaterialInstanceConstant per (kit material,
# tint) that pypcg.world.kit.materials_needed() lists, under /Game/PyPCG/World/Town/ (parent = the Megascans kit's own
# instance, "Albedo Tint" = the colour). Idempotent: an existing instance is updated in place. {"probe": true} only reports
# the parent's tint parameters and static switches. Prints a JSON summary.
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
from pypcg.world import kit as K  # noqa: E402

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
PARAM = "Albedo Tint"


def _pkg(path):
    return path.split(".")[0]


def main():
    args = globals().get("mcp_args") or {}
    need = K.materials_needed()
    if args.get("probe"):
        parent = unreal.load_asset(need[0][1])
        out = {"parent": need[0][1], "vectors": {}, "switches": [str(s) for s in MEL.get_static_switch_parameter_names(parent)]}
        for n in MEL.get_vector_parameter_names(parent):
            c = MEL.get_material_instance_vector_parameter_value(parent, n)
            out["vectors"][str(n)] = [round(c.r, 3), round(c.g, 3), round(c.b, 3), round(c.a, 3)]
        out["scalars"] = {str(n): MEL.get_material_instance_scalar_parameter_value(parent, n)
                          for n in MEL.get_scalar_parameter_names(parent) if "Tint" in str(n) or "Albedo" in str(n)}
        print(json.dumps(out))
        return
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    made, updated, failed = 0, 0, []
    for path, parent_path, color in need:
        pkg = _pkg(path)
        folder, name = pkg.rsplit("/", 1)
        parent = unreal.load_asset(parent_path)
        if parent is None:
            failed.append([path, "no parent " + parent_path])
            continue
        if EAL.does_asset_exist(pkg):
            mi = unreal.load_asset(pkg)
            updated += 1
        else:
            mi = tools.create_asset(name, folder, unreal.MaterialInstanceConstant,
                                    unreal.MaterialInstanceConstantFactoryNew())
            made += 1
        if mi is None:
            failed.append([path, "create_asset returned None"])
            continue
        MEL.set_material_instance_parent(mi, parent)
        MEL.set_material_instance_vector_parameter_value(mi, PARAM, unreal.LinearColor(color[0], color[1], color[2], 1.0))
        # MS_DefaultMaterial lerps towards the tinted albedo by this (the kit's instances leave it at 0)
        MEL.set_material_instance_scalar_parameter_value(mi, PARAM + " Intensity", 1.0)
        MEL.update_material_instance(mi)
        EAL.save_loaded_asset(mi, False)
    print(json.dumps({"needed": len(need), "made": made, "updated": updated, "failed": failed[:10]}))


main()
