#!/usr/bin/env python
"""
build_stage_manifest.py — 为 City Sample 18 阶段 PCG 运行生成报告清单。

读取：
  * Saved/Reports/stage_census.json    每阶段实例数（实测）
  * Saved/Screenshots/WindowsEditor/   每阶段截图

输出给 Tools/build_pcg_stage_report.py 使用的清单，逐阶段标注
ok / empty / missing，如实反映哪些阶段有画面、哪些没有。

    python Tools/build_stage_manifest.py
    python Tools/build_stage_manifest.py --out Saved/Reports/stage_manifest.json
"""

import argparse
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CENSUS = os.path.join(REPO, "Saved", "Reports", "stage_census.json")
SHOTS = os.path.join(REPO, "Saved", "Screenshots", "WindowsEditor")

LABELS = [
    "地形", "背景建筑", "背景山体",
    "主塔轮廓", "中央公园轮廓", "街区划分", "道路",
    "高架", "地块", "地面", "剩余地块", "停车", "建筑",
    "屋顶", "主塔视觉", "中央公园视觉", "城市边缘",
    "外林",
]

# 这些阶段的图产出的是数据而不是实例化几何，所以画面里看到的是
# PCG debug 立方体（以及地形），而不是该阶段自己的网格。
DATA_ONLY = {1, 4, 5, 6}

NOTES = {
    1: "地形塑形。不产出实例化几何；画面为地形 + PCG debug 立方体。",
    4: "主塔轮廓样条。纯数据阶段。",
    5: "中央公园轮廓样条。纯数据阶段。",
    6: "街区细分。纯数据阶段：产出的是区域/点数据。",
    13: "规模最大的一站：建筑，约 478k 实例、约 986 个组件。",
    16: "最密集的一站：中央公园视觉，约 965k 实例。",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default=CENSUS)
    ap.add_argument("--shots", default=SHOTS)
    ap.add_argument("--out", default=os.path.join(REPO, "Saved", "Reports", "stage_manifest.json"))
    ap.add_argument("--title", default="City Sample PCG 18 阶段运行报告")
    args = ap.parse_args()

    with open(args.census, encoding="utf-8") as fh:
        census = json.load(fh)

    order = census["order"]
    real = census["real_instances"]
    dbg = census["debug_instances"]
    cams = census.get("camera_per_stage", {})

    stages = []
    missing = []
    for i, graph in enumerate(order):
        n = i + 1
        shot = os.path.join(args.shots, "pcg_stage_%02d_%s.png" % (n, graph))
        have = os.path.exists(shot)
        if not have:
            missing.append(graph)
        status = "ok" if have else "missing"
        if have and real[i] == 0:
            status = "empty"  # 有画面，但该阶段本身没有几何
        note = NOTES.get(n, "")
        cam = cams.get(str(n), "n/a")
        note = (note + "  机位：%s。" % cam).strip()
        stages.append({
            "n": n,
            "graph": graph,
            "label": LABELS[i] if i < len(LABELS) else graph,
            "shot": shot if have else "",
            "metrics": {
                "instances": real[i],
                "debug_instances": dbg[i],
                "status": status,
            },
            "notes": note,
        })

    man = {
        "title": args.title,
        "subtitle": ("来自迁移进来的 City Sample PCG 演示关卡，逐阶段隔离拍摄，"
                     "机位使用关卡自带的电影摄像机，并开启 PCG debug 可视化。"),
        "level": "/CitySamplePCG/Levels/L_CitySamplePCG_Demo",
        "stages": stages,
        "footer": ("全部阶段在内存中就地重算，关卡**从未保存**，因此每个图资产与包都保持出厂状态。"
                   "实例合计 %d；debug 立方体合计 %d。" % (sum(real), sum(dbg))),
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1, ensure_ascii=False)

    have = len(stages) - len(missing)
    print("manifest: %d stages, %d captured, %d missing -> %s"
          % (len(stages), have, len(missing), args.out))
    if missing:
        print("missing: %s" % ", ".join(missing))


if __name__ == "__main__":
    main()
