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
