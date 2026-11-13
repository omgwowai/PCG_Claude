"""Image helpers for the City Sample clear-sky RenderDoc report (build_report.py).

Everything here turns the raw dumps of rdc_export.py (decoded by decode_tex.decode) into PIL images and data URIs.
"""
import base64
import io
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decode_tex import decode, filmic, srgb  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
RDC = os.path.join(ROOT, "Saved", "Reports", "cs_weather", "rdc")
TEX = os.path.join(RDC, "tex")
# the earlier capture (before the cloud shadow fix): report section 8 reads its shadow maps
RDC_V2 = os.path.join(ROOT, "Saved", "Reports", "cs_weather", "rdc_v2")


def _passes_json():
    try:
        with open(os.path.join(RDC, "passes.json"), encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return {}


_PJ = _passes_json()
VIEW = tuple(_PJ.get("view", (844, 1321)))        # internal view rect of the analysed render
OUTPUT = tuple(_PJ.get("output", (1171, 1834)))   # TSR / tonemap output
FOG = (-(-VIEW[0] // 4), -(-VIEW[1] // 4))         # froxel grid xy (r.VolumetricFog.GridPixelSize 4)
HALF = (-(-VIEW[0] // 2), -(-VIEW[1] // 2))        # light shafts run at half resolution
PASSES = {p["tag"]: p for p in _PJ.get("passes", [])}


def dumped(tag, name=None, nth=0):
    """Tag of a texture rdc_export.py dumped for pass <tag>: the nth one whose resource is called <name> (any name when
    None). Resource ids change from capture to capture, names do not."""
    d = [x for x in PASSES[tag].get("dumped", []) if name is None or x["name"] == name]
    if len(d) <= nth:
        raise KeyError("pass %s has no dump named %s (#%d): %s" % (
            tag, name, nth, [x["name"] for x in PASSES[tag].get("dumped", [])]))
    return d[nth]["tag"]


def scene_pair(tag):
    """(before, after) scene-colour dumps around a full-screen pass."""
    b = PASSES[tag]["dumped_before"]
    return b["tag"], b["after"]


def meta(tag, tex_dir=None):
    with open(os.path.join(tex_dir or TEX, tag + ".json"), encoding="utf-8") as f:
        return json.load(f)


def load(tag, slice_index=0, crop=None, tex_dir=None):
    """HxWxC float array of one 2D slice (crop = (w, h) from the top-left)."""
    m = meta(tag, tex_dir)
    f = [x for x in m["files"] if x["slice"] == slice_index][0]
    with open(os.path.join(tex_dir or TEX, f["file"]), "rb") as fh:
        a = decode(m, fh.read())[0]
    if crop:
        a = a[:crop[1], :crop[0]]
    return a


def load_volume(tag, crop=FOG):
    """DxHxWxC float array of a 3D texture (crop in xy)."""
    m = meta(tag)
    with open(os.path.join(TEX, m["files"][0]["file"]), "rb") as fh:
        a = decode(m, fh.read())
    if crop:
        a = a[:, :crop[1], :crop[0]]
    return a


def to_img(a01):
    a01 = np.clip(np.nan_to_num(a01), 0.0, 1.0)
    if a01.ndim == 2:
        a01 = np.repeat(a01[..., None], 3, -1)
    return Image.fromarray((a01[..., :3] * 255.0 + 0.5).astype(np.uint8))


def hdr(a, ref=None, pct=99.5, gain=1.0):
    """Exposure-normalised filmic view of an HDR colour array."""
    rgb = np.maximum(np.nan_to_num(a[..., :3]), 0.0)
    if ref is None:
        ref = float(np.percentile(rgb.mean(-1), pct)) or 1.0
    return to_img(srgb(filmic(rgb / max(ref, 1e-12) * 1.36 * gain)))


def lin(a):
    return to_img(srgb(np.clip(np.nan_to_num(a[..., :3]), 0.0, 1.0)))


def gray(ch, lo=None, hi=None, gamma=1.0, invert=False):
    ch = np.nan_to_num(ch.astype(np.float32))
    lo = float(np.percentile(ch, 0.5)) if lo is None else lo
    hi = float(np.percentile(ch, 99.5)) if hi is None else hi
    v = np.clip((ch - lo) / max(hi - lo, 1e-12), 0.0, 1.0) ** gamma
    return to_img(1.0 - v if invert else v)


def upscale(img, factor):
    return img.resize((img.size[0] * factor, img.size[1] * factor), Image.NEAREST)


def fit(img, max_w=None, max_h=None, nearest=False):
    w, h = img.size
    s = 1.0
    if max_w and w > max_w:
        s = min(s, max_w / w)
    if max_h and h > max_h:
        s = min(s, max_h / h)
    if s < 1.0:
        img = img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.NEAREST if nearest else Image.LANCZOS)
    return img


def _font(size):
    for name in ("msyh.ttc", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def grid(images, cols, labels=None, pad=6, bg=(16, 18, 22), label_h=20):
    """Lay images out on a grid; all cells take the size of the largest image."""
    cw = max(i.size[0] for i in images)
    ch = max(i.size[1] for i in images)
    rows = (len(images) + cols - 1) // cols
    lh = label_h if labels else 0
    out = Image.new("RGB", (cols * (cw + pad) + pad, rows * (ch + lh + pad) + pad), bg)
    d = ImageDraw.Draw(out)
    f = _font(13)
    for k, im in enumerate(images):
        x = pad + (k % cols) * (cw + pad)
        y = pad + (k // cols) * (ch + lh + pad)
        if labels:
            d.text((x + 2, y + 2), labels[k], fill=(235, 215, 120), font=f)
        out.paste(im.convert("RGB"), (x, y + lh))
    return out


def data_uri(img, fmt="JPEG", quality=88):
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        mime = "image/jpeg"
    else:
        img.save(buf, "PNG", optimize=True)
        mime = "image/png"
    return "data:%s;base64,%s" % (mime, base64.b64encode(buf.getvalue()).decode("ascii"))


def open_image(path):
    return Image.open(path).convert("RGB")
