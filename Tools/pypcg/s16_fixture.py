"""Distil the stage-16 taps into `Tools/pypcg/data/s16_fixture.json` (the offline tests' official numbers).

Inputs (written by the untracked editor probes `Content/Python/pyg_probe_t22f_read.py` on the tap graphs
`/Game/PyPCG/Probe/PCG_T22fTapA` / `PCG_T22fTapB`, 2026-10-20, component seed 42):
  Saved/t22f/tapA.full.json   the geometry taps (t01 .. t33)
  Saved/t22f/tapB.full.json   the post-grammar taps (u01 .. u21)
Run: `C:/Python314/python.exe Tools/pypcg/s16_fixture.py`.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(REPO, "Content", "Python")]

from pypcg import geo  # noqa: E402

KEEP = ("kind", "points", "closed", "linear", "tangents", "polyline", "frame", "point_rotations", "outer", "holes", "z",
        "loc", "rot", "quat", "n")


def _slim(r, keys=KEEP):
    return {k: v for k, v in r.items() if k in keys}


def _trees_inside(a, b):
    """The brief's "no vegetation inside the lake, the exclusion area or a road", measured on the OFFICIAL trees
    (u17): how many stand inside the forest exclusion, a lake, the grown Met or a grown road footprint, and how
    deep. The fill's +-200 cm jitter puts some there (s16.md section 6)."""
    from pypcg.checks import s16 as K

    def rd(r):
        return geo.from_json({k: v for k, v in r.items() if k in ("kind", "points", "closed", "linear", "tangents",
                                                                  "polyline", "outer", "holes", "z")})
    lakes = [geo.Polygon(geo.ccw(K.ring_of(rd(r))), [], 0.0) for r in a["t15_lakeflat"]]
    excl = [geo.Polygon(geo.ccw(K.ring_of(rd(r))), [], 0.0) for r in a["t22_forest"]] + lakes + [rd(a["t25_metexp"][0])]
    idx = K._Index(excl + [rd(r) for r in b["u03_borderexp"]])
    lake_idx = K._Index(lakes)
    n = inside = in_lake = 0
    deepest = 0.0
    for r in b["u17_trees"]:
        for loc in r["loc"]:
            p = (loc[0], loc[1])
            n += 1
            d = max([K.depth_inside(p, c) for c in idx.near(p)] or [0.0])
            if d > 0.0:
                inside += 1
                deepest = max(deepest, d)
            if any(K.depth_inside(p, c) > 0.0 for c in lake_idx.near(p)):
                in_lake += 1
    return {"trees": n, "inside": inside, "in_lake": in_lake, "deepest_cm": round(deepest, 3)}


def main():
    a = json.load(open(os.path.join(REPO, "Saved", "t22f", "tapA.full.json"), encoding="utf-8"))["rows"]
    b = json.load(open(os.path.join(REPO, "Saved", "t22f", "tapB.full.json"), encoding="utf-8"))["rows"]

    def area(r):
        return round(geo.area_m2(geo.from_json({k: v for k, v in r.items() if k in ("kind", "outer", "holes", "z")})), 3)

    fx = {
        "_": "Distilled by Tools/pypcg/s16_fixture.py from the stage-16 taps of 2026-10-20 (s16.md).",
        "footprint": _slim(a["t29_footprint"][0]),
        "centre": {"loc": a["t01_center"][0]["loc"][0], "quat": a["t01_center"][0]["quat"][0]},
        "lines": [a[t][0]["points"] for t in ("t02_line65", "t03_line79", "t04_line86", "t05_line97")],
        "outlines": [_slim(r, ("kind", "outer", "holes", "z")) for r in a["t06_outline"]],
        "border_segments": [r["points"] for r in a["t07_segments"]],
        "pieces_m2": [area(r) for r in a["t08_split"]],
        "contracted": [_slim(r, ("kind", "outer", "holes", "z")) for r in a["t09_contract"]],
        "sidewalk_segments": len(a["t10_sideseg"]),
        "drawn": [_slim(r) for r in a["t30_drawnraw"]],
        "walk": [_slim(r, ("kind", "points", "tangents")) for r in a["t12_walk"]],
        "path_bands_m2": [area(r) for r in a["t13_pathout"]],
        "areas_m2": [area(r) for r in a["t14_areas"]],
        "lakes": [_slim(r) for r in a["t31_lakeraw"]],
        "lake_lifted": [_slim(r, ("kind", "points", "tangents")) for r in a["t16_lakeoff"]],
        "lake_edge": [_slim(r, ("kind", "points", "tangents")) for r in a["t17_lakeedge"]],
        "lake_projected": [_slim(r, ("kind", "points", "tangents")) for r in a["t18_lakeproj"]],
        "lake_level": [_slim(r, ("kind", "points", "tangents")) for r in a["t19_lakelevel"]],
        "lake_bed": [_slim(r, ("kind", "points", "tangents")) for r in a["t20_lakebed"]],
        "lake_bed_points": a["t21_bedpts"][0].get("n"),
        "forest_exclusion": [_slim(r) for r in a["t32_forestraw"]],
        "met_point": a["t23_metpt"][0]["loc"][0],
        "met_shape": a["t24_metshape"][0]["points"],
        "met_expanded": _slim(a["t25_metexp"][0], ("kind", "outer", "holes", "z")),
        "met_projected": a["t26_metproj"][0]["points"],
        "met_spline": {"points": a["t28_metspline"][0]["points"], "rotations": a["t28_metspline"][0]["point_rotations"]},
        "road_footprints_m2": [area(r) for r in b["u01_borderfoot"]],
        "forest_areas_m2": [area(r) for r in b["u04_exclude"]],
        "split": {"selected_m2": [area(r) for r in b["u06_sel"]], "unselected_m2": [area(r) for r in b["u07_unsel"]]},
        "trees": {"filled": [sum(r["n"] if "n" in r else len(r["loc"]) for r in b["u08_fill1"]),
                             sum(r["n"] if "n" in r else len(r["loc"]) for r in b["u13_fill2"])],
                  "kept": [sum(len(r["loc"]) for r in b["u10_dens1"]), sum(len(r["loc"]) for r in b["u14_dens2"])],
                  "spawned": [len(r["loc"]) for r in b["u17_trees"]],
                  "_order": "[unselected (Fill_Forest, 0.05 /m2), selected (Fill_Forest_2, 0.02 /m2)]"},
    }
    fx["official_trees_inside"] = _trees_inside(a, b)
    out = os.path.join(HERE, "data", "s16_fixture.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(fx, fh)
    print("written", out, os.path.getsize(out))


if __name__ == "__main__":
    main()
