# pyworld_probe_mi.py -- READ-ONLY: a material instance's parent chain and parameter names/values (no compile).
# Args: {"paths": [...]}
import json

import unreal

MEL = unreal.MaterialEditingLibrary


def info(path):
    m = unreal.load_asset(path)
    out = {"class": m.get_class().get_name()}
    chain, p = [], m
    while isinstance(p, unreal.MaterialInstance):
        p = p.get_editor_property("parent")
        chain.append(p.get_path_name() if p else None)
    out["parents"] = chain
    base = m if isinstance(m, unreal.Material) else None
    out["textures"] = {str(n): (MEL.get_material_instance_texture_parameter_value(m, n).get_path_name()
                                if isinstance(m, unreal.MaterialInstance) and MEL.get_material_instance_texture_parameter_value(m, n) else None)
                       for n in MEL.get_texture_parameter_names(m)}
    out["scalars"] = [str(n) for n in MEL.get_scalar_parameter_names(m)]
    out["switches"] = [str(n) for n in MEL.get_static_switch_parameter_names(m)]
    return out


args = globals().get("mcp_args") or {}
print(json.dumps({p: info(p) for p in args.get("paths", [])}, indent=1))
