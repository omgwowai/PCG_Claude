import json

from mcp_server.protocol import (
    build_run_frame,
    parse_frame,
    StdoutFrame,
    ResultFrame,
)


def test_build_run_frame_roundtrips_to_expected_json():
    text = build_run_frame("req-1", "scripts/spawn.py", {"actor": "Cube", "count": 3})
    obj = json.loads(text)
    assert obj == {
        "type": "run",
        "id": "req-1",
        "script_path": "scripts/spawn.py",
        "args": {"actor": "Cube", "count": 3},
    }


def test_build_run_frame_defaults_args_to_empty_object():
    obj = json.loads(build_run_frame("req-2", "a.py", None))
    assert obj["args"] == {}


def test_parse_stdout_frame():
    frame = parse_frame('{"type":"stdout","id":"x","data":"hi\\n"}')
    assert isinstance(frame, StdoutFrame)
    assert frame.id == "x"
    assert frame.data == "hi\n"


def test_parse_result_frame_success():
    frame = parse_frame(
        '{"type":"result","id":"x","ok":true,"return":{"n":1},"stdout":"out"}'
    )
    assert isinstance(frame, ResultFrame)
    assert frame.ok is True
    assert frame.return_value == {"n": 1}
    assert frame.stdout == "out"
    assert frame.error is None


def test_parse_result_frame_failure():
    frame = parse_frame(
        '{"type":"result","id":"x","ok":false,"error":"Traceback","stdout":"partial"}'
    )
    assert isinstance(frame, ResultFrame)
    assert frame.ok is False
    assert frame.error == "Traceback"
    assert frame.stdout == "partial"
    assert frame.return_value is None


def test_parse_frame_rejects_unknown_type():
    try:
        parse_frame('{"type":"bogus","id":"x"}')
    except ValueError as exc:
        assert "bogus" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_parse_frame_rejects_invalid_json():
    try:
        parse_frame("not json")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
