#!/usr/bin/env python
"""Town census + screenshots -> the manifest Tools/build_pcg_stage_report.py renders.

    C:/Python314/python.exe Tools/pypcg/town_manifest.py --out Saved/Reports/pypcg_town_manifest.json
    C:/Python314/python.exe Tools/build_pcg_stage_report.py --manifest Saved/Reports/pypcg_town_manifest.json --out docs/pypcg-town-report.html

Each stage's notes carry its key parameters (spec 5.2.5), so a reader can retune a step and rerun from it,
and its pass-2 result (Task 28): identical, or the two counts and the differing meshes (ruling T28a).
"""
import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_ONLY = (1, 4, 5, 6, 9)
_RESHOT = re.compile(r"_r\d+(\.png)$")


def _params(params):
    if not params:
        return ""
    return "; ".join("%s=%s" % (k, json.dumps(v, ensure_ascii=False)) for k, v in sorted(params.items()))


def _shot_path(shots_dir, name):
    """The screenshot on disk. A re-shoot is recorded under its claimed `_rN` name, and promote_variants()
    renames it onto the canonical name, so fall back to that."""
    if not name:
        return ""
    path = os.path.join(shots_dir, name)
    if not os.path.exists(path):
        canonical = os.path.join(shots_dir, _RESHOT.sub(r"\1", name))
        if os.path.exists(canonical):
            return canonical
    return path


def _pass2(r):
    if "deterministic" not in r:
        return ""
    if r["deterministic"]:
        return "第二遍：逐 mesh 计数与第一遍相同（%s）" % r.get("instances_pass2")
    v = r.get("variation") or {}
    meshes = ", ".join("%s %s→%s" % (m.rsplit("/", 1)[-1], a, b)
                       for m, (a, b) in sorted((v.get("differing_meshes") or {}).items()))
    return "第二遍：%s → %s（净差 %s，逐 mesh 绝对差 %s；%s）%s" % (
        v.get("pass1", r.get("instances")), v.get("pass2", r.get("instances_pass2")), v.get("net"),
        v.get("per_mesh_abs"), v.get("label", "不同"), ("；不同的 mesh：" + meshes) if meshes else "")


def build(census, shots_dir):
    stages = []
    for r in census["stages"]:
        path = _shot_path(shots_dir, r.get("shot"))
        shot = {"kind": "geometry", "path": path}
        if not path or not os.path.exists(path):
            shot["img_missing"] = "未捕获"
        status = "ok" if r["instances"] else ("empty" if r["stage"] in DATA_ONLY else "missing")
        if r.get("status") == "unmeasured":
            status = "empty"
        notes = "; ".join(r.get("notes") or [])
        if r["stage"] in DATA_ONLY and not r["instances"]:
            notes = (notes + "; " if notes else "") + "数据阶段：产出数据，几何与前一阶段相同。"
        if r.get("params"):
            notes = (notes + "; " if notes else "") + "参数：" + _params(r["params"])
        p2 = _pass2(r)
        if p2:
            notes = (notes + "; " if notes else "") + p2
        stages.append({"n": r["stage"], "graph": r["graph"], "label": r.get("title", ""), "shots": [shot],
                       "metrics": {"instances": r["instances"], "debug_instances": 0, "status": status},
                       "notes": notes})
    return {"title": "PyPCG 小城镇 · 18 步", "level": census["_level"],
            "subtitle": "每张 City Sample PCG 图的计算节点都已换成一个 Python 脚本，只留参数节点与引擎生成节点；"
                        "这 18 张瘦身图按飞书文档的 18 步顺序在 1 km 小镇里逐步生成，每步一张累计几何截图。",
            "footer": "生成的 Actor 中超过 GitHub 100 MB 单文件上限的未入库（见 .gitignore）；"
                      "pypcg_town.py 可按顺序重新生成。",
            "stages": stages}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default=os.path.join(REPO, "Tools", "data", "pypcg_town_census.json"))
    ap.add_argument("--shots", default=os.path.join(REPO, "Saved", "Screenshots", "WindowsEditor"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.census, encoding="utf-8") as fh:
        manifest = build(json.load(fh), a.shots)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)
    print("stages", len(manifest["stages"]), "missing shots",
          sum(1 for s in manifest["stages"] if s["shots"][0].get("img_missing")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
