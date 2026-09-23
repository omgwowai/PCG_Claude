# Unreal MCP Server

Standalone MCP server. Exposes one tool, `run_unreal_script`, which forwards to a
running Unreal Engine editor (with the `UnrealMcpBridge` plugin enabled) over
WebSocket and runs a `.py` script in UE's embedded Python interpreter.

## Install

```bash
cd mcp_server
python -m venv .venv
. .venv/Scripts/activate   # PowerShell: .venv\Scripts\Activate.ps1
pip install -e .
```

## Configuration

Environment variables (defaults match the UE plugin):

- `UE_MCP_HOST` (default `127.0.0.1`)
- `UE_MCP_PORT` (default `8777`)

## Register with an MCP client

Example stdio entry (Claude Desktop / Claude Code `mcp` config):

```json
{
  "mcpServers": {
    "unreal": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "env": { "UE_MCP_PORT": "8777" }
    }
  }
}
```

Use the venv's Python in `command` if not on PATH.

## Tool

`run_unreal_script(script_path, args)`
- `script_path`: path to a `.py` file relative to the UE scripts root
  (default `<Project>/Content/Python/`).
- `args`: JSON object exposed to the script as the global `mcp_args`.
- The script may set `mcp_result` to return structured JSON data.
