"""Stage 12 (Task 21): the Python steps against the OFFICIAL intermediates, offline.

Reads the taps `Content/Python/pypcg_s12_measure.py` wrote (`Saved/t21/tap_<label>.json`, default `a`: the official
graph on the demo level at component seed 42) and compares, bit for bit:

  - the class split and the three Filter_Areas_BySize splits (each official polygon against the port's polygon of
    the same rooftop: frame, stored ring, ToPoint vertices, in the official order);
  - the Average z (`@data.height`) of every large rooftop above 500 m2, and the 70 m split;
  - Subgraph_8 / Subgraph_10's offset polygons (the frame and the ToPoint vertices MakePolygon2DData will give the
    port's polygon) and Subgraph_8's offset splines (control points);
  - the point difference on the official fitting nodes' points (Subgraph_7 less Subgraph_2) against Subgraph_12.

  C:/Python314/python.exe Tools/pypcg/s12_measure_offline.py [label] [--write]

`--write` stores the summary in `Tools/pypcg/data/s12_official_measurements.json` (key `offline_against_official_taps`).
"""
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "Content", "Python"))

from pypcg.geo import Points, Spline  # noqa: E402
from pypcg.geo import frames as F  # noqa: E402
from pypcg.stages import s12_rooftops as S  # noqa: E402
from pypcg.stages import s12_rooftops_assemblies as A  # noqa: E402

DATA = os.path.join(REPO, "Tools", "pypcg", "data", "s12_official_measurements.json")


def load(label):
    with open(os.path.join(REPO, "Saved", "t21", "tap_%s.json" % label), encoding="utf-8") as fh:
        return json.load(fh)


def spline_of(rec):
    ctrl = rec["raw"]["control"]
    return Spline([tuple(c["p"]) for c in ctrl], closed=rec["raw"]["closed"],
                  linear=all(c["type"] == 0 for c in ctrl),
                  frame=(tuple(rec["xf"]["t"]), tuple(rec["xf"]["q"]), tuple(rec["xf"]["s"])))


def points_of(rec):
    p = rec["points"]
    out = Points()
    for name, t in p["types"].items():
        out.declare(name, t)
    cols = p["cols"]
    for i in range(p["n"]):
        kw = {c: (tuple(cols[c][i]) if isinstance(cols[c][i], list) else cols[c][i]) for c in Points.DEFAULTS}
        kw.update({k: v[i] for k, v in p["attrs"].items()})
        out.add(tuple(cols["loc"][i]), **kw)
    out.quat = [tuple(q) for q in p["quat"]] if p["quat"] else None
    return out


def same_polygon(port_frame, port_vertices, rec):
    """(frame equal, vertices equal) against an official polygon tap record."""
    t, q = port_frame
    return (tuple(t) == tuple(rec["xf"]["t"]) and tuple(q) == tuple(rec["xf"]["q"]),
            [tuple(v) for v in port_vertices] == [tuple(v) for v in rec["vp"]])


def frame_of_written(poly):
    """What MakePolygon2DData gives the port's polygon: (frame, ToPoint vertices)."""
    zs = poly.zs if poly.zs is not None else [poly.z] * len(poly.outer)
    pts = [(x, y, z) for (x, y), z in zip(poly.outer, zs)]
    pos, _rot, frame = F.rebuilt_vertices(pts)
    return frame, pos


def main(label="a", write=False):
    t = load(label)
    items = [(spline_of(r), frozenset(r["tags"])) for r in t["T_roofs"]]
    t0 = time.perf_counter()
    out, counts, heights = S.rooftops(items)
    seconds = time.perf_counter() - t0
    res = {"tap": label, "counts": counts, "python_seconds_main": round(seconds, 3)}

    cls = S.by_class(items)
    s9 = S.by_size(cls["SmallRooftops"], 300.0)
    s6 = S.by_size(cls["MediumRooftops"], 800.0)
    s5 = S.by_size(cls["LargeRooftops"], 500.0)
    inside, outside, _h = S.by_height(s5[0])
    sets = {"T_s9sel": s9[0], "T_s9uns": s9[1], "T_s6sel": s6[0], "T_s6uns": s6[1], "T_s5sel": s5[0], "T_s5uns": s5[1],
            "T_inside": inside, "T_outside": outside}
    split = {}
    for tap, roofs in sets.items():
        recs = t.get(tap, [])
        frames = verts = 0
        for r, rec in zip(roofs, recs):
            f, v = same_polygon(r.poly.frame, r.poly.vertices, rec)
            frames += f
            verts += v
        split[tap] = {"official": len(recs), "port": len(roofs), "frame_equal": frames, "vertices_equal": verts}
    res["splits"] = split

    off_h = [r["rows"][0]["height"] for r in t.get("X_height", [])]
    res["heights"] = {"official": len(off_h), "port": len(heights),
                      "equal": sum(1 for a, b in zip(heights, off_h) if a == b),
                      "max_abs_diff": max((abs(a - b) for a, b in zip(heights, off_h)), default=0.0),
                      "above_7000": sum(1 for h in off_h if h > 7000.0),
                      "range": [min(off_h), max(off_h)] if off_h else None,
                      "nearest_to_7000_cm": min((abs(h - 7000.0) for h in off_h), default=None)}

    def offsets(pin, tap):
        recs = t.get(tap, [])
        port = out[pin]
        kinds = [type(v).__name__ for v, _t in port]
        off_kinds = ["Polygon" if r["class"] == "PCGPolygon2DData" else "Spline" for r in recs]
        frames = verts = ctrl = 0
        for (v, _tags), rec in zip(port, recs):
            if rec["class"] == "PCGPolygon2DData" and type(v).__name__ == "Polygon":
                f, vv = same_polygon(*frame_of_written(v), rec)
                frames += f
                verts += vv
            elif rec["class"] == "PCGSplineData" and type(v).__name__ == "Spline":
                ctrl += [tuple(p) for p in v.points] == [tuple(c["p"]) for c in rec["raw"]["control"]]
        return {"official": len(recs), "port": len(port), "same_kind_order": kinds == off_kinds,
                "polygons_frame_equal": frames, "polygons_vertices_equal": verts, "splines_equal": ctrl}
    res["offset_small"] = offsets("SmallAssemblyAreas", "T_off8")
    res["offset_skyscraper"] = offsets("SkyscraperAreas", "T_off20")

    # the official polygons each fitting node gets, against the rooftop the port forwards (its CreatePolygon2D)
    def forwarded(pin, taps):
        recs = [r for tap in taps for r in t.get(tap, [])]
        port = out[pin]
        frames = verts = 0
        for (v, _tags), rec in zip(port, recs):
            sp = F.SplinePolygon(v)
            f, vv = same_polygon(sp.frame, sp.vertices, rec)
            frames += f
            verts += vv
        return {"official": len(recs), "port": len(port), "frame_equal": frames, "vertices_equal": verts}
    res["wfc_inputs"] = forwarded("WfcAreas", ("T_s5uns", "T_s9sel", "T_outside"))
    res["vent_inputs"] = forwarded("VentAreas", ("T_s6uns", "T_s9uns"))

    # the point difference on the official fitting outputs
    wfc = [points_of(r) for r in t["T_fill7"]]
    small = [points_of(r) for r in t["T_fill2"]]
    t0 = time.perf_counter()
    kept, removed = A.difference(wfc, small)
    dsec = time.perf_counter() - t0
    off = [points_of(r) for r in t["T_diff"]]
    off_nonempty = [p for p in off if len(p)]
    same_items = len(kept) == len(off_nonempty)
    equal_items = 0
    if same_items:
        for a, b in zip(kept, off_nonempty):
            equal_items += (a.loc == b.loc and a.quat == b.quat and a.scale == b.scale
                            and a.bounds_min == b.bounds_min and a.attrs == b.attrs and a.seed == b.seed
                            and a.density == b.density)
    res["difference"] = {"wfc_points": sum(len(p) for p in wfc), "small_points": sum(len(p) for p in small),
                         "official_kept": sum(len(p) for p in off), "port_kept": sum(len(p) for p in kept),
                         "port_removed": removed, "official_items": len(off), "official_items_nonempty": len(off_nonempty),
                         "port_items": len(kept), "items_equal_field_for_field": equal_items,
                         "python_seconds": round(dsec, 2)}
    if write:
        doc = {}
        if os.path.exists(DATA):
            with open(DATA, encoding="utf-8") as fh:
                doc = json.load(fh)
        doc["offline_against_official_taps"] = res
        with open(DATA, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
    return res


def compare_slim(official="a", slim="slim", write=False):
    """The slim graph's taps (`pypcg_s12_measure.py` `"slim": true`) against the official ones, field for field: the
    areas the Python node writes into Subgraph_2 / Subgraph_3 as the engine holds them (frame, stored ring,
    ToPoint vertices; splines' control points), and every point the four kept fitting nodes and the difference
    node hand on (position, engine quaternion, scale, bounds, density, steepness, seed, colour, every attribute)."""
    o, s = load(official), load(slim)
    res = {"official_tap": official, "slim_tap": slim}
    for py_tap, off_tap in (("T_py_small", "T_off8"), ("T_py_sky", "T_off20")):
        a, b = s.get(py_tap, []), o.get(off_tap, [])
        same = 0
        for x, y in zip(a, b):
            if x["class"] != y["class"]:
                continue
            if x["class"] == "PCGPolygon2DData":
                same += x["xf"] == y["xf"] and x["vp"] == y["vp"] and x["raw"]["outer"] == y["raw"]["outer"]
            else:
                same += [c["p"] for c in x["raw"]["control"]] == [c["p"] for c in y["raw"]["control"]]
        res[py_tap] = {"slim": len(a), "official": len(b), "equal_as_engine_data": same}
    for tap in ("T_fill2", "T_fill7", "T_fill11", "T_fill3", "T_diff"):
        a, b = s.get(tap, []), o.get(tap, [])
        eq_items = 0
        pts_a = sum(r["points"]["n"] for r in a)
        pts_b = sum(r["points"]["n"] for r in b)
        for x, y in zip(a, b):
            px, py = x["points"], y["points"]
            eq_items += (px["n"] == py["n"] and px["cols"] == py["cols"] and px["quat"] == py["quat"]
                         and px["attrs"] == py["attrs"])
        res[tap] = {"slim_items": len(a), "official_items": len(b), "slim_points": pts_a, "official_points": pts_b,
                    "items_equal_field_for_field": eq_items}
    if write:
        doc = {}
        if os.path.exists(DATA):
            with open(DATA, encoding="utf-8") as fh:
                doc = json.load(fh)
        doc["slim_against_official_taps"] = res
        with open(DATA, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, indent=1, sort_keys=True)
    return res


FIXTURE = os.path.join(REPO, "Tools", "pypcg", "data", "s12_fixture.json")


def _pts_json(p, idx=None):
    idx = list(range(len(p))) if idx is None else idx
    return {"types": dict(p.types), "loc": [list(p.loc[i]) for i in idx], "quat": [list(p.quat[i]) for i in idx],
            "scale": [list(p.scale[i]) for i in idx], "bounds_min": [list(p.bounds_min[i]) for i in idx],
            "bounds_max": [list(p.bounds_max[i]) for i in idx], "density": [p.density[i] for i in idx],
            "steepness": [p.steepness[i] for i in idx], "seed": [p.seed[i] for i in idx],
            "attrs": {k: [v[i] for i in idx] for k, v in p.attrs.items()}}


def fixture(label="a"):
    """`Tools/pypcg/data/s12_fixture.json`: eight official rooftops (two small, a medium on each side of 800 m2, a
    large under 500 m2, a large above it under 70 m, two above 70 m) with the official polygon Filter_Areas_BySize
    made of each (frame, ToPoint vertices), the official offset areas and heights; and one official WFC item with
    every small-assembly point near it and what the official difference kept of it."""
    t = load(label)
    items = [(spline_of(r), frozenset(r["tags"])) for r in t["T_roofs"]]
    cls = S.by_class(items)
    s9 = S.by_size(cls["SmallRooftops"], 300.0)
    s6 = S.by_size(cls["MediumRooftops"], 800.0)
    s5 = S.by_size(cls["LargeRooftops"], 500.0)
    inside, outside, _h = S.by_height(s5[0])
    heights = [r["rows"][0]["height"] for r in t["X_height"]]
    off8 = t["T_off8"]
    n_poly8 = len(s5[0]) + len(s5[1]) + len(s6[0])

    def rec(roof, kind, official_poly, off8_rec=None, off20_rec=None, height=None):
        sp = roof.spline
        return {"kind": kind, "points": [list(p) for p in sp.points], "tags": sorted(roof.tags),
                "official_polygon": {"t": official_poly["xf"]["t"], "q": official_poly["xf"]["q"],
                                     "vp": official_poly["vp"]},
                "official_offset8": None if off8_rec is None else (
                    {"t": off8_rec["xf"]["t"], "q": off8_rec["xf"]["q"], "vp": off8_rec["vp"]}
                    if off8_rec["class"] == "PCGPolygon2DData" else {"control": [c["p"] for c in off8_rec["raw"]["control"]]}),
                "official_offset20": None if off20_rec is None else {"t": off20_rec["xf"]["t"], "q": off20_rec["xf"]["q"],
                                                                     "vp": off20_rec["vp"]},
                "official_height": height}

    roofs = []
    for j in (0, 1):                                              # small: Subgraph_9 Selected, Subgraph_8's splines
        r = cls["SmallRooftops"][j]
        roofs.append(rec(r, "small>300", t["T_s9sel"][s9[0].index(r)], off8[n_poly8 + j]))
    r = s6[0][0]
    roofs.append(rec(r, "medium>800", t["T_s6sel"][0], off8[len(s5[0]) + len(s5[1])]))
    r = s6[1][0]
    roofs.append(rec(r, "medium<=800", t["T_s6uns"][0]))
    r = s5[1][0]
    roofs.append(rec(r, "large<=500", t["T_s5uns"][0], off8[len(s5[0])]))
    k = s5[0].index(outside[0])
    roofs.append(rec(outside[0], "large>500 low", t["T_outside"][0], off8[k], height=heights[k]))
    for j in (0, 1):
        k = s5[0].index(inside[j])
        roofs.append(rec(inside[j], "large>500 high", t["T_inside"][j], off8[k], t["T_off20"][j], heights[k]))

    wfc = [points_of(r) for r in t["T_fill7"]]
    small = [points_of(r) for r in t["T_fill2"]]
    kept = [points_of(r) for r in t["T_diff"]]
    best = None
    for k, p in enumerate(wfc):
        if 20 <= len(p) <= 80 and 0 < len(kept[k]) < len(p):
            best = k
            break
    p = wfc[best]
    lo = [min(v[i] for v in p.loc) - 3000.0 for i in range(2)]
    hi = [max(v[i] for v in p.loc) + 3000.0 for i in range(2)]
    near = Points()
    near.quat = []
    for q in small:
        for i in range(len(q)):
            if lo[0] <= q.loc[i][0] <= hi[0] and lo[1] <= q.loc[i][1] <= hi[1]:
                quats = list(near.quat)
                near.extend(q.take([i]))
                near.quat = quats + [q.quat[i]]
    doc = {"tap": label, "roofs": roofs,
           "difference": {"wfc_item": best, "wfc": _pts_json(p), "small_near": _pts_json(near),
                          "official_kept_loc": [list(v) for v in kept[best].loc],
                          "official_kept_quat": [list(v) for v in kept[best].quat]}}
    with open(FIXTURE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=0)
    return {"roofs": len(roofs), "wfc_item": best, "wfc_points": len(p), "small_near": len(near),
            "official_kept": len(kept[best])}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--fixture" in sys.argv:
        print(json.dumps(fixture(args[0] if args else "a"), indent=1))
    elif "--slim" in sys.argv:
        print(json.dumps(compare_slim(args[0] if args else "a", args[1] if len(args) > 1 else "slim",
                                      "--write" in sys.argv), indent=1))
    else:
        print(json.dumps(main(args[0] if args else "a", "--write" in sys.argv), indent=1))
