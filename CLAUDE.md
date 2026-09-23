# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

- **PCG_Claude** — Unreal Engine **5.8** C++ project (third-person template + Variant_Combat / Variant_Platforming / Variant_SideScrolling).
- Engine: **`E:\UnrealEngine`** — a **source build** of UE 5.8.2. `EngineAssociation` in `PCG_Claude.uproject` is that build's registry GUID `{4B303DEF-4E44-1DE5-A177-09B23BCA8A5A}`.
- Primary game module: `PCG_Claude` (Runtime). Plugins enabled: ModelingToolsEditorMode, StateTree, GameplayStateTree, **PythonScriptPlugin**, **UnrealMcpBridge**.
- Git remote: `https://github.com/omgwowai/PCG_Claude.git`.

## Driving the editor from Claude (MCP bridge)

`UnrealMcpBridge` (under `Plugins/`) hosts a localhost WebSocket server inside the
running editor; the Python MCP server at `mcp_server/` exposes it as one tool,
`run_unreal_script`, which executes a `.py` file from `Content/Python/` in the
editor's embedded Python interpreter.

- **Port `8777`** (host `127.0.0.1`) — deliberately *not* the source project's `8765`, so the two editors can run side by side. The port is set in three places that must agree:
  - `Plugins/UnrealMcpBridge/Source/UnrealMcpBridge/Public/UnrealMcpBridgeSettings.h` (`Port`, and overridable per-user in `Saved/Config/WindowsEditor/Editor.ini` under `[/Script/UnrealMcpBridge.UnrealMcpBridgeSettings]`)
  - `.mcp.json` → `env.UE_MCP_PORT`
  - `mcp_server/mcp_server/server.py` (`UE_MCP_PORT` default)
- Scripts must live under `Content/Python/` (the scripts root); the bridge rejects paths that escape it.
- Python env: `mcp_server/.venv` (Python 3.14). Recreate with
  `python -m venv mcp_server/.venv` then `mcp_server/.venv/Scripts/python.exe -m pip install -e mcp_server`.
- **Workflow skill: `.claude/skills/driving-unreal-via-mcp/`** — read it before any UE editor task. Core discipline: introspect the `unreal` API at runtime, never write from memory.

If a tool call returns `Unreal editor not connected on 127.0.0.1:8777`, the editor is not
running with the plugin loaded — ask the user to launch it rather than retrying.

## Key Paths

| What | Path |
|------|------|
| Engine root | `E:\UnrealEngine` (source build) |
| Build.bat | `E:\UnrealEngine\Engine\Build\BatchFiles\Build.bat` |
| UnrealEditor.exe | `E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor.exe` |
| UnrealEditor-Cmd.exe | `E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor-Cmd.exe` |
| Project file | `E:\PCG_Claude\PCG_Claude.uproject` |
| MCP server | `mcp_server/` (tool: `run_unreal_script`) |
| UE Python scripts root | `Content\Python\` |

## Build

Compile the **editor** target (game module + all plugin modules):

```powershell
& "E:\UnrealEngine\Engine\Build\BatchFiles\Build.bat" PCG_ClaudeEditor Win64 Development -Project="E:\PCG_Claude\PCG_Claude.uproject" -WaitMutex
```

- Success = exit code 0 and `Result: Succeeded` / `Total execution time: N seconds` with no errors.
- Use the **game** target name `PCG_Claude` instead of `PCG_ClaudeEditor` for a packaged/runtime build.
- UBT auto-discovers new `.cpp`/`.h` files in already-globbed module directories, so adding source files does not require regeneration — just run `Build.bat`. Regenerate IDE project files only after adding/removing files or modules:
  ```powershell
  & "E:\UnrealEngine\GenerateProjectFiles.bat"
  ```

## Run tests (headless, no GPU)

```powershell
& "E:\UnrealEngine\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "E:\PCG_Claude\PCG_Claude.uproject" -ExecCmds="Automation RunTests PCG_Claude; Quit" -unattended -nopause -nosplash -nullrhi -log
```

- The filter is a name **prefix** and must match a registered test; a filter matching nothing exits **255** with `No automation tests matched '<x>'`. List registered names with `-ExecCmds="Automation List; Quit"`.
- Logs land in `Saved/Logs/PCG_Claude.log`. `**** TEST COMPLETE. EXIT CODE: 0 ****` = all passed.
