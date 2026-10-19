"""The contract between a Python stage and the node that runs it (spec 2.2). No unreal import.

A stage module defines:
  STAGE    the Feishu step number (0 = the host probe)
  DOC      one paragraph; it becomes the slim graph's description
  RANDOM   True when run() draws from ctx.rng
  PARAMS   {name: Param(...) or a plain default}; the slim graph gets one user parameter and one
           getter per entry, plus "Seed" (added here, never declared by the stage)
  INPUTS   {pin: kind}; kind documents what arrives: "spline" | "polygon" | "area" | "points" |
           "surface" | "param" | "any"
  OUTPUTS  (pin, ...)
  RECORD   optional: the run record's file name (default "sNN"), for a stage's second Python node
  run(inputs, params, ctx) -> {pin: [(value, [tags])]}
           inputs is {pin: [(value, frozenset(tags))]}, values are pypcg.geo types (or a surface
           object with height(x, y)); params excludes Seed; ctx.rng is random.Random(f"{Seed}:{STAGE}")
           (ruling N1) and ctx.ops the engine services (ruling N2).
"""
import json
import os
import random

from . import geo

SEED = "Seed"
SEED_DEFAULT = 42                  # the official components' seed in the demo level
PARAMS_PIN = "Params"
RECORD_ENV = "PYPCG_RECORD"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
RUNS_DIR = os.path.join(REPO, "Saved", "PyPCG", "runs")
VALUE_TYPES = (geo.Polygon, geo.Spline, geo.Points, geo.ParamSet)


def volume_point(inputs, pin="Volume"):
    """(loc, yaw) of the volume that owns a stage, from the one-point `geo.Points` a
    `Get Actor Data (GetSinglePoint)` node delivers on the `Volume` pin.

    Measured 2026-10-17 from `Saved/PyPCG/runs/s04.json` and `s05.json`: the value is a `Points`
    with exactly one point, `loc[0]` is the volume actor's WORLD translation, `rot[0]` is
    `(pitch, yaw, roll)` -- so the yaw every official `Create_Spline_Shape` uses is `[1]` -- and the
    value also carries `scale[0]` (the actor's own scale) and `attrs["ActorReference"]`. THE ACTOR
    SCALE IS NOT APPLIED by the official shapes: stage 4 builds `(1, Length/Width, 1)` and stage 5
    `(1, 1, 1)`, so a stage that multiplied by `scale[0]` would publish a 25x tower and a 500x park.

    Returns `(None, 0.0)` when the pin is empty, so an empty pin publishes an empty output."""
    for value, _tags in inputs.get(pin, []):
        loc, rot = getattr(value, "loc", None), getattr(value, "rot", None)
        if loc:
            r = rot[0] if rot else (0.0, 0.0, 0.0)
            return tuple(loc[0]), float(r[1])
    return None, 0.0


def volume_quat(inputs, pin="Volume"):
    """The volume's own rotation QUATERNION (x, y, z, w), as the engine stores it -- what an official
    `Create_Spline_Shape` composes with. Read from `Points.quat` (filled by `convert`); a value
    without one (an offline fixture) falls back to `geo.quat_from_yaw` of `volume_point`'s yaw, which
    is the same rotation but not the same bits. None when the pin is empty."""
    for value, _tags in inputs.get(pin, []):
        if getattr(value, "loc", None):
            q = getattr(value, "quat", None)
            if q:
                return tuple(float(c) for c in q[0])
            return geo.quat_from_yaw(volume_point(inputs, pin)[1])
    return None


def snapshot(p):
    """The geometry `unchanged` compares: a polygon's outer, holes and z as plain tuples; a spline's control
    points, closed / linear flags, tangents and rotations."""
    if isinstance(p, geo.Spline):
        return ([tuple(q) for q in p.points], bool(p.closed), bool(p.linear),
                [(tuple(a), tuple(b)) for a, b in p.tangents] if p.tangents else None,
                [tuple(r) for r in p.rotations] if p.rotations else None)
    return ([tuple(q) for q in p.outer], [[tuple(q) for q in h] for h in p.holes], p.z)


def unchanged(v, registry):
    """The registered input object a polygon came from, when a stage hands that polygon back with its
    geometry unchanged; else None (Task 18, s13.md 4.6). `registry` maps `Polygon.source` -> (object,
    `snapshot` taken when the input was read); `pypcg.ue.convert` fills it for one run and forwards what this
    returns. A polygon mutated in place, given another z, or rebuilt (a copy carries no `source`) is not
    forwarded -- it is written anew. A spline is forwarded the same way, but only a stage that sets
    `FORWARD_SPLINES` registers its input splines (stage 11's rooftops, Task 20)."""
    if registry is None or not isinstance(v, (geo.Polygon, geo.Spline)) or v.source is None or v.source not in registry:
        return None
    obj, snap = registry[v.source]
    return obj if snapshot(v) == snap else None


class StageError(Exception):
    pass


class Param:
    """A stage parameter. type is the graph parameter type ("Double", "Int32", "Bool", "String",
    "SoftObject", ...), inferred from the default when not given."""

    def __init__(self, default, tooltip="", type=None, type_object="", category=""):
        self.default = default
        self.tooltip = tooltip
        self.type = type or _type_of(default)
        self.type_object = type_object
        self.category = category


def _type_of(v):
    if isinstance(v, bool):
        return "Bool"
    if isinstance(v, int):
        return "Int32"
    if isinstance(v, float):
        return "Double"
    if isinstance(v, str):
        return "String"
    raise StageError("no parameter type for %r; use Param(..., type=...)" % (v,))


def param_specs(module):
    """[(name, type, default, tooltip, type_object, category)], Seed first."""
    out = [(SEED, "Int32", SEED_DEFAULT, "Random seed of this step; the step number is mixed in.", "", "")]
    for name, p in module.PARAMS.items():
        if name == SEED:
            raise StageError("%s: Seed is added automatically; do not declare it" % module.__name__)
        p = p if isinstance(p, Param) else Param(p)
        out.append((name, p.type, p.default, p.tooltip, p.type_object, p.category))
    return out


def defaults(module):
    return {s[0]: s[2] for s in param_specs(module)}


class Ctx:
    def __init__(self, stage, seed, ops):
        self.stage = stage
        self.seed = seed
        # A string seed goes through SHA-512, so the sequence does not depend on PYTHONHASHSEED.
        self.rng = random.Random("%d:%d" % (seed, stage))
        self.ops = ops
        self.notes = []


def execute(module, inputs, params, ops):
    names = [s[0] for s in param_specs(module)]
    missing = [n for n in names if n not in params]
    unknown = sorted(set(params) - set(names))
    if missing or unknown:
        raise StageError("%s: parameters missing %s, unexpected %s; the stage declares %s"
                         % (module.__name__, missing, unknown, names))
    absent = [pin for pin in module.INPUTS if pin not in inputs]
    if absent:
        raise StageError("%s: no data for input pins %s" % (module.__name__, absent))
    ctx = Ctx(module.STAGE, int(params[SEED]), ops)
    outputs = module.run(inputs, {n: params[n] for n in names if n != SEED}, ctx)
    _check_outputs(module, outputs)
    return outputs, ctx


def _check_outputs(module, outputs):
    if not isinstance(outputs, dict):
        raise StageError("%s: run() must return {pin: [(value, [tags])]}" % module.__name__)
    for pin, items in outputs.items():
        if pin not in module.OUTPUTS:
            raise StageError("%s: unknown output pin %r; outputs %s" % (module.__name__, pin, list(module.OUTPUTS)))
        for item in items:
            ok = (isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], VALUE_TYPES)
                  and isinstance(item[1], (list, tuple))
                  and all(isinstance(t, str) for t in item[1]))
            if not ok:
                raise StageError("%s: output %s holds %r; expected (Polygon | Spline | Points | ParamSet, [tags])"
                                 % (module.__name__, pin, item))


def record(module, inputs, params, outputs, seconds, ctx):
    """Write the run to Saved/PyPCG/runs/sNN.json (inputs, params with Seed, outputs, notes)."""
    os.makedirs(RUNS_DIR, exist_ok=True)
    doc = {"stage": module.STAGE, "module": module.__name__, "seconds": seconds, "params": dict(params),
           "notes": list(ctx.notes),
           "inputs": {pin: [[geo.to_json(v), sorted(t)] for v, t in items] for pin, items in inputs.items()},
           "outputs": {pin: [[geo.to_json(v), list(t)] for v, t in items] for pin, items in outputs.items()}}
    # A stage's second Python node (`SlimGraph(more_modules=...)`, stage 13 first) names its own record
    # with `RECORD`, so it does not overwrite the stage's main one, which V2's `read` copies.
    path = os.path.join(RUNS_DIR, "%s.json" % (getattr(module, "RECORD", None) or "s%02d" % module.STAGE))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    return path
