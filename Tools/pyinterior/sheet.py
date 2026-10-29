"""A labelled contact sheet of editor screenshots (the dynamic-outline sequence, before / after pairs) for the PyInterior guide.

Usage: python Tools/pyinterior/sheet.py OUT.jpg [--cols 2] [--crop W H] "label|path.png" ...
Each shot is cropped to W x H pixels around its centre (default: uncropped), laid out in a grid, label at the top left."""
import argparse
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
from plan import font  # noqa: E402


def sheet(out, items, cols=2, crop=None):
    tiles = []
    for label, path in items:
        im = Image.open(path).convert("RGB")
        if crop:
            w, h = crop
            cx, cy = im.width // 2, im.height // 2
            im = im.crop((cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2))
        tiles.append((label, im))
    tw, th = max(t.width for _l, t in tiles), max(t.height for _l, t in tiles)
    rows = (len(tiles) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * tw + (cols + 1) * 8, rows * th + (rows + 1) * 8), (24, 24, 24))
    d = ImageDraw.Draw(canvas)
    f = font(30)
    for k, (label, im) in enumerate(tiles):
        x, y = 8 + (k % cols) * (tw + 8), 8 + (k // cols) * (th + 8)
        canvas.paste(im, (x, y))
        box = d.textbbox((x + 14, y + 10), label, font=f)
        d.rectangle((box[0] - 8, box[1] - 6, box[2] + 8, box[3] + 6), fill=(0, 0, 0))
        d.text((x + 14, y + 10), label, fill=(255, 255, 255), font=f)
    canvas.save(out, quality=88)
    return canvas.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("items", nargs="+", help='"label|path.png"')
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("--crop", type=int, nargs=2, default=None)
    a = ap.parse_args()
    size = sheet(a.out, [tuple(s.split("|", 1)) for s in a.items], a.cols, a.crop)
    print("%s %dx%d" % (a.out, size[0], size[1]))


if __name__ == "__main__":
    main()
