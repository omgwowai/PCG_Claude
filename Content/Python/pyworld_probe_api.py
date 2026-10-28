# pyworld_probe_api.py -- READ-ONLY: names on an unreal class matching a filter (introspection helper).
# {"cls": "GeometryScript_MeshQueries", "match": "vertex"} -> sorted matching attribute names.
import json

import unreal

args = globals().get("mcp_args") or {}
cls = getattr(unreal, args.get("cls", "GeometryScript_MeshQueries"))
m = args.get("match", "").lower()
print(json.dumps(sorted(n for n in dir(cls) if m in n.lower() and not n.startswith("_"))))
