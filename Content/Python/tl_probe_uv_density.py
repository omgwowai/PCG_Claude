# tl_probe_uv_density.py -- READ-ONLY. UV density of a few CHA meshes (UV units
# per cm, per channel) and the parameters of the building materials TL will use.
import json

MESHES = ["/Game/Building/CH/A/Kit_Bldg_CHA_L1_A/Mesh/SM_BLDG_CHA_L01_A_Wall_01_N1",
          "/Game/Building/CH/A/Kit_Bldg_CHA_L2_A/Mesh/SM_BLDG_CHA_L02_A_Column_01_N1"]
MATS = ["/Game/Building/Material/MI_Bldg_Block_Limestone_Beige",
        "/Game/Building/Material/MI_Bldg_Glass",
        "/Game/Building/Material/MI_Bldg_PaintedMetal_Black",
        "/Game/Building/CH/A/Kit_Bldg_CHA_L1_A/Material/MI/MI_CHA_L01_A_Wall_01_1"]


def uv_stats(path):
    m = unreal.EditorAssetLibrary.load_asset(path)
    out = {"uv_channels": m.get_num_uv_channels(0) if hasattr(m, "get_num_uv_channels") else None,
           "nanite": None}
    try:
        out["nanite"] = m.get_editor_property("nanite_settings").get_editor_property("enabled")
    except Exception as e:
        out["nanite"] = "<%s>" % type(e).__name__
    try:
        desc = m.get_static_mesh_description(0)
    except Exception as e:
        out["desc_err"] = "%s: %s" % (type(e).__name__, e)
        return out
    n = desc.get_vertex_instance_count()
    pairs = []
    for i in range(0, n, max(1, n // 400)):
        vi = unreal.VertexInstanceID(i)
        v = desc.get_vertex_instance_vertex(vi)
        p = desc.get_vertex_position(v)
        uv0 = desc.get_vertex_instance_uv(vi, 0)
        pairs.append((p.x, p.y, p.z, uv0.x, uv0.y))
    # density: best linear fit of uv span vs position span over sampled points
    import itertools
    best = []
    for a, b in itertools.combinations(pairs[:120], 2):
        dp = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5
        du = ((a[3] - b[3]) ** 2 + (a[4] - b[4]) ** 2) ** 0.5
        if dp > 50:
            best.append(du / dp)
    best.sort()
    out["uv_per_cm_median"] = best[len(best) // 2] if best else None
    out["uv0_range"] = [min(p[3] for p in pairs), max(p[3] for p in pairs),
                        min(p[4] for p in pairs), max(p[4] for p in pairs)]
    out["samples"] = len(pairs)
    return out


def mat_info(path):
    MEL = unreal.MaterialEditingLibrary
    mi = unreal.EditorAssetLibrary.load_asset(path)
    if mi is None:
        return None
    out = {"parent": mi.get_editor_property("parent").get_path_name() if hasattr(mi, "parent") or True else None}
    for kind, fn in (("scalar", "get_scalar_parameter_names"), ("vector", "get_vector_parameter_names"),
                     ("texture", "get_texture_parameter_names"), ("switch", "get_static_switch_parameter_names")):
        try:
            names = getattr(MEL, fn)(mi)
            out[kind] = [str(n) for n in names][:40]
        except Exception as e:
            out[kind] = "<%s>" % type(e).__name__
    return out


R = {"meshes": {p.split("/")[-1]: uv_stats(p) for p in MESHES},
     "materials": {p.split("/")[-1]: mat_info(p) for p in MATS}}
mcp_result = json.loads(json.dumps(R, default=str))
