"""Dependency closure of Electric Dreams assets for PyWorld's vegetation (offline byte scan of package names).

Usage: python ed_closure.py [--copy]
Prints the files the seed folders need (by /Game package reference), their size per top folder, and every file
that already exists in E:/PCG_Claude/Content with different bytes (a collision). --copy copies the missing ones."""
import os
import re
import shutil
import sys

SRC = r"E:\ElectricDreams\ElectricDreamsEnv\Content"
DST = r"E:\PCG_Claude\Content"
PLANTS = ["EuropeanHornbeam", "Elderberry", "BeechFern", "Fern", "SilverLadyFern", "KikuyuGrass", "CloverVarieties",
          "GroundCover", "DeadLeaves", "Ivy", "EnglishIvy", "Periwinkle", "WhiteWindflower", "YellowArchangel",
          "LilyOfTheValley", "Crownbeard", "RedLachenalia", "PurpleShamrock", "CommonPurslane", "CustomMoss", "Lichen"]
ASSETS = ["MossyTree", "DeadTree", "FallenSpruceTree", "LargeFallenTree", "OldFallenTree", "TreeStump",
          "BirchTreeStump", "RottenTreeStump", "BrokenStump", "DryBranches", "OakBranch", "BrokenTreeBranch",
          "WoodenSticksAndTwigs", "MossyForestBoulder", "MossyForestRock", "MossyRocks", "LichenedForestBoulder",
          "TundraMossyBoulder", "NordicBoulder", "SmallStonesPack", "MossyForestRoots"]
SURFACES = ["MossyGrass", "DriedGrassOnDampSoil", "MossyRockyGround", "JungleGround", "NordicMoss", "RockCliff"]   # terrain layers
SEEDS = ["Megascans/3D_Plants/" + p for p in PLANTS] + ["Megascans/3D_Assets/" + a for a in ASSETS]     + ["Megascans/Surfaces/" + s for s in SURFACES]
# masters edited after the copy (Content/Python/pyworld_fix_aniso.py unhooks their Anisotropy input): not collisions
PATCHED = {"Custom/CustomMaterials/Materials/Master_Materials/Custom_MS_Master/M_MS_Default_Overwrite/M_MS_CustomDefault.uasset",
           "Custom/CustomMaterials/Materials/Master_Materials/M_MS_Default_Material_VT_DynamicLayering.uasset",
           "MSPresets/MS_Foliage_Material_LATEST/MasterMaterials/M_Foliage.uasset"}
REF = re.compile(rb"/Game/[A-Za-z0-9_\-/\.]+")


def files_under(rel):
    root = os.path.join(SRC, rel)
    for d, _s, fs in os.walk(root):
        for f in fs:
            if f.endswith((".uasset", ".umap", ".ubulk", ".uexp", ".uptnl")):
                yield os.path.relpath(os.path.join(d, f), SRC).replace("\\", "/")


def package_file(pkg):
    rel = pkg[len("/Game/"):].split(".")[0]
    for ext in (".uasset", ".umap"):
        if os.path.isfile(os.path.join(SRC, rel + ext)):
            return rel + ext
    return None


def companions(rel):
    base = rel.rsplit(".", 1)[0]
    return [base + e for e in (".ubulk", ".uexp", ".uptnl") if os.path.isfile(os.path.join(SRC, base + e))]


def closure():
    todo = [f for s in SEEDS for f in files_under(s)]
    seen, missing = set(), set()
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        if not rel.endswith((".uasset", ".umap")):
            continue
        todo += companions(rel)
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
    sizes, collide, new = {}, [], []
    for rel in sorted(seen):
        src = os.path.join(SRC, rel)
        dst = os.path.join(DST, rel)
        top = "/".join(rel.split("/")[:2])
        sizes[top] = sizes.get(top, 0) + os.path.getsize(src)
        if os.path.exists(dst):
            if rel in PATCHED:
                continue
            if os.path.getsize(dst) != os.path.getsize(src) or open(dst, "rb").read() != open(src, "rb").read():
                collide.append(rel)
        else:
            new.append(rel)
    for top, b in sorted(sizes.items()):
        print("%-40s %8.1f MB" % (top, b / 1e6))
    print("files %d, new %d, total %.2f GB" % (len(seen), len(new), sum(sizes.values()) / 1e9))
    print("collisions (exist with other bytes): %d" % len(collide))
    for c in collide[:40]:
        print("  ", c)
    unresolved = sorted(p for p in missing if not p.startswith(("/Game/__", )))
    print("unresolved /Game refs: %d" % len(unresolved))
    for p in unresolved[:30]:
        print("  ", p)
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
