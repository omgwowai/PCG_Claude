#!/usr/bin/env python
"""sa_extract_inventory.py — pull `data.inventory` out of a bridge tool-result file.

The bridge returns the script's output as one big JSON blob, which also gets
saved to a tool-results file when it is too large to print. This reads that file
and writes the inventory to a plain JSON file, so the level's baseline geometry
is on disk and can be diffed after the transform runs.

    python Tools/sa_extract_inventory.py \\
        --tool-result <path to the tool-results .txt> \\
        --out Saved/Reports/sa_inventory.json
"""

import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def payload_from_tool_result(text):
    """The bridge wraps the script output as {"result": "Script succeeded.\\n..."}.

    Inside that string the script's last print is a JSON object; take the widest
    brace-balanced span that parses.
    """
    outer = json.loads(text)
    inner = outer.get("result", text) if isinstance(outer, dict) else text
    start = inner.find("{")
    if start < 0:
        raise ValueError("no JSON object in the tool result")
    # try the widest span first, then shrink from the right
    for end in range(len(inner), start, -1):
        if inner[end - 1] != "}":
            continue
        try:
            return json.loads(inner[start:end])
        except Exception:
            continue
    raise ValueError("no parseable JSON object in the tool result")


def inventory_of(payload):
    """Accept either the whole {"ok","data":{...}} envelope or the data itself."""
    if isinstance(payload, dict) and "data" in payload:
        data = payload["data"]
    else:
        data = payload
    if not isinstance(data, dict) or "inventory" not in data:
        raise KeyError("payload has no data.inventory")
    return data["inventory"]


def summarise(inv):
    n_components = 0
    n_points = 0
    pts = []
    for a in inv.get("spline_actors", []):
        for sp in a.get("splines", []):
            n_components += 1
            n_points += len(sp.get("points", []))
            pts.extend(sp.get("points", []))
    bbox = None
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        bbox = {"min": [min(xs), min(ys), min(zs)],
                "max": [max(xs), max(ys), max(zs)]}
    return {
        "spline_actors": len(inv.get("spline_actors", [])),
        "spline_components": n_components,
        "spline_points": n_points,
        "volumes": len(inv.get("volumes", [])),
        "cameras": len(inv.get("cameras", [])),
        "terrain": len(inv.get("terrain", [])),
        "union_bbox": bbox,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool-result", required=True)
    ap.add_argument("--out", default=os.path.join(REPO, "Saved", "Reports",
                                                  "sa_inventory.json"))
    args = ap.parse_args()

    p = args.tool_result
    if not os.path.isabs(p):
        p = os.path.join(REPO, p)
    with open(p, encoding="utf-8") as fh:
        text = fh.read()

    payload = payload_from_tool_result(text)
    inv = inventory_of(payload)

    out = args.out if os.path.isabs(args.out) else os.path.join(REPO, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(inv, fh, indent=1, ensure_ascii=False)

    s = summarise(inv)
    print("wrote %s" % out)
    print("spline actors   : %d" % s["spline_actors"])
    print("spline components: %d" % s["spline_components"])
    print("spline points   : %d" % s["spline_points"])
    print("volumes/cameras/terrain: %d / %d / %d"
          % (s["volumes"], s["cameras"], s["terrain"]))
    if s["union_bbox"]:
        print("union bbox      : %s .. %s" % (s["union_bbox"]["min"], s["union_bbox"]["max"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
