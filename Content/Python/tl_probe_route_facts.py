# tl_probe_route_facts.py -- READ-ONLY. Facts needed before adding a TL
# foundation, props, half corners and a roof:
#   * the per-call parameters of the three Assign_CitySampleBuildings calls
#     (Foundation / Staggered / heights / styles) in PCG_3_3_1_Buildings;
#   * CHA's level-0 module rows in BDF_WithTL and the NY foundation mesh bounds;
#   * SGD_CHA_A / SGD_TL_A slot structs in full (corner grammar fields);
#   * BDF_Input_Processor's roof nodes' parameter values;
#   * which levels carry actors tagged BuildingDemo.
import json

EAL = unreal.EditorAssetLibrary
H = unreal.PCGGraphParametersHelpers
MA = unreal.PCGMetadataAccessorHelpers


def title(n):
    try:
        t = n.get_editor_property("node_title")
        if t and str(t) != "None":
            return str(t)
    except Exception:
        pass
    return n.get_name()


def call_params():
    g = EAL.load_asset("/CitySamplePCG/Levels/PCG/PCG_3_3_1_Buildings")
    out = {}
    for n in g.get_editor_property("nodes"):
        s = n.get_settings()
        if s is None or "Subgraph" not in s.get_class().get_name():
            continue
        inst = s.get_editor_property("subgraph_instance")
        if inst is None:
            continue
        sg = inst.get_editor_property("graph")
        if sg is None or not sg.get_path_name().endswith("Assign_CitySampleBuildings"):
            continue
        rec = {}
        for p, fn in (("Foundation", "get_bool_parameter"), ("Staggered", "get_bool_parameter"),
                      ("MinHeight", "get_double_parameter"), ("MaxHeight", "get_double_parameter"),
                      ("BuildingsStyles", "get_string_parameter"), ("SpawnMeshes", "get_bool_parameter")):
            try:
                rec[p] = getattr(H, fn)(inst, p)
                rec[p + "_overridden"] = H.is_overridden(inst, p)
            except Exception as e:
                rec[p] = "ERR %s" % e
        out[title(n)] = rec
    return out


def level0_rows():
    a = EAL.load_asset("/Game/PCG/DataAssets/BDF/BDF_WithTL")
    rows = []
    for it in a.get_editor_property("data").get_editor_property("tagged_data"):
        if "Modules" not in [str(t) for t in it.get_editor_property("tags")]:
            continue
        d = it.get_editor_property("data").get_editor_property("data")
        md = d.mutable_metadata()
        for pt in d.get_points():
            tok = MA.get_string_attribute(pt, md, "BuildingToken")
            if tok not in ("CHA", "TL", "NYAA", "SFA"):
                continue
            if MA.get_integer32_attribute(pt, md, "Level") != 0:
                continue
            rows.append({"tok": tok, "sym": MA.get_string_attribute(pt, md, "Symbol"),
                         "size": MA.get_double_attribute(pt, md, "Size"),
                         "scal": MA.get_bool_attribute(pt, md, "bScalable"),
                         "name": MA.get_string_attribute(pt, md, "Mod_Name"),
                         "pivot": MA.get_vector_attribute(pt, md, "PivotOffset").to_tuple(),
                         "mesh": MA.get_soft_object_path_attribute(pt, md, "Mesh").export_text()})
    return rows


def mesh_bounds(paths):
    out = {}
    for p in paths:
        m = EAL.load_asset(p)
        if m is None:
            out[p] = None
            continue
        bb = m.get_bounding_box()
        out[p.rsplit("/", 1)[-1]] = {"min": [round(v) for v in bb.min.to_tuple()],
                                     "max": [round(v) for v in bb.max.to_tuple()],
                                     "slots": [str(s.get_editor_property("material_slot_name"))
                                               for s in m.get_editor_property("static_materials")]}
    return out


def sgd_slots():
    out = {}
    for p in ("/CitySamplePCG/PCG/DataAssets/Buildings/CHA/SGD_CHA_A",
              "/Game/PCG/DataAssets/Buildings/TL/SGD_TL_A"):
        s = EAL.load_asset(p)
        out[p.rsplit("/", 1)[-1]] = {
            "main": s.get_editor_property("Main Grammar"),
            "slots": [x.export_text() for x in s.get_editor_property("Slots")][:3]}
        try:
            out[p.rsplit("/", 1)[-1]]["props"] = [nm for nm in dir(s) if not nm.startswith("_")][:80]
        except Exception:
            pass
    return out


def main():
    R = {"calls": call_params()}
    R["level0_rows"] = level0_rows()
    paths = sorted({r["mesh"].split(".")[0] for r in R["level0_rows"] if r["mesh"] and r["mesh"] != "None"})
    R["level0_mesh_bounds"] = mesh_bounds(paths)
    R["sgd"] = sgd_slots()
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
