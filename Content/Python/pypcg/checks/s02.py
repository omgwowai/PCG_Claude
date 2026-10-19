"""V1 checks of stage 2, BG_Buildings (spec 3, V1).

check() verifies the task's invariants on every recorded run:
  - every point lies on the ring: inside the OuterSize square, outside the CenterSize square;
  - every yaw is within +-MaxYaw, pitch and roll are 0, Z is 0;
  - the cull kept round(sampled x KeepRatio) points, where `sampled` is what the run's sampler
    produced (the stage records it as the note "sampled N"); a run record carries no notes when it is
    replayed from outputs only, so the count is then checked against the grid's expectation instead;
  - the points are the official sampler's grid: no X or Y below the first cell's lower edge.
The official graph's own output is points after `Spawn_Assets` and is not compared here: V2 does that
(count, bounds and instance shares)."""
import math

from pypcg.stages import s02_bg_buildings as S

SIGMAS = 5.0


def check(inputs, params, outputs, ops, official=None, notes=()):
    f = []
    outer, inner = S.halves(params)
    max_yaw = abs(float(params["MaxYaw"]))
    cell = S.cell_size(float(params["PointsPerSquaredMeter"]))
    n = 0
    for pts, _ in outputs.get("Points", []):
        n += len(pts)
        for (x, y, z), (pitch, yaw, roll) in zip(pts.loc, pts.rot):
            if not S.on_ring(x, y, outer, inner):
                f.append("a point at (%.0f, %.0f) is off the ring" % (x, y))
                break
            if abs(yaw) > max_yaw + 1e-9 or pitch != 0.0 or roll != 0.0 or z != 0.0:
                f.append("a point at (%.0f, %.0f) has rotation %s and Z %s" % (x, y, (pitch, yaw, roll), z))
                break
            if cell and (min(x, y) < math.ceil(-outer / cell) * cell):
                f.append("a point at (%.0f, %.0f) is below the sampler's first cell" % (x, y))
                break
    ratio = float(params["KeepRatio"])
    sampled = [int(s.split()[1]) for s in notes if s.startswith("sampled ")]
    if sampled:
        want = int(round(sampled[0] * ratio))
        if n != want:
            f.append("kept %d of %d sampled points, KeepRatio %.6g says %d" % (n, sampled[0], ratio, want))
    else:
        mean = S.expected_sampled(params) * ratio
        sd = math.sqrt(max(mean * (1.0 - ratio), 1.0))
        if abs(n - mean) > SIGMAS * sd:
            f.append("kept %d points, the grid expects %.1f +- %.1f" % (n, mean, sd))
    return f
