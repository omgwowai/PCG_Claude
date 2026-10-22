"""Stage 11: the port against the official graph's own intermediate data (Task 20).

Reads the official taps that `Content/Python/pypcg_s11_measure.py` writes (Saved/t20/tap_<label>.json and
Saved/t20/splines_hr.json; not committed) and runs `pypcg.stages.s11_buildings` on the official inputs --
the texture-written footprints with their engine vertices and frames, the official texture heights, the
HighRise splines with their frames, the official terrain heights at every vertex, the official selection
(Clipper is editor-only) and the official Write_Noise draws -- then compares, bit for bit:

  - every levelled footprint (`Subgraph_13_*` output): control points, height, yaw;
  - everything the medium and large Assign nodes receive (Branch_*DistrictDebug input order): polygons by
    frame and ToPoint vertices, cleaned splines by control points;
  - the complex-shape heights (AttributeMathsOp_2 / AttributeMathsOp_1 outputs).

`--records` also distills the V2 / oracle census files of Saved/Reports/v2/s11 (instance totals, the meshes that
differ, stage 12 downstream) under "editor_records".

Writes the distilled numbers to Tools/pypcg/data/s11_official_measurements.json (merged with what is there).
Run from the repo root: C:/Python314/python.exe Tools/pypcg/s11_measure_offline.py"""
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "Content", "Python"))

from pypcg.geo import ParamSet, Polygon, Spline  # noqa: E402
from pypcg.geo import frames as F  # noqa: E402
from pypcg.stages import s11_buildings as S  # noqa: E402

T20 = os.path.join(REPO, "Saved", "t20")
OUT = os.path.join(HERE, "data", "s11_official_measurements.json")


def load(name):
    with open(os.path.join(T20, name), encoding="utf-8") as fh:
        return json.load(fh)


class DictTerrain:
    """The official projected z at every vertex the projection saw (Subgraph_12_* outputs)."""

    def __init__(self, taps):
        self.z = {}
        for r in taps:
            for cp in r["raw"]["control"]:
                self.z[(cp["p"][0], cp["p"][1])] = cp["p"][2]

    def height(self, x, y):
        return self.z.get((x, y))


def poly_of(r):
    return Polygon([tuple(p[:2]) for p in r["raw"]["outer"]], [], 0.0, vertices=[tuple(v) for v in r["vp"]],
                   frame=(tuple(r["xf"]["t"]), tuple(r["xf"]["q"])))


def main():
    a, e = load("tap_a.json"), load("tap_e.json")
    # the HighRise splines' own transforms: read with the tap (`xf`) or, for the 2026-10-20 tap a, the dump
    # of the same two splines (Saved/t20/splines_hr.json)
    hr = [{"t": r["xf"]["t"], "q": r["xf"]["q"], "s": r["xf"]["s"]} for r in a["T_hr"]] if all(
        "xf" in r for r in a["T_hr"]) else load("splines_hr.json")
    proj = [r for c in "sml" for r in (e.get("T_%s_proj" % c) or a["T_%s_proj" % c])]
    zones = []
    for r, s in zip(a["T_hr"], hr):
        raw = r["raw"]
        zones.append((Spline([tuple(cp["p"]) for cp in raw["control"]], closed=True, linear=False,
                             tangents=[(tuple(cp["arrive"]), tuple(cp["leave"])) for cp in raw["control"]],
                             polyline=[tuple(p) for p in raw["polyline"]],
                             frame=(tuple(s["t"]), tuple(s["q"]), tuple(s["s"]))), frozenset(["HighRise"])))
    inputs = {"HighRise": zones, "MeshTerrain": [(DictTerrain(proj), frozenset())]}
    selected = set()
    for c, cls in zip("sml", S.CLASSES):
        inputs[cls + "Lots"] = [(poly_of(r), frozenset(r["tags"])) for r in e["T_%s_tex" % c]]
        inputs[cls + "Heights"] = [(ParamSet({"MaxHeight": x["rows"][0]["MaxHeight"]}, {"MaxHeight": "Double"}), frozenset())
                                   for x in a["T_%s_texh" % c]]
        selected |= {tuple(map(tuple, r["vp"])) for r in e.get("T_%s_sel" % c, [])}
    noise = [x["rows"][0]["MaxHeight"] for x in a["T_m_Subgraph_38h"]]
    S.within = lambda polys, _zones, _ops: [tuple(map(tuple, p.vertices)) in selected for p in polys]
    streams, notes = S.buildings(inputs, {"ComplexBuildingShapes": True, "CollisionGeometry": False}, None,
                                 S.Draws(random.Random(0), noise))
    levelled = {}
    for cls in S.CLASSES:
        polys = [v for v, _t in inputs[cls + "Lots"]]
        fps, _sel = S.footprints(polys, S.heights(inputs[cls + "Heights"]), zones, None, inputs["MeshTerrain"][0][0])
        levelled[cls] = [(fp.spline(), fp.height) for fp in fps]
    res = {"notes": notes, "levelled": {}, "to_assign": {}, "complex": {}}
    for c, cls in zip("sml", S.CLASSES):
        lvl = e["T_%s_lvl" % c]
        mine = levelled[cls]
        off_h = [x["rows"][0]["MaxHeight"] for x in a["T_%s_lvlh" % c]]
        res["levelled"][cls] = {
            "n": len(mine), "official": len(lvl),
            "point_mismatches": sum(1 for (sp, _h), r in zip(mine, lvl) for p, cp in zip(sp.points, r["raw"]["control"])
                                    if list(p) != cp["p"]),
            "points": sum(len(sp.points) for sp, _h in mine),
            "height_mismatches": sum(1 for (_s, h), ho in zip(mine, off_h) if h != ho),
            "height_max_rel": max(abs(h - ho) / ho for (_s, h), ho in zip(mine, off_h)),
            "yaw_max_deg_nondegenerate": max(
                (abs(rp[1] - ro[1][1]) for (sp, _h), r in zip(mine, lvl) for k, (rp, ro) in enumerate(zip(sp.rotations, r["sp"]))
                 if abs(rp[1] - ro[1][1]) < 180.0 and F._size(F._sub(sp.points[(k + 1) % len(sp.points)], sp.points[k])) > 1e-6),
                default=0.0)}
    for c, cls in (("m", "Medium"), ("l", "Large")):
        off = e.get("T_%s_bs_uns" % c, []) + e["T_%s_sq_uns" % c] + e.get("T_%s_fa_out" % c, [])
        mine = streams[cls + "Footprints"]
        bad = 0
        for (v, _h), r in zip(mine, off):
            if isinstance(v, Polygon):
                pos, _rot, (t, q) = F.rebuilt_vertices([(x, y, v.z) for x, y in v.outer])
                bad += [list(p) for p in pos] != r["vp"] or list(t) != r["xf"]["t"] or list(q) != r["xf"]["q"]
            else:
                bad += [list(p) for p in v.points] != [cp["p"] for cp in r["raw"]["control"]]
        res["to_assign"][cls] = {"n": len(mine), "official": len(off), "mismatches": bad,
                                 "polygons": sum(isinstance(v, Polygon) for v, _h in mine)}
        tap = "T_m_AttributeMathsOp_2h" if c == "m" else "T_l_AttributeMathsOp_1h"
        off_h = [x["rows"][0]["MaxHeight"] for x in a[tap]]
        mine_c = streams[cls + "Complex"]
        res["complex"][cls] = {"n": len(mine_c), "official": len(off_h),
                               "height_mismatches": sum(1 for (_v, h), ho in zip(mine_c, off_h) if h != ho),
                               "height_max_rel": max((abs(h - ho) / ho for (_v, h), ho in zip(mine_c, off_h)), default=0.0)}
    doc = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    doc["offline_against_official_taps"] = res
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    print(json.dumps(res, indent=1))


def records():
    d = os.path.join(REPO, "Saved", "Reports", "v2", "s11")
    def census(name):
        with open(os.path.join(d, name + ".json"), encoding="utf-8") as fh:
            return json.load(fh)
    off = census("official")
    po = off["instances"]["per_mesh"]
    out = {"official": {"total": off["instances"]["total"], "meshes": len(po),
                        "components": off["instances"]["components"]}}
    for name in ("official_after", "slim_7", "slim_13", "slim_101", "slim_977", "slim_42", "oracle_42", "oracle_42_run2"):
        if not os.path.exists(os.path.join(d, name + ".json")):
            continue
        rec = census(name)
        p = rec["instances"]["per_mesh"]
        diff = {k.rsplit("/", 1)[-1].split(".")[0]: [po.get(k, 0), p.get(k, 0)] for k in set(po) | set(p) if po.get(k, 0) != p.get(k, 0)}
        out[name] = {"total": rec["instances"]["total"], "meshes_differing": len(diff),
                     "tags": {t: sum(1 for it in rec["items"] if t in it["tags"]) for t in ("SmallRooftops", "MediumRooftops", "LargeRooftops")}}
        if name.startswith("oracle") or name == "official_after":
            out[name]["differing"] = diff
    o12, s12 = census("down_12_official"), census("down_12_slim")
    out["stage12"] = {"official_upstream": o12["instances"]["total"], "slim_42_upstream": s12["instances"]["total"],
                      "meshes": len(o12["instances"]["per_mesh"]),
                      "meshes_differing": sum(1 for k in set(o12["instances"]["per_mesh"]) | set(s12["instances"]["per_mesh"])
                                              if o12["instances"]["per_mesh"].get(k) != s12["instances"]["per_mesh"].get(k))}
    doc = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    doc["editor_records"] = out
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
    print(json.dumps(out, indent=1)[:3000])


if __name__ == "__main__":
    if "--records" in sys.argv:
        records()
    else:
        main()
