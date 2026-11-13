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
  MeshTerrainMode, ToolsetRegistry, SeasonalWeather.
- Git remote: `https://github.com/omgwowai/PCG_Claude.git` (branch `main`).
- The project has **PCG content of its own**: `Content/PyPCG/` (the PyPCG slim and town graphs and the
  generated town `L_PyTown`) and `Content/PCGArea/` (the small-area levels). The City Sample graphs and
  art come from the migrated `CitySamplePCG` plugin (`Plugins/CitySamplePCG/`, content gitignored).

The gameplay code is stock Epic template code; treat it as upstream behavior to extend rather than
rewrite. The bespoke additions are the MCP bridge toolchain ("Driving the editor" below), the
`PyPCGTools` C++ plugin, the `pypcg` Python package (see the **PyPCG** paragraph below), the
migrated `CitySamplePCG` plugin, the `SeasonalWeather` C++ plugin (see the **SeasonalWeather**
paragraph below), and the City Sample sky / weather / cloud scripts (see the **City Sample sky, weather and clouds**
paragraph below).

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

**SeasonalWeather** (spec: `docs/superpowers/specs/2026-11-02-seasonal-weather-design.md`; M0 plan:
`docs/superpowers/plans/2026-11-02-seasonal-weather-m0.md`). A four-season dynamic weather system after Atmos, the
weather system of Assassin's Creed Shadows, built in milestones (spec §9), of which M0, the skeleton, is done. The
project plugin `Plugins/SeasonalWeather` has three modules: `SeasonalWeatherShaders` (PostConfigInit: the global compute
shaders and their RDG passes), `SeasonalWeather` (runtime: the subsystem, calendar, astronomy, sky, GPU weather fields,
orchestrator and the `weather.*` console commands) and `SeasonalWeatherEditor` (the StateTree builders and the debug
panel `weather.Panel`). A world without an `AWeatherDomain` actor does nothing, and in the editor world the clock stands
still unless `SetRunInEditor(true)`. The calendar, astronomy, sky-rig and field-size formulas have Python twins in
`Tools/weather/weather_ref`, which reads the same parameter file as the C++, `Tools/weather/weather_params.json` (schema
`params_schema.json`); regenerate golden files with `Tools/weather/gen_golden.py` after changing either (the C++
`*.Golden` tests read `Tools/weather/golden`, and `test_weather_golden.py` fails while one is stale).
Driver: `Content/Python/weather.py`
(`assets / lab / set / advance / state / shot / scenario`, one phase per call, with `weather_assets.py` and
`weather_lab.py`); every phase but `assets` and `lab` refuses unless the lab is the current map. Plugin assets are
generated by `weather.py assets`; never edit them by hand. They are `MPC_Weather`, the star map `T_WeatherStars` and its
material `M_WeatherStars`, the 12 look data assets and the StateTrees `ST_WeatherType` / `ST_Season` under
`/SeasonalWeather`; `assets` imports the star map from the PNG that
`C:\Python314\python.exe Tools/weather/gen_starmap.py` writes, creates what is missing, updates the rest in place, and
never recreates the MPC, whose parameter GUIDs the materials store. `weather.py` always runs `assets` and `lab` deferred
(result in `Saved/Reports/weather/deferred.json`), because a direct bridge call that imports through Interchange crashes
the editor on TaskGraph's recursion guard, and `lab`'s level open / save may pump the task queue the same way. `shot`
writes `Saved/Screenshots/WindowsEditor/weather_<camera>_<tag>.png` asynchronously (a name used before gets `_rN`, and
the result's `fired.claimed` names the file), and a pending shot fences `set`, `advance`, `scenario` and `shot` until
its capture lands (about 10 s; the marker
`Saved/Reports/weather/shot_pending.json` goes stale after 60 s). The lab `/Game/Weather/L_WeatherLab` (ground, slope,
house, the sky rig, the `AWeatherDomain` and the `WeatherCam_*` cameras, from `weather_lab.py`'s `LAYOUT`) is where the
weather is accepted before it goes into `L_PyWorld`; `lab` opens or creates it and refuses while a big level is open
(traps 79, 83). `scenario {"name": "m0_look"}` is the M0 acceptance: 15 checks against `Tools/weather/thresholds.json`,
reported in `Saved/Reports/weather/m0_look.json`. The C++ automation needs `-RenderOffScreen`, not `-nullrhi`, because
its GPU tests (`SeasonalWeather.Gpu.Fields`, `SeasonalWeather.Subsystem.Fields`) read the fields back from the GPU.

**City Sample sky, weather and clouds** (reports `docs/citysample-clear-sky-renderdoc.html`,
`citysample-weather-presets.html`, `citysample-cloud-art.html`, `citysample-cloud-motion.html`; cloud-motion spec / plan
`docs/superpowers/{specs,plans}/2026-11-12-cs-cloud-motion*`). Looks for the demo level
`/CitySamplePCG/Levels/L_CitySamplePCG_Demo`, applied **in memory only**: the demo level is never saved, and every session
ends with `Content/Python/cs_weather.py {"phase": "restore", "to": "original"}` (puts the snapshotted originals back, deletes
the helper actors, clears the level packages' dirty flags, turns autosave back on). `cs_clear_sky.py apply` is the 10:00
base look; `cs_weather.py` (`apply / state / cams / shoot / restore / run / batch / prefs`) applies the 11 photo presets
(`cs_weather_presets.py`) and the 10 art-directed cloud weathers (`cs_weather_art.py`), every value `[value, why]`. The
cloud material `/Game/CitySampleSky/M_CS_CumulusCloud` is generated: `cs_cloud_code.py` writes its Custom HLSL (two
parameter slots A / `B_`, absolute altitude, time inputs; `Tools/cs_weather/hlsl_check.py` compiles it offline with the
engine's DXC) and `cs_sky_assets.py {"phase": "material"}` builds it -- only with the startup map open, deferred, result in
`Saved/Reports/cs_weather/assets_result.json` (trap 136: never rerun on a lost reply). The cloud director
`cs_cloud_director.py` (`play / pause / resume / speed / seek / to / state / stop / record`; editor side `cs_cloud_rt.py`,
pure model `cs_cloud_motion.py`) animates the clouds and blends preset to preset through one MaterialInstanceDynamic; a
manual `apply` stops it, `apply` / `shoot` / `batch` refuse while it records. Recording, encoding and checks:
`Tools/cs_weather/` (`encode_clips.py`, `motion_check.py`, `stills_check.py`, `regress_shots.py`, `perf_summary.py`);
working notes and measurements in `Saved/Reports/cs_cloud_motion/notes.md`. Traps 132-151.

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
- Building another project on `E:\UnrealEngine` can renew the engine's BuildId, after which this
  project's modules count as out of date (`Skipping out-of-date modules in manifest` in the log) and
  the editor will not start until a full `PCG_ClaudeEditor` build restamps them (the command above
  as written: a build limited with `-Module=A+B` stamps nothing). To check, compare `"BuildId"` in
  `E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor.modules` with this project's
  `Binaries\Win64\UnrealEditor.modules`. A build here that runs UHT can strand the other project the
  same way: UHT can rewrite the engine's `NetCore.init.gen.cpp` with another hash (cause unknown; this
  project's own builds have written both values), which relinks NetCore and renews the BuildId.
- A missing `E:\UnrealEngine\Engine\Source\ThirdParty\Intel\ISPC\bin\Windows\ispc.exe` (the build
  fails with `No ISPC compiler at ...`) is restored with
  `E:\UnrealEngine\Engine\Binaries\DotNET\GitDependencies\win-x64\GitDependencies.exe` in its default
  mode, which adds the missing files and leaves locally modified ones alone.

## Tests

Six suites:

| Suite | Runs | Baseline |
|---|---|---|
| `pypcg` (Python form of the 18 stage graphs, PyWorld and PyInterior, offline) | `C:\Python314\python.exe -m pytest Tools/pypcg/tests -q` | 2094 passed, 18 skipped (the skips are the per-node reference drafts' step check) |
| `weather` (the SeasonalWeather reference model, golden files, scenarios and the lab's big-level refusal, offline) | `C:\Python314\python.exe -m pytest Tools/weather/tests -q` | 38 passed |
| `cs_weather` (City Sample presets resolver, cloud material code, cloud motion model, clip and perf tools, offline) | `C:\Python314\python.exe -m pytest Tools/cs_weather/tests -q` | 105 passed |
| `PyPCGTools` C++ automation | command below; needs **both** editors (this one and `E:\PCG_Codex`) closed | 9 tests, all `Result={Success}`, exit 0 |
| `SeasonalWeather` C++ automation | second command below (`-RenderOffScreen` instead of `-nullrhi`); needs **both** editors closed | 22 tests, all `Result={Success}`, exit 0 |
| MCP server | `.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests -q` | 17 passed |

- `pypcg`, `weather` and `cs_weather` run on system Python 3.14 because the MCP venv lacks Pillow (and numpy,
  which `weather` and `cs_weather` also need).
  `C:\Python314\python.exe Tools/pypcg/baseline.py check` checks that the official CitySample assets
  under `Plugins/CitySamplePCG/Content` keep their recorded mtime and size.
- One MCP test: `... -m pytest mcp_server/tests/test_protocol.py::test_build_run_frame_roundtrips_to_expected_json -q`.
- The C++ tests live in `Plugins/PyPCGTools/Source/PyPCGTools/Private/Tests/` and in `Private/Tests/`
  of the `SeasonalWeather` and `SeasonalWeatherEditor` modules (`Plugins/SeasonalWeather/Source/`).
  The game module `PCG_Claude` registers none, so a `PCG_Claude` filter matches nothing and exits
  **255**.

The UE automation harness runs engine or in-editor tests headlessly (verified with the engine
self-test filter `System.Core.Algo`; swap the filter for `PyPCGTools` to run the plugin's tests). The
second line runs `SeasonalWeather`, whose GPU tests need `-RenderOffScreen` instead of `-nullrhi`:

```powershell
& "E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "E:\PCG_Claude\PCG_Claude.uproject" -ExecCmds="Automation RunTests PyPCGTools; Quit" -unattended -nopause -nosplash -nullrhi -log
& "E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "E:\PCG_Claude\PCG_Claude.uproject" -ExecCmds="Automation RunTests SeasonalWeather; Quit" -unattended -nopause -nosplash -RenderOffScreen -log
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
