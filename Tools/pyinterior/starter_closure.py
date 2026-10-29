"""Copy the StarterContent PyInterior uses from the engine (E:/UnrealEngine/Samples/StarterContent) into Content/StarterContent
(the folder is gitignored; this script brings it back). Dependency closure by an offline byte scan of /Game package names,
as Tools/pyworld/ed_closure.py does for Electric Dreams.

Usage: python Tools/pyinterior/starter_closure.py [--copy]"""
import os
import re
import shutil
import sys

SRC = r"E:\UnrealEngine\Samples\StarterContent\Content"
DST = r"E:\PCG_Claude\Content"
SEEDS = (["StarterContent/Props/%s.uasset" % p for p in ("SM_Couch", "SM_Chair", "SM_TableRound", "SM_Shelf", "SM_Bush",
                                                          "SM_Lamp_Wall")] +
         ["StarterContent/Materials/%s.uasset" % m for m in ("M_Glass", "M_Wood_Oak", "M_Wood_Pine",
                                                             "M_Wood_Floor_Walnut_Polished", "M_Concrete_Tiles",
                                                             "M_Concrete_Poured")] +
         ["StarterContent/Textures/%s.uasset" % t for t in ("T_Wood_Oak_D", "T_Wood_Pine_D", "T_Wood_Floor_Walnut_D",
                                                            "T_Wood_Walnut_D", "T_Concrete_Tiles_D", "T_Concrete_Poured_D")])
REF = re.compile(rb"/Game/[A-Za-z0-9_\-/\.]+")


def package_file(pkg):
    rel = pkg[len("/Game/"):].split(".")[0]
    for ext in (".uasset", ".umap"):
        if os.path.isfile(os.path.join(SRC, rel + ext)):
            return rel + ext
    return None


def closure():
    todo, seen, missing = list(SEEDS), set(), set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        base = rel.rsplit(".", 1)[0]
        todo += [base + e for e in (".ubulk", ".uexp", ".uptnl") if os.path.isfile(os.path.join(SRC, base + e))]
        if not rel.endswith((".uasset", ".umap")):
            continue
        with open(os.path.join(SRC, rel), "rb") as fh:
            data = fh.read()
        for m in set(REF.findall(data)):
            pkg = m.decode("ascii", "ignore").rstrip("./")
            f = package_file(pkg)
            if f is None:
                missing.add(pkg)
            elif f not in seen:
                todo.append(f)
    return seen, missing


def main():
    seen, missing = closure()
    new, collide = [], []
    for rel in sorted(seen):
        dst = os.path.join(DST, rel)
        if not os.path.exists(dst):
            new.append(rel)
        elif open(dst, "rb").read() != open(os.path.join(SRC, rel), "rb").read():
            collide.append(rel)
    size = sum(os.path.getsize(os.path.join(SRC, r)) for r in seen)
    print("files %d (%.1f MB), new %d, collisions %d, unresolved %d" % (len(seen), size / 1e6, len(new), len(collide),
                                                                        len(missing)))
    for c in collide[:20]:
        print("  collides:", c)
    if "--copy" in sys.argv:
        if collide:
            sys.exit("refusing to copy: collisions")
        for rel in new:
            dst = os.path.join(DST, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(SRC, rel), dst)
        print("copied %d files" % len(new))


if __name__ == "__main__":
    main()
