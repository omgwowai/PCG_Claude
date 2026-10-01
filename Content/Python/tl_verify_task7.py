# tl_verify_task7.py — direct verification of Task 7's output.
#
# The independent review subagent failed on a quota error, so the load-bearing
# invariants are checked here directly:
#   1. Epic's source asset is still byte-identical (size + mtime) and still has
#      27/240/2916/1966 points with NO TL row anywhere in it.
#   2. BDF_WithTL has TL rows in the right three groups and none in Props.
#   3. TL's values read correctly with the type-matched getters.
#
# READ-ONLY.

import json
import os

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers

NEW = "/Game/PCG/DataAssets/BDF/BDF_WithTL"
SRC = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG"
SRC_DISK = ("E:/PCG_Claude/Plugins/CitySamplePCG/Content/PCG/Primitives/Buildings/"
            "Subgraphs/CitySampleBuildingBDF_Asset_PCG.uasset")

EXPECTED_ORIGINAL = {"BDF": 27, "Levels": 240, "Modules": 2916, "Props": 1966}

def groups(asset):
    """Key by the SET-specific tag. Note 'BDFData' is shared, so a naive
    "+".join(sorted(tags)) collapses Levels/Modules/Props into one bucket --
    that was a bug in this probe's first version."""
    out = {}
    if asset is None:
        return out
    items = asset.get_editor_property("data").get_editor_property("tagged_data")
    for it in items:
        tags = [str(t) for t in it.get_editor_property("tags")]
        key = next((t for t in tags if t != "BDFData"), "+".join(tags))
        d = it.get_editor_property("data").get_editor_property("data")
        out[key] = {"points": d.get_num_points() if d else 0, "data": d,
                    "tags": tags}
    return out

# ---------- 1. Epic's source: disk state + no TL -------------------------
src_fs = {}
try:
    src_fs["exists"] = os.path.isfile(SRC_DISK)
    if src_fs["exists"]:
        st = os.stat(SRC_DISK)
        src_fs["size"] = st.st_size
        src_fs["mtime"] = st.st_mtime
        src_fs["size_ok"] = (st.st_size == 2958616)
        src_fs["mtime_ok"] = (st.st_mtime == 1788235103.3757093)
except Exception as e:
    src_fs["err"] = type(e).__name__
R["epic_source_disk"] = src_fs

src = EAL.load_asset(SRC)
sg = groups(src)
src_counts = {k.split("+")[0]: v["points"] for k, v in sg.items()}
R["epic_source_group_counts"] = src_counts
R["epic_source_counts_ok"] = all(
    src_counts.get(k) == v for k, v in EXPECTED_ORIGINAL.items())

# assert no TL token anywhere in Epic's asset
tl_in_epic = {}
for key, rec in sg.items():
    d = rec["data"]
    if d is None:
        continue
    md = d.mutable_metadata()
    hits = 0
    for pt in d.get_points():
        for fn in ("get_string_attribute", "get_name_attribute"):
            try:
                if str(getattr(MA, fn)(pt, md, "BuildingToken")) == "TL":
                    hits += 1
                    break
            except Exception:
                continue
    tl_in_epic[key] = hits
R["tl_rows_inside_epic_source"] = tl_in_epic
R["epic_source_clean"] = all(v == 0 for v in tl_in_epic.values())

# ---------- 2. BDF_WithTL group counts -----------------------------------
new = EAL.load_asset(NEW)
R["bdf_with_tl_exists"] = new is not None
ng = groups(new)
new_counts = {k.split("+")[0]: v["points"] for k, v in ng.items()}
R["bdf_with_tl_group_counts"] = new_counts
R["delta_vs_original"] = {k: new_counts.get(k, 0) - EXPECTED_ORIGINAL.get(k, 0)
                          for k in EXPECTED_ORIGINAL}

# ---------- 3. TL values with the type-matched getters -------------------
def read_tl(group_tag, fields):
    rec = ng.get(group_tag)
    if not rec or rec["data"] is None:
        return {"err": "group missing"}
    d = rec["data"]
    md = d.mutable_metadata()
    rows = []
    for pt in d.get_points():
        # get_string_attribute FIRST: these groups' BuildingToken is a String.
        # Trying get_name_attribute first is a trap -- on a String attribute it
        # returns a truthy non-empty value, so the name branch would win and the
        # token would never match. (Only the Levels group is Name-typed.)
        tok = ""
        for fn in ("get_string_attribute", "get_name_attribute"):
            try:
                v = str(getattr(MA, fn)(pt, md, "BuildingToken"))
            except Exception:
                continue
            if v == "TL":
                tok = v
                break
            if v and not tok:
                tok = v
        if tok != "TL":
            continue
        r = {}
        for f, kind in fields:
            fn = {"f": "get_float_attribute", "d": "get_double_attribute",
                  "s": "get_string_attribute", "n": "get_name_attribute",
                  "i": "get_integer32_attribute"}[kind]
            try:
                r[f] = getattr(MA, fn)(pt, md, f)
            except Exception as e:
                r[f] = "<%s>" % type(e).__name__
        rows.append(r)
    return {"count": len(rows), "rows": rows}

R["TL_BDF"] = read_tl("BDF",
                      [("MinWallWidth", "f"), ("MinBldgHeight", "f"),
                       ("MaxBldgHeight", "f"), ("VerticalGrammar", "s")])
R["TL_Levels"] = read_tl("Levels",
                         [("LevelToken", "s"), ("LevelNumber", "i"),
                          ("LevelHeight", "f"), ("F0", "s")])
mod = read_tl("Modules",
              [("Level", "i"), ("Symbol", "s"), ("Size", "d"), ("PtID", "i")])
R["TL_Modules_count"] = mod.get("count")
# summarize symbols/levels rather than dumping all 33
if mod.get("rows"):
    syms = {}
    for r in mod["rows"]:
        syms.setdefault(str(r.get("Level")), []).append(str(r.get("Symbol")))
    R["TL_Modules_by_level"] = {k: sorted(v) for k, v in sorted(syms.items())}

print(json.dumps(json.loads(json.dumps(R, default=str)), indent=1)[:6000])
mcp_result = json.loads(json.dumps(R, default=str))
