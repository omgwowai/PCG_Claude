#!/usr/bin/env python
"""Record or check mtime+size of the official CitySample assets this work must not touch.

    python Tools/pypcg/baseline.py record    # writes Tools/data/pypcg_official_baseline.json
    python Tools/pypcg/baseline.py check     # exit 1 and list every changed file
"""
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "Tools", "data", "pypcg_official_baseline.json")
ROOTS = [os.path.join(REPO, "Plugins", "CitySamplePCG", "Content", "Levels"),
         os.path.join(REPO, "Plugins", "CitySamplePCG", "Content", "PCG"),
         os.path.join(REPO, "Plugins", "CitySamplePCG", "Content", "__ExternalActors__")]


def scan():
    out = {}
    for root in ROOTS:
        for d, _, files in os.walk(root):
            for f in files:
                if f.endswith((".uasset", ".umap")):
                    p = os.path.join(d, f)
                    st = os.stat(p)
                    out[os.path.relpath(p, REPO).replace("\\", "/")] = [int(st.st_mtime), st.st_size]
    return out


def main(argv):
    if argv[1:] == ["record"]:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(scan(), fh, indent=0, sort_keys=True)
        print("recorded", OUT)
        return 0
    if argv[1:] == ["check"]:
        with open(OUT, encoding="utf-8") as fh:
            base = json.load(fh)
        now = scan()
        changed = sorted(k for k in set(base) | set(now) if base.get(k) != now.get(k))
        for k in changed:
            print("CHANGED", k, base.get(k), now.get(k))
        print("%d files, %d changed" % (len(now), len(changed)))
        return 1 if changed else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
