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

18 张图之间靠 **Actor 引用**（按名字取上游阶段的输出）传递数据，不是靠资产路径。
实测有 4 个资产按名字引用了演示关卡里的**手绘样条 Actor**：

| 资产 | 引用的样条 Actor |
|---|---|
| `Examples/City/CitySample_Generator_Steps_1_Base` | `Artery_1`、`Artery_2` |
| `Examples/City/CitySample_Generator_Steps_2_Districts` | `CityShape` |
| `Levels/PCG/PCG_1_1_Terrain` | `Terrain_shaping_1` |
| `Levels/PCG/PCG_3_1_3_Highways` | `Highway_Width` |

→ **单拎一张图出来跑是没数据的。** 两条路：

1. 用搬来的演示关卡 `/CitySamplePCG/Levels/L_CitySamplePCG_Demo`（它带 194 个外部 Actor，
   含那 7 个手绘样条与 18 个 PCGVolume），从上游阶段开始跑；
2. 或在自己关卡里画等价样条，并按 Actor 名命名（名字必须对得上）。

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
| 运行时挂载 | **需要重启编辑器**（见 §5）后 `/CitySamplePCG` 才可见 |
