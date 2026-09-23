# PCG 节点类名表（Python 建图用）

> **本文件是写 `add_node_of_type` 时的事实来源。** 全部来自 UE 5.8 源码核对。
> 从编辑器里看到的**节点标题**猜类名**会失败**——见文末陷阱表。

---

## 0. 三条必须先知道的规则

### 0.1 加载路径 = `/Script/<模块>.<类名去掉 U 前缀>`

```python
cls = unreal.load_class(None, "/Script/PCG.PCGSurfaceSamplerSettings")
node, settings = graph.add_node_of_type(cls)
```

**绝大多数节点在 `PCG` 模块**。少数在别处（见 §3），那类需要对应插件已启用，
否则 `load_class` 返回 `None`。

### 0.2 抽象类不能实例化

`UPCGSettings` 及所有标 `Abstract` 的子类**不能** `new_object`，也不能作为
`add_node_of_type` 的目标。抽象类清单：

`UPCGSettings`、`UPCGSettingsWithDynamicInputs`、`UPCGBaseSubgraphSettings`、
`UPCGControlFlowSettings`、`UPCGPlatformSwitchSettingsBase`、`UPCGMetadataSettingsBase`、
`UPCGFilterDataBaseSettings`、`UPCGExternalDataSettings`、`UPCGSubdivisionBaseSettings`、
`UPCGDataAttributesAndTagsSettingsBase`。

### 0.3 `UPCGGraph` 的建节点入口

```cpp
UPCGNode* AddNodeOfType(TSubclassOf<UPCGSettings> InSettingsClass,
                        UPCGSettings*& DefaultNodeSettings);   // meta DynamicOutputParam
UPCGNode* AddNodeInstance(UPCGSettings* InSettings);
UPCGNode* AddNodeCopy(const UPCGSettings*, UPCGSettings*& OutSettings);
```

`AddNodeOfType` 是主入口：传类，**同时拿回 node 与新建的 settings 对象**。
（`UPCGGraph::AddNode(UPCGSettingsInterface*)` **不是** `UFUNCTION`，Python 不可达。）

**已实测确认（2026-09-23，PCG_Claude）**：`add_node_of_type` 返回 **2 元组**
`(node, settings)`：

```python
node, settings = graph.add_node_of_type(
    unreal.load_class(None, "/Script/PCG.PCGCreatePointsGridSettings"))
```

它的 docstring 原文就是
`x.add_node_of_type(settings_class) -> (PCGNode, default_node_settings=PCGSettings)`。
`settings` 是**新建的** settings 实例，直接拿来设参数即可
（挂在 node 的子对象上，路径形如 `...:NodeName_0.PCGCreatePointsGridSettings_0`）。

**`add_edge` 的签名与返回值**（同样实测）：

```python
graph.add_edge(from_node, "Out", to_node, "PinLabel")   # -> 返回 To 节点
```

注意它返回的是 **To 节点**，不是布尔——**不能用返回值判断连线是否成功**，见 §0.4。

---

## 0.4 **最重要的一条**：`add_edge` 会静默失败，且返回值为真

实测（2026-09-23，PCG_Claude）：

```
把 CreatePointsGrid 的 "Out" 连到 SurfaceSampler 的 "In"
  → add_edge 返回了 SurfaceSampler 节点（真值）
  → 但 get_all_edges() 前后都是 1，edge_created = false
```

**原因有两点，都很隐蔽**：

1. **pin 标签猜错。** `SurfaceSampler` 的数据输入 pin **不叫 `"In"`**，
   而叫 **`"Surface"`**。传入不存在的标签**不报错**，只是不建边。
2. **类型不兼容。** 即便标签对，把 points 接到只吃 surface 的 pin 上，
   同样**静默不建边**。

**所以连接后必须验证，不能凭返回值**：

```python
before = len(graph.get_all_edges())
graph.add_edge(a, "Out", b, "Surface")
assert len(graph.get_all_edges()) > before, "edge silently failed"
```

更细的检查是 `pin.is_connected`（`PCGPin` 暴露了 `is_connected` 与 `edges`）。

### 如何拿到真实的 pin 标签

**不要猜。** `PCGNode` 暴露 `input_pins` / `output_pins`，
每个是 `PCGPin`；标签在 `pin.get_editor_property("properties")` 的 `label` 字段里：

```python
def pin_labels(node, which):
    pins = node.get_editor_property(which)          # "input_pins" / "output_pins"
    out = []
    for p in pins:
        try:
            out.append(str(p.get_editor_property("properties").get_editor_property("label")))
        except Exception:
            out.append(None)
    return out
```

**实测样例**（同一批节点）：

| 节点 | 输入 pin 标签 |
|---|---|
| `CreatePointsGrid` | `Execution Dependency`, `Overrides`, `GridExtents`, `CellSize`, `PointSteepness`, `CoordinateSpace`, `bSetPointsBounds`, `bCullPointsOutsideVolume`, `PointPosition` |
| `SurfaceSampler` | **`Surface`**, `Bounding Shape`, `Execution Dependency`, `Overrides`, `PointsPerSquaredMeter`, `PointExtents`, `Looseness`, `bUnbounded`, `bApplyDensityToPoints`, `PointSteepness`, `bKeepZeroDensityPoints`, `Seed` |
| `BoundsModifier` | **`In`**, `Execution Dependency`, `Overrides`, `Mode`, `BoundsMin`, `BoundsMax`, `bAffectSteepness`, `Steepness` |

**输出 pin 一律叫 `"Out"`**（本批三个节点都是）。

**规律**：标签就是**节点上那个参数/属性的显示名**；
凡是「吃数据」的输入，标签往往是**它的语义名**（`Surface`、`Bounding Shape`）
而不是通用的 `In`。**每个节点都不一样，必须逐个读。**

---

## 0.5 设置节点参数：属性名与类型的实测约定

**三个反复踩到的坑，全部实测（2026-09-23）**：

### (a) 布尔属性去掉开头的 `b`

C++ 里叫 `bSetPointsBounds`，Python 侧要写 **`set_points_bounds`**：

```python
gset.set_editor_property("set_points_bounds", True)      # OK
gset.set_editor_property("b_set_points_bounds", True)    # Exception: Failed to find property
```

同理 `bCullPointsOutsideVolume` → **`cull_points_outside_volume`**。

### (b) `Vector` 类型的属性必须传 `unreal.Vector`，不是 float

`CreatePointsGrid` 的 `CellSize` 与 `GridExtents` 都是**结构体 `Vector`**，
不是浮点数、不是 `Vector2D`：

```python
gset.set_editor_property("cell_size",   unreal.Vector(100.0, 100.0, 100.0))   # OK
gset.set_editor_property("grid_extents", unreal.Vector(2000.0, 2000.0, 100.0)) # OK
```

传 `500.0` 或 `unreal.Vector2D(...)` 会报
`Failed to convert type ... (StructProperty)` / `NativizeStructInstance`。

### (c) 枚举属性必须传枚举值，不是数字或向量

`PointPosition` 是枚举 `PCGPointPosition`（默认 `CELL_CENTER`），
`CoordinateSpace` 是 `PCGCoordinateSpace`（默认 `WORLD`）：

```python
gset.set_editor_property("point_position", unreal.PCGPointPosition.CELL_CENTER)
```

传 `unreal.Vector(...)` 会报 `Cannot nativize 'Vector' as 'PointPosition'`。

### (d) 拿不准就读回来

写完立刻 `get_editor_property` 验证，别假设写进去了：

```python
gset.set_editor_property("cell_size", unreal.Vector(100, 100, 100))
assert gset.get_editor_property("cell_size").x == 100.0
```

**属性的 Python 名可以从 `dir(settings)` 里读出来**——
实例的 `dir()` 会列出全部可访问的编辑器属性名，比猜快得多。

---

## 0.6 生成是**异步**的：读结果必须另发一次调用

**这是本项目实测最重要的一条操作事实**（2026-09-23）：

```
同一次 run_unreal_script 内：
  comp.generate_local(True)          -> 返回 OK
  coll = comp.get_generated_graph_output()
  len(coll.tagged_data)              -> 0        <-- 空的！

下一次 run_unreal_script：
  len(coll.tagged_data)              -> 1        <-- 数据在了
```

**写数据用一次调用，读数据必须用下一次调用。**
把 `generate_local` 和 `get_generated_graph_output` 写在同一个脚本里，
几乎必然读到空集合——而这**不会报错**，只会让你误判"图没产出"。

**正确姿势是两段式**：

| 阶段 | 脚本 | 职责 |
|---|---|---|
| A | `pcg_xxx_setup.py` | 建图 / 设参 / 挂组件 / `generate_local(True)`，**然后结束** |
| B | `pcg_xxx_read.py` | **重新查关卡里的 Actor**，读 `get_generated_graph_output()`，验证点数，最后清理 |

阶段 B 要**重新按类查 Actor**，不能指望阶段 A 的 Python 变量——
两次调用是两个独立的解释器上下文，**变量不跨调用存活**。
`unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()`
配合 `actor.get_class().get_name() == "PCGVolume"` 是最稳的重新定位方式。

---

## 1. 建城常用节点的类名（直接查表用）

全部是 `/Script/PCG.<类名>`。

| 节点标题（编辑器里看到的） | 类名 |
|---|---|
| Create Points Grid | `UPCGCreatePointsGridSettings` |
| Create Points | `UPCGCreatePointsSettings` |
| Surface Sampler | `UPCGSurfaceSamplerSettings` |
| Spline Sampler | `UPCGSplineSamplerSettings` |
| Spline Intersection | `UPCGSplineIntersectionSettings` |
| Create Spline | `UPCGCreateSplineSettings` |
| Create Surface From Spline | `UPCGCreateSurfaceFromSplineSettings` |
| Create Surface From Polygon 2D | `UPCGCreateSurfaceFromPolygon2DSettings` |
| Create Polygon 2D | `UPCGCreatePolygon2DSettings` |
| **Get Spline Data** | `UPCGGetSplineSettings` |
| **Get Actor Data** | `UPCGDataFromActorSettings` |
| Get Actor Property | `UPCGGetActorPropertySettings` |
| Get Bounds | `UPCGGetBoundsSettings` |
| Difference | `UPCGDifferenceSettings` |
| Union | `UPCGUnionSettings` |
| **Intersection** | `UPCGOuterIntersectionSettings` |
| Inner Intersection | `UPCGInnerIntersectionSettings` |
| Bounds Modifier | `UPCGBoundsModifierSettings` |
| Self Pruning | `UPCGSelfPruningSettings` |
| Transform Points | `UPCGTransformPointsSettings` |
| Static Mesh Spawner | `UPCGStaticMeshSpawnerSettings` |
| Spawn Actor | `UPCGSpawnActorSettings` |
| Spawn Spline Mesh | `UPCGSpawnSplineMeshSettings` |
| Spawn Spline | `UPCGSpawnSplineSettings` |
| Add Attribute | `UPCGAddAttributeSettings` |
| **Create Constant**（旧名 Create Attribute） | `UPCGCreateAttributeSetSettings` |
| **Point Filter** | `UPCGAttributeFilteringSettings` |
| Filter Attribute Elements | `UPCGAttributeFilteringSettings`（同上，默认档） |
| Point Filter Range | `UPCGAttributeFilteringRangeSettings` |
| Filter Data By Attribute | `UPCGFilterByAttributeSettings` |
| Filter Data By Tag | `UPCGFilterByTagSettings` |
| Filter Data By Index | `UPCGFilterByIndexSettings` |
| Filter Data By Type | `UPCGFilterByTypeSettings` |
| Density Filter | `UPCGDensityFilterSettings` |
| Cluster | `UPCGClusterSettings` |
| Random Choice | `UPCGRandomChoiceSettings` |
| Gather | `UPCGGatherSettings` |
| Merge | `UPCGMergeSettings` |
| Merge Attributes | `UPCGMergeAttributesSettings` |
| Match And Set Attributes | `UPCGMatchAndSetAttributesSettings` |
| Point Match And Set | `UPCGPointMatchAndSetSettings` |
| Attribute Rename | `UPCGMetadataRenameSettings` |
| Attribute Cast | `UPCGAttributeCastSettings` |
| Attribute Remap | `UPCGAttributeRemapSettings` |
| Normal To Density | `UPCGNormalToDensitySettings` |
| Distance | `UPCGDistanceSettings` |
| Projection | `UPCGProjectionSettings` |
| **Subgraph** | `UPCGSubgraphSettings` |
| Loop | `UPCGLoopSettings` |
| Debug | `UPCGDebugSettings` |
| Print | `UPCGPrintElementSettings` |
| Branch | `UPCGBranchSettings` |
| **Select** | `UPCGBooleanSelectSettings` |
| Select (Multi) | `UPCGMultiSelectSettings` |
| Switch | `UPCGSwitchSettings` |
| User Parameter Get | `UPCGUserParameterGetSettings` |
| Load Data Table | `UPCGLoadDataTableSettings` |
| Load PCG Data Asset | `UPCGLoadDataAssetSettings` |
| Save PCG Data Asset | `UPCGSaveDataAssetSettings` |
| Data Count | `UPCGDataNumSettings` |
| Number Of Elements | `UPCGNumberOfElementsSettings` |
| Visualize Attribute | `UPCGVisualizeAttributeSettings` |
| Duplicate Point | `UPCGDuplicatePointSettings` |
| Copy Points | `UPCGCopyPointsSettings` |
| Collapse Points | `UPCGCollapsePointsSettings` |
| **Convert To Point Data** | `UPCGConvertToPointDataSettings` |
| Attribute Noise | `UPCGAttributeNoiseSettings` |
| Spatial Noise | `UPCGSpatialNoiseSettings` |
| Generate Seed | `UPCGGenerateSeedSettings` |
| Mutate Seed | `UPCGMutateSeedSettings` |
| Data View To String | `UPCGDataViewToStringSettings` |
| Export Selected Attributes | `UPCGExportSelectedAttributesSettings` |

---

## 2. 子图节点：**唯一正确的接线方式是 `SetSubgraph()`**

这是本文件最重要的一节，也是**最容易踩错的地方**。

`UPCGSubgraphSettings`（`Public/PCGSubgraph.h`）的资产属性是：

```cpp
UPROPERTY(BlueprintReadOnly, VisibleAnywhere, Category = Properties, Instanced,
          meta = (NoResetToDefault))
TObjectPtr<UPCGGraphInstance> SubgraphInstance;

UPROPERTY(BlueprintReadOnly, Category = Properties, meta = (PCG_Overridable))
TObjectPtr<UPCGGraphInterface> SubgraphOverride;
```

**两个都是 `BlueprintReadOnly`——从 Python 写不进去**（写了也会破坏 instanced 子对象
与编辑器回调的一致性）。`SubgraphOverride` 更不是作者侧属性，
它只在「执行动态子图时」非空，由 `PCG_Overridable` 参数 pin 填充。

**正确入口是基类上的 `BlueprintCallable` setter**：

```cpp
// Use this method from the outside to set the subgraph,
// as it will connect editor callbacks
UFUNCTION(BlueprintCallable, Category = Graph)
virtual void SetSubgraph(UPCGGraphInterface* InGraph);
```

所以：

```python
cls = unreal.load_class(None, "/Script/PCG.PCGSubgraphSettings")
node, settings = graph.add_node_of_type(cls)
graph_asset = unreal.load_asset("/PCGPrimitives/Primitives/Subdivide/Subdivide_Areas_withGrid")
settings.set_subgraph(graph_asset)        # 传 UPCGGraph 或 UPCGGraphInstance 都行
```

`UPCGGraph` 与 `UPCGGraphInstance` **都实现了 `UPCGGraphInterface`**，两者都能传。
这就是**加载原语库**的方式（86 个成品原语，见 `tooling.md` §3.2）。

读回用 `SubgraphInstance` 属性（`BlueprintReadOnly`，可读）。
注意 `GetSubgraph()` / `GetSubgraphInterface()` **不是 `UFUNCTION`**，Python 调不到。

> `UPCGLoopSettings` 继承 `UPCGSubgraphSettings`，同样用 `SetSubgraph`。
> `UPCGSpawnActorSettings` 虽也继承自 `UPCGBaseSubgraphSettings`，
> 但它走的是「模板 Actor 类」而不是子图。

---

## 2.2 实测：子图节点的 pin 面板长什么样

把一个节点指向原语后，它会**把子图自己的参数暴露成 pin**。
实测：指向 `/PCGPrimitives/Primitives/Create/Create_Point` 的节点，输入 pin 为：

```
PrimaryInput          ← 通用主输入（接上游数据）
Execution Dependency  ← 执行依赖
Overrides             ← 覆盖
SubgraphOverride      ← 子图替换
InputsProcessingGraph / InputsFallbackGraph /
CoreProcessGraph / PrepareOutputsGraph   ← 子图内部段替换接口
Location / Rotation / Scale / Extents    ← **这个原语自己的参数**
```

输出 pin：**单一的 `Out`**

**两个实用结论**：

1. **往原语里喂数据用 `PrimaryInput`**，不是 `In`。
   不同原语的专用参数 pin 各不相同
   （`Create_Point` 是 `Location`/`Rotation`/`Scale`/`Extents`），
   **必须读回来，不能猜。**
2. `PCGSubgraphNode` 餐暴露了 `get_settings()` 与 `get_graph()`，
   可用来回读该节点到底挂了哪张子图。

---

## 3. 在 `PCG` 模块之外的节点（需要对应插件已启用）

| 类名 | 模块（load 前缀） |
|---|---|
| `UPCGMeshSamplerSettings`、`UPCGAppendMeshesFromPointsSettings`、`UPCGBooleanOperationSettings`、`UPCGSplineToMeshSettings` 等 DynamicMesh 系列 | `PCGGeometryScriptInterop` |
| `UPCGLoadAlembicSettings` | `PCGExternalDataInterop` |
| `UPCGExecutePythonScriptSettings`、`UPCGPythonDataProcessorSettings` | `PCGPythonInteropEditor`（**编辑器模块**，打包版不存在） |
| `UPCGSpawnInstancedActorsSettings` | `PCGInstancedActorsInterop` |
| `UPCGWriteToNiagaraDataChannelSettings` | `PCGNiagaraInterop` |
| `UPCGGetWaterSplineSettings` | `PCGWaterInterop` |
| `UPCGPatchInstanceSpawnerSettings`、`UPCGProjectionSpawnerSettings`、`UPCGGetMeshTerrainSectionSettings` 等 | `PCGMeshPartitionInterop` |

**`PCGPrimitives` / `PCGBiomeCore` / `PCGToolset` 贡献零个 settings 类。**
`PCGPrimitives` 是**纯内容插件**（连 `.h` 都没有）——
所以「用 PCGPrimitives 原语」永远是指**建 `UPCGSubgraphSettings` 节点再 `set_subgraph`**，
没有可直接实例化的类。

---

## 4. 陷阱表：从节点标题猜类名会失败的地方

| 编辑器标题 | 实际类 | 猜错会怎样 |
|---|---|---|
| **Get Actor Data** | `UPCGDataFromActorSettings` | 猜 `UPCGGetActorDataSettings` → 不存在（**词序都反了**） |
| **Get Spline Data** | `UPCGGetSplineSettings` | 猜 `UPCGGetSplineDataSettings` → 不存在（`Get*Data` 系列**都掉 "Data"**） |
| Get Landscape Data | `UPCGGetLandscapeSettings` | 同上规律 |
| Get Volume Data | `UPCGGetVolumeSettings` | 同上规律 |
| Get Primitive Data | `UPCGGetPrimitiveSettings` | 同上规律 |
| **Intersection** | `UPCGOuterIntersectionSettings` | 猜 `UPCGIntersectionSettings` → 不存在（只有**数据类** `UPCGIntersectionData`） |
| **Point Filter** | `UPCGAttributeFilteringSettings`（预置档 index 1） | 猜 `UPCGPointFilterSettings` → 不存在 |
| Filter Attribute Elements | `UPCGAttributeFilteringSettings`（默认档 index 0） | 同一个类，只是预置档不同 |
| **Create Constant** | `UPCGCreateAttributeSetSettings` | 猜 `UPCGCreateAttributeSettings` → **不存在** |
| **Select** | `UPCGBooleanSelectSettings` | 猜 `UPCGSelectSettings` → 不存在 |
| Cluster | `UPCGClusterSettings` | 猜 `UPCGClusterElementSettings` → 不存在 |
| Print | `UPCGPrintElementSettings` | 猜 `UPCGPrintSettings` → 不存在 |
| Load Data Table | `UPCGLoadDataTableSettings` | 文件名是 `IO/PCGDataTableElement.h`，别按文件名猜 |
| Convert To Point Data | `UPCGConvertToPointDataSettings` | 文件名是 `PCGCollapseElement.h` |
| Create Surface From Polygon 2D | `UPCGCreateSurfaceFromPolygon2DSettings` | 文件名是 `PCGSurfaceFromPolygon2D.h` |
| Reverse Spline | `UPCGReverseSplineSettings` | 文件名是 `PCGSplineDirection.h` |
| Get Tags / Get Attributes | `UPCGGetTagsSettings` / `UPCGGetAttributesSettings` | 文件名是 `PCGGetDataInfo.h` |
| Replace Data By Tag | `UPCGReplaceDataByTagSettings` | 文件名是 `PCGReplaceDataByTags.h`（**复数 Tag，类名却是单数**） |

**两条元规律**：
1. `Get*Data` 节点族**类名里没有 "Data"**；而 `UPCGDataFromActorSettings` 干脆把词序颠倒。
2. `Element` 后缀**不可预测**：`PCGClusterElement.h → UPCGClusterSettings`（掉了），
   但 `PCGPrintElement.h → UPCGPrintElementSettings`（留着）。**必须查表。**

---

## 4.1 实测：给 Static Mesh Spawner 塞网格的正确路径

**这是一个实测出来的、与直觉不同的路径。**
几个看似合理的猜法**全部失败**：

| 猜法 | 结果 |
|---|---|
| `settings.static_meshes = [mesh]` | `Failed to find property 'static_meshes'` |
| `settings.meshes = [mesh]` | `Failed to find property 'meshes'` |
| `settings.mesh_selector_parameters.default_selector_instance` | `Failed to find property ... on 'PCGMeshSelectorWeighted'` |
| `selector.entries = [...]` | `Failed to find property 'entries'` |

**原因**：`get_editor_property("mesh_selector_parameters")` 返回的**就是选择器对象本身**
(`PCGMeshSelectorWeighted`)，不是一个包着它的 struct。
所以网格列表在**这个对象自己的属性**里。

**正确路径（实测走通，成功生成 800 个实例）**：

```python
spawner, sset = g.add_node_of_type(
    unreal.load_class(None, "/Script/PCG.PCGStaticMeshSpawnerSettings"))

# 选择器对象本身，它的属性叫 mesh_entries
sel = sset.get_editor_property("mesh_selector_parameters")

entry = unreal.PCGMeshSelectorWeightedEntry()          # 先造条目
desc  = entry.get_editor_property("descriptor")        # PCGSoftISMComponentDescriptor
desc.set_editor_property("static_mesh", unreal.load_asset("/Engine/BasicShapes/Cube.Cube"))
entry.set_editor_property("weight", 1.0)
sel.set_editor_property("mesh_entries", [entry])       # 回写到选择器

# 必须开，否则 MCP 触发的首次执行看不到结果
sset.set_editor_property("synchronous_load", True)
```

**验证**：执行后 `cleanup` 前用
`actor.get_components_by_class(unreal.PrimitiveComponent)` 数一下，
应当出现一个 **`ISM_Cube_0(InstancedStaticMeshComponent)`**，
而不只有 `BrushComponent0`。

> 顺带记一条：`PCGMeshSelectorWeightedEntry` 的 `dir()` 里只有 `weight`，
> `descriptor` 要靠 `get_editor_property` 取。另一个类型
> `PCGMeshSelectorWeightedByCategory` 是另一种选择器，属性名不同。

---

## 5. 一个硬限制：动态输入 pin 加不了

`UPCGSettingsWithDynamicInputs`（抽象基类）是**输入 pin 可由用户点 "+" 增长**的那类节点。
它的 5 个具体子类：

> `UPCGGatherSettings`、`UPCGMergeSettings`、`UPCGMergeAttributesSettings`、
> `UPCGUnionSettings`、`UPCGOuterIntersectionSettings`

其 pin 增长机制 `OnUserAddDynamicInputPin()` / `AddDynamicInputPin()` /
`OnUserRemoveDynamicInputPin()` **全部是 `WITH_EDITOR`-only 且都不是 `UFUNCTION`**。

→ **从 Python 建得出 Gather/Union/Merge/Intersection 节点，但加不了额外的输入 pin。**
你只能拿到构造函数路径产生的默认 pin 数。

**规避**：需要 N 路 Union 时，**串接多个二元 Union**，而不是指望加 pin。
（`InputPinProperties()` 被声明为 `override final`，子类也改不了。）

---

## 6. `UPCGSettings` 基类能写什么

`BlueprintReadWrite` 且对脚本有意义的：

| 属性 | 说明 |
|---|---|
| `b_enabled` | 节点启用与否 |
| `b_debug` | 调试标记 |
| `seed` | 随机种子（**默认值随类名哈希而变**，别假设是固定值） |
| `b_execution_dependency_required` | |

注意：

- **`SetEnabled(bool)` / `SetDebugged(bool)` 不是 `UFUNCTION`**，
  Python 调不到。只能直接写 `b_enabled` 属性——代价是子图/reroute 这类
  「启用状态变化时有特殊逻辑」的节点**不会**跑那段逻辑。
- `GetType()` / `GetDefaultNodeName()` / `GetDefaultNodeTitle()`
  **都是 `WITH_EDITOR`-only 且非 `UFUNCTION`**。
  → **无法从 Python 反查「某个标题对应哪个类」**。必须靠本文件的表，或走编辑器节点调色板。
- `ApplyPreconfiguredSettings()` **不是 `UFUNCTION`**，
  所以想拿「Point Filter」那档预置默认值，得自己按属性手工设。
