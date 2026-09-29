# tl_verify_sgd.py -- PHASE A: bind SGD_TL_A onto a probe PCGVolume, generate.
#
# Run tl_verify_sgd_read.py as a SEPARATE call afterwards: generation is async,
# so reading output in this same call would return an empty/stale collection
# with no error.
#
# --- Why this does NOT match the task-6 brief's draft script, and why that's
#     correct, not a shortcut (folded in from tl_probe_task6..g.py, all deleted):
#
# 1. `Assign_ShapeGrammarDefinition` is NOT a native settings class you add
#    with graph.add_node_of_type(unreal.load_class(None,
#    "/Script/PCG.PCGAssignShapeGrammarDefinitionSettings")). That class path
#    resolves to None, and passing an unguarded None settings class into
#    add_node_of_type() is a native engine assert (PCGGraph.cpp,
#    UPCGGraph::AddNodeOfType -> NewObject called with a nullptr class object)
#    that is NOT catchable by Python try/except -- it crashed the whole editor
#    process the first time this was tried. `Assign_ShapeGrammarDefinition` is
#    actually a content-only PCG SUBGRAPH asset shipped by the PCGPrimitives
#    plugin, not a settings class at all.
#
# 2. Because of (1), this script does not hand-build a graph from scratch.
#    Instead it reuses CitySamplePCG's own proven test harness graph,
#    `/CitySamplePCG/PCG/DataAssets/Buildings/PCG_Bldg_SGD_test`, which is the
#    exact mechanism CitySamplePCG uses to test all 27 of its other building
#    styles (CHA, CHB, ... SFJ) against Assign_ShapeGrammarDefinition. Every
#    PCGVolume_SGD_* actor in `Bldg_SGD_level` points at this one shared graph
#    asset and gets a DIFFERENT building purely via a per-actor parameter
#    override -- there is no per-style graph duplication upstream of this.
#
# 3. The brief's footprint-spline problem does not apply to this harness: the
#    graph's own node list (read via graph.nodes, not the nonexistent
#    get_nodes()) contains a PCGSubgraphNode named "CreateSplineShape_Footprint"
#    titled "Create Building Footprint Rectangle" -- the graph SYNTHESIZES its
#    own closed rectangular footprint spline in-graph from Width/Length
#    parameters. This is confirmed by Bldg_SGD_level itself: it has ZERO
#    spline-bearing Actors, yet all 27 PCGVolume actors generate full facades.
#    So neither brief route (a) (duplicate a spline actor) nor route (b) (stop,
#    report, no spline available) actually applies -- there is a third,
#    better-attested route: reuse the harness that already builds its own
#    spline, and override which SGD asset it assigns.
#
# 4. The per-actor override mechanism (this took 7 rounds of dir()-introspection
#    and one engine-source read to find, because PCGGraphInstance's own dir()
#    only shows cosmetic overrides -- override_category/color/description/title
#    -- never a "parameter" or "override" named accessor for user parameters):
#      PCGComponent.graph_instance                          (PCGGraphInstance)
#        .parameters_overrides                     (PCGOverrideInstancedPropertyBag)
#          .properties_i_ds_overridden             (TSet<FGuid>, read-only from
#                                                    Python -- VisibleAnywhere)
#          .parameters                                       (InstancedPropertyBag)
#    InstancedPropertyBag is a dynamically-typed property bag: its Python
#    wrapper does NOT expose named fields via dir()/getattr, and
#    get_editor_property("FieldName") on it raises "Failed to find property"
#    even for fields that visibly exist. The only way in is TEXT: `.export_text()`
#    on PCGVolume_SGD_CHA's own bag returns exactly:
#      (Value=/Engine/Transient.PropertyBag_...(ShapeGrammarDefinition="/Cit...
#      SGD_CHA_A.SGD_CHA_A",Width=4100.000000,Length=4500.000000,Height=5000.000000))
#    i.e. every authored PCGVolume_SGD_* actor already has exactly these 4
#    parameters (ShapeGrammarDefinition, Width, Length, Height) marked
#    overridden. `properties_i_ds_overridden`'s 4-GUID count matches exactly.
#    Since marking a NEW property overridden requires UPCGGraphInstance::
#    UpdatePropertyOverride(const FProperty*, bool), which needs a raw FProperty
#    pointer that is not Python-reachable, a freshly spawned PCGVolume +
#    comp.set_graph(graph) would carry an EMPTY override set with no Python path
#    to mark ShapeGrammarDefinition overridden. So this script DUPLICATES an
#    already-correctly-configured actor (PCGVolume_SGD_CHA) instead of spawning
#    fresh -- the override bookkeeping travels with the duplicate for free, and
#    only the bag's TEXT VALUE needs to change (regex-replacing the
#    ShapeGrammarDefinition="..." field in export_text(), then import_text()
#    back in, then writing the struct back up the copy chain:
#    bag -> parameters_overrides -> graph_instance, since UE's Python bindings
#    return USTRUCTs by value).
#
# Width/Length/Height are deliberately left at CHA's own proven values
# (4100/4500/5000 cm) -- this test is about TL's mesh/pivot/scale/forward-axis
# correctness, not about re-deriving footprint dimensions from scratch, and the
# grammar's "+" sections repeat to fill whatever height is given regardless of
# style.

import gc
import json
import re

SPAWN = unreal.Vector(400000.0, 0.0, 300.0)
SGD_TL_PATH = "/Game/PCG/DataAssets/Buildings/TL/SGD_TL_A"
SOURCE_LABEL = "PCGVolume_SGD_CHA"
PROBE_LABEL = "TL_SGD_Probe_Volume"

R = {}
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
EAL = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

R["current_level"] = str(les.get_current_level())

# ---------- clean any previous run -----------------------------------------
for a in eas.get_all_level_actors():
    try:
        if a.get_actor_label() == PROBE_LABEL:
            comp = a.get_component_by_class(unreal.PCGComponent)
            if comp:
                try:
                    comp.cleanup_local(True)
                except Exception:
                    pass
            eas.destroy_actor(a)
    except Exception:
        pass

# ---------- find the source actor to duplicate ------------------------------
source = None
for a in eas.get_all_level_actors():
    if a.get_actor_label() == SOURCE_LABEL:
        source = a
        break

if source is None:
    R["fatal"] = "source volume not found: %s -- is Bldg_SGD_level loaded?" % SOURCE_LABEL
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit

src_loc = source.get_actor_location()
offset = unreal.Vector(SPAWN.x - src_loc.x, SPAWN.y - src_loc.y, SPAWN.z - src_loc.z)

dup = eas.duplicate_actor(source, offset=offset)
if dup is None:
    R["fatal"] = "duplicate_actor returned None"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit

dup.set_actor_label(PROBE_LABEL)
loc = dup.get_actor_location()
R["duplicated"] = True
R["dup_location"] = [round(float(loc.x), 1), round(float(loc.y), 1), round(float(loc.z), 1)]

comp = dup.get_component_by_class(unreal.PCGComponent)
if comp is None:
    R["fatal"] = "duplicate has no PCGComponent"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit

# wipe whatever CHA generated content came along with the duplicate, so every
# instance counted in the read-phase is attributable purely to this run
try:
    comp.cleanup_local(True)
    R["pre_cleanup"] = "OK"
except Exception as e:
    R["pre_cleanup"] = "%s: %s" % (type(e).__name__, e)

# ---------- override the ShapeGrammarDefinition parameter -------------------
gi = comp.graph_instance
po = gi.get_editor_property("parameters_overrides")
bag = po.get_editor_property("parameters")

before = bag.export_text()
R["bag_before"] = before

sgd = EAL.load_asset(SGD_TL_PATH)
if sgd is None:
    R["fatal"] = "could not load SGD_TL_A at %s" % SGD_TL_PATH
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit
sgd_path = sgd.get_path_name()
R["sgd_path"] = sgd_path

m = re.search(r'ShapeGrammarDefinition="([^"]*)"', before)
if not m:
    R["fatal"] = "ShapeGrammarDefinition field not found in bag export_text: %r" % before
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit
R["old_sgd_in_bag"] = m.group(1)

new_text = before[:m.start(1)] + sgd_path + before[m.end(1):]
import_ok = bag.import_text(new_text)
R["import_text_result"] = str(import_ok)

# write the mutated struct back up the copy chain (structs come back by value)
po.set_editor_property("parameters", bag)
gi.set_editor_property("parameters_overrides", po)

after = gi.get_editor_property("parameters_overrides").get_editor_property("parameters").export_text()
R["bag_after"] = after
R["sgd_set_correctly"] = sgd_path in after

# ---------- generate ---------------------------------------------------------
comp.activate(True)          # REQUIRED: without this it is a silent zero
comp.generate_local(True)
R["generated"] = True

print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
del R
gc.collect()
