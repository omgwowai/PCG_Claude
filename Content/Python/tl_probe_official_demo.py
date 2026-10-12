# tl_probe_official_demo.py -- THROWAWAY PROBE. Run an official example graph,
# unmodified, on a temporary PCGVolume in Lvl_TL_Showcase so its corners can be
# measured and photographed. The graph asset is only referenced, never edited or
# saved; the level is never saved while TLPROBE_* actors exist.
# Args: {"graph": path, "label": "TLPROBE_X", "origin": [x, y, z], "scale": 80}
#       {"label": "TLPROBE_X", "clear": true} removes the actor.
import json

args = mcp_args or {}


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    if not w.get_path_name().startswith("/Game/Map/Lvl_TL_Showcase."):
        return {"error": "current world is %s" % w.get_path_name()}
    label = args["label"]
    if not label.startswith("TLPROBE_"):
        return {"error": "label must start with TLPROBE_"}
    removed = 0
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == label:
            eas.destroy_actor(a)
            removed += 1
    if args.get("clear"):
        return {"removed": removed}
    g = unreal.EditorAssetLibrary.load_asset(args["graph"])
    if g is None:
        return {"error": "graph not loadable"}
    vol = eas.spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(*args["origin"]))
    vol.set_actor_label(label)
    s = float(args.get("scale", 80.0))
    vol.set_actor_scale3d(unreal.Vector(s, s, s))
    brush = vol.get_component_by_class(unreal.BrushComponent)
    if brush is not None:
        brush.set_visibility(False)
    comp = vol.get_component_by_class(unreal.PCGComponent)
    comp.set_graph(g)
    comp.activate(True)
    comp.generate_local(True)
    return {"spawned": label, "graph": args["graph"]}


mcp_result = json.loads(json.dumps(main(), default=str))
