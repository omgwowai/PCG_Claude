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
# Args: {"stage": n}                                   -> stage mode (below)
#       {"assign": {"stage": n}}                       -> assign mode (Task 12)
#       {"published": {"stage": n}}                    -> published mode (Task 11): the LIVE volume's
#                                                         output against the stage's own parameters
# The two are told apart by the presence of the "assign" key, whose value must be a DICT carrying
# "stage"; `{"stage": n, "assign": true}` is not a form this file accepts.
# Stage mode: for every Saved/Reports/v2/sNN/slim_<seed>.run.json:
#   - replay: when the inputs were recordable, run the stage again with the same params and seed and
#     require identical outputs (determinism);
#   - pypcg.checks.sNN.check(inputs or None, params, outputs, ops, official) when that module exists;
#     official is the volume's current output when it holds its official graph (after V2's restore).
# Assign mode (Task 12): every Assign_Assets call the official graph holds is rebuilt in Python from
# its OWN recorded settings, with one target point, and the Python expansion is reported -- the phase
# `{"assign": {"stage": n}}` of the plan. See `assign_phase` for what it does and does not compare.

ASSIGN_SUBGRAPH = "/PCGPrimitives/Primitives/Assign/Assign_Assets"

# The Assign_Assets pin names mapped onto the keys `pypcg.geo.assets.expand` reads. The dictionary is
# the seam between the graph and the helper, and it is the reason this table is explicit: without it
# every parameter recorded from the graph would arrive at `expand` under a name it does not read and
# be silently replaced by its default. Task 12's review found exactly that.
#
# Three pins are deliberately mapped to None, which `assign_calls` reads as "collected but not
# honoured by `expand`":
#   MatchScaleToInputBounds  the ratio is reported as `$Scale` either way; whether the primitive
#                            also writes it into the input points' `$Scale` is unmeasured
#   UseIndexattribute / IndexAttribute
#                            the index-attribute pick (`Branch_1_Index`) is not implemented; `choose`
#                            always draws
# The four graph-override pins are not parameters of the computation at all and are not listed.
ASSIGN_PARAM_KEYS = {
    "PositionOffset": "position_offset",
    "RotationOffset": "rotation_offset",
    "ScaleOffset": "scale_offset",
    "ExtentsScale": "extents_scale",
    "UniformScale": "uniform_scale",
    "UseMeshBounds": "use_mesh_bounds",
    "UseMeshAttribute": "use_mesh_attribute",
    "MeshAttribute": "mesh_attribute",
    "RandomPositionRange": "random_position_range",
    "RandomRotationRange": "random_rotation_range",
    "RandomScaleRange": "random_scale_range",
    "MatchScaleToInputBounds": None,
    "UseIndexattribute": None,
    "IndexAttribute": None,
}
# The three `TransformPoints_2` pins, whose values only mean anything together with an `rng`.
ASSIGN_RANDOM_PINS = ("RandomPositionRange", "RandomRotationRange", "RandomScaleRange")


def assign_calls(ir):
    """Every Assign_Assets node of a graph IR, with its settings and its `Assets` override.

    The overrides come from the IR the exporter writes (a subgraph node's `overrides` is its instance
    override bag), so nothing here has to reach into the property bag by hand.

    `params` is keyed the way `pypcg.geo.assets.expand` reads its `params` dict (see
    `ASSIGN_PARAM_KEYS`), and `unhonoured` lists the pins the graph sets that `expand` does not read,
    so a caller can see the gap rather than silently lose it. `random` is True when this call has a
    non-zero random range: a caller that does not supply an `rng` then cannot reproduce the
    primitive's draw.

    `seed` is the node's OWN `Seed` pin (instance override first, then the settings' value). It is
    recorded for a reader and is deliberately NOT fed to `expand`: the primitive spends that seed on
    `TransformPoints_2`'s draws and on the asset pick, while `expand` takes only `params["rng"]`, and
    this phase supplies no rng. A caller that wants to reproduce a random call must construct an
    `rng` and pass the call's `seed` to it; nothing today does, which is what `random_calls`
    reports."""
    out = []
    for node in ir.get("nodes", []):
        sub = node.get("subgraph") or ""
        if ASSIGN_SUBGRAPH not in sub:
            continue
        ov = dict(node.get("overrides") or {})
        params, unhonoured = {}, []
        for pin, key in ASSIGN_PARAM_KEYS.items():
            if pin not in ov:
                continue
            if key is None:
                unhonoured.append(pin)
            else:
                params[key] = ov[pin]
        random = any(_non_zero(ov.get(p)) for p in ASSIGN_RANDOM_PINS)
        out.append({"node": node["name"], "title": node.get("title", ""),
                    "assets": list(ov.get("Assets") or []),
                    "params": params, "unhonoured": unhonoured, "random": random,
                    "seed": (ov.get("Seed", (node.get("settings") or {}).get("Seed")))})
    return out


def _non_zero(v):
    """A Vector/Rotator override that is not all-zero, as a truth test for `assign_calls`' `random`."""
    if v is None:
        return False
    if isinstance(v, dict):
        return any(abs(float(x)) > 0.0 for x in v.values())
    if isinstance(v, (int, float)):
        return abs(float(v)) > 0.0
    return any(abs(float(x)) > 0.0 for x in v)


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
    """Expand every Assign_Assets call of stage `n` with ONE fixture target and report what came back.

    `fixtures` is the list of recorded run records. `_assign_target` uses the first run's first output
    point when one exists (a real point of this stage) and a fixed box otherwise, so this runs whether
    or not the stage has recorded runs; the caller reports how many it had. A call fails when it
    records no `Assets`, when one of its assets does not load, or when the expansion yields no points.

    Each `checked` row also carries `unhonoured` (pins the graph sets that `expand` does not read) and
    `random` (the call has a non-zero random range, so its real output cannot be reproduced without
    the primitive's own random stream). Those are reported, not failed: they are gaps in the helper's
    coverage, not wrong behaviour."""
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
                        "loc0": ours["loc"][0] if ours["loc"] else None,
                        "unhonoured": list(call.get("unhonoured") or []),
                        "random": bool(call.get("random"))})
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
    # `random_calls` counts the calls whose real output cannot be reproduced here: a non-zero random
    # range draws from `TransformPoints_2`'s own seeded stream, and this phase supplies no `rng`. A
    # clean `failures` list is therefore not a claim that those calls agree with the primitive.
    random_calls = [c["node"] for c in checked if c.get("random")]
    unhonoured = sorted({p for c in checked for p in (c.get("unhonoured") or [])})
    return {"stage": n, "calls": len(calls), "runs": len(fixtures),
            "target": {k: list(v) if isinstance(v, tuple) else v for k, v in _assign_target(fixtures).items()},
            "expanded": checked, "random_calls": random_calls,
            "random": bool(random_calls), "unhonoured_pins": unhonoured,
            "failures": failures[:20]}


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


HIGHWAY_SPLINES = ("HighwaySpline2", "HighwaySpline3")


def _highway_spline_lengths():
    """The two highway spline actors' own lengths, in cm, read off the scene the graph reads. Empty
    when the stage's level does not carry them."""
    from pypcg.profiles import official
    out = []
    for role in HIGHWAY_SPLINES:
        path = official.ROLES.get(role)
        if not path:
            return []
        obj = unreal.load_object(None, path)
        if obj is None:
            return []
        comps = obj.get_components_by_class(unreal.SplineComponent)
        if not comps:
            return []
        out.append(comps[0].get_spline_length())
    return out


def published_phase(n, as_name, width_name):
    """`{"published": {"stage": n, "as": <param>, "width": <param>}}`: the LIVE volume's published
    output checked against a parameter, on the live volume rather than on a recorded run.

    Needed because stage 8's published polygon comes out of NATIVE nodes, so the recorded run holds
    the Python node's splines and never sees it: `check()`'s polygon half otherwise only runs when a
    volume happens to hold its official graph. This reads the volume's generated output as
    `pypcg.geo` values and calls the stage's own `check()`. `as_name` is the parameter the published
    AREA is measured against through the highway spline lengths (default `Highway_Width`); the
    lengths come from the volume's own inputs where the check can reach them, else from the graph.

    Stage 8 only. Returns the check's failures plus the numbers it was judged on, so the bound is
    visible even when it passes."""
    from pypcg import census, geo, stages
    from pypcg.ue import convert
    module = stages.spec(n)
    try:
        chk = importlib.import_module("pypcg.checks.s%02d" % n)
    except ImportError:
        return {"stage": n, "abort": "no checks module"}
    pc = census.component(n)
    outs = {}
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        d = td.get_editor_property("data").get_editor_property("data")
        try:
            value = convert.from_pcg(d)
        except TypeError:
            continue
        for t in td.get_editor_property("tags"):
            if ":" not in str(t):
                outs.setdefault(str(t), []).append((value, [str(t)]))
    params = {name: spec.default for name, spec in module.PARAMS.items()}
    # the volume's own instance overrides win over the declared defaults
    inst = pc.get_editor_property("graph_instance")
    over = json.loads(unreal.PyPCGToolsLibrary.export_instance_overrides(inst)) if inst else {}
    params.update({k: v for k, v in over.items() if k in params})
    # the highway spline lengths, from the stage's own recorded run when there is one
    ins = None
    run = os.path.join(_REPO, "Saved", "PyPCG", "runs", "s%02d.json" % n)
    if os.path.exists(run):
        with open(run, encoding="utf-8") as fh:
            rec = json.load(fh)
        try:
            ins = {pin: [(geo.from_json(v), frozenset(t)) for v, t in items]
                   for pin, items in rec["inputs"].items()}
        except ValueError:
            ins = None
    # the LIVE volume has no recorded input to read the spline lengths from, but the check's area
    # clause needs them; take them off the highway spline actors the graph reads, which is what the
    # recorded path measures too. Only stages whose published output is a polygon need this.
    lengths = None
    if outs.get("Highway"):
        lengths = _highway_spline_lengths()
    failures = chk.check(ins, params, outs, None)
    if lengths:
        failures += chk._published_area(outs, params.get(width_name, 0.0), ins, lengths)
    polys = [v for v in geo.values(outs.get("Highway", [])) if hasattr(v, "outer")]
    detail = {"stage": n, "volume": census.volume(n).get_actor_label(), "params": params,
              "items": {k: len(v) for k, v in outs.items()}, "inputs_recorded": ins is not None}
    if polys:
        from pypcg.stages import s08_highways
        detail["half_width_cm"] = [round(chk.half_width(p), 1) for p in polys]
        detail["area_m2"] = round(sum(geo.area_m2(p) for p in polys), 2)
        detail["published_width_cm"] = s08_highways.published_width_cm(params.get(width_name, 0.0))
        want_half = 0.5 * params.get(width_name, 0.0) + s08_highways.EXPAND_CM
        detail["want_half_width_cm"] = want_half
        detail["width_tol_cm"] = chk.WIDTH_TOL_CM
        detail["width_error_cm"] = round(max(abs(h - want_half) for h in detail["half_width_cm"]), 1)
        detail["area_tol"] = chk.PUBLISHED_AREA_TOL
        if lengths:
            want_area = s08_highways.published_width_cm(params.get(width_name, 0.0)) * sum(lengths) / 1e4
            detail["spline_length_m"] = round(sum(lengths) / 100.0, 2)
            detail["want_area_m2"] = round(want_area, 2)
            detail["area_error"] = round(100.0 * (detail["area_m2"] - want_area) / want_area, 3)
    detail["failures"] = failures[:20]
    return detail


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
    if "published" in _args:
        _pub = _args["published"]
        mcp_result = json.loads(json.dumps(published_phase(int(_pub["stage"]), _pub.get("as", "Highway_Width"),
                                                           _pub.get("width", "Highway_Width")), default=str))
    elif "assign" in _args:
        mcp_result = json.loads(json.dumps(assign_phase(int(_args["assign"]["stage"]
                                                         if isinstance(_args["assign"], dict)
                                                         else _args["stage"])), default=str))
    else:
        mcp_result = json.loads(json.dumps(run_stage(_args), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
