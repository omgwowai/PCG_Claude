# pcg_stage_run.py — run the 18-stage City Sample PCG pipeline with PCG debug on
# and capture one screenshot per stage.
#
#   args={"phase":"gen","stages":[1,2,...]}   set node debug, activate, generate
#   args={"phase":"poll"}                     per-stage instance census (is it settled?)
#   args={"phase":"shot","stage":N}           isolate, frame, capture
#   args={"phase":"show_all"}                 restore visibility of all stages
#   args={"phase":"debug_off"}                restore every graph's node debug flags
#
# COMPACT OUTPUT: each call returns a short summary. The run is ~25 calls and the
# full census is ~4 KB per stage, which would exhaust context.
#
# FRAMING USES PERCENTILES, not min/max. Measured problems with every other source:
#   * Actor.get_actor_bounds()  -> ~±24,000,000 (useless)
#   * get_actor_bounds_pcg()    -> ~±2500 (the brush only, ignores output)
#   * min/max over instance translations -> ~±9,000,000 (outliers dominate)
# Per-axis 2nd/98th percentile over sampled instance translations rejects those
# outliers. Stages with no ISM output of their own (1 Terrain, 4/5 Footprints,
# 6 Districts) instead frame the union of all stages' geometry, since their result
# is data or a terrain deformation rather than instanced meshes.
#
# PCG DEBUG (proven on stage 3, not assumed): the per-node `debug` bool on
# PCGSettings is the switch — there is no global cvar (every pcg.* reads empty/0).
# With it set and the graph regenerated, stage 3 went from 1 ISM component / 59
# instances to 7 components / 419 instances, each an ISM of
# /PCG/DebugObjects/PCG_Cube. Engine source agrees: IPCGElement::DebugDisplay()
# early-outs unless SettingsInterface->bDebug.
#
# SAFETY: this file contains no save call of any kind, by design. Verified by
# grep. Epic's shipped content keeps its original mtimes; regenerated geometry
# lives only in memory and a level reload discards it. Engine autosaves go to
# Saved/Autosaves/ as *_AutoN.uasset shadow copies and never overwrite Content/.

import json
import math
import time

R = {"started": True}

try:
    try:
        args = mcp_args if isinstance(mcp_args, dict) else {}
    except NameError:
        args = {}

    PHASE = str(args.get("phase", "poll"))
    STAGE = args.get("stage")
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

    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    DBG = "/PCG/DebugObjects/"

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

    def find_volume(label):
        for a in vols():
            try:
                if S(a.get_actor_label()) == label:
                    return a
            except Exception:
                continue
        return None

    def classify(vol):
        real, dbg = [], []
        for c in vol.get_components_by_class(unreal.PrimitiveComponent):
            try:
                n = c.get_instance_count()
            except Exception:
                continue
            if not n:
                continue
            mesh = ""
            try:
                sm = c.get_editor_property("static_mesh")
                if sm:
                    mesh = S(sm.get_path_name())
            except Exception:
                pass
            (dbg if DBG in mesh else real).append((c, n, mesh))
        return real, dbg

    def sample_points(items, budget=4000):
        xs, ys, zs = [], [], []
        for c, n, _m in items:
            if len(xs) >= budget:
                break
            step = 1 if n <= 400 else max(1, n // 400)
            i = 0
            while i < n and len(xs) < budget:
                try:
                    o = c.get_instance_transform(i).translation
                except Exception:
                    i += step
                    continue
                xs.append(o.x); ys.append(o.y); zs.append(o.z)
                i += step
        return xs, ys, zs

    def pct_bounds(items, lo_p=2.0, hi_p=98.0):
        xs, ys, zs = sample_points(items)
        if len(xs) < 8:
            return None, None, len(xs)
        def rng(v):
            v = sorted(v)
            k = len(v)
            a = v[max(0, int(k * lo_p / 100.0))]
            b = v[min(k - 1, int(k * hi_p / 100.0))]
            return a, b
        ax, bx = rng(xs); ay, by = rng(ys); az, bz = rng(zs)
        return [ax, ay, az], [bx, by, bz], len(xs)

    def set_vis(vol, visible):
        n = 0
        for c in vol.get_components_by_class(unreal.PrimitiveComponent):
            if c.get_class().get_name() == "BrushComponent":
                continue
            try:
                c.set_visibility(visible, True)
                n += 1
            except Exception:
                continue
        return n

    def frame_camera(lo, hi):
        cx, cy, cz = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
        ex = max(hi[0] - lo[0], 500.0)
        ey = max(hi[1] - lo[1], 500.0)
        ez = max(hi[2] - lo[2], 500.0)
        diag = math.sqrt(ex * ex + ey * ey + ez * ez)
        d = diag * 1.0
        k = 1.0 / math.sqrt(3.0)
        loc = unreal.Vector(cx - d * k, cy - d * k, cz + d * k)
        dx, dy, dz = cx - loc.x, cy - loc.y, cz - loc.z
        horiz = math.sqrt(dx * dx + dy * dy)
        rot = unreal.Rotator(math.degrees(math.atan2(-dz, horiz)),
                             math.degrees(math.atan2(dy, dx)), 0.0)
        les.set_level_viewport_camera_info(loc, rot, les.get_active_viewport_config_key())
        return {"center": [round(c) for c in (cx, cy, cz)],
                "size": [round(v) for v in (ex, ey, ez)]}

    # ---------------- phases ----------------
    if PHASE == "gen":
        wanted = args.get("stages") or list(range(1, 19))
        out = []
        for si in wanted:
            idx = int(si) - 1
            if not (0 <= idx < len(ORDER)):
                continue
            label = ORDER[idx]
            v = find_volume(label)
            if v is None:
                out.append([si, label, "MISSING"])
                continue
            pc = v.pcg_component
            dset = dalready = 0
            try:
                g = pc.get_graph()
                if g:
                    for nd in g.get_editor_property("nodes"):
                        try:
                            st = nd.get_settings()
                            if st is None:
                                continue
                            if st.get_editor_property("debug"):
                                dalready += 1
                            else:
                                st.set_editor_property("debug", True)
                                dset += 1
                        except Exception:
                            continue
            except Exception as ex:
                out.append([si, label, "graph_err " + S(ex)[:60]])
                continue
            try:
                pc.activate(True)
            except Exception:
                pass
            try:
                pc.generate_local(True)
                out.append([si, label, "gen", dset, dalready])
            except Exception as ex:
                out.append([si, label, "gen_err " + S(ex)[:60]])
        R["gen"] = out
        R["note"] = "async; run phase=poll until counts settle, then shoot"

    elif PHASE == "poll":
        P = []
        for i, label in enumerate(ORDER, 1):
            v = find_volume(label)
            if v is None:
                P.append([i, label, -1, -1])
                continue
            real, dbg = classify(v)
            P.append([i, label,
                      sum(n for _c, n, _m in real),
                      sum(n for _c, n, _m in dbg)])
        R["poll"] = P
        R["totals"] = {"real": sum(p[2] for p in P if p[2] > 0),
                       "debug": sum(p[3] for p in P if p[3] > 0)}

    elif PHASE == "show_all":
        R["shown_total"] = sum(
            set_vis(v, True) for v in (find_volume(l) for l in ORDER) if v is not None)

    elif PHASE == "debug_off":
        cleared = 0
        for label in ORDER:
            v = find_volume(label)
            if v is None:
                continue
            try:
                g = v.pcg_component.get_graph()
                if not g:
                    continue
                for nd in g.get_editor_property("nodes"):
                    try:
                        st = nd.get_settings()
                        if st is not None and st.get_editor_property("debug"):
                            st.set_editor_property("debug", False)
                            cleared += 1
                    except Exception:
                        continue
            except Exception:
                continue
        R["debug_total_cleared"] = cleared

    elif PHASE == "shot" and STAGE is not None:
        idx = int(STAGE) - 1
        label = ORDER[idx] if 0 <= idx < len(ORDER) else None
        if label is None:
            R["fatal"] = "stage out of range"
        else:
            R["stage"] = int(STAGE)
            R["label"] = label
            v = find_volume(label)
            if v is None:
                R["fatal"] = "no volume " + label
            else:
                real, dbg = classify(v)
                R["real"] = [len(real), sum(n for _c, n, _m in real)]
                R["debug"] = [len(dbg), sum(n for _c, n, _m in dbg)]

                # isolate
                hidden = 0
                for other in ORDER:
                    if other == label:
                        continue
                    ov = find_volume(other)
                    if ov is not None:
                        hidden += set_vis(ov, False)
                R["shown_self"] = set_vis(v, True)

                # frame on own geometry; fall back to the union of everything
                framed_from = "own"
                lo, hi, n = pct_bounds(real + dbg)
                if lo is None:
                    framed_from = "union"
                    allitems = []
                    for a in vols():
                        r2, d2 = classify(a)
                        allitems.extend(r2)
                    lo, hi, n = pct_bounds(allitems)
                if lo is None:
                    R["framing_err"] = "no points to frame"
                else:
                    try:
                        R["framing"] = frame_camera(lo, hi)
                        R["framing"]["from"] = framed_from
                        R["framing"]["sampled"] = n
                    except Exception as ex:
                        R["framing_err"] = S(ex)[:150]

                name = "pcg_stage_%02d_%s.png" % (int(STAGE), label)
                try:
                    t = unreal.AutomationLibrary.take_high_res_screenshot(
                        1600, 900, name, None, False, False)
                    R["fired"] = name
                    R["task_valid"] = S(t.is_valid_task()) if t else None
                except Exception as ex:
                    R["shot_err"] = "%s: %s" % (type(ex).__name__, S(ex)[:160])

except Exception as fatal:
    R["top_level_exception"] = "%s: %s" % (type(fatal).__name__, str(fatal)[:400])

try:
    print(json.dumps(R, default=str))
except Exception as pe:
    print("print failed: %s" % pe)
try:
    mcp_result = json.loads(json.dumps(R, default=str))
except Exception as se:
    mcp_result = {"serialization_failed": str(se)[:300]}
