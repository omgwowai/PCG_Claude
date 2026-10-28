# pyworld_probe_roof_geometry.py -- READ-ONLY: the height of Roof_Kit_00's pieces at the corners of their footprint
# (vertex positions through Geometry Script), to know where a piece's eave and ridge are. Prints JSON.
import json

import unreal

K = "/Game/Megascans/3D_Assets/Modular_Building_Roof_Kit_00/"
R = "ukjsdfvdw_LOD0_Aset_modular__L_ukjsdfvdw_%02d_LOD0"
out = {}
for idx in (0, 1, 2, 3, 4):
    sm = unreal.load_asset(K + R % idx)
    dm = unreal.DynamicMesh()
    opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
    req = unreal.GeometryScriptMeshReadLOD()
    res = unreal.GeometryScript_AssetUtils.copy_mesh_from_static_mesh(sm, dm, opts, req)
    pts = []
    MQ = unreal.GeometryScript_MeshQueries
    for vid in range(MQ.get_num_vertex_i_ds(dm)):
        got = MQ.get_vertex_position(dm, vid)
        v, ok = (got[0], got[1]) if isinstance(got, tuple) else (got, True)
        if ok:
            pts.append((v.x, v.y, v.z))
    b = sm.get_bounding_box()
    xs = (b.min.x, b.max.x)
    ys = (b.min.y, b.max.y)

    def near(x, y, r=60.0):
        zs = [p[2] for p in pts if abs(p[0] - x) < r and abs(p[1] - y) < r]
        return [round(min(zs), 1), round(max(zs), 1)] if zs else None
    out[idx] = {"n": len(pts), "bounds": [[round(xs[0]), round(ys[0])], [round(xs[1]), round(ys[1])]],
                "z_at": {"(%d,%d)" % (x, y): near(x, y) for x in (round(xs[0]), round(xs[1]), round(0.5 * (xs[0] + xs[1])))
                         for y in (round(ys[0]), round(ys[1]), round(0.5 * (ys[0] + ys[1])))}}
print(json.dumps(out))
