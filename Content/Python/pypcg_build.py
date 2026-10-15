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
_DRAFTS = os.path.join(_REPO, "Tools", "pypcg")
if _DRAFTS not in sys.path:
    sys.path.insert(0, _DRAFTS)
for _m in [m for m in sys.modules if m == "reference_drafts" or m.startswith("reference_drafts.")]:
    del sys.modules[_m]

# pypcg_build.py -- build stage graphs from their Python form and check them (L2, spec 3.6).
# Args: {"stages": [n, ...] | "all", "profile": "official" | "town", "save": true}
# One or a few stages per call: the build blocks the editor until it returns.
import importlib


def run(args):
    from pypcg import build, compare, dsl, extract, stages
    from pypcg.profiles import official
    profile_name = args.get("profile", "official")
    town = importlib.import_module("pypcg.profiles.town") if profile_name == "town" else None
    wanted = [s[0] for s in stages.STAGES] if args.get("stages", "all") == "all" else list(args["stages"])
    save = bool(args.get("save", True))
    fresh = dsl.library()["fresh_seeds"]
    rows = []
    for n in wanted:
        name = stages.name(n)
        g = __import__("reference_drafts").graph(n)
        ir_off = g.to_ir(official)
        official_ir = extract.export_path(stages.official_path(n))
        mapping, _, _ = compare.match(compare.view(ir_off, fresh), compare.view(official_ir, fresh))
        if town is None:
            target = "/Game/PyPCG/Official/" + name
            undeclared = []
            diffs = build.build(ir_off, target, official_ir, (mapping, official_ir), fresh, check_layout=True, save=save)
        else:
            target = "/Game/PyPCG/Town/" + name
            ir_town = g.to_ir(town)
            undeclared = compare.undeclared_changes(ir_town, ir_off)
            diffs = build.build(ir_town, target, ir_town, (mapping, official_ir), fresh, check_layout=False,
                                save=save and not undeclared)
        rows.append({"stage": n, "graph": name, "asset": target, "diffs": len(diffs),
                     "undeclared": undeclared, "first": compare.format_diffs(diffs, 15),
                     "sites": len(g.to_ir(town or official)["sites"]),
                     "cdo_resets": list(build.LAST_CDO_RESETS)})
    path = os.path.join(_REPO, "Saved", "Reports", "pypcg_build_%s.json" % profile_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1, ensure_ascii=False)
    return rows


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
