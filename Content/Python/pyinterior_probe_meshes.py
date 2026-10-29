# pyinterior_probe_meshes.py -- probe (read-only): the StarterContent meshes PyInterior can use instead of a primitive
# recipe (spec 2026-10-28 §4.9). Per mesh: bounding box, material slots, and where its top vertices sit relative to the
# box centre (a couch's or chair's back is its tall side, so the front is the other way). Writes
# Saved/Reports/pyinterior_probe_meshes.json.
import json
import os

MESHES = ["SM_Couch", "SM_Chair", "SM_TableRound", "SM_Shelf", "SM_Lamp_Wall", "SM_Bush"]
GS = getattr(unreal, "GeometryScript_AssetUtils", None)


def vertices(sm):
    """World-less vertex positions of LOD 0 through Geometry Scripting, or None."""
    if GS is None:
        return None
    dm = unreal.DynamicMesh()
    opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
    res = GS.copy_mesh_from_static_mesh(sm, dm, opts, unreal.GeometryScriptMeshReadLOD())
    q = unreal.GeometryScript_MeshQueries
    got = q.get_all_vertex_positions(dm, True)
    plist = next(x for x in (got if isinstance(got, tuple) else (got,)) if isinstance(x, unreal.GeometryScriptVectorList))
    arr = unreal.GeometryScript_List.convert_vector_list_to_array(plist)
    return [(v.x, v.y, v.z) for v in arr], str(res)


R = {"geometry_script": GS is not None}
for name in MESHES:
    path = "/Game/StarterContent/Props/%s.%s" % (name, name)
    sm = unreal.load_asset(path)
    if sm is None:
        R[name] = {"missing": path}
        continue
    box = sm.get_bounding_box()
    lo, hi = box.min, box.max
    e = {"path": path, "min": [round(lo.x, 2), round(lo.y, 2), round(lo.z, 2)],
         "max": [round(hi.x, 2), round(hi.y, 2), round(hi.z, 2)],
         "slots": [str(m.get_editor_property("material_slot_name")) + " = " +
                   (m.get_editor_property("material_interface").get_path_name() if m.get_editor_property("material_interface") else "None")
                   for m in sm.get_editor_property("static_materials")]}
    try:
        got = vertices(sm)
        if got:
            vs, res = got
            e["vertices"] = len(vs)
            cx, cy = 0.5 * (lo.x + hi.x), 0.5 * (lo.y + hi.y)
            z70 = lo.z + 0.7 * (hi.z - lo.z)
            top = [v for v in vs if v[2] >= z70]
            if top:
                e["top_offset_xy"] = [round(sum(v[0] for v in top) / len(top) - cx, 2),
                                      round(sum(v[1] for v in top) / len(top) - cy, 2)]
            mid = [v for v in vs if lo.z + 0.25 * (hi.z - lo.z) <= v[2] <= lo.z + 0.6 * (hi.z - lo.z)]
            if mid:
                e["mid_offset_xy"] = [round(sum(v[0] for v in mid) / len(mid) - cx, 2),
                                      round(sum(v[1] for v in mid) / len(mid) - cy, 2)]
            # extent of the vertices hugging each side (a wall plate is a dense flat side)
            for axis, k in (("x", 0), ("y", 1)):
                a0, a1 = (lo.x, hi.x) if k == 0 else (lo.y, hi.y)
                band = 0.08 * (a1 - a0)
                e["near_" + axis] = [sum(1 for v in vs if v[k] <= a0 + band), sum(1 for v in vs if v[k] >= a1 - band)]
    except Exception as ex:
        e["vertex_error"] = "%s: %s" % (type(ex).__name__, str(ex)[:300])
    R[name] = e
if GS is None:
    R["gs_candidates"] = [n for n in dir(unreal) if n.startswith("GeometryScript")][:40]
os.makedirs(unreal.Paths.project_saved_dir() + "Reports", exist_ok=True)
with open(unreal.Paths.project_saved_dir() + "Reports/pyinterior_probe_meshes.json", "w") as fh:
    json.dump(R, fh, indent=1)
mcp_result = R
