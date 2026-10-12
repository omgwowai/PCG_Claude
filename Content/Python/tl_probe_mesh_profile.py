# tl_probe_mesh_profile.py -- READ-ONLY. For each given static mesh: bounds, vertex
# count, and the plan-view (XY) outline of its LOD0 vertices at a few heights, so a
# corner piece's shape (square end, bevel, quarter round, wedge...) can be read
# without looking at it. Vertices come from MeshDescription via
# StaticMeshEditorSubsystem / StaticMesh.get_static_mesh_description.
# Args: {"meshes": ["<asset path>", ...], "z_samples": [0.1, 0.5, 0.9]}
import json

args = mcp_args or {}


def verts_of(mesh):
    md = mesh.get_static_mesh_description(0)
    out = []
    n = md.get_vertex_count()
    for i in range(n):
        p = md.get_vertex_position(unreal.VertexID(i))
        out.append((p.x, p.y, p.z))
    return out


def main():
    res = []
    for path in args.get("meshes", []):
        m = unreal.EditorAssetLibrary.load_asset(path)
        if m is None:
            res.append({"mesh": path, "error": "not loadable"})
            continue
        bb = m.get_bounding_box()
        rec = {"mesh": path.rsplit("/", 1)[-1],
               "min": [round(v, 1) for v in bb.min.to_tuple()],
               "max": [round(v, 1) for v in bb.max.to_tuple()]}
        try:
            vs = verts_of(m)
            rec["verts"] = len(vs)
            if len(vs) <= 64:
                # a low-poly blockout piece: list every vertex so its plan shape is readable
                rec["all_verts"] = sorted({(round(x), round(y), round(z)) for x, y, z in vs})
            zmin, zmax = bb.min.z, bb.max.z
            for f in args.get("z_samples", [0.1, 0.5, 0.9]):
                z = zmin + f * (zmax - zmin)
                band = max(2.0, 0.04 * (zmax - zmin))
                pts = sorted({(round(x), round(y)) for x, y, zz in vs if abs(zz - z) < band})
                rec["xy@%.1f" % f] = pts[:80]
        except Exception as e:
            rec["verts_error"] = "%s: %s" % (type(e).__name__, e)
        res.append(rec)
    return res


mcp_result = json.loads(json.dumps(main(), default=str))
