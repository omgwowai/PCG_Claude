# tl_verify_task10_read.py — PHASE B: read the TL building that is already in the
# now-current level. Separate call from the load, per the async rule.
#
# Computes facade-only bounds from per-instance world-space pivot transforms
# (never get_actor_bounds, which includes the PCGVolume brush), counts distinct
# TL mesh paths, and buckets instances by level to check floor-to-floor deltas.

import gc
import json

R = {}
args = mcp_args or {}


def clear_stale():
    g = globals()
    for k in list(g.keys()):
        if k.startswith("_") or k in ("R", "args"):
            continue
        try:
            v = g[k]
        except Exception:
            continue
        if hasattr(v, "get_class") or hasattr(v, "get_path_name"):
            g[k] = None
    gc.collect()


def run():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    target = None
    for a in eas.get_all_level_actors():
        try:
            if a.get_actor_label() == "TL_Building_Volume":
                target = a
        except Exception:
            continue
    if target is None:
        R["fatal"] = "TL_Building_Volume not found in the current level"
        return
    R["actor"] = target.get_actor_label()

    comp = target.get_component_by_class(unreal.PCGComponent)
    if comp is not None:
        try:
            R["graph"] = str(comp.get_graph())
        except Exception:
            pass
        try:
            R["generated_flag"] = bool(comp.get_editor_property("generated"))
        except Exception:
            pass
        # the seed of truth for the graph instance's bound SGD, if reachable
        try:
            gi = comp.get_editor_property("graph_instance")
            R["has_graph_instance"] = gi is not None
        except Exception:
            pass

    # ---------- read geometry from the Ism components --------------------
    by_mesh = {}
    total = 0
    tl_total = 0
    all_pts = []          # world-space pivot positions of every instance
    level_z = {}          # level token -> list of Z
    n_comp = 0
    for c in target.get_components_by_class(unreal.PrimitiveComponent):
        try:
            n = c.get_instance_count()
        except Exception:
            continue
        if not n:
            continue
        n_comp += 1
        try:
            mp = c.get_editor_property("static_mesh")
            path = mp.get_path_name() if mp else "<none>"
        except Exception:
            path = "<err>"
        by_mesh[path] = by_mesh.get(path, 0) + n
        total += n
        is_tl = "/Game/Building/TL/" in path
        if is_tl:
            tl_total += n
        # level token from the kit folder, e.g. Kit_Bldg_TL_L2_A
        lvl = None
        for tok in ("L1_A", "L2_A", "L3_A", "L0_A"):
            if tok in path:
                lvl = tok[1]
                break
        for i in range(n):
            try:
                t = c.get_instance_transform(i, world_space=True)
                loc = t.translation
            except Exception:
                continue
            all_pts.append((loc.x, loc.y, loc.z))
            if lvl is not None:
                level_z.setdefault(lvl, []).append(loc.z)

    R["primitive_components_with_instances"] = n_comp
    R["total_instances"] = total
    R["tl_instances"] = tl_total
    R["non_tl_instances"] = total - tl_total
    R["distinct_mesh_count"] = len(by_mesh)
    R["distinct_tl_mesh_count"] = len([p for p in by_mesh if "/Game/Building/TL/" in p])
    R["meshes"] = {k.split("/")[-1]: v for k, v in sorted(by_mesh.items(), key=lambda x: -x[1])}

    # ---------- facade-only bounds ---------------------------------------
    if all_pts:
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        zs = [p[2] for p in all_pts]
        R["pivot_span_xyz"] = [round(max(xs) - min(xs), 1),
                               round(max(ys) - min(ys), 1),
                               round(max(zs) - min(zs), 1)]
    # ---------- per-level floor stacking ---------------------------------
    floors = {}
    for lvl, zlist in level_z.items():
        floors[lvl] = {
            "count": len(zlist),
            "min_z": round(min(zlist), 1),
            "max_z": round(max(zlist), 1),
            "spread": round(max(zlist) - min(zlist), 1),
        }
    R["floors"] = dict(sorted(floors.items()))
    order = [l for l in ("0", "1", "2", "3") if l in floors]
    deltas = []
    for a, b in zip(order, order[1:]):
        d = round(floors[b]["min_z"] - floors[a]["min_z"], 1)
        deltas.append({"from": "L" + a, "to": "L" + b, "delta_cm": d})
    R["floor_deltas"] = deltas
    non_tl_spread = [v["spread"] for k, v in floors.items() if v["spread"] > 1.0]
    R["levels_with_visible_spread"] = non_tl_spread


run()
print(json.dumps(json.loads(json.dumps(R, default=str)), indent=1)[:4500])
mcp_result = json.loads(json.dumps(R, default=str))
