# ab.py -- review strip for tuning one preset: reference photo | photo-matched render for each tag, side by side.
#   C:\Python314\python.exe -P -E Tools/cs_weather/ab.py <preset> <tag> [<tag> ...] [--h 360]
#       -> Saved/Reports/cs_weather2/compare/ab_<preset>.jpg (prints the mean sRGB of each panel's top / bottom half)
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont, ImageStat

sys.path.insert(0, os.path.dirname(__file__))
import compare  # noqa: E402  (ref_path, short, fit_h, P)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("preset")
    ap.add_argument("tags", nargs="+")
    ap.add_argument("--h", type=int, default=360)
    a = ap.parse_args()
    p = compare.P.PRESETS[a.preset]
    label, ref = next((l, r) for l, r in p["shots"] if r is not None)
    photo = Image.open(compare.ref_path(p["ref"], ref)).convert("RGB")
    crop = p.get("ref_crop", {}).get(str(ref))
    if crop:
        photo = photo.crop((round(crop[0] * photo.width), round(crop[1] * photo.height),
                            round(crop[2] * photo.width), round(crop[3] * photo.height)))
    panels = [("photo", photo)]
    for tag in a.tags:
        path = os.path.join(compare.SHOTS, "wx_%s_%s_%s.png" % (a.preset, compare.short(label), tag))
        if os.path.exists(path):
            panels.append((tag, Image.open(path).convert("RGB")))
        else:
            print("missing", path)
    for name, im in panels:
        top = ImageStat.Stat(im.crop((0, 0, im.width, im.height // 2))).mean
        bot = ImageStat.Stat(im.crop((0, im.height // 2, im.width, im.height))).mean
        print("%-10s top %s bottom %s" % (name, [round(x) for x in top], [round(x) for x in bot]))
    panels = [(n, compare.fit_h(im, a.h)) for n, im in panels]
    sheet = Image.new("RGB", (sum(im.width for _, im in panels) + 6 * (len(panels) - 1), a.h))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("arial.ttf", 16)
    x = 0
    for n, im in panels:
        sheet.paste(im, (x, 0))
        d.text((x + 5, 3), n, fill=(255, 255, 0), font=font)
        x += im.width + 6
    out = os.path.join(compare.OUT, "ab_%s.jpg" % a.preset)
    os.makedirs(compare.OUT, exist_ok=True)
    sheet.save(out, quality=86)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
