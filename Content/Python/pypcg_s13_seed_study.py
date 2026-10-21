import gc
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pypcg_s13_seed_study.py -- the editor half of Tools/pypcg/data/s13_seed_study.json (the stage 13 rows of
# docs/pypcg-v2-thresholds.md); the distiller is Tools/pypcg/s13_seed_study.py.
#   {"official_seed": k}   put the OFFICIAL LeftOverLots graph on the stage-13 volume with its shipped
#                          overrides and COMPONENT seed k, and generate (one generation). Read it in the next
#                          call with pypcg_compare_stage.py {"phase": "read", "stage": 13, "as": "offseed_<k>"}.
#                          Every Filter_RandomChoice of the graph seeds from its own Seed combined with the
#                          component's, so k moves all eight draws. Restore with V2's gen official / restore.
# Needs V2's prepare (Saved/Reports/v2/_state.json). Never saves anything. It LEAVES the component seed at k:
# restore it with V2's gen official (or restore) -- V2's slim gen now also resets it (Task 18: the kept fitting
# nodes draw from it, and a slim run under component seed 31337 changed 2 of 496 plaza items).


def run(args):
    from pypcg import census, level, stages
    # Final review I2: swaps the stage-13 volume's graph and seed; the demo is the only level it may touch.
    refused = level.require(level.DEMO, "pypcg_s13_seed_study.py")
    if refused:
        return refused
    n = 13
    state = json.load(open(os.path.join(_REPO, "Saved", "Reports", "v2", "_state.json"), encoding="utf-8"))
    shipped = state[stages.name(n)]
    pc = census.component(n)
    pc.set_graph(unreal.EditorAssetLibrary.load_asset(shipped["graph"].split(".")[0]))
    applied = census.apply_overrides(pc, shipped["overrides"])
    pc.set_editor_property("seed", int(args["official_seed"]))
    pc.activate(True)
    pc.generate_local(True)
    return {"stage": n, "graph": pc.get_graph().get_path_name(), "seed": int(pc.get_editor_property("seed")),
            "overrides": applied, "next": "read {\"as\": \"offseed_%d\"}, then gen official / restore" % int(args["official_seed"])}


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
