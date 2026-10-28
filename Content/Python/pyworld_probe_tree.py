# pyworld_probe_tree.py -- READ-ONLY: why a tree renders without leaves. Material slots (with their parent chain and
# blend mode), Nanite settings and any assembly references of a few tree meshes.
import json

import unreal

PATHS = ["/CitySamplePCG/Megaplants/Tree_European_Beech/Tree_European_Beech_01/SM_European_Beech_01_A",
         "/Game/Prop/Kit_Tree_Birch/Mesh/SM_Tree_Birch_a",
         "/Game/Megascans/3D_Plants/EuropeanHornbeam/Geometry/SimpleWind/SM_EuropeanHornbeam_Forest_01"]


def chain(mi):
    out = []
    while mi is not None:
        out.append(mi.get_path_name().rsplit("/", 1)[-1])
        mi = mi.get_editor_property("parent") if isinstance(mi, unreal.MaterialInstance) else None
    return out


def main():
    res = {}
    for p in PATHS:
        m = unreal.load_asset(p)
        info = {"slots": []}
        for s in m.get_editor_property("static_materials"):
            mi = s.material_interface
            base = mi.get_base_material() if mi else None
            info["slots"].append({"slot": str(s.material_slot_name), "chain": chain(mi),
                                  "blend": str(base.get_editor_property("blend_mode")) if base else None,
                                  "two_sided": bool(base.get_editor_property("two_sided")) if base else None})
        ns = m.get_editor_property("nanite_settings")
        info["nanite"] = {k: str(ns.get_editor_property(k))[:120] for k in dir(ns)
                          if not k.startswith("_") and not callable(getattr(ns, k, None))}
        for k in ("nanite_assembly_data", "assembly_data"):
            try:
                info[k] = str(m.get_editor_property(k))[:300]
            except Exception:
                pass
        b = m.get_bounding_box()
        info["bounds_z"] = [round(b.min.z), round(b.max.z)]
        info["tris_lod0"] = m.get_num_triangles(0) if hasattr(m, "get_num_triangles") else None
        res[p.rsplit("/", 1)[-1]] = info
    print(json.dumps(res, indent=1))


main()
