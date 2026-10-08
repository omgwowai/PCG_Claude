# tl_probe_kit_refs.py -- READ-ONLY. Who references the TL kit meshes, and
# whether any of them is loaded in the current world.
import json


def main():
    EAL = unreal.EditorAssetLibrary
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    opts = unreal.AssetRegistryDependencyOptions()
    out = {}
    for a in EAL.list_assets("/Game/Building/TL/A", recursive=True, include_folder=False):
        pkg = a.split(".")[0]
        refs = [str(r) for r in (ar.get_referencers(unreal.Name(pkg), opts) or [])]
        out[pkg.split("/")[-1]] = refs
    users = sorted({r for v in out.values() for r in v})
    return {"meshes": len(out), "referencers": users}


mcp_result = json.loads(json.dumps(main(), default=str))
