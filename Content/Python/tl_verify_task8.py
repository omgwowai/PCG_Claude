# tl_verify_task8.py — verify Task 8's four registrations on the LIVE assets.
#
# Task 8's reviewer subagent is unavailable (quota), so the controller checks the
# load-bearing invariants directly. This is Review Focus 1 and 5's territory:
# an authored-but-unregistered style produces ZERO buildings with ZERO errors.
#
#  1. DT_Bldg_MinWidth has TL, 28 rows, and all 27 originals survived.
#  2. DT_Bldg_LevelMinWidth has TL's 4 rows, 244 total, originals intact.
#  3. Assign_CitySampleBuildings' BuildingsStyles carries TL AND all 27 codes.
#  4. LoadCitySampleData points at BDF_WithTL.
#
# READ-ONLY.

import json

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary

ORIGINAL_CODES = ["CHA", "CHB", "CHC", "CHD", "CHE", "CHF", "CHG", "CHH", "CHI",
                  "CHJ", "NYAA", "NYAB", "NYAC", "NYAD", "NYAE", "NYAF", "NYG",
                  "NYGA", "NYH", "QBA", "QBAA", "SFA", "SFB", "SFC", "SFD",
                  "SFE", "SFJ"]

DT_MIN = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_MinWidth"
DT_LVL = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_LevelMinWidth"
ASG = "/CitySamplePCG/PCG/Primitives/Buildings/Assign_CitySampleBuildings"
LOAD = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/LoadCitySampleData"

# ---------- 1 + 2. the two DataTables ------------------------------------
for label, path in (("DT_Bldg_MinWidth", DT_MIN), ("DT_Bldg_LevelMinWidth", DT_LVL)):
    rec = {}
    dt = EAL.load_asset(path)
    if dt is None:
        R[label] = {"err": "not loadable"}
        continue
    try:
        rows = [str(x) for x in dt.get_row_names()]
        rec["row_count"] = len(rows)
        rec["has_TL"] = any(r == "TL" or r.startswith("TL") for r in rows)
        rec["TL_rows"] = sorted([r for r in rows if r.startswith("TL")])
        rec["does_row_exist_TL"] = bool(dt.does_row_exist(unreal.Name("TL")))
        missing = [c for c in ORIGINAL_CODES if c not in rows]
        rec["missing_originals"] = missing
        rec["originals_intact"] = (len(missing) == 0)
        rec["columns"] = [str(c) for c in dt.get_column_names()]
        # a sample row for TL, to see the values actually stored
        txt = dt.export_to_csv_string()
        lines = [l for l in txt.splitlines() if l.startswith("TL")]
        rec["TL_csv_line"] = lines[:4]
    except Exception as e:
        rec["err"] = "%s: %s" % (type(e).__name__, e)
    R[label] = rec

# ---------- 3. BuildingsStyles on the live graph -------------------------
try:
    g = EAL.load_asset(ASG)
    txt = g.get_editor_property("user_parameters").export_text()
    R["BuildingsStyles_reachable"] = True
    R["has_TL"] = ("TL" in txt)
    missing = [c for c in ORIGINAL_CODES if c not in txt]
    R["missing_originals"] = missing
    R["all_originals_present"] = (len(missing) == 0)
    # excerpt around the parameter so a human can read the literal value
    i = txt.find("BuildingsStyles")
    R["excerpt"] = txt[max(0, i - 40):i + 800] if i >= 0 else "<not found>"
except Exception as e:
    R["BuildingsStyles_err"] = "%s: %s" % (type(e).__name__, e)

# ---------- 4. LoadCitySampleData's database reference -------------------
try:
    lg = EAL.load_asset(LOAD)
    refs = []
    for node in lg.get_editor_property("nodes"):
        try:
            s = node.get_settings()
        except Exception:
            continue
        if s is None:
            continue
        for prop in ("asset", "data_asset"):
            try:
                v = s.get_editor_property(prop)
            except Exception:
                continue
            if v is not None:
                refs.append({"node": s.get_class().get_name(),
                             "param": prop, "value": str(v)})
    R["LoadCitySampleData_refs"] = refs
    R["points_at_BDF_WithTL"] = any("BDF_WithTL" in r["value"] for r in refs)
    R["still_points_at_epic"] = any(
        "CitySampleBuildingBDF_Asset_PCG" in r["value"] for r in refs)
except Exception as e:
    R["LoadCitySampleData_err"] = "%s: %s" % (type(e).__name__, e)

print(json.dumps(json.loads(json.dumps(R, default=str)), indent=1)[:5000])
mcp_result = json.loads(json.dumps(R, default=str))
