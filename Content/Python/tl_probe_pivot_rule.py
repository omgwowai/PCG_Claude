# tl_probe_pivot_rule.py -- READ-ONLY. For every CHA L1/L2 and CHJ L1 module
# row, put PivotOffset next to the mesh bounding box and test the rule
#   pivot.y = -(centre of the run), run = [0, bb.max.y] or [bb.min.y, 0]
#   pivot.z = -LevelHeight / 2           (levels >= 1)
# Also dumps every TL part mesh's bounding box.
import json

NEW = "/Game/PCG/DataAssets/BDF/BDF_WithTL"
LH = {("CHA", 1): 500.0, ("CHA", 2): 300.0, ("CHJ", 1): 750.0}


def main():
    MA = unreal.PCGMetadataAccessorHelpers
    EAL = unreal.EditorAssetLibrary
    a = EAL.load_asset(NEW)
    d = md = None
    for it in a.get_editor_property("data").get_editor_property("tagged_data"):
        if "Modules" in [str(t) for t in it.get_editor_property("tags")]:
            d = it.get_editor_property("data").get_editor_property("data")
            md = d.mutable_metadata()
    bb_cache = {}

    def bb_of(path):
        if path not in bb_cache:
            m = EAL.load_asset(path.split(".")[0])
            bb_cache[path] = m.get_bounding_box() if m else None
        return bb_cache[path]

    checks, tl_bb = [], {}
    for pt in d.get_points():
        tok = MA.get_string_attribute(pt, md, "BuildingToken")
        lv = MA.get_integer32_attribute(pt, md, "Level")
        sym = MA.get_string_attribute(pt, md, "Symbol")
        path = MA.get_soft_object_path_attribute(pt, md, "Mesh").export_text()
        if tok == "TL":
            b = bb_of(path)
            tl_bb["L%d %s" % (lv, sym)] = [round(b.min.y, 1), round(b.max.y, 1),
                                           round(b.min.x, 1), round(b.max.x, 1),
                                           round(b.max.z, 1)]
            continue
        if (tok, lv) not in LH:
            continue
        b = bb_of(path)
        size = MA.get_double_attribute(pt, md, "Size")
        p = MA.get_vector_attribute(pt, md, "PivotOffset")
        run_c = b.max.y / 2.0 if abs(b.max.y) >= abs(b.min.y) else b.min.y / 2.0
        checks.append({
            "row": "%s L%d %s" % (tok, lv, sym), "size": size,
            "pivot": [round(p.x, 2), round(p.y, 2), round(p.z, 2)],
            "bb_y": [round(b.min.y, 2), round(b.max.y, 2)],
            "rule_y": round(-run_c, 2), "rule_z": -LH[(tok, lv)] / 2.0,
            "y_ok": abs(p.y + run_c) < 1.0,
            "z_ok": abs(p.z + LH[(tok, lv)] / 2.0) < 0.5,
        })
    return {"rule_hits_y": sum(c["y_ok"] for c in checks),
            "rule_hits_z": sum(c["z_ok"] for c in checks),
            "rows": len(checks),
            "misses": [c for c in checks if not (c["y_ok"] and c["z_ok"])],
            "tl_bb_[ymin,ymax,xmin,xmax,zmax]": tl_bb}


R = main()
print(json.dumps(R, indent=1, default=str)[:12000])
mcp_result = json.loads(json.dumps(R, default=str))
