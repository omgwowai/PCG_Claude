"""MCP server exposing a single tool that runs scripts in the UE editor."""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

from .bridge import UnrealBridge, BridgeNotConnected
from .protocol import ResultFrame


def format_tool_output(frame: ResultFrame) -> str:
    """Render a ResultFrame into human/LLM-readable tool output text."""
    if not frame.ok:
        parts = ["Script failed."]
        if frame.stdout:
            parts.append(f"stdout:\n{frame.stdout}")
        parts.append(f"error:\n{frame.error or 'unknown error'}")
        return "\n\n".join(parts)

    parts = ["Script succeeded."]
    if frame.stdout:
        parts.append(f"stdout:\n{frame.stdout}")
    if frame.return_value is not None:
        parts.append("return:\n" + json.dumps(frame.return_value, indent=2))
    return "\n\n".join(parts)


async def handle_run_unreal_script(bridge, script_path: str, args) -> str:
    """Core tool logic, separated from FastMCP wiring for testability."""
    try:
        frame = await bridge.run_script(script_path, args or {})
    except BridgeNotConnected as exc:
        return str(exc)
    return format_tool_output(frame)


def build_app() -> FastMCP:
    host = os.environ.get("UE_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("UE_MCP_PORT", "8777"))
    bridge = UnrealBridge(host, port)
    app = FastMCP("unreal-mcp")

    @app.tool()
    async def run_unreal_script(script_path: str, args: dict | None = None) -> str:
        """Run a Python script inside the Unreal Engine editor.

        script_path: path to a .py file, relative to the UE scripts root
                     (default <Project>/Content/Python/).
        args:        JSON object exposed to the script as the global `mcp_args`.
        """
        return await handle_run_unreal_script(bridge, script_path, args)

    return app


def main() -> None:
    build_app().run()  # stdio transport by default


if __name__ == "__main__":
    main()
