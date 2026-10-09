# tl_delete_obsolete_kit.py -- delete TL kit meshes that are no longer in the
# spec. Only touches /Game/Building/TL/A, refuses anything with referencers.
# Args: {"apply": true}; default is a dry run.
import json

args = mcp_args or {}
ROOT = "/Game/Building/TL/A"
SPEC = "E:/PCG_Claude/Tools/tl_kit/tl_kit_spec.json"


def main():
    EAL = unreal.EditorAssetLibrary
    with open(SPEC, encoding="utf-8") as f:
        wanted = {p["mesh_name"] for p in json.load(f)["parts"]}
    out = {"deleted": [], "kept_referenced": [], "would_delete": []}
    for a in EAL.list_assets(ROOT, recursive=True, include_folder=False):
        path = a.split(".")[0]
        name = path.rsplit("/", 1)[-1]
        if not name.startswith("SM_BLDG_TL_") or name in wanted:
            continue
        refs = [r for r in EAL.find_package_referencers_for_asset(path, False) if r != path]
        if refs:
            out["kept_referenced"].append({"asset": path, "refs": list(refs)})
            continue
        if not args.get("apply"):
            out["would_delete"].append(path)
            continue
        out["deleted"].append({"asset": path, "ok": bool(EAL.delete_asset(path))})
    for d in ("Kit_Bldg_TL_L5_A/Mesh", "Kit_Bldg_TL_L5_A"):
        p = ROOT + "/" + d
        if args.get("apply") and EAL.does_directory_exist(p) and not EAL.list_assets(p, True, False):
            EAL.delete_directory(p)
    return out


mcp_result = json.loads(json.dumps(main(), default=str))
