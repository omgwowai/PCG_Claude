# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

- **PCG_Claude** — Unreal Engine **5.8** C++ project, a third-person template plus three
  self-contained gameplay variants (Combat, Platforming, SideScrolling).
- Engine: **`E:\UnrealEngine`** — a **source build** of UE 5.8.2. `EngineAssociation` in
  `PCG_Claude.uproject` is that build's registry GUID `{4B303DEF-4E44-1DE5-A177-09B23BCA8A5A}`.
- Game module: `PCG_Claude` (Runtime). Plugins enabled: ModelingToolsEditorMode, StateTree,
  GameplayStateTree, PythonScriptPlugin, UnrealMcpBridge.
- Git remote: `https://github.com/omgwowai/PCG_Claude.git` (branch `main`).
- **Despite the name, the PCG (Procedural Content Generation) framework is not used** — the PCG
  plugin is not enabled, and there is no PCG graph or component anywhere in `Source/` or `Content/`.

Almost all game code is stock Epic template code. The only bespoke addition is the MCP bridge
toolchain described under "Driving the editor" below; treat the rest as upstream template
behavior to extend rather than rewrite.

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

**This project registers no C++ automation tests.** `Source/` contains no
`IMPLEMENT_*_AUTOMATION_TEST`, so a filter like `Automation RunTests PCG_Claude` matches nothing and
exits **255** with `No automation tests matched 'PCG_Claude'`. Add tests under `Source/PCG_Claude/`
wrapped in `#if WITH_DEV_AUTOMATION_TESTS` before that filter means anything.

The tests that do exist cover the MCP server. Run them against the project venv from the repo root:

```powershell
# whole suite
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests -q

# one file, or one test
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_protocol.py -q
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_protocol.py::test_build_run_frame_roundtrips_to_expected_json -q
```

The UE automation harness itself works and is how you run engine or in-editor tests headlessly.
Verified against an engine self-test (`System.Core.Algo.Unique` to `Result={Success}`, exit 0):

```powershell
& "E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "E:\PCG_Claude\PCG_Claude.uproject" -ExecCmds="Automation RunTests System.Core.Algo; Quit" -unattended -nopause -nosplash -nullrhi -log
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
