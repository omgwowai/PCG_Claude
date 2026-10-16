import gc
import importlib
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

# pypcg_v1_editor.py -- V1 checks with the editor's real booleans, on the runs V2 recorded (spec 3, V1).
# Args: {"stage": n}. For every Saved/Reports/v2/sNN/slim_<seed>.run.json:
#   - replay: when the inputs were recordable, run the stage again with the same params and seed and
#     require identical outputs (determinism);
#   - pypcg.checks.sNN.check(inputs or None, params, outputs, ops, official) when that module exists;
#     official is the volume's current output when it holds its official graph (after V2's restore).


def _official_outputs(n):
    from pypcg import census, stages
    from pypcg.ue import convert
    pc = census.component(n)
    g = pc.get_graph()
    if g is None or g.get_path_name().split(".")[0] != stages.official_path(n):
        return None
    out = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        d = td.get_editor_property("data").get_editor_property("data")
        try:
            value = convert.from_pcg(d)
        except TypeError:
            continue
        for t in td.get_editor_property("tags"):
            if ":" not in str(t):
                out.setdefault(str(t), []).append(value)
    return out


def run(args):
    from pypcg import geo, stage_api, stages
    from pypcg.ue.ops import Ops
    n = int(args["stage"])
    official = _official_outputs(n)
    d = os.path.join(_REPO, "Saved", "Reports", "v2", "s%02d" % n)
    files = sorted(f for f in os.listdir(d) if f.endswith(".run.json")) if os.path.isdir(d) else []
    if not files:
        return {"abort": "no recorded runs under %s; run V2 first" % d}
    try:
        checks = importlib.import_module("pypcg.checks.s%02d" % n)
    except ImportError:
        checks = None
    module, ops = stages.spec(n), Ops()
    failures, replayed, deterministic = [], 0, True
    for f in files:
        rec = json.load(open(os.path.join(d, f), encoding="utf-8"))
        outputs = {pin: [(geo.from_json(v), tags) for v, tags in items] for pin, items in rec["outputs"].items()
                   if all(not v.get("truncated") for v, _ in items)}
        try:
            inputs = {pin: [(geo.from_json(v), frozenset(tags)) for v, tags in items] for pin, items in rec["inputs"].items()}
        except ValueError:
            inputs = None
        if inputs is not None:
            again, _ = stage_api.execute(module, inputs, rec["params"], ops)
            replayed += 1
            same = {p: [[geo.to_json(v), list(t)] for v, t in items] for p, items in again.items()} == \
                {p: [[v, list(t)] for v, t in items] for p, items in rec["outputs"].items()}
            if not same:
                deterministic = False
                failures.append("%s: replay with the same seed gave different outputs" % f)
        if checks is not None:
            failures += ["%s: %s" % (f, x) for x in checks.check(inputs, {k: v for k, v in rec["params"].items()
                                                                         if k != stage_api.SEED}, outputs, ops, official)]
    return {"stage": n, "runs": len(files), "replayed": replayed, "deterministic": deterministic,
            "official_seen": official is not None, "failures": failures[:40]}


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
