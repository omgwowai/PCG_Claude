# tl_spike_bdf_compact.py — P0 SPIKE S2d. READ-ONLY. Compact output only.
#
# Prints ONE line per row instead of nested JSON, so the result is small
# enough to read directly. Answers: what does a style need, exactly?

import json

R = {}
args = mcp_args or {}
SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"
EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers

LEVELS = {"BuildingToken": ("get_name_attribute", "n"),
          "LevelNumber": ("get_integer32_attribute", "i"),
          "LevelToken": ("get_string_attribute", "s"),
          "LevelHeight": ("get_double_attribute", "d"),
          "F0": ("get_string_attribute", "s"),
          "F1": ("get_string_attribute", "s"),
          "F2": ("get_string_attribute", "s"),
          "IsTopper": ("get_bool_attribute", "b")}

MODULES = {"BuildingToken": ("get_string_attribute", "s"),
           "Level": ("get_integer32_attribute", "i"),
           "Symbol": ("get_string_attribute", "s"),
           "Size": ("get_double_attribute", "d"),
           "Mod_Name": ("get_string_attribute", "s"),
           "Mesh": ("get_soft_object_path_attribute", "o"),
           "bScalable": ("get_bool_attribute", "b"),
           "PivotOffset": ("get_vector_attribute", "v"),
           "MeshForwardAxis": ("get_double_attribute", "d"),
           "PropOffset": ("get_vector_attribute", "v"),
           "HasProps": ("get_bool_attribute", "b"),
           "HasWindow": ("get_bool_attribute", "b")}

def row(pt, md, spec):
    out = {}
    for nm, (fn, _t) in spec.items():
        try:
            v = getattr(MA, fn)(pt, md, nm)
        except Exception:
            out[nm] = None
            continue
        if hasattr(v, "x") and hasattr(v, "z"):
            out[nm] = "%g,%g,%g" % (v.x, v.y, v.z)
        elif hasattr(v, "to_string"):
            out[nm] = v.to_string()
        else:
            out[nm] = v
    return out

a = EAL.load_asset(SRC)
items = a.get_editor_property("data").get_editor_property("tagged_data")

def get_set(tag):
    for it in items:
        if tag in [str(t) for t in it.get_editor_property("tags")]:
            d = it.get_editor_property("data").get_editor_property("data")
            return d, d.mutable_metadata()
    return None, None

lines = []

# ---- levels for CHA -----------------------------------------------------
d, md = get_set("Levels")
if d:
    for pt in d.get_points():
        r = row(pt, md, LEVELS)
        if str(r.get("BuildingToken")) == "CHA":
            lines.append("LV n=%s %s h=%s F0=%s | F1=%s" % (
                r.get("LevelNumber"), r.get("LevelToken"),
                r.get("LevelHeight"), r.get("F0"), r.get("F1")))
R["levels_lines"] = lines
R["levels_total"] = len(d.get_points()) if d else 0

# ---- modules for CHA L1..L3 --------------------------------------------
lines2 = []
d, md = get_set("Modules")
if d:
    rows = []
    for pt in d.get_points():
        r = row(pt, md, MODULES)
        if str(r.get("BuildingToken")) == "CHA":
            rows.append(r)
    R["cha_module_total"] = len(rows)
    for r in sorted(rows, key=lambda x: (int(x.get("Level") or 0), str(x.get("Symbol")))):
        lv = int(r.get("Level") or 0)
        if lv <= 3:
            meshname = str(r.get("Mesh") or "").split("/")[-1].split(".")[0]
            lines2.append("L%d %-8s size=%-8s scal=%-5s fwd=%-4s piv=%-14s mesh=%s" % (
                lv, r.get("Symbol"), r.get("Size"), r.get("bScalable"),
                r.get("MeshForwardAxis"), r.get("PivotOffset"), meshname))
R["modules_lines"] = lines2

# ---- the distinct module symbols across ALL codes -----------------------
d, md = get_set("Modules")
if d:
    syms = set()
    for pt in d.get_points():
        r = row(pt, md, MODULES)
        syms.add(str(r.get("Symbol")))
    R["all_symbols"] = sorted(syms)

# ---- SFA L1 modules, to compare a different code's mesh-path shape ------
sfa = []
if d:
    for pt in d.get_points():
        r = row(pt, md, MODULES)
        if str(r.get("BuildingToken")) == "SFA" and int(r.get("Level") or 0) == 1:
            sfa.append("%s size=%s mesh=%s" % (r.get("Symbol"), r.get("Size"), r.get("Mesh")))
R["sfa_l1"] = sfa

print("###LEVELS###")
for ln in R["levels_lines"]:
    print(ln)
print("###LEVELS_TOTAL###", R["levels_total"])
print("###MODULES###")
for ln in R["modules_lines"]:
    print(ln)
print("###CHA_MODULE_TOTAL###", R.get("cha_module_total"))
print("###ALL_SYMBOLS###", ",".join(R["all_symbols"]))
print("###SFA_L1###")
for ln in R["sfa_l1"]:
    print(ln)

mcp_result = R
