# 新增建筑样式码 `TL`（3 层，网格对齐 CHA）——设计文档

- 日期：2026-09-24
- 状态：待用户复核
- 项目：`E:\PCG_Claude`（UE 5.8.2 源码版引擎 `E:\UnrealEngine`）

---

## 1. 目标与非目标

### 1.1 目标

新增一个建筑样式码 **`TL`**，配一套**自建的模块化美术套件**（Blender 建模 → 导入 UE），
使 `TL` 能被 CitySample 的 PCG building 流程**当作一种可选建筑样式生成出来**，
供后续场景使用。

首期规模限定为**最小可跑通：3 层**（L1 入口层 + L2/L3 标准层），
模块网格与尺寸体系**对齐 CHA**（芝加哥 A 型），以便直接复用其语法串与数值。

### 1.2 非目标

- 不做 `TL` 的 21 层满配（留作后续按层扩容）。
- 不改动 CitySample 的 18 阶段流水线结构（只改样式码白名单与 BDF 数据，不动图的拓扑）。
- 不做建筑内部、不做法线/贴图以外的额外美术规格（LOD/碰撞首期只做到能生成）。
- 不为 `TL` 建独立的成品关卡或交付区。

---

## 2. 关键事实（全部实测，2026-09-24）

这一节是后面所有决策的依据。**其中两条推翻了先前的认知，必须先记住。**

### 2.1 `.bdf` 是什么，以及它在 UE 侧的处境

`Content/Building/HDA/Bldg/BDF/` 下有 **30 个 `.bdf`** 文件（27 样式码 + `Props_Library`
+ `STK_primary` + `BLDG_ECO_primary`），是 **Houdini 的 Building Definition File（JSON）**。

顶层结构：

```
Building
├── Type / Author / LastGenerated / Version / Tested_With_BuildingGenerator
├── BDF             样式码字符串，如 "CHA"
├── Modules         { 层号: { 符号: { Mod_Dim, Rotation, Name, Grammar, Level, AssetRef, Props } } }
├── Levels          { 层号: { LevelNum, Height, F0[], [Topper], Alignment_Level } }
├── LevelsGrammar   { 档位: [允许的层号] }
├── minWallWidth / minBldgHeight / maxBldgHeight
└── Roof_Inset / Roof_Offset / SubRoof_Inset / SubRoof_Offset
```

**UE 侧没有 Houdini 工具链**：引擎里无 `HoudiniEngine` 插件，`PCG_Claude.uproject` 无任何
Houdini 引用，全项目 `.uasset` **零处**引用 `.bdf` 或 `/BDF/`。

→ **`.bdf` 是上游作者源文件，只读参考。** UE 运行时真身是下面那个二进制资产，
两者之间**没有现成转换器**。

### 2.2 **推翻认知 A：`SGD_*.uasset` 不是城市生成的入口**

27 个 `SGD_<CODE>_A`（`BP_ShapeGrammarDefinition_C`）只被
`Bldg_SGD_level.umap` / `PCG_Bldg_SGD_test` 这条**预览/测试**路线消费。

真正跑城市的是 `PCG_3_3_1_Buildings`：
`Assign_CitySampleBuildings` → `LoadCitySampleData` → **`CitySampleBuildingBDF_Asset_PCG`**
（2,958,616 字节，`/Script/PCG.PCGDataAsset`，`PCGDataCollectionExporter` 导出），
按 `BuildingToken` 属性过滤样式。

**整条链里 `SGD_` 出现 0 次。**

### 2.3 **推翻认知 B：BDF 数据库可用 Python 重建**

`CitySampleBuildingBDF_Asset_PCG` **不是**不透明的压缩 blob：

- `UPCGDataAsset` 的 `data` 是 `UPROPERTY(BlueprintReadWrite) FPCGDataCollection`；
- `FPCGDataCollection.TaggedData` 是 `UPROPERTY(BlueprintReadWrite) TArray<FPCGTaggedData>`；
- `UPCGDataCollectionExporter` 是 `BlueprintType` 非抽象，`ExportAsset` 全文只是三次赋值；
- `UPCGAssetExporterUtils.CreateAsset` 是 **`BlueprintCallable`**；
- `PCGPointData` / `PCGParamData` 是具体类，可 `unreal.new_object` 创建
  （**必须传非空 outer**，`unreal.find_package("/Engine/Transient")`）。

→ **可以用编辑器内 Python 读出它的结构、并构造/扩展它。**
（`FPCGDataCollection` 自身的成员函数全是纯 C++、Python 不可达，所以走
`get_editor_property` / `set_editor_property` 操作反射字段。）

⚠️ 一条约束：`UPCGAssetExporter::DuplicateAndReOuterData` **只对 outer 恰好是 transient
package 的数据**做重新挂载。所以 Python 造的 `UPCGPointData` 要么挂 transient，
要么自己挂到目标资产上。

⚠️ 另一条：`UPCGDataCollectionExporter::ShouldSave` 会比对 CRC。
**同一个导出重跑到内容完全相同的既有资产上会返回 false、`CreateAsset` 返回 `None`。**
做幂等重生成时需换新包、先删旧资产，或改动 `AssetDescription`。

### 2.4 样式码与白名单的现状（三处必须同步改）

| 位置 | 现状 | TL 需要 |
|---|---|---|
| `DT_Bldg_MinWidth`（7,002 B） | **已含全部 27 码** | 加 `TL` 行 |
| `DT_Bldg_LevelMinWidth`（101,326 B） | **已含全部 27 码** | 加 `TL` 各行 |
| `CitySampleBuildingBDF_Asset_PCG`（2.96 MB） | **已含全部 27 码** | 加 `TL` 的 `BuildingToken` 块 |
| `PCG_3_3_1_Buildings` 图内 | **硬编码 19 码白名单** | 加 `TL`，否则不进城市 |
| `Assign_BldgStyles_per_MinWallWidth` | 全 27 码 + 7 个按墙宽递减的桶 | 按 `minWallWidth` 把 `TL` 插进合适的桶 |

> **2026-10-07 更正**：「白名单」不是这里写的图内硬编码字符串，而是 `PCG_3_3_1_Buildings`
> 三次 `Assign_CitySampleBuildings` 调用各自的 `BuildingsStyles` 覆写，外加
> `CitySampleBuildingBDF_NamesOnly_PCG` 名单资产的过滤。详见
> `migrated-citysample-library.md` §3.2。

→ **只加资产目录是无效的。** 白名单不改，`TL` 永不出现。

### 2.5 一个有用的先例

`STK_primary.bdf` 与 `BLDG_ECO_primary.bdf` 存在，但
`DT_Bldg_MinWidth` / `DT_Bldg_LevelMinWidth` / `BDF_Asset_PCG` 里**都没有** `STK` / `BLDG_ECO`。

→ 说明 Epic 自己也留下过"写了 BDF 但没注册"的样式。**新增样式确实是自己补注册，
不是自动发现。**

### 2.6 **重要发现：两套语法串是可对应的**

BDF 的 `Levels[n].F0` 与 `RULE_<CODE>_Lnn` 的 `grammar` 是
**同一套立面排布的两种记法**。用 CHA 的第一层做对照：

```
BDF  Levels["1"].F0[0] : C|W1*|(W1-P1)|E1|P1|E1|P1|E1|(P1-W1)|W1*|C
RULE RULE_CHA_L01      : [FC][WS1][W1]+[W1,P1][E1][P1][E1][P1][E1][P1,W1][WS1][W1]+[LC]
```

推断出的对应关系：

| BDF 记法 | RULE 记法 | 含义 |
|---|---|---|
| `A\|B\|C` | `[A][B][C]` | 序列（相邻即相接） |
| `(A-B)` | `[A,B]` | 二选一 |
| `X*` | `[X]+` | 重复 |
| 首/尾 `C` | `[FC]` / `[LC]` | 首/末转角 |
| —— | `[WS1]` | **RULE 独有**的墙段/连接件 |

**这条推断由一对样本得出，需在 spike 里再核 2–3 对**（见 §7 U2）。

它为什么重要：BDF 头部写着 `Tested_With_BuildingGenerator: 1.4851`、`Author: votch.levi`、
SFA 的描述是 `"converted from BDF"`——即**这个双向转换器在 Houdini 侧，本机没有**。
所以 TL 的两套表示必须**手工写成一致**；上面这张表就是手工转换的依据。

### 2.7 层号与规则号的对应（已由三个样本交叉验证）

| 样式码 | BDF `Levels` 数 | `RULE_*` 数 | 关系 |
|---|---|---|---|
| `CHA` | 20（1–20） | 21（L00–L20） | 层数 + 1 |
| `NYAA` | 5（1–5） | 6（L00–L05） | 层数 + 1 |
| `SFA` | 9（1–9） | 10（L00–L09） | 层数 + 1 |

且 `RULE_CHA_L01` 引用的网格是 `SM_BLDG_CHA_L01_A_*`，与 BDF `Levels["1"]` 的模块一致。

→ **`RULE_<CODE>_Lnn` ↔ BDF `Level nn`；`L00` 是额外的一条**（推测为基础层/地面规则）。
TL 3 层 ⇒ 需要 `RULE_TL_L00` … `RULE_TL_L03`，共 **4 条**。

### 2.8 CHA 的数值体系（TL 对齐的目标）

`Mod_Dim` 是 **[沿墙宽度, 层高]，单位米**。

| 层 | Height | `W1` 墙 | `P1` 柱 | `E1` 入口 | 转角 `C_*` |
|---|---|---|---|---|---|
| L1 | 5.0 | 3.25 | 1.25 | 3.25 | 1.5 |
| L2 | 3.0 | 3.25 | 1.25 | 4.75 | 1.5 |
| L3 | 3.0 | 3.25 | 1.25 | 4.75 | 1.5 |

`CHA` 的 `minWallWidth = 12`，`minBldgHeight = 25`，`maxBldgHeight = 2000`。

模块符号族（10 个）：
`C_CE`（外角封边，`Rotation = -45`）`C_E` `C_I` `C_IL` `C_IR` `C_SL` `C_SR`
`E1`（入口）`P1`（柱）`W1`（墙）。
每层可有额外符号：L2+ 出现 `P2`（细柱，0.25），高阶层出现 `W2` `C_CI`。

各层网格清单：
- **L1：9 个部件 + 9 个 `_decal` 变体 = 18 个**
  `Column_01` `CornerEx{,L,R}_01` `CornerIn{,L,R}_01` `Entrance_01` `Wall_01`
- **L2/L3：9–10 个**
  `Column_01` `Column_02` `CornerEx{,L,R}_01` `CornerIn{,L,R}_01` `Entrance_01` `Wall_01`

命名规范（必须逐字符对齐，否则 BDF/RULE 引用不到）：

```
Mesh     : /Game/Building/<CITY>/<VARIANT>/Kit_Bldg_<CODE>_L<n>_<V>/Mesh/SM_BLDG_<CODE>_L<nn>_<V>_<Part>_01_N1
Material : .../Kit_Bldg_<CODE>_L<n>_<V>/Material/MI/MI_<CODE>_L<nn>_<V>_<Part>_01
Decal    : .../decal/SM_BLDG_<CODE>_L<nn>_<V>_<Part>_01_decal
Texture  : .../Kit_Bldg_<CODE>_L<n>_<V>/Texture/T_<CODE>_<...>
```

注意实测到的两个**大小写不一致**（`Kit_Bldg_CHa_L20_A` / `Kit_Bldg_CHa_L21_A` 里是小写 `a`），
说明 Epic 自己的路径大小写就不严格——**但引用字符串必须与磁盘完全一致**，所以 TL 要自洽。

### 2.9 道具锚点系统

模块可带 `Props`：`{ 组名: { Group_Type, Probability, MaxLimit, Anchors: { 序号: { Type, var, Offset, Rotation, Scale, AssetRef } } } }`。

实测 CHA 里出现的 `Group_Type`：`Signage` `Generic` `ground_decal` `Frosted`；
`Anchor Type`：`Sign` `Wall` `Corner` `LargeBanner` `Outlet` `Awning` `Banner` `Window`
`Ceiling` `Helper` `A`。
道具网格来自共享库 `/Game/Prop/BLDG/...`（如 `Kit_Prop_BA` `Kit_Prop_Lamp` `Kit_Prop_Clock`）
与模块自带的 `_decal` 网格。

→ **首期不做道具锚点**（YAGNI）。`Props` 留空即可，不影响生成。

### 2.10 环境与工具链现状

| 项 | 状态 |
|---|---|
| Blender | `E:\Blender\blender-5.2.1-windows-x64\blender.exe`（**5.2.1**） |
| Blender MCP | 全局配 `uvx blender-mcp`，**本会话未挂载、9876 端口未监听** |
| Blender 插件 | `%APPDATA%\Blender Foundation\Blender\5.2\scripts\addons\blender_mcp.py` |
| UE MCP 桥 | `run_unreal_script`，端口 8777，**编辑器当前未运行** |
| 引擎自带的语法样板 | `/PCGPrimitives/Grammar/DataAsset/Bldg_Demo`（`RULE_Bldg_L1/L2/L3_Demo` + `SGD_Bldg_Demo`）——**正好三层，可直接抄骨架** |
| 形状语法引导资产 | `/PCGToolset/Content/Skills/Skill_PCGShapeGrammarDefinition` |

⚠️ **待确认**：先前打通的"Interchange 从 Python 导入必崩"绕法
（`Interchange.FeatureFlags.Import.FBX=False`）是在 **UE 5.7** 验的，本项目是 **5.8**。
**必须重新确认**（见 §7 U4）。

### 2.11 版本控制影响

`.gitignore` 已忽略 `/Content/Building/`（第 60 行）与 `/Plugins/CitySamplePCG/Content/`（第 103 行）。
`git ls-files Plugins/CitySamplePCG` 只有 4 个文件（`.uplugin` / `.uplugin.orig` /
`MIGRATION-NOTES.md` / 图标）。

→ **TL 的美术与资产落盘后不进 git。**
**本任务的真正交付物是可复现的脚本 + 文档，不是资产文件本身。**
这是设计的硬约束（见 §5）。

---

## 3. 两条路线与推荐

### 3.1 路线 A — SGD / 形状语法（第一期）

建 `SGD_TL_A` + `RULE_TL_L00..L03`，用 `Assign_ShapeGrammarDefinition` 沿样条铺立面。

- **优点**：完全可用 Python 作者化（全是 Blueprint `UPrimaryDataAsset` + 反射属性）；
  能在编辑器里**立刻看到立面拼得对不对**，是美术的天然验收测试；无需碰二进制数据库。
- **缺点**：**不进 18 阶段城市流水线**，只走预览/独立图。

### 3.2 路线 B — BDF 主流水线（第二期）

向 `CitySampleBuildingBDF_Asset_PCG` 增 `BuildingToken` 块，补两张表，改两处白名单。

- **优点**：**唯一能让 `TL` 进入城市生成的路**。
- **缺点**：要写那个 2.96 MB 的资产（风险最高，故先 spike）；改的是 Epic 的原始资产。

### 3.3 推荐：先 A 后 B，分两期

**理由**：

1. **A 是 B 的美术前置。** 立面拼得对不对、模块尺寸/pivot/朝向对不对，
   在 A 里一眼可判、循环极快；到了 B 只能看"城里有没有出现"，反馈慢且噪声大。
   **先用 A 把美术定型，再解决数据难题**，是唯一合理的顺序。
2. **两者是平行表示**（§2.6：SGD 的描述写着 "converted from BDF"），
   所以 A 不浪费——A 的 `RULE` 语法串正是 B 的 `F0` 语法串的手工转换源。
3. **B 的不确定性已被 §2.3 大幅降低**，但它仍是全局风险最高的一环，值得单独一期。

---

## 4. 组件设计

### 块 A — 美术套件（Blender → UE）

**工具**：Blender **headless CLI**（`blender -b -P build_tl_kit.py`），
不用 Blender MCP——本会话未挂载，且程序化套件用脚本更可复现、可重跑。

**产出**（≈28–38 个网格）：

| 层 | 部件 | 网格数 |
|---|---|---|
| L1 | `Wall_01` `Column_01` `Entrance_01` `CornerEx{,L,R}_01` `CornerIn{,L,R}_01` | 9（+9 可选 decal） |
| L2 | 同上 + `Column_02` | 10 |
| L3 | 同 L2 | 10 |

**必须满足的规格**（§2.8 是验收标准）：

1. **尺寸**：`Mod_Dim` = [沿墙宽, 层高]。L1 用 3.25/1.25/3.25/1.5 + 高 5.0；
   L2/L3 用 3.25/1.25/4.75/1.5 + 高 3.0。
2. **Pivot 与朝向**：底部中心为原点（便于沿样条拼接与落地）；
   朝向轴与 CHA 一致（CHA 的 RULE 用 `MeshForwardAxis = EAxis::Y`）。
   **这两个约定要在 spike 里从既有网格实测反推**（见 §7 U3），不要猜。
3. **命名**：严格按 §2.8 的模板。
4. **材质**：每个网格一个 `MI_*`，母材质沿用
   `/Game/Building/Material/` 下的既有建筑母材质体系（母材质已有，不新建）。
5. **单位**：米（UE 侧 ×100 得厘米）。导出 FBX 时确认 scalefactor。

**导入**：走**传统 FBX 路径**（不依赖 Interchange）。
⚠️ 绕法在 5.7 验过，5.8 需重新确认（§7 U4）。
落点：`/Game/Building/TL/A/Kit_Bldg_TL_L<n>_A/{Mesh,Material/MI,Texture,decal}`。

### 块 B — SGD 路线（第一期，验证美术）

**产出**：

- `RULE_TL_L00` … `RULE_TL_L03`（4 条，`BP_ShapeGrammarRule_C`）
- `SGD_TL_A`（1 个，`BP_ShapeGrammarDefinition_C`）

**关键字段**（从既有资产实测的 schema）：

`BP_ShapeGrammarRule_C`：
- `grammar`（`FString`）——用 §2.6 的对应表从 B 的 `F0` 手工转换
- `Modules Infos`（`TArray<STC_Module>`）——每项含 `Symbol`(FName) /
  `Mesh`(UStaticMesh*) / `Size`(FVector) / `Scalable`(bool) / `PivotOffset`(FVector) /
  `MeshForwardAxis`(EAxis) / `GuessSize` / `GuessPivotOffset` / `DebugColor`
- `Spawn Spline Mesh` / `Set Spline Mesh Roll` / `Spline Roll Degrees` 等

`BP_ShapeGrammarDefinition_C`：
- `Slots`（`TArray<STC_Slot>`）——每项含 `Symbol` / `size` / `scalable` /
  `offset` / `Shape Grammar Rules`(`TArray<BP_ShapeGrammarRule_C*>`)
- `Main Grammar`（`FString`）= `"L00, L01, L02, L03"`
- `Use Grammar`(bool) = true，`Minimum Size`(double)，
  `Spawn on`(枚举)，`Reverse Spline`(bool)，`Description`(FText)

**放置**：两条路都留。
1. 项目侧 `/Game/PCG/DataAssets/Buildings/TL/`（**首选**——不动 Epic 的插件内容）
2. 若某工具硬要求插件内路径，再同步一份到
   `Plugins/CitySamplePCG/Content/PCG/DataAssets/Buildings/TL/`

**验收**：新建临时 `PCGVolume`，挂 `Assign_ShapeGrammarDefinition` 图，
喂一条样条，`activate(True)` → `generate_local(True)`，**下一次调用**读 ISM 实例数
（见 §6），核对：实例数 > 0、实例用的网格是 `/Game/Building/TL/...`、高度与拼接无错位。
跑完销毁临时 Volume，**不保存关卡**。

### 块 C — BDF 主流水线（第二期）

**spike 先行**（§7 的 S1/S2），拿到答案再决定写入策略。

**注册三处**（§2.4）：

1. **`CitySampleBuildingBDF_Asset_PCG`** 增 `TL` 的 `BuildingToken` 块。
   两种写法，spike 后择一：
   - **(C1) 原地扩展**：脚本读出原资产 → 追加 TL 的行 → 用
     `PCGAssetExporterUtils.create_asset` 写到**新路径**（如
     `/Game/PCG/DataAssets/BDF/BDF_WithTL`），再让 `LoadCitySampleData` 指向它。
     **推荐**：Epic 原始资产零改动，可回退。
   - **(C2) 原地覆盖**：直接改 `CitySampleBuildingBDF_Asset_PCG` 本身。
     改动最直接，但**先做文件级备份**（它在 gitignore 内，没有 git 兜底）。
2. **`DT_Bldg_MinWidth`** 加 `TL` 行：`buildingToken = "TL"`，`minWidth = 12`（对齐 CHA）。
3. **`DT_Bldg_LevelMinWidth`** 加 `TL` 的逐层行：
   `BuildingToken` / `LevelToken` / `LevelNumber` / `F0Grammar` / `CornerModuleSymbol` /
   `CornerSize` / `MinWidthWorstCase`。
4. **两处白名单**：
   - `PCG_3_3_1_Buildings` 内的样式码字符串（现 19 码）追加 `TL`
   - `Assign_BldgStyles_per_MinWallWidth` 的 7 个墙宽桶，按 `minWallWidth = 12`
     把 `TL` 插进合适的桶

> **2026-10-07 更正**：白名单实际是调用覆写（`BuildingsStyles` 参数）加
> `CitySampleBuildingBDF_NamesOnly_PCG` 名单资产，不是图内字符串。详见
> `migrated-citysample-library.md` §3.2。

**验收**：跑 `PCG_3_3_1_Buildings`（或 3.3.1 那一段），
在生成结果里**数出 `TL` 的网格实例**，并确认与既有样式混合出现。
用已有脚本 `Content/Python/pcg_sa_*.py` 的读法。

### 块 D — 验证

见 §6。每步都必须实证。

---

## 5. 交付物

**因为 `Content/Building/` 与插件 `Content/` 都在 gitignore 内（§2.11），
交付物是"能重建资产的脚本 + 文档"，而不是资产本身。**

| 交付物 | 路径 | 说明 |
|---|---|---|
| Blender 建模脚本 | `Tools/tl_kit/build_tl_kit.py` | headless 生成 3 层模块网格 + 材质 |
| FBX 导出脚本 | `Tools/tl_kit/export_tl_kit.py` | 导出到 `E:\Blender\TL_Kit\FBX_Export\` |
| UE 导入脚本 | `Content/Python/tl_import_kit.py` | 传统 FBX 路径导入 + 槽位赋值 + 读回 assert |
| 网格规格表 | `Tools/tl_kit/tl_kit_spec.json` | 部件名/尺寸/pivot/材质槽的**唯一事实源**，被上面三个脚本共读 |
| BDF 写入脚本 | `Content/Python/tl_register_bdf.py` | 块 C 的注册（含备份） |
| 白名单修改脚本 | `Content/Python/tl_whitelist.py` | 改两张图的样式码字符串（2026-10-07 更正：实际实现是 `tl_whitelist_city.py` 改调用覆写 + `tl_names_with_tl.py` 改名单资产，见 `migrated-citysample-library.md` §3.2） |
| 验证脚本 | `Content/Python/tl_verify_sgd.py` / `tl_verify_city.py` | 块 B / 块 C 的验收 |
| 设计文档 | `docs/superpowers/specs/2026-09-24-tl-building-style-design.md` | 本文 |
| 技能文档更新 | `.claude/skills/city-sample-pcg-city-builder/references/migrated-citysample-library.md` | 补 §2.2 / §2.6 两条推翻性发现 |
| 计划文档 | `docs/superpowers/plans/2026-09-24-tl-building-style.md` | 由 writing-plans 产出 |

**不交付**：`/Game/Building/TL/**`、`/Game/PCG/DataAssets/Buildings/TL/**`、
改写后的 BDF 资产——它们可随时由脚本重建，且已被 gitignore。

---

## 6. 验证策略

PCG 的失败模式是**静默零点**（配置错不报错，只是不出东西）。所以每步都要**实证**。

**四条铁律**（都有本项目实测依据）：

1. **两段式读数**：`generate_local` 之后**同一次调用里**读
   `get_generated_graph_output()` 会读到空集合且**不报错**。
   **必须一次调用生成、下一次调用读。**
2. **spawn 型图必须数 ISM 实例**：实测过"输出 pin 0 个 tagged data，却有 3129 个实例"。
   "写了输出 pin"与"spawn 了几何"是两件事。
3. **必须 `activate(True)` 再 `generate_local`**——不 activate 就是静默零点。
4. **几何验证走数值**（包围盒/顶点数/实例数/资产路径），**不目测截图**——
   PCG 检视态有幻影可视化。

**分步验收指标**：

| 步骤 | 指标 |
|---|---|
| 块 A 建模 | 每个 FBX 的包围盒尺寸 == `tl_kit_spec.json`；pivot 在底面中心 |
| 块 A 导入 | `load_asset` 全部返回 `StaticMesh`；材质槽非 `WorldGridMaterial`（读回 assert） |
| 块 B | 临时 Volume 生成后 ISM 实例数 > 0，且实例网格路径含 `/Game/Building/TL/` |
| 块 C | `PCG_3_3_1_Buildings` 输出里数出 `TL` 实例；`TL` 与既有样式混合出现 |
| 全局 | 已交付的 3×3 区域回归不破（`pcg_postmigration_regression.py` 仍 41 实例） |

---

## 7. 风险与未决问题

| 编号 | 项 | 现状 | 处置 |
|---|---|---|---|
| **U1** | BDF 数据库的**内部 schema**：`BDF_Input_Processor` 到底期望什么属性/行结构 | **未读**。只知道属性名 `@data.BDF` / `BuildingToken` / `BDFData` / `BDFNameOnlyData`，pin 标签 `BDFData` / `BDFNameOnlyData` | **spike S1**（只读 dump） |
| **U2** | §2.6 的 BDF↔RULE 语法映射**只有一对样本** | 高置信但未定 | **spike S3**：再核 2–3 对（如 CHA L2/L5、SFB） |
| **U3** | 既有模块网格的 **pivot 与朝向轴**约定 | 未实测。只知 RULE 写 `MeshForwardAxis = EAxis::Y` | **spike S4**：从既有网格读包围盒与 pivot 反推 |
| **U4** | **Interchange FBX 导入绕法在 5.8 是否仍适用** | 5.7 验过，5.8 未验 | **spike S5**：单资产先试，看是否崩 |
| **U5** | §2.7 的 `RULE_L00` 是"额外一条" | 3 个样本一致，但 `L00` 的具体语义未读 | spike S3 顺带读 `RULE_CHA_L00` 的 `grammar` |
| **U6** | `LevelsGrammar` 的档位语义（`"0"/"1"/"2"` → 层号集合） | 观察到 CHA 是 `{0:[1..10], 1:[6..10], 2:[9,10]}`，语义未确证 | spike S1 顺带读；3 层时影响小 |
| **U7** | 改 Epic 原始资产的风险 | `CitySampleBuildingBDF_Asset_PCG` 在 gitignore 内，**无 git 兜底** | 走 C1（写新资产 + 改 `LoadCitySampleData` 指向）；若必须 C2，先做文件级备份 |
| **U8** | 编辑器当前**未运行** | 8777 未监听 | 所有编辑器相关步骤前请用户启动编辑器 |

### Spike 清单（全部只读，除 S5 会落一个网格）

| 编号 | 内容 | 成本 |
|---|---|---|
| S1 | dump `CitySampleBuildingBDF_Asset_PCG` 的结构：pin 标签、tagged_data 条数与类型、每条的类型与属性名/行数；并按 `BuildingToken` 抽出 CHA 那一条的形状 | 1–2 次往返 |
| S2 | 读 `CHA` 的 `BuildingToken` 块，确认"一条样式"需要哪些属性/字段（U1 的答案） | 含在 S1 |
| S3 | 核 §2.6 映射：读 `RULE_CHA_L00/L02/L05` 与 `RULE_SFB_L01` 的 `grammar` | 1 次往返 |
| S4 | 读 3 个既有网格（如 `SM_BLDG_CHA_L01_A_Wall_01_N1`）的包围盒与 pivot | 1 次往返 |
| S5 | 单 OBJ/FBX 导入试跑，确认 5.8 是否仍崩 | 1 次往返 |
| S6 | dump `PCG_3_3_1_Buildings` 与 `Assign_BldgStyles_per_MinWallWidth` 的样式码字符串**所在节点与参数名**（改白名单要知道改哪个节点的哪个参数） | 1 次往返 |

**S1/S2 是块 C 的准入条件**；S3/S4 是块 A/B 的准入条件。

---

## 8. 分期

| 期 | 内容 | 准入条件 |
|---|---|---|
| **P0** | Spike S1–S6（只读探测） | 编辑器已启动 |
| **P1** | 块 A：`tl_kit_spec.json` → Blender 建模 → FBX → 导入 UE → 验证 | S4、S5 通过 |
| **P2** | 块 B：`RULE_TL_L00..L03` + `SGD_TL_A` → 样条铺立面验证 | S3 通过；P1 完成 |
| **P3** | 块 C：BDF 注册 + 白名单 → 城市生成验证 | S1/S2 通过；P2 完成 |
| **P4** | 文档回填 + 回归验证 | P3 完成 |

`TL` 首期 3 层。**后续按层扩容**复用同一套脚本：加层 = 在
`tl_kit_spec.json` 增层 + 重跑建模/导入 + 加对应 `RULE_TL_Lnn` + 在两处白名单与 BDF 里同步。

---

## 9. 附：本设计依赖的确切路径

| 用途 | 路径 |
|---|---|
| BDF 源文件（只读参考） | `Content/Building/HDA/Bldg/BDF/<CODE>_primary.bdf` |
| 既有模块网格 | `/Game/Building/{CH,NY,SF,QB}/<V>/Kit_Bldg_<CODE>_L<n>_<V>/` |
| 既有样式资产 | `Plugins/CitySamplePCG/Content/PCG/DataAssets/Buildings/<CODE>/` |
| BDF 数据库 | `/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/CitySampleBuildingBDF_Asset_PCG` |
| 加载子图 | `/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/LoadCitySampleData` |
| 建筑原语 | `/CitySamplePCG/PCG/Primitives/Buildings/Assign_CitySampleBuildings` |
| 城市建筑图 | `/CitySamplePCG/Levels/PCG/PCG_3_3_1_Buildings` |
| 墙宽分桶 | `/CitySamplePCG/PCG/Assign_BldgStyles_per_MinWallWidth` |
| 引擎语法样板（三层） | `/PCGPrimitives/Grammar/DataAsset/Bldg_Demo` |
| Blender | `E:\Blender\blender-5.2.1-windows-x64\blender.exe` |
| UE 脚本根 | `Content/Python/` |
| 现有读点参考实现 | `Content/Python/pcg_scatter_read.py` |
