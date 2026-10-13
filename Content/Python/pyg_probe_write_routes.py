# pyg_probe_write_routes.py -- writes ONLY to a transient in-memory PCGGraph
# (outer /Engine/Transient, never saved, no asset created). Tests whether the
# properties a Python graph builder needs can be written from Python:
#   A. subgraph parameter overrides via parameters_overrides import_text
#      (scalar + the ActorReferences array, which has no typed helper)
#   B. graph user parameters via user_parameters import_text
#   C. inline pin default values on a metadata-op node
#   D. node comment / position
import json


def txt(v):
    return v.export_text() if hasattr(v, "export_text") else str(v)


def main():
    R = {}
    tp = unreal.find_package("/Engine/Transient")
    g = unreal.new_object(unreal.PCGGraph, tp, "PYG_PROBE_GRAPH")
    src = unreal.EditorAssetLibrary.load_asset("/CitySamplePCG/Levels/PCG/PCG_3_1_4_Lots")

    # ---- A. ActorReferences array through the whole-struct text route
    n, st = g.add_node_of_type(unreal.load_class(None, "/Script/PCG.PCGSubgraphSettings"))
    st.set_subgraph(unreal.EditorAssetLibrary.load_asset("/PCGPrimitives/Primitives/Get/Get_ActorDataByRef"))
    inst = st.get_editor_property("subgraph_instance")
    H = unreal.PCGGraphParametersHelpers
    before = txt(inst.get_editor_property("parameters_overrides"))
    R["A_before"] = before[:300]
    # take the official override text verbatim from Lots and swap the actor path
    off = None
    for sn in src.get_editor_property("nodes"):
        s = sn.get_settings()
        if s.get_class().get_name() == "PCGSubgraphSettings":
            si = s.get_editor_property("subgraph_instance")
            if si and si.get_editor_property("graph") and \
                    si.get_editor_property("graph").get_name() == "Get_ActorDataByRef":
                off = txt(si.get_editor_property("parameters_overrides"))
                break
    R["A_official"] = off[:400]
    want = off.replace("/CitySamplePCG/Levels/L_CitySamplePCG_Demo.L_CitySamplePCG_Demo",
                       "/Game/PyPCG/L_Probe.L_Probe")
    po = inst.get_editor_property("parameters_overrides")
    try:
        po.import_text(want)
        inst.set_editor_property("parameters_overrides", po)
        after = txt(inst.get_editor_property("parameters_overrides"))
        R["A_after"] = after[:400]
        R["A_roundtrip_exact"] = (after == want)
        R["A_is_overridden"] = H.is_overridden(inst, "ActorReferences")
    except Exception as e:
        R["A_err"] = str(e)[:300]

    # scalar helper on a different primitive, for comparison
    n2, st2 = g.add_node_of_type(unreal.load_class(None, "/Script/PCG.PCGSubgraphSettings"))
    st2.set_subgraph(unreal.EditorAssetLibrary.load_asset("/PCGPrimitives/Primitives/Transform/Transform_Areas_Expand"))
    i2 = st2.get_editor_property("subgraph_instance")
    try:
        H.set_double_parameter(i2, "Expand", 60000.0)
        R["A2_scalar"] = [H.get_double_parameter(i2, "Expand"), H.is_overridden(i2, "Expand")]
    except Exception as e:
        R["A2_err"] = str(e)[:300]

    # ---- B. user parameters on a fresh graph via text
    up_src = txt(src.get_editor_property("user_parameters"))
    try:
        up = g.get_editor_property("user_parameters")
        up.import_text(up_src)
        g.set_editor_property("user_parameters", up)
        got = txt(g.get_editor_property("user_parameters"))
        R["B_after"] = got[:300]
        R["B_roundtrip_exact"] = (got == up_src)
        R["B_get_double"] = H.get_double_parameter(g, "PlazaReservationRatio")
    except Exception as e:
        R["B_err"] = str(e)[:300]

    # ---- C. inline pin defaults on a maths node
    n3, st3 = g.add_node_of_type(unreal.load_class(None, "/Script/PCG.PCGMetadataMathsSettings"))
    R["C_dir"] = sorted(m for m in dir(st3) if "default" in m.lower())
    for prop in ("default_values", "DefaultValues"):
        try:
            R["C_get_" + prop] = txt(st3.get_editor_property(prop))[:200]
        except Exception as e:
            R["C_get_" + prop] = "ERR " + str(e)[:160]

    # ---- D. node comment / position
    try:
        n.set_node_position(123, 456)
        R["D_pos"] = list(n.get_node_position())
    except Exception as e:
        R["D_pos_err"] = str(e)[:200]
    for prop in ("node_comment", "NodeComment"):
        try:
            n.set_editor_property(prop, "hello")
            R["D_" + prop] = "set ok"
        except Exception as e:
            R["D_" + prop] = "ERR " + str(e)[:160]
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
