# pcg_reuse_test_setup.py — phase A of the City Sample REUSE test.
#
# Goal: prove the migrated library can actually GENERATE, not merely load. The
# Building_Staggered_* examples are the best candidates: a byte scan shows each
# references only two /Game paths, one of which (MI_Rooftop_BitumenRoofing)
# resolves to real migrated art.
#
# Phase A does: spawn a test PCGVolume far from the delivered area, give it a
# real brush, assign one migrated graph, seed it, ACTIVATE, then generate.
# It deliberately does NOT save the level, so test residue cannot be committed.
#
# Reading the result must happen in a SEPARATE call — generation is async
# (references/node-classes.md 0.6). Reading here would return an empty
# collection without raising, which is the silent-zero trap.

import json

R = {}
def S(x):
    return str(x)

GRAPH = "/CitySamplePCG/Examples/Building/Building_Staggered_HShape"

# 20 km out so the test cannot overlap or disturb the delivered 3x3 area
TEST_ORIGIN = unreal.Vector(20000.0, 0.0, 0.0)

EAL = unreal.EditorAssetLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# ---- confirm the graph exists before touching the level ----
G = {}
try:
    G["exists"] = EAL.does_asset_exist(GRAPH)
    g = unreal.load_asset(GRAPH) if G["exists"] else None
    G["class"] = g.get_class().get_name() if g else None
    if g:
        G["nodes"] = len(g.get_editor_property("nodes"))
        G["edges"] = len(g.get_all_edges())
except Exception as e:
    G["err"] = "%s: %s" % (type(e).__name__, S(e)[:150])
R["graph"] = G

if not G.get("exists"):
    R["fatal"] = "graph not found: " + GRAPH
    print(json.dumps(R, indent=1, default=str))
    mcp_result = json.loads(json.dumps(R, default=str))
    raise SystemExit("graph missing")

# ---- remove any previous run's test volume ----
killed = []
for a in eas.get_all_level_actors():
    try:
        if a.get_class().get_name() == "PCGVolume" and \
                "ReuseTest" in S(a.get_actor_label()):
            c = a.get_component_by_class(unreal.PCGComponent)
            if c:
                try:
                    c.cleanup_local(True)
                except Exception:
                    pass
            eas.destroy_actor(a)
            killed.append(S(a.get_actor_label()))
    except Exception:
        continue
R["prior_test_volumes_destroyed"] = killed

# ---- spawn the test volume ----
V = {}
vol = eas.spawn_actor_from_class(unreal.PCGVolume, TEST_ORIGIN,
                                 unreal.Rotator(0.0, 0.0, 0.0))
if vol is None:
    R["fatal"] = "spawn returned None"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = json.loads(json.dumps(R, default=str))
    raise SystemExit("spawn failed")
V["spawned"] = True
try:
    vol.set_actor_label("PCGVolume_ReuseTest")
    V["label"] = S(vol.get_actor_label())
except Exception as e:
    V["label"] = "ERR %s" % S(e)[:80]

# A modest box around the origin of the test area. CubeBuilder x/y/z are FULL
# sizes (measured: x=3300 -> local bounds +-1650).
try:
    bb = vol.get_editor_property("brush_builder")
    for p, v in (("x", 8000.0), ("y", 8000.0), ("z", 4000.0)):
        bb.set_editor_property(p, v)
    V["brush_readback"] = [S(bb.get_editor_property(p)) for p in ("x", "y", "z")]
    V["local_bounds"] = S(vol.get_actor_local_bounds_pcg())
except Exception as e:
    V["brush_err"] = "%s: %s" % (type(e).__name__, S(e)[:150])

# ---- assign graph, activate, generate ----
pc = None
try:
    pc = vol.pcg_component
    V["pcg_component"] = S(pc)
except Exception as e:
    V["pcg_component"] = "ERR %s" % S(e)[:100]

if pc is not None:
    try:
        pc.set_graph(unreal.load_asset(GRAPH))
        V["graph_on_component"] = S(pc.get_graph())
    except Exception as e:
        V["graph_on_component"] = "ERR %s: %s" % (type(e).__name__, S(e)[:150])
    try:
        pc.set_editor_property("seed", 12345)
        V["seed"] = S(pc.get_editor_property("seed"))
    except Exception as e:
        V["seed"] = "ERR %s" % S(e)[:80]
    # without activate(), ShouldGenerate() is false and generate_local() is a
    # SILENT no-op (traps.md 18)
    try:
        pc.activate(True)
        V["activated"] = S(pc.get_editor_property("activated"))
    except Exception as e:
        V["activated"] = "ERR %s: %s" % (type(e).__name__, S(e)[:120])
    try:
        pc.generate_local(True)
        V["generate_local"] = "called"
    except Exception as e:
        V["generate_local"] = "ERR %s: %s" % (type(e).__name__, S(e)[:150])
R["volume"] = V

R["level_saved"] = "DELIBERATELY NOT SAVED (test residue must not be committed)"
R["next"] = "run pcg_reuse_test_read.py in a SEPARATE call"
print("reuse setup: graph_ok=%s activated=%s gen=%s" % (
    G.get("exists"), V.get("activated"), V.get("generate_local")))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
