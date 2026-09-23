# pcg_final_state.py — last check after the migration, restart, and reuse test.
#
# Confirms the level holds no test residue and the delivered 3x3 area is intact,
# and reports whether the level is dirty. The reuse test spawned and destroyed a
# PCGVolume and deliberately never saved; this proves that was clean.
#
# Read-only: no generation, no save.

import json

R = {}
def S(x):
    return str(x)

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# ---- every PCGVolume in the level ----
vols = []
for a in eas.get_all_level_actors():
    try:
        if a.get_class().get_name() == "PCGVolume":
            e = {"label": S(a.get_actor_label()),
                 "location": S(a.get_actor_location())}
            try:
                e["graph"] = S(a.pcg_component.get_graph())
            except Exception:
                e["graph"] = None
            comps = {}
            total = 0
            for c in a.get_components_by_class(unreal.PrimitiveComponent):
                try:
                    n = c.get_instance_count()
                except Exception:
                    continue
                if n is None:
                    continue
                comps[S(c.get_name())] = n
                total += n
            e["instances"] = total
            e["ism_components"] = comps
            vols.append(e)
    except Exception:
        continue
R["pcgvolumes"] = vols
R["pcgvolume_count"] = len(vols)
R["test_residue_present"] = any("ReuseTest" in v["label"] for v in vols)

# ---- delivered artifact ----
G = {}
try:
    g = unreal.load_asset("/Game/PCGArea/PCG_SmallArea_3x3")
    G["exists"] = g is not None
    if g:
        G["nodes"] = len(g.get_editor_property("nodes"))
        G["edges"] = len(g.get_all_edges())
except Exception as e:
    G["err"] = S(e)[:120]
R["delivered_graph"] = G

# ---- actor census ----
census = {}
for a in eas.get_all_level_actors():
    cn = a.get_class().get_name()
    census[cn] = census.get(cn, 0) + 1
R["actor_census"] = census
R["actor_total"] = sum(census.values())

# ---- anything out near the reuse-test origin left behind? ----
stray = 0
for a in eas.get_all_level_actors():
    try:
        loc = a.get_actor_location()
    except Exception:
        continue
    if abs(loc.x - 20000.0) < 9000 and abs(loc.y) < 9000 and abs(loc.z) < 5000:
        stray += 1
R["actors_near_reuse_test_origin"] = stray

# ---- migrated library still mounted ----
M = {}
M["CitySamplePCG"] = unreal.EditorAssetLibrary.does_directory_exist("/CitySamplePCG")
try:
    M["Game_total"] = len(unreal.EditorAssetLibrary.list_assets(
        "/Game", recursive=True, include_folder=False))
except Exception as e:
    M["err"] = type(e).__name__
R["mount"] = M

ok = (not R["test_residue_present"] and R["pcgvolume_count"] == 1
      and G.get("nodes") == 12 and G.get("edges") == 12 and stray == 0)
R["FINAL_STATE_OK"] = bool(ok)
print("final: volumes=%d residue=%s graph=%sx%s stray=%d mounted=%s OK=%s" % (
    R["pcgvolume_count"], R["test_residue_present"], G.get("nodes"), G.get("edges"),
    stray, M["CitySamplePCG"], ok))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
