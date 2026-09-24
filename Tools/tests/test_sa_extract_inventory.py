import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import sa_extract_inventory as X


def _wrap(inner_text):
    """The bridge wraps the script output in {"result": "Script succeeded...."}."""
    return json.dumps({"result": inner_text})


def test_payload_is_read_out_of_the_bridge_envelope():
    inner = ("Script succeeded.\n\nstdout:\n" +
             json.dumps({"ok": True, "data": {"inventory": {"volumes": [1, 2]}}}) +
             "\n\nreturn:\n{...}")
    got = X.payload_from_tool_result(_wrap(inner))
    assert got["data"]["inventory"]["volumes"] == [1, 2]


def test_payload_survives_braces_inside_string_values():
    # A volume label with a brace must not truncate the parse.
    inner = json.dumps({"ok": True,
                        "data": {"inventory": {"volumes": [{"label": "a{b}"}]}}})
    got = X.payload_from_tool_result(_wrap("stdout:\n" + inner))
    assert got["data"]["inventory"]["volumes"][0]["label"] == "a{b}"


def test_inventory_of_accepts_both_the_envelope_and_the_bare_data():
    inv = {"volumes": [], "cameras": []}
    assert X.inventory_of({"ok": True, "data": {"inventory": inv}}) is inv
    assert X.inventory_of({"inventory": inv}) is inv


def test_inventory_of_rejects_a_payload_without_one():
    try:
        X.inventory_of({"ok": True, "data": {}})
    except KeyError:
        return
    raise AssertionError("expected KeyError")


def test_summarise_counts_splines_and_unions_their_bbox():
    inv = {"spline_actors": [
        {"splines": [{"points": [[0.0, 0.0, 0.0], [10.0, 10.0, 0.0]]}]},
        {"splines": [{"points": [[-5.0, 20.0, 3.0]]}]},
    ], "volumes": [1, 2, 3], "cameras": [1], "terrain": [1]}
    s = X.summarise(inv)
    assert s["spline_actors"] == 2
    assert s["spline_components"] == 2
    assert s["spline_points"] == 3
    assert s["union_bbox"]["min"] == [-5.0, 0.0, 0.0]
    assert s["union_bbox"]["max"] == [10.0, 20.0, 3.0]
    assert (s["volumes"], s["cameras"], s["terrain"]) == (3, 1, 1)


def test_summarise_of_an_empty_inventory_has_no_bbox():
    s = X.summarise({"spline_actors": []})
    assert s["spline_points"] == 0
    assert s["union_bbox"] is None
