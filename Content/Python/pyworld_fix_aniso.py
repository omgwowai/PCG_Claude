# pyworld_fix_aniso.py -- EDITS AND SAVES the Electric Dreams master materials copied into /Game (Tools/pyworld/
# ed_closure.py): unhooks the Anisotropy input of their Substrate legacy-conversion node.
# Why: this project runs Substrate with the blendable GBuffer (r.Substrate.ProjectGBufferFormat=0). A material whose
# conversion node has Anisotropy wired is compiled as anisotropic while its conservative layout says it is not, and
# the shader map check asserts (MaterialShader.cpp:2567, "missing expected shader type FAnisotropyPS") the first
# time such a mesh is drawn. The rocks and dead wood never use anisotropy. Args: {"dry": true} only reports.
import json

import unreal

MEL = unreal.MaterialEditingLibrary
ROOTS = ["/Game/Custom/CustomMaterials", "/Game/MSPresets", "/Game/Megascans/3D_Plants", "/Game/Megascans/3D_Assets",
         "/Game/Megascans/Surfaces"]


def masters():
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    flt = unreal.ARFilter(package_paths=ROOTS, recursive_paths=True,
                          class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "Material")])
    return [str(a.package_name) for a in reg.get_assets(flt)]


def main():
    args = globals().get("mcp_args") or {}
    dry = bool(args.get("dry"))
    out = {}
    for path in masters():
        m = unreal.load_asset(path)
        fixed = []
        for e in MEL.get_material_expressions(m):
            if e.get_class().get_name() != "MaterialExpressionSubstrateShadingModels":
                continue
            names = [str(n) for n in MEL.get_material_expression_input_names(e)]
            ins = MEL.get_inputs_for_material_expression(m, e)
            for n, src in zip(names, ins):
                if n == "Anisotropy" and src is not None:
                    outs = [str(o) for o in MEL.get_material_expression_output_names(src)]
                    pin = "Anisotropy" if "Anisotropy" in outs else str(
                        MEL.get_input_node_output_name_for_material_expression(e, src))
                    done = None
                    if not dry:
                        MEL.disconnect_material_expressions(e, n)
                        done = MEL.get_inputs_for_material_expression(m, e)[names.index(n)] is None
                    fixed.append([e.get_name(), src.get_name(), pin, done])
        if fixed:
            out[path] = fixed
            if not dry and all(f[3] for f in fixed):
                MEL.recompile_material(m)
                unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False)
    print(json.dumps({"dry": dry, "materials_checked": len(masters()), "fixed": out}, indent=1))


main()
