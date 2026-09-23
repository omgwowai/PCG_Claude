# pcg_shots.py — final per-stage runner: bounded PCG debug, cine-camera framing,
# one stage per call, pipelined so the async generation always has a call to settle in.
#
#   args={"phase":"reset"}              reload the demo level (sheds bulk regeneration)
#   args={"phase":"run","stage":13}     generate stage 13, capture stage 12
#   args={"phase":"finish"}             generate stage 18, capture stage 18
#   args={"phase":"show_all"}           restore visibility of every stage
#
# WHY PIPELINED: generate_local() returns immediately (measured 0.0 s) and the work
# continues on worker threads, so a capture in the same call would photograph the
# old state. Doing "gen N" and "shot N-1" in one call means each stage's generation
# has a full call's worth of wall clock to finish, and the whole run costs ~20 calls
# instead of ~36.
#
# WHY DEBUG IS BOUNDED AT THE NODE, NOT JUST AT VISIBILITY: flagging every node of
# all 18 graphs produced 20,570,859 debug cubes and pushed the editor to 91.9 GB.
# Debug cubes are one ISM component per flagged node, so flagging DEBUG_NODES nodes
# per stage keeps both memory and the picture readable, while still being genuine
# PCG debug output for the nodes that produced the stage's data.
#
# WHY THE SHIPPED CINE CAMERAS: every computed camera produced sky-only frames
# because the geometry sits far from the origin (stage 3's vista is ~10M units out;
# the city spans x 0..170000, y 0..78000) while my derived poses landed at
# x ≈ -971730. The level ships 11 authored CineCameraActors, so this uses them.
#
# SCREENSHOT SIGNATURE (this cost a failed call): take_high_res_screenshot(res_x,
# res_y, filename, camera=None, mask_enabled=False, capture_hdr=False,
# comparison_tolerance=..., comparison_notes="", delay=0.0, force_game_view=True).
# Passing game_view positionally lands it on comparison_tolerance and raises
# "Failed to convert parameter 'comparison_tolerance'". Keywords only.
#
# SAFETY: no save call anywhere in this file.

import json
import math
import time

R = {"started": True}

try:
    try:
        args = mcp_args if isinstance(mcp_args, dict) else {}
    except NameError:
        args = {}

    PHASE = str(args.get("phase", "run"))
    STAGE = args.get("stage")
    DEBUG_NODES = int(args.get("debug_nodes", 4))
    # How many debug-cube components may be drawn. One component per flagged node,
    # so this is a small, bounded overlay rather than the 20.5M-instance blowup
    # that flagging every node of every graph produced.
    MAX_DBG_SHOWN = int(args.get("max_debug_shown", 3))
    R["phase"] = PHASE

    ORDER = [
        "PCG_1_1_Terrain", "PCG_1_2_BG_Buildings", "PCG_1_3_BG_Mountains",
        "PCG_2_1_MainTower_Footprint", "PCG_2_2_CentralPark_Footprint",
        "PCG_3_1_1_Districts", "PCG_3_1_2_Roads", "PCG_3_1_3_Highways",
        "PCG_3_1_4_Lots", "PCG_3_2_1_Ground", "PCG_3_2_2_LeftOverLots",
        "PCG_3_2_3_Parkings", "PCG_3_3_1_Buildings", "PCG_3_3_2_Rooftops",
        "PCG_4_1_MainTower_Visuals", "PCG_4_2_CentralPark_Visuals",
        "PCG_5_1_CityEdge", "PCG_5_2_OuterForest",
    ]
    # camera per stage, from the measured camera table
    CAM = {
        1: "City_WideView_1", 2: "City_WideView_1", 3: "City_WideView_1",
        4: "Building_Edit", 5: "CentralPark_1",
        6: "City_WideView_2", 7: "Street_1", 8: "HighWayEdit",
        9: "Street_2", 10: "Street_3", 11: "Street_2", 12: "Street_3",
        13: "Building_Edit", 14: "Building_Edit",
        15: "City_WideView_1", 16: "CentralPark_1",
        17: "City_WideView_2", 18: "City_WideView_1",
    }
    DBG = "/PCG/DebugObjects/"

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    def S(x):
        return str(x)

    def vols():
        out = []
        for a in eas.get_all_level_actors():
            try:
                if a.get_class().get_name() == "PCGVolume":
                    out.append(a)
            except Exception:
                continue
        return out

    def vol_by_label(label):
        for v in vols():
            try:
                if S(v.get_actor_label()) == label:
                    return v
            except Exception:
                continue
        return None

    def cam_by_name(frag):
        for a in eas.get_all_level_actors():
            try:
                if a.get_class().get_name() == "CineCameraActor" and frag in S(a.get_actor_label()):
                    return a
            except Exception:
                continue
        return None

    def comps(v):
        out = []
        for c in v.get_components_by_class(unreal.PrimitiveComponent):
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
                    m = S(sm.get_path_name())
            except Exception:
                pass
            out.append((c, n, m))
        return out

    def set_vis_all(visible):
        n = 0
        for v in vols():
            for c, _i, _m in comps(v):
                try:
                    c.set_visibility(visible, True)
                    n += 1
                except Exception:
                    pass
        return n

    if PHASE == "status":
        # Read-only. Reports whether the demo level is the one currently open,
        # so the batch never triggers a reload it does not need.
        cur = None
        try:
            cur = S(les.get_current_level())
        except Exception as ex:
            cur = "ERR " + S(ex)[:100]
        R["status"] = {"current_level": cur,
                       "on_demo_level": "L_CitySamplePCG_Demo" in cur,
                       "volumes": len(vols())}

    elif PHASE == "load":
        # ONE-TIME only. Reloading this level is what crashed the editor:
        # UEditorEngine::CheckForWorldGCLeaks() aborts on
        # "World Memory Leaks: 2 leaks objects and packages" because the old
        # world is still referenced when the new one loads. So the batch loads
        # once and never reloads; if the level is already open this is a no-op.
        already = False
        try:
            already = "L_CitySamplePCG_Demo" in S(les.get_current_level())
        except Exception:
            pass
        if already:
            R["load"] = {"skipped": "demo level already open", "volumes": len(vols())}
        else:
            t0 = time.time()
            ok = None
            try:
                ok = S(les.load_level("/CitySamplePCG/Levels/L_CitySamplePCG_Demo"))
            except Exception as ex:
                ok = "ERR " + S(ex)[:120]
            R["load"] = {"ok": ok, "sec": round(time.time() - t0, 1),
                         "volumes": len(vols())}

    elif PHASE == "show_all":
        R["shown"] = set_vis_all(True)

    elif PHASE == "shot":
        # Re-capture an ALREADY generated stage: isolation + cine camera + capture,
        # no generation. Needed because a capture renders on a LATER frame using
        # whatever visibility is current at that moment, so several captures fired
        # in one response collide and most never land. One stage per response is
        # the reliable cadence.
        si = int(STAGE)
        slabel = ORDER[si - 1]
        sv = vol_by_label(slabel)
        C = {"stage": si, "label": slabel}
        if sv is None:
            C["err"] = "no volume " + slabel
        else:
            hid = 0
            for v in vols():
                if v is sv:
                    continue
                for c, _i, _m in comps(v):
                    try:
                        c.set_visibility(False, True)
                        hid += 1
                    except Exception:
                        pass
            real_c = [(c, n, m) for c, n, m in comps(sv) if DBG not in m]
            dbg_c = [(c, n, m) for c, n, m in comps(sv) if DBG in m]
            for c, _n, _m in real_c:
                try:
                    c.set_visibility(True, True)
                except Exception:
                    pass
            dbg_c.sort(key=lambda e: -e[1])
            for i, (c, _n, _m) in enumerate(dbg_c):
                try:
                    c.set_visibility(i < MAX_DBG_SHOWN, True)
                except Exception:
                    pass
            C["hidden_other"] = hid
            C["real_components"] = len(real_c)
            C["debug_components"] = len(dbg_c)
            C["debug_shown"] = min(len(dbg_c), MAX_DBG_SHOWN)
            frag = CAM.get(si, "City_WideView_1")
            cam = cam_by_name(frag)
            if cam is not None:
                try:
                    les.set_level_viewport_camera_info(
                        cam.get_actor_location(), cam.get_actor_rotation(),
                        les.get_active_viewport_config_key())
                    C["cam"] = frag
                except Exception as ex:
                    C["cam_err"] = S(ex)[:100]
            else:
                C["cam_err"] = "no camera matching " + frag
            name = "pcg_stage_%02d_%s.png" % (si, slabel)
            try:
                t = unreal.AutomationLibrary.take_high_res_screenshot(
                    1600, 900, name, None, False, False, force_game_view=False)
                C["fired"] = name
                C["valid"] = S(t.is_valid_task()) if t else None
            except Exception as ex:
                C["shot_err"] = "%s: %s" % (type(ex).__name__, S(ex)[:180])
        R["recaptured"] = C

    elif PHASE in ("run", "finish"):
        # ---- 1. generate the requested stage with bounded debug ----
        if STAGE is None and PHASE == "finish":
            STAGE = 18
        gi = int(STAGE)
        glabel = ORDER[gi - 1]
        gv = vol_by_label(glabel)
        G = {}
        if gv is None:
            G["err"] = "no volume " + glabel
        else:
            pc = gv.pcg_component
            # first clear every node's debug flag on this graph, then flag a few
            cleared = flagged = 0
            try:
                g = pc.get_graph()
                if g:
                    nodes = g.get_editor_property("nodes")
                    for nd in nodes:
                        try:
                            st = nd.get_settings()
                            if st is not None and st.get_editor_property("debug"):
                                st.set_editor_property("debug", False)
                                cleared += 1
                        except Exception:
                            continue
                    for nd in nodes[:DEBUG_NODES]:
                        try:
                            st = nd.get_settings()
                            if st is not None:
                                st.set_editor_property("debug", True)
                                flagged += 1
                        except Exception:
                            continue
            except Exception as ex:
                G["graph_err"] = S(ex)[:120]
            G["cleared"] = cleared
            G["flagged"] = flagged
            try:
                pc.activate(True)
            except Exception:
                pass
            t0 = time.time()
            try:
                pc.generate_local(True)
                G["gen"] = "ok"
            except Exception as ex:
                G["gen"] = "ERR " + S(ex)[:140]
            G["sec"] = round(time.time() - t0, 2)
        R["generated"] = [gi, glabel, G]

        # ---- 2. capture the PREVIOUS stage (its generation has settled) ----
        si = gi - 1 if PHASE == "run" else gi
        if si >= 1:
            slabel = ORDER[si - 1]
            sv = vol_by_label(slabel)
            C = {"stage": si, "label": slabel}
            if sv is None:
                C["err"] = "no volume"
            else:
                # isolate: only the target's real geometry visible, debug hidden
                hid = 0
                for v in vols():
                    if v is sv:
                        continue
                    for c, _i, _m in comps(v):
                        try:
                            c.set_visibility(False, True)
                            hid += 1
                        except Exception:
                            pass
                # Real geometry always visible. PCG debug cubes are the thing
                # the user asked to see, so a BOUNDED number of them is shown
                # too: for stages with geometry they overlay the result, and for
                # the data-only stages (1 Terrain, 4/5 Footprints, 6 Districts,
                # which emit no instanced geometry) they are the only visible
                # trace of the stage at all.
                real_c = [(c, n, m) for c, n, m in comps(sv) if DBG not in m]
                dbg_c = [(c, n, m) for c, n, m in comps(sv) if DBG in m]
                for c, _n, _m in real_c:
                    try:
                        c.set_visibility(True, True)
                    except Exception:
                        pass
                dbg_c.sort(key=lambda e: -e[1])
                for i, (c, _n, _m) in enumerate(dbg_c):
                    try:
                        c.set_visibility(i < MAX_DBG_SHOWN, True)
                    except Exception:
                        pass
                C["real_components"] = len(real_c)
                C["debug_components"] = len(dbg_c)
                C["debug_shown"] = min(len(dbg_c), MAX_DBG_SHOWN)
                C["hidden_other"] = hid
                # camera
                frag = CAM.get(si, "City_WideView_1")
                cam = cam_by_name(frag)
                if cam is not None:
                    try:
                        les.set_level_viewport_camera_info(
                            cam.get_actor_location(), cam.get_actor_rotation(),
                            les.get_active_viewport_config_key())
                        C["cam"] = frag
                    except Exception as ex:
                        C["cam_err"] = S(ex)[:100]
                else:
                    C["cam_err"] = "no camera matching " + frag
                name = "pcg_stage_%02d_%s.png" % (si, slabel)
                try:
                    t = unreal.AutomationLibrary.take_high_res_screenshot(
                        1600, 900, name, None, False, False, force_game_view=False)
                    C["fired"] = name
                    C["valid"] = S(t.is_valid_task()) if t else None
                except Exception as ex:
                    C["shot_err"] = "%s: %s" % (type(ex).__name__, S(ex)[:180])
            R["captured"] = C

except Exception as fatal:
    R["top_level_exception"] = "%s: %s" % (type(fatal).__name__, str(fatal)[:300])

try:
    print(json.dumps(R, default=str))
except Exception as pe:
    print("print failed: %s" % pe)
try:
    mcp_result = json.loads(json.dumps(R, default=str))
except Exception as se:
    mcp_result = {"serialization_failed": str(se)[:200]}
