# pyworld_veg_probe.py -- READ-ONLY: registers the migrated Electric Dreams vegetation and reports every static mesh's
# bounds (cm), Nanite flag, LOD0 triangles and materials, to Saved/Reports/pyworld_veg_meshes.json.
# Args: {"roots": ["/Game/Megascans/3D_Plants", ...]} (optional)
import json
import os

import unreal

ROOTS = ["/Game/Megascans/3D_Plants", "/Game/Megascans/3D_Assets"]


def main():
    args = globals().get("mcp_args") or {}
    roots = args.get("roots", ROOTS)
    reg = unreal.AssetRegistryHelpers.get_asset_registry()
    reg.scan_paths_synchronous(roots, True)
    out = {}
    flt = unreal.ARFilter(package_paths=roots, recursive_paths=True,
                          class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "StaticMesh")])
    for ad in reg.get_assets(flt):
        path = str(ad.package_name)
        if args.get("all"):
            pass
        elif "/Megascans/3D_Assets/" in path and not any(k in path for k in (
                "Mossy", "Dead", "Fallen", "Stump", "Branch", "Twig", "Boulder", "Stones", "Roots", "Tree")):
            continue
        m = unreal.load_asset(path)
        if m is None:
            continue
        b = m.get_bounding_box()
        ns = m.get_editor_property("nanite_settings")
        mats = [str(s.material_interface.get_path_name()) if s.material_interface else None
                for s in m.get_editor_property("static_materials")]
        try:
            tris = unreal.EditorStaticMeshLibrary.get_number_triangles(m, 0) if hasattr(unreal, "EditorStaticMeshLibrary") \
                else m.get_num_triangles(0)
        except Exception:
            tris = -1
        out[path] = {"min": [round(b.min.x), round(b.min.y), round(b.min.z)],
                     "max": [round(b.max.x), round(b.max.y), round(b.max.z)],
                     "nanite": bool(ns.enabled), "tris": tris, "lods": m.get_num_lods(), "mats": mats}
    rep = os.path.join(unreal.Paths.project_saved_dir(), "Reports", args.get("out", "pyworld_veg_meshes.json"))
    os.makedirs(os.path.dirname(rep), exist_ok=True)
    with open(rep, "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    print(json.dumps({"meshes": len(out), "nanite": sum(v["nanite"] for v in out.values()), "report": rep}))


main()
