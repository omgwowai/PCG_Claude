"""WebSocket client to the UE plugin. Correlates requests/responses by id."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import websockets

from .protocol import build_run_frame, parse_frame, ResultFrame, StdoutFrame

logger = logging.getLogger(__name__)


class BridgeNotConnected(Exception):
    """Raised when the UE editor is not reachable or drops mid-call."""


class UnrealBridge:
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._ws = None
        self._connected = False
        self._pending: dict[str, asyncio.Future] = {}
        self._stdout: dict[str, list[str]] = {}
        self._reader_task: asyncio.Task | None = None

    @property
    def url(self) -> str:
        return f"ws://{self._host}:{self._port}"

    async def connect(self) -> None:
        """Connect to the UE WS server and start the read loop. Raises on failure."""
        try:
            self._ws = await websockets.connect(self.url)
        except OSError as exc:
            raise BridgeNotConnected(
                f"Unreal editor not connected on {self._host}:{self._port}"
            ) from exc
        self._connected = True
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for message in self._ws:
                try:
                    frame = parse_frame(message)
                except ValueError:
                    # Malformed/unknown frame: skip it without tearing down the
                    # connection or failing in-flight calls.
                    logger.warning("ignoring unparseable frame from Unreal editor")
                    continue
                if isinstance(frame, StdoutFrame):
                    self._stdout.setdefault(frame.id, []).append(frame.data)
                elif isinstance(frame, ResultFrame):
                    future = self._pending.pop(frame.id, None)
                    if future and not future.done():
                        if not frame.stdout:
                            frame.stdout = "".join(self._stdout.get(frame.id, []))
                        self._stdout.pop(frame.id, None)
                        future.set_result(frame)
        except websockets.ConnectionClosed:
            # Genuine teardown: pending calls are failed in the finally block.
            logger.debug("Unreal editor connection closed")
        except Exception:
            # Final safety net: log so real bugs are not silently swallowed.
            logger.exception("unexpected error in bridge read loop")
        finally:
            self._connected = False
            self._fail_all()

    def _fail_all(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(
                    BridgeNotConnected("Unreal editor connection closed mid-call")
                )
        self._pending.clear()
        self._stdout.clear()

    async def run_script(self, script_path: str, args: Any) -> ResultFrame:
        """Send a run request and await the terminal result frame."""
        if not self._connected:
            await self.connect()
        if not self._connected or self._ws is None:
            raise BridgeNotConnected(
                f"Unreal editor not connected on {self._host}:{self._port}"
            )

        req_id = uuid.uuid4().hex
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        try:
            await self._ws.send(build_run_frame(req_id, script_path, args))
        except Exception as exc:
            self._pending.pop(req_id, None)
            raise BridgeNotConnected("failed to send to Unreal editor") from exc
        return await future

    async def close(self) -> None:
        self._connected = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
