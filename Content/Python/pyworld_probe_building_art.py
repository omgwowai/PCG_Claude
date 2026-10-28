# pyworld_probe_building_art.py -- READ-ONLY: what building art the town could use. Per City Sample style folder under
# /Game/Building: mesh count and sample names; materials / textures whose names suggest plaster, brick, stone, wood,
# roof tiles; the PCGPrimitives grammar kit (data assets and meshes). Writes Saved/Reports/pyworld_building_art.json.
import json
import os

import unreal

AR = unreal.AssetRegistryHelpers.get_asset_registry()
OUT = os.path.join(unreal.Paths.project_saved_dir(), "Reports", "pyworld_building_art.json")


def assets(path, cls=None, recursive=True):
    f = unreal.ARFilter(package_paths=[path], recursive_paths=recursive,
                        class_paths=[unreal.TopLevelAssetPath(*cls.split(".", 1))] if cls else [])
    return AR.get_assets(f)


def names(lst, n=40):
    return [str(a.asset_name) for a in lst[:n]]


out = {"building_dirs": {}, "materials": {}, "primitives": {}}
SM = "/Script/Engine.StaticMesh"
MAT = ["/Script/Engine.Material", "/Script/Engine.MaterialInstanceConstant"]
for sub in unreal.EditorAssetLibrary.list_assets("/Game/Building", False, True):
    pass
# top-level folders under /Game/Building
dirs = sorted({str(a.package_path) for a in assets("/Game/Building")})
tops = sorted({"/".join(d.split("/")[:4]) for d in dirs})
for top in tops:
    meshes = assets(top, "/Script/Engine.StaticMesh")
    out["building_dirs"][top] = {"meshes": len(meshes), "sample": names(sorted(meshes, key=lambda a: str(a.asset_name)), 25)}
keys = ("plaster", "stucco", "brick", "stone", "wood", "timber", "roof", "tile", "shingle", "slate", "wall", "window",
        "door", "concrete", "facade")
for root in ("/Game/Building", "/Game/Material", "/Game/Megascans", "/Game/Prop", "/CitySamplePCG"):
    for cls in MAT + ["/Script/Engine.Texture2D"]:
        for a in assets(root, cls):
            n = str(a.asset_name).lower()
            hit = [k for k in keys if k in n]
            if hit:
                out["materials"].setdefault(hit[0], []).append(str(a.package_name))
for k in out["materials"]:
    out["materials"][k] = sorted(out["materials"][k])[:60]
prim = assets("/PCGPrimitives/Grammar")
out["primitives"]["grammar"] = sorted(str(a.package_name) for a in prim)[:80]
out["primitives"]["meshes"] = sorted(str(a.package_name) for a in assets("/PCGPrimitives/Meshes", SM))[:120]
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as fh:
    json.dump(out, fh, indent=1)
print(json.dumps({"building_dirs": {k: v["meshes"] for k, v in out["building_dirs"].items()},
                  "materials": {k: len(v) for k, v in out["materials"].items()},
                  "grammar_assets": len(out["primitives"]["grammar"]), "prim_meshes": len(out["primitives"]["meshes"])},
                 indent=1))
