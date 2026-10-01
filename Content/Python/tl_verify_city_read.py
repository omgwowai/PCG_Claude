# tl_verify_city_read.py -- Task 9 PHASE B: count TL instances in the
# generated city-buildings stage output.
#
# SEPARATE call from tl_verify_city.py -- generation is async, reading it in
# the same call returns an empty/stale census with no error (Task 6/10
# finding). Scans ONLY the PCG_3_3_1_Buildings volume's own components (found
# by graph path, same rule as the generate half) so "all_instances" means
# "everything this stage itself produced", not every ISM in the whole level
# (the demo level's other 17 stage volumes also carry instances and would
# swamp the denominator if counted together).
#
# Aggregates by short mesh name only -- never dumps full long paths, per the
# brief's compact-output requirement.

import json

R = {}
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

TARGET_GRAPH_SUBSTR = "PCG_3_3_1_Buildings"
TL = "/Game/Building/TL/"

R["current_level"] = str(les.get_current_level())

vol = None
vol_graph = None
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
        vol = a
        vol_graph = gpath
        break

if vol is None:
    R["fatal"] = "No PCGVolume carrying PCG_3_3_1_Buildings found in current level."
    print(json.dumps(R, indent=1, default=str))
    mcp_result = json.loads(json.dumps(R, default=str))
else:
    R["volume"] = {"actor": vol.get_actor_label(), "graph": vol_graph}

    def short_name(path):
        # Collapse a long asset path down to "<Folder>/.../<AssetName>" so
        # output stays compact (brief: "do not dump long mesh-path lists").
        parts = path.split("/")
        if len(parts) <= 3:
            return path
        return parts[-2] + "/" + parts[-1]

    by_style = {}   # style-code-ish bucket (TL, or "other") -> instance count
    tl_by_mesh = {}  # short mesh name -> instance count, TL only
    style_by_folder = {}  # top folder under /Game/Building/<CODE>/ -> count
    all_total = 0
    n_components = 0
    tl_total = 0

    for c in vol.get_components_by_class(unreal.PrimitiveComponent):
        try:
            n = c.get_instance_count()
        except Exception:
            continue
        if not n:
            continue
        n_components += 1
        all_total += n
        try:
            sm = c.get_editor_property("static_mesh")
            path = sm.get_path_name() if sm else "<none>"
        except Exception:
            path = "<err>"

        if TL in path:
            tl_total += n
            tl_by_mesh[short_name(path)] = tl_by_mesh.get(short_name(path), 0) + n

        # bucket every instance by its /Game/Building/<CODE>/ folder so we can
        # report TL's share against every OTHER style the stage drew from,
        # not just a TL-vs-everything-else binary.
        if "/Game/Building/" in path:
            tail = path.split("/Game/Building/", 1)[1]
            code = tail.split("/", 1)[0] if "/" in tail else tail
            style_by_folder[code] = style_by_folder.get(code, 0) + n

    R["components_with_instances"] = n_components
    R["all_instances"] = all_total
    R["tl_instances"] = tl_total
    R["tl_share_pct"] = round(100.0 * tl_total / all_total, 3) if all_total else None
    R["tl_meshes"] = tl_by_mesh
    R["tl_distinct_mesh_count"] = len(tl_by_mesh)
    R["instances_by_building_style_folder"] = dict(
        sorted(style_by_folder.items(), key=lambda kv: -kv[1]))
    R["distinct_style_folders"] = len(style_by_folder)
    R["only_tl_present"] = (len(style_by_folder) == 1 and "TL" in style_by_folder
                            and tl_total > 0)

    if tl_total:
        if R["only_tl_present"]:
            R["verdict"] = ("TL GENERATES BUT NARROWED THE CITY -- only TL "
                           "mesh folder present, no other style. FAILURE per "
                           "brief's pass condition.")
        else:
            R["verdict"] = "TL GENERATES, alongside other styles."
    else:
        R["verdict"] = "TL ABSENT -- check whitelist, DT rows, and minWallWidth"

    print(json.dumps(R, indent=1, default=str))
    mcp_result = json.loads(json.dumps(R, default=str))
