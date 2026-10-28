# pyworld_probe_dynmesh3.py -- READ-ONLY: find the GeometryScript libraries by their Python names, build a small ribbon
# mesh (vertices + triangles + one UV channel + normals) and wrap it in a PCGDynamicMeshData; time a big one.
import json
import time

import unreal


def main():
    out = {}
    libs = {n: getattr(unreal, n) for n in dir(unreal) if n.startswith("GeometryScript_")}
    out["libs"] = sorted(libs)
    edit = libs.get("GeometryScript_MeshEdits")
    out["edit"] = sorted(f for f in dir(edit) if f[0].islower() and not f.startswith("_"))[:60] if edit else None
    print(json.dumps(out, indent=0))


main()
