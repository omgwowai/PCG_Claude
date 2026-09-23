import asyncio
import json

import pytest
import websockets

from mcp_server.bridge import UnrealBridge, BridgeNotConnected


async def _start_fake_ue(handler):
    """Start a fake UE WebSocket server on an ephemeral port. Returns (server, port)."""
    server = await websockets.serve(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port


async def test_run_script_returns_result_on_success():
    async def handler(ws):
        async for message in ws:
            req = json.loads(message)
            assert req["type"] == "run"
            rid = req["id"]
            await ws.send(json.dumps({"type": "stdout", "id": rid, "data": "line1\n"}))
            await ws.send(json.dumps(
                {"type": "result", "id": rid, "ok": True,
                 "return": {"spawned": 3}, "stdout": "line1\n"}
            ))

    server, port = await _start_fake_ue(handler)
    bridge = UnrealBridge("127.0.0.1", port)
    await bridge.connect()
    try:
        result = await bridge.run_script("scripts/spawn.py", {"count": 3})
        assert result.ok is True
        assert result.return_value == {"spawned": 3}
        assert "line1" in result.stdout
    finally:
        await bridge.close()
        server.close()
        await server.wait_closed()


async def test_run_script_surfaces_failure_result():
    async def handler(ws):
        async for message in ws:
            rid = json.loads(message)["id"]
            await ws.send(json.dumps(
                {"type": "result", "id": rid, "ok": False,
                 "error": "Traceback: boom", "stdout": ""}
            ))

    server, port = await _start_fake_ue(handler)
    bridge = UnrealBridge("127.0.0.1", port)
    await bridge.connect()
    try:
        result = await bridge.run_script("bad.py", {})
        assert result.ok is False
        assert "boom" in result.error
    finally:
        await bridge.close()
        server.close()
        await server.wait_closed()


async def test_concurrent_calls_are_routed_by_id():
    async def handler(ws):
        async for message in ws:
            req = json.loads(message)
            rid = req["id"]
            # Echo the script path back so we can assert correlation.
            await ws.send(json.dumps(
                {"type": "result", "id": rid, "ok": True,
                 "return": req["script_path"], "stdout": ""}
            ))

    server, port = await _start_fake_ue(handler)
    bridge = UnrealBridge("127.0.0.1", port)
    await bridge.connect()
    try:
        results = await asyncio.gather(
            bridge.run_script("a.py", {}),
            bridge.run_script("b.py", {}),
            bridge.run_script("c.py", {}),
        )
        returns = {r.return_value for r in results}
        assert returns == {"a.py", "b.py", "c.py"}
    finally:
        await bridge.close()
        server.close()
        await server.wait_closed()


async def test_run_without_connection_raises():
    bridge = UnrealBridge("127.0.0.1", 1)  # nothing listening
    with pytest.raises(BridgeNotConnected):
        await bridge.run_script("a.py", {})


async def test_unknown_frame_does_not_break_pending_call():
    async def handler(ws):
        async for message in ws:
            rid = json.loads(message)["id"]
            # Send a frame the protocol does not understand, then the real result.
            await ws.send(json.dumps({"type": "heartbeat", "id": rid}))
            await ws.send(json.dumps(
                {"type": "result", "id": rid, "ok": True, "return": 42, "stdout": ""}
            ))

    server, port = await _start_fake_ue(handler)
    bridge = UnrealBridge("127.0.0.1", port)
    await bridge.connect()
    try:
        result = await bridge.run_script("a.py", {})
        assert result.ok is True
        assert result.return_value == 42
    finally:
        await bridge.close()
        server.close()
        await server.wait_closed()


async def test_disconnect_midflight_fails_pending_call():
    async def handler(ws):
        # Read one request, then drop the connection without replying.
        await ws.recv()
        await ws.close()

    server, port = await _start_fake_ue(handler)
    bridge = UnrealBridge("127.0.0.1", port)
    await bridge.connect()
    try:
        with pytest.raises(BridgeNotConnected):
            await bridge.run_script("a.py", {})
    finally:
        await bridge.close()
        server.close()
        await server.wait_closed()
