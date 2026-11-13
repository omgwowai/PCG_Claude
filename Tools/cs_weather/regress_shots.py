# regress_shots.py -- compare re-renders of weather presets (Saved/Screenshots/WindowsEditor/wx_<preset>_<cam>_<tag>.png)
# with their finals (wx_<preset>_<cam>_final.png) using diff_shots.py's metric: the largest channel mean of the absolute
# sRGB difference, and the 99.9th percentile of the luma difference after an 8x box downscale. Checks them against the
# noise floor (spec §2.6: two renders of the unchanged scene).
#   --make-floor      the result becomes the floor (max over the shots) in noise_floor.json
#   (default)         every shot must stay within --factor (1.5) x the floor; exit 1 otherwise
#   --expect-change   every shot must exceed --factor x the floor (the director stills at 1200 s: the clouds moved)
#   --first-cam       only each preset's first shot camera (the director stills shoot that one)
#   C:\Python314\python.exe -P -E Tools/cs_weather/regress_shots.py --tag noise --presets base art_storm --make-floor
#   C:\Python314\python.exe -P -E Tools/cs_weather/regress_shots.py --tag v2
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Content", "Python"))
sys.path.insert(0, os.path.dirname(__file__))
import cs_weather_presets as P  # noqa: E402
import diff_shots as D  # noqa: E402

SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
OUT = os.path.join(ROOT, "Saved", "Reports", "cs_cloud_motion")
BASE_CAMS = ["CS_WX_Across", "CS_SkyCam"]          # the base look's finals (cs_weather.py batch "extra")
W = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def short(label):
    return "hero" if label == "CS_SkyCam" else label.replace("CS_WX_", "").replace("CS_ART_", "").lower()


def cams(name, first_only):
    labels = BASE_CAMS if name == "base" else [s[0] for s in P.PRESETS[name]["shots"]]
    return labels[:1] if first_only else labels


def metric(a_path, b_path):
    a, b = D.load(a_path), D.load(b_path)
    if a.shape != b.shape:
        return None
    d = np.abs(a - b)
    dl = np.abs(D.box(a, 8) @ W - D.box(b, 8) @ W)
    return {"mean": round(float(d.reshape(-1, 3).mean(axis=0).max()), 3),
            "p999": round(float(np.percentile(dl, 99.9)), 3)}


def compare(presets, tag, first_only):
    rows = []
    for name in presets:
        for label in cams(name, first_only):
            fin = os.path.join(SHOTS, "wx_%s_%s_final.png" % (name, short(label)))
            new = os.path.join(SHOTS, "wx_%s_%s_%s.png" % (name, short(label), tag))
            row = {"shot": os.path.basename(new)}
            if not (os.path.exists(fin) and os.path.exists(new)):
                row["missing"] = True
            else:
                m = metric(fin, new)
                row.update(m if m else {"size_differs": True})
            rows.append(row)
    return rows


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--presets", nargs="*")
    ap.add_argument("--make-floor", action="store_true")
    ap.add_argument("--expect-change", action="store_true")
    ap.add_argument("--first-cam", action="store_true")
    ap.add_argument("--factor", type=float, default=1.5)
    ap.add_argument("--floor", default=os.path.join(OUT, "noise_floor.json"))
    a = ap.parse_args()
    presets = a.presets or ["base"] + list(P.ORDER) + list(P.ART_ORDER)
    rows = compare(presets, a.tag, a.first_cam)
    os.makedirs(OUT, exist_ok=True)
    if a.make_floor:
        good = [r for r in rows if "mean" in r]
        if len(good) != len(rows):
            print("missing shots:", [r["shot"] for r in rows if "mean" not in r])
            return 1
        floor = {"mean": max(r["mean"] for r in good), "p999": max(r["p999"] for r in good), "from": a.tag,
                 "shots": rows}
        json.dump(floor, open(a.floor, "w", encoding="utf-8"), indent=1)
        print("floor", {k: floor[k] for k in ("mean", "p999")})
        return 0
    floor = json.load(open(a.floor, encoding="utf-8"))
    lim_m, lim_p = a.factor * floor["mean"], a.factor * floor["p999"]
    bad = []
    for r in rows:
        if "mean" not in r:
            bad.append(r)
        elif a.expect_change and not (r["mean"] > lim_m or r["p999"] > lim_p):
            bad.append(r)
        elif not a.expect_change and (r["mean"] > lim_m or r["p999"] > lim_p):
            bad.append(r)
    res = {"tag": a.tag, "floor": {"mean": floor["mean"], "p999": floor["p999"]}, "factor": a.factor,
           "expect_change": a.expect_change, "rows": rows, "bad": bad}
    json.dump(res, open(os.path.join(OUT, "regress_%s.json" % a.tag), "w", encoding="utf-8"), indent=1)
    for r in rows:
        print(r)
    print("%d shots, %d outside the limits (mean %.2f, p999 %.2f)" % (len(rows), len(bad), lim_m, lim_p))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
