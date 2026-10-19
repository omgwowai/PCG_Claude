"""Distil stage 10's official measurements (Task 17) into Tools/pypcg/data/s10_official_measurements.json.

Reads what `Content/Python/pypcg_s10_measure.py` and the V2 reads wrote under Saved/Reports/v2/s10/:
tap_official.json, tilecmp.json, pieces.json, nontile_outputs.json, corners_official.json,
corners_<port>.json, official*.json and slim_<seed>.json. Run from the repo root:

    C:/Python314/python.exe Tools/pypcg/s10_measurements.py [corners_port_name]
"""
import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "Content", "Python"))

from pypcg import geo  # noqa: E402

D = os.path.join(REPO, "Saved", "Reports", "v2", "s10")
OUT = os.path.join(REPO, "Tools", "pypcg", "data", "s10_official_measurements.json")


def load(name):
    return json.load(open(os.path.join(D, name), encoding="utf-8"))


def _pts(v):
    if isinstance(v, geo.Spline):
        return [tuple(p[:3]) for p in v.points], v.closed
    return [tuple(p[:2]) + (v.z,) for p in v.outer], True


def _dist(pa, pb, closed):
    if len(pa) != len(pb):
        return None
    best = None
    for s in (range(len(pb)) if closed else [0]):
        q = pb[s:] + pb[:s]
        d = max(max(abs(x - y) for x, y in zip(p, r)) for p, r in zip(pa, q))
        best = d if best is None else min(best, d)
    return best


def match(port, official):
    """Each official item to the nearest unused port item of the same kind and size (cyclic shift for a
    closed one): matched, bit-for-bit, worst coordinate difference, how many sit at the same index."""
    used, worst, exact, same, unmatched = set(), 0.0, 0, 0, 0
    for j, b in enumerate(official):
        pb, cb = _pts(b)
        best = bi = None
        for i, a in enumerate(port):
            if i in used or type(a) is not type(b):
                continue
            pa, ca = _pts(a)
            if ca != cb:
                continue
            d = _dist(pa, pb, cb)
            if d is not None and (best is None or d < best):
                best, bi = d, i
        if bi is None or best > 1.0:
            unmatched += 1
            continue
        used.add(bi)
        worst = max(worst, best)
        exact += best == 0.0
        same += bi == j
    return {"port": len(port), "official": len(official), "matched": len(used), "bit_exact": exact,
            "worst_cm": worst, "same_index": same, "unmatched": unmatched}


def per_mesh(rec):
    return rec["instances"]["per_mesh"]


def main(port_corners="slim_rot"):
    tap = load("tap_official.json")
    nontile = load("nontile_outputs.json")["outputs"]
    mine = {pin: [geo.from_json(v) for v, _ in items] for pin, items in nontile.items()}
    off_segs = [geo.from_json(v) for v in tap["T_lotsegs"] + tap["T_lmsegs"]]
    off_corners = [geo.from_json(v) for v in tap["T_cornersA"] + tap["T_landmark"]]
    off_rails = [geo.from_json(v) for v in tap["T_rail"]]
    c_off, c_port = load("corners_official.json")["meshes"], load("corners_%s.json" % port_corners)["meshes"]

    def corner_gap(port_rows):
        worst, missing = 0.0, 0
        for m, rows in c_off.items():
            mine_rows = [tuple(r) for r in port_rows.get(m, [])]
            for r in rows:
                d = min((math.dist(r[:3], q[:3]) for q in mine_rows), default=float("inf"))
                worst = max(worst, d) if d != float("inf") else worst
                missing += d > 1.0
        return worst, missing

    worst, missing = corner_gap(c_port)
    without = None
    if os.path.exists(os.path.join(D, "corners_slim.json")):
        rows = load("corners_slim.json")["meshes"]
        without = {"port": sum(len(v) for v in rows.values()), "official_missing_in_port": corner_gap(rows)[1],
                   "what": "the same run with the boundary pieces' control points at identity rotation"}
    official = load("official.json")
    slims = {s: load("slim_%d.json" % s) for s in (7, 13, 101, 977, 42)}
    off_pm = per_mesh(official)
    non_tile = lambda pm: {k: v for k, v in pm.items() if "Plaza_Square" not in k}  # noqa: E731
    doc = {
        "what": "Stage 10 Ground against the official graph on the demo level's stage-10 volume (seed 42, "
                "2026-10-19, Task 17). Taps: Content/Python/pypcg_s10_measure.py; distilled by "
                "Tools/pypcg/s10_measurements.py. Lengths in cm.",
        "fill_and_fit": load("tilecmp.json"),
        "buildable_pieces": load("pieces.json"),
        "buildable_pieces_in_subject_frame": (load("frame_exclusion.json")
                                              if os.path.exists(os.path.join(D, "frame_exclusion.json")) else None),
        "sidewalk_segments": match(mine["SidewalkSegments"], off_segs),
        "corner_shapes": match(mine["CornerShapes"], off_corners),
        "railing_zones": match(mine["RailingZones"], off_rails),
        "corner_instances": {"official": sum(len(v) for v in c_off.values()),
                             "port": sum(len(v) for v in c_port.values()),
                             "official_missing_in_port": missing, "worst_cm": worst,
                             "without_control_point_rotations": without},
        "instances": {
            "official_total": sum(off_pm.values()),
            "official_reads": {n: sum(per_mesh(load(n + ".json")).values())
                               for n in ("official", "official_after", "official_after_reread", "official_final")
                               if os.path.exists(os.path.join(D, n + ".json"))},
            "slim_totals": {str(s): sum(per_mesh(r).values()) for s, r in slims.items()},
            "non_tile_equal_per_mesh": {str(s): non_tile(per_mesh(r)) == non_tile(off_pm) for s, r in slims.items()},
            "official_tiles": {k.rsplit(".", 1)[-1]: v for k, v in sorted(off_pm.items()) if "Plaza_Square" in k},
            "slim_tiles": {str(s): {k.rsplit(".", 1)[-1]: v for k, v in sorted(per_mesh(r).items())
                                    if "Plaza_Square" in k} for s, r in slims.items()},
        },
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=1)
    return doc


if __name__ == "__main__":
    d = main(*sys.argv[1:])
    print(json.dumps({k: v for k, v in d.items() if k not in ("instances", "what")}, indent=1)[:3000])
    print(json.dumps(d["instances"]["non_tile_equal_per_mesh"]), d["instances"]["official_reads"])
