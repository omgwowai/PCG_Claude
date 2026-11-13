# art_sheet.py -- review sheet for tuning one art weather (cs_weather_art.py): each tag is a row with the designed shot
# and the hero shot (CS_SkyCam) side by side, plus the luminance statistics of each panel.
#   C:\Python314\python.exe -P -E Tools/cs_weather/art_sheet.py <preset> <tag> [<tag> ...] [--h 420]
#       -> Saved/Reports/cs_weather2/art/sheet_<preset>.jpg
# The statistics are of the sRGB image: mean luma (0-255) of the top / bottom halves, the 1st / 99th percentile luma and
# the share of clipped pixels (any channel >= 254), so exposure changes can be judged in numbers as well as by eye.
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Content", "Python"))
import cs_weather_presets as P  # noqa: E402

SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
OUT = os.path.join(ROOT, "Saved", "Reports", "cs_weather2", "art")


def short(label):
    return "hero" if label == "CS_SkyCam" else label.replace("CS_WX_", "").replace("CS_ART_", "").lower()


def shot_path(preset, label, tag):
    return os.path.join(SHOTS, "wx_%s_%s_%s.png" % (preset, short(label), tag))


def stats(im):
    a = np.asarray(im, dtype=np.float32)
    luma = a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722
    h = luma.shape[0] // 2
    return {"top": round(float(luma[:h].mean()), 1), "bottom": round(float(luma[h:].mean()), 1),
            "p1": round(float(np.percentile(luma, 1)), 1), "p99": round(float(np.percentile(luma, 99)), 1),
            "clip%": round(float((a.max(axis=2) >= 254).mean() * 100.0), 2)}


def fit_h(im, h):
    return im.resize((round(im.width * h / im.height), h), Image.LANCZOS)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("preset")
    ap.add_argument("tags", nargs="+")
    ap.add_argument("--h", type=int, default=420)
    a = ap.parse_args()
    p = P.PRESETS[a.preset]
    rows = []
    for tag in a.tags:
        row = []
        for label, _ref in p["shots"]:
            path = shot_path(a.preset, label, tag)
            if not os.path.exists(path):
                print("missing", path)
                continue
            im = Image.open(path).convert("RGB")
            print("%-8s %-12s %s" % (tag, short(label), stats(im)))
            row.append(("%s  %s" % (tag, short(label)), fit_h(im, a.h)))
        if row:
            rows.append(row)
    if not rows:
        return 1
    width = max(sum(im.width for _, im in r) + 6 * (len(r) - 1) for r in rows)
    sheet = Image.new("RGB", (width, len(rows) * a.h + 6 * (len(rows) - 1)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("arial.ttf", 16)
    y = 0
    for r in rows:
        x = 0
        for name, im in r:
            sheet.paste(im, (x, y))
            d.text((x + 5, y + 3), name, fill=(255, 255, 0), font=font)
            x += im.width + 6
        y += a.h + 6
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, "sheet_%s.jpg" % a.preset)
    sheet.save(out, quality=86)
    print(out, sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
