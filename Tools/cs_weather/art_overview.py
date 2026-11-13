# art_overview.py -- one contact sheet of all ten art weathers for a tag: each row = designed shot + hero shot.
#   C:\Python314\python.exe -P -E Tools/cs_weather/art_overview.py <tag> [--h 300] [--only art_storm,art_shelf]
#       -> Saved/Reports/cs_weather2/art/overview_<tag>.jpg
import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import art_sheet as S  # noqa: E402  (P, shot_path, fit_h, stats, OUT)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--h", type=int, default=300)
    ap.add_argument("--only")
    a = ap.parse_args()
    names = a.only.split(",") if a.only else S.P.ART_ORDER
    rows = []
    for name in names:
        p = S.P.PRESETS[name]
        row = []
        for label, _ref in p["shots"]:
            path = S.shot_path(name, label, a.tag)
            if os.path.exists(path):
                im = Image.open(path).convert("RGB")
                print("%-15s %-8s %s" % (name, S.short(label), S.stats(im)))
                row.append(S.fit_h(im, a.h))
        rows.append((name, row))
    width = max(sum(im.width for im in r) + 6 * max(len(r) - 1, 0) for _, r in rows) + 170
    sheet = Image.new("RGB", (width, len(rows) * (a.h + 6)), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("arial.ttf", 15)
    y = 0
    for name, r in rows:
        d.text((6, y + 6), name.replace("art_", ""), fill=(255, 220, 120), font=font)
        x = 170
        for im in r:
            sheet.paste(im, (x, y))
            x += im.width + 6
        y += a.h + 6
    os.makedirs(S.OUT, exist_ok=True)
    out = os.path.join(S.OUT, "overview_%s.jpg" % a.tag)
    sheet.save(out, quality=84)
    print(out, sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
