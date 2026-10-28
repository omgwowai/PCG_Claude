"""What every Python Data Processor node runs (spec 2.2, ruling N4). The node's inline script is:

    from pypcg import host
    host.run("s06_districts", globals())

run() drops every cached pypcg module first, so an edited stage or library file takes effect on the
next generation. It converts the node's inputs to pypcg.geo values, runs the stage, and writes the
outputs back. UObjects stay in locals (traps.md 25). Importable offline: unreal is imported inside run().
"""
import importlib
import os
import sys
import time


def inline_script(stage_name):
    return 'from pypcg import host\nhost.run("%s", globals())\n' % stage_name


def _fresh():
    for name in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
        del sys.modules[name]


def run(stage_name, scope):
    _fresh()
    import unreal
    from pypcg import stage_api
    from pypcg.ue import convert, ops as ue_ops
    module = importlib.import_module("pypcg.stages." + stage_name)
    data_in, data_out = scope["data_in"], scope["data_out"]
    t0 = time.perf_counter()
    params = stage_api.unprefixed(convert.read_params(data_in, stage_api.PARAMS_PIN), module.STAGE)
    # The input polygons' own data objects, for this run only (traps.md 25): a polygon the stage hands
    # back unchanged is forwarded as the engine's object, frame and local coordinates included (Task 18).
    registry = {}
    splines = bool(getattr(module, "FORWARD_SPLINES", False))
    inputs = {pin: convert.read_pin(data_in, pin, registry, splines) for pin in module.INPUTS}
    outputs, ctx = stage_api.execute(module, inputs, params, ue_ops.Ops())
    exact = bool(getattr(module, "EXACT_ROTATIONS", False))       # stage 12: points keep their engine quaternions
    exact_rot = bool(getattr(module, "EXACT_SPLINE_ROTATORS", False))   # stage 16: spline rotations keep doubles
    count = 0
    for pin, items in outputs.items():
        for value, tags in items:
            data_out.add_to_collection(convert.to_pcg(value, registry, exact, exact_rot), pin, list(tags))
            count += 1
    registry.clear()
    seconds = time.perf_counter() - t0
    if os.environ.get(stage_api.RECORD_ENV):
        stage_api.record(module, inputs, params, outputs, seconds, ctx)
    if os.environ.get(stage_api.CAPTURE_ENV):
        stage_api.capture(module, inputs, params)
    unreal.log("PyPCG %s: %d outputs in %.2f s%s" % (stage_name, count, seconds,
                                                     "; notes: " + "; ".join(ctx.notes) if ctx.notes else ""))
