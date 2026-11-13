# compare.py -- side-by-side review image of one preset: reference photo | photo-matched render | hero render.
#   C:\Python314\python.exe -P -E Tools/cs_weather/compare.py <preset> <tag> [--h 560]
#       -> Saved/Reports/cs_weather2/compare/<preset>_<tag>.jpg
import argparse
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Content", "Python"))
import cs_weather_presets as P  # noqa: E402

SHOTS = os.path.join(ROOT, "Saved", "Screenshots", "WindowsEditor")
REFS = os.path.join(ROOT, "Saved", "Reports", "cs_weather2", "refs")
OUT = os.path.join(ROOT, "Saved", "Reports", "cs_weather2", "compare")


def short(label):
    return "hero" if label == "CS_SkyCam" else label.replace("CS_WX_", "").lower()


def ref_path(key, idx):
    full = os.path.join(REFS, "full", "%s_%d.jpg" % (key, idx))
    if os.path.exists(full):
        return full
    picks = json.load(open(os.path.join(ROOT, "Saved", "Reports", "cs_weather2", "menu", "picks.json"), encoding="utf-8"))
    ck, ci = picks[key][idx]["cand"]
    return os.path.join(REFS, "cand", ck, "%02d.jpg" % ci)


def fit_h(im, h):
    return im.resize((max(1, round(im.width * h / im.height)), h), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("preset")
    ap.add_argument("tag")
    ap.add_argument("--h", type=int, default=560)
    a = ap.parse_args()
    p = P.PRESETS[a.preset]
    panels = []
    for label, ref in p["shots"]:
        if ref is not None:
            im = Image.open(ref_path(p["ref"], ref)).convert("RGB")
            crop = p.get("ref_crop", {}).get(str(ref))
            if crop:
                im = im.crop((round(crop[0] * im.width), round(crop[1] * im.height),
                              round(crop[2] * im.width), round(crop[3] * im.height)))
            panels.append(("photo", im))
        path = os.path.join(SHOTS, "wx_%s_%s_%s.png" % (a.preset, short(label), a.tag))
        if os.path.exists(path):
            panels.append((short(label), Image.open(path).convert("RGB")))
    panels = [(n, fit_h(im, a.h)) for n, im in panels]
    w = sum(im.width for _, im in panels) + 8 * (len(panels) - 1)
    sheet = Image.new("RGB", (w, a.h), (0, 0, 0))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("arial.ttf", 18)
    x = 0
    for n, im in panels:
        sheet.paste(im, (x, 0))
        d.text((x + 6, 4), n, fill=(255, 255, 0), font=font)
        x += im.width + 8
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, "%s_%s.jpg" % (a.preset, a.tag))
    sheet.save(out, quality=88)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
