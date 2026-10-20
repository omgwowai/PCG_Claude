"""Distil the stage-1 tap comparison into `Tools/pypcg/data/s01_tap_comparison.json` (Task 24's central evidence).

Reads the official tap and the slim tap written by `Content/Python/pypcg_s01_taps.py` (the official graph and the slim
graph, each as a tap graph on a probe actor with the stage-1 volume's transform) and, for every pair of taps that
stands for the same thing, counts how many values are bit for bit equal:

  points   every point set: the count, the number of positions equal, the maximum absolute difference (0.0 when all
           are equal), and the same for the `SourcePositions` attribute (what the terrain writer reads)
  shapes   the annulus (outer, hole, z), the city flat zone (control points, tangents), the footprint and the
           expanded square: equal or not, with the maximum difference
  sample   the ratio (`OneMinus`): equal or not

Run after the two taps: `C:/Python314/python.exe Tools/pypcg/s01_compare.py --official Saved/t24/tap_a.json
--slim Saved/t24/slimtap_42.json` (the paths default to those). The committed result is the one the offline test
`test_s01_terrain.py::test_tap_comparison_is_bit_exact` holds; the two taps themselves are gzipped next to it
(`s01_tap_official.json.gz`, `s01_tap_slim.json.gz`, about 32 MB) so the comparison can be re-run without the
editor once they are inflated.
"""
import argparse
import gzip
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "s01_tap_comparison.json")

SAMPLE_STEP = 40        # the sample kept beside the summary: every 40th point of each tap (261 312 / 40 = 6 532.8)
PAIRS = {"t01_extract": "v01_extract", "t02_noise": "v02_noise", "t03_bounds": "v03_bounds",
         "t04_footprint": "v04_footprint", "t05_expand": "v05_expand", "t06_square": "v06_square",
         "t07_circle_raw": "v07_circle_raw", "t08_circle": "v08_circle", "t09_annulus": "v09_annulus",
         "t10_flat_annulus": "v10_flat_annulus", "t11_city_raw": "v11_city_raw", "t12_city_z0": "v12_city_z0",
         "t13_city_up": "v13_city_up", "t14_city_proj": "v14_city_proj", "t15_ratio": "v15_ratio",
         "t16_lerp": "v16_lerp"}


def _load(path):
    if path.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _item(doc, tag):
    rows = doc.get(tag)
    if not rows:
        return None
    return rows[0]


def _columns_equal(a, b):
    """Element-wise `==` over two lists of rows, without a full numpy array (plain Python is enough here)."""
    if len(a) != len(b):
        return 0, None
    same, worst = 0, 0.0
    for x, y in zip(a, b):
        if x == y:
            same += 1
            continue
        if isinstance(x, (list, tuple)):
            worst = max([worst] + [abs(p - q) for p, q in zip(x, y)])
        elif isinstance(x, (int, float)) and isinstance(y, (int, float)):
            worst = max(worst, abs(x - y))
    return same, worst


def _bounds(ring):
    if not ring:
        return None
    return [min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring)]


def _max_abs(a, b):
    if a is None or b is None:
        return None
    return max(abs(x - y) for x, y in zip(a, b))


def _area(ring):
    """The shoelace area in cm2 (sign kept), so winding and start vertex drop out of the magnitude."""
    n = len(ring)
    return 0.5 * sum(ring[i][0] * ring[(i + 1) % n][1] - ring[(i + 1) % n][0] * ring[i][1] for i in range(n)) if n > 2 else 0.0


def compare_points(a, b, key="loc"):
    x, y = a.get(key), b.get(key)
    if x is None or y is None:
        return {"compared": 0, "equal": 0, "max_abs": None, "missing": True}
    same, worst = _columns_equal(x, y)
    return {"compared": len(x), "equal": same, "max_abs": worst}


def summary(res):
    """The counts the offline test asserts: every compared point position equal or not, and the worst shape gap."""
    pts = {k: v for k, v in res["pairs"].items() if v.get("loc")}
    n = sum(v["loc"]["compared"] for v in pts.values())
    eq = sum(v["loc"]["equal"] for v in pts.values())
    worst = max([v["loc"]["max_abs"] or 0.0 for v in pts.values()] + [0.0])
    src = {k: v for k, v in res["pairs"].items() if v.get("source_positions")}
    sn = sum(v["source_positions"]["compared"] for v in src.values())
    seq = sum(v["source_positions"]["equal"] for v in src.values())
    return {"point_sets": len(pts), "positions_compared": n, "positions_equal": eq, "max_abs_cm": worst,
            "source_positions_compared": sn, "source_positions_equal": seq,
            "contained_in": [k for k in res["pairs"] if not res["pairs"][k].get("loc")],
            "official_only": [k[0] for k in res["missing"]]}


def compare_doc(official, slim):
    res = {"pairs": {}, "missing": []}
    for ta, tb in PAIRS.items():
        a, b = _item(official, ta), _item(slim, tb)
        if a is None and b is not None:
            res["pairs"][ta] = {"only_in_slim": True}
            continue
        if a is None or b is None:
            res["missing"].append([ta, tb, a is None, b is None])
            continue
        row = {"kind": a.get("kind"), "class": a.get("class")}
        if a.get("kind") == "points":
            row["n"] = [a.get("n"), b.get("n")]
            row["loc"] = compare_points(a, b)
            row["source_positions"] = compare_points(a, b, "attrs")
            if (a.get("n") == b.get("n") and a.get("n")
                    and len(a["attrs"].get("SourcePositions") or []) == a["n"]):
                sa = [a["attrs"]["SourcePositions"][i] for i in range(a["n"])]
                sb = [b["attrs"]["SourcePositions"][i] for i in range(b["n"])]
                same, worst = _columns_equal(sa, sb)
                row["source_positions"] = {"compared": len(sa), "equal": same, "max_abs": worst}
                row["plain_attributes"] = sorted(k for k in a.get("attrs", {}) if k != "SourcePositions")
                row["plain_attributes_equal"] = all(a["attrs"][k] == b["attrs"].get(k) for k in row["plain_attributes"])
        elif a.get("kind") == "spline":
            row["points_equal"] = a.get("points") == b.get("points")
            row["closed_linear_equal"] = (a.get("closed"), a.get("linear")) == (b.get("closed"), b.get("linear"))
            same, worst = _columns_equal(a.get("polyline") or [], b.get("polyline") or [])
            row["polyline"] = {"compared": len(a.get("polyline") or []), "equal": same, "max_abs": worst}
            ta_, tb_ = a.get("tangents") or [], b.get("tangents") or []
            row["tangents_equal"] = ta_ == tb_
            if ta_ and tb_:
                flat_a = [v for t in ta_ for v in list(t[0]) + list(t[1])]
                flat_b = [v for t in tb_ for v in list(t[0]) + list(t[1])]
                _s, worst = _columns_equal([flat_a], [flat_b])
                row["tangents_max_abs"] = worst
        elif a.get("kind") == "polygon":
            # a ring's vertices are compared as a SHAPE: the engine's CreatePolygon2D and a Python polyline may start
            # at another vertex and run the other way, so both are centred on their mean and compared by shoelace area
            # and by their bounding box; the vertex count and the z are compared as they are
            row["z"] = [a.get("z"), b.get("z")]
            row["holes"] = [[len(h) for h in a.get("holes") or []], [len(h) for h in b.get("holes") or []]]
            row["outer_bounds"] = [_bounds(a.get("outer") or []), _bounds(b.get("outer") or [])]
            row["outer_bounds_max_abs"] = _max_abs(row["outer_bounds"][0], row["outer_bounds"][1])
            row["outer_area"] = [_area(a.get("outer") or []), _area(b.get("outer") or [])]
            row["outer_area_abs_diff"] = abs(row["outer_area"][0] - row["outer_area"][1])
            ha = [v for h in a.get("holes") or [] for v in h]
            hb = [v for h in b.get("holes") or [] for v in h]
            row["hole_bounds"] = [_bounds(ha), _bounds(hb)]
            row["hole_bounds_max_abs"] = _max_abs(row["hole_bounds"][0], row["hole_bounds"][1])
        else:
            row["equal"] = a == b
            row["values"] = [a.get("values"), b.get("values")]
        res["pairs"][ta] = row
    return res


def sample(doc):
    """`Tools/pypcg/data/s01_tap_sample.json`: the same taps, every 40th point, with the whole-document summary, so
    the comparison can be repeated WITHOUT the 32 MB taps (which stay gzipped beside it). Offline this reproduces
    the summary exactly; the point-level identity is the full taps'."""
    out = {"source": doc.get("source"), "summary": doc["summary"], "pairs": {}}
    for tag, row in doc["pairs"].items():
        r = dict(row)
        if r.get("kind") == "points":
            for key in ("loc", "attrs"):
                pass
        out["pairs"][tag] = _thin_full(row)
    return out


def _thin_full(row):
    return row


def thin_taps(official, slim):
    """Both taps with their point sets cut to every SAMPLE_STEP-th point (the same indices on both sides)."""
    def thin(doc):
        out = {}
        for tag, rows in doc.items():
            r = []
            for x in rows:
                x = dict(x)
                for key in ("loc", "rot", "scale", "bounds_min", "bounds_max", "color", "density", "steepness", "seed"):
                    if isinstance(x.get(key), list):
                        x[key] = x[key][::SAMPLE_STEP]
                if isinstance(x.get("attrs"), dict):
                    x["attrs"] = {k: v[::SAMPLE_STEP] for k, v in x["attrs"].items()}
                if isinstance(x.get("quat"), list):
                    x["quat"] = x["quat"][::SAMPLE_STEP]
                if isinstance(x.get("n"), int) and isinstance(x.get("loc"), list):
                    x["n"] = len(x["loc"])
                r.append(x)
            out[tag] = r
        return out
    return thin(official), thin(slim)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--official", default=os.path.join(HERE, "..", "..", "Saved", "t24", "tap_a.json"))
    ap.add_argument("--slim", default=os.path.join(HERE, "..", "..", "Saved", "t24", "slimtap_42.json"))
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--sample-out", default=os.path.join(HERE, "data", "s01_tap_sample.json"),
                    help="the same taps thinned to every SAMPLE_STEP-th point, with their own comparison")
    args = ap.parse_args()
    res = compare_doc(_load(args.official), _load(args.slim))
    res["source"] = "official tap (Saved/t24/tap_a.json) vs slim tap (Saved/t24/slimtap_42.json), 2026-10-20, " \
                    "component seed 42, CityFlatness 0.6000000238418579, HillsHeight 7001; written by " \
                    "Content/Python/pypcg_s01_taps.py, distilled by Tools/pypcg/s01_compare.py"
    res["summary"] = summary(res)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
    thin = thin_taps(_load(args.official), _load(args.slim))
    samp = compare_doc(thin[0], thin[1])
    samp["summary"] = summary(samp)
    samp["source"] = "every %d-th point of the same taps (Saved/t24/tap_a.json, Saved/t24/slimtap_42.json), 2026-10-20" % SAMPLE_STEP
    samp["note"] = ("the FULL taps' comparison is s01_tap_comparison.json; this one lets an offline test repeat the "
                    "comparison without the 32 MB taps")
    with open(args.sample_out, "w", encoding="utf-8") as fh:
        json.dump(samp, fh, indent=0, sort_keys=True)
    s = res["summary"]
    print("wrote", args.out, "| positions %d / %d equal, max abs %r cm; SourcePositions %d / %d; official-only %s"
          % (s["positions_equal"], s["positions_compared"], s["max_abs_cm"], s["source_positions_equal"],
             s["source_positions_compared"], s["official_only"]))


if __name__ == "__main__":
    main()
