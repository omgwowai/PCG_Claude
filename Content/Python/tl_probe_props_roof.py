# tl_probe_props_roof.py -- READ-ONLY. Facts for TL facade props and the roof:
#   * bounds + first material of candidate CitySample prop meshes;
#   * full point data (bounds, transform, density) of a few CHA Props rows;
#   * SelfPruning_0 / StaticMeshSpawner_2 settings in BDF_BuildingFromSpline;
#   * parameter overrides on BDF_Input_Processor's roof nodes and on the
#     stage graph's Create_Mesh_Planar roof nodes;
#   * the PCGGraph node-editing API surface.
import json

EAL = unreal.EditorAssetLibrary
MA = unreal.PCGMetadataAccessorHelpers
H = unreal.PCGGraphParametersHelpers

PROPS = [
    "/Game/Prop/BLDG/Kit_Prop_AC/Mesh/SM_BLDG_Prop_AC_Window_A01_N1",
    "/Game/Prop/BLDG/Kit_Prop_AC/Mesh/SM_BLDG_Prop_AC_Window_A02_N1",
    "/Game/Prop/BLDG/Kit_Prop_Lamp/Mesh/SM_BLDG_Prop_Lamp_Wall_A01_N1",
    "/Game/Prop/BLDG/Kit_Prop_Lamp/Mesh/SM_BLDG_Prop_Lamp_Wall_A02_N1",
    "/Game/Prop/BLDG/Kit_Prop_Lamp/Mesh/SM_BLDG_Prop_Lamp_Wall_C01_N1",
    "/Game/Prop/BLDG/Kit_Prop_FirehoseConn/Mesh/SM_BLDG_Prop_FirehoseConn_Outlet_A01_N1",
    "/Game/Prop/BLDG/B/Kit_Prop_BA/Mesh/SM_BLDG_Prop_BA_Sign_B01_N1",
    "/Game/Prop/BLDG/B/Kit_Prop_BA/Mesh/SM_BLDG_Prop_BA_Sign_E01_N1",
    "/Game/Prop/BLDG/B/Kit_Prop_BA/Mesh/SM_BLDG_Prop_BA_Awning_A01_N1",
    "/Game/Prop/BLDG/B/Kit_Prop_BA/Mesh/SM_BLDG_Prop_BA_Banner_B01_N1",
    "/Game/Prop/BLDG/B/Kit_Prop_BA/Mesh/SM_BLDG_Prop_BA_LargeBanner_C01_N1",
    "/Game/Prop/BLDG/B/Kit_Prop_BA/Mesh/SM_BLDG_Prop_BA_Text_A01_N1",
    "/Game/Prop/BLDG/B/Kit_Prop_BA/Mesh/SM_BLDG_Prop_BA_Marquee_A01_N1",
    "/Game/Prop/BLDG/Kit_LightSign/Mesh/SM_BLDG_Prop_LightSign_SignShort_A01_N1",
    "/Game/Prop/BLDG/Kit_LightSign/Mesh/SM_BLDG_Prop_LightSign_SignFlush_A01_N1",
    "/Game/Building/NY/A/Kit_PROP_NYA/Mesh/SM_PROP_NYA_A_Awning_07_N1",
]


def mesh_info(p):
    m = EAL.load_asset(p)
    if m is None:
        return None
    bb = m.get_bounding_box()
    mats = [s.get_editor_property("material_interface") for s in m.get_editor_property("static_materials")]
    return {"min": [round(v, 1) for v in bb.min.to_tuple()],
            "max": [round(v, 1) for v in bb.max.to_tuple()],
            "mat0": mats[0].get_path_name() if mats and mats[0] else None,
            "nmats": len(mats)}


def props_rows(token, limit):
    a = EAL.load_asset("/Game/PCG/DataAssets/BDF/BDF_WithTL")
    out = []
    for it in a.get_editor_property("data").get_editor_property("tagged_data"):
        if "Props" not in [str(t) for t in it.get_editor_property("tags")]:
            continue
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        for pt in d.get_points():
            if MA.get_string_attribute(pt, md, "BuildingToken") != token:
                continue
            out.append({"module": MA.get_string_attribute(pt, md, "ModuleName"),
                        "type": MA.get_string_attribute(pt, md, "Type"),
                        "group": MA.get_string_attribute(pt, md, "GroupType"),
                        "clutter": [MA.get_bool_attribute(pt, md, "Clutter"),
                                    MA.get_bool_attribute(pt, md, "ClutterLow")],
                        "mesh": MA.get_soft_object_path_attribute(pt, md, "Mesh").export_text().rsplit(".", 1)[-1],
                        "bmin": pt.get_editor_property("bounds_min").to_tuple(),
                        "bmax": pt.get_editor_property("bounds_max").to_tuple(),
                        "density": pt.get_editor_property("density"),
                        "steepness": pt.get_editor_property("steepness"),
                        "seed": pt.get_editor_property("seed"),
                        "loc": pt.transform.translation.to_tuple(),
                        "rot": pt.transform.rotation.rotator().to_tuple()})
            if len(out) >= limit:
                return out
    return out


def node_settings(graph, names):
    g = EAL.load_asset(graph)
    out = {}
    for n in g.get_editor_property("nodes"):
        if n.get_name() not in names:
            continue
        s = n.get_settings()
        rec = {"class": s.get_class().get_name()}
        for prop in ("pruning_type", "radius_similarity_factor", "randomized_pruning",
                     "use_collision_attribute", "mesh_selector_type", "out_attribute_name",
                     "static_mesh_component_property_overrides", "instance_packer_type",
                     "apply_mesh_bounds_to_points", "synchronous_load"):
            try:
                v = s.get_editor_property(prop)
                rec[prop] = v.export_text() if hasattr(v, "export_text") else str(v)
            except Exception:
                pass
        try:
            sel = s.get_editor_property("mesh_selector_parameters")
            rec["selector_class"] = sel.get_class().get_name()
            for prop in ("mesh_attribute", "use_attribute_material_overrides",
                         "material_override_attributes", "template_descriptor"):
                try:
                    v = sel.get_editor_property(prop)
                    rec["sel." + prop] = v.export_text() if hasattr(v, "export_text") else str(v)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            inst = s.get_editor_property("subgraph_instance")
            if inst is not None:
                pars = {}
                for p, fn in (("Material", "get_object_parameter"), ("DynamicMesh", "get_bool_parameter"),
                              ("OutMeshName", "get_string_parameter")):
                    try:
                        v = getattr(H, fn)(inst, p)
                        pars[p] = v.get_path_name() if hasattr(v, "get_path_name") else v
                    except Exception as e:
                        pars[p] = "ERR %s" % e
                rec["params"] = pars
                try:
                    rec["instance_params"] = inst.get_editor_property("parameters_overrides").export_text()[:3000]
                except Exception as e:
                    rec["instance_params_err"] = str(e)
        except Exception:
            pass
        out[n.get_name()] = rec
    return out


def main():
    R = {"props": {p.rsplit("/", 1)[-1]: mesh_info(p) for p in PROPS}}
    R["cha_props"] = props_rows("CHA", 40)
    R["bfs_nodes"] = node_settings(
        "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/BDF_BuildingFromSpline",
        {"SelfPruning_0", "StaticMeshSpawner_2", "StaticMeshSpawner_3", "CreateConstant_26",
         "CreateConstant_27", "CreateConstant_28"})
    R["inproc_nodes"] = node_settings(
        "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/BDF_Input_Processor",
        {"Subgraph_2", "Subgraph_3"})
    R["stage_roof_nodes"] = node_settings(
        "/CitySamplePCG/Levels/PCG/PCG_3_3_1_Buildings",
        {"Subgraph_0", "Subgraph_28", "Subgraph_30", "Subgraph_22"})
    R["graph_api"] = [m for m in dir(unreal.PCGGraph) if not m.startswith("_")]
    R["subgraph_api"] = [m for m in dir(unreal.PCGSubgraphSettings) if "graph" in m.lower() or "subgraph" in m.lower()]
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
