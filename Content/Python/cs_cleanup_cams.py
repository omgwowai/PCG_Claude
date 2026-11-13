# cs_cleanup_cams.py -- delete helper camera actors by label (unsaved level state only).
# Args: {"labels": ["CS_WaterCam", ...]}
import unreal

_eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
_labels = set((globals().get("mcp_args") or {}).get("labels", []))
_deleted = []
for _a in _eas.get_all_level_actors():
    if _a.get_actor_label() in _labels:
        _deleted.append(_a.get_actor_label())
        _eas.destroy_actor(_a)
mcp_result = {"deleted": _deleted}
del _a, _eas
