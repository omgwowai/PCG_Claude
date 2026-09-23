# pcg_postmigration_regression.py
# After migrating City Sample content and restarting the editor, confirm the
# DELIVERED 3x3 area still works. The restart re-registered 147k assets and
# enabled 8 new plugins, so "it worked before the restart" is not evidence.
#
# Also re-verifies the migrated library is still mounted in this session, and
# reports the volume's current instance counts. Reads only; no generation, so
# no async concern.

import json

R = {}
def S(x):
    return str(x)

EAL = unreal.EditorAssetLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# ---- 1. delivered graph intact ----
G = {}
try:
    p = "/Game/PCGArea/PCG_SmallArea_3x3"
    G["exists"] = EAL.does_asset_exist(p)
    g = unreal.load_asset(p)
    if g:
        G["class"] = g.get_class().get_name()
        G["nodes"] = len(g.get_editor_property("nodes"))
        G["edges"] = len(g.get_all_edges())
    else:
        G["load"] = "None"
except Exception as e:
    G["err"] = "%s: %s" % (type(e).__name__, S(e)[:150])
R["delivered_graph"] = G

# ---- 2. the PCGVolume and its live instances ----
V = {}
vol = None
for a in eas.get_all_level_actors():
    if a.get_class().get_name() == "PCGVolume":
        vol = a
        break
if vol is None:
    V["fatal"] = "no PCGVolume in level"
else:
    V["label"] = S(vol.get_actor_label())
    V["scale"] = S(vol.get_actor_scale3d())
    try:
        V["graph"] = S(vol.pcg_component.get_graph())
    except Exception as e:
        V["graph"] = "ERR %s" % type(e).__name__
    comps = {}
    total = 0
    for c in vol.get_components_by_class(unreal.PrimitiveComponent):
        try:
            n = c.get_instance_count()
        except Exception:
            continue
        if n is None:
            continue
        comps[S(c.get_name())] = n
        total += n
    V["ism_components"] = comps
    V["total_instances"] = total
    V["expected"] = 41
    V["matches_delivery"] = (total == 41)
R["volume"] = V

# ---- 3. migrated library still mounted ----
M = {}
M["CitySamplePCG_dirs"] = EAL.does_directory_exist("/CitySamplePCG")
for p in ("/CitySamplePCG/Levels/PCG/PCG_3_3_1_Buildings",
          "/CitySamplePCG/PCG/DataAssets/Buildings/CHA/SGD_CHA_A"):
    try:
        a = EAL.load_asset(p)
        M[p.split("/")[-1]] = a.get_class().get_name() if a else None
    except Exception as e:
        M[p.split("/")[-1]] = "ERR %s" % type(e).__name__
R["migrated_library"] = M

# ---- 4. counts ----
I = {}
try:
    I["Game_total"] = len(EAL.list_assets("/Game", recursive=True, include_folder=False))
    I["CitySamplePCG_total"] = len(EAL.list_assets("/CitySamplePCG", recursive=True,
                                                  include_folder=False))
except Exception as e:
    I["err"] = type(e).__name__
R["inventory"] = I

ok = (G.get("nodes") == 12 and G.get("edges") == 12
      and V.get("matches_delivery") is True and M.get("CitySamplePCG_dirs") is True)
R["REGRESSION_PASS"] = bool(ok)
print("regression: graph=%sx%s instances=%s(cap 41) migrated=%s PASS=%s" % (
    G.get("nodes"), G.get("edges"), V.get("total_instances"),
    M.get("CitySamplePCG_dirs"), ok))
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
