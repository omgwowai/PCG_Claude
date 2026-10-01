# tl_verify_city.py -- Task 9 PHASE A: run the real city-buildings stage.
#
# Locates the PCGVolume carrying the PCG_3_3_1_Buildings graph by GRAPH PATH
# (never by actor order -- pcg_postmigration_regression.py's "first PCGVolume
# in the current level" pattern produced two false results in Task 10 because
# several unrelated levels each contain a PCGVolume). activate(True) is
# REQUIRED before generate_local -- skipping it is a silent zero (Task 6/10
# finding). Generation is ASYNCHRONOUS: this call only fires it. Read results
# with a SEPARATE call to tl_verify_city_read.py, never in this same call.
#
# Run from the DEMO level (/CitySamplePCG/Levels/L_CitySamplePCG_Demo) --
# that is the level with all 18 stage volumes wired up, per the Task 9 brief.
# This script does not switch levels itself (level switches are a distinct,
# riskier operation handled once, deliberately, by the caller) -- it only
# reports which level is current and aborts cleanly if the target volume
# is not present in it, rather than silently generating something else.

import json

R = {}
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

TARGET_GRAPH_EXACT = (
    "/CitySamplePCG/Levels/PCG/PCG_3_3_1_Buildings.PCG_3_3_1_Buildings"
)
TARGET_GRAPH_SUBSTR = "PCG_3_3_1_Buildings"

R["current_level"] = str(les.get_current_level())

candidates = []
for a in eas.get_all_level_actors():
    try:
        if a.get_class().get_name() != "PCGVolume":
            continue
    except Exception:
        continue
    try:
        comp = a.get_component_by_class(unreal.PCGComponent)
    except Exception:
        comp = None
    if comp is None:
        continue
    try:
        g = comp.get_graph()
        gpath = str(g.get_path_name()) if g else None
    except Exception:
        gpath = None
    if gpath and TARGET_GRAPH_SUBSTR in gpath:
        candidates.append({"actor": a.get_actor_label(), "graph": gpath,
                           "comp": comp, "exact_match": gpath == TARGET_GRAPH_EXACT})

R["candidates_found"] = [{"actor": c["actor"], "graph": c["graph"],
                          "exact_match": c["exact_match"]} for c in candidates]

if not candidates:
    R["fatal"] = ("No PCGVolume carrying graph containing '%s' found in the "
                 "current level. Not generating anything else -- reporting "
                 "this plainly per instructions." % TARGET_GRAPH_SUBSTR)
    R["generated"] = False
elif len(candidates) > 1:
    R["fatal"] = ("Multiple PCGVolumes matched '%s' -- ambiguous, refusing to "
                 "guess which one." % TARGET_GRAPH_SUBSTR)
    R["generated"] = False
else:
    c = candidates[0]
    comp = c["comp"]
    R["volume"] = {"actor": c["actor"], "graph": c["graph"],
                   "exact_match": c["exact_match"]}
    try:
        comp.activate(True)      # REQUIRED: silent zero without it
        comp.generate_local(True)
        R["generated"] = True
    except Exception as ex:
        R["generated"] = False
        R["generate_error"] = "%s: %s" % (type(ex).__name__, str(ex)[:300])

R["note"] = "async; read results with a SEPARATE call to tl_verify_city_read.py"
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
