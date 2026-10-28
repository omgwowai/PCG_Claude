# pyworld_probe_mi2.py -- READ-ONLY: a material instance's scalar / vector / switch VALUES (and the parent defaults).
import json

import unreal

MEL = unreal.MaterialEditingLibrary
args = globals().get("mcp_args") or {}
out = {}
for p in args.get("paths", []):
    m = unreal.load_asset(p)
    base = m.get_editor_property("parent") if isinstance(m, unreal.MaterialInstance) else m
    r = {"scalars": {}, "vectors": {}, "switches": {}}
    for n in MEL.get_scalar_parameter_names(m):
        r["scalars"][str(n)] = round(MEL.get_material_instance_scalar_parameter_value(m, n), 3)
    for n in MEL.get_vector_parameter_names(m):
        v = MEL.get_material_instance_vector_parameter_value(m, n)
        r["vectors"][str(n)] = [round(v.r, 3), round(v.g, 3), round(v.b, 3), round(v.a, 3)]
    for n in MEL.get_static_switch_parameter_names(m):
        r["switches"][str(n)] = bool(MEL.get_material_instance_static_switch_parameter_value(m, n))
    out[p.rsplit("/", 1)[1]] = r
print(json.dumps(out, indent=0))
