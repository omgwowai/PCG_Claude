import gc
import json

import unreal

# pyworld_probe_instances.py -- READ ONLY. For one PyWorld volume: each ISM component's mesh, instance count, its
# material, and the first instance's world transform plus the trace height under it.


def run(args):
    from pypcg import world as W
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next(a for a in eas.get_all_level_actors() if W.volume_tag(int(args.get("stage", 4))) in [str(t) for t in a.tags])
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    out = []
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        n = c.get_instance_count()
        rec = {"mesh": sm.get_path_name() if sm else None, "n": n, "visible": c.is_visible(),
               "materials": [m.get_path_name() if m else None for m in c.get_materials()][:3]}
        if n:
            t = c.get_instance_transform(min(int(args.get("i", 0)), n - 1), True)
            r = t.rotation.rotator()
            rec["first"] = {"loc": [t.translation.x, t.translation.y, t.translation.z], "rot": [r.pitch, r.yaw, r.roll],
                            "scale": [t.scale3d.x, t.scale3d.y, t.scale3d.z]}
            res = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(t.translation.x, t.translation.y, 500000.0),
                                                         unreal.Vector(t.translation.x, t.translation.y, -500000.0),
                                                         unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
                                                         unreal.DrawDebugTrace.NONE, True)
            hit = res[-1] if isinstance(res, tuple) else res
            parts = hit.to_tuple() if hit is not None else None
            rec["trace_z"] = float(parts[4].z) if parts and parts[0] else None
        out.append(rec)
    return out


mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
gc.collect()
