# pypcg_s01_v1_faults.py -- stage 1 (Task 24): V1's partial replay (`pypcg.checks.s01.check_record`) with the editor's
# real booleans, on the recorded slim run, clean and with four planted faults (each must report). Read-only; run after
# `pypcg_v1_editor.py {"stage": 1}` has produced Saved/Reports/v2/s01/slim_42.run.json.
import copy
import json
import sys

for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]

from pypcg.checks import s01 as K  # noqa: E402
from pypcg.ue.ops import Ops  # noqa: E402

rec = json.load(open("E:/PCG_Claude/Saved/Reports/v2/s01/slim_42.run.json", encoding="utf-8"))
ops = Ops()
res = {"clean": K.check_record(rec, ops)}
r = copy.deepcopy(rec)
r["outputs"]["FlattenArea"][0][0]["z"] += 1.0
res["area_z"] = K.check_record(r, ops)
r = copy.deepcopy(rec)
r["outputs"]["FlattenArea"][0][0]["holes"] = []
res["no_hole"] = K.check_record(r, ops)
r = copy.deepcopy(rec)
r["outputs"]["CityFlatZone"][0][0]["points"][0][2] = 0.0
res["zone_z"] = K.check_record(r, ops)
r = copy.deepcopy(rec)
r["notes"] = [n.replace("footprint -149415.0625", "footprint -149000.0") for n in r["notes"]]
res["footprint"] = K.check_record(r, ops)
mcp_result = {k: v[:3] for k, v in res.items()}
