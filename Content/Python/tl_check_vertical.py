# tl_check_vertical.py — test the strongest structural candidate.
#
# Reading the BDF rows earlier, TL's VerticalGrammar is "[LV0][LV1][LV2][LV3]"
# with NO asterisk, while CHA's is "[LV0]..[LV6]*[LV7][LV8][LV9]*[LV10][LV20]"
# and CHF's is "[LV0][LV1][LV2]*[LV3][LV4][LV5]". A '*' marks a REPEATABLE level
# -- which is how a style stretches to fit a requested building height.
#
# If every one of the 27 working styles has a '*' and TL alone has none, then TL
# is the only style whose vertical grammar cannot repeat, i.e. cannot be scaled
# to any requested height, and would be rejected by every lot -- matching the
# symptom exactly (zero TL, no error, all other styles normal).
#
# READ-ONLY.

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
            "vg": MA.get_string_attribute(pt, md, "VerticalGrammar"),
            "vgs": MA.get_string_attribute(pt, md, "VerticalGrammarStaggered"),
        })
    rows.sort(key=lambda r: str(r["tok"]))
    R["rows"] = rows
    R["has_star"] = {r["tok"]: ("*" in r["vg"]) for r in rows}
    R["without_star"] = [r["tok"] for r in rows if "*" not in r["vg"]]
    R["without_star_count"] = len(R["without_star"])
    R["without_star_staggered"] = [
        r["tok"] for r in rows
        if "*" not in r["vgs"] and r["vgs"]
    ]
    R["staggered_values"] = {r["tok"]: r["vgs"] for r in rows
                             if r["tok"] in ("TL", "CHA", "CHF", "SFB")}

print(json.dumps(json.loads(json.dumps(R, default=str)), indent=1)[:4000])
mcp_result = json.loads(json.dumps(R, default=str))
