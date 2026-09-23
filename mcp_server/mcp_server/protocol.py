"""Pure (de)serialization of the WebSocket bridge protocol. No I/O."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


def build_run_frame(req_id: str, script_path: str, args: Any) -> str:
    """Serialize a 'run' request frame to JSON text."""
    return json.dumps(
        {
            "type": "run",
            "id": req_id,
            "script_path": script_path,
            "args": args if args is not None else {},
        }
    )


@dataclass
class StdoutFrame:
    id: str
    data: str


@dataclass
class ResultFrame:
    id: str
    ok: bool
    stdout: str = ""
    return_value: Any = None
    error: str | None = None


def parse_frame(text: str) -> StdoutFrame | ResultFrame:
    """Parse a JSON text frame from UE into a typed frame object.

    Raises ValueError on invalid JSON or unknown frame type.
    """
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON frame: {exc}") from exc

    frame_type = obj.get("type")
    if frame_type == "stdout":
        return StdoutFrame(id=obj["id"], data=obj.get("data", ""))
    if frame_type == "result":
        return ResultFrame(
            id=obj["id"],
            ok=bool(obj.get("ok", False)),
            stdout=obj.get("stdout", ""),
            return_value=obj.get("return"),
            error=obj.get("error"),
        )
    raise ValueError(f"unknown frame type: {frame_type!r}")
