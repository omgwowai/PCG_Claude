import gc
import importlib
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
# The bridge keeps sys.modules between calls; drop pypcg so edits to it take effect.
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pypcg_build_slim.py -- build slim stage graphs from pypcg/graphs/sNN_*.py and check each against its
# own description (spec 3, structural check). Saves only graphs with 0 differences.
# Args: {"stages": [n, ...] | "all", "profile": "official" | "town", "save": true}
#   official -> /Game/PyPCG/Slim/<graph>   actor references into the demo level (V2)
#   town     -> /Game/PyPCG/Town/<graph>   actor references into /Game/PyPCG/L_PyTown
#   stage 0  -> /Game/PyPCG/Probe/PCG_PyProbe


def run(args):
    from pypcg import build, compare, graphs, stages
    profile_name = args.get("profile", "official")
    profile = importlib.import_module("pypcg.profiles." + profile_name)
    if args.get("stages", "all") == "all":
        wanted = [s[0] for s in stages.STAGES if graphs.exists(s[0])]
    else:
        wanted = [int(n) for n in args["stages"]]
    rows = []
    for n in wanted:
        folder = "Probe" if n == 0 else ("Slim" if profile_name == "official" else "Town")
        target = "/Game/PyPCG/%s/%s" % (folder, stages.name(n))
        ir = graphs.graph(n).to_ir(profile)
        diffs = build.build_slim(ir, target, save=bool(args.get("save", True)))
        rows.append({"stage": n, "asset": target, "nodes": len(ir["nodes"]), "diffs": len(diffs),
                     "first": compare.format_diffs(diffs, 15)})
    path = os.path.join(_REPO, "Saved", "Reports", "pypcg_build_slim_%s.json" % profile_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)
    return rows


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
