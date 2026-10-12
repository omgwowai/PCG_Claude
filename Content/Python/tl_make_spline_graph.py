# tl_make_spline_graph.py -- build /Game/PCG/TL/PCG_TL_SplineBuilding.
# docs/superpowers/specs/2026-10-09-tl-spline-building-design.md section 6 and
# docs/superpowers/plans/2026-10-12-tl-spline-building.md Tasks 7-10.
# Args: {"segments": "abc" | "abcd" | "abcde" | "all"} -- build up to that segment
# (each task extends the graph and verifies before the next).
import importlib
import json
import sys

sys.path.insert(0, unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python"))
import tl_graph_kit
importlib.reload(tl_graph_kit)
from tl_graph_kit import GraphKit, Sel, Txt

args = mcp_args or {}
DEST = "/Game/PCG/TL/PCG_TL_SplineBuilding"
TEMPLATE = "/CitySamplePCG/PCG/DataAssets/Buildings/PCG_Bldg_SGD_test"   # owns the Height parameter (R4)
SUB = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/"
PIER_FILLER_CM = 625.0     # 150 + 325 + 150 (ruling R1)
FOUND_FILLER_CM = 200.0


def fresh_graph():
    EAL = unreal.EditorAssetLibrary
    if EAL.does_asset_exist(DEST):
        if not EAL.delete_asset(DEST) or EAL.does_asset_exist(DEST):
            raise RuntimeError("could not delete the previous %s (traps.md 17)" % DEST)
    g = EAL.duplicate_asset(TEMPLATE, DEST)
    if g is None:
        raise RuntimeError("duplicate_asset returned None")
    keep = None
    doomed = []
    for n in g.get_editor_property("nodes"):
        st = n.get_settings()
        if st.get_class().get_name() == "PCGGenericUserParameterGetSettings" and \
                str(st.get_editor_property("property_path")) == "Height":
            keep = n
        else:
            doomed.append(n)
    # Measured (Task 7): UPCGGraph::RemoveNodes takes a non-const TArray<UPCGNode*>&
    # ("out" style in the Python binding), so g.remove_nodes(doomed) raises
    # "takes no arguments" and a zero-arg call does nothing. Use RemoveNode in a
    # loop instead -- functionally identical, just not the bulk path.
    for n in doomed:
        g.remove_node(n)
    if keep is None:
        raise RuntimeError("template has no Height getter")
    return g, keep


def tl_group(K, load, tag, token_type):
    f = K.node("PCGFilterByTagSettings", operation=unreal.PCGFilterByTagOperation.KEEP_TAGGED,
               selected_tags=tag)
    K.edge(load, f, "In")
    inside, _ = K.filt((f, "InsideFilter"), "BuildingToken", "EQUAL",
                       value=(token_type, '%sValue="TL"' % token_type))
    return inside


def build_segments_abc(K, height_node):
    P = {}
    # ---- A. data
    load = (K.sub(SUB + "LoadCitySampleData"), "Out")
    P["levels"] = tl_group(K, load, "Levels", "Name")       # Levels.BuildingToken is a Name
    P["modules"] = tl_group(K, load, "Modules", "String")
    P["props"] = tl_group(K, load, "Props", "String")
    P["bdf"] = tl_group(K, load, "BDF", "String")

    # ---- B. footprint and storeys
    spl = K.node("PCGGetSplineSettings")                    # actor selector defaults to Self
    clean = K.node("PCGCleanSplineSettings", fuse_colocated_control_points=True,
                   remove_collinear_control_points=True, collinear_angle_threshold=1.0)
    cw = K.node("PCGReverseSplineSettings", operation=unreal.PCGReverseSplineOperation.FORCE_CLOCKWISE)
    K.edge((spl, "Out"), clean, "In")
    K.edge((clean, "Out"), cw, "In")
    P["footprint"] = (cw, "Out")
    hvec = K.node("PCGMetadataMathsSettings", operation=unreal.PCGMetadataMathsOperation.MULTIPLY,
                  input_source1=Sel("@Last"), output_target=Sel("ExtrudeVector"))
    K.edge((height_node, "Out"), hvec, "InA")
    K.edge(K.const("Vector", "(X=0.0,Y=0.0,Z=1.0)", "Up"), hvec, "InB")
    addext = K.node("PCGAddAttributeSettings", input_source=Sel("ExtrudeVector"),
                    output_target=Sel("@Data.ExtrudeVector"))
    K.edge(P["footprint"], addext, "In")
    K.edge((hvec, "Out"), addext, "Attributes")
    vg = K.node("PCGCopyAttributesSettings", input_source=Sel("VerticalGrammar"),
                output_target=Sel("@Data.VerticalGrammar"))
    K.edge((addext, "Out"), vg, "Target")
    K.edge(P["bdf"], vg, "Source")
    # Levels as module info: Epic adds Scalable=False and casts Size to Double first
    scal = K.copy("AddAttribute_6")
    K.edge(P["levels"], scal, "In")
    cast = K.copy("AttributeCast_3")
    K.edge((scal, "Out"), cast, "In")
    lvl_info = K.node("PCGConvertToAttributeSetSettings")
    K.edge((cast, "Out"), lvl_info, "In")
    dcs = K.copy("DuplicateCrossSections_1", extrude_vector_attribute=Sel("@Data.ExtrudeVector"))
    K.edge((vg, "Out"), dcs, "In")
    K.edge((lvl_info, "Out"), dcs, "ModulesInfo")

    # ---- C. segments and their grammars
    seg = K.copy("SplineToSegment_0")
    K.edge((dcs, "Out"), seg, "In")
    hz = K.copy("AttributeMathsOp_0")                        # $BoundsMax.Z = Size.Z
    K.edge((seg, "Out"), hz, "InA")
    K.edge((seg, "Out"), hz, "InB")
    mas = K.copy("MatchAndSetAttributes_0")                  # FloorSymbol -> Levels row
    K.edge((hz, "Out"), mas, "In")
    K.edge((lvl_info, "Out"), mas, "Match Data")
    seglen = K.maths((mas, "Out"), "MULTIPLY", "$BoundsMax.X", 2.0, "SegLen")
    sscale = K.node("PCGAddAttributeSettings", output_target=Sel("ShortScale"),
                    attribute_types=Txt("(Type=Double,DoubleValue=1.000000)"))
    K.edge(seglen, sscale, "In")
    P["segs"] = (sscale, "Out")

    found, storeys = K.filt(P["segs"], "LevelNumber", "EQUAL", value=("Integer32", "Int32Value=0"))

    def short_branch(src, filler_symbol, filler_cm):
        g = K.node("PCGAddAttributeSettings", output_target=Sel("FloorGrammar"),
                   attribute_types=Txt('(Type=String,StringValue="[%s]")' % filler_symbol))
        K.edge(src, g, "In")
        s = K.maths((g, "Out"), "DIVIDE", "SegLen", filler_cm, "ShortScale")
        return K.maths(s, "POW", "ShortScale", -1.0, "$Scale.X")   # subdivision then sees filler_cm

    def const_grammar(src, text):
        g = K.node("PCGAddAttributeSettings", output_target=Sel("FloorGrammar"),
                   attribute_types=Txt('(Type=String,StringValue="%s")' % text))
        K.edge(src, g, "In")
        return (g, "Out")

    # storeys >= 1
    s_short, s_long = K.filt(storeys, "SegLen", "LESSER", value=("Double", "DoubleValue=%f" % PIER_FILLER_CM))
    in2, out2 = K.filt(s_long, "SegLen", "GREATER_OR_EQUAL", against="FLengths.Z")
    in1, out1 = K.filt(out2, "SegLen", "GREATER_OR_EQUAL", against="FLengths.Y")
    in0, mid = K.filt(out1, "SegLen", "GREATER_OR_EQUAL", against="FLengths.X")
    picked = []
    for src, f in ((in2, "F2"), (in1, "F1"), (in0, "F0")):
        r = K.node("PCGMetadataRenameSettings", attribute_to_rename=Sel(f), new_attribute_name="FloorGrammar")
        K.edge(src, r, "In")
        picked.append((r, "Out"))
    picked.append(const_grammar(mid, "[FC][WS1][LC]"))
    long_merged = K.merge(*picked)
    drop = K.node("PCGDeleteAttributesSettings",
                  operation=unreal.PCGAttributeFilterOperation.DELETE_SELECTED_ATTRIBUTES,
                  selected_attributes="F0,F1,F2")
    K.edge(long_merged, drop, "In")

    def replace(src, token, acute_attr, acute_tok, plain_tok):
        a_in, a_out = K.filt(src, acute_attr, "GREATER", value=("Double", "DoubleValue=90.000000"))
        outs = []
        for port, rep in ((a_in, acute_tok), (a_out, plain_tok)):
            n = K.node("PCGMetadataStringOpSettings",
                       operation=unreal.PCGMetadataStringOperation.REPLACE,
                       input_source1=Sel("FloorGrammar"), input_source2=Sel("@Last"),
                       input_source3=Sel("@Last"), output_target=Sel("FloorGrammar"))
            K.edge(port, n, tl_graph_kit.STRING3_PINS[0])
            K.edge(K.const("String", token, "Find"), n, tl_graph_kit.STRING3_PINS[1])
            K.edge(K.const("String", rep, "With"), n, tl_graph_kit.STRING3_PINS[2])
            outs.append((n, "Out"))
        return K.merge(*outs)

    starts = replace((drop, "Out"), "[FC", "PreviousAngle", "[EAL", "[EL")
    ends = replace(starts, "[LC", "NextAngle", "[EAR", "[ER")
    storey_short = short_branch(s_short, "WS1", 325.0)

    # foundation: no piers, grammar [FS2]+ (ruling R1 for short edges)
    f_short, f_long = K.filt(found, "SegLen", "LESSER", value=("Double", "DoubleValue=%f" % FOUND_FILLER_CM))
    found_long = const_grammar(f_long, "[FS2]+")
    found_short = short_branch(f_short, "FS2", FOUND_FILLER_CM)

    P["walls_in"] = K.merge(ends, storey_short, found_long, found_short)
    return P


def main():
    g, height_node = fresh_graph()
    K = GraphKit(g)
    P = build_segments_abc(K, height_node)
    seg = args.get("segments", "abc")
    if seg == "abc":
        # expose the edge stream for the probe; Task 8 replaces this
        K.edge(P["walls_in"], g.get_output_node(), "Out")
    ok = unreal.EditorAssetLibrary.save_asset(DEST, only_if_is_dirty=False)
    return {"saved": ok, "nodes": len(g.get_editor_property("nodes")),
            "edges": len(g.get_all_edges()), "segments": seg}


mcp_result = json.loads(json.dumps(main(), default=str))
