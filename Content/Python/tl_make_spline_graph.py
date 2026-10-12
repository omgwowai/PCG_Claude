# tl_make_spline_graph.py -- build /Game/PCG/TL/PCG_TL_SplineBuilding.
# docs/superpowers/specs/2026-10-09-tl-spline-building-design.md section 6 and
# docs/superpowers/plans/2026-10-12-tl-spline-building.md Tasks 7-10.
# Args: {"segments": "abc" | "abcd" | "abcde" | "all"} -- build up to that segment
# (each task extends the graph and verifies before the next).
import importlib
import json
import math
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


def build_segment_d(K, P):
    # subdivide each segment into wall modules, by storey level (Epic's
    # Loop_0/Loop_Subdivide: LevelNumber selects the matching ModulesInfo row).
    part = K.node("PCGMetadataPartitionSettings", partition_attribute_selectors=[Sel("LevelNumber")])
    K.edge(P["walls_in"], part, "In")
    minfo = K.node("PCGConvertToAttributeSetSettings")
    K.edge(P["modules"], minfo, "In")
    loop = K.copy("Loop_0")                               # Loop_Subdivide, as Epic wires it
    K.edge((part, "Out"), loop, "In")
    K.edge((minfo, "Out"), loop, "NewPin")
    # placement: copied from BDF_BuildingFromSpline (MeshForwardAxis == 2, TL's only value)
    fwd = K.node("PCGCopyAttributesSettings", input_source=Sel("$Rotation.Forward"),
                 output_target=Sel("ForwardDir"))
    K.edge((loop, "Out"), fwd, "Target")
    K.edge((loop, "Out"), fwd, "Source")
    swap = K.copy("AttributeMathsOp_17")                  # $Scale = $Scale.yxz
    K.edge((fwd, "Out"), swap, "InA")
    K.edge((fwd, "Out"), swap, "InB")
    rot = K.copy("MakeRotatorAttribute_3")                # MakeRotFromYZ(ForwardDir, $Rotation.Up)
    K.edge((swap, "Out"), rot, "Y")
    K.edge((swap, "Out"), rot, "Z")
    short = K.maths((rot, "Out"), "MULTIPLY", "$Scale.Y", Sel("ShortScale"), "$Scale.Y")
    piv = K.copy("AttributeMathsOp_22")                   # PivotOffset *= $Scale
    K.edge(short, piv, "InA")
    K.edge(short, piv, "InB")
    tdir = K.copy("AttributeVectorOp_3")                  # PivotOffset into world
    K.edge((piv, "Out"), tdir, "In")
    K.edge((piv, "Out"), tdir, "Transform")
    add = K.copy("AttributeMathsOp_23")                   # $Position += PivotOffset
    K.edge((tdir, "Out"), add, "InA")
    K.edge((tdir, "Out"), add, "InB")
    P["walls"] = (add, "Out")
    return P["walls"]


FAN_TEMPLATE_POINTS = 18     # ceil(180 / 10): enough slices for any turn
N_CEIL_EPS = 1e-6            # slice-count epsilon before CEIL (see build_segment_e)


def build_segment_e(K, P):
    """Corner fans (task-9-brief.md). One fan per storey vertex, built from the
    segment that STARTS there: PreviousAngle is the signed turn at the vertex
    (> 0 convex, measured: the footprint's shoelace area is positive after
    FORCE_CLOCKWISE and the L-shape's five convex corners read +90, its concave
    one -90), the vertex is $Position - Forward * SegLen / 2, the incoming
    exterior normal is $Rotation.Yaw - PreviousAngle - 90 and the fan sweeps
    PreviousAngle from it (corner_math.fan with area_sign = +1)."""
    s = K.maths(P["segs"], "ABS", "PreviousAngle", None, "AbsTurn")
    s, _ = K.filt(s, "AbsTurn", "GREATER_OR_EQUAL", value=("Double", "DoubleValue=1.000000"))
    s = K.maths(s, "MULTIPLY", "SegLen", 0.5, "HalfLen")
    s = K.maths(s, "MULTIPLY", "$Rotation.Forward", Sel("HalfLen"), "HalfVec")
    s = K.maths(s, "SUBTRACT", "$Position", Sel("HalfVec"), "VPos")
    s = K.maths(s, "DIVIDE", "AbsTurn", 10.0, "N")
    # Measured on TL_Pent (exact 160 deg turn): AbsTurn / 10 reads back a hair
    # above 16 and CEIL gave 17 slices against corner_math's 16. Subtract the
    # same kind of epsilon corner_math.fan does (ceil(x - 1e-9)) before CEIL;
    # 1e-6 slice = 1e-5 deg, far below any turn that matters, and N stays >= 1
    # because AbsTurn >= 1 deg here.
    s = K.maths(s, "SUBTRACT", "N", N_CEIL_EPS, "N")
    s = K.maths(s, "CEIL", "N", None, "N")                  # stays Double (bForceRoundingOpToInt off)
    s = K.maths(s, "DIVIDE", "AbsTurn", Sel("N"), "HalfA")
    s = K.maths(s, "MULTIPLY", "HalfA", 0.5, "HalfA")
    s = K.maths(s, "SUBTRACT", "$Rotation.Yaw", Sel("PreviousAngle"), "Yaw0")
    s = K.maths(s, "SUBTRACT", "Yaw0", 90.0, "Yaw0")
    for op, a, out in (("DEG_TO_RAD", "HalfA", "HalfRad"), ("COS", "HalfRad", "CosA"), ("SIN", "HalfRad", "SinA")):
        n = K.node("PCGMetadataTrigSettings", operation=getattr(unreal.PCGMetadataTrigOperation, op),
                   input_source1=Sel(a), output_target=Sel(out))
        K.edge(s, n, "In")
        s = (n, "Out")
    s = K.maths(s, "DIVIDE", "CosA", math.cos(math.radians(5.0)), "Sx")
    s = K.maths(s, "DIVIDE", "SinA", math.sin(math.radians(5.0)), "Sy")
    corners = s

    # 18 template points at x = 100 k. K is made an integer (ruling 2): Round
    # with bForceRoundingOpToInt writes Integer64. KH = k + 0.5 is computed
    # here, as a Double, before CopyPoints overwrites $Position.
    pts = []
    for k in range(FAN_TEMPLATE_POINTS):
        p = unreal.PCGPoint()
        p.set_editor_property("transform", unreal.Transform(location=unreal.Vector(100.0 * k, 0.0, 0.0)))
        pts.append(p)
    tmpl = K.node("PCGCreatePointsSettings", points_to_create=pts,
                  coordinate_space=unreal.PCGCoordinateSpace.WORLD)
    if len(tmpl.get_settings().get_editor_property("points_to_create")) != FAN_TEMPLATE_POINTS:
        raise RuntimeError("CreatePoints did not take %d template points" % FAN_TEMPLATE_POINTS)
    kf = K.maths((tmpl, "Out"), "DIVIDE", "$Position.X", 100.0, "KF")
    kh = K.maths(kf, "ADD", "KF", 0.5, "KH")
    kk = K.node("PCGMetadataMathsSettings", operation=unreal.PCGMetadataMathsOperation.ROUND,
                force_rounding_op_to_int=True, input_source1=Sel("KF"), output_target=Sel("K"))
    if not kk.get_settings().get_editor_property("force_rounding_op_to_int"):
        raise RuntimeError("K rounding node did not take force_rounding_op_to_int")
    K.edge(kh, kk, "In")

    # Source = the template, Target = the corners (ruling 4): every output
    # point inherits the corner's attributes (SOURCE_FIRST takes the source's
    # metadata as root and copies the target's other attributes onto it).
    cp = K.node("PCGCopyPointsSettings",
                attribute_inheritance=unreal.PCGCopyPointsMetadataInheritanceMode.SOURCE_FIRST)
    K.edge((kk, "Out"), cp, "Source")
    K.edge(corners, cp, "Target")
    # keep k < n. Written as N > K: the threshold is broadcast to the target's
    # type, and Integer64 -> Double broadcasts while Double -> Integer64 does not.
    s, _ = K.filt((cp, "Out"), "N", "GREATER", against="K")
    s = K.maths(s, "DIVIDE", "PreviousAngle", Sel("N"), "Step")
    s = K.maths(s, "MULTIPLY", "KH", Sel("Step"), "YawD")
    s = K.maths(s, "ADD", "Yaw0", Sel("YawD"), "Yaw")
    rot = K.node("PCGMetadataMakeRotatorSettings",
                 operation=unreal.PCGMetadataMakeRotatorOp.MAKE_ROT_FROM_ANGLES,
                 input_source1=Sel("@Last"), input_source2=Sel("@Last"), input_source3=Sel("Yaw"),
                 output_target=Sel("$Rotation"))
    K.edge(K.const("Double", 0.0, "Zero"), rot, "Roll")
    K.edge(K.const("Double", 0.0, "Zero"), rot, "Pitch")
    K.edge(s, rot, "Yaw")
    # output_type must be Vector: the default (Vector2) has no Z pin.
    vec = K.node("PCGMetadataMakeVectorSettings", output_type=unreal.PCGMetadataTypes.VECTOR,
                 input_source1=Sel("Sx"), input_source2=Sel("Sy"),
                 input_source3=Sel("@Last"), output_target=Sel("$Scale"))
    K.edge((rot, "Out"), vec, "X")
    K.edge((rot, "Out"), vec, "Y")
    K.edge(K.const("Double", 1.0, "One"), vec, "Z")
    pos = K.node("PCGCopyAttributesSettings", input_source=Sel("VPos"), output_target=Sel("$Position"))
    K.edge((vec, "Out"), pos, "Target")
    K.edge((vec, "Out"), pos, "Source")
    convex, concave = K.filt((pos, "Out"), "PreviousAngle", "GREATER", value=("Double", "DoubleValue=0.000000"))
    outs = []
    for port, sym in ((convex, "FF"), (concave, "FB")):
        tab, _ = K.filt(P["modules"], "Symbol", "EQUAL", value=("String", 'StringValue="%s"' % sym))
        tab_set = K.node("PCGConvertToAttributeSetSettings")
        K.edge(tab, tab_set, "In")
        m = K.node("PCGMatchAndSetAttributesSettings", match_attributes=True,
                   input_attribute=Sel("LevelNumber"), match_attribute=Sel("Level"), keep_unmatched=False)
        K.edge(port, m, "In")
        K.edge((tab_set, "Out"), m, "Match Data")
        outs.append((m, "Out"))
    P["fans"] = K.merge(*outs)
    return P["fans"]


def build_spawner(K, *ports):
    sp = K.copy("StaticMeshSpawner_3", synchronous_load=True)   # mesh by attribute "Mesh" (traps.md 4)
    K.edge(K.merge(*ports), sp, "In")
    return (sp, "Out")


def main():
    g, height_node = fresh_graph()
    K = GraphKit(g)
    P = build_segments_abc(K, height_node)
    seg = args.get("segments", "abc")
    if seg == "abc":
        # expose the edge stream for the probe; Task 8 replaces this
        K.edge(P["walls_in"], g.get_output_node(), "Out")
    if seg in ("abcd", "abcde", "all"):
        # Every dispatch past segment C ends in exactly ONE spawner and ONE
        # output edge; only what feeds the spawner differs:
        #   abcd  = walls
        #   abcde = walls + fans
        #   all   = walls + fans (+ props and roof, Task 10)
        spawn_in = [build_segment_d(K, P)]
        if seg in ("abcde", "all"):
            spawn_in.append(build_segment_e(K, P))
        K.edge(build_spawner(K, *spawn_in), g.get_output_node(), "Out")
    elif seg != "abc":
        raise RuntimeError("unknown segments %r" % seg)
    ok = unreal.EditorAssetLibrary.save_asset(DEST, only_if_is_dirty=False)
    return {"saved": ok, "nodes": len(g.get_editor_property("nodes")),
            "edges": len(g.get_all_edges()), "segments": seg}


mcp_result = json.loads(json.dumps(main(), default=str))
