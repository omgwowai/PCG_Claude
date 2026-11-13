# Read-only probe: trace rays from the CS_SkyCam camera through given normalized screen points (u, v in [0,1],
# v down) and report the hit actor / component / materials (blend mode, shading model, two-sided).
# args: {"points": [[u, v], ...], "camera": "CS_SkyCam", "hfov": 60, "aspect": 0.6383}
import math

import unreal


def _find(label):
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    return None


def _mat_info(m):
    if m is None:
        return None
    base = m.get_base_material()
    info = {"path": m.get_path_name()}
    if base:
        info["base"] = base.get_path_name()
        for p in ("blend_mode", "shading_model", "two_sided", "translucency_lighting_mode", "material_domain"):
            try:
                info[p] = str(base.get_editor_property(p))
            except Exception:
                pass
    return info


def _main(args):
    cam = _find(args.get("camera", "CS_SkyCam"))
    loc = cam.get_actor_location()
    rot = cam.get_actor_rotation()
    fwd, right, up = rot.get_forward_vector(), rot.get_right_vector(), rot.get_up_vector()
    th = math.tan(math.radians(float(args.get("hfov", 60.0))) * 0.5)
    tv = th / float(args.get("aspect", 0.6383))
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    out = []
    for u, v in args["points"]:
        d = fwd + right * ((2 * u - 1) * th) + up * ((1 - 2 * v) * tv)
        d = d.normal()
        end = loc + d * 5.0e6
        hit = unreal.SystemLibrary.line_trace_single(world, loc, end, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, True, [],
                                                      unreal.DrawDebugTrace.NONE, True)
        rec = {"uv": [u, v], "dir": [d.x, d.y, d.z]}
        if hit:
            t = hit.to_tuple()
            # HitResult tuple: (blocking, initial_overlap, time, distance, location, impact_point, normal,
            #                   impact_normal, phys_mat, hit_actor, hit_component, hit_bone_name, bone_name, hit_item, element_index, face_index, trace_start, trace_end)
            names = [f for f in dir(hit) if not f.startswith("_")]
            rec["fields"] = names[:0]
            rec["distance_m"] = round(t[3] / 100.0, 1)
            p = t[4]
            rec["location"] = [round(p.x), round(p.y), round(p.z)]
            actor, comp = t[9], t[10]
            rec["actor"] = actor.get_actor_label() if actor else None
            rec["actor_class"] = actor.get_class().get_name() if actor else None
            rec["component"] = comp.get_name() if comp else None
            rec["component_class"] = comp.get_class().get_name() if comp else None
            if comp and isinstance(comp, unreal.MeshComponent):
                rec["materials"] = [_mat_info(m) for m in comp.get_materials()][:3]
                if isinstance(comp, unreal.StaticMeshComponent) and comp.get_editor_property("static_mesh"):
                    sm = comp.get_editor_property("static_mesh")
                    rec["mesh"] = sm.get_path_name()
                    try:
                        rec["mesh_tris_lod0"] = sm.get_num_triangles(0)
                    except Exception:
                        pass
                    b = sm.get_bounding_box()
                    rec["mesh_bounds_cm"] = [round(b.max.x - b.min.x), round(b.max.y - b.min.y), round(b.max.z - b.min.z)]
                    s = comp.get_world_scale()
                    rec["scale"] = [s.x, s.y, s.z]
        else:
            rec["hit"] = False
        out.append(rec)
    return out


mcp_result = _main(globals().get("mcp_args") or {})
