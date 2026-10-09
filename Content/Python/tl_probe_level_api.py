# tl_probe_level_api.py -- READ-ONLY. Signatures for creating a level and for
# the actor/light classes a showcase level needs.
import json

R = {}
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
R["LevelEditorSubsystem"] = {
    m: str(getattr(les, m).__doc__)[:300]
    for m in dir(les) if not m.startswith("_") and
    any(k in m.lower() for k in ("new_level", "save", "load", "current", "level"))
}
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
R["EditorActorSubsystem"] = [m for m in dir(eas) if not m.startswith("_")]
R["classes"] = {}
for c in ("DirectionalLight", "SkyLight", "SkyAtmosphere", "ExponentialHeightFog",
          "VolumetricCloud", "StaticMeshActor", "PostProcessVolume", "PlayerStart"):
    R["classes"][c] = hasattr(unreal, c)
import os
R["template_candidates"] = [p for p in (
    "/Engine/Maps/Templates/OpenWorld",
    "/Engine/Maps/Templates/Template_Default",
) if unreal.EditorAssetLibrary.does_asset_exist(p)]
mcp_result = json.loads(json.dumps(R, default=str))
