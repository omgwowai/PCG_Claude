# pcg_area_demo_recon.py — read-only recon for the small-area run (route B).
#
# Why this file exists: the first version of it crashed the editor. It kept
# UObject wrappers in Python globals (`pkg = w.get_outermost()`), and because the
# bridge runs scripts with exec(..., globals()) inside the persistent __main__
# module, a live wrapper in any global pins the old world. The next level load
# then aborts in UEditorEngine::CheckForWorldGCLeaks() with
#   FPyReferenceCollector::AddReferencedObjects(Package /Temp/Untitled_1)
# So: every UObject lives inside recon(), the only module-level names are plain
# data, and we purge and collect before switching levels.
#
# It reports what the similarity-transform step needs:
#   * every actor with a SplineComponent: class, tags, closed flag, world points
#   * the terrain actors (MeshPartition) and their bounds
#   * all 18 PCGVolumes: label, graph, position, actor scale, brush size
#   * the cine cameras and where they sit
#   * a couple of StaticMeshActors, which are not obvious spline carriers
#
# It never saves anything.

import gc
import json

TEMPLATE = "/CitySamplePCG/Levels/L_CitySamplePCG_Demo"


def vec(v):
    return [round(float(v.x), 3), round(float(v.y), 3), round(float(v.z), 3)]


def purge_uobject_globals():
    """Drop any unreal wrapper left in module globals so the old world can die."""
    import unreal
    dropped = []
    for name, val in list(globals().items()):
        if name.startswith("__") or name in ("gc", "json", "TEMPLATE", "unreal"):
            continue
        if isinstance(val, unreal.Object) or isinstance(val, unreal.StructBase):
            dropped.append(name)
            del globals()[name]
        elif isinstance(val, (list, tuple, dict)):
            del globals()[name]        # container: may hold wrappers we cannot see
            dropped.append(name)
    gc.collect()
    return dropped


def recon():
    import unreal

    out = {}
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    out["level_before"] = str(les.get_current_level())
    if TEMPLATE.split("/")[-1] not in out["level_before"]:
        out["loaded"] = bool(les.load_level(TEMPLATE))
    out["level_after"] = str(les.get_current_level())

    want = {"CityShape", "Artery_1", "Artery_2", "Artery_3", "Highway",
            "Highway_Width", "MainTowerPark", "LandmarkPark",
            "Terrain_shaping", "Terrain_shaping_1"}

    spline_actors = []
    terrain = []
    volumes = []
    cameras = []
    static_meshes = []
    class_hist = {}

    for a in eas.get_all_level_actors():
        cn = a.get_class().get_name()
        class_hist[cn] = class_hist.get(cn, 0) + 1
        label = str(a.get_actor_label())
        try:
            tags = [str(t) for t in a.get_editor_property("tags")]
        except Exception:
            tags = []

        comps = a.get_components_by_class(unreal.SplineComponent)
        if comps:
            entry = {"label": label, "class": cn, "tags": tags,
                     "tags_of_interest": [t for t in tags if t in want],
                     "loc": vec(a.get_actor_location()),
                     "scale": vec(a.get_actor_scale3d()),
                     "splines": []}
            for sc in comps:
                n = int(sc.get_number_of_spline_points())
                pts = [vec(sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD))
                       for i in range(min(n, 200))]
                types = [str(sc.get_spline_point_type(i)) for i in range(min(n, 200))]
                entry["splines"].append({
                    "num_points": n,
                    "closed": bool(sc.is_closed_loop()),
                    "point_types": sorted(set(types)),
                    "points": pts,
                })
            spline_actors.append(entry)

        if "MeshPartition" in cn or "MeshTerrain" in cn:
            try:
                origin, extent = a.get_actor_bounds(False)
                terrain.append({"label": label, "class": cn,
                                "origin": vec(origin), "extent": vec(extent)})
            except Exception as ex:
                terrain.append({"label": label, "class": cn, "bounds_err": str(ex)[:80]})

        if cn == "PCGVolume":
            e = {"label": label, "tags": tags,
                 "loc": vec(a.get_actor_location()),
                 "scale": vec(a.get_actor_scale3d())}
            try:
                bb = a.get_editor_property("brush_builder")
                e["brush"] = [float(bb.get_editor_property(k)) for k in ("x", "y", "z")]
                e["builder_class"] = bb.get_class().get_name()
            except Exception as ex:
                e["brush_err"] = str(ex)[:80]
            try:
                pc = a.pcg_component
                g = pc.get_graph()
                e["graph"] = str(g.get_name()) if g else None
                e["seed"] = int(pc.get_editor_property("seed"))
                e["generated"] = bool(pc.get_editor_property("generated"))
            except Exception as ex:
                e["pcg_err"] = str(ex)[:80]
            volumes.append(e)

        if cn == "CineCameraActor":
            r = a.get_actor_rotation()
            cameras.append({"label": label, "loc": vec(a.get_actor_location()),
                            "rot": [round(float(r.pitch), 2), round(float(r.yaw), 2),
                                    round(float(r.roll), 2)]})

        if cn == "StaticMeshActor":
            e = {"label": label, "tags": tags, "loc": vec(a.get_actor_location()),
                 "scale": vec(a.get_actor_scale3d())}
            try:
                smc = a.get_component_by_class(unreal.StaticMeshComponent)
                sm = smc.get_editor_property("static_mesh")
                e["mesh"] = str(sm.get_path_name()) if sm else None
            except Exception as ex:
                e["mesh_err"] = str(ex)[:60]
            static_meshes.append(e)

    out["class_histogram"] = dict(sorted(class_hist.items(), key=lambda kv: -kv[1]))
    out["spline_actors"] = spline_actors
    out["terrain_actors"] = terrain
    out["pcg_volumes"] = volumes
    out["cine_cameras"] = cameras
    out["static_mesh_actors"] = static_meshes
    return out


try:
    _dropped = purge_uobject_globals()
    RESULT = {"ok": True, "dropped_globals": _dropped, "data": recon()}
except Exception as exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(exc).__name__, str(exc)[:400])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as se:
    mcp_result = {"ok": False, "serialization_failed": str(se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:400000])
del RESULT
gc.collect()
