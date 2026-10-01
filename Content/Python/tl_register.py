# tl_register.py -- register TL: two DataTable row sets, the BuildingsStyles
# whitelist parameter, and the LoadCitySampleData repoint.
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
#     TL's LV0 row must match it; TL's own LV1-LV3 profile (C_CE/150/650/950,
#     mirroring CHA's LV1-LV3 and Task 7's BDF group data) is used for LV1-LV3.
#   * The style whitelist is a graph-LEVEL USER PARAMETER named "BuildingsStyles"
#     (String, default "") on Assign_CitySampleBuildings' user_parameters
#     InstancedPropertyBag -- not a literal string on any node (Task 1 scanned
#     the full 48-graph closure and found zero node-level hits).
#   * InstancedPropertyBag.set_editor_property()/set_editor_properties() both
#     raise "Failed to find property 'BuildingsStyles'" -- there is no working
#     setter by property name. The working mechanism is bag.import_text(text),
#     where text is bag.export_text() with the BuildingsStyles="..." substring
#     replaced. Proven to persist through a save/reload cycle.
#   * LoadCitySampleData has TWO PCGLoadDataAssetSettings nodes: one loads
#     CitySampleBuildingBDF_NamesOnly_PCG (leave alone), the other loads
#     CitySampleBuildingBDF_Asset_PCG (the one to repoint at BDF_WithTL). The
#     settings property holding the data asset is named "asset", not
#     "data_asset".
#
# Idempotent: every edit checks for TL's presence first and is a no-op if
# already registered. Safe to re-run.

import json

R = {"steps": [], "errors": []}
EAL = unreal.EditorAssetLibrary

DT_MIN = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_MinWidth"
DT_LVL = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_LevelMinWidth"
ASG    = "/CitySamplePCG/PCG/Primitives/Buildings/Assign_CitySampleBuildings"
LOAD   = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/LoadCitySampleData"
NEW_BDF = "/Game/PCG/DataAssets/BDF/BDF_WithTL"

ALL_27 = ["CHA", "CHB", "CHC", "CHD", "CHE", "CHF", "CHG", "CHH", "CHI", "CHJ",
          "NYAA", "NYAB", "NYAC", "NYAD", "NYAE", "NYAF", "NYG", "NYGA", "NYH",
          "QBA", "QBAA", "SFA", "SFB", "SFC", "SFD", "SFE", "SFJ"]


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
            EAL.save_loaded_asset(dt)
except Exception as e:
    R["errors"].append("DT_Bldg_MinWidth: %s: %s" % (type(e).__name__, e))

dt = None

# ---------- 2. DT_Bldg_LevelMinWidth: add TL's LV0-LV3 rows -----------------
try:
    dt2 = EAL.load_asset(DT_LVL)
    before_names2 = [str(n) for n in dt2.get_row_names()]
    before_count2 = len(before_names2)
    tl_rows_already = [n for n in before_names2 if n.startswith("TL_")]
    if tl_rows_already:
        note("DT_Bldg_LevelMinWidth", action="already has TL rows, skipped",
             tl_rows=tl_rows_already, row_count=before_count2)
    else:
        full_csv2 = dt2.export_to_csv_string()
        if not full_csv2.endswith("\n"):
            full_csv2 += "\n"
        # LV0 uses the universal LV0 corner profile shared by all 27 existing
        # styles (C_E/40/200/280); LV1-LV3 use TL's own profile, matching
        # CHA's LV1-LV3 and Task 7's BDF group Levels data (C_CE/150/650/950).
        new_rows = (
            'TL_LV0,"TL","LV0","0","[FC][FS2]+[LC]","False","C_E","40.000000","200.000000","280.000000"\n'
            'TL_LV1,"TL","LV1","1","[FC][WS1][W1]+[LC]","False","C_CE","150.000000","650.000000","950.000000"\n'
            'TL_LV2,"TL","LV2","2","[FC][WS1][W1]+[LC]","False","C_CE","150.000000","650.000000","950.000000"\n'
            'TL_LV3,"TL","LV3","3","[FC][WS1][W1]+[LC]","False","C_CE","150.000000","650.000000","950.000000"\n'
        )
        combined2 = full_csv2 + new_rows
        fill_ok2 = dt2.fill_from_csv_string(combined2)
        after_names2 = [str(n) for n in dt2.get_row_names()]
        after_count2 = len(after_names2)
        rows_lost2 = [n for n in before_names2 if n not in after_names2]
        rows_gained2 = [n for n in after_names2 if n not in before_names2]
        note("DT_Bldg_LevelMinWidth",
             action="appended TL LV0-LV3 rows",
             fill_from_csv_string_return=bool(fill_ok2),
             row_count_before=before_count2,
             row_count_after=after_count2,
             rows_lost=rows_lost2,
             rows_gained=rows_gained2,
             csv_fed=new_rows)
        if rows_lost2 or len(rows_gained2) != 4:
            R["errors"].append(
                "DT_Bldg_LevelMinWidth: fill produced unexpected result "
                "(rows_lost=%s, rows_gained=%s)" % (rows_lost2, rows_gained2))
        else:
            EAL.save_loaded_asset(dt2)
except Exception as e:
    R["errors"].append("DT_Bldg_LevelMinWidth: %s: %s" % (type(e).__name__, e))

dt2 = None

# ---------- 3. BuildingsStyles whitelist parameter --------------------------
try:
    g = EAL.load_asset(ASG)
    bag = g.get_editor_property("user_parameters")
    before_text = bag.export_text()

    # Extract the current BuildingsStyles="..." value, if any.
    marker = 'BuildingsStyles="'
    idx = before_text.find(marker)
    if idx == -1:
        raise RuntimeError("BuildingsStyles=\"...\" substring not found in export_text()")
    start = idx + len(marker)
    end = before_text.find('"', start)
    current_value = before_text[start:end]
    current_codes = [c for c in current_value.split(",") if c]

    if "TL" in current_codes:
        note("BuildingsStyles", action="already contains TL, skipped",
             before_text=before_text, current_value=current_value)
    else:
        if current_value == "":
            new_codes = ALL_27 + ["TL"]
        else:
            # Unexpected: the parameter was already set to something other
            # than the empty default, and it doesn't contain TL yet. Extend
            # the existing list rather than clobbering it, and flag loudly.
            new_codes = current_codes + ["TL"]
            R["errors"].append(
                "BuildingsStyles: parameter was non-empty and did not match "
                "the expected all-27 baseline before this run (value=%r); "
                "extended it with TL instead of overwriting -- verify by hand."
                % current_value)
        new_value = ",".join(new_codes)
        new_text = before_text.replace(
            marker + current_value + '"', marker + new_value + '"')
        import_ok = bag.import_text(new_text)
        after_text = bag.export_text()
        after_idx = after_text.find(marker)
        after_start = after_idx + len(marker)
        after_end = after_text.find('"', after_start)
        after_value = after_text[after_start:after_end]
        after_codes = [c for c in after_value.split(",") if c]
        missing_from_27 = [c for c in ALL_27 if c not in after_codes]
        note("BuildingsStyles",
             action="set via import_text",
             import_text_return=bool(import_ok),
             before_value=current_value,
             target_value=new_value,
             after_value=after_value,
             has_TL_after="TL" in after_codes,
             all_27_survive=(len(missing_from_27) == 0),
             missing_from_27=missing_from_27)
        if not import_ok or "TL" not in after_codes or missing_from_27:
            R["errors"].append(
                "BuildingsStyles: edit did not verify cleanly "
                "(import_ok=%s, has_TL=%s, missing=%s)"
                % (import_ok, "TL" in after_codes, missing_from_27))
        else:
            EAL.save_loaded_asset(g)
except Exception as e:
    R["errors"].append("BuildingsStyles: %s: %s" % (type(e).__name__, e))

g = None
bag = None

# ---------- 4. repoint LoadCitySampleData at BDF_WithTL ---------------------
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
            EAL.save_loaded_asset(lg)
except Exception as e:
    R["errors"].append("LoadCitySampleData: %s: %s" % (type(e).__name__, e))

lg = None
target_settings = None

print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
