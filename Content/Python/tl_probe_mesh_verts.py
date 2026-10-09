# tl_probe_mesh_verts.py -- READ-ONLY. For each mesh, sample LOD0 vertex
# positions and summarise them per slab of one axis, so the orientation of a
# prop (which end mounts on the wall) or of a facade module (where the glass
# sits) can be read from geometry rather than from bounds.
# Args: {"meshes": [...paths...], "axis": "y", "bins": 6}
import json

args = mcp_args or {}
MESHES = args.get("meshes", [])
AXIS = args.get("axis", "y")
BINS = int(args.get("bins", 6))


def verts(mesh):
    smd = mesh.get_static_mesh_description(0)
    n = smd.get_vertex_count()
    out = []
    for i in range(n):
        p = smd.get_vertex_position(unreal.VertexID(i))
        out.append((p.x, p.y, p.z))
    return out


def summary(pts, axis):
    ai = "xyz".index(axis)
    lo = min(p[ai] for p in pts)
    hi = max(p[ai] for p in pts)
    step = (hi - lo) / BINS or 1.0
    rows = []
    for b in range(BINS):
        a0, a1 = lo + b * step, lo + (b + 1) * step
        sel = [p for p in pts if a0 <= p[ai] <= a1 + 1e-6]
        if not sel:
            rows.append({"slab": [round(a0, 1), round(a1, 1)], "n": 0})
            continue
        rows.append({"slab": [round(a0, 1), round(a1, 1)], "n": len(sel),
                     "x": [round(min(p[0] for p in sel), 1), round(max(p[0] for p in sel), 1)],
                     "y": [round(min(p[1] for p in sel), 1), round(max(p[1] for p in sel), 1)],
                     "z": [round(min(p[2] for p in sel), 1), round(max(p[2] for p in sel), 1)]})
    return rows


def main():
    out = {}
    for p in MESHES:
        m = unreal.EditorAssetLibrary.load_asset(p)
        if m is None:
            out[p] = None
            continue
        try:
            pts = verts(m)
        except Exception as e:
            out[p.rsplit("/", 1)[-1]] = "ERR %s: %s" % (type(e).__name__, e)
            continue
        out[p.rsplit("/", 1)[-1]] = {"verts": len(pts), "by_" + AXIS: summary(pts, AXIS)}
    return out


mcp_result = json.loads(json.dumps(main(), default=str))
