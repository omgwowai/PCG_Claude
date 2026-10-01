# tl_check_heightband.py — read every style's height band, to see whether TL is
# structurally unique and what a sane TL band should be.
#
# Context: Task 9 found TL generates 0 instances in the city pipeline, and TL is
# the only of 28 registered styles whose MinBldgHeight == MaxBldgHeight (both
# 1600.0, a ruling the controller made in Task 7). This reads all 28 rows with
# the type-matched FLOAT getter to test that claim and to see the real pattern.

import json

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers

NEW = "/Game/PCG/DataAssets/BDF/BDF_WithTL"

def get_set(asset, tag):
    items = asset.get_editor_property("data").get_editor_property("tagged_data")
    for it in items:
        if tag in [str(t) for t in it.get_editor_property("tags")]:
            d = it.get_editor_property("data").get_editor_property("data")
            return d, d.mutable_metadata()
    return None, None

a = EAL.load_asset(NEW)
d, md = get_set(a, "BDF")
if d is None:
    R["fatal"] = "no BDF group"
else:
    rows = []
    for pt in d.get_points():
        rows.append({
            "tok": MA.get_string_attribute(pt, md, "BuildingToken"),
            "minW": MA.get_float_attribute(pt, md, "MinWallWidth"),
            "minH": MA.get_float_attribute(pt, md, "MinBldgHeight"),
            "maxH": MA.get_float_attribute(pt, md, "MaxBldgHeight"),
        })
    rows.sort(key=lambda r: str(r["tok"]))
    R["rows"] = rows
    # which have a zero span?
    zero = [r["tok"] for r in rows if r["minH"] == r["maxH"]]
    R["styles_with_zero_span"] = zero
    R["zero_span_count"] = len(zero)
    # the span distribution
    R["spans"] = {r["tok"]: r["maxH"] - r["minH"] for r in rows}
    R["minH_values"] = sorted({r["minH"] for r in rows})
    R["maxH_min"] = min(r["maxH"] for r in rows)
    R["maxH_max"] = max(r["maxH"] for r in rows)
    R["minH_min"] = min(r["minH"] for r in rows)
    R["minH_max"] = max(r["minH"] for r in rows)

# ---------- the graph-level height window --------------------------------
ASG = "/CitySamplePCG/PCG/Primitives/Buildings/Assign_CitySampleBuildings"
try:
    g = EAL.load_asset(ASG)
    txt = g.get_editor_property("user_parameters").export_text()
    i = txt.find("MinHeight")
    R["graph_params_excerpt"] = txt[max(0, i - 60):i + 420] if i >= 0 else "<none>"
except Exception as e:
    R["graph_err"] = "%s: %s" % (type(e).__name__, e)

print(json.dumps(json.loads(json.dumps(R, default=str)), indent=1)[:3500])
mcp_result = json.loads(json.dumps(R, default=str))
