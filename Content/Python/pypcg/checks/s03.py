"""V1 checks of stage 3, BG_Mountains (spec 3, V1).

check() verifies the task's invariants on every recorded run, against the recorded cliff points:
  - one output point per source point, in the source order;
  - X and Y are the source's x AnchorScaleXY, Z is clamp(source Z x AnchorScaleZ + AnchorZ, ZMin, ZMax);
  - pitch and roll are 0, the yaw is the source's;
  - every attribute survives the round trip, `Mesh` above all (the spawner selects the mesh by it).
The official graph publishes no output (its output node is unwired), so there is no oracle on
outputs here; V2 compares the spawned instances, and the Task 14 report records the per-instance
comparison with the official spawner (`pyg_probe_t14_ism.py`)."""
from pypcg.stages import s03_bg_mountains as S


def check(inputs, params, outputs, ops, official=None):
    f = []
    if inputs is None:
        return f
    sources = [v for v, _ in inputs.get("Cliffs", []) if len(v)]
    stamped = [v for v, _ in outputs.get("Points", [])]
    if len(sources) != len(stamped):
        return ["%d cliff data items in, %d out" % (len(sources), len(stamped))]
    (tx, ty, tz), (sx, sy, sz) = S.anchor(params)
    lo, hi = float(params["ZMin"]), float(params["ZMax"])
    for src, out in zip(sources, stamped):
        if len(src) != len(out):
            f.append("%d cliff points in, %d out" % (len(src), len(out)))
            continue
        for name in src.attrs:
            if out.types.get(name) != src.types[name] or out.attrs.get(name) != src.attrs[name]:
                f.append("attribute %s did not survive the stamp" % name)
        for i in range(len(src)):
            x, y, z = src.loc[i]
            want = (x * sx + tx, y * sy + ty, S.clamp(z * sz + tz, lo, hi))
            if any(abs(a - b) > 1e-6 for a, b in zip(out.loc[i], want)):
                f.append("point %d is at %s, the stamp says %s" % (i, out.loc[i], want))
                break
            r = out.rot[i]
            if r[0] != 0.0 or r[2] != 0.0 or abs(r[1] - src.rot[i][1]) > 1e-9:
                f.append("point %d has rotation %s, source yaw %s" % (i, r, src.rot[i][1]))
                break
    return f
