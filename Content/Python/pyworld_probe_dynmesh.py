# pyworld_probe_dynmesh.py -- READ-ONLY probe: can editor Python build a UDynamicMesh (vertices, triangles, UVs) and wrap
# it in a UPCGDynamicMeshData? Reports which GeometryScript functions exist, and times a 200x6 ribbon.
import json
import time

import unreal


def main():
    out = {}
    names = ["DynamicMesh", "PCGDynamicMeshData", "GeometryScript_MeshBasicEditFunctions",
             "GeometryScript_MeshPrimitiveFunctions", "GeometryScript_MeshUVFunctions", "GeometryScriptLibrary_MeshBasicEditFunctions",
             "GeometryScriptLibrary_MeshPrimitiveFunctions", "GeometryScriptLibrary_MeshUVFunctions",
             "GeometryScriptLibrary_MeshNormalsFunctions", "GeometryScriptLibrary_MeshMaterialFunctions"]
    out["have"] = {n: hasattr(unreal, n) for n in names}
    edit = getattr(unreal, "GeometryScriptLibrary_MeshBasicEditFunctions", None)
    if edit:
        out["edit_fns"] = sorted(f for f in dir(edit) if not f.startswith("_") and "append" in f or "add" in f)[:40]
    prim = getattr(unreal, "GeometryScriptLibrary_MeshPrimitiveFunctions", None)
    if prim:
        out["prim_fns"] = sorted(f for f in dir(prim) if f.startswith("append"))[:60]
    uvs = getattr(unreal, "GeometryScriptLibrary_MeshUVFunctions", None)
    if uvs:
        out["uv_fns"] = sorted(f for f in dir(uvs) if not f.startswith("_"))[:60]
    # a ribbon through GeometryScript's triangle-list append, if present
    try:
        m = unreal.DynamicMesh()
        n, w = 200, 6
        verts = unreal.Array(unreal.Vector)
        for i in range(n):
            for j in range(w):
                verts.append(unreal.Vector(i * 100.0, j * 100.0, 0.0))
        tris = unreal.Array(unreal.IntVector)
        for i in range(n - 1):
            for j in range(w - 1):
                a, b = i * w + j, i * w + j + 1
                c, d = (i + 1) * w + j, (i + 1) * w + j + 1
                tris.append(unreal.IntVector(a, c, b))
                tris.append(unreal.IntVector(b, c, d))
        t0 = time.perf_counter()
        fn = None
        for cand in ("append_triangles", "add_triangles_to_mesh"):
            if hasattr(edit, cand):
                fn = cand
        out["append_fn"] = fn
        if hasattr(edit, "add_vertices_to_mesh"):
            out["add_vertices_sig"] = str(getattr(edit, "add_vertices_to_mesh").__doc__)[:400]
        if hasattr(edit, "add_triangles_to_mesh"):
            out["add_triangles_sig"] = str(getattr(edit, "add_triangles_to_mesh").__doc__)[:400]
        out["t"] = round(time.perf_counter() - t0, 3)
    except Exception as ex:
        out["ribbon_error"] = str(ex)[:300]
    try:
        d = unreal.PCGDynamicMeshData()
        out["pcg_dm_fns"] = sorted(f for f in dir(d) if not f.startswith("_") and ("init" in f or "mesh" in f))[:20]
    except Exception as ex:
        out["pcg_dm_error"] = str(ex)[:200]
    print(json.dumps(out, indent=1))


main()
