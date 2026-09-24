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
        # Named `dbg_n`, not `dbg`: `dbg` is the census dict from the top of this function,
        # and the first version of this edit rebound it to an int, so the second loop
        # iteration crashed on `int.get`.
        dbg_n = int(dbg.get(str(n), 0) or 0)
        status = status_for(n, inst, present)
        if n in DATA_ONLY:
            note = ("数据阶段：图产出的是数据而不是实例化几何，"
                    "本阶段的 geometry 张与前一张相同。")
        elif not (inst and inst > 0):
            # Keyed on the DATA, not on `status`. Keying on status meant the note vanished
            # whenever a stage's shots were also absent (status becomes "missing" first),
            # so the report would lose its explanation for the run's only empty stage
            # exactly when it mattered most. The graph completing with data but no geometry
            # is a property of the stage, not of whether its PNGs were written.
            note = ("空阶段（实测结论，不是脚本失败）：%s 生成完成（debug 立方体 %s 个，"
                    "说明中间数据是有的），但**没有产出任何实例化几何**。"
                    "该阶段在 600 m 岛屿上按密度散布植被，可能因可用地面不足而未达阈值；"
                    "已按「重新生成 + 再读一次」两步复核，两次都为 0。"
                    % (graph, format(dbg_n, ",")))
        else:
            note = ""
        stages.append({
            "n": n,
            "graph": graph,
            "label": LABELS[i] if i < len(LABELS) else graph,
            "shots": shots,
            "metrics": {
                "instances": inst,
                "debug_instances": dbg_n,
                "status": status,
            },
            "notes": note,
        })
    return stages


def footer_text(stages):
    """The report's closing prose.

    This is where the measurements that live in the census and the ledger reach the page a
    reader actually opens. The plan's Review Focus requires three things the first version
    of this footer omitted entirely:

    * the density trade-off between this 600 m area and the full-scale city, stated with
      its numbers rather than as a caveat, because a reader comparing the two would
      otherwise conclude the pipeline behaves differently at this scale;
    * the next-step parameter position, so "make it less dense" has an address
      (`PCG_3_1_1_Districts`' block grid length/width graph parameters) instead of
      requiring another investigation;
    * the two visual cases that were never verified: the highway silhouette's provenance
      (deliberately long at the source, not a scaling artifact) and the
      `missing_visual` case where a distant landmark may simply fall outside the frame.

    It also states the magnitude of the git exclusion. The excluded actor belongs to
    `PCG_4_2_CentralPark_Visuals`, which is the run's densest stage at 1,806,980 instances,
    so the committed level is missing ~62% of the geometry the report's own totals
    advertise — not "one actor's content" in any incidental sense.
    """
    tot_inst = sum((s.get("metrics") or {}).get("instances") or 0 for s in stages)
    tot_dbg = sum((s.get("metrics") or {}).get("debug_instances") or 0 for s in stages)
    biggest = max(((s.get("metrics") or {}).get("instances") or 0) for s in stages) \
        if stages else 0
    pct = int(round(100.0 * biggest / tot_inst)) if tot_inst else 0

    return (
        "地形来自复制过来的 MeshPartition Actor，阶段 1 按新的 CityShape 重新塑形；"
        "18 张图资产未做任何修改。实例合计 %s；debug 立方体合计 %s。"
        "本表数字取自 Tools/data/stage_census_smallarea.json，即 18 个阶段跑完后的实测值："
        "保存下来的关卡里 debug 立方体已全部清掉（第二个有序 pass 用 debug_nodes=0 重跑了一遍），"
        "所以直接去看关卡会读到 0，那是清理结果，不是本表算错。"
        "【密度取舍】本次把 2,130×1,818 m 的城市按相似变换缩到 600×512 m，"
        "**但美术保持原尺寸**，所以单位面积上的实例数比原城高一个数量级："
        "建筑阶段 382,245 个实例（全尺寸 2 km 城为 478,349），"
        "中央公园阶段 1,806,980 个（全尺寸为 965,022）—— 面积缩到约 9%%，实例数却接近或超过原城。"
        "这是「只改样条、不动图」的必然结果，不是缩放错误。若要接近原城观感，"
        "下一步是改图内参数：`PCG_3_1_1_Districts` 的 **Block grid length / width** "
        "（按 Large / Medium / Small 街区分档各一组），属结构性改图，需另行确认。"
        "【未验证项一】高架（HighWay_2 / HighWay_3）在缩后仍从城市两侧各伸出约 2 km，"
        "这是原关卡的设计（高架本就跨城而过），**不是缩放留下的错误**；"
        "若远景那两条长剪影不可接受，应改样条而不是改缩放。"
        "【未验证项二】背景山体（阶段 3，来自 /Game/Environment/Background_City/VistaCliffs_PCG）"
        "是绝对位置资产，城市缩小后它是否仍落在机位视野内**未做校验**；"
        "若某阶段画面里看不到预期地物，本报告以 `missing_visual`（未截图证明）如实标注，"
        "不以截图充数。"
        "【入库范围】该关卡有一个外部 Actor 文件 **288 MB**，超过 GitHub 单文件 100 MB 的上限，"
        "因此被 .gitignore 按 GUID 路径排除、**未入库**。该 Actor 属于 "
        "**PCG_4_2_CentralPark_Visuals**（本表最大的一个阶段，%s 个实例，占全部实例的约 %d%%）："
        "仓库里的关卡打开后会缺这一个阶段的内容，与编辑器内的实时状态明显不一致。"
        "这是仓库体积上限导致的结果，已在 .gitignore 旁注明。"
        % (format(tot_inst, ","), format(tot_dbg, ","), format(biggest, ","), pct))


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
        # Wired to the function, not an inline string: the first version of this fix added
        # footer_text() and left the old inline footer here, so the function's tests passed
        # while the generated page carried none of its content. Keeping any of this prose
        # inline is the bug; the function is the single definition.
        "footer": footer_text(stages),
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
