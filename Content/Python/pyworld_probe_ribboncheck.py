# pyworld_probe_ribboncheck.py -- READ-ONLY: the river ribbon probe actor's mesh bounds, triangle count, material and
# whether that material compiled (its base material's shading model / any compile error the log shows is checked
# separately).
import json

import unreal

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
out = []
for a in eas.get_all_level_actors():
    if str(a.get_actor_label()).startswith("PyWorldProbe_"):
        c = a.get_editor_property("dynamic_mesh_component") if isinstance(a, unreal.DynamicMeshActor) else None
        row = {"label": str(a.get_actor_label()), "hidden": bool(a.is_hidden_ed())}
        if c:
            o, e = a.get_actor_bounds(False)
            row.update(tris=c.get_dynamic_mesh().get_triangle_count(), origin=[round(o.x), round(o.y), round(o.z)],
                       extent=[round(e.x), round(e.y), round(e.z)], mats=[m.get_path_name() if m else None for m in c.get_materials()],
                       visible=bool(c.is_visible()))
        out.append(row)
print(json.dumps(out, indent=1))
