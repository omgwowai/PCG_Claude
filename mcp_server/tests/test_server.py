from mcp_server.protocol import ResultFrame
from mcp_server.bridge import BridgeNotConnected
from mcp_server.server import format_tool_output, handle_run_unreal_script


class FakeBridge:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls = []

    async def run_script(self, script_path, args):
        self.calls.append((script_path, args))
        if self._error:
            raise self._error
        return self._result


def test_format_success_with_return_value():
    frame = ResultFrame(id="x", ok=True, stdout="hello\n", return_value={"n": 1})
    text = format_tool_output(frame)
    assert "hello" in text
    assert "n" in text and "1" in text


def test_format_failure_includes_error():
    frame = ResultFrame(id="x", ok=False, stdout="", error="Traceback: boom")
    text = format_tool_output(frame)
    assert "boom" in text


async def test_handle_calls_bridge_and_formats():
    bridge = FakeBridge(
        result=ResultFrame(id="x", ok=True, stdout="out", return_value=None)
    )
    text = await handle_run_unreal_script(bridge, "scripts/a.py", {"k": "v"})
    assert bridge.calls == [("scripts/a.py", {"k": "v"})]
    assert "out" in text


async def test_handle_surfaces_not_connected_as_message():
    bridge = FakeBridge(error=BridgeNotConnected("Unreal editor not connected on 127.0.0.1:8777"))
    text = await handle_run_unreal_script(bridge, "a.py", {})
    assert "not connected" in text
