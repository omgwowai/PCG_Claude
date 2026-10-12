# tl_probe_end_profiles.py -- READ-ONLY. The x-z end profile of TL wall pieces:
# for each mesh, split the height into bands at every distinct vertex z, and in
# each band report the x range of the vertices (x = depth: facade at 0, exterior
# +X). front = max x (projection in front of the facade), back = -min x (body
# behind it). Used to size the corner caps and to check the L4 top course.
# Args: {"meshes": ["<asset path>", ...]}
import json

args = mcp_args or {}


def main():
    res = []
    for path in args.get("meshes", []):
        m = unreal.EditorAssetLibrary.load_asset(path)
        if m is None:
            res.append({"mesh": path, "error": "not loadable"})
            continue
        md = m.get_static_mesh_description(0)
        vs = []
        for i in range(md.get_vertex_count()):
            p = md.get_vertex_position(unreal.VertexID(i))
            vs.append((p.x, p.y, p.z))
        zs = sorted({round(v[2], 1) for v in vs})
        bands = []
        for z0, z1 in zip(zs, zs[1:]):
            zm = 0.5 * (z0 + z1)
            # vertices of faces spanning this band: approximate with verts at either edge
            xs = [x for x, y, z in vs if z0 - 0.05 <= z <= z1 + 0.05]
            bands.append((z0, z1, round(max(xs), 1), round(-min(xs), 1)))
        # merge consecutive bands with the same front/back
        merged = []
        for b in bands:
            if merged and merged[-1][2:] == b[2:]:
                merged[-1] = (merged[-1][0], b[1]) + b[2:]
            else:
                merged.append(b)
        res.append({"mesh": path.rsplit("/", 1)[-1],
                    "bands_z0_z1_front_back": merged[:40]})
    return res


mcp_result = json.loads(json.dumps(main(), default=str))
