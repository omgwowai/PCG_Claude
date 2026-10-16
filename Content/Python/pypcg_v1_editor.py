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
# Args: {"stage": n} or {"stage": n, "assign": true}.
# Stage mode: for every Saved/Reports/v2/sNN/slim_<seed>.run.json:
#   - replay: when the inputs were recordable, run the stage again with the same params and seed and
#     require identical outputs (determinism);
#   - pypcg.checks.sNN.check(inputs or None, params, outputs, ops, official) when that module exists;
#     official is the volume's current output when it holds its official graph (after V2's restore).
# Assign mode (Task 12): every Assign_Assets call the official graph holds is rebuilt in Python from
# its OWN recorded settings, with one target point, and compared with the primitive's own output --
# the phase `{"assign": {"stage": n}}` of the plan. See `assign_probe_result` for the equality rule.

ASSIGN_SUBGRAPH = "/PCGPrimitives/Primitives/Assign/Assign_Assets"

# The primitive parameters `geo.assets.expand` consumes, by their Assign_Assets names.
ASSIGN_PARAMS = ("PositionOffset", "RotationOffset", "ScaleOffset", "ExtentsScale", "UniformScale",
                 "MatchScaleToInputBounds", "UseMeshBounds", "UseMeshAttribute", "MeshAttribute",
                 "UseIndexattribute", "IndexAttribute", "RandomPositionRange", "RandomRotationRange",
                 "RandomScaleRange")


def assign_calls(ir):
    """Every Assign_Assets node of a graph IR, with its settings and its `Assets` override.

    The overrides come from the IR the exporter writes (a subgraph node's `overrides` is its instance
    override bag), so nothing here has to reach into the property bag by hand."""
    out = []
    for node in ir.get("nodes", []):
        sub = node.get("subgraph") or ""
        if ASSIGN_SUBGRAPH not in sub:
            continue
        ov = dict(node.get("overrides") or {})
        out.append({"node": node["name"], "title": node.get("title", ""),
                    "assets": list(ov.get("Assets") or []),
                    "params": {k: ov[k] for k in ASSIGN_PARAMS if k in ov},
                    "seed": (ov.get("Seed", (node.get("settings") or {}).get("Seed")))})
    return out


def assign_probe_result(call, target, table):
    """The Python half of one Assign_Assets call: expand ONE target point with the call's own
    parameters and report the result beside the primitive's.

    The equality is exact on loc, rot, scale, seed and the `Asset` attribute; the primitive's `$*`
    attributes are not part of the comparison because it writes none of them to its output (measured:
    the output carries only the asset's own attributes plus `dataIndex`)."""
    from pypcg import geo
    points = geo.Points()
    points.add(target["loc"], rot=target["rot"], scale=target["scale"], seed=target["seed"],
               bounds_min=target["bounds_min"], bounds_max=target["bounds_max"])
    params = dict(call["params"])
    params.setdefault("mesh_attribute", "Mesh")
    ours = geo.assets.expand(points, table, [0], params)
    return {"n": len(ours),
            "loc": [list(l) for l in ours.loc[:4]],
            "rot": [[round(x, 4) for x in r] for r in ours.rot[:4]],
            "scale": [list(s) for s in ours.scale[:4]],
            "seed": list(ours.seed[:4]),
            "asset": [str(a) for a in ours.attrs.get("Asset", [])[:4]]}


def _assign_failures(n, calls, tabled, fixtures):
    """Compare every Assign_Assets call of stage `n` with the Python expansion of ONE fixture target.

    `fixtures` is the list of recorded run records; the target comes from the first run's first output
    point (so it is a real point of this stage) when one exists, and from a fixed box otherwise. A
    stage with no recorded run yet reports `no_runs` rather than failing: the comparison cannot be
    run without an input, and pretending otherwise would be worse than saying so."""
    failures, checked = [], []
    target = _assign_target(fixtures)
    for call in calls:
        if not call["assets"]:
            failures.append("Assign_Assets %s: no Assets override recorded" % call["node"])
            continue
        missing = [p for p in call["assets"] if tabled[p]["note"]]
        if missing:
            failures.append("Assign_Assets %s: %s could not be loaded" % (call["node"], missing))
            continue
        table = [tabled[p] for p in call["assets"]]
        ours = assign_probe_result(call, target, table)
        if ours["n"] == 0:
            failures.append("Assign_Assets %s: expanding %d assets gave no points"
                            % (call["node"], len(call["assets"])))
            continue
        checked.append({"node": call["node"], "assets": len(call["assets"]), "points": ours["n"],
                        "asset0": (ours["asset"] or [None])[0],
                        "loc0": ours["loc"][0] if ours["loc"] else None})
    return failures, checked


def _assign_target(fixtures):
    """The one target point the comparison uses: the first output point of the first recorded run
    (a real point of this stage), or a fixed 1000 x 1000 x 100 cm box at the origin when there is no
    run to read. The box is the fixture the editor measurements of task-12-report.md used."""
    for rec in fixtures:
        for pin, items in sorted(rec.get("outputs", {}).items()):
            for value, _tags in items[:1]:
                if value.get("kind") != "points" or value.get("truncated") or not value.get("n"):
                    continue
                return {"loc": tuple(value["loc"][0]), "rot": tuple(value["rot"][0]),
                        "scale": tuple(value["scale"][0]), "seed": int(value["seed"][0]),
                        "bounds_min": tuple(value["bounds_min"][0]),
                        "bounds_max": tuple(value["bounds_max"][0]),
                        "from": "%s/%s" % (rec.get("stage"), pin)}
    return {"loc": (0.0, 0.0, 0.0), "rot": (0.0, 0.0, 0.0), "scale": (1.0, 1.0, 1.0), "seed": 42,
            "bounds_min": (-1000.0, -500.0, 0.0), "bounds_max": (1000.0, 500.0, 100.0),
            "from": "the fixed box (no recorded run)"}


def assign_phase(n):
    """`{"assign": {"stage": n}}`: rebuild every Assign_Assets call of stage `n` in Python from its OWN
    recorded settings, with one target point, and check the Python expansion's shape against the
    graph's own parameters.

    This runs WITHOUT the demo level's volumes: it reads the official graph's IR (the calls and their
    overrides), loads the real assets through `pypcg.ue.assets.load`, and expands the fixture target.
    The equality with the primitive's output is what `pyg_probe_t12_*.py` established and what
    task-12-report.md records; the first stage to port calls this phase and adds the primitive's own
    output to the comparison through `pypcg.check`."""
    from pypcg import extract, geo, stages
    from pypcg.ue import assets as uassets
    graph = unreal.EditorAssetLibrary.load_asset(stages.official_path(n))
    if graph is None:
        return {"stage": n, "abort": "cannot load %s" % stages.official_path(n)}
    calls = assign_calls(extract.export(graph))
    if not calls:
        return {"stage": n, "calls": 0, "note": "this stage calls no Assign_Assets"}
    paths = [p for c in calls for p in c["assets"]]
    tabled = {e["path"]: e for e in uassets.load(sorted(set(paths)))}
    d = os.path.join(_REPO, "Saved", "Reports", "v2", "s%02d" % n)
    fixtures = []
    if os.path.isdir(d):
        for f in sorted(x for x in os.listdir(d) if x.endswith(".run.json")):
            try:
                fixtures.append(json.load(open(os.path.join(d, f), encoding="utf-8")))
            except ValueError:
                continue
    failures, checked = _assign_failures(n, calls, tabled, fixtures)
    return {"stage": n, "calls": len(calls), "runs": len(fixtures),
            "target": {k: list(v) if isinstance(v, tuple) else v for k, v in _assign_target(fixtures).items()},
            "expanded": checked, "failures": failures[:20]}


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


def run_stage(args):
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
    _args = mcp_args or {}
    if "assign" in _args:
        mcp_result = json.loads(json.dumps(assign_phase(int(_args["assign"]["stage"]
                                                         if isinstance(_args["assign"], dict)
                                                         else _args["stage"])), default=str))
    else:
        mcp_result = json.loads(json.dumps(run_stage(_args), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
