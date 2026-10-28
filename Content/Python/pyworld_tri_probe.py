# pyworld_tri_probe.py -- READ-ONLY: which way does the mesh terrain split its vertex cells into triangles?
# Traces the 4 corners and interior points of random lattice cells (585.9375 cm, vertex at the origin) and reports the
# mean / max error of bilinear and of both diagonal splits against the traced surface. Needs L_PyWorld open.
import json
import math
import random

import unreal

S = 585.9375


def trace(x, y):
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    hits = unreal.SystemLibrary.line_trace_multi(world, unreal.Vector(x, y, 500000.0), unreal.Vector(x, y, -500000.0),
                                                 unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
                                                 unreal.DrawDebugTrace.NONE, True)
    hits = hits[-1] if isinstance(hits, tuple) else hits
    best = None
    for h in hits or []:
        t = h.to_tuple()
        actor = t[9] if len(t) > 9 else None
        name = actor.get_class().get_name() if actor else ""
        if "PCG" in name or "Instanced" in name:
            continue
        z = float(t[4].z)
        best = z if best is None else min(best, z)
    return best


def main():
    rng = random.Random(1)
    err = {"bilinear": [], "diag_00_11": [], "diag_10_01": []}
    names = set()
    for _ in range(60):
        i, j = rng.randint(-150, 150), rng.randint(-150, 150)
        x0, y0 = i * S, j * S
        a, b, c, d = trace(x0, y0), trace(x0 + S, y0), trace(x0, y0 + S), trace(x0 + S, y0 + S)
        if None in (a, b, c, d):
            continue
        for _k in range(6):
            u, v = rng.random(), rng.random()
            z = trace(x0 + u * S, y0 + v * S)
            if z is None:
                continue
            bil = a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
            d1 = a + (b - a) * u + (d - b) * v if u >= v else a + (c - a) * v + (d - c) * u
            d2 = (a + (b - a) * u + (c - a) * v) if u + v <= 1.0 else (d + (c - d) * (1 - u) + (b - d) * (1 - v))
            err["bilinear"].append(abs(z - bil))
            err["diag_00_11"].append(abs(z - d1))
            err["diag_10_01"].append(abs(z - d2))
    out = {k: {"n": len(v), "mean": round(sum(v) / len(v), 2) if v else None, "max": round(max(v), 2) if v else None}
           for k, v in err.items()}
    print(json.dumps(out))


main()
