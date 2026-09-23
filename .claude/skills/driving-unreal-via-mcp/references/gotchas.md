# Gotchas & conventions

Things introspection cannot tell you. Read before writing a real script.

## Game thread

UE Python runs on the editor's main (game) thread; the `UnrealMcpBridge` plugin
already marshals execution onto it. You don't manage threads — but long-running
loops block the editor UI for the whole run, so keep batch operations bounded and
`print` progress so the run is observable.

## Editor vs runtime subsystems

Use **Editor** subsystems for editor automation
(`EditorActorSubsystem`, `LevelEditorSubsystem`). Game/runtime subsystems
operate on PIE/standalone worlds and usually return nothing useful from an
editor script. When introspection shows two similar classes, prefer the
`Editor*` one for editor tasks.

## Undo / transactions

Wrap mutating operations so the user can Ctrl+Z them:

```python
import unreal
with unreal.ScopedEditorTransaction("Tint cubes red") as _:
    # ... mutate actors/assets here ...
    pass
```

## Asset path formats

- Project assets: `/Game/Path/Asset` (the `.uasset` on disk under `Content/`).
- Engine assets: `/Engine/...` (e.g. `/Engine/BasicShapes/Cube.Cube`).
- `load_object`/`load_asset` may need the `Package.AssetName` form
  (note the duplicated trailing name, e.g. `/Engine/BasicShapes/Cube.Cube`).
- Verify a path with `unreal.EditorAssetLibrary.does_asset_exist("/Game/...")`
  before relying on it.

## Saving edits persist nothing until you save

Editing an asset in memory does not write it to disk. After mutating an asset:

```python
import unreal
unreal.EditorAssetLibrary.save_asset("/Game/Path/Asset")   # or save_loaded_asset(obj)
```

Spawning/moving actors in the level is saved when the level is saved, not per-actor.

## mcp_result must be JSON-serializable

`run_unreal_script` returns `mcp_result` as JSON. `unreal.Vector`, `unreal.Name`,
actor objects, etc. are NOT serializable. Convert first:

```python
loc = actor.get_actor_location()
mcp_result = {"location": [loc.x, loc.y, loc.z], "label": str(actor.get_actor_label())}
```

## Path safety

Every script (including `_explore.py`) must be written under `Content/Python/`.
Paths that escape the scripts root are rejected by the bridge.

## Normal-sampler texture parameters need a TC_NORMALMAP default

A `MaterialExpressionTextureSampleParameter2D` with
`sampler_type = SAMPLERTYPE_NORMAL` defaults its `texture` to the engine's
`DefaultTexture` (a Color texture). That is a HARD SM6 compile error
("Sampler type is Normal, should be Color") — the material AND every MI based
on it silently fall back to the default material. Always set the default:

```python
node.set_editor_property(
    "texture", unreal.EditorAssetLibrary.load_asset("/Engine/EngineMaterials/FlatNormal"))
```

Diagnosis: `MaterialEditingLibrary.get_statistics(mat)` returns
`num_pixel_shader_instructions == 0` (and `num_samplers == -1`) for a material
that failed to compile — a cheap health probe. Root-cause error lines live in
`Saved/Logs/<project>.log` (`LogShaderCompilers`), not in the Python API.
