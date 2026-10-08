# tl_register.py -- register TL: two DataTable row sets and the
# LoadCitySampleData repoint.
#
# MEASURED BACKGROUND (Task 8 probing, this run):
#   * DataTable.fill_from_csv_string() is a FULL REPLACE, not a merge. Feeding
#     it a CSV with only the new row(s) wipes every existing row. The safe
#     pattern is: export_to_csv_string() the live table, append the new
#     row(s) as raw CSV lines to that text, and feed the COMBINED csv back in.
#   * DT_Bldg_MinWidth (struct ST_Bldg_MinWidth) columns are exactly
#     buildingToken, minWidth, worstLevelToken -- not just buildingToken/
#     minWidth as an earlier draft assumed. Row name == buildingToken (e.g. "CHA").
#   * DT_Bldg_LevelMinWidth (struct ST_Level_MinWidth) columns are
#     BuildingToken, LevelToken, LevelNumber, F0Grammar, isTopper,
#     CornerModuleSymbol, CornerSize, WallContribution, MinWidthWorstCase.
#     Row name is "{BuildingToken}_{LevelToken}" (e.g. "CHA_LV0").
#   * Every one of the 27 existing styles' LV0 row uses the identical corner
#     profile CornerModuleSymbol=C_E, CornerSize=40.0, WallContribution=200.0,
#     MinWidthWorstCase=280.0 -- a universal convention, not CHA-specific.
#     TL's LV0 row must match it; TL's LV1-LV4 use its own profile
#     (C_CE/150/650/950, mirroring CHA's upper levels). LV4 is the topper.
#   * The style whitelist consumed by the city stage is not a literal string
#     on any node, and it is not `Assign_CitySampleBuildings`' own
#     `BuildingsStyles` user parameter default either: `PCG_3_3_1_Buildings`
#     overrides `BuildingsStyles` on each of its three
#     `Assign_CitySampleBuildings` call sites (on `subgraph_instance`), so the
#     subgraph's own default is never read there. That call-site whitelist is
#     handled separately by `tl_whitelist_city.py`.
#   * LoadCitySampleData has TWO PCGLoadDataAssetSettings nodes: one loads
#     CitySampleBuildingBDF_NamesOnly_PCG (leave alone), the other loads
#     CitySampleBuildingBDF_Asset_PCG (the one to repoint at BDF_WithTL). The
#     settings property holding the data asset is named "asset", not
#     "data_asset".
#
# Idempotent: every edit checks the current state first and is a no-op when
# it already matches. Safe to re-run.

import json

R = {"steps": [], "errors": []}
EAL = unreal.EditorAssetLibrary

DT_MIN = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_MinWidth"
DT_LVL = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_LevelMinWidth"
LOAD   = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/LoadCitySampleData"
NEW_BDF = "/Game/PCG/DataAssets/BDF/BDF_WithTL"


def note(step, **kw):
    R["steps"].append(dict(step=step, **kw))


# ---------- 1. DT_Bldg_MinWidth: add TL's row -------------------------------
try:
    dt = EAL.load_asset(DT_MIN)
    before_names = [str(n) for n in dt.get_row_names()]
    before_count = len(before_names)
    already_has_tl = dt.does_row_exist("TL")
    if already_has_tl:
        note("DT_Bldg_MinWidth", action="already has TL row, skipped",
             row_count=before_count)
    else:
        full_csv = dt.export_to_csv_string()
        if not full_csv.endswith("\n"):
            full_csv += "\n"
        new_row = 'TL,"TL","950.000000","LV1"\n'
        combined = full_csv + new_row
        fill_ok = dt.fill_from_csv_string(combined)
        after_names = [str(n) for n in dt.get_row_names()]
        after_count = len(after_names)
        rows_lost = [n for n in before_names if n not in after_names]
        rows_gained = [n for n in after_names if n not in before_names]
        note("DT_Bldg_MinWidth",
             action="appended TL row",
             fill_from_csv_string_return=bool(fill_ok),
             row_count_before=before_count,
             row_count_after=after_count,
             rows_lost=rows_lost,
             rows_gained=rows_gained,
             does_row_exist_TL_after=dt.does_row_exist("TL"),
             csv_fed=new_row)
        if rows_lost or not dt.does_row_exist("TL"):
            R["errors"].append(
                "DT_Bldg_MinWidth: fill produced unexpected result "
                "(rows_lost=%s, has_TL=%s)" % (rows_lost, dt.does_row_exist("TL")))
        else:
            if not EAL.save_loaded_asset(dt):
                R["errors"].append("DT_Bldg_MinWidth: save_loaded_asset returned False")
except Exception as e:
    R["errors"].append("DT_Bldg_MinWidth: %s: %s" % (type(e).__name__, e))

dt = None

# ---------- 2. DT_Bldg_LevelMinWidth: TL's per-level rows ------------------
# TL_LV0..TL_LV4. The table is rewritten to exactly these TL rows on every run
# (other styles' rows are kept verbatim), so a level added to the kit lands
# here without a manual step. Not read by the 18-stage city; kept for
# Filter_Footprints_for_bldgs.
TL_LEVEL_ROWS = [
    ("TL_LV0", "LV0", 0, "[FC][FS2]+[LC]", "False", "C_E", 40.0, 200.0, 280.0),
    ("TL_LV1", "LV1", 1, "[FC][WS1][W1]+[LC]", "False", "C_CE", 150.0, 650.0, 950.0),
    ("TL_LV2", "LV2", 2, "[FC][WS1][W1]+[LC]", "False", "C_CE", 150.0, 650.0, 950.0),
    ("TL_LV3", "LV3", 3, "[FC][WS1][W1]+[LC]", "False", "C_CE", 150.0, 650.0, 950.0),
    ("TL_LV4", "LV4", 4, "[FC][WS1][W1]+[LC]", "True", "C_CE", 150.0, 650.0, 950.0),
]
try:
    dt2 = EAL.load_asset(DT_LVL)
    before_names2 = [str(n) for n in dt2.get_row_names()]
    want = [r[0] for r in TL_LEVEL_ROWS]
    if sorted(n for n in before_names2 if n.startswith("TL_")) == sorted(want):
        note("DT_Bldg_LevelMinWidth", action="TL rows already present, skipped",
             row_count=len(before_names2))
    else:
        lines = dt2.export_to_csv_string().splitlines()
        kept = [l for l in lines if not l.startswith("TL_")]
        new_rows = ['%s,"TL","%s","%d","%s","%s","%s","%f","%f","%f"' % r for r in TL_LEVEL_ROWS]
        fill_ok2 = dt2.fill_from_csv_string("\n".join(kept + new_rows) + "\n")
        after_names2 = [str(n) for n in dt2.get_row_names()]
        others_before = [n for n in before_names2 if not n.startswith("TL_")]
        rows_lost2 = [n for n in others_before if n not in after_names2]
        note("DT_Bldg_LevelMinWidth", action="rewrote TL rows",
             fill_from_csv_string_return=bool(fill_ok2),
             row_count_before=len(before_names2), row_count_after=len(after_names2),
             rows_lost=rows_lost2, tl_rows=sorted(n for n in after_names2 if n.startswith("TL_")))
        if rows_lost2 or sorted(n for n in after_names2 if n.startswith("TL_")) != sorted(want):
            R["errors"].append("DT_Bldg_LevelMinWidth: fill produced unexpected result "
                               "(rows_lost=%s)" % rows_lost2)
        elif not EAL.save_loaded_asset(dt2):
            R["errors"].append("DT_Bldg_LevelMinWidth: save_loaded_asset returned False")
except Exception as e:
    R["errors"].append("DT_Bldg_LevelMinWidth: %s: %s" % (type(e).__name__, e))

dt2 = None

# ---------- 3. repoint LoadCitySampleData at BDF_WithTL ---------------------
try:
    lg = EAL.load_asset(LOAD)
    target_settings = None
    other_asset_vals = []
    for node in lg.get_editor_property("nodes"):
        try:
            s = node.get_settings()
        except Exception:
            continue
        if s is None:
            continue
        try:
            v = s.get_editor_property("asset")
        except Exception:
            continue
        if "CitySampleBuildingBDF_Asset_PCG" in str(v):
            target_settings = s
        else:
            other_asset_vals.append(str(v))

    if target_settings is None:
        # Maybe already repointed in a prior run -- look for BDF_WithTL instead.
        for node in lg.get_editor_property("nodes"):
            try:
                s = node.get_settings()
            except Exception:
                continue
            if s is None:
                continue
            try:
                v = s.get_editor_property("asset")
            except Exception:
                continue
            if "BDF_WithTL" in str(v):
                note("LoadCitySampleData", action="already repointed, skipped",
                     current_value=str(v))
                target_settings = "already_done"
                break
        if target_settings is None:
            R["errors"].append(
                "LoadCitySampleData: could not find the "
                "CitySampleBuildingBDF_Asset_PCG node to repoint")
    elif target_settings != "already_done":
        before_asset = str(target_settings.get_editor_property("asset"))
        new_asset = EAL.load_asset(NEW_BDF)
        if new_asset is None:
            raise RuntimeError("%s did not load" % NEW_BDF)
        target_settings.set_editor_property("asset", new_asset)
        after_asset = str(target_settings.get_editor_property("asset"))
        note("LoadCitySampleData",
             action="repointed asset",
             before_asset=before_asset,
             after_asset=after_asset,
             other_node_asset_vals=other_asset_vals,
             points_at_BDF_WithTL=("BDF_WithTL" in after_asset))
        if "BDF_WithTL" not in after_asset:
            R["errors"].append(
                "LoadCitySampleData: asset property did not read back as BDF_WithTL")
        else:
            if not EAL.save_loaded_asset(lg):
                R["errors"].append("LoadCitySampleData: save_loaded_asset returned False")
except Exception as e:
    R["errors"].append("LoadCitySampleData: %s: %s" % (type(e).__name__, e))

lg = None
target_settings = None

print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
