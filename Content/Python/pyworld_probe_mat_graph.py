# pyworld_probe_mat_graph.py -- READ-ONLY: every expression of a material (class, name, inputs and what feeds them,
# key properties) so its graph can be understood without the material editor.
# Args: {"path": "..."}
import json

import unreal

MEL = unreal.MaterialEditingLibrary
KEYS = ("parameter_name", "constant", "r", "material_function", "texture", "layer_name", "attribute_name", "name",
        "texture_object", "desc", "input_name", "code")


def main():
    args = globals().get("mcp_args") or {}
    path = args.get("path", "/PCGPrimitives_MeshPartitionInterop/Assets/Materials/M_MeshTerrain_Basic")
    m = unreal.load_asset(path)
    rows = []
    for e in MEL.get_material_expressions(m):
        row = {"name": e.get_name(), "class": e.get_class().get_name().replace("MaterialExpression", "")}
        for k in KEYS:
            try:
                v = e.get_editor_property(k)
            except Exception:
                continue
            row[k] = v.get_path_name() if isinstance(v, unreal.Object) else str(v)[:120]
        try:
            names = [str(n) for n in MEL.get_material_expression_input_names(e)]
            ins = MEL.get_inputs_for_material_expression(m, e)
            row["in"] = {n: i.get_name() for n, i in zip(names, ins) if i is not None}
        except Exception:
            pass
        rows.append(row)
    print(json.dumps({"use_attributes": bool(m.get_editor_property("use_material_attributes")),
                      "expressions": rows}, indent=0))


main()
