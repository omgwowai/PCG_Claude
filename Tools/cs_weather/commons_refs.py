# commons_refs.py -- search Wikimedia Commons for reference photos of each candidate weather, keep the ones with a
# usable licence and EXIF (date, exposure), download 640 px thumbnails and draw one numbered contact sheet per weather.
#
#   C:\Python314\python.exe -I Tools/cs_weather/commons_refs.py search [--only key,key]
#       -> Saved/Reports/cs_weather2/refs/cand/<key>/NN.jpg, cand/<key>.json, sheet_<key>.jpg
#
# EV100 = log2(N^2 / t) - log2(ISO / 100) from the EXIF exposure triangle (exposure bias reported separately).
import argparse
import io
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "Saved", "Reports", "cs_weather2", "refs")
API = "https://commons.wikimedia.org/w/api.php"
UA = "PCGClaudeWeatherRefs/0.1 (internal rendering research; python-urllib)"

def _cat(name):
    return 'incategory:"%s"' % name


# key -> {"q": [search strings], optional "hours": (from, to) local EXIF hour, "months": [..]}
QUERIES = {
    "clear_noon": {"q": [_cat("Chicago skyline"), _cat("Skylines of Manhattan"), "skyline clear sky"],
                   "hours": (10, 15), "months": [4, 5, 6, 7, 8, 9]},
    "golden_hour": {"q": [_cat("Sunset skylines"), _cat("Sunrise skylines"), _cat("Golden hour"),
                          _cat("Sunset skylines of Toronto")]},
    "blue_hour": {"q": [_cat("Blue hour skylines"), _cat("Belt of Venus"), _cat("Earth's shadow")]},
    "overcast": {"q": [_cat("Overcast"), "overcast skyline", "overcast skyscrapers", _cat("June Gloom")]},
    "fog": {"q": [_cat("Fog in Chicago"), _cat("Fog in New York City"), _cat("Fog in San Francisco"),
                  _cat("Fog in Seattle")]},
    "haze": {"q": [_cat("Smog in Beijing"), _cat("Smog in Los Angeles"), _cat("Haze")]},
    "storm": {"q": [_cat("Shelf clouds"), _cat("Cumulonimbus clouds"), _cat("Cumulonimbus incus"),
                    _cat("Arcus clouds")]},
    "dust": {"q": [_cat("2009 Australian dust storm"), _cat("Haboobs"), _cat("Dust storms")]},
    "cirrus": {"q": [_cat("Cirrus clouds"), _cat("Cirrus fibratus clouds"), _cat("Cirrus uncinus clouds")]},
    # elevated views (observation decks): the demo camera looks over the city from ~300 m
    "noon_aerial": {"q": [_cat("Views from Willis Tower"), _cat("Views from Skydeck Chicago at Willis Tower"),
                          _cat("Views from the Willis Tower"), _cat("Views from 875 North Michigan Avenue"),
                          _cat("Views from the Empire State Building in the 2020s"),
                          _cat("Views from the Empire State Building in the 2000s")],
                    "hours": (10, 15), "months": [5, 6, 7, 8, 9]},
    "aerial_any": {"q": [_cat("Views from Willis Tower"), _cat("Views from Skydeck Chicago at Willis Tower"),
                         _cat("Views from the Willis Tower"), _cat("Views from 875 North Michigan Avenue")]},
}
OK_LICENSES = re.compile(r"^(CC BY(-SA)? [0-9.]+|CC0|Public domain|PD|Attribution)", re.I)


def _fetch(url, tries=6):
    """GET with the Wikimedia-required User-Agent; backs off on 429 / 5xx (honours Retry-After)."""
    import urllib.error
    delay = 5.0
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
            ra = exc.headers.get("Retry-After") if exc.headers else None
            wait = float(ra) if ra and ra.isdigit() else delay
            print("  http %d, waiting %.0f s" % (exc.code, wait), file=sys.stderr, flush=True)
            time.sleep(wait)
            delay = min(delay * 2, 120.0)


def _get(params):
    q = dict(params, format="json", formatversion="2")
    url = API + "?" + urllib.parse.urlencode(q)
    data = json.loads(_fetch(url).decode("utf-8"))
    time.sleep(1.0)
    return data


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    m = re.match(r"^(-?[0-9.]+)\s*/\s*([0-9.]+)$", s)
    if m:
        d = float(m.group(2))
        return float(m.group(1)) / d if d else None
    try:
        return float(s)
    except ValueError:
        return None


def _meta_list(md):
    out = {}
    for item in md or []:
        name, val = item.get("name"), item.get("value")
        if isinstance(val, list):
            continue
        out[name] = val
    return out


def _strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _date_ok(date, spec):
    hours, months = spec.get("hours"), spec.get("months")
    if not hours and not months:
        return True
    m = re.match(r"^(\d{4})[:-](\d{2})[:-](\d{2})[ T](\d{2}):", date or "")
    if not m:
        return False
    if months and int(m.group(2)) not in months:
        return False
    if hours and not (hours[0] <= int(m.group(4)) < hours[1]):
        return False
    return True


def search(key, spec, limit=50):
    seen, cands = set(), []
    for q in spec["q"]:
        res = _get({"action": "query", "generator": "search", "gsrsearch": q + " filetype:bitmap filew:>1500",
                    "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo",
                    "iiprop": "url|size|mime|extmetadata|metadata", "iiurlwidth": 640})
        for page in (res.get("query") or {}).get("pages", []):
            title = page["title"]
            if title in seen or not page.get("imageinfo"):
                continue
            seen.add(title)
            ii = page["imageinfo"][0]
            if ii.get("mime") != "image/jpeg":
                continue
            em = {k: (v or {}).get("value") for k, v in (ii.get("extmetadata") or {}).items()}
            lic = _strip_html(em.get("LicenseShortName"))
            if not OK_LICENSES.match(lic or ""):
                continue
            ex = _meta_list(ii.get("metadata"))
            date = ex.get("DateTimeOriginal") or _strip_html(em.get("DateTimeOriginal"))
            if not _date_ok(date, spec):
                continue
            n, t, iso = _num(ex.get("FNumber")), _num(ex.get("ExposureTime")), _num(ex.get("ISOSpeedRatings"))
            ev = None
            if n and t and iso:
                ev = math.log2(n * n / t) - math.log2(iso / 100.0)
            cands.append({
                "title": title, "query": q, "page": ii.get("descriptionurl"), "url": ii.get("url"),
                "thumb": ii.get("thumburl"), "w": ii.get("width"), "h": ii.get("height"),
                "license": lic, "license_url": em.get("LicenseUrl"), "artist": _strip_html(em.get("Artist"))[:120],
                "desc": _strip_html(em.get("ImageDescription"))[:300],
                "date": date,
                "fnumber": n, "exposure": t, "iso": iso, "bias": _num(ex.get("ExposureBiasValue")),
                "focal": _num(ex.get("FocalLength")), "model": ex.get("Model"),
                "gps": [ex.get("GPSLatitude"), ex.get("GPSLatitudeRef"), ex.get("GPSLongitude"),
                        ex.get("GPSLongitudeRef")] if ex.get("GPSLatitude") else None,
                "ev100": round(ev, 2) if ev is not None else None,
            })
    # photos with an exposure triangle first, then by resolution
    cands.sort(key=lambda c: (c["ev100"] is None, -(c["w"] or 0)))
    return cands


def download(url, path):
    data = _fetch(url)
    with open(path, "wb") as f:
        f.write(data)
    time.sleep(0.5)


def sheet(key, cands, folder, max_n=24):
    from PIL import Image, ImageDraw, ImageFont
    cell_w, cell_h, cols = 360, 270, 4
    n = min(len(cands), max_n)
    rows = max(1, math.ceil(n / cols))
    img = Image.new("RGB", (cols * cell_w, rows * (cell_h + 34)), (24, 24, 24))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for i, c in enumerate(cands[:n]):
        p = os.path.join(folder, "%02d.jpg" % i)
        if not os.path.exists(p):
            continue
        try:
            im = Image.open(p).convert("RGB")
        except Exception:
            continue
        im.thumbnail((cell_w - 6, cell_h - 6))
        x, y = (i % cols) * cell_w, (i // cols) * (cell_h + 34)
        img.paste(im, (x + 3, y + 3))
        label = "%02d %s ev%s" % (i, (c.get("date") or "")[:10], c["ev100"] if c["ev100"] is not None else "-")
        d.text((x + 4, y + cell_h), label, fill=(255, 230, 120), font=font)
        d.text((x + 4, y + cell_h + 16), c["title"][5:52], fill=(200, 200, 200), font=font)
    img.save(os.path.join(OUT, "sheet_%s.jpg" % key), quality=85)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["search"])
    ap.add_argument("--only", default="")
    ap.add_argument("--max", type=int, default=32)
    a = ap.parse_args()
    keys = [k for k in QUERIES if not a.only or k in a.only.split(",")]
    os.makedirs(os.path.join(OUT, "cand"), exist_ok=True)
    for key in keys:
        cands = search(key, QUERIES[key])[: a.max]
        folder = os.path.join(OUT, "cand", key)
        os.makedirs(folder, exist_ok=True)
        for i, c in enumerate(cands):
            p = os.path.join(folder, "%02d.jpg" % i)
            if not os.path.exists(p) and c.get("thumb"):
                try:
                    download(c["thumb"], p)
                    time.sleep(0.15)
                except Exception as exc:
                    c["download_error"] = str(exc)[:200]
        with open(os.path.join(OUT, "cand", key + ".json"), "w", encoding="utf-8") as f:
            json.dump(cands, f, indent=1, ensure_ascii=False)
        sheet(key, cands, folder, a.max)
        with_ev = sum(1 for c in cands if c["ev100"] is not None)
        print("%-12s %2d candidates, %2d with EXIF exposure" % (key, len(cands), with_ev), flush=True)


if __name__ == "__main__":
    main()
