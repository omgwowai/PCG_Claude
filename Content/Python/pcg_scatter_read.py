# pcg_scatter_read.py — canonical TWO-PHASE example, stage B: read + verify + clean.
#
# Run this ONLY as a separate MCP call after pcg_scatter_cube.py.
# In the same call it would read an empty collection (generation is async).
#
# It demonstrates the whole verification recipe the skill teaches:
#   * relocate the volume by CLASS (Python variables do NOT survive across calls)
#   * unwrap PCGDataCollection -> tagged_data -> FPCGDataPtrWrapper -> data
#   * read a real point count numerically
#   * count spawned instance components as a second independent check
#
# Pass args={"keep": true} to skip the cleanup step.

import json

R = {}
args = mcp_args or {}
KEEP = bool(args.get("keep", False))
GRAPH = "/Game/PCGTest/PCG_ScatterCube"

EAL = unreal.EditorAssetLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

# ---------- 1. relocate the volume by class ------------------------------
target = None
for a in eas.get_all_level_actors():
    try:
        if a.get_class().get_name() == "PCGVolume":
            target = a
    except Exception:
        continue
if target is None:
    R["fatal"] = "no PCGVolume found — run pcg_scatter_cube.py first"
    print(json.dumps(R, indent=1, default=str))
    mcp_result = R
    raise SystemExit

comp = target.get_component_by_class(unreal.PCGComponent)
R["actor"] = target.get_actor_label()
R["graph"] = str(comp.get_graph())

# ---------- 2. read the generated data numerically -----------------------
read = {}
try:
    coll = comp.get_generated_graph_output()
    items = coll.get_editor_property("tagged_data")
    read["tagged_count"] = len(items)
    detail = []
    for it in items:
        d = {"pin": str(it.get_editor_property("pin"))}
        wrap = it.get_editor_property("data")
        d["wrapper"] = type(wrap).__name__
        # the unwrap that actually works: a struct field named "data"
        data = wrap.get_editor_property("data")
        d["data_class"] = data.get_class().get_name() if data else None
        if data:
            d["num_points"] = data.get_num_points()
            d["is_empty"] = data.is_empty()
        detail.append(d)
    read["items"] = detail
    read["total_points"] = sum(d.get("num_points") or 0 for d in detail)
except Exception as e:
    read["fatal"] = "%s: %s" % (type(e).__name__, e)
R["output"] = read

# ---------- 3. independent check: what got spawned? ----------------------
spawn = {}
try:
    prims = target.get_components_by_class(unreal.PrimitiveComponent)
    names = []
    for c in prims:
        try:
            names.append("%s(%s)" % (c.get_name(), c.get_class().get_name()))
        except Exception:
            pass
    spawn["primitive_components"] = names
except Exception as e:
    spawn["primitive_components_err"] = type(e).__name__
R["spawned"] = spawn

# ---------- 4. cleanup (unless args.keep) --------------------------------
cl = {}
if not KEEP:
    try:
        comp.cleanup_local(True)
        cl["cleanup_local"] = "OK"
    except Exception as e:
        cl["cleanup_local"] = type(e).__name__
    try:
        eas.destroy_actor(target)
        cl["actor_destroyed"] = True
    except Exception as e:
        cl["actor_destroyed"] = type(e).__name__
    try:
        cl["graph_deleted"] = EAL.delete_asset(GRAPH)
        cl["graph_gone"] = not EAL.does_asset_exist(GRAPH)
    except Exception as e:
        cl["graph_deleted"] = "%s: %s" % (type(e).__name__, e)
else:
    cl["skipped"] = "args.keep is true"
R["cleanup"] = cl

print(json.dumps(R, indent=1, default=str))
mcp_result = R
