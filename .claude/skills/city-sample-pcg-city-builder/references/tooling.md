# 传输层与工具形态（PCG_Claude / UnrealMcpBridge）

> 本项目**只有一个 MCP 工具**：`run_unreal_script`。
> 没有 `PCGToolset`、没有 `list_toolsets`/`call_tool`、没有 `EditorToolset` 家族。
> 一切「找资产、读写属性、摆 Actor、建图」都要**自己写 Python 调 `unreal.*`**。

---

## 1. 调用形态

```
run_unreal_script(script_path = "pcg_xxx.py", args = { ... })
```

- `script_path`：**相对** `E:\PCG_Claude\Content\Python\` 的 `.py` 路径
- `args`：可选 JSON 对象，脚本内以**已解析的 dict** 出现在全局 `mcp_args`（缺省为 `{}`）
- 返回值是**字符串**，格式固定：

```
Script succeeded.
stdout:
<你 print 的东西>

return:
<你赋给 mcp_result 的 JSON>
```

失败时：

```
Script failed.
stdout:
<异常前已 print 的内容>

error:
<完整 traceback>
```

### 1.1 脚本契约（非常重要）

| 项 | 规则 |
|---|---|
| 脚本位置 | **必须**在 `Content/Python/` 下（可含子目录）。逃出该根、非 `.py`、文件不存在**一律拒绝** |
| 返回值 | 赋给全局 **`mcp_result`**，且必须**可 `json.dump`** |
| 输出 | 用 **`print`**。stdout 被捕获后**在脚本结束时一次性返回**（无流式） |
| `mcp_args` | 顶层可用；函数内要用需 `global mcp_args` |
| 执行方式 | `exec(compile(...), globals())`，所以顶层赋值 `mcp_result = {...}` 即可 |
| 线程 | **游戏线程**。脚本跑完前**阻塞编辑器 UI** |
| 超时 | **没有任何超时**。死循环 = 编辑器永久卡死 |

### 1.2 六个反直觉之处

1. **`sys.stderr` 不被捕获**，`unreal.log` / `log_warning` **也不进 stdout**——
   它们只进编辑器输出日志。**要回传就必须 `print` 或写进 `mcp_result`。**
2. **`mcp_result` 不可序列化时没有有用的报错**。
   `json.dump` 在 try/finally **之后**才失败，结果文件根本没写出，
   你只会看到笼统的 `failed to produce result file`。
   → `unreal.Vector` / `unreal.Name` / Actor 都**不是** JSON 可序列化的，
   必须转成 `[x,y,z]` 或 `str(...)`。
3. **没有大小限制**：脚本长度无上限（只有 base64 展开与 WebSocket 帧的实际约束）。
4. **没有超时**：唯一能让调用提前结束的是连接断开。
5. **请求帧格式错误时无回复**。`type` 不是 `"run"`、缺 `id` 或 `script_path`
   → 帧被**静默丢弃**，你只会一直等。所以「没反应」首先怀疑脚本路径写错。
6. **`args` 必须是对象**；传非对象则退化为 `{}`（不报错）。

### 1.3 拒绝时的确切报错串

| 情形 | 报错 |
|---|---|
| 逃出脚本根 | `script path escapes scripts root: <你传的相对路径>` |
| 非 `.py` | `script path must end with .py` |
| 文件不存在 | `script not found: <解析后的绝对路径>` |
| 引擎无 Python | `Python is not available in this editor.` |
| 读文件失败 | `failed to read script: <路径>` |

编辑器未运行时，工具返回的**不是异常**，而是一段普通文本：

```
Unreal editor not connected on 127.0.0.1:8777
```

**看到这句就停下来请用户启动编辑器**，不要反复重试。
端口被占可查：`netstat -ano | findstr 8777`。

---

## 2. 本项目的 MCP 配置

`E:\PCG_Claude\.mcp.json`：

```json
{
  "mcpServers": {
    "unreal": {
      "command": "E:/PCG_Claude/mcp_server/.venv/Scripts/python.exe",
      "args": ["-m", "mcp_server"],
      "cwd": "E:/PCG_Claude/mcp_server",
      "env": { "UE_MCP_HOST": "127.0.0.1", "UE_MCP_PORT": "8777" }
    }
  }
}
```

工具 id 因此是 `mcp__unreal__run_unreal_script`。

**端口 `8777` 写在四个地方，必须一致**：
`UnrealMcpBridgeSettings.h` 的 `Port` 默认值、
`.mcp.json` 的 `env.UE_MCP_PORT`、
`mcp_server/mcp_server/server.py` 的 `UE_MCP_PORT` 默认值、
以及本文件的连接错误串描述。
另有每用户覆盖：`Saved/Config/WindowsEditor/Editor.ini` 的
`[/Script/UnrealMcpBridge.UnrealMcpBridgeSettings]`。

**`mcp` 包必须 `<2.0`**：2.x 把 `FastMCP` 改名为 `MCPServer`，装错版本启动即崩。

---

## 3. 没有工具集意味着什么

`E:\CitySample 5.8` 那边有 `EditorToolset` 全家桶（`AssetTools` / `ObjectTools` /
`SceneTools` / `BlueprintTools` / `StaticMeshTools` / `DataTableTools` …）和 `PCGToolset`。
**本项目一个都没有。** 对照关系：

| CitySample 侧的工具 | 本项目怎么写 |
|---|---|
| `AssetTools.find_assets` | `unreal.EditorAssetLibrary.list_assets(path, recursive=True)` + 自己筛 |
| `AssetTools.save_assets([])` | `unreal.EditorAssetLibrary.save_asset(path)` / `save_directory` |
| `AssetTools.delete` | `unreal.EditorAssetLibrary.delete_asset(path)` |
| `SceneTools.add_to_scene_from_class` | `unreal.EditorActorSubsystem().spawn_actor_from_class(cls, loc, rot)` |
| `SceneTools.remove_from_scene` | `unreal.EditorActorSubsystem().destroy_actor(actor)` |
| `ObjectTools.set_properties` | `obj.set_editor_property(name, value)` |
| `ObjectTools.get_properties` | `obj.get_editor_property(name)` |
| `StaticMeshTools.get_bounds` | `mesh.get_bounds()` / `mesh.get_bounding_box()`（**自己验证方法名**） |
| `PCGToolset.CreateGraph` | 走 `unreal.AssetToolsHelpers` + PCG 图工厂（**先验证工厂名**） |
| `PCGToolset.AddNode` | `graph.add_node_of_type(settings_class)`（**先验证绑定形态**） |
| `PCGToolset.ConnectNodePins` | `graph.add_edge(from_node, "Out", to_node, "In")` |
| `PCGToolset.ExecuteGraphInstance` | `component.generate_local(True)` |
| `PCGToolset.GetNodeDataView` | **无对应**。改用 `component.get_generated_graph_output()` 或引擎端其它脚本可达面 |
| `PCGToolset.ListAvailableSubgraphs` | 无对应，改用 `EditorAssetLibrary.list_assets("/PCGPrimitives/Primitives", recursive=True)` |
| `PCGToolset.DrawSpline` | 无对应。样条要么脚本造，要么请用户手画 |

### 3.1 两个已从源码确认的关键入口

这两处是**纯 Python 建图链路的枢纽**，已核对过 `UFUNCTION` 标记：

**(a) 把子图节点指向一个子图资产** ——
`Engine/Plugins/PCG/Source/PCG/Public/PCGSubgraph.h`：

```cpp
UCLASS(MinimalAPI, Abstract)
class UPCGBaseSubgraphSettings : public UPCGSettings
{
	UFUNCTION(BlueprintCallable, Category = Graph)
	UE_API virtual void SetSubgraph(UPCGGraphInterface* InGraph);
};
```

→ 这是**加载原语库**的入口（实测 `/PCGPrimitives/Primitives` 下有 **86 个成品原语**，
递归共 225 个资产，见 §3.2）：
建一个 `UPCGSubgraphSettings` 节点，把 `/PCGPrimitives/Primitives/...` 的图
（`unreal.load_asset(path)`）传给 `set_subgraph(...)`。
`PCGGraphInstance` 与 `PCGGraph` 都实现了 `UPCGGraphInterface`，两者都能传。

**(b) 读生成结果的点数** ——
`Engine/Plugins/PCG/Source/PCG/Public/Data/PCGBasePointData.h`：

```cpp
UFUNCTION(BlueprintCallable, Category = PointData, meta = (Keywords="Number"))
virtual int32 GetNumPoints() const PURE_VIRTUAL(...);
```

→ **`get_num_points()` 在 Python 里是可用的**（在**基类** `UPCGBasePointData` 上，
不是在 `UPCGPointData` 上——后者里那个是 C++ override，别找错地方）。
配合 `UPCGPointData::get_points()` / `get_point(i)` 即可做数值验证。

> **已实测（2026-09-23）**：`FPCGDataCollection` 的 **C++ 访问器在 Python 侧不可用**——
> `get_all_inputs()` / `get_all_spatial_inputs()` / `get_inputs()` **全部 `AttributeError`**。
> 但它是 `USTRUCT`，**字段可以直接读**：
>
> ```python
> coll = comp.get_generated_graph_output()      # -> PCGDataCollection 结构体
> tagged = coll.get_editor_property("tagged_data")   # -> TArray<FPCGTaggedData>
> for item in tagged:
>     pin  = item.get_editor_property("pin")
>     tags = item.get_editor_property("tags")
>     wrap = item.get_editor_property("data")       # -> FPCGDataPtrWrapper
> ```
>
> **读法就是「读结构体字段」，不是「调方法」。** 这是本项目做数值验证的主路径。

**完整可用的读数链路（实测走通，读到 3200 点）**：

```python
coll  = comp.get_generated_graph_output()                  # PCGDataCollection 结构体
items = coll.get_editor_property("tagged_data")            # TArray<FPCGTaggedData>
for it in items:
    pin   = it.get_editor_property("pin")                  # 如 "Out"
    wrap  = it.get_editor_property("data")                 # FPCGDataPtrWrapper
    data  = wrap.get_editor_property("data")               # -> PCGPointArrayData  ← 关键一步
    n     = data.get_num_points()                          # 3200
    empty = data.is_empty()                                # False
```

**三个坑**：

1. **解包要走 `get_editor_property("data")`**，不是 `wrap.data`。
   `FPCGDataPtrWrapper` 的 `dir()` 里只有 `get_editor_property` / `to_dict` / `to_tuple` 等，
   没有裸的 `.data` 属性。
2. **`get_num_points()` 与 `is_empty()` 可用，但 `get_points()` / `get_points_copy()` 报 `AttributeError`**
   —— 在 `PCGPointArrayData` 上它们不可达。
   → **能拿到「有多少点」，拿不到「点数组本身」。**
   要逐点数据得换别的路径（未验证）。
3. 结果是 **`PCGPointArrayData`**（不是 `PCGPointData`），类别名判断要按这个来。

### 3.3 `CreatePointsGrid` 的点数公式（实测修正）

**`GridExtents` 是「全宽」不是「半宽」**，且 **Z 轴也算一层**：

```
点数 = (2 * extent.x / cell.x) * (2 * extent.y / cell.y) * (2 * extent.z / cell.z)
```

实测：`extent = (2000, 2000, 100)`、`cell = (100, 100, 100)`
→ `(2*2000/100) * (2*2000/100) * (2*100/100)` = `40 * 40 * 2` = **3200** ✓

（我最初按「半宽 + 忽略 Z」算成 21×21=441，错了两次。按上面这条公式来。）

### 3.2 原语库的实际规模（实测，2026-09-23）

| 查询 | 结果 |
|---|---|
| `/PCGPrimitives/Primitives` 递归列全部资产 | **225** 个（含各原语的 `_CoreProcess` 等内部子图） |
| 其中**顶层成品原语**（`Primitives/<动词>/<名>.uasset`） | **86** 个 |
| `/PCGPrimitives/Examples` 递归 | **99** 个 |
| `/PCGPrimitives/Instants` 递归 | **16** 个 |

**写脚本时注意**：`list_assets` 递归会连内部子图一起返回，
所以直接数会得到 225 而不是 86。要数成品原语得按路径深度过滤。

`load_asset("/PCGPrimitives/Primitives/Subdivide/Subdivide_Areas_withGrid")`
实测返回 **`PCGGraph`**——正是 `set_subgraph()` 想要的东西。

> **上表中带「先验证」的条目不要照抄。**
> 本项目的 `unreal` API 可达面必须**运行时实测**——
> 先跑 `pcg_preflight.py`（已放在 `Content/Python/`），它会报告：
> PCG 是否加载、`unreal.PCGGraph` 有哪些成员、
> `add_node_of_type`/`add_edge` 是否存在、有哪些 `*Settings` 类（即节点调色板）、
> `PCGComponent` 有哪些方法、`/PCGPrimitives/*` 挂载点是否存在。

---

## 4. 项目约定

- **脚本放 `Content/Python/`**，`Content/Python` 未被 `.gitignore` 排除，所以脚本会被 git 跟踪。
  正式脚本用有意义的名字；探索性的用完即删。
- **一个脚本 = 一次往返。** 每次调用都是完整的进程内执行 + 一次性 stdout 回传，
  所以**把能合并的探查合并进一个脚本**，不要为查三个属性发三次调用。
  反复「查一个属性 → 再查一个」是最大的时间浪费来源。
- **长任务要 print 进度。** 因为 stdout 只在结束时返回，中途 print 看不到；
  但如果脚本崩了，异常前的 print 会随 `stdout` 一起回来，是唯一的现场证据。
- **破坏性操作前先 `save`/先确认。** 没有 `ScopedEditorTransaction` 就不会有撤销栈，
  误删只能靠重开关卡。
