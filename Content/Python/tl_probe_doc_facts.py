# tl_probe_doc_facts.py -- READ-ONLY. Exact values for the build-up document:
# the rooftop assembly list on the showcase graph's Fill node, the graph's
# user parameters as set on the showcase volume, the TL rows of BDF_WithTL
# (BDF / Levels / Modules / Props), and asset existence for every path cited.
import json
import re

MA = unreal.PCGMetadataAccessorHelpers
EAL = unreal.EditorAssetLibrary

CITED = [
    "/Game/Map/Lvl_TL_Showcase", "/Game/PCG/TL/PCG_TL_Building_BDF",
    "/Game/PCG/DataAssets/BDF/BDF_WithTL", "/Game/PCG/DataAssets/BDF/BDF_NamesOnly_WithTL",
    "/Game/PCG/DataAssets/Buildings/TL/SGD_TL_A",
    "/CitySamplePCG/PCG/Primitives/Buildings/Assign_CitySampleBuildings",
    "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/Assign_CitySampleBuildings_CoreProcess",
    "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/BDF_Input_Processor",
    "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/PartitionBDF_PerSpline",
    "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/BDF_BuildingFromSpline",
    "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/Loop_Subdivide",
    "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/Loop_GroupedPropsCopy",
    "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/ASM_Clutter_Behavior",
    "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/LoadCitySampleData",
    "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_MinWidth",
    "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/DT_Bldg_LevelMinWidth",
    "/CitySamplePCG/Examples/Building/Building_Staggered_LShape",
    "/Game/Environment/RoofTop/Material/MI/MI_Rooftop_BitumenRoofing",
    "/Game/Building/Material/MI/Brick/MI_Bldg_BrickOffset_Red",
    "/Game/Building/Material/MI/Block/MI_Bldg_Block_Limestone_Beige",
    "/Game/Building/Material/MI/MI_Bldg_Glass",
    "/Game/Building/Material/MI/Paint/MI_Bldg_PaintedMetal_Black",
    "/Game/Road/Material/MI/MI_Sidewalk_Plaza_A",
]


def fill_assets():
    g = EAL.load_asset("/Game/PCG/TL/PCG_TL_Building_BDF")
    for n in g.get_editor_property("nodes"):
        if n.get_name() != "Subgraph_5":
            continue
        inst = n.get_settings().get_editor_property("subgraph_instance")
        txt = inst.get_editor_property("parameters_overrides").export_text()
        return re.findall(r"RoofTops/(\w+)\.", txt)
    return []


def volume_params():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    H = unreal.PCGGraphParametersHelpers
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == "TL_Showcase_Building":
            gi = a.get_component_by_class(unreal.PCGComponent).get_editor_property("graph_instance")
            return {n: H.get_double_parameter(gi, n) for n in
                    ("WingAWidth", "WingALength", "WingBWidth", "WingBLength",
                     "BaseLayerHeight", "SecondLayerHeight")}
    return None


def tl_rows():
    a = EAL.load_asset("/Game/PCG/DataAssets/BDF/BDF_WithTL")
    out = {}
    for it in a.get_editor_property("data").get_editor_property("tagged_data"):
        tags = [str(t) for t in it.get_editor_property("tags")]
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        key = [t for t in tags if t != "BDFData"][0]
        rows = []
        for pt in d.get_points():
            if key == "Levels":
                if str(MA.get_name_attribute(pt, md, "BuildingToken")) != "TL":
                    continue
                rows.append({"LevelToken": MA.get_string_attribute(pt, md, "LevelToken"),
                             "LevelHeight": MA.get_float_attribute(pt, md, "LevelHeight"),
                             "F0": MA.get_string_attribute(pt, md, "F0"),
                             "F1": MA.get_string_attribute(pt, md, "F1"),
                             "F2": MA.get_string_attribute(pt, md, "F2"),
                             "FLengths": MA.get_vector_attribute(pt, md, "FLengths").to_tuple(),
                             "IsTopper": MA.get_bool_attribute(pt, md, "IsTopper")})
                continue
            if MA.get_string_attribute(pt, md, "BuildingToken") != "TL":
                continue
            if key == "BDF":
                rows.append({k: MA.get_string_attribute(pt, md, k) for k in
                             ("VerticalGrammar", "VerticalGrammarStaggered")})
                rows[-1].update({k: MA.get_float_attribute(pt, md, k) for k in
                                 ("MinWallWidth", "MinBldgHeight", "MaxBldgHeight")})
                rows[-1]["RoofData"] = MA.get_vector4_attribute(pt, md, "RoofData").export_text()
            elif key == "Modules":
                rows.append({"Level": MA.get_integer32_attribute(pt, md, "Level"),
                             "Symbol": MA.get_string_attribute(pt, md, "Symbol"),
                             "Size": MA.get_double_attribute(pt, md, "Size"),
                             "Mod_Name": MA.get_string_attribute(pt, md, "Mod_Name"),
                             "bScalable": MA.get_bool_attribute(pt, md, "bScalable"),
                             "HasProps": MA.get_bool_attribute(pt, md, "HasProps"),
                             "PivotOffset": [round(v, 2) for v in MA.get_vector_attribute(pt, md, "PivotOffset").to_tuple()]})
            elif key == "Props":
                t = pt.transform
                rows.append({"ModuleName": MA.get_string_attribute(pt, md, "ModuleName"),
                             "PropGroup": MA.get_string_attribute(pt, md, "PropGroup"),
                             "Type": MA.get_string_attribute(pt, md, "Type"),
                             "Probability": MA.get_double_attribute(pt, md, "Probability"),
                             "Mesh": MA.get_soft_object_path_attribute(pt, md, "Mesh").export_text().rsplit(".", 1)[-1],
                             "loc": [round(v, 1) for v in t.translation.to_tuple()],
                             "yaw": round(t.rotation.rotator().yaw),
                             "scale": round(t.scale3d.x, 2)})
        out[key] = rows
    return out


def main():
    return {"fill_assets": fill_assets(), "volume_params": volume_params(),
            "tl_rows": tl_rows(),
            "cited_missing": [p for p in CITED if not EAL.does_asset_exist(p)]}


mcp_result = json.loads(json.dumps(main(), default=str))
