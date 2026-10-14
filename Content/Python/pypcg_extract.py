import gc
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

# pypcg_extract.py -- write the official IR of the 18 stage graphs (or any listed graphs).
# Args: {"graphs": [asset paths], "out": "Tools/pypcg/official_ir"}  (defaults: the 18 stages)
# Gate: totals over the 18 must be 1509 nodes and 1780 edges (measured 2026-10-13).


def run(args):
    from pypcg import extract, ir as pir, stages
    paths = args.get("graphs") or [stages.official_path(s[0]) for s in stages.STAGES]
    out_dir = os.path.join(_REPO, args.get("out", "Tools/pypcg/official_ir"))
    rows, nodes, edges = [], 0, 0
    seed_warnings = []
    for path in paths:
        extract.LAST_SEED_WARNINGS[:] = []
        g_ir = extract.export_path(path)
        for cls_name in extract.LAST_SEED_WARNINGS:
            if cls_name not in seed_warnings:
                seed_warnings.append(cls_name)
        n = len(g_ir["nodes"])
        e = sum(len(p["edges"]) for x in g_ir["nodes"] for p in x["inputs"])
        nodes, edges = nodes + n, edges + e
        pir.dump(g_ir, os.path.join(out_dir, path.rsplit("/", 1)[-1] + ".json"))
        rows.append({"graph": path, "nodes": n, "edges": e, "params": len(g_ir["params"]),
                     "boxes": len(g_ir["comment_boxes"]),
                     "unbound_getters": [x["name"] for x in g_ir["nodes"]
                                         if x.get("getter_param", "").startswith("!unbound")]})
    full = not args.get("graphs")
    return {"rows": rows, "nodes": nodes, "edges": edges,
            "gate": (nodes == 1509 and edges == 1780) if full else None,
            "seed_warnings": seed_warnings}


mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
gc.collect()
