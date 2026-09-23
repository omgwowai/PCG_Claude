# 搬进来的 City Sample 资产库（可复用）

> **2026-09-23 迁入。** 本文是「有哪些现成资产可用、怎么用」的索引。
> 在此之前，技能文档写的是这些资产**搬不过来**（依赖 CitySample 的美术），
> 现在它们**已经在磁盘上、已经挂载**，**优先用它们，不要重新自建**。

---

## 1. 挂载点与规模

| 挂载点 | 内容 | 来源 |
|---|---|---|
| `/CitySamplePCG/` | **插件**（Epic 的整套 PCG 流水线内容） | `Plugins/CitySamplePCG/` |
| `/Game/Building`、`/Game/Prop`、`/Game/Road`、`/Game/Megascans`、`/Game/Material`、`/Game/Environment`、`/Game/Textures`、`/Game/Vehicle`、`/Game/Crowd`、`/Game/Character`、`/Game/Effect`、`/Game/UI`、`/Game/Audio`、`/Game/Map` 等 | 建筑/道具/道路/植被/材质**美术资产** | `Content/` 下同名目录 |

规模实测：约 **62 GB / 26030 文件**，其中 `/Game` 侧约 24380 文件、插件侧 1650 文件。
拷贝经**逐字节校验**（9 个子树文件数与总字节数全部与源一致）。

---

## 2. 18 张城市阶段图（核心成品）

全部在 **`/CitySamplePCG/Levels/PCG/`**。它们就是 City Sample PCG 流水线的 18 个阶段，
按 `docs/city-sample-pcg-pipeline.md` 的数据流主线串起来：

| 组 | 图 |
|---|---|
| 地形/背景 | `PCG_1_1_Terrain`、`PCG_1_2_BG_Buildings`、`PCG_1_3_BG_Mountains` |
| 地标轮廓 | `PCG_2_1_MainTower_Footprint`、`PCG_2_2_CentralPark_Footprint` |
| 骨架 | `PCG_3_1_1_Districts`、`PCG_3_1_2_Roads`、`PCG_3_1_3_Highways`、`PCG_3_1_4_Lots` |
| 地面/剩余地块 | `PCG_3_2_1_Ground`、`PCG_3_2_2_LeftOverLots`、`PCG_3_2_3_Parkings` |
| 建筑/屋顶 | `PCG_3_3_1_Buildings`、`PCG_3_3_2_Rooftops` |
| 视觉收尾 | `PCG_4_1_MainTower_Visuals`、`PCG_4_2_CentralPark_Visuals` |
| 城市边缘/外林 | `PCG_5_1_CityEdge`、`PCG_5_2_OuterForest` |

**怎么用**：`unreal.load_asset("/CitySamplePCG/Levels/PCG/PCG_3_3_1_Buildings")` 拿到 `PCGGraph`，
挂到任意 `PCGVolume` 的 `PCGComponent`（`set_graph` + `activate(True)` + `generate_local`）。

### 2.1 硬约束：这些图**不是自含的**

18 张图之间靠**上一阶段的数据**传递，通道有两种，都**不是资产路径引用**：

**(a) 图用户参数（已实测）**
`PCG_3_1_3_Highways` 里有一个 `PCGGenericUserParameterGetSettings` 节点，
名为 `GetParam_HighwayWidth`，其 `property_path = "Highway_Width"`；
它的 tooltip 原文是 *"Width is driven by the Highway_Width graph parameter."*。
`PCG_1_1_Terrain` 顶层 20 个节点 = 15 个子图 + 3 个数学 + **2 个用户参数读取**
（它自己不含任何 Actor 筛选节点，"Get Terrain_shaping_1 Spline" 这个名字在**子图内部**）。

**(b) 演示关卡里的 Actor 标签（已实测）**
`L_CitySamplePCG_Demo` 的 194 个外部 Actor 里，这些名字是**作为 Tag 存在**的：

| 名字 | 出现次数 | 用途 |
|---|---|---|
| `Terrain_shaping` | 2（**无 `_1` 后缀**） | 地形形变轮廓 |
| `CityShape` | 2 | 城市边界 |
| `Artery_1` / `Artery_2` / `Artery_3` | 各 2 | 三条主干道 |
| `Highway_Width` / `Highway` / `Highway_Lane` … | 1 / 85 / … | 高架及其宽度与车道 |
| `MainTowerPark` / `LandmarkPark` | 2 / 1 | 地标园区 |

> ⚠️ **命名细节**：图里写的是 `Terrain_shaping_1`，而关卡 Actor 的 Tag 是
> `Terrain_shaping`（没有 `_1`）。别把这两个当成同一个字符串。

→ **单拎一张图出来挂到空关卡上是没数据的。** 两条路：

1. 用搬来的演示关卡 `/CitySamplePCG/Levels/L_CitySamplePCG_Demo`（带 194 个外部 Actor、
   那 7 个手绘样条、以及 18 个 PCGVolume），从上游阶段开始跑；
2. 或在自己关卡里画等价样条，并**同时**把 Actor 打上与参数同名的 Tag，
   （参数名与 Tag 名必须对得上，见上表）。

反过来，**不依赖上游阶段的图是可以单独跑的** —— 见 §3.1 的实测。

---

## 3. 27 个建筑样式资产

在 **`/CitySamplePCG/PCG/DataAssets/Buildings/<CODE>/`**，每个样式码一个 `SGD_<CODE>_A`：

| 地区 | 样式码 | 数量 |
|---|---|---|
| 芝加哥 | `CHA` `CHB` `CHC` `CHD` `CHE` `CHF` `CHG` `CHH` `CHI` `CHJ` | 10 |
| 纽约 | `NYAA` `NYAB` `NYAC` `NYAD` `NYAE` `NYAF` | 6 |
| 纽约 | `NYG` `NYGA` `NYH` | 3 |
| 魁北克 | `QBA` `QBAA` | 2 |
| 旧金山 | `SFA` `SFB` `SFC` `SFD` `SFE` `SFJ` | 6 |
| | | **合计 27** |

同目录下还有 **240 个形状语法规则** `RULE_<CODE>_L##`（每样式码按层高分级，
`L1`…`L21`），以及 `DataAssets/{RoofTops,Roads,Plazas,Piers}` 下 **220 个**屋顶/道路/广场/码头规则。

**怎么用**：`Assign_BldgStyles_per_MinWallWidth` 与 `AssignBuildingShape`
（都在 `/CitySamplePCG/PCG/`）是入口；样式资产本身由形状语法消费。

> 注意：27 个样式资产的**闭包约 9.15 GB**（主要是 `/Game/Building` 的 8.9 GB 建筑美术 +
> 插件内 84 个网格）。只取样式码子集时，`/Game/Building/CH|NY|QB|SF` 要一并带上。

### 3.1 实测：搬来的图**真的能生成真实建筑**（2026-09-23）

这是"可复用"的实证，不是"能加载"的推断。做法见
`Content/Python/pcg_reuse_test_setup.py`（阶段 A）+ `pcg_reuse_test_read.py`（阶段 B）：

1. 在离交付区 20 km 处 spawn 一个临时 PCGVolume（**避免污染已交付的 3×3 区域**）；
2. 给它 brush 8000×8000×4000（全尺寸 → 局部 ±4000 / ±2000）；
3. `set_graph("/CitySamplePCG/Examples/Building/Building_Staggered_HShape")`；
4. `activate(True)` → `generate_local(True)`（**不 activate 就是静默零点**，见 `traps.md` 18）；
5. **下一次调用**再读，然后 cleanup + destroy（实测 `test_volumes_remaining=0`）。

结果：

| 指标 | 数值 |
|---|---|
| 图规模 | 18 节点 / 24 边 |
| ISM 组件数 | **151** |
| 总实例数 | **3129** |
| 其中用 `/Game` 美术的实例 | **3129（100%）** |

消费到的是**真实 City Sample 建筑构件**，不是代理盒：`Kit_Bldg_CHC_L01_A` … `L15_A` 的
`Wall_01/02/03/04`、`CornerEx/CornerIn`、`Entrance`、decal 变体，外加屋顶与立面道具
（`SM_roof_pipe_a_N1`、`SM_roof_window_N1`、`SM_BLDG_Prop_BA_Awning_A01_N1`、
`SM_BLDG_Prop_Lamp_Wall_A01_N1`、`SM_Scaffolding_metal_N1` …）。单构件最多被复用到 **295 次**。

**两个值得记住的观察**：

1. **`get_generated_graph_output()` 读到 0 个 tagged data，却有 3129 个实例。**
   说明"该图把数据写进输出 pin"与"该图 spawn 了几何"**不是一回事** ——
   这张图在中间就 spawn 掉了，输出 pin 是空的。
   → **验证 spawn 型图必须数 ISM 实例，不能只读输出点数。** 这条同时补充了
   `SKILL.md`「如何验证」一节。
2. 该图**不依赖上游阶段**（自含），所以能这样单独跑。它是 `Examples/` 下的示例，
   与 18 张阶段图不同 —— 拿不准时先试跑一次，别假设。

---

## 4. 其他现成内容

| 路径 | 内容 |
|---|---|
| `/CitySamplePCG/Examples/City/CitySample_Generator_Steps_1_Base` … `_7_CitySample_Contour` | **7 段串联的入门图**，最贴近「分阶段」教法 |
| `/CitySamplePCG/Examples/City/City_Circular_1km_2_arteries*` | 完整 1km 圆城示例（含多个人工编辑变体） |
| `/CitySamplePCG/Examples/Building/` | 9 个建筑体量示例（L/H/C/X/Hexagon/Square 等形状） |
| `/CitySamplePCG/Examples/Plaza/` | 广场/树阵/长椅示例 |
| `/CitySamplePCG/PCG/AssignBuildingShape`、`SetComplexBuildings`、`GridPartition`、`Crosswalks`、`Intersection_solving` 等 | 管线里的功能性子图 |
| `/CitySamplePCG/PCG/Primitives/Buildings/` | 建筑专用子图（`BDF_BuildingFromSpline`、`LoadCitySampleData`、`SpawntoBuildingActor` …） |

**注意区分**：引擎自带的 `/PCGPrimitives/`（86 个通用原语）与这里搬来的
`/CitySamplePCG/PCG/Primitives/` 是**两套不同的库**。通用原语用前者，建筑专用用后者。

---

## 5. 环境前置（已配好，2026-09-23）

`PCG_Claude.uproject` 现在启用了 15 个插件。其中为本次迁移新增的：

```
CitySamplePCG                        (content-only，无 Source/Binaries，不需编译)
GeometryScripting                    /Script/GeometryScripting        (14 文件引用)
PCGGeometryScriptInterop             /Script/PCGGeometryScriptInterop (6 文件引用)
PCGMeshPartitionInterop              /Script/PCGMeshPartitionInterop  (23 文件引用)
PCGPrimitives_MeshPartitionInterop   (content-only)
MeshPartition                        被 PCGMeshPartitionInterop 依赖
MeshTerrainMode                      被 PCGPrimitives_MeshPartitionInterop 依赖
ToolsetRegistry                      1 文件引用
```

**从插件的 `.uplugin` 里删掉了两个**：`ModelContextProtocol` 与 `AllToolsets`。
依据是对全部 13061 个 `.uasset`/`.umap` 的字节扫描——**零**引用
`/Script/ModelContextProtocol`、`/Script/AllToolsets`、`/Script/ProceduralVegetation`。
前者会额外起一个 HTTP MCP 服务（默认端口 8000），与本项目已有的
`UnrealMcpBridge`（8777）并存；后者会连带启用 21 个 toolset 插件。
两者都是纯编辑器工具、不含内容，删掉不减功能。原始描述文件保留为
`Plugins/CitySamplePCG/CitySamplePCG.uplugin.orig`。

**新增内容只有挂了新插件才可见**：插件挂载点 `/CitySamplePCG/` 只在**编辑器启动时**注册，
**改了 `.uproject` 必须重启编辑器**。而 `/Game` 侧的美术**不需要重启**——
实测对 `/Game` 做一次 `AssetRegistry.scan_paths_synchronous` 后，
注册资产数从 2516 涨到 147467，且 `BLDG_Volume_C` 等能正常 `load_asset` 成 `StaticMesh`。

---

## 6. 版本控制策略

**这 62 GB 不进 git。** 原因实测：

- 未配置 git-lfs（无 `.gitattributes`）；
- **48 个文件超过 100 MB**，GitHub 单文件硬上限就是 100 MB，最大一个 **719 MB**
  （`Content/Building/Texture/Brick/T_Brick_PackedB.uasset`）。

根 `.gitignore` 已加入对应规则（`/Content/Building/` 等 27 条）。
**重新拉取用**：

```powershell
.\Tools\sync-citysample-assets.ps1            # 从 E:\CitySample 5.8 robocopy 并逐字节校验
.\Tools\sync-citysample-assets.ps1 -WhatIf    # 只报告不写入
```

脚本结尾会自查文件数与总字节数是否与源一致，不一致即抛错。

---

## 7. 验证状态

| 项 | 证据 |
|---|---|
| 拷贝完整性 | 9 个子树文件数与总字节数全部等于源（robocopy 后逐项核对） |
| `/Game` 美术可加载 | 对 `/Game` 重扫后注册数 2516 → 147467；`load_asset` 实测返回 `StaticMesh` |
| 插件描述文件 | JSON 合法；15 个插件名全部能在 897 个 `.uplugin` 里找到 |
| 27 样式 / 18 图 | 文件在磁盘上：27 个 `SGD_*.uasset`、18 个 `PCG_*.uasset` |
| **运行时挂载** | 重启后 `/CitySamplePCG` 已挂载；`list_assets` 得 1648；`/Game` 总注册 147459 |
| **18 图可加载** | 全部 18 个 `load_asset` 返回 `PCGGraph`（规模 3…210 节点，见验证脚本输出） |
| **27 样式可加载** | 全部 27 个返回 `BP_ShapeGrammarDefinition_C` |
| **8 个新插件挂载** | 日志各 1 条 `Mounting Engine plugin …`；**0 条**加载失败 |
| **裁剪生效** | `ModelContextProtocol` / `AllToolsets` 的 `Mounting` 条目数 = **0** |
| **可复用（端到端）** | 用 `Building_Staggered_HShape` 生成 **151 ISM / 3129 实例，100% 用 `/Game` 美术**（§3.1） |
| **交付物未受影响** | 迁移+重启后回归：3×3 区域仍 12 节点 12 边、41 实例（`pcg_postmigration_regression.py`） |

复现命令（脚本都在 `Content/Python/`，用 `run_unreal_script` 调用）：

```
pcg_migration_verify.py            # 挂载 + 18 图 + 27 样式 的验收
pcg_reuse_test_setup.py            # 复用实测 阶段 A（会 spawn 临时 Volume 并生成）
pcg_reuse_test_read.py             # 复用实测 阶段 B（读数并自清理）
pcg_postmigration_regression.py    # 已交付 3×3 区域的回归
```

> 后三个会**改动关卡**（前两个 spawn/销毁临时 Actor）。跑完**不要保存关卡**，
> 否则测试残留会被提交。`pcg_reuse_test_setup.py` 自身刻意不保存。
