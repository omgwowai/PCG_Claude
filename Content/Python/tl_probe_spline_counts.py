# tl_probe_spline_counts.py -- READ-ONLY. Instances per mesh on TLPROBE_Spline.
import json
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
a = next(x for x in eas.get_all_level_actors() if x.get_actor_label() == "TLPROBE_Spline")
out = {}
for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
    sm = c.get_editor_property("static_mesh")
    if sm:
        out[sm.get_name()] = out.get(sm.get_name(), 0) + c.get_instance_count()
mcp_result = {"meshes": out, "total": sum(out.values())}
