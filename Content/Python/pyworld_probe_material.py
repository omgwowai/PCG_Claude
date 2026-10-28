# pyworld_probe_material.py -- READ-ONLY: how does a material feed anisotropy? Lists the expressions on the
# material's root inputs and the inputs of the Substrate front material node.
# Args: {"path": "/Game/Custom/CustomMaterials/Materials/Master_Materials/M_MS_Default_Material_VT_DynamicLayering"}
import json

import unreal

MEL = unreal.MaterialEditingLibrary


def main():
    args = globals().get("mcp_args") or {}
    m = unreal.load_asset(args.get("path", "/Game/Custom/CustomMaterials/Materials/Master_Materials/"
                                          "M_MS_Default_Material_VT_DynamicLayering"))
    out = {"class": m.get_class().get_name()}
    props = {}
    for name in dir(unreal.MaterialProperty):
        if not name.startswith("MP_"):
            continue
        try:
            node = MEL.get_material_property_input_node(m, getattr(unreal.MaterialProperty, name))
        except Exception as ex:
            continue
        if node is not None:
            props[name] = node.get_class().get_name()
    out["root"] = props
    front = MEL.get_material_property_input_node(m, unreal.MaterialProperty.MP_FRONT_MATERIAL) \
        if hasattr(unreal.MaterialProperty, "MP_FRONT_MATERIAL") else None
    if front is not None:
        names = MEL.get_material_expression_input_names(front)
        ins = MEL.get_inputs_for_material_expression(m, front)
        out["front"] = {n: (i.get_class().get_name() if i else None) for n, i in zip(names, ins)}
    out["num_expressions"] = MEL.get_num_material_expressions(m)
    print(json.dumps(out, indent=1))


main()
