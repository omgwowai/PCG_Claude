# Content/Python/pcg_sa_level.py
# Task A: derive the small-area level from the demo level's template.
#
# args: {"template": "/CitySamplePCG/Levels/L_CitySamplePCG_Demo",
#        "target":   "/Game/PCGArea/L_SmallArea18",
#        "force":    false}   # true = proceed even if the target already exists
#
# WHY A TEMPLATE COPY: the demo level's terrain is one
# /Script/MeshPartition.MeshPartition actor. Stage 1 reads it and writes it back,
# and every later stage projects onto it, so a blank level produces nothing at all
# (silent zero, no error). Copying also brings the 18 PCGVolumes with their graph
# parameters, the 11 cine cameras, lights and the water plane.
#
# GLOBAL DISCIPLINE: no UObject may survive this script. Everything lives inside
# run(); module level holds only JSON. See the Global Constraints in the plan.
#
# WHY purge_uobject_globals() RUNS FIRST: this script switches levels, and the
# bridge execs scripts inside the persistent __main__ module, so any unreal
# wrapper left in a global by an EARLIER script pins the old world and the switch
# aborts in UEditorEngine::CheckForWorldGCLeaks() (reference chain
# FPyReferenceCollector::AddReferencedObjects(Package ...)). Measured 2026-09-24;
# the spec lists it as fact 4. Defensive, cheap, and it is what makes this call
# survivable no matter what ran before it.

import gc
import json

TEMPLATE = "/CitySamplePCG/Levels/L_CitySamplePCG_Demo"
TARGET = "/Game/PCGArea/L_SmallArea18"


def vec(v):
    return [round(float(v.x), 3), round(float(v.y), 3), round(float(v.z), 3)]


def _holds_uobject(val, ue):
    """True if val is, or contains, an unreal wrapper that could pin a world.

    Deliberately NOT "is a container": the first version of this function dropped
    every dict/list global, which deleted `_args` (a plain dict) before run() read
    it and killed the call with NameError. Only values that actually carry an
    engine object are a hazard.
    """
    if isinstance(val, (ue.Object, ue.StructBase)):
        return True
    if isinstance(val, (list, tuple, set)):
        return any(_holds_uobject(v, ue) for v in val)
    if isinstance(val, dict):
        return any(_holds_uobject(v, ue) for v in val.values())
    return False


def purge_uobject_globals():
    """Drop anything left in the module globals that could pin a world."""
    import unreal

    dropped = []
    for name, val in list(globals().items()):
        if name.startswith("__") or callable(val) or isinstance(val, type):
            continue
        try:
            if _holds_uobject(val, unreal):
                del globals()[name]
                dropped.append(name)
        except Exception:
            continue
    gc.collect()
    return dropped


def inventory(eas, ue):
    """Everything Task B needs to transform, in JSON-safe form."""
    inv = {"spline_actors": [], "volumes": [], "cameras": [], "terrain": [],
           "tagged_any": {}}
    for a in eas.get_all_level_actors():
        cn = a.get_class().get_name()
        try:
            tags = [str(t) for t in a.get_editor_property("tags")]
        except Exception:
            tags = []
        # Tags must be collected from EVERY actor, not only the spline carriers.
        # Highway_Width is carried by a PCGVolume that has no spline component, so
        # collecting tags from spline actors alone reports it missing and fails the
        # gate on a level that is actually complete (measured 2026-09-24: the first
        # run of this script failed its gate for exactly that reason).
        for t in tags:
            inv["tagged_any"][t] = inv["tagged_any"].get(t, 0) + 1
        if cn == "PCGVolume":
            try:
                pc = a.pcg_component
                g = pc.get_graph()
                gname = str(g.get_name()) if g else None
            except Exception:
                gname = None
            inv["volumes"].append({"label": str(a.get_actor_label()),
                                   "loc": vec(a.get_actor_location()),
                                   "graph": gname, "tags": tags})
        if cn == "CineCameraActor":
            r = a.get_actor_rotation()
            inv["cameras"].append({"label": str(a.get_actor_label()),
                                   "loc": vec(a.get_actor_location()),
                                   "rot": [round(float(r.pitch), 3),
                                           round(float(r.yaw), 3),
                                           round(float(r.roll), 3)]})
        if "MeshPartition" in cn:
            inv["terrain"].append({"label": str(a.get_actor_label()), "class": cn})
        comps = a.get_components_by_class(ue.SplineComponent)
        if not comps:
            continue
        entry = {"label": str(a.get_actor_label()), "class": cn, "tags": tags,
                 "loc": vec(a.get_actor_location()), "scale": vec(a.get_actor_scale3d()),
                 "splines": []}
        for sc in comps:
            n = int(sc.get_number_of_spline_points())
            entry["splines"].append({
                "num_points": n,
                "closed": bool(sc.is_closed_loop()),
                "points": [vec(sc.get_location_at_spline_point(
                    i, ue.SplineCoordinateSpace.WORLD))
                    for i in range(min(n, 200))],
            })
        inv["spline_actors"].append(entry)
    return inv


def highway_width_probe(eas):
    """Locate the Highway_Width dependency, which is NOT an actor tag.

    Measured 2026-09-24: none of the demo level's 194 actors carries a
    Highway_Width tag, in the source level or in the copy. The string appears
    inside one PCGVolume's package because that volume holds a GRAPH PARAMETER
    OVERRIDE, and the graphs read it through
    PCGGenericUserParameterGetSettings(property_path="Highway_Width").
    references/migrated-citysample-library.md lists it among the actor tags; that
    is wrong, and this probe is how the dependency is really confirmed.

    The value is a width in cm and is deliberately NOT scaled by the transform.
    """
    found = []
    for v in eas.get_all_level_actors():
        try:
            if v.get_class().get_name() != "PCGVolume":
                continue
            g = v.pcg_component.get_graph()
            if g is None:
                continue
            for nd in g.get_editor_property("nodes"):
                st = nd.get_settings()
                if st is None:
                    continue
                try:
                    pp = str(st.get_editor_property("property_path"))
                except Exception:
                    continue
                if pp == "Highway_Width":
                    found.append({"volume": str(v.get_actor_label()),
                                  "graph": str(g.get_name()),
                                  "node_class": st.get_class().get_name()})
        except Exception:
            continue
    return found


EXPECT_GRAPHS = ["PCG_1_1_Terrain", "PCG_1_2_BG_Buildings", "PCG_1_3_BG_Mountains",
                 "PCG_2_1_MainTower_Footprint", "PCG_2_2_CentralPark_Footprint",
                 "PCG_3_1_1_Districts", "PCG_3_1_2_Roads", "PCG_3_1_3_Highways",
                 "PCG_3_1_4_Lots", "PCG_3_2_1_Ground", "PCG_3_2_2_LeftOverLots",
                 "PCG_3_2_3_Parkings", "PCG_3_3_1_Buildings", "PCG_3_3_2_Rooftops",
                 "PCG_4_1_MainTower_Visuals", "PCG_4_2_CentralPark_Visuals",
                 "PCG_5_1_CityEdge", "PCG_5_2_OuterForest"]


def run(template, target, force):
    import unreal

    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ael = unreal.EditorAssetLibrary

    out = {"template": template, "target": target,
           "current_before": str(les.get_current_level())}

    if ael.does_asset_exist(target):
        if not force:
            out["abort"] = ("target level already exists; pass force=true to "
                            "close the current level and overwrite it")
            out["gate"] = {"pass": False, "reason": "target exists"}
            return out
        out["existed"] = True

    attempts = []
    ok = False

    # Path 1: the documented one-call copy.
    try:
        ok = bool(les.new_level_from_template(target, template))
        attempts.append({"path": "new_level_from_template", "ok": ok})
    except Exception as ex:
        attempts.append({"path": "new_level_from_template",
                         "error": "%s: %s" % (type(ex).__name__, str(ex)[:200])})

    # Path 2: explicit new-map-from-template + save-as.
    if not ok:
        try:
            world = unreal.EditorLoadingAndSavingUtils.new_map_from_template(template, False)
            saved = bool(unreal.EditorLoadingAndSavingUtils.save_map(world, target)) if world else False
            attempts.append({"path": "new_map_from_template+save_map", "ok": saved})
            ok = saved
        except Exception as ex:
            attempts.append({"path": "new_map_from_template+save_map",
                             "error": "%s: %s" % (type(ex).__name__, str(ex)[:200])})

    out["attempts"] = attempts
    if not ok:
        out["failed"] = ("both scripted copy paths failed; ask the user to run "
                         "File > Save Current Level As from the demo level")
        out["gate"] = {"pass": False, "reason": "both copy paths failed"}
        return out

    out["current_after"] = str(les.get_current_level())
    out["on_target"] = target.split("/")[-1] in out["current_after"]

    inv = inventory(eas, unreal)
    out["inventory"] = inv

    # Gate: every dependency the 18 graphs read must have come across.
    # Tags come from EVERY actor (see inventory()); Highway_Width is not a tag at
    # all but a graph parameter, so it is confirmed by its own probe and is not
    # looked for in the tag table.
    tagged = inv["tagged_any"]
    graphs = sorted([v["graph"] for v in inv["volumes"] if v["graph"]])
    hw = highway_width_probe(eas)
    gate = {
        "level_actors": len(eas.get_all_level_actors()),
        "terrain_actors": len(inv["terrain"]),
        "volumes": len(inv["volumes"]),
        "cameras": len(inv["cameras"]),
        "spline_actors": len(inv["spline_actors"]),
        "spline_components": sum(len(a["splines"]) for a in inv["spline_actors"]),
        "tagged": tagged,
        "graphs": graphs,
        "highway_width_nodes": hw,
    }
    gate["missing_graphs"] = [g for g in EXPECT_GRAPHS if g not in graphs]
    gate["missing_tags"] = [t for t in ("City", "Arteries", "Highway",
                                        "LandmarkPark", "Terrain_shaping_1")
                            if t not in tagged]
    gate["pass"] = bool(
        gate["terrain_actors"] >= 1
        and gate["volumes"] == 18
        and gate["cameras"] >= 11
        and gate["spline_actors"] == 19          # measured baseline, see the ledger
        and not gate["missing_graphs"]
        and not gate["missing_tags"]
        and hw                                     # Highway_Width param reachable
    )
    out["gate"] = gate
    return out


try:
    _args = mcp_args if isinstance(mcp_args, dict) else {}
except NameError:
    _args = {}

try:
    _dropped = purge_uobject_globals()
    RESULT = {"ok": True, "dropped_globals": _dropped,
              "data": run(str(_args.get("template", TEMPLATE)),
                          str(_args.get("target", TARGET)),
                          bool(_args.get("force", False)))}
except Exception as _exc:
    RESULT = {"ok": False, "error": "%s: %s" % (type(_exc).__name__, str(_exc)[:400])}

try:
    mcp_result = json.loads(json.dumps(RESULT, default=str))
except Exception as _se:
    mcp_result = {"ok": False, "serialization_failed": str(_se)[:200]}

print(json.dumps(mcp_result, ensure_ascii=False, default=str)[:200000])
del RESULT, _args
gc.collect()
