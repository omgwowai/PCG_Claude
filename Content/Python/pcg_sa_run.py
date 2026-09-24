# Content/Python/pcg_sa_run.py
# Stage runner for the small-area 18-stage run.
#
# args: {"phase": "cleanup_all" | "gen" | "apply_camera" | "probe",
#        "stage": 1..18,
#        "target_cm": 60000,        # for the computed camera
#        "debug_nodes": 4,          # how many nodes to flag per stage
#        "camera_mode": "computed"} # "computed" | "cine"
#
# ONE PHASE PER CALL. Generation is asynchronous and generate_local returns
# immediately, so a read in the same call is always empty and never errors.
# The capture phases live in pcg_sa_shots.py; the split keeps each script small
# enough to hold in context, which is where these scripts have historically gone
# wrong.
#
# DEBUG FLAGGING: there is no global PCG debug switch (every pcg.* cvar reads
# empty/0 and PCGComponent has no debug member); it is the per-node `debug` bool on
# PCGSettings. Flagging all nodes of all 18 graphs produced 20,570,859 debug cubes
# and killed the editor at 92 GB, so this flags at most `debug_nodes` per stage.
#
# FINDING THE NODES THAT PRODUCE A STAGE'S DATA: walk the output node's incoming
# edges. `predecessors()` derives the partner as `b if a == node else a`, which is
# deliberately independent of which of get_output_node/get_input_node returns which
# node — traps.md #23 records that those two are named against intuition (for the
# edge Spawner.Out -> Output.In, get_output_node() returns the Output node).
#
# THE COMPUTED CAMERA: the 09-23 run had to use the level's own cine cameras because
# every bounds-derived pose flew to ~-971730 and photographed sky, since that city's
# stage 3 vista sits ~10M units out. Here the subject is 600 m of our own geometry at
# a known centre, so an orbit around the measured city bbox is both safe and exactly
# framed. camera_mode="cine" remains available as a fallback.
#
# GLOBAL DISCIPLINE: no UObject survives this script — module level holds only
# constants and functions, and every component reference lives inside a phase.

import gc
import json
import time

TARGET = "/Game/PCGArea/L_SmallArea18"
DEBUG_CUBE = "/PCG/DebugObjects/"
ORDER = [
    "PCG_1_1_Terrain", "PCG_1_2_BG_Buildings", "PCG_1_3_BG_Mountains",
    "PCG_2_1_MainTower_Footprint", "PCG_2_2_CentralPark_Footprint",
    "PCG_3_1_1_Districts", "PCG_3_1_2_Roads", "PCG_3_1_3_Highways",
    "PCG_3_1_4_Lots", "PCG_3_2_1_Ground", "PCG_3_2_2_LeftOverLots",
    "PCG_3_2_3_Parkings", "PCG_3_3_1_Buildings", "PCG_3_3_2_Rooftops",
    "PCG_4_1_MainTower_Visuals", "PCG_4_2_CentralPark_Visuals",
    "PCG_5_1_CityEdge", "PCG_5_2_OuterForest",
]
# Which cine camera suits which stage, when camera_mode="cine".
CINE = {1: "City_WideView_1", 2: "City_WideView_1", 3: "City_WideView_1",
        4: "Building_Edit", 5: "CentralPark_1", 6: "City_WideView_2",
        7: "Street_1", 8: "HighWayEdit", 9: "Street_2", 10: "Street_3",
        11: "Street_2", 12: "Street_3", 13: "Building_Edit",
        14: "Building_Edit", 15: "City_WideView_1", 16: "CentralPark_1",
        17: "City_WideView_2", 18: "City_WideView_1"}
# The computed orbit per stage: (bearing deg, elevation deg, distance multiple).
# Wide stages look from the same bearing as Epic's City_WideView_1 (roughly +X,
# looking back toward -X); ground-level stages come down low from the south.
ORBIT = {1: (0, 32, 2.6), 2: (0, 20, 2.8), 3: (20, 12, 6.0), 4: (90, 30, 1.6),
         5: (135, 28, 1.8), 6: (0, 38, 2.4), 7: (-60, 22, 2.0), 8: (60, 18, 2.6),
         9: (170, 30, 2.0), 10: (-100, 12, 2.0), 11: (150, 18, 2.0),
         12: (150, 14, 1.8), 13: (30, 20, 2.2), 14: (30, 45, 2.2),
         15: (90, 30, 1.8), 16: (135, 24, 2.2), 17: (-30, 16, 2.2),
         18: (0, 24, 4.0)}

# Stages whose graphs emit data rather than instanced geometry: a zero instance
# count is correct for these, not a failure.
DATA_ONLY = (1, 4, 5, 6)


def vol_by_label(eas, label):
    for a in eas.get_all_level_actors():
        try:
            if a.get_class().get_name() == "PCGVolume" and str(a.get_actor_label()) == label:
                return a
        except Exception:
            continue
    return None


def comps(volume):
    """(component, instance_count, mesh_path) for every comp with instances."""
    import unreal
    out = []
    for c in volume.get_components_by_class(unreal.PrimitiveComponent):
        if c.get_class().get_name() == "BrushComponent":
            continue
        try:
            n = c.get_instance_count()
        except Exception:
            continue
        if not n:
            continue
        m = ""
        try:
            sm = c.get_editor_property("static_mesh")
            if sm:
                m = str(sm.get_path_name())
        except Exception:
            pass
        out.append((c, n, m))
    return out


def counted(volume):
    """(real_instances, debug_instances, real_components, debug_components)."""
    real_n = dbg_n = real_c = dbg_c = 0
    for c, n, m in comps(volume):
        if m.startswith(DEBUG_CUBE):
            dbg_n += n
            dbg_c += 1
        else:
            real_n += n
            real_c += 1
    return real_n, dbg_n, real_c, dbg_c


def all_volumes(eas):
    return [a for a in eas.get_all_level_actors()
            if a.get_class().get_name() == "PCGVolume"]


def city_bbox(eas, ue):
    """Union bbox of the splines tagged City, for framing the computed camera."""
    pts = []
    for a in eas.get_all_level_actors():
        try:
            tags = [str(t) for t in a.get_editor_property("tags")]
        except Exception:
            tags = []
        if "City" not in tags:
            continue
        for sc in a.get_components_by_class(ue.SplineComponent):
            n = int(sc.get_number_of_spline_points())
            for i in range(n):
                p = sc.get_location_at_spline_point(i, ue.SplineCoordinateSpace.WORLD)
                pts.append([p.x, p.y, p.z])
    return pts


def phase_cleanup_all(eas):
    n = 0
    for v in all_volumes(eas):
        try:
            v.pcg_component.cleanup_local(True)
            n += 1
        except Exception:
            pass
    return {"cleaned": n}


def phase_gen(eas, stage, debug_nodes):
    import unreal
    label = ORDER[stage - 1]
    vol = vol_by_label(eas, label)
    if vol is None:
        return {"err": "no volume labelled %s" % label}
    pc = vol.pcg_component
    g = pc.get_graph()
    info = {"stage": stage, "graph": label, "cleared_flags": 0, "flagged": 0,
            "flagged_nodes": [], "activated": False, "fired": False}
    if g is None:
        info["err"] = "volume %s has no graph" % label
        return info

    # 1. clear every node's flag on this graph
    nodes = g.get_editor_property("nodes")
    for nd in nodes:
        try:
            st = nd.get_settings()
            if st is not None and st.get_editor_property("debug"):
                st.set_editor_property("debug", False)
                info["cleared_flags"] += 1
        except Exception:
            continue

    # 2. flag the nodes that actually produce this stage's data: walk the output
    #    node's incoming edges and take its direct predecessors, then go one hop
    #    further back if there are not enough of them.
    chosen = []

    def predecessors(node):
        found = []
        for pin in node.get_editor_property("input_pins"):
            for e in pin.edges:
                try:
                    a = e.get_output_node()
                    b = e.get_input_node()
                except Exception:
                    continue
                other = b if a == node else a
                if other is not None and other != node and other not in found:
                    found.append(other)
        return found

    try:
        out_node = g.get_output_node()
    except Exception:
        out_node = None
    if out_node is not None:
        first = predecessors(out_node)
        chosen.extend(first)
        if len(chosen) < debug_nodes:
            for nd in list(first):
                for extra in predecessors(nd):
                    if extra not in chosen:
                        chosen.append(extra)
                    if len(chosen) >= debug_nodes:
                        break
                if len(chosen) >= debug_nodes:
                    break
    if not chosen:                     # fall back to the first few nodes
        chosen = list(nodes[:debug_nodes])
    for nd in chosen[:debug_nodes]:
        try:
            st = nd.get_settings()
            if st is None:
                continue
            st.set_editor_property("debug", True)
            info["flagged"] += 1
            try:
                info["flagged_nodes"].append(str(st.get_class().get_name()))
            except Exception:
                info["flagged_nodes"].append("?")
        except Exception:
            continue

    # 3. activate then generate. A freshly spawned/copied component needs the
    #    explicit activate() or ShouldGenerate() is false and nothing happens,
    #    silently and without error.
    try:
        pc.activate(True)
        info["activated"] = bool(pc.get_editor_property("activated"))
    except Exception as ex:
        info["activate_err"] = str(ex)[:120]
    t0 = time.time()
    try:
        pc.generate_local(True)
        info["fired"] = True
    except Exception as ex:
        info["gen_err"] = str(ex)[:160]
    info["sec"] = round(time.time() - t0, 2)
    return info


def phase_apply_camera(eas, les, stage, camera_mode, target_cm):
    import unreal
    import sys
    cdir = unreal.Paths.project_content_dir() + "Python"
    if cdir not in sys.path:
        sys.path.insert(0, cdir)
    import pcg_sa_geom as G

    if camera_mode == "cine":
        frag = CINE.get(stage, "City_WideView_1")
        for a in eas.get_all_level_actors():
            try:
                if (a.get_class().get_name() == "CineCameraActor"
                        and frag in str(a.get_actor_label())):
                    loc = a.get_actor_location()
                    les.set_level_viewport_camera_info(
                        loc, a.get_actor_rotation(),
                        les.get_active_viewport_config_key())
                    return {"stage": stage, "camera": frag, "mode": "cine",
                            "loc": [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1)]}
            except Exception:
                continue
        return {"stage": stage, "camera": frag, "mode": "cine", "err": "not found"}

    pts = city_bbox(eas, unreal)
    if not pts:
        return {"stage": stage, "mode": "computed", "err": "no City spline"}
    mn, mx = G.bbox_of_points(pts)
    center = [(mn[i] + mx[i]) / 2.0 for i in range(3)]
    radius = 0.5 * max(mx[0] - mn[0], mx[1] - mn[1])
    az, elev, mult = ORBIT.get(stage, (0, 30, 2.4))
    loc, rot = G.orbit_camera(center, radius, az, elev, mult, min_height=radius * 0.6)
    les.set_level_viewport_camera_info(
        unreal.Vector(loc[0], loc[1], loc[2]),
        unreal.Rotator(rot[0], rot[1], rot[2]),
        les.get_active_viewport_config_key())
    return {"stage": stage, "mode": "computed", "center": [round(v, 1) for v in center],
            "radius": round(radius, 1), "loc": [round(v, 1) for v in loc],
            "rot": [round(v, 2) for v in rot]}


def phase_probe(eas, stage):
    label = ORDER[stage - 1]
    vol = vol_by_label(eas, label)
    if vol is None:
        return {"err": "no volume labelled %s" % label}
    real_n, dbg_n, real_c, dbg_c = counted(vol)
    gen = None
    try:
        gen = bool(vol.pcg_component.get_editor_property("generated"))
    except Exception:
        pass
    return {"stage": stage, "graph": label, "generated": gen,
            "real_instances": real_n, "debug_instances": dbg_n,
            "real_components": real_c, "debug_components": dbg_c,
            "suspect_zero": bool(real_n == 0 and stage not in DATA_ONLY)}


def run(phase, stage, debug_nodes, camera_mode, target_cm):
    import unreal
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    cur = str(les.get_current_level())
    if TARGET.split("/")[-1] not in cur:
        return {"abort": "not on %s (current: %s)" % (TARGET, cur)}
    if phase == "cleanup_all":
        return phase_cleanup_all(eas)
    if stage is None:
        return {"abort": "phase %s needs a stage" % phase}
    s = int(stage)
    if not 1 <= s <= 18:
        return {"abort": "stage out of range: %s" % stage}
    if phase == "gen":
        return phase_gen(eas, s, debug_nodes)
    if phase == "apply_camera":
        return phase_apply_camera(eas, les, s, camera_mode, target_cm)
    if phase == "probe":
        return phase_probe(eas, s)
    return {"abort": "unknown phase %s" % phase}


try:
    _args = mcp_args if isinstance(mcp_args, dict) else {}
except NameError:
    _args = {}

try:
    RESULT = {"ok": True, "data": run(str(_args.get("phase", "probe")),
                                     _args.get("stage", None),
                                     int(_args.get("debug_nodes", 4)),
                                     str(_args.get("camera_mode", "computed")),
                                     float(_args.get("target_cm", 60000.0)))}
except Exception as _exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(_exc).__name__, str(_exc)[:400])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as _se:
    mcp_result = {"ok": False, "serialization_failed": str(_se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:200000])
del RESULT, _args
gc.collect()
