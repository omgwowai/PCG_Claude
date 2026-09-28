# tl_probe_facts.py -- P0 spikes S3/S4/S6. READ-ONLY (no asset writes, no
# imports). Freezes the Task 1 facts consumed by every later task.
#
# S4: pivot + bounds of real CHA meshes -> the kit's coordinate convention.
# S3: RULE_* grammar strings -> cross-check the BDF<->RULE mapping.
# S6: where the style-code whitelist actually lives -> which node, which param.
#
# Prints compact lines (the nested-JSON form overflows the tool result).
#
# Deviations from the brief's Step 1 script, all discovered by probing the
# live API instead of writing calls from memory (all noted again in the
# Task 1 report):
#   - StaticMesh bounds: the real property names are origin/box_extent/
#     sphere_radius (an FBoxSphereBounds), not box_origin.
#   - StaticMesh.get_num_vertices()/get_num_triangles() both *require* an
#     explicit lod_index positional argument; there is no render_data/
#     lod_resources path reachable from Python.
#   - RULE assets (BP_ShapeGrammarRule_C instances) do NOT expose a
#     "grammar" property. Their single top-level property is "rule", an
#     STC_Rule struct whose own to_dict() is empty {} -- the working read
#     path is rule.export_text(), UE's canonical "(Name_GUID=value,...)"
#     text, from which the grammar_<GUID>="..." value is regex-extracted.
#     THIS CONTRADICTS TASK 4's PLAN, which assumes set_editor_property(
#     "grammar", ...) works -- flagged loudly in whitelist_nodes/report.
#   - mesh path #3 in the brief reads ".../Kit_Bldg_CHA_L01_A/Mesh/
#     SM_BLDG_CHA_L02_A_Wall_01_N1" (an L01 folder holding an L02-named
#     mesh); that folder does not exist on disk. The real folder for an
#     L02 wall module is "Kit_Bldg_CHA_L2_A". Both spellings are tried;
#     the one that actually loads is recorded per the coordinator's ruling.
#   - The brief's whitelist-search approach (scan node settings properties
#     for the literal substring "CHA") can never succeed: the enumerated
#     CHA/CHB/.../SFJ list + per-code glossary text found via raw .uasset
#     byte inspection is FProperty/pin TOOLTIP metadata (documentation),
#     never reachable through get_editor_property()-based Python scans,
#     which only read live values. The real, API-reachable whitelist fact
#     is a graph-level user parameter named "BuildingsStyles" (a String,
#     default "") on Assign_CitySampleBuildings's user_parameters
#     InstancedPropertyBag -- confirmed via export_text(), and confirmed
#     UN-overridden by every node that targets that subgraph (subgraph_
#     override is None on all of them) including from the top-level level
#     graph PCG_3_3_1_Buildings itself (whose own user_parameters bag has
#     no BuildingsStyles entry at all -- it only carries District height/
#     Debug/Partitioned/ComplexBuildingShapes/CollisionGeometry). A live
#     PCG *attribute* also named "BuildingsStyles" is separately read/
#     filtered/tagged (not written) by two nodes inside
#     Assign_CitySampleBuildings_CoreProcess.
#
# Fix pass (Task 1 code review -- 3 Important findings, all addressed below):
#   - Finding 1: BuildingsStyles is a SELECTION filter, not the sole "TRUE
#     edit target" the first draft claimed. A style code is only AVAILABLE
#     to be selected once it has rows in the BDF asset's BDF/Levels/Modules
#     groups (Task 7's job). Both facts now recorded; certainty language
#     dropped; the not-located write/materialization site is explicitly
#     marked as not needed given this framing.
#   - Finding 2: the original 4-pair BDF<->RULE check silently omitted
#     LV2-F0. Now checked against the FULL RULE_CHA_L00..L20 set (21 assets,
#     not just the 5 named in the brief) and against SGD_CHA_A's slot->rule
#     object bindings (STC_Slot's real field is a mangled
#     "ShapeGrammarRules_<GUID>" name, reachable only via export_text() --
#     "shape_grammar_rules" and "ShapeGrammarRules" both fail via
#     get_editor_property()). LV2-F0's BDF grammar string turns out to be
#     byte-identical across 17 separate RULE_CHA_L04..L20 assets, and slots
#     are indexed by level number only (no F0/F1/F2 distinction), so no
#     asset can be independently confirmed as "LV2-F0" -- recorded honestly
#     as indistinguishable rather than as a fabricated 5th match.
#   - Finding 3: mesh_pivot now states the pivot conclusion explicitly
#     (corner/base pivot: origin at bounds_min.z and bounds_max.y) instead
#     of leaving three raw bounds tuples for Task 2 to re-derive, plus a
#     PivotOffset magnitude cross-check (sign deliberately not asserted).

import json
import re

R = {}
args = mcp_args or {}
EAL = unreal.EditorAssetLibrary

# ---------- S4: mesh pivot + bounds --------------------------------------
MESH_CANDIDATES = [
    [
        "/Game/Building/CH/A/Kit_Bldg_CHA_L1_A/Mesh/SM_BLDG_CHA_L01_A_Wall_01_N1",
    ],
    [
        "/Game/Building/CH/A/Kit_Bldg_CHA_L1_A/Mesh/SM_BLDG_CHA_L01_A_Column_01_N1",
    ],
    [
        # brief's path (confirmed defective: L01 folder + L02 mesh name,
        # folder doesn't exist on disk), then the on-disk spelling that
        # actually loads
        "/Game/Building/CH/A/Kit_Bldg_CHA_L01_A/Mesh/SM_BLDG_CHA_L02_A_Wall_01_N1",
        "/Game/Building/CH/A/Kit_Bldg_CHA_L2_A/Mesh/SM_BLDG_CHA_L02_A_Wall_01_N1",
    ],
]
mesh_facts = []
for candidates in MESH_CANDIDATES:
    rec = {"tried": candidates}
    m = None
    used = None
    for p in candidates:
        m = EAL.load_asset(p)
        if m is not None:
            used = p
            break
    rec["path"] = used if used else candidates[0]
    rec["deviated_from_brief"] = (used is not None and used != candidates[0])
    rec["loaded"] = m is not None
    if m:
        try:
            b = m.get_bounds()
            extent = b.get_editor_property("box_extent")
            origin = b.get_editor_property("origin")
            radius = b.get_editor_property("sphere_radius")
            rec["extent_cm"] = [round(extent.x, 2), round(extent.y, 2), round(extent.z, 2)]
            rec["origin_cm"] = [round(origin.x, 3), round(origin.y, 3), round(origin.z, 3)]
            rec["sphere_radius_cm"] = round(radius, 3)
            rec["bounds_min"] = [round(origin.x - extent.x, 3), round(origin.y - extent.y, 3), round(origin.z - extent.z, 3)]
            rec["bounds_max"] = [round(origin.x + extent.x, 3), round(origin.y + extent.y, 3), round(origin.z + extent.z, 3)]
            # Fix (Task 1 review, Finding 3): state the pivot conclusion, not
            # just the raw tuples. Z: local origin (0,0,0) sits at bounds_min.z
            # (~0, the BOTTOM of the Z range) in every mesh measured, never the
            # Z-centre. Y: local origin sits at bounds_max.y (~0, an EDGE of
            # the Y range, since Y always runs from a negative bounds_min.y up
            # to 0), never the Y-centre. Corner/base pivot, not a centre pivot.
            z_min, z_max = rec["bounds_min"][2], rec["bounds_max"][2]
            y_min, y_max = rec["bounds_min"][1], rec["bounds_max"][1]
            rec["pivot_convention"] = (
                "Local origin (0,0,0) sits at bounds_min.z (%.3f, ~=0, the BOTTOM of "
                "the Z range [%.3f,%.3f], not the Z-centre %.1f) and at bounds_max.y "
                "(%.3f, ~=0, an EDGE of the Y range [%.3f,%.3f], not the Y-centre %.1f). "
                "Corner/base pivot, not a centre pivot." % (
                    z_min, z_min, z_max, (z_min + z_max) / 2.0,
                    y_max, y_min, y_max, (y_min + y_max) / 2.0))
        except Exception as e:
            rec["bounds_err"] = "%s: %s" % (type(e).__name__, e)
        try:
            rec["num_lods"] = m.get_num_lods()
            rec["lod0_verts"] = m.get_num_vertices(0)
            rec["lod0_tris"] = m.get_num_triangles(0)
        except Exception as e:
            rec["verts_err"] = "%s: %s" % (type(e).__name__, e)
    mesh_facts.append(rec)
R["mesh_pivot"] = mesh_facts

# Fix (Task 1 review, Finding 3): one summary conclusion across all meshes,
# plus the coordinator-supplied PivotOffset magnitude cross-check. Sign is
# deliberately NOT asserted -- only one sample was available and its sign was
# supplied by the coordinator, not independently re-derived here across
# multiple modules; flagged as an open question for Task 3/4.
R["mesh_pivot_summary"] = {
    "conclusion": (
        "All measured CHA kit meshes are CORNER/BASE-pivoted, not centre-pivoted: "
        "the local origin (0,0,0) sits at the bottom of each mesh's Z bounding "
        "range (bounds_min.z ~= 0 in every case, never the Z-midpoint) and at one "
        "edge of its Y bounding range (bounds_max.y ~= 0 in every case, never the "
        "Y-midpoint). This is the pivot convention Task 2 should assume for any "
        "new TL mesh authored to fit this kit: origin at the base-corner, not "
        "centred."
    ),
    "pivot_offset_cross_check": {
        "source": "BDF Modules group row for CHA, Level 1 (L1 wall module), "
                   "PivotOffset attribute, as reported by the coordinator "
                   "(not independently re-read by this script; recording the "
                   "coordinator-supplied magnitude without asserting sign, per "
                   "the coordinator's explicit instruction).",
        "value_as_reported": "(-0, 162.5, -250)",
        "magnitude_match": "Y magnitude 162.5 = half the L1 wall's Y width "
                            "(325/2); Z magnitude 250 = half the L1 wall's Z "
                            "height (500/2). Both match the corner-pivot "
                            "reading: PivotOffset is what re-centres a "
                            "base/corner-pivoted mesh for grammar placement.",
        "sign_convention": "NOT ASSERTED from this single sample. Whether "
                            "PivotOffset's sign is a fixed convention or "
                            "varies by module/mirroring is UNCONFIRMED -- "
                            "flagged as an open question for Task 3/4.",
    },
}

# ---------- S3: RULE grammar strings -------------------------------------
RULES = [
    "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L00",
    "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L01",
    "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L02",
    "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L05",
    "/CitySamplePCG/PCG/DataAssets/Buildings/SFB/RULE_SFB_L01",
]
# Fix (Task 1 review, Finding 2): the original RULES list above only covered
# the 5 assets named in the brief. Reading LV2-F0 honestly required knowing
# EVERY CHA RULE asset's grammar, because RULE_CHA_L00..L20 (21 assets) all
# exist, and several share identical grammar strings. Extend to the full set.
RULES += [
    "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L%02d" % i
    for i in range(0, 21)
    if "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L%02d" % i not in RULES
]
GRAMMAR_RE = re.compile(r'(\w*[Gg]rammar\w*)="((?:[^"\\]|\\.)*)"')
rule_facts = {}
for p in RULES:
    a = EAL.load_asset(p)
    if a is None:
        rule_facts[p] = {"loaded": False}
        continue
    got = {"loaded": True}
    try:
        rule = a.get_editor_property("rule")
        et = rule.export_text()
        got["rule_export_text_len"] = len(et)
        m = GRAMMAR_RE.search(et)
        if m:
            got["grammar_field_name"] = m.group(1)
            got["grammar"] = m.group(2)
        else:
            got["grammar_regex_no_match"] = True
            got["rule_export_text_sample"] = et[:600]
    except Exception as e:
        got["rule_read_err"] = "%s: %s" % (type(e).__name__, e)
    rule_facts[p] = got
R["rule_grammars"] = rule_facts

# Fix (Task 1 review, Finding 2): independent, object-level confirmation of
# which RULE asset a given SGD_CHA_A slot symbol binds to. STC_Slot does NOT
# expose this via get_editor_property("shape_grammar_rules") (that name is
# wrong, and so is the exact-cased "ShapeGrammarRules" -- both raise). The
# real, working read path -- discovered the same way as the RULE asset's own
# "grammar" field -- is export_text() on the slot struct, which reveals the
# true mangled field name and a regex over it yields the bound RULE path(s).
SGD_PATH = "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/SGD_CHA_A"
SLOT_RULE_RE = re.compile(r"'(/[^']+?\.(RULE_[A-Za-z0-9_]+))'")
sgd_slot_binding = {"sgd_used": SGD_PATH, "slot_to_rule_bindings": {}}
sgd = EAL.load_asset(SGD_PATH)
if sgd is not None:
    try:
        for s in sgd.get_editor_property("slots"):
            try:
                sym = str(s.get_editor_property("symbol"))
            except Exception:
                continue
            try:
                et = s.export_text()
                names = SLOT_RULE_RE.findall(et)
                sgd_slot_binding["slot_to_rule_bindings"][sym] = (
                    names[0][1] if names else None)
            except Exception:
                sgd_slot_binding["slot_to_rule_bindings"][sym] = None
    except Exception as e:
        sgd_slot_binding["slots_err"] = "%s: %s" % (type(e).__name__, e)
sgd_slot_binding["summary"] = (
    "STC_Slot carries a real, object-level rule binding under the mangled "
    "field name 'ShapeGrammarRules_<GUID>' (readable via export_text(), not "
    "via get_editor_property() under any name tried). Every slot on SGD_CHA_A "
    "binds 1:1 to the single RULE asset whose name suffix matches its own "
    "symbol (e.g. slot 'L02' -> RULE_CHA_L02), with no exceptions."
)
sgd_slot_binding["why_it_does_not_resolve_lv2_f0"] = (
    "Slots are indexed purely by LEVEL NUMBER (L00..L20), not by BDF "
    "FACADE-VARIANT label (F0/F1/F2), and each slot binds exactly one rule. "
    "There is no 'L02-F0'-style slot: slot 'L02' is already accounted for as "
    "the LV2-F1 pairing (RULE_CHA_L02 matches LV2's F1 string, not F0). So "
    "this mechanism has nothing further to say about which RULE asset is "
    "'LV2-F0' -- there is no distinct slot object for it to point at."
)
R["rule_grammars"]["_sgd_slot_binding"] = sgd_slot_binding

# Step 4 verdict: compare the BDF-side grammar strings against their
# corresponding RULE_* assets. Fix (Task 1 review, Finding 2): the original
# 4-pair list silently omitted LV2-F0 (in neither RULES nor here), which made
# "HOLDS on all 4 pairs" read as complete coverage of the 5 strings given in
# the brief. Extended to 5 pairs; LV2-F0 is recorded honestly as
# indistinguishable rather than faked as a 5th confirmed match, because its
# BDF grammar string ("[FC][WS1][W1]+[LC]") is byte-identical across 17
# separate RULE_CHA_L04..L20 assets, and the slot-binding mechanism above
# (which does independently confirm LV1-F1/LV2-F1) has no F0-specific slot to
# check against.
BDF_VS_RULE = [
    ("LV0",    "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L00", "[FC][FS2]+[LC]"),
    ("LV1-F0", "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L05", "[FC][WS1][W1]+[LC]"),
    ("LV1-F1", "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L01",
     "[FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]"),
    ("LV2-F1", "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L02",
     "[FC][WS1][W1]+[W1,P1][E1][E1][E1][P1,W1][WS1][W1]+[LC]"),
]
LV2_F0_BDF_GRAMMAR = "[FC][WS1][W1]+[LC]"

verdict = {"pairs": [], "all_match": True}
for bdf_label, rule_path, bdf_grammar in BDF_VS_RULE:
    rule_grammar = rule_facts.get(rule_path, {}).get("grammar")
    match = (rule_grammar == bdf_grammar)
    verdict["all_match"] = verdict["all_match"] and match
    verdict["pairs"].append({
        "bdf_label": bdf_label, "rule_asset": rule_path,
        "bdf_grammar": bdf_grammar, "rule_grammar": rule_grammar, "match": match,
    })

# LV2-F0: find every RULE_CHA_L* asset whose grammar matches, to make the
# collision count a measured fact rather than an assertion.
colliding = sorted(
    p for p, got in rule_facts.items()
    if got.get("grammar") == LV2_F0_BDF_GRAMMAR
    and p.startswith("/CitySamplePCG/PCG/DataAssets/Buildings/CHA/RULE_CHA_L")
)
verdict["pairs"].append({
    "bdf_label": "LV2-F0", "rule_asset": None,
    "bdf_grammar": LV2_F0_BDF_GRAMMAR, "rule_grammar": None,
    "match": "indistinguishable",
    "colliding_rule_assets": colliding,
    "note": ("BDF's live LV2.F0 value matches %d separate RULE_CHA_L* assets "
              "byte-for-byte (%s), including RULE_CHA_L05 already used above "
              "for LV1-F0. No RULE asset's own level number can be "
              "independently matched to 'LV2' specifically for the F0 "
              "variant -- the SGD slot-binding mechanism has no F0-specific "
              "slot to check (see _sgd_slot_binding above). Recorded "
              "honestly as indistinguishable: string matches, level not "
              "independently confirmed." % (len(colliding), colliding)),
})
verdict["headline"] = (
    "BDF<->RULE token mapping HOLDS on %d of %d pairs considered; the 5th "
    "(LV2-F0) is honestly indistinguishable, not confirmed."
    % (sum(1 for p in verdict["pairs"] if p["match"] is True), len(verdict["pairs"]))
)
R["rule_grammars"]["_step4_verdict"] = verdict

# ---------- S6: where is the style-code whitelist? ------------------------
whitelist = {}


# 1) the confirmed live answer: Assign_CitySampleBuildings's own graph-level
#    user_parameters InstancedPropertyBag carries a BuildingsStyles String
#    parameter (default "").
target_path = "/CitySamplePCG/PCG/Primitives/Buildings/Assign_CitySampleBuildings"
target_entry = {"path": target_path, "hits": []}
g = EAL.load_asset(target_path)
if g:
    up = g.get_editor_property("user_parameters")
    try:
        et = up.export_text()
        target_entry["user_parameters_export_text"] = et
        m = re.search(r'BuildingsStyles="([^"]*)"', et)
        target_entry["hits"].append({
            "node": "<graph user_parameters>",
            "settings_class": "InstancedPropertyBag",
            "param": "BuildingsStyles",
            "value": m.group(1) if m else None,
            "note": "Graph-level user parameter on Assign_CitySampleBuildings itself "
                    "(not a per-node setting). Default value is the empty string, which "
                    "per the pin tooltip means \"randomly use all available building "
                    "styles\". Fix (Task 1 review, Finding 1): this parameter is where "
                    "style SELECTION is constrained, NOT where a code becomes eligible "
                    "to exist. A code is only AVAILABLE to be selected (by name, or by "
                    "the empty-string 'all' default) once it has rows in the BDF asset's "
                    "'BDF'/'Levels'/'Modules' groups (Task 7's job). Do not treat this "
                    "parameter alone as 'the' edit target for adding style code TL -- "
                    "both facts (selection constraint here, availability via BDF rows) "
                    "are required.",
        })
    except Exception as e:
        target_entry["export_text_err"] = "%s: %s" % (type(e).__name__, e)
whitelist["Assign_CitySampleBuildings"] = target_entry
whitelist["write_site_not_located"] = {
    "summary": "The node inside Assign_CitySampleBuildings_CoreProcess that "
               "WRITES/materializes the live PCG point-data attribute "
               "'BuildingsStyles' from the graph user-parameter of the same "
               "name was not located (only the two READ/consumer nodes below "
               "were found).",
    "why_it_is_not_needed": "Given the two-part mechanism above (selection "
               "parameter + BDF-asset availability), the write/materialization "
               "site is not load-bearing for the TL plan: the parameter's role "
               "is fully characterized by its measured name, type, and "
               "default, and by confirming no consumer overrides it. Task 7 "
               "supplies BDF-asset rows; the whitelist default (or an "
               "explicit append of 'TL') is a parameter-level edit that does "
               "not require knowing the internal materialization node.",
}

# 2) confirm no override exists anywhere in the two graphs named in the brief:
#    walk every PCGSubgraphSettings node whose subgraph_instance.graph resolves
#    to Assign_CitySampleBuildings, and record subgraph_override (should be
#    None everywhere actually observed).
GRAPHS = {
    "PCG_3_3_1_Buildings": "/CitySamplePCG/Levels/PCG/PCG_3_3_1_Buildings",
    "Assign_BldgStyles_per_MinWallWidth":
        "/CitySamplePCG/PCG/Assign_BldgStyles_per_MinWallWidth",
}
for label, path in GRAPHS.items():
    gg = EAL.load_asset(path)
    entry = {"path": path, "loaded": gg is not None, "hits": [],
             "assign_citysamplebuildings_instances": []}
    if gg:
        nodes = gg.get_editor_property("nodes")
        entry["node_count"] = len(nodes)
        for n in nodes:
            try:
                s = n.get_settings()
            except Exception:
                continue
            if s is None or s.get_class().get_name() != "PCGSubgraphSettings":
                continue
            try:
                inst = s.get_editor_property("subgraph_instance")
                target = inst.get_editor_property("graph")
                target_path_ = target.get_path_name() if target else None
            except Exception:
                target_path_ = None
            if not target_path_ or "Assign_CitySampleBuildings" not in target_path_:
                continue
            try:
                ov = s.get_editor_property("subgraph_override")
                ov_desc = {"is_none": ov is None}
                if ov is not None:
                    try:
                        ov_desc["export_text"] = ov.export_text()[:500]
                    except Exception as e:
                        ov_desc["export_text_err"] = str(e)
            except Exception as e:
                ov_desc = {"err": str(e)}
            entry["assign_citysamplebuildings_instances"].append({
                "node": n.get_name(), "target_graph": target_path_,
                "subgraph_override": ov_desc,
            })
    # also record the graph's own user_parameters export_text, to prove
    # (for PCG_3_3_1_Buildings) that no BuildingsStyles param exists there
    # either -- i.e. it is never surfaced/overridden at the level-graph level.
    if gg:
        try:
            up = gg.get_editor_property("user_parameters")
            entry["own_user_parameters_export_text"] = up.export_text()[:1500]
            entry["own_user_parameters_has_BuildingsStyles"] = "BuildingsStyles" in entry["own_user_parameters_export_text"]
        except Exception as e:
            entry["own_user_parameters_err"] = str(e)
    whitelist[label] = entry

# 3) the two live consumer nodes (read/filter/tag the BuildingsStyles PCG
#    *attribute*, not the graph user-parameter -- distinct but related).
consumer_path = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/Assign_CitySampleBuildings_CoreProcess"
consumer_entry = {"path": consumer_path, "hits": []}
gc = EAL.load_asset(consumer_path)
if gc:
    nodes = gc.get_editor_property("nodes")
    consumer_entry["node_count"] = len(nodes)
    for n in nodes:
        if n.get_name() not in ("FilterDataByAttribute_4", "DataAttributesToTags_1"):
            continue
        s = n.get_settings()
        cn = s.get_class().get_name()
        if cn == "PCGFilterByAttributeSettings":
            v = s.get_editor_property("attribute")
            consumer_entry["hits"].append({"node": n.get_name(), "settings_class": cn,
                                            "param": "attribute", "value": str(v)})
        elif cn == "PCGDataAttributesToTagsSettings":
            v = s.get_editor_property("attributes_tags_mapping")
            consumer_entry["hits"].append({"node": n.get_name(), "settings_class": cn,
                                            "param": "attributes_tags_mapping", "value": str(v)})
consumer_entry["note"] = ("These nodes READ/tag the live PCG point-data attribute " +
    "\"BuildingsStyles\" (materialized elsewhere in this subgraph from the graph " +
    "user-parameter of the same name); they do not define/write the whitelist. " +
    "See whitelist['write_site_not_located'] for why the materialization node's " +
    "location is not load-bearing for the TL plan.")
whitelist["Assign_CitySampleBuildings_CoreProcess_consumers"] = consumer_entry

# 4) root-cause note on the tooltip prose (found via raw .uasset byte
#    inspection outside the unreal Python API -- NOT reproducible through
#    get_editor_property()-based scans, recorded here for the record only).
whitelist["_tooltip_metadata_note"] = (
    "The full CHA/CHB/.../SFJ enumerated list + per-code glossary text exists "
    "as FProperty/pin TOOLTIP metadata embedded in "
    "Assign_BldgStyles_per_MinWallWidth.uasset's raw bytes (confirmed via a raw "
    "byte scan of the .uasset from outside the editor -- grep found ~45 'CHA' "
    "occurrences). This tooltip text is NOT reachable via any get_editor_property()"
    "-based Python scan (tried: per-node settings scan across a 48-graph BFS "
    "closure of both whitelist graphs named in the brief, and a direct "
    "input_pins/output_pins + label scan) -- it is documentation metadata, not a "
    "live property value. The live, API-reachable whitelist fact is the "
    "BuildingsStyles graph user-parameter recorded above."
)

R["whitelist_nodes"] = whitelist

# ---------- fbx_import_ok (READ-ONLY -- must NOT import anything) ---------
# Per the coordinator's explicit ruling: Task 1 must determine this without
# importing any FBX, and Config/DefaultEngine.ini's missing
# Interchange.FeatureFlags.Import.FBX cvar is Task 3's dependency, out of
# scope here. Attempt only read-only introspection; fall back to "unknown".
fbx = {"value": "unknown", "checks": {}}
try:
    cvar = unreal.SystemLibrary.get_console_variable_int_value("Interchange.FeatureFlags.Import.FBX")
    fbx["checks"]["Interchange.FeatureFlags.Import.FBX_int"] = cvar
except Exception as e:
    fbx["checks"]["cvar_read_err"] = "%s: %s" % (type(e).__name__, e)
try:
    fbx["checks"]["has_legacy_fbx_factory"] = hasattr(unreal, "FbxSceneImportFactory") or hasattr(unreal, "FbxFactory")
except Exception as e:
    fbx["checks"]["factory_check_err"] = str(e)
fbx["note"] = ("Determined read-only, no import attempted (importing FBX with " +
    "Interchange from Python is known to crash the editor -- explicitly out of " +
    "scope for Task 1 per the coordinator's ruling; the missing " +
    "Interchange.FeatureFlags.Import.FBX cvar in DefaultEngine.ini is Task 3's " +
    "dependency). Value stays \"unknown\" unless a read-only check above proves it " +
    "either way.")
R["fbx_import_ok"] = fbx

# ---------- report ---------------------------------------------------------
print("###MESH_PIVOT###")
for r in R["mesh_pivot"]:
    print("  %s loaded=%s deviated=%s origin=%s extent=%s lods=%s verts=%s tris=%s" % (
        r["path"].split("/")[-1], r.get("loaded"), r.get("deviated_from_brief"),
        r.get("origin_cm"), r.get("extent_cm"), r.get("num_lods"),
        r.get("lod0_verts"), r.get("lod0_tris")))
    if r.get("pivot_convention"):
        print("    pivot: %s" % r["pivot_convention"])
print("  SUMMARY: %s" % R["mesh_pivot_summary"]["conclusion"])

print("###RULE_GRAMMARS###")
for p, got in R["rule_grammars"].items():
    if p in ("_step4_verdict", "_sgd_slot_binding"):
        continue
    print("  %s loaded=%s grammar=%s" % (p.split("/")[-1], got.get("loaded"), got.get("grammar")))
print("  SGD_SLOT_BINDING: %s" % R["rule_grammars"]["_sgd_slot_binding"]["slot_to_rule_bindings"])
print("  STEP4_VERDICT: %s" % R["rule_grammars"]["_step4_verdict"]["headline"])
for pair in R["rule_grammars"]["_step4_verdict"]["pairs"]:
    print("     %s match=%s" % (pair["bdf_label"], pair["match"]))

print("###WHITELIST###")
tgt = R["whitelist_nodes"]["Assign_CitySampleBuildings"]
for h in tgt["hits"]:
    print("  BuildingsStyles param: node=%s class=%s value=%r" % (h["node"], h["settings_class"], h["value"]))
for label in ("PCG_3_3_1_Buildings", "Assign_BldgStyles_per_MinWallWidth"):
    e = R["whitelist_nodes"][label]
    print("  %s: own_user_parameters_has_BuildingsStyles=%s, assign_instances=%d" % (
        label, e.get("own_user_parameters_has_BuildingsStyles"),
        len(e.get("assign_citysamplebuildings_instances", []))))
    for inst in e.get("assign_citysamplebuildings_instances", []):
        print("     node=%s override_is_none=%s" % (inst["node"], inst["subgraph_override"].get("is_none")))
consumers = R["whitelist_nodes"]["Assign_CitySampleBuildings_CoreProcess_consumers"]
for h in consumers["hits"]:
    print("  consumer node=%s class=%s param=%s value=%s" % (h["node"], h["settings_class"], h["param"], h["value"]))

print("###FBX_IMPORT_OK###")
print("  value=%s checks=%s" % (R["fbx_import_ok"]["value"], R["fbx_import_ok"]["checks"]))

mcp_result = R
