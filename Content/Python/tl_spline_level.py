# tl_spline_level.py -- creates /Game/PCG/TL/BP_TL_SplineBuilding (an Actor
# with a SplineComponent "Footprint" and a PCGComponent running
# /Game/PCG/TL/PCG_TL_SplineBuilding), creates/loads /Game/Map/Lvl_TL_Spline
# from Template_Default, and places the test buildings.
# docs/superpowers/plans/2026-10-12-tl-spline-building.md Task 11, Step 1.
#
# Args: {"probe_only": true} -- place only TLPROBE_Spline (the L-shape), for
# Tasks 7-10's graph-segment probes. Without it (Task 11), places every
# BUILDINGS entry under its own label.
#
# Ruling R2 (task-7-brief.md): if SubobjectDataSubsystem cannot create the
# blueprint's components, STOP and report NEEDS_CONTEXT rather than inventing
# a workaround. (Measured in Task 7's exploration: it CAN -- add_new_subobject
# succeeded for both SplineComponent and PCGComponent -- so this path is not
# expected to trigger, but the guard stays for a future, differently
# configured editor.)
#
# No unreal.SystemLibrary.collect_garbage anywhere (traps.md 40: crashes
# LoadLevel). Do not save this level here (Task 11 Step 5 does that,
# separately, once no TLPROBE_* actor remains).
import gc
import json
import math

args = mcp_args or {}

BP_PATH = "/Game/PCG/TL/BP_TL_SplineBuilding"
GRAPH_PATH = "/Game/PCG/TL/PCG_TL_SplineBuilding"
DEST = "/Game/Map/Lvl_TL_Spline"
TEMPLATE = "/Engine/Maps/Templates/Template_Default"

# label: (origin (cm), vertices, Height (cm)). Each vertex is (x, y) or
# (x, y, z) in cm, local to origin; a 2-tuple is treated as z=0 (fix round 1,
# I5: TL_Tilt's vertex 2 needs z=50 for Review Focus 1, previously only a
# comment -- place_building now actually uses a per-vertex z).
BUILDINGS = {
    "TL_Hex": ((0, 0, 0),
               [(3000 * math.cos(math.radians(60 * k)), 3000 * math.sin(math.radians(60 * k)))
                for k in range(6)], 3000.0),
    # Review Focus 3: exactly one 20 deg convex corner (vertex 2), next to a
    # 400 cm short edge (edge 1, v1->v2) -- both asserted below before use.
    # Task 11: vertex 4 raised from y=137.8 to y = x*tan(25 deg) so vertex 0's
    # interior is 25 deg; at 137.8 it was 12.6 deg, outside the supported
    # 15-345 deg range (asserted by check_support_range).
    "TL_Pent": ((12000, 0, 0),
                [(0.0, 0.0), (4913.176731805098, 0.0), (5297.113635227847, 112.21610486089091),
                 (2566.821000177357, 289.13740426446907),
                 (617.2581639212892, 617.2581639212892 * math.tan(math.radians(25.0)))],
                3000.0),
    "TL_L": ((0, 12000, 0),
             [(0, 0), (6000, 0), (6000, 3000), (3000, 3000), (3000, 6000), (0, 6000)], 3000.0),
    "TL_Rect": ((12000, 12000, 0),
                [(0, 0), (6000, 0), (6000, 3000), (0, 3000)], 3000.0),
    "TL_Low": ((24000, 0, 0),
               [(0, 0), (3000, 0), (3000, 2000), (0, 2000)], 1000.0),          # Review Focus 4
    "TL_Tilt": ((24000, 12000, 0),
                [(0, 0), (4000, 0), (4000, 3000, 50.0), (0, 3000)], 3000.0),   # vertex 2 raised 50 cm, Review Focus 1
}
PROBE_LABEL = "TLPROBE_Spline"


def _holds_uobject(val):
    if isinstance(val, (unreal.Object, unreal.StructBase)):
        return True
    if isinstance(val, (list, tuple, set)):
        return any(_holds_uobject(v) for v in val)
    if isinstance(val, dict):
        return any(_holds_uobject(v) for v in val.values())
    return False


def purge():
    dropped = []
    for name, val in list(globals().items()):
        if name.startswith("__") or callable(val) or isinstance(val, type):
            continue
        try:
            if _holds_uobject(val):
                del globals()[name]
                dropped.append(name)
        except Exception:
            continue
    gc.collect()
    return dropped


def check_pentagon():
    """Review Focus 3: assert TL_Pent has exactly one 20 deg convex corner and
    that its short edge is correctly flagged, before it is ever placed."""
    import sys
    sys.path.insert(0, "E:/PCG_Claude/Tools/tl_kit")
    import importlib
    import corner_math
    importlib.reload(corner_math)
    pts = BUILDINGS["TL_Pent"][1]
    c = corner_math.classify(pts)
    spikes = [i for i, v in enumerate(c) if v["convex"] and abs(180 - abs(v["turn"]) - 20.0) < 0.5]
    if len(spikes) != 1:
        raise RuntimeError("TL_Pent must have exactly one 20 deg corner, found %r" % spikes)
    i = spikes[0]
    short_edges = []
    for ei in ((i - 1) % len(pts), i):
        plan = corner_math.edge_plan(pts, ei, 1)
        if plan["short"] and abs(plan["length"] - 400.0) < 1.0:
            short_edges.append(ei)
    if not short_edges:
        raise RuntimeError("TL_Pent's 20 deg corner has no adjacent 400 cm short edge")
    return {"spike_vertex": i, "short_edges": short_edges}


def check_support_range():
    """Every test corner must be inside the supported 15-345 deg interior
    range, or a failure there would say nothing about the claim."""
    import corner_math
    out = {}
    for label, (_, verts, _) in BUILDINGS.items():
        pts = corner_math.clean([(v[0], v[1]) for v in verts])
        interiors = [180.0 - abs(c["turn"]) if c["convex"] else 180.0 + abs(c["turn"])
                     for c in corner_math.classify(pts)]
        bad = [round(a, 2) for a in interiors if not 15.0 <= a <= 345.0]
        if bad:
            raise RuntimeError("%s has corners outside 15-345 deg: %r" % (label, bad))
        out[label] = [round(a, 2) for a in interiors]
    return out


def ensure_blueprint():
    """Create BP_TL_SplineBuilding (Actor + SplineComponent "Footprint" +
    PCGComponent) if it does not already exist. Returns (blueprint, created)."""
    EAL = unreal.EditorAssetLibrary
    if EAL.does_asset_exist(BP_PATH):
        return EAL.load_asset(BP_PATH), False

    factory = unreal.BlueprintFactory()
    factory.set_editor_property("parent_class", unreal.Actor)
    at = unreal.AssetToolsHelpers.get_asset_tools()
    name = BP_PATH.rsplit("/", 1)[-1]
    folder = BP_PATH.rsplit("/", 1)[0]
    bp = at.create_asset(name, folder, unreal.Blueprint, factory)
    if bp is None:
        raise RuntimeError("NEEDS_CONTEXT: AssetTools.create_asset returned None for %s" % BP_PATH)

    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    SDL = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    root = None
    for h in handles:
        if SDL.is_handle_valid(h) and SDL.is_root_component(SDL.get_data(h)):
            root = h
            break
    if root is None:
        raise RuntimeError("NEEDS_CONTEXT: BP_TL_SplineBuilding has no root component handle; "
                           "create the blueprint by hand (Actor + Spline + PCG components)")

    p1 = unreal.AddNewSubobjectParams()
    p1.set_editor_property("parent_handle", root)
    p1.set_editor_property("new_class", unreal.SplineComponent)
    p1.set_editor_property("blueprint_context", bp)
    spline_handle, reason1 = sds.add_new_subobject(p1)
    if not (spline_handle and SDL.is_handle_valid(spline_handle)):
        raise RuntimeError("NEEDS_CONTEXT: could not add SplineComponent to %s: %s"
                           % (BP_PATH, reason1))
    sds.rename_subobject(spline_handle, "Footprint")

    p2 = unreal.AddNewSubobjectParams()
    p2.set_editor_property("parent_handle", root)
    p2.set_editor_property("new_class", unreal.PCGComponent)
    p2.set_editor_property("blueprint_context", bp)
    pcg_handle, reason2 = sds.add_new_subobject(p2)
    if not (pcg_handle and SDL.is_handle_valid(pcg_handle)):
        raise RuntimeError("NEEDS_CONTEXT: could not add PCGComponent to %s: %s"
                           % (BP_PATH, reason2))

    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    if not unreal.EditorAssetLibrary.save_asset(BP_PATH, only_if_is_dirty=False):
        raise RuntimeError("could not save %s" % BP_PATH)
    return bp, True


def ensure_level():
    """Fix round 1 (I4): the original version called load_level and ignored
    its return value, so a failed level switch left TLPROBE actors to be
    spawned into whatever level happened to still be current -- silently.
    Now: skip the switch entirely when the editor world is already DEST
    (load_level would just reload it, which is unnecessary and has its own
    failure mode); otherwise check load_level's/new_level_from_template's
    return; then, regardless of which path was taken, assert the editor
    world's path actually is DEST before returning, so a caller can never
    proceed to spawn actors into the wrong level."""
    EAL = unreal.EditorAssetLibrary
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

    def current_world_matches_dest():
        w = ues.get_editor_world()
        return w is not None and w.get_path_name().startswith(DEST)

    if current_world_matches_dest():
        result = "already_current"
    elif EAL.does_asset_exist(DEST):
        if not les.load_level(DEST):
            raise RuntimeError("load_level(%r) returned False" % DEST)
        result = "loaded_existing"
    else:
        if not les.new_level_from_template(DEST, TEMPLATE):
            raise RuntimeError("new_level_from_template(%r, %r) returned False" % (DEST, TEMPLATE))
        result = "freshly_created"

    if not current_world_matches_dest():
        w = ues.get_editor_world()
        raise RuntimeError("editor world is %r after ensure_level(%r), refusing to spawn actors"
                           % (w.get_path_name() if w else None, DEST))
    return result


def place_building(bp, graph, eas, label, origin, verts_local, height):
    """Spawn one BP instance, wire its spline to verts_local (closed loop,
    linear), override Height, activate and generate_local. Returns the actor."""
    # remove any stale actor with this label first (idempotent reruns)
    for a in list(eas.get_all_level_actors()):
        if a.get_actor_label() == label:
            c = a.get_component_by_class(unreal.PCGComponent)
            if c is not None:
                try:
                    c.cleanup_local(True)
                except Exception:
                    pass
            eas.destroy_actor(a)

    loc = unreal.Vector(float(origin[0]), float(origin[1]), float(origin[2]))
    actor = eas.spawn_actor_from_object(bp, loc)
    if actor is None:
        raise RuntimeError("spawn_actor_from_object returned None for %s" % label)
    actor.set_actor_label(label)

    sc = actor.get_component_by_class(unreal.SplineComponent)
    sc.clear_spline_points(False)
    for i, v in enumerate(verts_local):
        lx, ly = v[0], v[1]
        lz = v[2] if len(v) > 2 else 0.0   # fix round 1, I5: per-vertex z
        world = loc + unreal.Vector(float(lx), float(ly), float(lz))
        sc.add_spline_point(world, unreal.SplineCoordinateSpace.WORLD, False)
    for i in range(len(verts_local)):
        sc.set_spline_point_type(i, unreal.SplinePointType.LINEAR, False)
    sc.set_closed_loop(True, False)
    sc.update_spline()

    comp = actor.get_component_by_class(unreal.PCGComponent)
    comp.set_graph(graph)
    gi = comp.graph_instance
    H = unreal.PCGGraphParametersHelpers
    H.set_double_parameter(gi, "Height", float(height))
    got = H.get_double_parameter(gi, "Height")
    if abs(got - float(height)) > 1e-6:
        raise RuntimeError("%s: Height override reads back %r, wanted %r" % (label, got, height))
    comp.activate(True)
    comp.generate_local(True)
    return got


def setup_floor(eas):
    """Task 11: the template's Floor is 80 m square around the origin; the
    test buildings reach x 28000 / y 18000. Stretch it under all of them
    (its mesh is 1000 cm per unit of scale, pivot on the top face)."""
    floor = next((a for a in eas.get_all_level_actors() if a.get_actor_label() == "Floor"), None)
    if floor is None:
        return None
    floor.set_actor_location(unreal.Vector(12500.0, 7700.0, -0.5), False, False)
    floor.set_actor_scale3d(unreal.Vector(40.0, 30.0, 8.0))
    o, e = floor.get_actor_bounds(False)
    return {"origin": [round(v, 1) for v in o.to_tuple()], "extent": [round(v, 1) for v in e.to_tuple()]}


def main():
    R = {"purged": purge()}
    R["pentagon_check"] = check_pentagon()
    R["interior_angles"] = check_support_range()

    bp, created = ensure_blueprint()
    R["blueprint_created"] = created

    EAL = unreal.EditorAssetLibrary
    if not EAL.does_asset_exist(GRAPH_PATH):
        raise RuntimeError("graph %s does not exist; run tl_make_spline_graph.py first" % GRAPH_PATH)
    graph = EAL.load_asset(GRAPH_PATH)

    R["level"] = ensure_level()

    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    placed = []
    if args.get("probe_only"):
        origin, verts, height = BUILDINGS["TL_L"]
        place_building(bp, graph, eas, PROBE_LABEL, origin, verts, height)
        placed.append(PROBE_LABEL)
    else:
        # Task 11: the test level is saved later, so no TLPROBE_* actor may stay in it
        removed = []
        for a in list(eas.get_all_level_actors()):
            if a.get_actor_label().startswith("TLPROBE_"):
                removed.append(a.get_actor_label())
                c = a.get_component_by_class(unreal.PCGComponent)
                if c is not None:
                    c.cleanup_local(True)
                eas.destroy_actor(a)
        R["removed_probes"] = removed
        R["floor"] = setup_floor(eas)
        heights = {}
        for label, (origin, verts, height) in BUILDINGS.items():
            heights[label] = place_building(bp, graph, eas, label, origin, verts, height)
            placed.append(label)
        R["height_readback"] = heights
    R["placed"] = placed
    R["fired"] = True
    R["note"] = "generation fired asynchronously; read in a separate call"
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
