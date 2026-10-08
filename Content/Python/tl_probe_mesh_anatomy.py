# tl_probe_mesh_anatomy.py -- READ-ONLY. For CHA and TL kit meshes, report
# what each piece actually is: triangle count, bounds, material slots.
import json

ROOTS = {
    "CHA": "/Game/Building/CH/A/Kit_Bldg_CHA_L{n}_A/Mesh/SM_BLDG_CHA_L{nn}_A_{part}_N1",
    "TL": "/Game/Building/TL/A/Kit_Bldg_TL_L{n}_A/Mesh/SM_BLDG_TL_L{nn}_A_{part}_N1",
}
PARTS = ["Wall_01", "Wall_02", "Entrance_01", "Column_01", "Column_02", "CornerEx_01",
         "CornerExL_01", "CornerExR_01", "CornerIn_01", "CornerInL_01", "CornerInR_01"]
LEVELS = (1, 2, 3, 12, 13, 20, 21)


def anatomy(path):
    m = unreal.EditorAssetLibrary.load_asset(path)
    if m is None:
        return None
    bb = m.get_bounding_box()
    slots = [str(s.get_editor_property("material_slot_name")) for s in m.get_editor_property("static_materials")]
    try:
        tris = unreal.EditorStaticMeshLibrary.get_number_triangles(m, 0) if hasattr(unreal, "EditorStaticMeshLibrary") else None
    except Exception:
        tris = None
    if tris is None:
        try:
            tris = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).get_number_verts(m, 0)
            tris = "verts=%d" % tris
        except Exception as e:
            tris = "<%s>" % type(e).__name__
    return {"tris": tris,
            "x": [round(bb.min.x), round(bb.max.x)],
            "y": [round(bb.min.y), round(bb.max.y)],
            "z": [round(bb.min.z), round(bb.max.z)],
            "slots": slots}


def main():
    R = {}
    for style, tmpl in ROOTS.items():
        for n in LEVELS:
            for part in PARTS:
                p = tmpl.format(n=n, nn="%02d" % n, part=part)
                a = anatomy(p)
                if a:
                    R["%s L%d %s" % (style, n, part)] = a
    return R


R = main()
mcp_result = json.loads(json.dumps(R, default=str))
