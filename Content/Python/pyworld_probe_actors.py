import gc
import json

import unreal

# pyworld_probe_actors.py -- READ ONLY. Every actor of the current level with its class, label, tags, component
# classes and bounds, grouped, so the PyWorld layout knows which template actors are terrain and which are city
# controls.


def run():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    groups = {}
    for a in eas.get_all_level_actors():
        cls = a.get_class().get_name()
        comps = sorted({c.get_class().get_name() for c in a.get_components_by_class(unreal.ActorComponent)})
        tags = [str(t) for t in a.get_editor_property("tags")]
        key = "%s | %s" % (cls, ",".join(comps))
        g = groups.setdefault(key, {"n": 0, "examples": []})
        g["n"] += 1
        if len(g["examples"]) < 6:
            o, e = a.get_actor_bounds(False)
            g["examples"].append({"label": str(a.get_actor_label()), "tags": tags, "folder": str(a.get_folder_path()),
                                  "loc": [round(v) for v in (o.x, o.y, o.z)], "ext": [round(v) for v in (e.x, e.y, e.z)]})
    tagged = {}
    for a in eas.get_all_level_actors():
        for t in a.get_editor_property("tags"):
            tagged.setdefault(str(t), []).append(str(a.get_actor_label()))
    return {"groups": groups, "tags": {k: v[:8] + (["... %d" % len(v)] if len(v) > 8 else []) for k, v in tagged.items()}}


mcp_result = json.loads(json.dumps(run(), default=str))
gc.collect()
