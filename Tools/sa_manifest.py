#!/usr/bin/env python
"""sa_manifest.py — build the report manifest for the small-area 18-stage run.

Two shots per stage, not one: `_debug.png` (this stage's flagged nodes, isolated)
and `_geometry.png` (the city accumulated through stage N). Both are required for
a stage to count as captured.

    python Tools/sa_manifest.py \\
        --census Tools/data/stage_census_smallarea.json \\
        --shots Saved/Screenshots/WindowsEditor \\
        --out Saved/Reports/sa_manifest.json

WHY THE DEFAULT CENSUS IS THE TRACKED FILE, NOT Saved/Reports/sa_census.json:

`Saved/` is gitignored, so a census living there cannot reproduce this report from a
clean clone, and the live one is also easy to clobber — it holds the run's numbers only
until some later `census` phase overwrites it with whatever state the editor is in at
that moment (which happened twice during this run). `Tools/data/stage_census_smallarea.json`
is the settled, git-tracked record of what the 18 stages produced, including the
2,449,359 debug cubes, and it is what the report's metrics must present. The saved level
itself now reports 0 debug cubes everywhere because a second ordered pass regenerated
every stage with debug_nodes=0; that difference is explained in the tracked file's own
`_note`. Use --census to point anywhere else.
"""

import argparse
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_BYTES = 50000

DEFAULT_CENSUS = os.path.join(REPO, "Tools", "data", "stage_census_smallarea.json")
FALLBACK_CENSUS = os.path.join(REPO, "Saved", "Reports", "sa_census.json")

ORDER = ["PCG_1_1_Terrain", "PCG_1_2_BG_Buildings", "PCG_1_3_BG_Mountains",
         "PCG_2_1_MainTower_Footprint", "PCG_2_2_CentralPark_Footprint",
         "PCG_3_1_1_Districts", "PCG_3_1_2_Roads", "PCG_3_1_3_Highways",
         "PCG_3_1_4_Lots", "PCG_3_2_1_Ground", "PCG_3_2_2_LeftOverLots",
         "PCG_3_2_3_Parkings", "PCG_3_3_1_Buildings", "PCG_3_3_2_Rooftops",
         "PCG_4_1_MainTower_Visuals", "PCG_4_2_CentralPark_Visuals",
         "PCG_5_1_CityEdge", "PCG_5_2_OuterForest"]

LABELS = ["地形", "背景建筑", "背景山体", "主塔轮廓", "中央公园轮廓", "街区划分",
          "道路", "高架", "地块", "地面", "剩余地块", "停车", "建筑", "屋顶",
          "主塔视觉", "中央公园视觉", "城市边缘", "外林"]

# Stages whose graphs emit data rather than instanced geometry, so a zero instance
# count is correct and their geometry shot repeats the previous stage's picture.
DATA_ONLY = {1, 4, 5, 6}

KINDS = ("debug", "geometry")


def shot_name(n, graph, kind):
    return "sa_stage_%02d_%s_%s.png" % (n, graph, kind)


def status_for(n, instances, shots_present):
    if not shots_present:
        return "missing"
    if instances and instances > 0:
        return "ok"
    return "empty" if n in DATA_ONLY else "empty_expected_geometry"


def build_stages(census_path, shots_dir, order=None, min_bytes=MIN_BYTES):
    with open(census_path, encoding="utf-8") as fh:
        census = json.load(fh)
    order = list(order or census.get("order") or ORDER)
    real = census.get("real_instances", {})
    dbg = census.get("debug_instances", {})

    stages = []
    for i, graph in enumerate(order):
        n = i + 1
        shots = []
        for kind in KINDS:
            name = shot_name(n, graph, kind)
            p = os.path.join(shots_dir, name)
            if os.path.exists(p) and os.path.getsize(p) >= min_bytes:
                shots.append({"kind": kind, "path": p,
                              "bytes": os.path.getsize(p)})
            else:
                shots.append({"kind": kind, "img_missing": p})
        present = all("path" in s for s in shots)
        inst = int(real.get(str(n), 0) or 0)
        stages.append({
            "n": n,
            "graph": graph,
            "label": LABELS[i] if i < len(LABELS) else graph,
            "shots": shots,
            "metrics": {
                "instances": inst,
                "debug_instances": int(dbg.get(str(n), 0) or 0),
                "status": status_for(n, inst, present),
            },
            "notes": ("数据阶段：图产出的是数据而不是实例化几何，"
                      "本阶段的 geometry 张与前一张相同。" if n in DATA_ONLY else ""),
        })
    return stages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default=DEFAULT_CENSUS)
    ap.add_argument("--shots", default=os.path.join(
        REPO, "Saved", "Screenshots", "WindowsEditor"))
    ap.add_argument("--out", default=os.path.join(
        REPO, "Saved", "Reports", "sa_manifest.json"))
    ap.add_argument("--title", default="City Sample PCG 18 阶段 · 600 m 小区域")
    args = ap.parse_args()

    census_path = args.census
    if not os.path.exists(census_path) and os.path.exists(FALLBACK_CENSUS):
        print("note: %s missing, falling back to %s" % (census_path, FALLBACK_CENSUS))
        census_path = FALLBACK_CENSUS

    stages = build_stages(census_path, args.shots)
    man = {
        "title": args.title,
        "subtitle": ("由 demo 关卡模板复制出的 600 m 区域，逐阶段生成并隔离拍摄；"
                     "每阶段两张：PCG debug 与累计几何。美术全部复用 City Sample 资产。"),
        "level": "/Game/PCGArea/L_SmallArea18",
        "census": census_path,
        "stages": stages,
        "footer": ("地形来自复制过来的 MeshPartition Actor，阶段 1 按新的 CityShape "
                   "重新塑形；18 张图资产未做任何修改。实例合计 %d；debug 立方体合计 %d。"
                   % (sum(s["metrics"]["instances"] for s in stages),
                      sum(s["metrics"]["debug_instances"] for s in stages))),
    }
    out = args.out if os.path.isabs(args.out) else os.path.join(REPO, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1, ensure_ascii=False)

    n_shots = sum(len([s for s in st["shots"] if "path" in s]) for st in stages)
    n_stages = sum(1 for st in stages if all("path" in s for s in st["shots"]))
    print("manifest: %d stages, %d/%d complete, %d shots -> %s"
          % (len(stages), n_stages, len(stages), n_shots, out))
    bad = [st["n"] for st in stages if not all("path" in s for s in st["shots"])]
    if bad:
        print("stages missing a shot: %s" % ", ".join(map(str, bad)))


if __name__ == "__main__":
    main()
