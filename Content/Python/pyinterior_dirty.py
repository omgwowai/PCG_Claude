# pyinterior_dirty.py -- the packages the editor holds dirty; {"save_interior": true} saves the dirty ones under
# /Game/PyPCG/Interior (PyInterior's own materials and graph) and nothing else.
ELS = unreal.EditorLoadingAndSavingUtils
args = mcp_args or {}
R = {}
if args.get("save_interior"):
    R["saved"] = bool(unreal.EditorAssetLibrary.save_directory("/Game/PyPCG/Interior", True, True))
maps = [p.get_name() for p in ELS.get_dirty_map_packages()]
content = [p.get_name() for p in ELS.get_dirty_content_packages()]
groups = {}
for n in content:
    k = n.rsplit("/", 1)[0]
    groups[k] = groups.get(k, 0) + 1
R.update({"maps": maps, "content": len(content), "by_folder": groups})
mcp_result = R
