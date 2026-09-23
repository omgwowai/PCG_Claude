# 坑与硬约束

> **本文是"跑通了但没结果"时的第一站。**
> PCG 最大风险是**静默零点**：配置错误不报错，只是不出点/不出网格。
> 以下全部为实测记录，不是推测。

---

## 1. 静默零点：16 条实测坑

| # | 坑 | 规避 |
|---|---|---|
| 1 | `Surface Sampler` 必须喂**真实 Surface 数据**。`Input` 节点的 Volume 过滤成 Surface 是**空的**；`World Ray Hit` 在**非 PIE** 编辑器上下文也采不到 | 用 `Create Polygon 2D` → `Create Surface From Polygon2D` 自造表面 |
| 2 | `Static Mesh Spawner` 的网格**不能**经 `AddNode` 的 `jsonParams` 设置（实例化子对象） | 先建**空参**节点，再对 `DefaultSelectorInstance` 用 `ObjectTools.set_properties` 二次写入 |
| 3 | MCP **数组属性追加只能 0→1**，多元素数组写不进去 | 需要多行/多网格的地方用**多分支**或**表行**承载 |
| 4 | Spawner 需 `bSynchronousLoad=true` | 否则 MCP 触发的**首次执行因异步加载看不到结果** |
| 5 | **CitySample 侧**：`GetNodeDataView` 首调只启用检视，返回 no data；`attributeName` 描述说可省、schema 却标必填 | 传 `attributeName: ""`，再执行一次后读取。**本项目无此工具**——改用 `PCGComponent.get_generated_graph_output()` + 点数据读取 |
| 6 | `Self Pruning` 前必须 `Bounds Modifier` 设**真实包围盒**（点默认包围盒极小，**永不剪枝**） | 在布局层用 `FootprintExtent` 作为界 |
| 7 | `Spline Intersection` 的 `bUseBestFitBox=true` 会让 PCA 使四元数绕 XY 轴翻转约 180°，**网格倒扣** | 设 `bUseBestFitBox=false`，下游保持**加性旋转继承** |
| 8 | 无缝路口**不是边对边** | 套件式**重叠**：裁剪框（17×7）**故意小于**垫块（20×11），路伸入垫块下方，垫块抬 **+3cm** 盖缝 |
| 9 | `SM_ROAD` 枢轴不居中 | 垫块局部偏移 `Y=-500`；`Spawn Spline Mesh` 的 `startOffset/endOffset.x = -500` |
| 10 | `Spline Sampler` 在 **Distance 模式**下，当 `startOffset+endOffset ≥ 段长` 时**静默零点** | 切断后的路段可能短于 25m → **`offset` 合计 ≤ 200cm** |
| 11 | `Spawn Actor` 生成的建筑会**继承上游微缩尺度 → 不可见** | 生成后重置为**绝对缩放并轴对齐**（`bAbsoluteScale=true`），否则会与 `PCGVolume` 自身 `scale{25,25,10}` 叠乘 |
| 12 | `CaptureViewport` 必须传**完整 annotations 对象**（6 个子字段全给）；返回 base64 需解码 | 需要截图验证时照此处理 |
| 13 | 属性驱动解析（ByAttribute 网格选择器、`Spawn Actor` 按属性选类、DataTable 建行/读行）**全部需要 spine 验证** | 涉及实例化子对象时仍走第 2 条的两步法 |
| **14** | **`add_edge` 静默失败**：pin 标签写错、或类型不兼容时，**不报错、不建边，却返回真值**（返回的是 To 节点） | 连完**必须**用 `len(graph.get_all_edges())` 前后对比验证。pin 标签用 `node.get_editor_property("input_pins")` 读真实 `label`，**不要猜 `"In"`**——`SurfaceSampler` 的输入叫 `"Surface"`。详见 `node-classes.md` §0.4 |

### 额外环境坑

- **PCG 检视态的幻影可视化**：在 CitySample 侧由 `GetNodeDataView` 启用检视触发，
  截图里会出现**幻影立方体**。本项目虽无该工具，但 PCG 的调试可视化同样不可信——
  **几何验证一律走数值（点数 / 包围盒 / Actor 计数），不要目测截图。**
- **`Spline Intersection` 输出角点系统性内缩 2.5177cm** — 已知系统性偏差，
  验收时按此解释，不要当成 bug 追。
- **某些规模下路段数比公式少 1** — 经复核**非缺陷**，已排除。
- Windows 环境下 `python3 -c "..."` 可能静默失败（exit code 49），
  疑似 `python3` 是 WindowsApps 的 stub 别名。**写独立 `.py` 文件后用 `python` 执行。**

---

| **15** | **`create_asset` 失败时返回 `None`，不抛异常。** 实测：在同一脚本里先 `delete_asset` 再立刻 `create_asset` **同名**资产 → 返回 `None`（包尚未从内存释放），后续 `None.add_node_of_type` 才炸 | **不要复用刚删掉的名字**；用带时间戳的唯一名。并且**每次 `create_asset` 后立刻判 `None`**：`g = at.create_asset(...)` / `if g is None: raise RuntimeError("create_asset returned None")` |
| **16** | **`FPCGDataCollection` 的方法在 Python 侧不可用。** `get_all_inputs()` / `get_all_spatial_inputs()` / `get_inputs()` **全部 `AttributeError`**——它们是普通 C++ 方法，没有 `UFUNCTION` | 它是 `USTRUCT`，**读字段而不是调方法**：`coll.get_editor_property("tagged_data")` 拿到 `TArray<FPCGTaggedData>`，再逐项读 `pin` / `tags` / `data` |

| **17** | **资产删除不可靠。** 实测同一目录下 6 个资产：3 个 `delete_asset -> True` 删掉，3 个 `-> False` 赖着不动；对后者再试 `delete_loaded_asset`（**TypeError**）与 `delete_directory`（**也返回 False**）均无效 | 删资产后**必须复查** `does_asset_exist`。**删不掉就如实报告、留给用户手工删**——不要绕过资产系统直接删文件，那会让资产注册表失同步 |

## 2. 项目硬约束（工具面缺失的能力）

| 约束 | 后果 | 绕法 |
|---|---|---|
| **无通用 Struct 创建工具** | 任何"新建自定义 Struct 资产"做不到。`search_row_structs` 只能**发现**已存在的 TableRowBase 子类，不能**创建** | 复用既有 struct（如引擎自带 `MirrorTableRow` 可临时代用），或把结构塞进**蓝图内嵌变量**（`BlueprintTools.add_struct_variable`） |
| **无新建 Level 资产工具** | 只有 `load_level` / `get_current_level` / `create_level_instance`（后者建的是引用现有关卡的 **Level Instance Actor**）。**没有"新建空关卡"入口** | 请用户在编辑器 `File → New Level`；或 `AssetTools.duplicate` 复制现成 `.umap`（未验证）；或在现有关卡里新增 Volume |
| **`PCGVolume` 类工具拒绝蓝图 Actor**（CitySample 侧） | 那边的 `ExecuteGraphInstance` / `GetNodeDataView` 只认原生 `PCGVolume` | 本项目无此限制——直接对任意 Actor 的 `PCGComponent` 调 `generate_local()` 即可。此条**仅供参考** |
| **BP 的 `bCallInEditor` 不可经反射写入** | "CallInEditor 按钮"方案需换实现 | 用原生 PCGComponent 的 Generate/Cleanup 按钮，或换实现方式 |

---

### 2.1 一条来自源码的硬限制：动态输入 pin 加不了

`UPCGSettingsWithDynamicInputs` 的 5 个子类
（`Gather` / `Merge` / `MergeAttributes` / `Union` / `OuterIntersection`）
在编辑器里能点 "+" 加输入 pin，但**加 pin 的机制全是 `WITH_EDITOR`-only 且非 `UFUNCTION`**
（`OnUserAddDynamicInputPin` / `AddDynamicInputPin` / `OnUserRemoveDynamicInputPin`）。

→ **纯 Python 建这类节点，只能拿到默认的 pin 数，加不了额外输入。**
`InputPinProperties()` 被声明为 `override final`，子类也改不了。

**规避**：需要 N 路并集就**串接多个二元 Union**，不要指望加 pin。

---

## 3. 已实测的机制结论（可直接复用，不必重新验证）

### 3.1 资产解析：机制 A 可用（DataTable 链路）

链路：**DataTable → `Load Data Table`（`outputType="Param"`）→
`Match And Set Attributes`（`inputAttribute`=匹配键，`matchAttribute`=表列名，
`bMatchAttributes=true`，`bKeepUnmatched=true`）→ `Attribute Rename` →
`Attribute Cast` → ByAttribute Spawner**

**关键坑**：`Attribute Rename` **只改属性名，不改类型**。
若原属性来自 DataTable 的 `Name` 字段（**FName** 类型），Rename 后下游按 String 使用时
Spawner 会报：

```
Attribute 'X' is not of valid type (must be FString or FSoftObjectPath)
```

→ **必须插 `Attribute Cast`**（`inputSource` / `outputTarget` = 同名，`outputType="String"`）。

`bKeepUnmatched=true` 的意义：**未匹配的行不报错，只保留默认值** →
新增 Category 取值时只需加表行，**图不用动**。

### 3.2 Actor 解析：byAttr 可用

`Spawn Actor` 节点原生具备三个字段，**均可经 `AddNode`/`UpdateNode` 的 `jsonParams`
直接设置**（不是实例化子对象，**不需要两步法**）：

- `bSpawnByAttribute` (bool)
- `spawnAttribute` (string)
- `templateActorClass` (Class 引用)

> **硬性要求**：byAttribute 模式下 `templateActorClass` **仍必填**，
> 且必须是**所有待生成 Actor 的共同父类**。工具描述原文：
> *"When spawning by attribute, it is mandatory for that template actor to be
> a parent class of ALL actors that will be spawned"*。
> 若新 SubType 的 Actor 类不是现有 `templateActorClass` 的子类，
> **必须同时更新 `templateActorClass`**——这是该机制唯一需要动图的场景。

### 3.3 种子策略：**组件 Seed 有效，无需图参数**

实测结论：节点级 `seed` / `bRecomputeSeed` 字段**无需统一收编到图参数**。
只要节点不显式设 `bRecomputeSeed=true` 覆盖，其随机行为**默认继承自宿主组件**
（`PCGVolume` / 蓝图 Actor 上的 `PCGComponent`）的 `Seed` 属性。

→ **换种子 = 改这一个属性**，不需新增图参数或改动图内连线。

### 3.4 加权随机选择：单节点搞定

`Match And Set Attributes` 设 `bUseWeightAttribute=true`
可在**一个节点内**完成按权重随机选择（如树种混植），
优于"三分支 + Random Choice"的常量硬降级方案。

### 3.5 代理与兜底模式（值得复用的设计）

| 机制 | 做法 | 价值 |
|---|---|---|
| **代理模式** | 跳过资产解析，全部语义点渲染为按 `FootprintExtent` 缩放、按 `Category` 着色的立方体 | 秒级重算，**大布局调参必用** |
| **红盒兜底** | 任何**无匹配行**的语义点一律渲染为**红色代理盒** | **配置缺失肉眼可见，杜绝静默消失** |

第二个机制尤其值得推广——它把 PCG 最危险的"静默零点"变成了**可见的红色**。
