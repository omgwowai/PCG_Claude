# tl_new_showcase_level.py -- create /Game/Map/Lvl_TL_Showcase from the engine's
# default template (sky, sun, fog, floor) and report what it contains. The
# current level is closed WITHOUT saving (it may be the CitySample demo level,
# which must never be saved). UObject globals are purged first, because a
# stale wrapper pins the old world and aborts the switch (traps: level switch).
import gc
import json

DEST = "/Game/Map/Lvl_TL_Showcase"
TEMPLATE = "/Engine/Maps/Templates/Template_Default"


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


def main():
    R = {"purged": purge()}
    EAL = unreal.EditorAssetLibrary
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if EAL.does_asset_exist(DEST):
        R["loaded_existing"] = les.load_level(DEST)
    else:
        R["created"] = les.new_level_from_template(DEST, TEMPLATE)
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    R["world"] = w.get_path_name()
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    acts = []
    for a in eas.get_all_level_actors():
        rec = {"label": a.get_actor_label(), "class": a.get_class().get_name(),
               "loc": [round(v) for v in a.get_actor_location().to_tuple()],
               "scale": [round(v, 2) for v in a.get_actor_scale3d().to_tuple()]}
        if a.get_class().get_name() == "StaticMeshActor":
            sm = a.static_mesh_component.get_editor_property("static_mesh")
            rec["mesh"] = sm.get_path_name() if sm else None
        acts.append(rec)
    R["actors"] = acts
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
