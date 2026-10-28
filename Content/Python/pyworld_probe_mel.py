# pyworld_probe_mel.py -- READ-ONLY: MaterialEditingLibrary functions, and the master's expressions that have an
# "Anisotropy" input (class, inputs connected) -- no compile, no edit.
import json

import unreal

MEL = unreal.MaterialEditingLibrary
PATH = "/Game/Custom/CustomMaterials/Materials/Master_Materials/M_MS_Default_Material_VT_DynamicLayering"


def main():
    out = {"mel": sorted(n for n in dir(MEL) if not n.startswith("_"))}
    m = unreal.load_asset(PATH)
    out["use_material_attributes"] = bool(m.get_editor_property("use_material_attributes"))
    out["shading_model"] = str(m.get_editor_property("shading_model"))
    exprs = None
    for name in ("get_material_expressions", "get_all_material_expressions"):
        if hasattr(MEL, name):
            exprs = getattr(MEL, name)(m)
            break
    if exprs is None:
        try:
            eod = m.get_editor_property("editor_only_data")
            exprs = eod.get_editor_property("expression_collection").get_editor_property("expressions")
        except Exception as ex:
            out["exprs_error"] = str(ex)
    if exprs is not None:
        classes = {}
        hits = []
        for e in exprs:
            c = e.get_class().get_name()
            classes[c] = classes.get(c, 0) + 1
            try:
                names = [str(n) for n in MEL.get_material_expression_input_names(e)]
            except Exception:
                continue
            if any("nisotrop" in n for n in names):
                ins = MEL.get_inputs_for_material_expression(m, e)
                hits.append({"name": e.get_name(), "class": c,
                             "inputs": {n: (i.get_class().get_name() if i else None) for n, i in zip(names, ins)}})
        out["classes"] = classes
        out["aniso_nodes"] = hits
    print(json.dumps(out, indent=1))


main()
