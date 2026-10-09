# tl_probe_showcase_props.py -- READ-ONLY. World positions and yaw of the
# showcase building's awnings, signs and corner pieces, to aim close-up shots.
import json

LABEL = "TL_Showcase_Building"
WANT = ("Awning", "Sign_E01", "Sign_B01", "L01_A_Entrance", "L01_A_CornerEx", "AC_Window")


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next(a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL)
    out = {}
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None:
            continue
        n = sm.get_name()
        key = next((k for k in WANT if k in n), None)
        if key is None:
            continue
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            out.setdefault(key, []).append([round(v) for v in t.translation.to_tuple()] + [round(t.rotation.rotator().yaw)])
    return {k: v[:8] for k, v in out.items()} | {"counts": {k: len(v) for k, v in out.items()}}


mcp_result = json.loads(json.dumps(main(), default=str))
