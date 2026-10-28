import gc
import json

import unreal

# pyworld_probe_state.py -- READ ONLY. What the editor has open, whether it is safe to switch levels, and what
# the mesh-terrain template levels and mesh-partition definitions offer (for the PyWorld design).


def _props(obj, limit=60):
    out = {}
    for name in dir(obj):
        if name.startswith("_") or len(out) >= limit:
            continue
        try:
            v = obj.get_editor_property(name)
        except Exception:
            continue
        s = str(v)
        out[name] = s[:200]
    return out


def run():
    from pypcg import level
    out = {"current_map": level.current_map()}
    out["dirty_maps"] = [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    out["dirty_content"] = [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()][:20]
    eal = unreal.EditorAssetLibrary
    maps = ["/PCGPrimitives_MeshPartitionInterop/Levels/L_MeshTerrain_Default",
            "/PCGPrimitives_MeshPartitionInterop/Levels/L_MeshTerrain_Basic",
            "/Game/PyPCG/L_PyCitySmall", "/Game/PyPCG/L_PyWorld"]
    out["maps"] = {m: bool(eal.does_asset_exist(m)) for m in maps}
    mpds = {}
    for p in ["/PCGPrimitives_MeshPartitionInterop/Assets/MeshPartitionDefinitions/MPD_Basic",
              "/PCGPrimitives_MeshPartitionInterop/Assets/MeshPartitionDefinitions/MPD_Default"]:
        a = eal.load_asset(p)
        mpds[p] = {"class": a.get_class().get_name() if a else None, "props": _props(a) if a else None}
    out["mpd"] = mpds
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    actors = eas.get_all_level_actors()
    out["actor_count"] = len(actors)
    classes = {}
    for a in actors:
        c = a.get_class().get_name()
        classes[c] = classes.get(c, 0) + 1
    out["actor_classes"] = dict(sorted(classes.items(), key=lambda kv: -kv[1])[:25])
    terr = []
    for a in actors:
        c = a.get_class().get_name()
        if "Mesh" in c and ("Partition" in c or "Terrain" in c):
            o, e = a.get_actor_bounds(False)
            terr.append({"label": str(a.get_actor_label()), "class": c, "origin": [o.x, o.y, o.z], "extent": [e.x, e.y, e.z]})
    out["terrain_actors"] = terr[:10]
    return out


mcp_result = json.loads(json.dumps(run(), default=str))
gc.collect()
