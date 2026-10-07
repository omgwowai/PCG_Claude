# tl_probe_symbol_coverage.py -- READ-ONLY. For every style, which corner
# symbols does each level define? Tests whether C_E / C_I are universal (and so
# required by the corner grammar) while TL lacks them. Also reports the mesh
# paths siblings use for their level-0 corner modules.
import json

NEW = "/Game/PCG/DataAssets/BDF/BDF_WithTL"
CORNERS = ("C_E", "C_I", "C_CE", "C_SL", "C_SR", "C_IL", "C_IR")


def main():
    MA = unreal.PCGMetadataAccessorHelpers
    a = unreal.EditorAssetLibrary.load_asset(NEW)
    d = md = None
    for it in a.get_editor_property("data").get_editor_property("tagged_data"):
        if "Modules" in [str(t) for t in it.get_editor_property("tags")]:
            d = it.get_editor_property("data").get_editor_property("data")
            md = d.mutable_metadata()
    syms = {}
    l0_corner_meshes = {}
    for pt in d.get_points():
        tok = MA.get_string_attribute(pt, md, "BuildingToken")
        lv = MA.get_integer32_attribute(pt, md, "Level")
        sym = MA.get_string_attribute(pt, md, "Symbol")
        syms.setdefault(tok, {}).setdefault(lv, set()).add(sym)
        if lv == 0 and sym in ("C_E", "C_I") and tok in ("CHA", "CHJ", "SFB", "NYH", "QBA"):
            l0_corner_meshes.setdefault(tok, {})[sym] = {
                "mesh": MA.get_soft_object_path_attribute(pt, md, "Mesh").export_text(),
                "size": MA.get_double_attribute(pt, md, "Size"),
                "bScalable": MA.get_bool_attribute(pt, md, "bScalable"),
                "MeshForwardAxis": MA.get_double_attribute(pt, md, "MeshForwardAxis"),
                "PivotOffset": str(MA.get_vector_attribute(pt, md, "PivotOffset")),
            }
    missing = {}
    for tok, levels in syms.items():
        for lv, s in levels.items():
            gone = [c for c in ("C_E", "C_I") if c not in s]
            if gone:
                missing.setdefault(tok, {})[lv] = gone
    R = {
        "styles": len(syms),
        "styles_missing_C_E_or_C_I": missing,
        "corner_symbols_by_style_level": {
            t: {lv: sorted(c for c in s if c in CORNERS) for lv, s in sorted(levels.items())}
            for t, levels in syms.items() if t in ("TL", "CHA", "CHJ", "SFB", "NYH")},
        "l0_corner_meshes": l0_corner_meshes,
    }
    return R


R = main()
print(json.dumps(R, indent=1, default=str)[:12000])
mcp_result = json.loads(json.dumps(R, default=str))
