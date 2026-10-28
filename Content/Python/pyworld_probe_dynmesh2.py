# pyworld_probe_dynmesh2.py -- READ-ONLY: list the unreal classes whose names mention geometry script / mesh edit.
import json

import unreal

hits = sorted(n for n in dir(unreal) if ("Function" in n or "Library" in n) and ("Mesh" in n or "Geometry" in n)
              and not n.startswith("_"))
out = {"classes": hits[:200]}
for n in hits:
    if "BasicEdit" in n or "MeshQuery" in n or ("UV" in n and "Function" in n) or "MeshNormals" in n or "MeshMaterial" in n:
        c = getattr(unreal, n)
        out[n] = sorted(f for f in dir(c) if not f.startswith("_") and f[0].islower())[:60]
print(json.dumps(out, indent=0))
