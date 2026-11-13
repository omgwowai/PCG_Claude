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

---

## 4. 2026-09-23 第二次实测新增（搭 3×3 小区域时踩到）

| # | 坑 | 规避 |
|---|---|---|
| **18** | **`generate_local()` 会静默不生成。** `GenerateInternal` 的第一行是 `if (IsGenerating() \|\| !GetSubsystem() \|\| !ShouldGenerate(...)) return InvalidPCGTaskId;`，而 `ShouldGenerate` 要求 **`bActivated && GetGraph() && GetSubsystem()`**。在**同一个脚本里刚 spawn 的 PCGVolume** 上直接 `generate_local` 会命中这个分支：**不报错、不生成**，下次读就是空集合 | **生成前先 `pc.activate(True)`**（并 `get_editor_property("activated")` 复查为 True）。`bActivated` 头文件默认是 `true`，但新建/刚 spawn 的组件实测需要显式 activate |
| **19** | 上面那条导致**第一次读是 `tagged_count=0`**，极易误判成"图配置错了"。实际图是对的 | 静默零点先怀疑**组件未激活/未就绪**，再怀疑图。分开两次调用：一次 activate+generate，下次读 |
| **20** | **`unreal.CubeBuilder` 不存在**（`hasattr` 为 False），但 PCGVolume 实例上 `get_editor_property("brush_builder")` **拿得到** `CubeBuilder` 对象 | 不要 `unreal.CubeBuilder()` 造；直接从 volume 取实例再 `set_editor_property("x"/"y"/"z", ...)` |
| **21** | **`BrushComponent.brush` 是 protected，读不了**（`Property 'Brush' ... is protected and cannot be read`）。所以**没法用"复制别的 Volume 的 brush"来给 PCGVolume 塑形** | 走 `brush_builder`（见上条） |
| **22** | **`CubeBuilder` 的 x/y/z 是"全尺寸"不是半尺寸。** 实测 `x=3300` → `get_actor_local_bounds_pcg()` 返回 `±1650` | 想要 ±W 就填 `2W` |
| **23** | **`PCGEdge` 的 `get_output_node()` / `get_input_node()` 命名与直觉相反**（实测：数据流 `Spawner.Out → Output.In` 的边，`get_output_node()` 返回的是 **DefaultOutputNode**） | **不要靠边的 getter 判断上下游**。要定位"某节点的搭档"，用**实测属性值**匹配（如下游 TransformPoints 的 `scale_min`），或用 `pin.is_connected` |
| **24** | `PCGEdge` 上 `get_output_node` / `get_input_node` / `get_output_pin_label` / `get_input_pin_label` 是**方法**，`input_pin` / `output_pin` 是**属性**。把它们当属性/方法搞反会得到 `AttributeError` 或 `<Object PCGPin>` 字符串 | 需要拓扑时**先 `dir()`**，别猜 |

### 4.1 一条重要的正面结论：同一次调用内**建图 + 设参 + 连线**是安全的

`node-classes.md` §0.6 的"异步"约束**只针对 `get_generated_graph_output()`**。
在同一脚本里 `add_node_of_type` → 设参 → `add_edge` → 读回 pin 标签 → `save_asset`，
**全部同步生效**，实测建出 12 节点 12 边且 `get_all_edges()` 立刻可见。
所以**建图不需要拆成多次调用**，只有"读生成结果"需要。

### 4.2 PCGVolume 必须给真实 brush，否则覆盖不了区域

新建的 PCGVolume 只有一个 **200 单位**的默认立方体 brush（`local_bounds_pcg` = ±100）。
它决定组件的生成范围。两条路：

- **改 brush_builder 的 x/y/z**（推荐，与 actor scale 解耦）：填全尺寸。
- 或者放大 actor scale —— 但那样必须把网格节点的 `coordinate_space` 设成 **`WORLD`**，
  否则 `LOCAL_COMPONENT`（**默认值**）会把 actor 的缩放乘进 GridExtents，城市会放大同样倍数。

---

## 5. 2026-09-24 第三次实测新增（把 18 阶段跑在小区域上时踩到）

> 这一节按**代价**排序，不是按发现顺序。前五条是计划里原本就列的；**30–33 是本次实际花掉最多时间的四条**。

| # | 坑 | 规避 |
|---|---|---|
| **25** | **Python 全局里的 UObject 会钉住旧 world，让下一次切关卡 abort 在 `CheckForWorldGCLeaks()`。** 实测引用链 `FPyReferenceCollector::AddReferencedObjects(Package /Temp/Untitled_1)`，脚本栈指向 `LevelEditorSubsystem.LoadLevel`。09-23 记的「重载 demo 关卡会崩」是误诊 | 顶层只放 JSON；UObject 全放函数内；切关卡前清理并 `gc.collect()`。详见 `stage-run-playbook.md` §3.2 |
| **26** | **`Actor.add_component_by_class` 不存在**（`AttributeError`），所以**不能从 Python 给 Actor 新挂 SplineComponent** | 要新样条就走「复制带样条的 Actor」或请用户手画。样条只有改写已有的：`set_location_at_spline_point` / `set_tangent_at_spline_point` / `set_closed_loop` / `update_spline`（都是 `UFUNCTION`，实测可用） |
| **27** | **`set_spline_points()` 会把所有点重设为 `CurveAuto` 并丢弃自定义切线**，原本是 `CURVE_CUSTOM_TANGENT` 的样条形状会变 | 逐点 `set_location_at_spline_point(i, p, WORLD, False)` + `set_tangent_at_spline_point(i, 变换后的切线, WORLD, False)`，最后 `update_spline()` 一次 |
| **28** | **demo 关卡的样条不止「7 个手绘样条」。** 实测 **19 个 Actor** 带 `SplineComponent`（85 个组件、453 个点），其中 `PCG_3_1_1_Districts` **一个 Volume 就带 67 个**细分样条；另有 `HighRise_Zone_*`、`HighWay_2/3`、以及 `PCG Generated Actor` 产生的 `ForestExclusion_*` / `Lake_*` / `ParkPath_*` | 缩放城市必须**遍历所有 SplineComponent**。只改「7 个」会漏掉整张街区细分图。复现数字在 `Saved/Reports/sa_inventory.json` 与 `pcg_sa_verify.py` |
| **29** | **`PCGComponent` 上没有 `is_generating()`**（实测 `hasattr` 为 False），只有 `generated` 布尔 | 判断「生成好了没」用 `generated` + 实例数两次读数是否相同；不要找不存在的 API |
| **30** | **（本次最难的一条）样条的 world ↔ local 存储规则**，四次尝试、两次关卡重置才搞对：`world = local + actor_location`（组件 rotation 1 / scale 1）；**`local` 在 actor 移动时不变**；`set_location_at_spline_point(p, WORLD)` 存的是 `local = p - actor_location`，写 WORLD 读回来**精确**（`write_error` 为 0）；但**写完再移动 actor，该点会跟着位移** | **读点在动 actor 之前，写点在动 actor 之后。** 正确顺序是三段式：PASS 0 快照所有点的 world → PASS 1 每个 actor **只移动一次**（按 `get_path_name()` 去重，带样条的 PCGVolume 会同时出现在两个集合里，移动两次就错）→ PASS 2 写映射后的 world 点。所有错误版本的症状都一样：误差恰为 `s * (L1 - L0)`（实测 CityShape 偏 `(-1921.2, 1401.6)` cm，与 `0.2816816 * (-6820.516, 4975.783)` 吻合到 0.1 cm）。复现探针：`Content/Python/pcg_sa_convprobe.py` |
| **31** | **截图是异步的，落盘延迟约 1–2 分钟**，不是「下一帧」。同一次调用里查 `os.path.exists()` 会读到 `False`，90 秒的轮询也会超时 —— 于是**六张已经成功的截图被判为失败**，并因此产生了四个被证伪的假设（文件名复用、同调用内移机位、realtime 开关、窗口最小化） | **不要用同一次调用的结果判断截图成败**；核验放到**下一次调用**（或主机侧等 1–2 分钟再查盘）。`pcg_sa_drive.py` 的两个 phase 都内建了这个等待，并把 `WAIT(<name>)` 作为「上一张还没落盘」的信号返回 |
| **32** | **截图文件名是一次性的：automation 会拒绝写过一次的名字，即使文件已被删除。** 而它记住了什么**从 Python 侧读不到** | 用「带时间戳或 `_rN` 后缀的新名字」；把已用过的名字**落盘记账**（`Saved/Reports/sa_shot_names.json`），并在下一次调用把 `_rN` 改名回规范名。**不要靠 `os.path.exists` 推断名字是否可用** —— 删掉文件后它照样拒绝 |
| **33** | **一次调用里批量重新生成全部 18 个阶段会破坏阶段间依赖。** 图之间靠 `Get_ActorDataByRef` 读上游 Actor 数据；并发重跑让下游阶段读到「正在重建」的上游数据。实测：阶段 17 的 6,400 个实例**全部丢失**、阶段 13 少了 8,177 个建筑 | **严格按阶段号顺序重跑**，一阶段一次调用，中间留出生成时间。判断修复成功的方法不是「没报错」，而是**逐阶段把 `real_instances` 与一份已定稿的 census 比对**（`pcg_sa_census_cmp.py` 就是干这个的） |

---

## 6. 2026-10-07 第四次实测新增（新增建筑样式码 TL 时踩到）

> 这次的主症状是**新样式 0 实例、0 报错、其他样式一切正常**，前后试了五个假设才找到真因。真因是第 34、35 两条，它们在 BDF 数据之前就把样式码过滤掉了；36–37 是样式能进语法之后才暴露的数据问题；38–40 是本轮另外踩到的工具/流程坑。

| # | 坑 | 规避 |
|---|---|---|
| **34** | **`PCG_3_3_1_Buildings` 里共五处样式码列表**：三个 `Assign_CitySampleBuildings` 调用各自覆写了 `BuildingsStyles`（Small 6 码 / Medium 19 码 / Large 8 码，并集 25 码），另两个 `SetComplexBuildings` 节点各带一份拼写不同的 `BuildingStyles`（喂复杂足迹建筑，TL 不需要进去）。只改子图的用户参数默认值**完全无效** | 改每个调用节点 `subgraph_instance` 上的覆写：`PCGGraphParametersHelpers.get/set_string_parameter(inst, "BuildingsStyles", …)`，`is_overridden()` 可确认。字节 grep `.uasset` 找逗号分隔的样式码列表，比扫节点属性可靠 |
| **35** | **样式码还要过一道名单：`CitySampleBuildingBDF_NamesOnly_PCG`**（27 个 Name）。CoreProcess 把名单 JOIN 成串，请求的样式码**不是其子串就被丢掉** | 复制名单资产到 `/Game` 追加新码，`LoadCitySampleData.PCGLoadDataAsset_1.asset` 指过去（`tl_names_with_tl.py`）。`PCGParamData` 加条目：`set_name_attribute(unreal.PCGPoint(), md, "Name", code)`；按 key 读：`p = PCGPoint(); p.import_text("(MetadataEntry=%d)" % k)` |
| **36** | **元数据 getter 类型不匹配时不抛异常，返回哨兵值**：Float 上用 `get_double_attribute` 得 `0.0`，String 上用 `get_name_attribute` 得 `"None"`。曾因此误判「27 个样式的高度字段全是 0」 | 先 `md.get_attributes()` 拿真实类型再选 getter。`Levels.BuildingToken` 是 **Name**，其他 `BuildingToken` 是 String；`Mod_Name` 是 String |
| **37** | **BDF 行里有一批「派生字段」，照抄源数据就错**：`Levels.Size` = `LevelHeight`；LV0 高 0.5；`MaxBldgHeight` 开放上限 200000；`VerticalGrammar` 必须带 `*`；`PivotOffset = (0, -run 中心, -LevelHeight/2)`；外角符号必须有 `C_E`。单位全是厘米 | 照 `migrated-citysample-library.md` §3.2 的表逐项对照。日志里的 **`Unmatched token found in grammar: C_E`** 意味着某层缺符号行，样式其实已经进了语法 |
| **38** | **三次实测：紧跟在保存一个被图引用的资产之后，同一次调用里依次跑 `pcg.FlushCache` + `cleanup_local` + `generate_local`，`generated` 都停在 False、实例数 0。** 每次换成另起一次调用、只跑一个 `generate_local`，都成功了。成因未定位，可能是前面的保存，也可能是同一调用里的 `FlushCache`，两者没有分开测过 | 把保存和生成分到不同调用里；生成后读 `generated`，为 False 就再单独触发一次 |
| **39** | **一个被引用的资产无法 delete+duplicate 重建**：`ForceDeleteObject` 拒绝并警告 package 可能损坏，随后 `duplicate_asset` 因目标已存在而失败 | 原地修补：读出点、改值、`set_points`，最后用 `EditorAssetLibrary.save_asset(path, only_if_is_dirty=False)` 落盘（单独 `save_loaded_asset` 实测没刷新 mtime） |
| **40** | **切关卡前不要在同一调用里 `unreal.SystemLibrary.collect_garbage()`**：实测在 `LoadLevel` 内触发断言 `!LevelList.Contains(TickTaskLevel)`（`FTickTaskManager::FreeTickTaskLevel`）编辑器崩溃 | 只做 Python 侧 `gc.collect()` 与清全局（第 25 条），引擎 GC 交给 `LoadLevel` 自己。崩溃后 `Saved/Autosaves/PackageRestoreData.json` 会让下次启动卡在恢复弹窗、桥不响应：先挪走 `Saved/Autosaves` 再启动 |

## 7. 2026-10-12 第五次实测新增（样条建筑任意角转角时踩到）

| # | 坑 | 规避 |
|---|---|---|
| **41** | **`IsClockwiseXY` 的命名和标准约定相反。** UE 的 `ForceClockwise`（shoelace 叉乘项取负号）判定的"顺时针"，对应标准 shoelace 公式的**正**面积——也就是 `corner_math.signed_area > 0` 称为"逆时针"的那一侧。`ForceClockwise` 之后：凸角 ⇔ `SplineToSegment` 给出的转角 > 0，模块外立面（`MakeRotFromYZ` 之后局部 +X）在行进方向右侧 | 不要去"修正"这个命名错位——按 UE 的实际行为写判断，不要按函数名字面意思猜 |
| **42** | **`add_node_copy` 是唯一能带走内联 pin 默认值的办法。** 直接 `AddNode`/`UpdateNode` 建的新节点，metadata 算子（如 `PCGMetadataMathsSettings`）的逐 pin 内联默认值无法从 Python 设置——`default_values`/`DefaultValues` 两种大小写都不存在或受保护（`q3_has_default_values_prop=false`，见 task-1 spike） | 凡是 Epic 现成图里已经配好内联默认值的节点，用 `graph.add_node_copy(existing_node.get_settings())` 复制过来，而不是新建同类节点再试图设默认值；新建节点改用显式 `CreateAttributeSet` 常量节点连线喂值 |
| **43** | **PCG 图的用户参数（User Parameters）不能从 Python 新增。** `UPCGGraph` 没有暴露"加一个 Double/Int 用户参数"的 Python API | 复制一个已经带着所需用户参数的现成图（如 `/CitySamplePCG/PCG/DataAssets/Buildings/PCG_Bldg_SGD_test` 自带 `Double` 型 `Height`），再清空其节点重新搭图；参数名和类型继承自被复制的资产 |
| **44** | **给 `PCGComponent` 重新 `set_graph` 会清掉组件上已有的图实例参数覆盖值。** 实测：先 `set_graph(G)` 并设置 `Height=3000` 的覆盖，之后再对同一组件调用一次 `set_graph(G)`（哪怕图资产本身没变），`Height` 覆盖值丢失、读回的是图默认值（曾导致意外出现 13 层重复楼层而不是预期的 6 层：`(5000-920.5)/300≈13.6→13`） | **重新 `set_graph` 之后必须重新应用一遍所有图实例参数覆盖**，不要假设"图没换就不用重设参数"；脚本里把"设图"和"设参数"算作一个不可拆的步骤 |
| **45** | **`UPCGGraph.remove_nodes`（复数）在 Python 侧是只出参、不收参的桩方法。** `graph.remove_nodes(doomed_list)` 报 `TypeError: remove_nodes() takes no arguments (1 given)`；不传参调用则什么也不删，直接返回 `[]`。C++ 签名是 `void RemoveNodes(TArray<UPCGNode*>& InNodes)`，这个非 const 引用"输出参数"被反射层处理成了零参方法 | 改用单数 `graph.remove_node(n)` 逐个删，功能等价，只是不走批量/单次 notify 的路径 |
| **46** | **`PCGComponent.get_generated_graph_output()` 的每条 `TaggedData.data` 不是直接的 `PCGBasePointData`，而是包了一层 `PCGDataPtrWrapper` struct。** 直接 `isinstance(td.get_editor_property("data"), unreal.PCGBasePointData)` 恒为 `False`，循环悄悄读到 0 行却不报错 | 先 `wrapper = td.get_editor_property("data")`，再 `d = wrapper.get_editor_property("data")` 拆出真正的数据对象；拆出来的往往是 `PCGPointArrayData`（没有 `get_points()`），需要再调一次（已废弃但仍可用的）`to_point_data()` 转成 `PCGPointData` 才能 `get_points()`/`mutable_metadata()` |
| **47** | **`PCGMetadataStringOpSettings` 的三个数据 pin 不叫 `InA/InB/InC`，而是 `In`/`Search`/`Replace`。** 实测 `REPLACE` 操作的 `input_pins` 为 `In, Search, Replace, Execution Dependency, Overrides, SearchCase, InputSource1, InputSource2, InputSource3, OutputTarget` | 连字符串替换节点的边时用这三个真实名字，不要套二元算子 `InA/InB` 的命名习惯 |
| **48** | **`PCGMetadataMakeVectorSettings` 默认 `OutputType` 是 Vector2，只有 `X`/`Y` 两个输入 pin，没有 `Z`。** 不显式设置就拿不到 Z 分量输入，连线会找不到 pin 或悄悄只做了 2D | 建节点时显式 `output_type=unreal.PCGMetadataTypes.VECTOR`，才会出现 `X`/`Y`/`Z` 三个 pin |
| **49** | **`PCGAttributeReduceSettings` 是逐个输入数据分别归约的，不会跨多条 data 合并。** 直接把"每条楼层边一条 data"的 `DuplicateCrossSections` 输出喂给 Reduce(MAX)，会对每条 data 各算出一个最大值，等价于**每栋楼出一个屋顶 Z 值的点数据集合**而不是一个——实测因此多生成了按楼层数重复的屋顶（16 层楼出了 16 份屋顶装饰） | 归约前先 `Merge` 把所有要参与同一个最大/最小/平均值计算的 data 合成一条，Reduce 节点才会在合并后的单条数据上算出唯一值 |
| **50** | **`SplineToSegment` 给每段的横向（跨墙宽度）坐标系默认是 `[0, 1]`，模块按 `SubdivideSegment` 放在这个区间的中点，相当于整面墙向内缩进了半个单位（量出来是 0.5 cm）。** 扇形件的轴心钉在顶点/立面线上，和这 0.5 cm 缩进的墙对不齐 | 要让墙体和扇形件共享同一条立面线，把横向坐标系改成 `[-0.5, 0.5]`（而不是 `[0, 1]`），使模块中心正好落在立面线上 |

## 8. 2026-10-16 PyPCG Python 节点首测

| # | 坑 | 规避 |
|---|---|---|
| **51** | **`SystemLibrary.line_trace_single` 返回的 `HitResult` 在 Python 里几乎读不动。** 5.8 中它直接返回一个裸 `HitResult`（不是 tuple），`get_editor_property("location")` 报 `protected and cannot be read`；`unreal.GameplayStatics` 也没有 `break_hit_result`（`dir()` 里没有任何带 hit 的函数）。另外 `TraceTypeQuery.TRACE_TYPE_QUERY1` 已弃用 | 用 `hit.to_tuple()`：`(blocking_hit, initial_overlap, time, distance, location, impact_point, normal, impact_normal, phys_mat, actor, component, ...)`，`parts[0]` 判命中，`parts[4].z` 取高度；通道写 `unreal.TraceTypeQuery.ECC_VISIBILITY` |
| **52** | **`PCGSpatialData.k2_sample_point(transform, box, None)` 在 Python 里命中时返回裸 `PCGPoint`，未命中时返回 `None`**（不是 `(bool, point)` 元组）。`Get_MeshTerrain`（Final）在 demo 关卡交出的是 `PCGMeshPartitionData`，在 (0,0) 采到 z=2536.126，与物理射线 2536.118 相差 0.008 cm——真射线投射，不是回传查询点 z | `pypcg.ue.terrain.Terrain.height` 按"PCGPoint 即命中、None 即未命中"判断；不需要 §4.3 的射线回退。`Terrain.kind` 记录数据类名，探针报告里 `TerrainKinds` 就是它 |
| **53** | **`build._reset_to_class_defaults` 不能碰图自带的输入/输出节点。** 新建 `PCGGraph` 的 `DefaultInputNode`/`DefaultOutputNode` 导出里带 `bHasAddedDefaultPin`（输出节点还带 `Pins`），slim IR 不列它们，于是被当成"偏离 CDO 的陈旧键"去重置，而 `bHasAddedDefaultPin` 是 protected，`set/get_editor_property` 直接抛 `RuntimeError` | 重置循环跳过 `ir.IO_NODES`（与 `compare.slim_normalize` 清空 IO 节点 settings 的口径一致）；修好后探针图 `LAST_CDO_RESETS == []`、`diffs: 0` |
| **54** | **Python Data Processor 节点里 stage 抛异常会响亮地报出来**：`LogPython: Error:` 整段 traceback（含 `pypcg/stages/sNN.py` 的行号），外加一行 `LogPCG: Error: [<组件> - Python: s00_probe (Source Input)]: Python: RuntimeError: probe failure`；`run_unreal_script` 那一侧照样 `Script succeeded`（生成是异步的） | 排查 stage 失败去 `Saved/Logs/PCG_Claude.log` 搜 `LogPCG: Error` 和 `Python:`；不要以 spawn 调用的返回值判断 stage 是否跑通 |
| **55** | **热重载由 `host.run` 的 `_fresh()` 负责，不靠桥脚本。** 实测：故意在 `sys.modules` 里留一个 `pypcg.stages.s00_probe` 并把 `VERSION` 改成 99，再直接 `generate_local(True)`（不清缓存），记录到的 `Version` 是磁盘文件里的 3。改完 stage 文件无需重建图、无需重启编辑器 | 改 stage 后只要重新生成；但组件上的**实例参数覆盖会一直留在复用的探针 actor 上**（例如 `BenchPoints=100000`），换测试前先 `{"phase": "remove"}` 再 spawn |
| **56** | **`PCGBasePointData.to_point_data()`（已弃用）在 Python 节点里照常可用**：对 `PCGPointArrayData` 调用返回 `PCGPointData`、点数正确，只发一条 `DeprecationWarning`（"use To Point Data With Context instead"），不会让节点失败。`PCGMetadataTypes` 枚举值与 `getattr(unreal.PCGMetadataTypes, "DOUBLE")` 等成员相等且同哈希；`SoftObjectPath(...).export_text()` 返回不带引号的纯路径 | `convert._points_of` 的 `to_point_data()` 回退可保留；若将来日志噪声成问题，改用 `to_point_data_with_context` |
| **57** | **点写出器（`convert._point_data`，逐点 `PCGPoint` + `set_points`）10 万个无属性点耗时 1.13 s**（整段 stage 计时，含 Python 侧 `Points.add`），比 G7 预估的 0.7 s 慢，但远低于 3 s 门槛 | 散布类 stage 每次十万点量级可接受；到百万点量级（≈11 s）再考虑把批量写回下沉到 C++ |
| **58** | **阶段 7 官方图的计数在不同会话之间变过（2026-10-16／17），而在固定输入下连续三次完全相同（2026-10-19）。** 实测 2026-10-16／17：阶段 7 的**三次**官方生成（同一图资产、同一组件、同一 seed，中间只做过 restore）给出**三个**不同总数——**286 378** / **286 232** / **286 371**（跨度 146，0.05 %），连 `SM_Lane_Divider_40_201` 一个 mesh 都取了 19 817 / 19 832 / 19 817 三个值（`Tools/pypcg/data/s07_fixture.json`、`Saved/Reports/v2/s07/{official,official_after}.json`）。2026-10-19 同一会话、同一上游输入下连续三次都是 **286 393**；把阶段 5 的公园改成与官方逐位相同后，slim 上游下的阶段 7 也是 286 393、逐 mesh 相同。所以早先的离散**可能**来自各次生成之间上游输入不同（如末位浮点不同的地标外形），而不是阶段 7 自身不确定——尚未证明，见 62。`official_after` 记录只能证明"官方图还跑得出来" | 把下游差异当噪声之前，先在**同一会话、同一输入**上把官方图跑两次；若两次相同，这个差异就属于端口（见 62），不是噪声 |
| **59** | **`generate_local(True)` 之后立刻 `read` 会读到上一轮的数据，而下游阶段尤其容易踩到。** 实测 2026-10-16：阶段 9（读阶段 7 的产物）紧跟在自己 `gen` 之后 `read`，拿回 `items=1273` 正确但 `instances=0`；隔一段时间再 `read` 一次，`instances=11255`（官方基准也是 11255）。同一轮里阶段 8 的 `instances` 是对的，所以**不是每次必错，而是"还没算完"** | 阶段 7 这一级别的慢阶段，`gen` 与 `read` 之间等 **100–120 s** 再读；读到 `instances` 比预期少一个数量级时，**先重读一次再怀疑端口**（`items` 对而 `instances` 错，正是"读早了"的指纹） |
| **60** | **带地形（surface）输入的 stage，V1 的 `replayed` 恒为 0——`PCGMeshPartitionData` 进不了 run record。** 实测 2026-10-17：阶段 8（Highways）的 `inputs` 里含 `MeshTerrain`，`geo.to_json` 只把一个 `{"kind": "Terrain"}` 占位写进 record，`from_json` 拒收，于是 `pypcg_v1_editor.py` 取 `inputs = None` 不去重放，`replayed: 0`。它**不是**回放失败；V1 的 failures 仍为空，确定性由「五个 seed 的记录逐位相同」佐证。连带一个盲点：V2 的 determinism 检查比的是官方图自己（见 58），对这类 stage 也测不到种子化的确定性 | 带 surface 输入的 stage 别把 `replayed: 0` 当失败去查；确定性证据改用「同一 stage 多 seed 的 slim 记录逐字段相等」（阶段 8 五份记录面积到小数点后一位、实例数 81835 完全一致）。需要真正的回放证据时，把 surface 换成一张可记录的高度表再喂进 stage |
| **61** | **官方图在生成过程中可能直接把编辑器驱动到崩溃：`Illegal call to StaticFindObjectFast() while garbage collecting!`**，栈顶是引擎原生节点 `FPCGGetClassFromAttributeElement::ExecuteInternal()`（`PCGGetClassFromAttribute.cpp:175`）里的 `FSoftObjectPath::ResolveObjectInternal()`。实测 2026-10-17 13:05（本地时间）：阶段 5 的 V2 收尾里连着跑下游官方生成（13/16/18），第 18 阶段那次把编辑器打崩，进程留在崩溃上报窗口里、`127.0.0.1:8777` 端口消失——后续所有桥调用全部失败。崩溃点不在 Python 侧，也不在任何 stage 模块里；我们的 `gen`/`restore` 序列是否提高触发概率尚未测 | 桥连不上而 `UnrealEditor.exe` 还活着，先看 `Saved/Logs/PCG_Claude.log` 尾部有没有 `Crash in runnable thread`，别当成"编辑器没开"。用户关掉崩溃窗口、重开编辑器并**重新打开 demo 关卡**后才能继续（不能自己杀进程）。之后跑长批量生成时，每个 `gen` 之间留间隔，并把已完成的 `read` 记录落盘，崩了就从记录续，不必重跑整段 |
| **62** | **下游 stage 对上游外形的"末位浮点"敏感：差 1e-12 cm 就能改变几百个实例。** 实测 2026-10-19：阶段 4 的六边形与官方差 ≤2.9e-12 cm（`4000.000000000001` 对 `3999.999999999998`），阶段 15 从 35 239 变成 35 008（-0.66 %，屋顶道具和一个墙体 mesh）；阶段 5 的公园差 ≤1.6e-11 cm，阶段 7 从 286 393 变成 286 319。tag、逐点 rotation 单独换都没用，把官方 double 原样喂进去才恢复。阶段 15 和阶段 7 在固定输入下自身是确定的（两到三次官方生成计数相同）。两个机制：**阶段 4**（单位四元数下）是三角式的写法与角度基准——官方顶点 = `-(R cos p, R sin p)`，`p = 120 - 60k` 度，`ngon` 从 -60 起步给出同一组点但末位不同；**阶段 5** 是四元数的运算顺序加 actor 自己存的四元数——局部点经 `FQuat::RotateVector`（`T=2(q×v); v+wT+(q×T)`，无 FMA）再加平移，从 rotator 用 UE 公式重算四元数**拿不回同样的位** | 发布"会被后续阶段采样的几何"的端口，必须复现引擎的**运算顺序**和**原始输入位**，不能只做到 1e-11 的数值一致：用 `geo.place`（`geo.quat_rotate` + 平移），四元数取 `stage_api.volume_quat`（`convert` 把点的 `transform.rotation` 原样带进 `Points.quat`）。判"一致"用逐位比较（`==`），别用容差；V2 的 `downstream: []` 不看量级，要自己比下游实例数和逐 mesh 表 |
| **63** | **Python 写出的样条，控制点旋转全是单位旋转；转角语法靠它判转角，于是一个转角都不放，而且不报错。** 实测 2026-10-19（阶段 10）：官方边界样条的控制点带着 `GetSplineControlPoints` 给的 yaw（逆时针多边形上该顶点出边的方向），`CreateSpline` 和 `Transform_Splines_Reverse` 原样保留；`SGD_Sidewalk_Corners` 用它判转角。端口写出的两段边界位置、切线、类型与官方逐点一致（≤0.0033 cm），却一个转角都没放——官方 1 228 个转角里缺的 112 个**全部**在这两段上；补上控制点 yaw 后六种转角网格计数全等、位置 ≤0.0046 cm。同一批样条喂人行道语法（`SGD_Sidewalk_A`）时计数完全一致，那个语法不读旋转 | 判"样条一致"不能只比位置/切线/类型，还要比控制点旋转（`SplineDataToJson` 不输出它，`convert.from_pcg` 也不读）；凡是喂给转角类语法的样条，用 `geo.Spline.rotations` 写上官方链路给的控制点 yaw |
| **64** | **Clipper 结果环的"起始顶点"取决于布尔运算所在的坐标系。** 引擎的多边形运算在多边形自己的框架里做（`CreatePolygon2D` 的框架：顶点均值为原点、yaw -90；Lots、街区、道路多边形实测都是），世界坐标里算出的环几何相同，但起点不同——阶段 10 的城市外扩差了 754 个顶点，主塔内缩也错位。下游凡是"从起点断开"的步骤（把闭合样条当开路径裁剪的 `ClipPaths`、`Extract_Segments` 的输出顺序）都跟着变 | offset / contract 这类会决定下游起点的运算，用 `geo.areas.in_frame` 在多边形框架里做；只比面积或顶点集合发现不了这个差异，要比顶点顺序 |
| **65** | **"读早了"可以是半新半旧：几个 spawner 完成时间不同。** 实测 2026-10-19：阶段 10 从 slim 切回官方后第一次 `read` 得到 220 021——地砖是官方新算的 155 859，人行道/转角却还是上一次 slim 生成留下的实例；之后连续三次读都是 220 128（与另一会话的官方记录逐 mesh 相同）。差异长得像"官方图自身不确定" | 切换图之后的第一个官方记录，过 1–2 分钟再读一次，两次逐 mesh 相同才落盘；不要拿这种半旧读数去证明官方图不确定（58） |
| **66** | **官方图引用的贴图本项目里没有，整条链静默产出 0：阶段 13 的外围树林一棵都不放。** 实测 2026-10-19：`Write_Attribute_fromTexture` 读 `/Game/Textures/Noise/T_CloudNoise_4k`，项目里不存在（只有 `T_Noises_Clouds_4k_`），`GetTextureData_0` 只在日志里报一行 `LogPCG: Error: ... could not be loaded`，两个贴图写节点都输出空——6 518 个已投影的树点进去、0 个出来，`SM_BlackAlder_Field_05_PP` 一个实例都没有（官方记录里的 515 棵 Black Alder 是广场白桦替换出来的）。阶段 18（OuterForest）已查：官方 IR 里两个 `Write_Attribute_fromTexture`（`Subgraph_12` / `Subgraph_2`）读同一张贴图，唯一的 spawner `SpawnForest_0` 在它们下游，磁盘上三份阶段 18 官方记录实例数全是 **0**。Task 27 的小镇跑同一张阶段 13 slim 图、同样的原生贴图节点，外围树林也会是 0 棵——这是预期，不是回归 | 某个 spawner 的实例数为 0 时先去日志搜 `could not be loaded`，别当成端口丢了点；端口要复现"官方产出为空"而不是去补贴图。需要测下游行为时，只在 oracle / tap 图里用 `set` 换一张存在的贴图（不要改出货图）。阶段 18 的端口：官方产出按"空"预期，贴图读取保持原生，`UseIndexattribute` / 随机范围照阶段 13 的做法用替换贴图的 oracle 量 |
| **67** | **V2 的 slim `gen` 以前不重置组件 seed：slim 图里保留的原生节点按组件 seed 抽随机数，Python 的 seed 不变，结果却变了。** 实测 2026-10-19：为官方多 seed 采样把阶段 13 组件 seed 设成 31337 后，同一个 Python seed 42 的 slim 运行里，五个保留的 fitting 节点给出 494 个而不是 496 个广场 item（实例 33 702 对 33 704）；重新 `gen official` 把组件 seed 设回 42 后复原 | 已修：`pypcg_compare_stage.py` 的 slim `gen` 现在也把组件 seed 设回 `_state.json` 里的出货值。任何改组件 seed 的探针跑完都要 `gen official` / `restore`；比较同 seed 的两次 slim 运行前先确认组件 seed |
| **68** | **Python 写回的 Polygon2D 和官方的"同一块地"几何逐位相同，下游结果却不同：框架不一样。** 实测 2026-10-19：官方 Lots 体积发布的地块全部带着 City 共享的多边形变换（平移 (1 874.36, -1 673.60)、yaw -90），`MakePolygon2DData` 按每块自己的质心建框架；阶段 14 在多边形自己的框架里做 contract / 切分（64），同样五块地喂进去，停车线 834→832、箭头 40→32、车辆重新分布（13 535→13 545）| 已修：`host.run` 给每个输入多边形登记一次（只在本次运行的局部变量里，traps 25），stage 原样交回的输入多边形直接转发引擎自己的数据对象（`convert.passed_through`），框架和局部坐标都保住；之后阶段 14 与官方逐 mesh 相同。新造的多边形仍走 `MakePolygon2DData`，这个限制还在（s10.md 4.1） |
| **69** | **`Custom_Projector_with_rotation_fix` 的三个角点按点的缩放放置（`ResetPointCenter` 用 `TransformVector`：先缩放再旋转）。** 阶段 10 的地砖缩放都是 1，看不出来；阶段 13 的广场套件点有缩放，不乘缩放时 32 108 个点里 1 044 个倾角偏到 0.25°；乘上后全部一致（位置逐位、四元数 ≤3.4e-9）。另外：中心点没投到地面时点保留、density 0、z 再加一遍原 z（翻倍），这种点在 `Compose_Points_Difference`（Binary）里不扣任何点 | `geo.ground.project_tile` / `project_point` 传 `scale=`（和 `quat=`）；未命中按 `project_point` 处理 |
| **70** | **`Assign_Assets` 的 `UseIndexattribute` 不丢点，随机范围也不是"min = max = v"。** 实测 2026-10-19（阶段 13 `Subgraph_26`，oracle 换贴图）：点的 index 按条目的整型 `$Index` 读（截断）；对不上的（8、9）因 `bKeepUnmatched` 默认 true 而保留，`Asset` 取属性默认值 = 第一个条目，6 518 个点各字段逐位一致。随机范围的 pin 值 v 在 CoreProcess 里变成：位置 / 旋转 ±v（旋转向量 X/Y/Z = Roll/Pitch/Yaw），缩放 1 ± v（`UniformScale` 时三轴同一个数）——6 518 次抽样缩放 0.8001..1.1997、pitch/roll ±2、yaw ±180 | 用 `geo.assets.index_picks` 和 `_pin_range`；Task 12 的"单值即定值"读法已改。另：大图的 tap / oracle 生成在 `run_unreal_script` 调用里同步跑，常会超过桥的 keepalive 报 `connection closed mid-call`，编辑器并没崩（端口仍在 LISTENING、日志无 crash），等一两分钟再读即可 |
| **71** | **slim 连续换 seed 时，`generate_local(True)` 会隔一次空跑：返回成功，日志里却没有这次的 `PyPCG sNN` 行，读到的是上一次的实例。** 实测 2026-10-20（阶段 10 V2 重跑）：seed 7、13、101、977、42 依次 `gen` → `read`，只有 7、101、42 真的跑了；13 和 977 的 run record 拷过来带的是 Seed 7 / 101，地砖份额与上一个 seed 逐位相同。从官方图切过来的第一次 slim `gen` 总会跑 | 每次 slim `gen` 之后先在 `Saved/Logs/PCG_Claude.log` 里确认有新的 `PyPCG sNN ...` 行（或比对 run record 的 `params.Seed`）再 `read`；没跑就重发一次 `gen`。V2 verdict 前把五份 `slim_<seed>.run.json` 的 Seed 核一遍 |
| **72** | **引擎把多边形/样条"读回"时会重算坐标，末位和存进去的不一样；要逐位复现就得照抄引擎的运算。** 实测 2026-10-20（阶段 11）：`ToPoint` 读多边形顶点走 `GetTransformAtDistance(i, 0)`——`FSegment2d::PointAt(-Extent)` 重算段起点再乘框架，和 `Polygon2DToJson` 的 `TransformPosition(V)` 在 54 / 3 384 个顶点上差末位；`CreatePolygon2D` 的框架是 Newell 平面 + `MakeFromZ`，质心用 `operator/=`（乘倒数，不是除）；距离采样走 `FSplineCurves` 的 **float** 重参数表、`CubicInterp` 的 float 权重，且在样条**局部**算再加平移（`c0 + c3 != 1`，世界坐标里算差 6e-3 cm）；`AttributeReduce` Average 是 `sum x float(1/n)`。照这些写（`pypcg.geo.frames`），阶段 11 的 379 个足迹逐位等于官方 | 需要引擎读回值时用 `convert` 给的 `Polygon.vertices`（= `get_location_at_distance(i, 0, True)`）和 `Spline.frame`；重建多边形/采样样条用 `geo.frames`，别在世界坐标里近似；判一致用 `==` |
| **73** | **`unreal.Quat(x, y, z, w)` 在 Python 里把四个分量都舍入成 float32；`Transform.rotation` 读出来却是 double。** 实测 2026-10-20（阶段 12）：把官方点的引擎四元数经 `unreal.Quat(*q)` 写回 `PCGPoint.transform`，读回 `-0.9670166969299316`（float32），原值 `-0.9670166737402451`；改成 `q = unreal.Quat(); q.x, q.y, q.z, q.w = ...`（或 `set_editor_property` / `import_text`）四个分量逐位保留。`unreal.Vector(*v)` 不受影响（位置逐位）。另：只从 rotator 重建旋转（`Transform(loc, Rotator, scale)`）本来就拿不回同样的位 | 要把引擎四元数原样写回点时，用属性赋值建 `unreal.Quat`；`convert._point_data` 在 stage 设 `EXACT_ROTATIONS` 时这样写（阶段 12：差集后 5 765 个点与官方逐字段相同）。`convert._ue("Quat", ...)`（Quat 型属性）仍用构造函数，尚未改 |
| **74** | **`unreal.Rotator(pitch=..., yaw=..., roll=...)` 在 Python 里把三个角都舍入成 float32（和 73 的 `unreal.Quat` 同病）；而引擎的 `FRotator::Quaternion()` 走 SVML 的 sincos，和 Python 的 `math.sin/cos` 在末位上不一样。** 实测 2026-10-20（阶段 16）：公园中心点的 `$Rotation` 是"多边形最长边起点的 rotator → 再转回四元数"（`Place_Point_AtCenter_CoreProcess_Loop` 的 `CopyAttributes_4`），yaw 34.22265945387145；Python 公式算出的 z 分量差 1 ulp，四条横路和 Met 足迹跟着差 1e-11 cm，Met 的 CHA 楼道具差 ±8（trap 62）。用 `r = unreal.Rotator(); r.yaw = y` 再 `r.quaternion()` 才逐位等于官方 | 需要引擎四元数时走 `ctx.ops.rotator_quat(p, y, r)`（`pypcg.ue.ops`，属性赋值建 rotator）；yaw 本身要按引擎的读回算（`geo.frames.vertex_points`：`FSegment2d` 先归一化方向再 `MakeFromXZ`）。样条控制点旋转要保 double 的 stage 设 `EXACT_SPLINE_ROTATORS`（`convert._rotator_exact`）；默认路径没改，旧 stage 不受影响 |
| **75** | **`Assign_CitySampleBuildings` 读足迹样条控制点的旋转（不只是位置）：足迹逐位相同，楼的道具照样不同。** 实测 2026-10-20（阶段 16 的 Met）：官方足迹是 `Transform_Project` 后的 CURVE 样条（自动切线带 z 分量）经 `Transform_Level` → `GetSplineControlPoints` → `CreateSpline` 重建的线性样条，每个控制点带 `MakeFromXZ(切线, up)` 的旋转（pitch ±0.9 / ±1.4°）。Python 写成单位旋转时 4 个角点逐位一致、墙体一致，`AC_Window`/`Lamp_Wall`/`Banner` 等道具仍差 ±8；写上这组旋转后 Met 的 46 种 `SM_BLDG_*` mesh（1 067 个实例）全部等于官方 | 给建筑节点喂足迹时，按官方链路补上控制点旋转（`s16_park_geometry.footprint_rotations`：投影后角点的自动切线）；和 63（转角语法读旋转）是同一类坑 |
| **76** | **`Transform_Project` 的最近目标搜索在 GPU 上（`CustomHLSL_1` 的 float32 `distance`），Python 复现不了末位：阶段 1 的环形压平 261 312 个高度里只有 247 241 个逐位相同，其余差 GPU 距离的 ±1 个 float32 ulp（-1：11 424，+1：2 642，-2：5；z 最多 0.0012 cm），换 FMA / 正确舍入 / rsqrt 哪种运算顺序都对不上全部。** 实测 2026-10-20（Task 24）：目标是多边形表面采样（0.5 点/m²，格 `sqrt(2e4)` cm、偏移 `(格-0.002)/2`、ratio 1），掩码 = `AttributeRemap_4`（double 算、存 float）再过 `AttributeRemap_3` 曲线（`FRichCurve` 的 float Bezier），最后 double Lerp；纯 Python 最近目标搜索（只算 double）就要 138 µs/点 = 36 s/次。反过来，结果对目标多边形的**末位**不敏感：Python 写的环形洞（convert 折线，与官方 CreatePolygon2D 顶点差 ≤0.11 cm）、单位变换的世界坐标城市样条，喂给原生投影后 261 312 个写回点与官方逐位相同 | 投影类 `Transform_Project`（带 falloff、投到多边形/样条）留原生，Python 只出它的 Secondary 形状；判"一致"比最终点位（逐位），不比中间形状 |
| **77** | **阶段 10 的车辆数会偶发跳一次：同一份逐位相同的地形下，一次生成 220 150（`vehCar/vehTruck/vehVan` 多 11 辆、各带 `SM_All_Trans_*` 孪生，`uh4ocfafa` 少 2），之后三次生成读到的都是官方的 220 128（其中两次是同一图同一输入的重跑，ISM 组件对象被复用，无法用对象名证明是新生成）。** 实测 2026-10-20（Task 24 下游）：那次的两次读数（隔 70 s）都是 220 150；历史上官方 s10 记录全是 220 128，Task 17 的 `trial_slim_42` 也出现过一次 veh03 2496。另：探针图同设置重建后**立刻**读，读到的是上一轮输出对象（同名 `PCGMeshPartitionData_879`），要么等 20–30 s，要么比对输出对象名确认是新生成 | 下游出现小幅差异时先在同一输入上重跑该下游 stage（trap 58），并用输出对象路径名确认读到的是新生成；阶段 10 的车辆数差异不能单凭一次读数归给上游 |
| **78** | **编辑器异常退出（崩溃、卡死被结束）后重启，会弹出「Restore Packages」；点了恢复，就会把 `Saved/Autosaves/` 里 demo 关卡的自动保存版本写回 demo 的真实外部 actor 文件——等于悄悄保存了 demo。** 实测 2026-10-19 11:37 与 2026-10-21 11:15 两次重启：`Plugins/CitySamplePCG/Content/__ExternalActors__/Levels/L_CitySamplePCG_Demo` 里 18 个文件被改写、11 个探针/调试 volume（`PCG_T10bTap`、`PCG_T12_AssignProbe`、`PCG_T24SlimTap` 等）被写成正式 actor；之后用 demo 作模板复制出的关卡也带上了它们。该目录被 `.gitignore` 忽略，git 救不回来；`E:\CitySample 5.8\Plugins\Experimental\CitySamplePCG\Content\` 里有逐字节一致的原件（其余 176 个文件与之完全相同） | 异常退出后**重启前**先把 `Saved/Autosaves/CitySamplePCG` 挪到 `Saved/Autosaves_bak_<日期>/`；重启时若仍弹「Restore Packages」，选不恢复。怀疑已被写回时，逐文件 `cmp` 对照 `E:\CitySample 5.8` 的同名文件，按时间戳找出被改写的，先备份到 `Saved/demo_restore_backup_<日期>/` 再拷回原件 |
| **79** | **从 Python 先 `new_blank_map` 再 `load_level` 一个刚保存过的大关卡，会在拆掉空白世界时触发引擎断言把编辑器打崩**：`Assertion failed: !LevelList.Contains(TickTaskLevel)`（`TickTaskManager.cpp:1992`），栈在 `UEditorEngine::EditorDestroyWorld` → `IncrementalDestroyGarbage`。实测 2026-10-21 16:09：`L_PyTown`（54 万实例）保存后 `new_blank_map(False)` 成功，紧接着 `load_level("/Game/PyPCG/L_PyTown")` 崩溃；关卡文件已在崩溃前落盘、完好，重启后直接 `load_level` 一次即可、实例数与保存前逐卷一致 | 想验证"保存后能否重新加载"时，别在同一会话里先切空白地图再加载；关掉编辑器重开后直接 `load_level`。崩溃后**重启前**先按 trap 78 把 `Saved/Autosaves/` 下的 CitySamplePCG / Game 挪走 |

## 9. PyPCG 计划实测汇总（2026-10-15 ~ 10-21，18 张图移植 + 18 步小镇）

> 用法见 `docs/pypcg-guide.md`。本计划测出的事实大多已在第 8 节逐条记录（51–79），这里先给索引，再补 80–84 五条第 8 节没有的。

| 主题 | 条目 |
|---|---|
| Python 节点本身：报错去哪看、热重载、`to_point_data` 弃用、点写出吞吐 | 54、55、56、57 |
| 从 Python 读引擎数据：`HitResult` 读法、`k2_sample_point` 命中返回裸 `PCGPoint` / 未命中 `None`、getter 类型不符返回哨兵 | 51、52、36 |
| 元数据条目：`import_text("(MetadataEntry=%d)")` 读、`set_name_attribute` 写 Name 属性 | 35、82 |
| 构建瘦身图：IO 节点不能重置、未接线的动态 pin 会剔除整个节点 | 53、80 |
| 生成与读取的时序：读早了、半新半旧、隔一次空跑、组件 seed、`regenerate_in_editor` 连锁 | 59、65、71、67、81 |
| 官方图自身的不确定 / 原生节点的波动 | 58、77 |
| 逐位复现：下游对末位敏感、引擎读回重算坐标、`unreal.Quat` / `unreal.Rotator` 舍成 float32、Clipper 环起点随坐标系、框架不同 | 62、72、73、74、64、68 |
| 几何要带的"隐藏"属性：样条控制点旋转、建筑节点读足迹旋转、投影器按缩放放角点 | 63、75、69 |
| 选资产 `Assign_Assets`：`UseIndexattribute` 与随机范围 | 70 |
| 留原生的依据：GPU 投影复现不了末位、贴图缺失静默产出 0 | 76、66 |
| V1 / V2 的盲点：surface 输入 `replayed` 恒为 0；份额是百分点、按 item 的比例不是面积比 | 60、84 |
| 编辑器崩溃与恢复：生成中崩溃、Restore Packages 悄悄保存 demo、切关卡崩溃 | 61、78、79、83、40 |

| # | 坑 | 规避 |
|---|---|---|
| **80** | **Python Data Processor 的动态输入 pin 没接线，图编译器会把整个 Python 节点静默剔除**：动态输入 pin 对执行是"必需"的（`UPCGPythonDataProcessorSettings::IsInputPinRequiredByExecution`），缺一条边就整节点不跑、下游全空、不报错。Task 5 评审对照 `PCGGraphCompiler` 源码确认 | 瘦身图的每个 Python 输入 pin 都接线；`dsl.SlimGraph.to_ir` 对未接线的 pin 直接抛 `ValueError`（"an unwired dynamic pin culls the node"），不要绕过它。某个输入确实可能为空时，照样接一个场景读取，让它送空集合进来 |
| **81** | **`set_graph` 会让开着 `regenerate_in_editor` 的组件立刻自己重新生成——18 个 volume 乱序并发，下游读到上游半成品。** 实测 2026-10-21（Task 27）：`pypcg_town.py assign` 给 18 个 volume 设图后，18 个组件在 05:35 各自跑了一遍，顺序不受控；之后两次 `reset {"from": 6}` 加一遍按序重生成才恢复。关掉之后（T28b，`reset` 把每个 PCG volume 的 `regenerate_in_editor` 设成 False），第二遍的每条 `PyPCG sNN` 日志都落在自己的 `gen` 窗口里。V2 的 `prepare` 与探针脚本也是同样处理 | 任何会 `set_graph` / 改覆写的脚本之后、按序生成之前，先把所有 volume 的 `regenerate_in_editor` 关掉；只用显式 `generate_local` 生成。要保存的关卡顺带检查 `GENERATE_ON_LOAD`（小镇的 `CentralPark_Footprint`、`Roads` 原本带着，已改为按需），否则加载时会自己乱序重生成 |
| **82** | **`FPCGPoint::MetadataEntry` 在 Python 里不能 `set_editor_property`：它是 `VisibleAnywhere`（`CPF_EditConst`，`PCGPoint.h:63`），直接抛错。** 也不需要写它：对一个新 `PCGPoint` 第一次调用 `set_*_attribute(point, md, name, v)` 就会建条目（`InitializeOnSet`），`UPARAM(ref)` 的点链会把后续属性都写进同一条目。读某个条目的值时，先 `p = unreal.PCGPoint(); p.import_text("(MetadataEntry=%d)" % k)` 再用对应类型的 getter（第 35 条的路线）。Name 型属性用 `set_name_attribute` / `get_name_attribute`（类型不符时返回哨兵 `"None"`，第 36 条） | `pypcg.ue.convert` 的参数写出器不显式设 `metadata_entry`，读多个条目走 `import_text`；写 PCGDataAsset 另见记忆里的"复制后改"路线 |
| **83** | **离开 demo 关卡的 `load_level` 也会崩：只跑过只读脚本、没有任何脏包，切到 `L_PyTown` 时在拆 demo 世界时触发同一个断言 `!LevelList.Contains(TickTaskLevel)`（`TickTaskManager.cpp:1992`，`FTickTaskManager::FreeTickTaskLevel` ← `ULevel::~ULevel` ← `UEditorEngine::Cleanse` ← `EditorDestroyWorld` ← `Map_Load`）。** 实测 2026-10-21 16:30（Task 29 回归）：`Lvl_ThirdPerson` → `Lvl_TL_Showcase` → demo 三次切换都正常，demo 里只读了 census 与外部 actor 包名，切回 `L_PyTown` 时编辑器退出；切换脚本在 `load_level` 前照 `tl_load_level.py` 的做法清掉了 Python 全局里持有 UObject 的变量，前一次调用确认 `get_dirty_map_packages()` 为空。和第 79 条同一个断言，说明不只是"先切空白地图"才会触发——离开大型 World Partition 关卡（demo 约 220 万实例、`L_PyTown` 54 万）本身就有风险 | 一个会话里尽量少切大关卡；必须验证多个关卡时把 demo 放在**最后**，验证完不切走，交给用户关编辑器。崩溃后**重启前**按第 78 条挪走 `Saved/Autosaves/`；本次没有脏包，`PackageRestoreData.json` 的 `Packages` 为空 |
| **84** | **V2 里有两种容易被当成"面积比"的比例：** ① 每种 mesh 的份额阈值 `share_pp` 是**百分点**（绝对差：1.2 % → 2.0 % 是 +0.8 pp），不是相对变化；② `Ratio_Plaza_vs_Trees`、`DockRatio`、`PlazaReservationRatio` 这类参数喂的是 `Filter_RandomChoice`（`RandomPerDataset`），**按 item 抽伯努利**（每个地块 / 区域一次），不是按面积分。实测：阶段 13 的官方图换 5 个组件 seed，发布地块面积相对出货记录就是 -77..+57 %（移植 199 个 seed，出货记录在第 37–38 百分位），所以面积阈值放到 0.75；阶段 16 一次森林区随机二分决定 98 % 的实例，官方自己跨 5 个 seed 就是 -4.4..+26.1 %；阶段 9 出货记录的保留抽样是尾部事件（18 块庭院地块里 ≥6 块被保留，超几何概率约 1.7 %） | 判 V2 失败前先看该 tag 的量是不是"少数大 item 的伯努利和"：是的话用官方多 seed + 移植多 seed 的研究定阈值，并在 `docs/pypcg-v2-thresholds.md` 写清百分位；不要用"占比 × 总面积"去估期望 |
| **85** | **`UEditorLoadingSavingSettings`（autosave 开关所在的类）在 5.8 没有 Python 包装：`unreal.EditorLoadingSavingSettings` 不存在（AttributeError），snake_case 名 `auto_save_enable` 也找不到。** 实测 2026-10-22：`unreal.get_default_object(unreal.load_class(None, "/Script/UnrealEd.EditorLoadingSavingSettings"))` 能拿到 CDO，属性要用原始 C++ 名 `bAutoSaveEnable`（`AutoSaveTimeMinutes` 同理）；`set_editor_property("bAutoSaveEnable", False, unreal.PropertyAccessChangeNotifyMode.NEVER)` 写入、读回、再恢复都成立，且 NEVER 不触发 SaveConfig。终审修复的 V2 `prepare` 一开始按 snake_case 写，离线编译通过、编辑器里第一次调用就会抛——**没有 Python 包装的设置类，离线测试证明不了任何事，必须在编辑器里跑一次。** | 设置类先 `dir(unreal)` 找包装；找不到就 `load_class` 按路径拿 CDO、用 C++ 原名读写，并在编辑器里跑一次 |
| **86** | **`cleanup_local(True)` 之后同一轮马上存关卡，包里仍写进了已清掉的生成组件。** 实测 2026-10-22（单图城 `L_PyCity`）：生成后 actor 包 149 MB；`reset` 后 `save_current_level` 仍是 104 MB（内含 `ISM_SM_Sidewalk_0` 等）；探针确认 actor 上只剩 Brush + PCG 组件后，`actor.modify()` 再存，包 30 KB | 清理后要存"干净"的关卡：先等清理完成，存前对 volume 调 `modify()`（`pypcg_city.py` 的 `save` 已这样做），存完看包大小 |
| **87** | **PCG 的 Reroute（`PCGRerouteSettings`）输入只收一条边**；第二条 `add_edge` 不生效（`build._write` 报 "edge … not created"）。 | 要把多路数据并成一个输入用 `PCGGatherSettings`（Gather 保留每条数据的 tag）；合并 18 张图时 31 处跨阶段读取都是 Gather |
| **88** | **桥接调用阻塞游戏线程较久（几十秒以上）时，MCP 返回 "Unreal editor connection closed mid-call"，但脚本在编辑器里照常跑完**，结果丢失。实测：合并图 473 节点的 `build` 每次都这样。 | 长任务用 `unreal.register_slate_post_tick_callback` 推到下一帧执行、把结果写文件，调用立即返回（`pypcg_city.py` 的 `{"defer": true}`）；即使返回了 closed，也先去读结果文件再决定重跑 |
| **89** | **结构核对的 WL 匹配在大图里会"选错对称点"**：两个看似相同的节点（同类同参数）只差在汇入同一 Gather 的边序号，按名字字典序硬配一对会级联出几十条假 diff（合并图 44 / 73 条）。`compare.match` 已改为对歧义组逐个试配、取让所有颜色类平衡的那一个。注意：只要图里还有**真** diff，就没有任何配对能平衡，假 diff 会和真 diff 混在一起出现 | 看到大量 "edge 顺序" 类 diff 时先修掉非边类的真 diff（如结构体只写了一半的设置，trap 90），再看剩下的 |
| **90** | **写结构体设置（如 `ActorSelector`）时只给部分字段，导出时引擎会补全其余字段**，结构核对把它报成设置差异。 | 描述里写完整结构体：先建一次、用 `extract.export` 读回引擎补全后的样子，抄进描述（`combined._actor_selector`） |
| **91** | **重写（clear + rewrite）一个 PCG 图资产后，挂它的组件上的 graph instance 覆盖全部回到图的默认值**，组件仍指着同一个资产，看不出变化。实测 2026-10-22：重建 `PCG_PyCity` 后直接生成，地形比例 0.5（覆盖是 0.4）、阶段 6 15 项（应 50）、阶段 9 11 项（应 479），整城几乎没有建筑 | 每次重建图之后重新套覆盖（`pypcg_city.py assign`）；生成前核对组件覆盖（`gen` 已这样做：缺覆盖就拒绝） |

## 10. 2026-10-22 PyWorld（山谷世界，`docs/pyworld-guide.md`）实测

| # | 坑 | 规避 |
|---|---|---|
| **92** | **`Get_ActorData`（按 tag）能直接读另一个 PCG volume 的生成输出**：它的 `GetDataFromPCGComponentOrParseComponents` 模式拿到的就是那个组件 Output 节点收到的数据，数据 tag 原样带过来（只删含 `input` 子串的 tag）。PyWorld 的 9 个阶段全靠它串起来 | 跨阶段传数据不必用 actor 引用：给 volume 一个 tag（`PyWorld_W02`），下游按 tag 读；tag 名里别带 `input` |
| **93** | **`MeshPartition` actor 的地形定义能从 Python 换**：`set_editor_property("mega_mesh_definition", load_asset(MPD_Basic))` 立即生效，`MPD_Basic` 的 6 个材质通道（Grass Rock ForestFloor Dirt Mud Gravel）由 `Write_MeshTerrain(Channels=[...])` 加同名 Float 点属性写入，权重和为 1 时颜色正确 | 需要地表材质时先换成带通道的 MPD；`ModifierLayerPriority` 留默认 `None` 即可 |
| **94** | **PCGPrimitives 的建筑语法（`SGD_Bldg_B_Advance_Template`）只要一个足迹不合适，整个节点一栋都不生成**：足迹边 < 约 8 m 报 `SubdivideSpline: Grammar does not fit for this spline`；`Size` 450 同样失败；`Size` 2 400 报 `OffsetSpline: Invalid cardinality among pins 'In' and 'Magnitude'`。600 / 750 / 1 050 / 1 950 可用，墙顶高度正好等于 `Size` | 足迹两边都 ≥ 8 m；按层高分组时每组单独一个语法节点，坏一组不连累别组；用实测的 Size |
| **95** | **同一份足迹输入，建筑语法的实例数偶尔差 1**：三次生成 `SM_Bldg_Wall_L` 2 540 / 2 541 / 2 540（Python 输出逐项相同） | "两遍逐网格相同"对语法生成的网格要容许 ±1，比较时先确认 Python 输出相同再归因 |
| **96** | **编辑器窗口在后台时 `take_high_res_screenshot` 不落盘**（`bThrottleCPUWhenNotForeground`），而且后发的截图会顶掉还没渲染的那张 | 截图前跑 `tl_editor_no_throttle.py {"throttle": false}`，结束后 `{"throttle": true}`；一次只发一张，等文件出现再发下一张 |
| **97** | **City Sample Megaplants 的树在本项目只剩光秃枝干**：它们是 Nanite 装配体（树干 + `Instances/` 下的枝叶部件），叶子是 Nanite 体素植被，`r.Nanite.Foliage` 默认 0（City Sample 自己也关着）。只读 cvar，运行时改不了 | 写进 `Config/DefaultEngine.ini` `[ConsoleVariables]`（`r.Nanite.Foliage=1`），重启编辑器并重编 shader。部件材质被映射到根网格的槽位，换根网格的叶子槽即可换叶色（`pyworld_megaplant_summer.py`） |
| **98** | **Electric Dreams 的母材质（`M_MS_Default_Material_VT_DynamicLayering`、`M_MS_CustomDefault`、`M_Foliage`）一画就崩编辑器**：`MaterialShader.cpp:2567` "missing expected shader type FAnisotropyPS"，Substrate 混合 GBuffer（`ProjectGBufferFormat=0`）下旧材质转换节点连了 Anisotropy | `pyworld_fix_aniso.py`：断开 Substrate 转换节点的 Anisotropy 输入后存盘（拷进来的副本，ED 原工程不动） |
| **99** | **W7 那种 140 万个点交给 `Spawn_Assets`（GetClassFromAttribute）会让编辑器在生成中崩**（trap 61 同一个 GC 竞争） | 用原生 `PCGStaticMeshSpawnerSettings` + `PCGMeshSelectorByAttribute`；`MeshSelectorParameters` 要写完整（`TemplateDescriptor` 全字段 + `bUseAttributeMaterialOverrides` + `MaterialOverrideAttributes`），否则 build 报 diff；生成期间关自动保存、调大 `gc.TimeBetweenPurgingPendingKillObjects` |
| **100** | **Python 往材质里加表达式时，每次 `set_editor_property` 都触发整个材质重编**（贴图属性尤甚），几十个节点把编辑器推到 100 GB 后显存耗尽崩溃 | 表达式属性一律 `PropertyAccessChangeNotifyMode.NEVER`，全部连完再 `MaterialEditingLibrary.recompile_material` 一次（`pyworld_terrain_material.py`） |
| **101** | **本机常同时开两个 UE 编辑器**（PCG_Claude 和 PCG_Codex，各由一个 AI 驱动），`tasklist` 里都叫 `UnrealEditor.exe` | 杀进程前用 `Get-CimInstance Win32_Process` 看命令行含 `PCG_Claude.uproject`；崩溃报告进程看 `-MONITOR=<pid>`；Git Bash 里启动要 `MSYS_NO_PATHCONV=1`，否则 `/Game/...` 参数被改写 |

## 11. 2026-10-27 PyWorld 道路与水系形状（`docs/pyworld-guide.md` §7）

| # | 坑 | 规避 |
|---|---|---|
| **102** | **Single Layer Water 的散射 / 吸收系数单位是每厘米**（`MaterialExpressionSingleLayerWaterMaterialOutput.h`）：填 1–40 这种数，每 1 cm 水都不透明，水深完全看不出；**`Opacity` 不接时默认 1 = 不透明表面**，水面成了一面暗镜子，改系数毫无变化（换色只差 2/255） | 清澈偏绿的河水约 0.01–0.03 /cm 吸收、0.001 /cm 散射；`Opacity` 一定要接（0 = 体积水，只给泡沫处 1） |
| **103** | **PCG Spawn Dynamic Mesh 生成的 `DynamicMeshComponent` 不参与贴图流送**：材质里的流式法线贴图一直停在最低 mip（平的），水面看着是完美镜面，加大法线强度也没用（把法线当颜色输出是均匀灰） | 法线贴图拷一份到 `/Game` 并设 `never_stream`（`pyworld_water_material.py` 的 `T_PyWorldWaterNormal`） |
| **104** | **正在被网格用的材质删不掉**：`delete_asset` 报 "in use"（ForceDelete 失败），接着 `create_asset` 返回 None；改成就地重建后，**`delete_all_material_expressions` 不删 Single Layer Water 输出节点**，再建一个就编译失败 "only one Single Layer Water Material node"（引擎回退默认材质，画面是灰的） | 就地重建：`delete_all_material_expressions` 之后再逐个 `delete_material_expression` 直到为空 |
| **105** | **A\* 的启发式不能超过每厘米的最低代价**：代价乘了 < 1 的因子（偏好场 / 漂移噪声 / 复用折扣）而 `h_scale` 还是 1 时，启发式不可采纳，A\* 直冲终点——改噪声参数路径一点不变 | `h_scale` = 代价每厘米的下界（如 `exp(-Wander)`、`ReuseFactor`）；噪声要乘在整个代价上，加法项会被高度项淹没 |
| **106** | **动态网格三角形的朝向**：`append_buffers_to_mesh` 的三角形 (a, b, c) 只有在右手读 (b − a) × (c − a) 的 z < 0 时从上面看得见（单面）；反过来的绕序整张水面在编辑器里不可见 | 按 `geo.Mesh` 文档的绕序生成（`w03_river.surface`），测试里断言每个三角形的这个 z 为负 |

## 12. 2026-10-27 PyWorld 城镇模块化建筑（`docs/pyworld-guide.md` §8）

| # | 坑 | 规避 |
|---|---|---|
| **107** | **Megascans `Modular_Roof`（`Modular_Building_Roof_Kit_00`）的角块不是看名字或包围盒能判断的**：两个 600 × 600 的角块里 `_02` 是**天沟（valley）**，`_01` 才是**四坡顶的斜脊角**（经过枢轴的两条边都是檐口，脊端在 (−600, −600)）；直段的檐口在枢轴线 y = 0、屋脊在 y = −600。**俯视截图分不出正四坡顶和倒扣的"漏斗顶"**，按包围盒猜放了两次都是倒的 | 用 Geometry Script 读顶点量高度（`copy_mesh_from_static_mesh` → `get_vertex_position`，`pyworld_probe_roof_geometry.py`）；`_01` 放在屋顶矩形的角上、转 +90°，直段放在檐口上（`building._roof`） |
| **108** | **`MS_DefaultMaterial`（Megascans 默认母材质）的 `Albedo Tint` 单独设没用**：`Albedo Tint Intensity` 默认 0；而 `Roof_Kit_00` 的板岩反照率接近白色，中等色调（0.33）看起来还是浅灰 | 色调子材质同时设 `Albedo Tint Intensity = 1`（`pyworld_town_materials.py`）；屋顶色要压暗（板岩 0.16、陶土 (0.62, 0.22, 0.12)） |
| **109** | **Megascans `Modular_Building` 家族 01（`*_01` 砖房）的子网格 `_01.._04` 导入时丢了材质（`WorldGridMaterial`），而且它的窗没有玻璃槽**：直接放是灰格子墙、窗洞透光 | 这些模块的 0 号槽一律覆写成同套件的 `*_inst`（实测贴图对得上，`kit.py` 的 `fix`）；每栋楼窗后放一块室内遮挡体，材质用套件的 `M_Bldg_glass`（深色块看着像墙上开的洞） |
| **110** | **Megascans 模块化建筑的朝向约定**（实测）：模块沿本地 +X 从 0 到槽宽、立面朝 +Y、墙体在 −Y、外角的枢轴在墙角点、占当前边前 c 和上一条边后 c。**沿足迹逆时针摆，立面全朝里** | 足迹按**顺时针**遍历，每条边用边的朝向摆（左手法线即外侧）；家族 00 的角宽逐层不同（144 / 129 / 115 / 106 / 151），用端区 + 缩放壁柱填充，窗洞才能上下对齐 |
| **111** | **原生 Static Mesh Spawner 按属性覆写材质**：`bUseAttributeMaterialOverrides` + `MaterialOverrideAttributes = ["Mat0"]`，属性是 SoftObjectPath（或 String），按槽位顺序对应；空路径 = 该槽不覆写（用网格自己的材质）。每种 (网格, 材质) 组合一个 ISM | 一个属性只覆写 0 号槽，玻璃等其它槽保持原样；W6 的 3.2 万个模块 114 种网格 |
| **112** | **`Lattice.height` 是双线性插值，引擎的地形是沿 (i, j)–(i+1, j+1) 切开的三角面**（`Lattice.tri_height`，实测误差 0.04 cm）。在扭曲的格子上两者差到约 16 cm：按双线性高度贴地的街道石板，在一条横坡陡的商业街上整片被地面盖住（只在截图里看得出，按格点量是贴着的） | 凡是要**坐在可见地面上**的东西（街道石板）都用 `tri_height`，并把足迹里的地形顶点也算进去（三角面的峰值在顶点上，`Lattice.vertices_in`）；石板平面按 9 × 9 网格最小二乘拟合、按网格和顶点抬高（`w06.street_modules`）；验收按更密的网格量 |
| **113** | **City Sample 的 `SM_Plaza_Square_E`（石块路面）是一层带石块起伏的 4 cm 皮（z 15.8–20），不是平板**：Z 缩放连起伏一起拉长，石缝随之变深。×10（42 cm）时地面在石顶下 8 cm，石缝里露土，像真的石块路；×20（84 cm）、地面在石顶下 3 cm 时，整条街看着是土路、只露出石块顶 | 石块路面只拉到 ×10，地面留在石顶下 8 cm（`w06.SETTS_Z` `SETTS_TOP`）；要加厚只加厚平顶的板（人行道 `SM_Sidewalk_3_3_A` ×5）；改完要在街上平视截图看，俯视看不出 |

## 13. 2026-10-28 PyInterior（生活模拟室内，`docs/pyinterior-guide.md`）实测

| # | 坑 | 规避 |
|---|---|---|
| **114** | **Python 改样条不发属性变更通知，PCG 用缓存里的旧样条**：`set_spline_points` / `set_closed_loop` / `update_spline` 之后 `generate_local(True)`，`Get Spline Data (Self)` 拿到的还是旧外形（实测 13 × 9 m 的外形仍按 10.5 × 8 m 规划），不报错 | 改完样条 `pcg.FlushCache` 再生成（`pyinterior.py` 的 `_flush`）；或者像视口拖点那样发一次通知（trap 115），PCG 的追踪会清掉这栋房子 Self 键的缓存并自己重算 |
| **115** | **`set_editor_property` 默认的通知模式只在值真的变了时才通知**：把属性设回它自己（想"碰一下"让引擎刷新）什么都不发，`PostEditChangeProperty` 不来，PCG 无反应 | 用 `set_editor_property(name, value, unreal.PropertyAccessChangeNotifyMode.ALWAYS)`；实测对样条写 `spline_curves` 后，开着 Regenerate In Editor 的 PCG 组件按新外形自己重算（`pyinterior_live_probe.py`） |
| **116** | **视口拖样条点时 PCG 不会每帧重算**：样条可视化工具拖动中发 `EPropertyChangeType::Interactive`，PCG 的 actor 追踪器（`PCGActorTracker::OnObjectPropertyChanged`）直接忽略；松开鼠标（`TrackingStopped`）才发非交互通知，组件只刷新一次。组件自己的样条变化走"总是追踪"的 Self 键，Regenerate In Editor 关着时只登记不生成 | 实时编辑靠 Regenerate In Editor（`assign` 默认开）；拖完一次重算 0.02–0.2 s，不用节流 |
| **117** | **给关卡里已放好的 actor 加组件（这里是足迹样条），Python 里没有现成函数**：`AActor::AddComponentByClass` 标了 `ScriptNoExport` + `BlueprintInternalUseOnly`（`Actor.h`，Python 生成器跳过这类函数），蓝图的 Add Component 节点是它的包装 | 走编辑器的子对象系统（Details 面板的 Add 也是它），得到能存盘的实例组件：`SubobjectDataSubsystem.k2_gather_subobject_data_for_instance(actor)` → `add_new_subobject(AddNewSubobjectParams(parent_handle=handles[0], new_class=unreal.SplineComponent, blueprint_context=None))` → `SubobjectDataBlueprintFunctionLibrary.get_object(get_data(handle))`（`pyinterior.py` `_add_spline`） |
| **118** | **Geometry Script 读顶点的两个名字**：列表工具类是 `unreal.GeometryScript_List`（没有 `GeometryScript_ListUtils`）；`GeometryScript_MeshQueries.get_all_vertex_positions(mesh, skip_gaps)` 返回元组（网格, `GeometryScriptVectorList`, 有无空洞），取 `[0]` 拿到的是网格，传给 `convert_vector_list_to_array` 报 "Cannot nativize 'DynamicMesh' as 'VectorList'" | 按类型从元组里挑 `GeometryScriptVectorList`（`pyinterior_probe_meshes.py`）；判断网格朝向就看高处顶点的重心偏向哪边（靠背） |
| **119** | **StarterContent 道具的真实身份和朝向**（实测）：`SM_Chair` 是休闲椅（82 × 81 × 115，和 `SM_Couch` 同材质 `M_Chair`），不是餐椅；`SM_Shelf` 是 2 m 长、挂墙的一块隔板，枢轴在顶边后沿（z −25.3..0）；`SM_Couch` / `SM_Chair` 正面朝 +X（靠背在 −X）；`SM_Lamp_Wall` 的墙板在 x = 0 | 按名字猜会放错家具、放反方向；用 trap 118 的办法量，写进目录（`catalog.REAL`），旋转按"正面转到 +y"记 |
| **120** | **一次调用里生成多个组件后，下一次调用马上读会读到一部分旧结果**：8 栋房子 `generate_local` 后紧接着 `read`，4 栋还是上一次的实例数（生成是异步的、逐个排队，Python 节点跑完后 spawner 还要几帧） | 读之前看日志里最后一栋的 Python 节点那行已经出来，再隔一次调用读；或者核对实例数等于 Summary 里的零件数 |
| **121** | **降墙（`WallCut`）只降墙块不够**：门框、窗框、窗顶过梁、吊柜和镜子还停在原高度，悬在降低的墙上面，俯视一片浮空的框 | 墙上的东西（门、窗）一律剪到降墙高度，整个在降墙高度以上的挂墙件不出（`assemble.WALL_HUNG`、`_Out(top)`） |
| **122** | **`pypcg.world.grammar.solve` 找不到合格解时照样返回"最接近的"解**（`ok = False`，`symbols` 非空）：厨房台面 `[K][C]*[S]` 铺在比电器长 10–20 cm 的墙上时，`C` 的缩放只有 0.17（下限 0.5），结果照用，出了 10 cm 宽的台面和同宽的吊柜（50 cm 普查里 2.7 % 的房子），不报错 | 调用方要么看 `res["ok"]`，要么传 `slack=True` 把塞不满的零头留成空（`furnish._try_runs`；PyWorld 的 `bdf.py` 一直用 slack）；窄模块用 `Tools/pyinterior/census.py` 普查 |
| **123** | **桥接脚本里删掉一批 actor 后紧接着 `load_level` 重开当前关卡，编辑器崩溃**：`Assertion failed: !LevelList.Contains(TickTaskLevel)`（`TickTaskManager.cpp:1992`，`ULevel::~ULevel` ← `EditorDestroyWorld` ← `Map_Load` ← `LevelEditorSubsystem.LoadLevel`）。脚本跑在游戏线程的 tick 里，旧关卡销毁时它的 tick 任务还挂在列表上。同样的 `load_level` 在没有删 actor 的调用里成功过，不可靠 | 预览 / 探针脚本不重开关卡：删完临时 actor 后不存盘，关编辑器或切关卡时选不保存（`pyinterior_steps.py`）；确需重开时单独一次调用、前面不删任何东西。崩溃后照 trap 78 先挪走 `Saved/Autosaves` 再重启 |

## 14. 2026-10-29 PyInterior 多层（`docs/pyinterior-guide.md` §8）实测

| # | 坑 | 规避 |
|---|---|---|
| **124** | **重建图（`pyinterior.py build`、任何 `build_slim`）会清掉房子组件上的图参数覆写**：示范街的 `WallCut` 110（House_04 是 0）回到 0，单层房的实例数从 143 / 237 / 355 … 跳到 182 / 296 / 425 …，看着像"单层输出变了"，其实是降墙没了（离线：同一房子 `WallCut` 110 → 143，0 → 182） | `build` 之后一定 `assign`（现在 `assign` 会把示范街的降墙和多层房的 `Floors` / `StairType` / `ShowFloors` / `WallCut` 一起放回去）；比较实例数之前先确认两边的覆写一样 |
| **125** | **一栋房子的楼层来自它所有样条组件的高度**：`Get Spline Data (Self)` 把 actor 上**每一条** SplineComponent 都交给 Python 节点，阶段按样条点的平均高度归层（层高 = WallHeight + 30）。所以在 Details 面板里给房子加一条样条、整体抬高 300 cm，它就是新的一层；带通知的编辑后房子**自己重算**（实测：House_11 加一条抬到 600 cm 的样条 → 自动变三层 26 间）。反过来，误加的样条也会被当成一层 | 加层 = 加样条 + 抬高；不想要的样条要删掉组件，不能只挪开（挪到别的高度就成了别的楼层）。脚本改样条照 trap 114–115 用 `ALWAYS` 通知或先 `pcg.FlushCache` |
| **126** | **给打分函数加缓存时，浮点加法的顺序也要一模一样**：`floorplan` 给"每间房的得分"做缓存、再把每间的总分相加，和原来逐项 `s += …` 的结果差在最后几位，接近平局的两个布局换了赢家，多层房的布局摘要变了（单层没走这条路所以没发现） | 只缓存每一项（尺寸检查、长宽比项），按原来的顺序逐项加（`floorplan._Memo`）；用一个测试逐位比较缓存版和原函数（`test_floor_memo_matches_the_layout_checks`，打乱加法顺序它就失败） |
| **127** | **`[a.get_actor_label() for a in actors if destroy_actor(a)]` 得到一串空字符串**：条件先执行，actor 已经被删，再读标签只剩 `""` | 先把标签读出来，再删（`pyinterior.py houses`） |

## 15. 2026-11-02 MeshTerrain 在运行时（PIE / Simulate / 打包）

> 编辑器里画地形的是 editor-only 的 `APreviewSection`（`FMegaMeshCustomPreviewSceneProxy`，不是 Nanite）；运行时只有 compiled section（`ACompiledSection`，由 MeshPartition 定义的构建变体里的 transformer 管线生成）。下面四条都在关卡的模板副本上实测，原关卡没动。检查脚本 `meshterrain_runtime.py`（`copy` / `load` / `inspect` / `pie` / `shot`）。

| # | 坑 | 规避 |
|---|---|---|
| **128** | **PyWorld 的 MeshTerrain 在运行时是空的：定义 `MPD_PyWorld`（`MPD_Basic` 的副本）没有 compiled-section 构建变体。** `CompiledSectionBuildVariants` 为空时，`GetCompiledSectionBuildVariants()` 回退到类默认对象的唯一变体 `Default`，它的 `TransformerPipeline` 为空。于是不跑 Static Mesh Transformer，每个 `ACompiledSection` 只剩构造函数里那个空的、隐藏的 `FarFieldMeshComponent`。`WorldPartitionMeshPartitionBuilder` 照样报 `Built 2 … Failed 0`，也照样存盘：WP builder 存盘不打 `Saving Package`，要看 `__ExternalActors__` 的文件时间。PIE 现建的占位 section 同样是空的。2026-10-30 天气探针看到的就是这个现象。实测 2026-11-02，L_PyWorld 副本：Simulate 里只有海面；给定义配上变体后，同一副本的 W1 地形和碰撞都有了。City Sample 的 `MPD_CitySamplePCG_Demo` 自带 `Default` 变体（`TP_DefaultPreviewSection`，非 Nanite，BlockAll），所以 `L_PyTown`、`L_PyCitySmall` 的副本在 PIE 里本来就有地形。`L_PyCity` 存的是未生成的状态：z = −600 的平面压在 −500 的水面下，PIE 和编辑器里一样看不见 | 定义里要有带管线的变体。`pyworld_terrain_material.py {"mpd_only": true}` 把引擎 `/MeshPartition/DataAssets/MPD_Default` 默认平台选用的两个变体抄进 `MPD_PyWorld`：`Common_GameplayData` 是 `CollisionTransformer`；`HighEndPlatform_RenderData` 是 `StaticMeshTransformer`，Nanite、无碰撞、带裙边。它的 `PerPlatformRuntimeSettings` 也一起抄（完整重建材质时同样会抄）。核对用 `meshterrain_runtime.py inspect {"world": "pie"}`：每个 `HighEndPlatform_RenderData` section 应有一个 Nanite 网格，`Common_GameplayData` section 应有 `MeshPartitionCollisionComponent`，PIE 里向下打射线会命中它。直接用 `MPD_Basic` 的关卡，运行时同样是空的：`pyworld.py layout` 在 `MPD_PyWorld` 不存在时就会回退到 `MPD_Basic` |
| **129** | **`new_level_from_template` 刚复制出的关卡直接进 PIE，常驻（非空间加载）actor 一个也进不了 PIE 世界。** MeshPartition、9 个 PCG volume、相机、PlayerStart 全都没有，PIE 世界只有 30 个 actor。占位 section 报 `Failed to build compiled section: could not find parent MeshPartition actor`。`wp.Editor.DumpStreamingGenerationLog` 显示 `Always loaded Actor Count: 0`，cell 里的 actor 路径还是 `/Temp/Untitled_N`：内存里的世界仍是按模板加载出来的临时包，PIE 按存盘路径找常驻 actor，找不到。存盘之后不重开也一样。用 `load_level` 重开后计数变成 36，PIE 正常。实测 2026-11-02，L_PyWorld 副本 | 复制后先用 `load_level` 重开，再进 PIE（`meshterrain_runtime.py copy` → `load`）。切关卡加 `{"defer": true}`，在 Slate post-tick 里切。本次切了 16 次关卡（12 次 defer，其中包括从 54 万实例的 L_PyTown 副本切走），没有一次触发 trap 79 / 83 的断言。不过大关卡上这次调用可能丢回复（"connection closed mid-call"），结果去看 `Saved/Reports/meshterrain_runtime_load.json` |
| **130** | **PIE 现建的占位 compiled section，地表通道是错的；高度和碰撞都对。** W9 写的 6 个通道，在 builder 存过盘的 section 上和编辑器一致：谷底是草，陡坡是岩。在 PIE 现建的占位 section 上像是错了位：谷底是灰褐色，陡坡上反倒是草色斑块（`docs/img/pyworld/runtime_simulate_placeholder.jpg` 对照 `runtime_simulate_built.jpg`）。原因没查到。占位 section 走 `FSeparateWorldBuilder::BuildCompiledSectionMesh`，存盘的 section 走 commandlet 的 `BuildMegaMeshCompiledSectionTextures`，插件还是 Experimental | 看材质、截图、验收之前，先 build compiled section（trap 131）。`LogMegaMeshEditor` 调到 Verbose 后，PIE 日志里出现 `Created 0 placeholders` 和 `REUSING UpToDate`，就说明用的是存盘的 section。地形一改（任何写地形的阶段重跑）section 就过期，PIE 会剥掉过期的、换成占位（`MeshPartition.PIE.StripOutOfDateSections`），所以要再 build 一次 |
| **131** | **compiled section 要在编辑器外构建、存盘。** Build 菜单里的 "Build Mesh Partition"（`ByPackageHash`，只重建依赖变了的）和 "(force rebuild)" 依次做这几步：提示存脏包，切到空白地图，起一个 `UnrealEditor.exe "<uproject>" -run=WorldPartitionBuilderCommandlet <map> -AllowCommandletRendering -Builder=WorldPartitionMeshPartitionBuilder -ReuseMode=… -SCCProvider=<当前>`，完成后重新打开关卡。命令行照抄这一条就行，`-SCCProvider=None` 没问题。L_PyWorld 副本（W1 + W9）实测 40–60 s，产出 4 个 section（2 个变体 × 2 组 base，一组 62 个、一组 2 个）。大的渲染 section 9.7 MB、碰撞 section 5.7 MB，另有 `MeshPartitionDataLayerContainer`，每个变体一个 data layer，cook 时按平台剥离。同时会删掉从 City Sample demo 一路继承下来的旧 section `305C41`（定义 `/Aspen/…/MPD_MedievalVillage`，没有网格）。PIE 本身不需要先 build：`MeshPartition.PIE.CreateMissingSections` 默认开，会按存盘的修改器现建，L_PyWorld 约 10 s，但材质有 trap 130 的问题 | 编辑器开着同一关卡时不要跑命令行：Build 菜单会自己切走；用脚本的话，先 `load` 到别的关卡。修改器有没存盘的改动时，PIE 会弹模态框并且不反映这些改动（`meshterrain_runtime.py pie` 遇到脏包会拒绝），所以先存盘，再 build 或进 PIE。section 属于生成结果，仓库里的 L_PyWorld 不带生成结果，section 也只在本地 build |

## 16. 2026-11-11 City Sample 静态天气预设（`cs_weather.py`，报告 `docs/citysample-weather-presets.html`）

| # | 坑 | 规避 |
|---|---|---|
| **132** | **在 Slate post-tick 回调里存资产，回调会被自己重入，编辑器内存耗尽崩溃。** `save_asset` 打开 slow-task 对话框，对话框里 `FSlateApplication::Tick()` 又广播 `PostTickEvent`，同一个回调在第一次存盘还没返回时再跑一遍。批量拍摄的回调在一帧里连套三层"应用预设 → 存材质实例"，进程私有内存到 90 GB，系统提交量耗尽（143/145 GB），`D3D12 CreateCommittedResource E_OUTOFMEMORY` 崩溃（2026-11-11 05:15 UTC，PID 47856）；显存只用了 8.9/15.2 GB，不是显存问题 | 回调都包一层防重入（`cs_wx_lib.guarded`，`busy` 标志放在 try/finally 里）；回调里不存资产（`phase_apply {"save_mi": false}`，批量结束后在一次普通的桥调用里存，`cs_weather_save_mis.py`）；批量每做完一个预设记一次进程内存，超过 `max_commit_gb` 就自己停（`cs_wx_lib.process_memory_gb`） |
| **133** | **编辑器窗口不在前台时，排队的 HighResShot 一张也拍不出来，等到超时。** 编辑器偏好「Use Less CPU when in Background」（`bThrottleCPUWhenNotForeground`，默认开）在 `!FApp::HasFocus()` 时给每个视口加 realtime override 关掉实时渲染（`EditorEngine.cpp` 1807），视口不出帧，截图请求永远等不到下一帧。同一个批次里有的天气拍出来、有的超时：取决于拍的时候窗口有没有焦点 | 拍摄期间在内存里关掉它：`perf_cdo().set_editor_property("bThrottleCPUWhenNotForeground", False, NEVER)`。这个类没有 Python 包装，要用 C++ 原名（同 trap 85 的 `bAutoSaveEnable`）；`restore` 时再按快照开回来。快照记的是**第一次被管理时**的值，不是引擎默认值 |
| **134** | **`restore` 把值全改回去之后，demo 关卡的外部 actor 包仍然是脏的；一打开 autosave，编辑器就把它们写进 `Saved/Autosaves/`**，之后一旦崩溃再点"恢复"，就是 trap 78。值相同不代表包不脏：`modify()` 和 `set_editor_property` 都会置脏 | `restore` 在打开 autosave 之前先清脏：`cs_weather_reload_clean.py` 逐项核对每个受管属性与快照一致后，对这些 actor 调 `EditorAssetSubsystem.set_dirty_flag(actor, False)`（外部 actor 自己就是它那个包的资产，`IsAsset()` 为真；`reload_packages` 对外部 actor 包不可靠）。收尾时核对 `get_dirty_content_packages()` 为空、`Saved/Autosaves/` 里没有 demo 的包 |
| **135** | **`git checkout <file>` 对未跟踪的文件是空操作，`;` 之后的改写照样执行。** 本想先把改坏的 `cs_weather_presets.py` 还原再改，但文件从没提交过：`git checkout` 报 pathspec 错，后面的脚本又在坏文件上 `import` 失败，源码只剩编辑器里上一次编译成功的模块 | 改未提交的数据文件前先备份（`Saved/Reports/cs_weather2/backup/`）。真坏了：从编辑器里活着的模块 dump 出数据（`_dump_mem_presets.py`），再用会话记录里的读取 + 编辑逐段重建源码，两头核对（逐行对上重读的片段、语义上等于活模块）后才写回 |

## 17. 2026-11-12 City Sample 体积云艺术天气（`cs_weather_art.py`，报告 `docs/citysample-cloud-art.html`）

| # | 坑 | 规避 |
|---|---|---|
| **136** | **demo 关卡开着时重建云材质（`cs_sky_assets.py {"phase": "material"}`，`MaterialEditingLibrary.recompile_material`），编辑器私有内存 25 秒内从 23 GB 涨到 98 GB（本机 127 GB 内存、10 GB 页面文件），约 45 秒后回落到 53 GB；两次桥接调用都返回 `Unreal editor connection closed mid-call`，可推迟的任务其实做完了、结果写进了 `assets_result.json`。** `recompile_material` 用默认选项的 `FMaterialUpdateContext`（`MaterialShared.h` 3525：`RecreateRenderStates`），会对世界里每个组件重建渲染状态，demo 关卡的组件数极大，这很可能就是峰值的来源 | 重建前确认没有别的编辑器、batch、构建在跑，留出约 80 GB 空闲；看到 "connection closed" 不要重跑（再来一次峰值翻倍），轮询 `Saved/Reports/cs_weather/assets_result.json` 的 `state`。要量内存就在后台跑 `Saved/Reports/cs_weather2/memsample.ps1 -ProcId <pid>` |
| **137** | **雷暴的云砧下表面、乳状云和弧状云底部发亮、发紫、没有体积感：体积云的天光不会被上方的云体遮挡。** `VolumetricCloud.usf` 945–953：天光 = 该高度的一个远处天光颜色 × 材质的 AO 输出（AO 引脚接了线时，`MATERIAL_VOLUMETRIC_ADVANCED_OVERRIDE_AMBIENT_OCCLUSION`），否则 × 一个按层内高度的渐变（`SkyLightCloudBottomVisibility`）。几公里厚的积雨云下面照样拿到整片天空的光 | 厚的部分在材质里自己压 AO：风暴单体（云顶 15% 以下）、乳状云和弧状云下部乘 `StormAO`（雷暴 0.25、弧状云 0.06）。默认 1 不改变其它天气 |
| **138** | **天空球用网格 UV 采样星图，星星是一个个拉长的方块。** `T_WeatherStars` 2048×1024 铺满整个球面，一个像素 ≈0.18°；84° 视野、1920 px 宽的镜头一个屏幕像素 ≈0.044°，一颗星被双线性放大成 4×4 像素的方块，暗的背景也一起放大成雾斑 | 在天空材质里按视线方向采样：`d = -CameraVectorWS`，`u = atan2(d.y, d.x)/2π + 0.5`，`v = acos(d.z)/π`，`Texture2DSampleLevel(..., 0)`，再把像素值取 `StarSharp` 次方（4）——星星成为点，暗背景消失（`M_CS_NightSky`，`cs_sky_assets.py nightsky`）。SeasonalWeather 的 `M_WeatherStars` 也是按网格 UV 采样同一张图，同样的放大比例下会是同样的方块（没有在渲染里核对过） |

## 18. 2026-11-13 City Sample 云的时间演变与过渡（`cs_cloud_director.py`，报告 `docs/citysample-cloud-motion.html`）

| # | 坑 | 规避 |
|---|---|---|
| **139** | **`unreal.KismetMaterialLibrary` 不存在：`create_dynamic_material_instance` 在 `unreal.MaterialLibrary` 上。** UE 的 Python 绑定去掉了 Kismet 前缀（和 `unreal.SystemLibrary` 一样），签名 `(world_context_object, parent, optional_name, creation_flags)`；MID 挂在传进去的对象下面（传云组件时路径是 `...VolumetricCloudComponent.MID_M_CS_CumulusCloud_N`） | 写调用前先内省（`dir(unreal)` 里找含 `Material` 和 `Library` 的类）；用 `unreal.MaterialLibrary.create_dynamic_material_instance` |
| **140** | **同一个静态天气渲两次，差别可以差一倍：只用两对相位对齐的图量出的噪声底太严。** 同一材质、同一会话的两张 HighResShot，`art_rays` 差 5.0 / 16.2（mean / p999），`art_storm` 一对差 1.2、另一对差 2.6；区域平均一致到 0.01，高频能量相同，差的是时域抖动的相位和会话状态（体积雾、Lumen、云影的历史），64 px 块平均后仍差 1.5–7 | 判断"材质改没改"用同一会话的参照图，并再渲一张同材质的图量这个预设自己的方差；64 px 块平均对参数错误灵敏、对相位噪声不灵敏（`Tools/cs_weather/stills_check.py`，阈值 10） |
| **141** | **体积云材质的保守密度（ConservativeDensity）每个步进采样都要算，空的地方也算。** `UpdateMaterialCloudParam`（`VolumetricCloudMaterialPixelCommon.ush` 65–67）对每个采样调用 `GetVolumetricAdvancedMaterialOutput6`；DXC 把这条路径裁剪到 Cons 用到的部分，所以 Cons 依赖的每次纹理采样都落在每个样本上，云影图大部分是空样本 | Cons 只读不需要额外采样的量；演变项用上界 `covC = cov × (1 + 2·EvoAmt)`（经过同样的单调步骤），它的两次采样就只在 Cons > 0 的地方执行（`cs_cloud_code.py`） |
| **142** | **抓帧之间切换参数做 GPU A/B 不可信：参数一变，云影图有一段变贵的过渡。** 每次抓帧前把 `EvoAmt` 切到 A 或 B，一次得到 +42 %，再测一次变成 −33 %。固定参数的块很稳（±5 %），但块与块之间会漂（有的块与参数无关地贵：`EvoAmt` 0.05 比 0.6 贵 30 %） | 每个条件单独一段，先稳定 240+ tick，抓 3–4 帧取中位数；先把视口对准云（重启后视口看不到云，主 pass 只有 0.01 ms：`UnrealEditorSubsystem.set_level_viewport_camera_info`）；只比较同一会话、同样条件下的数 |
| **143** | **`cs_weather._night_sky(cfg)` 会把星空参数写进存盘的 `MI_CS_NightSky`。** 导演第一次生成星空球时用渐变中的 StarIntensity 调它，材质实例被弄脏（内存里是 5e-5），`restore` 之后仍是脏的 | `_night_sky(cfg, write_mi=False)`：导演用自己的 MID 驱动星星；已经弄脏的写回 2.0 / 4.0 再保存 |
| **144** | **部分未提交的 `cs_*` 文件（`cs_weather.py`、`cs_sky_assets.py`、`cs_weather_art.py`）是 CRLF 行尾；用 Python `newline="\n"` 写回会改掉整个文件的行尾，diff 全文都是改动。** | 改这些文件时先按字节判断有没有 `\r\n`，写回时保持（`open(..., "w", newline="\r\n")`） |
| **145** | **每次 `play`（静态应用 + 保存材质实例 + 换 MID）之后的头几秒，编辑器很卡：7 s 里 Slate tick 只跑了 20–100 次，导演的模拟时钟只走了 28–105 s（30 倍时应约 210 s）；这段时间的 GPU 读数也偏高（浓积云塔 31.5 ms，稳定后 22–23 ms）。** | 测量、截图前等 10 s 以上；录制逐帧冻结时钟，不受影响 |
| **146** | **City Sample 的水面在相机离水面约 19–20 m 以下时是暗的，以上时反射天空：相机上下穿过这个高度时，整片水面在一帧里跳变。** 静态对比（同一视角，z −500 vs −400 cm）：画面下三分之一差 18.5，天空只差 0.9。从 14 m 的水边机位移到高处机位的过渡片段因此在某一帧闪一下（第一次录的 mackerel→cloudsea 第 53 帧，towers→storm 第 80 帧） | 需要上下移动镜头的片段，低处机位放在 21 m（`CS_ART_WideHi` / `CS_ART_TowersHi`），整段不穿过这个高度；`test_transition_cameras_do_not_cross_the_water_switch` 锁住 |
| **147** | **过渡开始时把云组件一下子设成并集、结束时一下子设回目标的值，就是一帧跳变：云层高度、采样倍数、追踪距离一变，同一片云的离散化就变了。** 每段过渡的第一帧都跳一下（towers→storm 第 30 帧变化 5.1，前后 2.6–2.9；改后 2.6，与前后一样） | 云组件连续变化：目标的云开始生成之前从原值渐变到并集，原来的云完全消散之后再渐变到目标值（`cs_cloud_motion.vc_at`，`LAYER_RAMP` 0.1）；并集的采样倍数取保持两种云各自步长的值（有上限） |
| **148** | **按整段中位数判断跳变，会把明暗差别大的片段（白天→黄昏）里亮的那一半的正常运动当成跳变。** 暗的后半段把中位数拉低，前半段云影扫过水面的帧都超过 3 倍 | 除了超过整段中位数的 3 倍，还要求比前后各 8 帧的中位数高 1.75 倍（实测最小的真跳变是邻域的 2.07 倍，正常运动的峰值约 1.5 倍）；用录下来的曲线做测试（`Tools/cs_weather/tests/data/`） |
| **149** | **没有体积覆盖时，局部曝光的高光/暗部对比默认是项目设置里的 0.8，不是 `PostProcessSettings()` 结构体默认值 1.0。** `FSceneView::StartFinalPostprocessSettings`（`SceneView.cpp` 2081–2089）在任何体积之前就用 `r.DefaultFeature.LocalExposure.HighlightContrastScale` / `ShadowContrastScale` 设好起点（`r.LocalExposure` 关闭时为 1.0，2180）。导演把只有一端设置的参数朝结构体默认值插值，过渡结束、关掉覆盖时就跳一下（mackerel→cloudsea 最后一帧亮度掉 5%） | “不覆盖时的值” = 结构体默认值 + 这些控制台变量 + 关卡里其它无界体积按优先级混合（`cs_cloud_motion.underlying_ppv`，编辑器侧 `cs_cloud_rt.read_ppv_defaults`） |
| **150** | **两个机位之间直线插值，镜头会穿过城市：** 从 4.5 km 外 250 m 高的机位到水边 21 m 的机位，直线在 70–130 m 高度从市中心的楼之间穿过，有一帧整面墙挡在镜头前 | 水平移动超过 300 m 时走“升—平移—降”：先升到 max(两端高度, 600 m)，在这个高度上平移，再降到终点（最高的楼顶 438 m）；`test_moving_cameras_cross_the_city_above_the_roofs` 锁住 |
| **151** | **想把一段 40–60 s 的过渡冻结在中点测 GPU，经桥接发 `pause` 到达时过渡已经结束：两次都抓到的是结束后的雷暴。** 读状态、判断、再发下一次桥接调用之间的延迟可以超过一分钟；刚重启的编辑器上，第一次 `record`（调用里要先应用预设）还返回过 "connection closed mid-call"，其实录制已经正常开始 | 要在某个进度上停住，就在编辑器里挂一个 tick 回调，到进度时设 `paused`（`_cs_pause_at.py` 这类一次性脚本）；"connection closed" 不重发，读状态文件（trap 136） |
