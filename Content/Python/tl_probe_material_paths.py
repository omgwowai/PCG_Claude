# tl_probe_material_paths.py -- READ-ONLY. Full object paths of the generic
# building material instances the TL kit uses, and whether each is opaque.
import json

WANT = ["MI_Bldg_BrickOffset_Red", "MI_Bldg_BrickOffset_Brown", "MI_Bldg_Block_Limestone_Beige",
        "MI_Bldg_Block_Granite_Grey", "MI_Bldg_Block_Granite_Black", "MI_Bldg_glass_opaque",
        "MI_Bldg_Glass", "MI_Bldg_PaintedMetal_Black", "MI_Bldg_PaintedMetal_Green"]


def main():
    EAL = unreal.EditorAssetLibrary
    found = {}
    for root in ("/Game/Building/Material", "/Game/Building/CH/A/Material"):
        for a in EAL.list_assets(root, recursive=True, include_folder=False):
            name = a.split(".")[0].split("/")[-1]
            if name in WANT:
                found.setdefault(name, []).append(a.split(".")[0])
    info = {}
    for name, paths in found.items():
        for p in paths:
            mi = EAL.load_asset(p)
            rec = {"class": mi.get_class().get_name() if mi else None}
            try:
                base = mi.get_base_material()
                rec["base"] = base.get_path_name()
                rec["blend"] = str(base.get_editor_property("blend_mode"))
            except Exception as e:
                rec["err"] = "%s: %s" % (type(e).__name__, e)
            info[p] = rec
    return {"found": found, "info": info}


mcp_result = json.loads(json.dumps(main(), default=str))
