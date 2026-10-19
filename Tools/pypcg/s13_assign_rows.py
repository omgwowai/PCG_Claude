"""The stage-13 rows of Tools/pypcg/data/assign_oracle_rows.json, from the oracle runs on disk. Offline; from the
repo root:

    C:/Python314/python.exe Tools/pypcg/s13_assign_rows.py

Inputs (all written by tracked editor scripts):
  Saved/Reports/v2/s13/assign_oracle_s13_shipped.json        pypcg_v1_editor.py {"assign": {"stage": 13, "label":
                                                              "s13_shipped"}} after the shipped oracle generation
  Saved/Reports/v2/s13/assign_oracle_s13_index_tex.json      the same after an oracle generation on Subgraph_26
                                                              with the substitute texture on Subgraph_27 / 28 and
                                                              Subgraph_26's random ranges zeroed
  Saved/Reports/v2/s13/oracle_taps_s13_random.json           pypcg_s13_measure.py {"step": "dump"} of an oracle on
                                                              Subgraph_26 and Subgraph_73 with their random ranges
                                                              ON (the substitute texture again): the draws' ranges

The random rows compare what a draw cannot move (sizes, order, Asset) and MEASURE the drawn ranges: the scale
factor out / (in x ScaleOffset), whether it is one number for all axes, and the rotation delta in / out as a
rotator -- against `geo.assets._pin_range`'s reading of the pins (1 +- v for scale, +-v for rotation)."""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "Content", "Python"))

from pypcg import geo  # noqa: E402
from pypcg.geo import assets as A  # noqa: E402

D = os.path.join(REPO, "Saved", "Reports", "v2", "s13")
ROWS = os.path.join(REPO, "Tools", "pypcg", "data", "assign_oracle_rows.json")
WHAT = {
    "s13_shipped": "stage 13 LeftOverLots as shipped (component seed 42): the seven ground-tile calls (one static mesh "
                   "each, PositionOffset (-150, -150, 0)); only A and G get lots on this draw, B..F tap nothing. "
                   "Subgraph_73 is random (pick + scale); Subgraph_12/14/26 get nothing (the official texture is missing)",
    "s13_index_texture_substitute": "stage 13 Subgraph_26 (UseIndexattribute on Index, ScaleOffset (0.7, 1, 1)) with "
                                    "/Game/Textures/Noise/T_Noises_Clouds_4k_ on Subgraph_27/28 (the official "
                                    "T_CloudNoise_4k is not in the project) and its random ranges zeroed: index 1..7 -> "
                                    "entries 1..7, index 0, 8, 9 -> entry 0 (unmatched, kept, the attribute default)",
}


def _oracle_rows(label, run):
    path = os.path.join(D, "assign_oracle_%s.json" % label)
    if not os.path.exists(path):
        return []
    doc = json.load(open(path, encoding="utf-8"))
    rows = []
    for c in doc.get("calls", []):
        r = {"run": run, "stage": 13, "call": c["node"], "what": WHAT[run], "random": c["random"],
             "settings": c["settings"], "targets": c["targets"], "items": c["items"],
             "python_items": c["python_items"], "points": c.get("points")}
        if c["random"]:
            r.update(compared=c.get("compared"), equal=c.get("equal"))
        else:
            f = c.get("fields") or {}
            r.update(max_diff={k: f[k]["max"] for k in f}, bit_exact={k: f[k]["exact"] for k in f},
                     equal=c.get("equal"))
        rows.append(r)
    return rows


def _merged(recs):
    out = geo.Points()
    for k, rec in enumerate(recs):
        p = geo.from_json(rec)
        p.seed = [A._i32(int(s) + k) for s in p.seed]
        out.extend(p)
    return out


def _random_rows():
    path = os.path.join(D, "oracle_taps_s13_random.json")
    if not os.path.exists(path):
        return []
    taps = json.load(open(path, encoding="utf-8"))["taps"]
    rows = []
    for call, offset, settings in (("Subgraph_26", 0.7, {"random_rotation_range": {"X": 2, "Y": 2, "Z": 180},
                                                          "random_scale_range": {"X": 0.2, "Y": 0, "Z": 0},
                                                          "scale_offset": {"X": 0.7, "Y": 1, "Z": 1},
                                                          "use_index_attribute": True, "index_attribute": "Index"}),
                                   ("Subgraph_73", 1.0, {"random_scale_range": {"X": 0.2, "Y": 0, "Z": 0},
                                                         "extents_scale": {"X": 0.7, "Y": 1, "Z": 1}})):
        if "AssignOut_" + call not in taps:
            continue
        tin, tout = _merged(taps["AssignIn_" + call]), geo.from_json(taps["AssignOut_" + call][-1])
        f, uniform, rot, moved = [], True, [], 0.0
        for i in range(len(tout)):
            s = [tout.scale[i][a] / (tin.scale[i][a] * offset) for a in range(3)]
            f.append(s[0])
            uniform &= abs(s[0] - s[1]) < 1e-9 and abs(s[0] - s[2]) < 1e-9
            qi = A.quat_of(*tin.rot[i])
            qd = A._qmul((-qi[0], -qi[1], -qi[2], qi[3]), tuple(tout.quat[i]))
            rot.append(A.rotator_of(qd))
            moved = max(moved, max(abs(tout.loc[i][a] - tin.loc[i][a]) for a in range(3)))
        lo_s, hi_s = A._pin_range(settings["random_scale_range"], False, A.DEFAULT_SCALE_RANGE)
        rr = settings.get("random_rotation_range")
        lo_r, hi_r = A._pin_range(rr, True, None) if rr else ((0.0,) * 3, (0.0,) * 3)
        hist = {}
        for a in tout.attrs["Asset"]:
            k = str(a).rsplit("/", 1)[-1]
            hist[k] = hist.get(k, 0) + 1
        measured = {"scale_factor": [round(min(f), 4), round(max(f), 4)], "scale_uniform": uniform,
                    "pitch": [round(min(r[0] for r in rot), 3), round(max(r[0] for r in rot), 3)],
                    "yaw": [round(min(r[1] for r in rot), 3), round(max(r[1] for r in rot), 3)],
                    "roll": [round(min(r[2] for r in rot), 3), round(max(r[2] for r in rot), 3)],
                    "location_moved_cm": moved, "assets": hist}
        expected = {"scale_factor": [lo_s[0], hi_s[0]], "pitch": [lo_r[0], hi_r[0]], "yaw": [lo_r[1], hi_r[1]],
                    "roll": [lo_r[2], hi_r[2]]}
        inside = all(expected[k][0] - 1e-6 <= measured[k][0] and measured[k][1] <= expected[k][1] + 1e-6
                     for k in expected)
        rows.append({"run": "s13_random_ranges_texture_substitute", "stage": 13, "call": call,
                     "what": "the call's random ranges ON (substitute texture on Subgraph_27/28): the drawn ranges "
                             "against the CoreProcess reading of the pins (geo.assets._pin_range: scale 1 +- v, "
                             "rotation +-v with X/Y/Z = Roll/Pitch/Yaw); %d draws" % len(tout),
                     "random": True, "settings": settings, "targets": len(tin), "points": len(tout),
                     "compared": "drawn ranges", "measured": measured, "expected": expected,
                     "equal": {"inside_expected_range": inside}})
    return rows


def main():
    doc = json.load(open(ROWS, encoding="utf-8"))
    keep = [r for r in doc["rows"] if r.get("stage") != 13]
    new = (_oracle_rows("s13_shipped", "s13_shipped") + _oracle_rows("s13_index_tex", "s13_index_texture_substitute")
           + _random_rows())
    doc["rows"] = keep + new
    with open(ROWS, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    return [(r["run"], r["call"], r.get("bit_exact") or r.get("equal")) for r in new]


if __name__ == "__main__":
    for row in main():
        print(row)
