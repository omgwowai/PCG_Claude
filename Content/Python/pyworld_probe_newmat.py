# pyworld_probe_newmat.py -- PROBE: create /Game/PyPCG/Probe/M_ProbeWater from scratch with MaterialFactoryNew in this
# Substrate project, report which expressions/properties a new material starts with, switch it to Single Layer Water,
# wire a few constants and compile. {"clear": true} deletes it.
import json

import unreal

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
PATH = "/Game/PyPCG/Probe/M_ProbeWater"
NEVER = unreal.PropertyAccessChangeNotifyMode.NEVER


def main():
    args = globals().get("mcp_args") or {}
    if EAL.does_asset_exist(PATH):
        EAL.delete_asset(PATH)
    if args.get("clear"):
        print("cleared")
        return
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    m = tools.create_asset("M_ProbeWater", "/Game/PyPCG/Probe", unreal.Material, unreal.MaterialFactoryNew())
    out = {"start_exprs": [e.get_class().get_name() for e in MEL.get_material_expressions(m)],
           "use_attrs": bool(m.get_editor_property("use_material_attributes")),
           "shading": str(m.get_editor_property("shading_model"))}
    out["slw_class"] = hasattr(unreal, "MaterialExpressionSingleLayerWaterMaterialOutput")
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER, NEVER)
    c = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -400, 0)
    c.set_editor_property("constant", unreal.LinearColor(0.02, 0.03, 0.03, 1.0), NEVER)
    r = MEL.create_material_expression(m, unreal.MaterialExpressionConstant, -400, 200)
    r.set_editor_property("r", 0.04, NEVER)
    out["base"] = bool(MEL.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR))
    out["rough"] = bool(MEL.connect_material_property(r, "", unreal.MaterialProperty.MP_ROUGHNESS))
    if out["slw_class"]:
        w = MEL.create_material_expression(m, unreal.MaterialExpressionSingleLayerWaterMaterialOutput, -200, 400)
        sc = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -600, 400)
        sc.set_editor_property("constant", unreal.LinearColor(0.1, 0.2, 0.2, 1.0), NEVER)
        ab = MEL.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, -600, 500)
        ab.set_editor_property("constant", unreal.LinearColor(0.6, 0.3, 0.2, 1.0), NEVER)
        names = [str(n) for n in MEL.get_material_expression_input_names(w)]
        out["slw_inputs"] = names
        out["slw_scatter"] = bool(MEL.connect_material_expressions(sc, "", w, names[0]))
        out["slw_absorb"] = bool(MEL.connect_material_expressions(ab, "", w, names[1]))
    MEL.recompile_material(m)
    EAL.save_asset(PATH, only_if_is_dirty=False)
    out["end_exprs"] = [e.get_class().get_name() for e in MEL.get_material_expressions(m)]
    out["stats"] = str(MEL.get_statistics(m))[:400] if hasattr(MEL, "get_statistics") else None
    print(json.dumps(out, indent=1))


main()
