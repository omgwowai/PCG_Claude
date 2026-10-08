# tl_building_bounds.py -- READ-ONLY. World bounds of the TL building in
# Lvl_TL_Building, from per-instance transforms plus mesh bounds.
import json


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    lo = [1e18] * 3
    hi = [-1e18] * 3
    for a in eas.get_all_level_actors():
        if a.get_actor_label() != "TL_Building_Volume":
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            for i in range(c.get_instance_count()):
                p = c.get_instance_transform(i, True).translation
                for k, v in enumerate((p.x, p.y, p.z)):
                    lo[k] = min(lo[k], v)
                    hi[k] = max(hi[k], v)
    return {"min": lo, "max": hi, "centre": [(lo[k] + hi[k]) / 2 for k in range(3)]}


mcp_result = json.loads(json.dumps(main(), default=str))
