# tl_probe_cha_reference.py -- READ-ONLY. CHA reference facts for the TL kit
# rebuild: material instances per slot name, RULE_CHA_L01 module symbols and
# grammar, SGD_CHA_A slot fields, and Levels.IsTopper per style row.
import json
import re

EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers
GRAMMAR_FIELD = "grammar_10_4003928D40C6099DCA57829F48235D57"


def main():
    R = {}
    m = EAL.load_asset("/Game/Building/CH/A/Kit_Bldg_CHA_L1_A/Mesh/SM_BLDG_CHA_L01_A_Wall_01_N1")
    R["cha_wall_materials"] = {
        str(s.get_editor_property("material_slot_name")):
            s.get_editor_property("material_interface").get_path_name()
        for s in m.get_editor_property("static_materials")}

    for lv in ("L01", "L13", "L20"):
        rule = EAL.load_asset("/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_%s" % lv)
        if rule is None:
            continue
        txt = rule.get_editor_property("rule").export_text()
        g = re.search(GRAMMAR_FIELD + r'="([^"]*)"', txt)
        syms = re.findall(r'Symbol_6_F9FB29564DEA8BEF1EA1DD8AA30C03E3="([^"]*)"', txt)
        pivots = re.findall(r'PivotOffset_28_063B0B4741DD9478C20E8E83A4DFF20A=\(([^)]*)\)', txt)
        R["RULE_CHA_" + lv] = {"grammar": g.group(1) if g else None,
                                "symbols": syms, "pivots": pivots,
                                "top_fields": sorted(set(re.findall(r'(?:^\(|,)([A-Za-z]+_\d+_[0-9A-F]{32})=', txt)))[:40]}
    tl = EAL.load_asset("/Game/PCG/DataAssets/Buildings/TL/RULE_TL_L01")
    txt = tl.get_editor_property("rule").export_text()
    R["RULE_TL_L01_symbols"] = re.findall(r'Symbol_6_F9FB29564DEA8BEF1EA1DD8AA30C03E3="([^"]*)"', txt)

    sgd = EAL.load_asset("/CitySamplePCG/PCG/DataAssets/Buildings/CHA/SGD_CHA_A")
    R["SGD_CHA_A_main"] = sgd.get_editor_property("Main Grammar")
    R["SGD_CHA_A_slots"] = [s.export_text()[:400] for s in sgd.get_editor_property("Slots")][-3:]
    tsgd = EAL.load_asset("/Game/PCG/DataAssets/Buildings/TL/SGD_TL_A")
    R["SGD_TL_A_main"] = tsgd.get_editor_property("Main Grammar")
    R["SGD_TL_A_slots"] = [s.export_text()[:400] for s in tsgd.get_editor_property("Slots")]

    a = EAL.load_asset("/Game/PCG/DataAssets/BDF/BDF_WithTL")
    for it in a.get_editor_property("data").get_editor_property("tagged_data"):
        if "Levels" not in [str(t) for t in it.get_editor_property("tags")]:
            continue
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        toppers = {}
        for pt in d.get_points():
            if MA.get_bool_attribute(pt, md, "IsTopper"):
                tok = str(MA.get_name_attribute(pt, md, "BuildingToken"))
                toppers.setdefault(tok, []).append(
                    "%s(%g)" % (MA.get_string_attribute(pt, md, "LevelToken"),
                                MA.get_float_attribute(pt, md, "LevelHeight")))
        R["toppers"] = toppers
    return R


R = main()
mcp_result = json.loads(json.dumps(R, default=str))
