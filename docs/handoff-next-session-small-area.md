# Handoff — 小区域 PCG 交付（2026-09-24）

> **本文已更新。** 上一版的前提「本项目只有 `/Engine/BasicShapes`、没有建筑美术资产」**已经过时**：
> 迁移进来的 62 GB City Sample 美术与整套 PCG 库都在位（见 `references/migrated-citysample-library.md`）。
> 下面第一节是给下个 session 的提示词，后面是本次交付的结论与残留事项。

---

## 提示词（复制这一段）

```
用 city-sample-pcg-city-builder 技能，在本项目（E:\PCG_Claude）做 PCG 相关的工作。

## 先读这些（不要自己试错）
- `.claude/skills/city-sample-pcg-city-builder/SKILL.md`
- 它的 references/，尤其 `traps.md`（**33 条实测坑，第 30–33 条是 2026-09-24 花时间最多的四条**）、
  `stage-run-playbook.md` §3.2（切关卡崩溃的真实原因）、
  `migrated-citysample-library.md` §2.2/§2.3（地形是硬依赖 + 新区域走模板复制）
- `docs/city-sample-pcg-pipeline.md`（18 阶段流水线分析，参考项目是 E:\CitySample 5.8）

## 环境现状（已就绪）
- MCP 桥在 ws://127.0.0.1:8777，唯一工具是 `run_unreal_script`，脚本放 `Content/Python/`
- PCG / PCGPrimitives / CitySamplePCG 三个插件已在 uproject 启用
- **美术资产齐备**：`/Game/Building`、`/Game/Road`、`/Game/Megascans`、`/CitySamplePCG/` 都能直接用
- 已交付的区域见下面「本次交付」一节，别重复造

## 硬纪律（本次代价换来的）
1. **一个脚本一次往返**，且**改动编辑器的调用必须串行**，不要并行发。
2. **UObject 只放函数局部**，全局只放 JSON；切关卡前清理 + `gc.collect()`。
3. **截图约 1–2 分钟才落盘**，同一次调用里查文件必为 False；核验放到下一次调用。
4. **截图文件名一次性**，重拍要用新名字（`_rN`），别靠 exists 判断。
5. **重跑多阶段必须按阶段号顺序**，批量并发会丢下游内容；修好与否靠 `real_instances` 与定稿 census 比对。
6. **静默零点是常态**：没有报错不等于有产出，判定一律用数字（实例数 / 点数）或看图。
```

---

## 本次交付（2026-09-24）

**一个 600 m 的区域，用 Epic 的 18 张 City Sample 阶段图从模板复制出的新关卡里跑通。**

| 项 | 位置 |
|---|---|
| 关卡 | `/Game/PCGArea/L_SmallArea18`（由 `L_CitySamplePCG_Demo` 模板复制而来） |
| 验收报告 | `docs/pcg-small-area-18-stage-report.html`（自包含，36 张截图内嵌） |
| 实测数字 | `Tools/data/stage_census_smallarea.json`（18 阶段 real / debug 计数，git 跟踪） |
| 截图原件 | `Saved/Screenshots/WindowsEditor/sa_stage_*.png`（36 张，1.8–3.1 MB/张） |
| 复现脚本 | `Content/Python/pcg_sa_level.py`（模板复制）、`pcg_sa_shape.py`（相似变换）、`pcg_sa_run.py`（生成/机位/读数）、`pcg_sa_shots.py`（截图）、`pcg_sa_drive.py`（逐阶段驱动） |
| 报告工具 | `Tools/sa_manifest.py` + `build_pcg_stage_report.py`（支持每阶段两张图） |
| 测试 | `Tools/tests/`，23 passed（`C:\Python314\python.exe -m pytest Tools/tests -q`） |

**关键数字**：real 实例合计 **2,891,519**；debug 立方体合计 **2,449,359**（18 阶段跑完后实测）。
17 / 18 个阶段产出实例化几何；阶段 18（`PCG_5_2_OuterForest`）为 0，属实测为空的阶段。

## 已知限制（如实记录，未粉饰）

1. **600 m 区域里塞的是原尺寸的美术**，所以密度远高于原城：阶段 16（中央公园）1,806,980 个实例，
   对比 09-23 全尺寸 2 km 城的 965,022 —— 尺度缩了约 11 倍，实例数反而接近两倍。
   这是「相似变换而非重画样条」的必然结果，报告里写明了。
2. **一个 288 MB 的外部 Actor 未入库**：GitHub 单文件上限 100 MB，该文件按 GUID 路径被
   `.gitignore` 排除；仓库里的关卡打开后会缺这一个 Actor 的内容。报告 footer 有说明。
3. **`Content/PCGTest/` 下 6 个删不掉的测试资产**仍待人工在内容浏览器里删（沿用上一版的残留事项）。
4. **编辑器内的实时关卡才是完整的**（含那个 288 MB Actor）；本次会话结束后若重启，
   该 Actor 的内容只存在于磁盘、不在 git 里。

## 下一步的自然延伸

- **形状**：改 7 类样条（其实是 19 个带样条的 Actor）即可换城市形态；`pcg_sa_shape.py` 的相似变换
  可换成任意变换，图不用动。
- **密度**：若要接近原城观感，需要改图内参数（街区块尺寸、地块尺寸），
  这是 `docs/city-sample-pcg-pipeline.md` §14 列的「结构性改图」，要用户确认。
- **地形**：阶段 1 写的是 MeshPartition 网格地形；若要换地形方案，先读 §2.2 再动手。
