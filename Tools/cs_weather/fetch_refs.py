# fetch_refs.py -- download 2000 px versions of the picked reference photos (Saved/Reports/cs_weather2/menu/picks.json)
# into Saved/Reports/cs_weather2/refs/full/<weather>_<n>.jpg, plus refs/full/index.json (title, page, licence, author).
#   C:\Python314\python.exe -P -E Tools/cs_weather/fetch_refs.py
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import commons_refs as cr  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PICKS = os.path.join(ROOT, "Saved", "Reports", "cs_weather2", "menu", "picks.json")
OUT = os.path.join(ROOT, "Saved", "Reports", "cs_weather2", "refs", "full")


def main():
    os.makedirs(OUT, exist_ok=True)
    picks = json.load(open(PICKS, encoding="utf-8"))
    titles = [x["title"] for v in picks.values() for x in v]
    res = cr._get({"action": "query", "titles": "|".join(titles), "prop": "imageinfo", "iiprop": "url|size",
                   "iiurlwidth": 2000})
    urls = {p["title"]: p["imageinfo"][0] for p in res["query"]["pages"] if p.get("imageinfo")}
    index = {}
    for key, lst in picks.items():
        for i, x in enumerate(lst):
            name = "%s_%d.jpg" % (key, i)
            path = os.path.join(OUT, name)
            ii = urls.get(x["title"])
            if ii is None:
                print("missing", x["title"])
                continue
            if not os.path.exists(path):
                cr.download(ii.get("thumburl") or ii["url"], path)
            index[name] = {k: x.get(k) for k in ("title", "page", "license", "license_url", "artist", "date", "fnumber",
                                                   "exposure", "iso", "bias", "ev100", "where", "place", "sun", "note")}
            print(name, os.path.getsize(path))
    json.dump(index, open(os.path.join(OUT, "index.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
