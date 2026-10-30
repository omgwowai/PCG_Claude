# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

- **PCG_Claude** — Unreal Engine **5.8** C++ project, a third-person template plus three
  self-contained gameplay variants (Combat, Platforming, SideScrolling).
- Engine: **`E:\UnrealEngine`** — a **source build** of UE 5.8.2. `EngineAssociation` in
  `PCG_Claude.uproject` is that build's registry GUID `{4B303DEF-4E44-1DE5-A177-09B23BCA8A5A}`.
- Game module: `PCG_Claude` (Runtime). Plugins enabled (as in `PCG_Claude.uproject`):
  ModelingToolsEditorMode, StateTree, GameplayStateTree, PythonScriptPlugin, PCG, PCGPrimitives,
  UnrealMcpBridge, PyPCGTools, CitySamplePCG, GeometryScripting, PCGGeometryScriptInterop,
  PCGMeshPartitionInterop, PCGPrimitives_MeshPartitionInterop, PCGPythonInterop, MeshPartition,
  MeshTerrainMode, ToolsetRegistry.
- Git remote: `https://github.com/omgwowai/PCG_Claude.git` (branch `main`).
- The project has **PCG content of its own**: `Content/PyPCG/` (the PyPCG slim and town graphs and the
  generated town `L_PyTown`) and `Content/PCGArea/` (the small-area levels). The City Sample graphs and
  art come from the migrated `CitySamplePCG` plugin (`Plugins/CitySamplePCG/`, content gitignored).

The gameplay code is stock Epic template code; treat it as upstream behavior to extend rather than
rewrite. The bespoke additions are the MCP bridge toolchain ("Driving the editor" below), the
`PyPCGTools` C++ plugin, the `pypcg` Python package (see the **PyPCG** paragraph below), and the
migrated `CitySamplePCG` plugin.

## Architecture

`Source/PCG_Claude/` holds a shared base set and three independent variants. **Most C++
gameplay classes are `UCLASS(abstract)`** and are meant to be used through the Blueprints under
`Content/` that derive from them, so edit the `BP_*` assets to change behavior. Adding a property in
C++ is only half the change until the Blueprint picks it up, and you cannot instantiate an abstract
class in a level.

The handful of concrete gameplay classes are `ACombatActivationVolume`, `APlatformingGameMode`, and
`ASideScrollingCameraManager`. The `AnimNotify_*` and `EnvQueryContext_*` classes are also concrete:
they are referenced by name from animation montages and AI queries, so renaming one breaks the asset
that points at it.

Shared base (third-person template):

| C++ class | Blueprint |
|---|---|
| `APCG_ClaudeCharacter` | `Content/ThirdPerson/Blueprints/BP_ThirdPersonCharacter` |
| `APCG_ClaudeGameMode` | `Content/ThirdPerson/Blueprints/BP_ThirdPersonGameMode` |
| `APCG_ClaudePlayerController` | `Content/ThirdPerson/Blueprints/BP_ThirdPersonPlayerController` |

Each `Variant_*/` directory is self-contained — its own character, game mode, player controller,
AI, and UI — and does **not** share the base character with the others. Each variant's level
selects its own game mode, so variants are switched by opening a level, not by a project setting:

| Variant | Level | Game mode Blueprint |
|---|---|---|
| Combat | `/Game/Variant_Combat/Lvl_Combat` | `BP_CombatGameMode` |
| Platforming | `/Game/Variant_Platforming/Lvl_Platforming` | `BP_PlatformingGameMode` |
| SideScrolling | `/Game/Variant_SideScrolling/Lvl_SideScrolling` | `BP_SideScrollingGameMode` |
| (base) | `/Game/ThirdPerson/Lvl_ThirdPerson` | `BP_ThirdPersonGameMode` |

Gameplay is composed through interfaces in each variant's `Interfaces/` directory, which is what
lets interactables work without knowing each other's types:

- **Combat** — `ICombatAttacker` (attack traces driven by the `AnimNotify_*` classes),
  `ICombatDamageable` (damage/heal/knockback/death/danger), `ICombatActivatable`
  (context-agnostic activate/toggle, used to chain spawners and volumes).
- **SideScrolling** — `ISideScrollingInteractable` (single `Interaction` entry point).

Enemy AI runs through **StateTree** (`ST_CombatEnemy`, `ST_SideScrollingNPC`) with C++ utility
tasks in `Variant_Combat/AI/CombatStateTreeUtility` and `Variant_SideScrolling/AI/`.

Shared content across all variants lives in `Content/Characters/` (Manny/Quinn mannequins, rigs,
anims), `Content/Input/` (base input actions and mapping contexts), and `Content/LevelPrototyping/`
(reusable meshes and interactables). Each variant adds its own `Input/`, `UI/`, and `Anims/` on top.

`Config/DefaultEngine.ini` carries `ActiveClassRedirects` / `ActiveGameNameRedirects` mapping the
original `TP_ThirdPerson` names onto `PCG_Claude` names. Keep these working if you rename classes;
they are what keeps existing Blueprint references from breaking.

## Driving the editor from Claude (MCP bridge)

`UnrealMcpBridge` (under `Plugins/`) hosts a localhost WebSocket server inside the running editor.
The Python MCP server at `mcp_server/` exposes it as one tool, `run_unreal_script`, which executes
a `.py` file from `Content/Python/` in the editor embedded Python interpreter.

- **Port `8777`** (host `127.0.0.1`) — deliberately not `8765`, which the project this was ported
  from still uses, so both editors can run at once. The port lives in four places that must agree:
  - `Plugins/UnrealMcpBridge/Source/UnrealMcpBridge/Public/UnrealMcpBridgeSettings.h` (the `Port`
    default; also overridable per-user in `Saved/Config/WindowsEditor/Editor.ini` under
    `[/Script/UnrealMcpBridge.UnrealMcpBridgeSettings]`)
  - `.mcp.json` to `env.UE_MCP_PORT`
  - `mcp_server/mcp_server/server.py` (the `UE_MCP_PORT` default)
  - `.claude/skills/driving-unreal-via-mcp/SKILL.md` (the connection-error text it tells you to
    look for)
- Scripts must live under `Content/Python/` (the scripts root); the bridge rejects paths that
  escape it.
- **Workflow skill: `.claude/skills/driving-unreal-via-mcp/`** — read it before any editor task.
  Its core discipline is to introspect the `unreal` API at runtime rather than write calls from
  memory, because that API is large and version-specific.
- Python env for the MCP server is `mcp_server/.venv` (Python 3.14), installed with
  `pip install -e "mcp_server[dev]"`. **`mcp` must stay below 2.0**: `server.py` imports
  `mcp.server.fastmcp.FastMCP`, which was renamed to `MCPServer` in the 2.x SDK, so an unpinned
  install fails at import.
- If a call returns `Unreal editor not connected on 127.0.0.1:8777`, the editor is not running with
  the plugin loaded — ask the user to launch it rather than retrying. A ghost process can also squat
  the port; check with `netstat -ano | findstr 8777`.
- **After an editor crash or a killed editor, move `Saved/Autosaves/*` aside before relaunching**, and
  answer "don't restore" if a *Restore Packages* dialog still appears. Restoring writes the autosaved
  demo state over the demo level's real (gitignored) external-actor files under
  `Plugins/CitySamplePCG/Content/__ExternalActors__/`; it happened twice (skill `traps.md` 78). The
  byte-identical originals are in `E:\CitySample 5.8\Plugins\Experimental\CitySamplePCG\Content\`.
  V2's `prepare` turns editor autosave off in memory and its `restore` turns it back on, so always
  end a V2 session with `restore`.
  Switching away from a large level (the demo, `L_PyTown`) with `load_level` can itself crash the
  editor, and `new_blank_map` before `load_level` does (traps 79, 83).

**PyPCG** (guide: `docs/pypcg-guide.md`). The 18 City Sample stage graphs, ported so that their
computation runs in Python Data Processor nodes. `Content/Python/pypcg/` holds the stage modules
(`stages/sNN_*.py`, pure Python with no `unreal` import, `run(inputs, params, ctx)`), the slim-graph
descriptions (`graphs/`), the node shim (`host.py`), the PCG-data adapters (`ue/`), the shared geometry
(`geo/`), the V1 invariants (`checks/`), V2 (`v2.py`, `v2_thresholds.json`) and the census
(`census.py`). The editor entry points are `Content/Python/pypcg_build_slim.py` (builds the graphs and
must report `diffs: 0`), `pypcg_compare_stage.py` (V2 against the official graph in the demo level,
never saved), `pypcg_v1_editor.py` (V1), and `pypcg_town_level.py` / `pypcg_town.py` (the 18-step town
`/Game/PyPCG/L_PyTown`). Every driver that swaps graphs or spawns volumes refuses unless its level
(the demo, `L_PyTown`, `L_PyCity` or `L_PyCitySmall`, by full package path) is current (`pypcg/level.py`). `PyPCGTools` is a project plugin (Editor module) with 13 functions that
Python cannot reach otherwise (graph IR export, parameter and pin writes, `MakePolygon2DData`,
dynamic pins). `PCGPythonInterop` is an enabled engine plugin (Beta, editor-only), built into
`E:\UnrealEngine`. The assets under `/Game/PyPCG/Slim`, `/Game/PyPCG/Town`, `/Game/PyPCG/City` and
`/Game/PyPCG/Probe` are generated from those `.py` files: edit the `.py` and rebuild, never the asset in
the graph editor.

**Single-graph city** (guide §13). `pypcg/combined.py` merges the 18 slim graphs into one graph
`/Game/PyPCG/City/PCG_PyCity` (parameters renamed `SNN_<name>`, grouped by stage) that one volume in
`/Game/PyPCG/L_PyCity` runs; the control regions stay tagged / referenced level actors, plus the two
footprint volumes as tagged control actors. Driver: `pypcg_city.py` (one phase per call; long phases
take `{"defer": true}` and write `Saved/Reports/pypcg_city_deferred.json`, because a long bridge call
loses its reply). `L_PyCity` is saved without its generated output (one 149 MB actor otherwise):
regenerate after opening it. `/Game/PyPCG/L_PyCitySmall` runs the same graph on a ~560 x 440 m layout
(`{"profile": "small"}`, `pypcg/profiles/small.py` + `small_layout.py`) and is saved generated (85 MB).
Every control actor is read by tag, so the graph runs in any level that carries the tags; rebuilding
the graph resets the volume's overrides, so run `assign` after every `build`.

**PyWorld** (guide: `docs/pyworld-guide.md`; **workflow skill: `.claude/skills/pyworld-scene-builder/`** - read it before changing
the terrain material, vegetation, towns or buildings). The world-building pipeline of the talk "Building Worlds with Houdini"
(Ubisoft, Ghost Recon) as nine PCG graphs `/Game/PyPCG/World/PCGW_01_Terrain` … `PCGW_09_Surface`, one Python node each,
run in order in `/Game/PyPCG/L_PyWorld` (a 2 x 2 km valley: terrain, river, roads, bridges, settlements, vegetation, props,
surface materials). Logic in `Content/Python/pypcg/stages/wNN_*.py` and `pypcg/world/`; driver `Content/Python/pyworld.py`
(`build / make / layout / assign / reset / gen / read / check / shot / compare / save`, one phase per call);
offline tests `Tools/pypcg/tests/test_world_*.py`. W7 is a layered vegetation ecology (guide §6: `pypcg/world/flora.py`,
`ecology.py`, `grow.py`; 48 species, ~2.8 M instances) on Electric Dreams Megascans copied into `/Game` by
`Tools/pyworld/ed_closure.py --copy` (9.75 GB, not in git) and summer copies of the Megaplants trees
(`/Game/PyPCG/World/Trees`); their leaves need `r.Nanite.Foliage=1` (Config/DefaultEngine.ini, traps 97-101). Shapes
(guide §7): W3 walks Kinoshita meanders along an A* base line and emits ONE continuous water mesh (`geo.Mesh` ->
PCGDynamicMeshData -> native Spawn Dynamic Mesh, material `M_PyWorldStream` from `pyworld_water_material.py`); W4 roads
wander on a preference field and join the network at junctions; W6 streets grow organically (`pypcg/world/settle.py`);
`pypcg/world/shape.py` measures straightness / kinks (traps 102-106). Towns (guide §8): W6 assembles every building
from the Megascans Modular_Building kits by a City-Sample-style style database -- `pypcg/world/grammar.py` (facade
grammar), `kit.py` (modules, tints, street kit), `bdf.py` (7 style codes), `building.py` (walls, corners, doors, props,
hip roofs), `rules.py` (archetypes, zones, storeys from height noise and settlement rank) -- as `Modules` points (Mesh,
Mat0) for the native mesh spawner; the 70 tinted material instances in `/Game/PyPCG/World/Town` come from
`pyworld_town_materials.py`, and `pyworld_town_preview.py` lays sample buildings over the sea, never saved (traps
107-113). Offline loop: `pyworld.py gen {"stage": 3, "capture": true}` pickles the node's inputs, then
`C:\Python314\python.exe Tools/pyworld/offline.py --tag <t>` runs W3->W6 on them and draws
`Saved/Reports/pyworld_plan_<t>.png` (~10 s; `--town` adds the town's plan by style). `L_PyWorld` is saved
**without its generated output** (10 MB; generated it is 449 MB over 179 files, and the W7 actor alone is 361 MB, over
GitHub's 100 MB file limit): after opening it, run `gen` / `read` for W1..W9 in order (about 10 minutes), and to commit a
level change, `reset {"from": 1}` before `save`.

**PyInterior** (guide: `docs/pyinterior-guide.md`). Rule-driven life-sim interiors (inZOI / The Sims style): a house is a
PCGVolume with its own closed footprint spline (an instance SplineComponent added through `SubobjectDataSubsystem`, trap 117);
graph `/Game/PyPCG/Interior/PCGI_House` (Get Spline Data (Self) + Get Actor Data (Self) -> one Python node
`pypcg/stages/i01_house.py` -> native Static Mesh Spawner, `Mesh` / `Mat0` attributes) plans footprint -> program (by area)
-> zoning grammar -> doors -> windows (`[S][W,S]*`) -> furniture (room recipes, kitchen grammar) -> walls, floors, openings
and furniture instances, all from the rule tables in `Content/Python/pypcg/interior/` (`program.py` is its BDF). Level
`/Game/PyPCG/L_PyInterior` (two streets, 15 demo houses, saved generated, 3.7 MB); driver `Content/Python/pyinterior.py`
(`level / build / site / houses / assign / gen / read / shape / view / shot / status / save`; run `assign` after every
`build` -- a rebuilt graph forgets the volumes' overrides, and `assign` puts the street's WallCut and the storeys' Floors /
StairType back, trap 124);
offline plans `Tools/pyinterior/plan.py --demo --sweep`, and `Tools/pyinterior/census.py` (every rectangle on a 50 cm grid
through the chain, ~3 min; run it before and after a rule change). `pypcg/interior/house.py` is the chain: a variant whose
required furniture does not fit steps down like a room below its minimum. Change the outline and the plan follows: dragging a footprint point
in the viewport regenerates the house on mouse release (Regenerate In Editor), but Python spline edits send no change
notification, so scripts flush the PCG cache (`pcg.FlushCache`) before generating (traps 114-116). Four primitive recipes
become StarterContent meshes (couch, lounge chair, round table, bush) while the stage parameter `RealMeshes` is on;
`Content/StarterContent/` comes from `Tools/pyinterior/starter_closure.py --copy` (gitignored).
**Multi-storey houses** (guide §8): one footprint spline per floor, read by height (floor k at the actor's z + k x 300 cm;
stage params `Floors`, `ShowFloors`, `StairType`); `pypcg/interior/storeys.py` (floors, clipping, terraces, the building
loop), `stairs.py` (U / L / straight stairs, candidates, parts), `floorplan.py` (each floor zoned around the fixed stair
room), `terrace.py`; the stair is placed first, every floor is planned around it from its own GROUND / UPPER program table,
exposed roofs become terraces with a glass door, furniture and railing. One floor left -> today's single-floor path, whose
output is pinned by `Tools/pypcg/tests/test_interior_regression.py` (golden digests: keep them passing). The 7 demo houses
stand on the second street (`houses {"set": "storeys"}`); `view {"floors": k, "wallcut": 100}` is the cutaway;
`plan.py --storeys` and `census.py --storeys` (708 houses, ~5 min) are the offline checks.

## Build

```powershell
& "E:\UnrealEngine\Engine\Build\BatchFiles\Build.bat" PCG_ClaudeEditor Win64 Development -Project="E:\PCG_Claude\PCG_Claude.uproject" -WaitMutex
```

- Success = exit code 0 and `Result: Succeeded` with no errors. An incremental build after touching
  a few files takes well under a minute; allow 10+ minutes for the first one.
- Build the **game** target with `PCG_Claude` instead of `PCG_ClaudeEditor`.
- UBT auto-discovers new `.cpp`/`.h` files in already-globbed module directories, so adding source
  files does not require regeneration — just run `Build.bat`. Regenerate IDE project files (the
  `*.sln`/`*.slnx` files, which are gitignored) only after adding or removing files or modules:
  ```powershell
  & "E:\UnrealEngine\GenerateProjectFiles.bat"
  ```

## Tests

Three suites:

| Suite | Runs | Baseline |
|---|---|---|
| `pypcg` (Python form of the 18 stage graphs, PyWorld and PyInterior, offline) | `C:\Python314\python.exe -m pytest Tools/pypcg/tests -q` | 2094 passed, 18 skipped (the skips are the per-node reference drafts' step check) |
| `PyPCGTools` C++ automation | command below; needs **both** editors (this one and `E:\PCG_Codex`) closed | 9 tests, all `Result={Success}`, exit 0 |
| MCP server | `.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests -q` | 17 passed |

- `pypcg` runs on system Python 3.14 because the MCP venv lacks Pillow.
  `C:\Python314\python.exe Tools/pypcg/baseline.py check` checks that the official CitySample assets
  under `Plugins/CitySamplePCG/Content` keep their recorded mtime and size.
- One MCP test: `... -m pytest mcp_server/tests/test_protocol.py::test_build_run_frame_roundtrips_to_expected_json -q`.
- The C++ tests live in `Plugins/PyPCGTools/Source/PyPCGTools/Private/Tests/`. The game module
  `PCG_Claude` registers none, so a `PCG_Claude` filter matches nothing and exits **255**.

The UE automation harness runs engine or in-editor tests headlessly (verified with the engine
self-test filter `System.Core.Algo`; swap the filter for `PyPCGTools` to run the plugin's tests):

```powershell
& "E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "E:\PCG_Claude\PCG_Claude.uproject" -ExecCmds="Automation RunTests PyPCGTools; Quit" -unattended -nopause -nosplash -nullrhi -log
```

- List the registered test names with `-ExecCmds="Automation List; Quit"`.
- The filter is a name **prefix**; join several with `+`. A filter matching nothing exits 255.
- UE ignores a custom `-log=<path>`; results go to `Saved/Logs/PCG_Claude.log`. Success looks like
  `Test Completed. Result={Success}` and `**** TEST COMPLETE. EXIT CODE: 0 ****`.
- If a plugin asserts under `-nullrhi`, add `-DisablePlugins=<Name>`. The project this was ported
  from needed `-DisablePlugins=Fab`; the Fab plugin is not enabled here, and a plain run needs no
  such flag.

## Key paths

| What | Path |
|------|------|
| Engine root | `E:\UnrealEngine` (source build) |
| Build.bat | `E:\UnrealEngine\Engine\Build\BatchFiles\Build.bat` |
| UnrealEditor.exe | `E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor.exe` |
| UnrealEditor-Cmd.exe | `E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor-Cmd.exe` |
| Project file | `E:\PCG_Claude\PCG_Claude.uproject` |
| MCP server | `mcp_server/` (tool: `run_unreal_script`) |
| UE Python scripts root | `Content\Python\` |
| Logs | `Saved\Logs\PCG_Claude.log` |
