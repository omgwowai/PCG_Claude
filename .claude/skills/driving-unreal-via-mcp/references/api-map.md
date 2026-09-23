# API map — where to start introspecting

This is NOT the full API. It is a signpost: for a task, find the likely
class/subsystem, then introspect it (see `introspection.md`) for the real methods.
Names are starting points to verify, not signatures to trust.

| Task | Entry point | Then introspect for |
|---|---|---|
| Spawn / delete / move / query actors | `EditorActorSubsystem` (`unreal.get_editor_subsystem(unreal.EditorActorSubsystem)`) | `spawn_actor_from_class`, `destroy_actor`, `get_all_level_actors`, `get_selected_level_actors` |
| Current selection | `EditorActorSubsystem` | `get_selected_level_actors`, `set_selected_level_actors` |
| Level / world ops, save level | `LevelEditorSubsystem`, `UnrealEditorSubsystem` | get/save current level, get editor world |
| Load an existing object/asset | module funcs `unreal.load_object`, `unreal.load_asset` | path forms (`/Game/...`, `/Engine/...`) |
| Import assets (textures, meshes, FBX) | `AssetImportTask`, `AssetTools` (`unreal.AssetToolsHelpers.get_asset_tools()`) | `import_asset_tasks`, task fields |
| Create new assets | `AssetTools` + a `Factory` (e.g. `MaterialFactoryNew`) | `create_asset`, factory class for the type |
| Asset CRUD on disk (exists/delete/rename/save) | `EditorAssetLibrary` (`unreal.EditorAssetLibrary`) | `does_asset_exist`, `save_asset`, `delete_asset` |
| Edit / wire up materials | `MaterialEditingLibrary` | connect expressions, set scalar/vector params |
| Static mesh component on an actor | the actor's `static_mesh_component` | `set_static_mesh`, `set_material` |
| Logging to the editor output | `unreal.log`, `unreal.log_warning`, `unreal.log_error` | — |

If the task's concept isn't here, search class names by keyword
(`introspection.md` → "Search class/symbol names by keyword").
