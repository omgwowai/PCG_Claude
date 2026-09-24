# 18 阶段跑一遍：操作手册与实测约束

> **2026-09-23 实测记录。** 本文是「打开 `L_CitySamplePCG_Demo`，把 18 张图各跑一遍，
> 每阶段截图」这件事的完整做法与踩过的坑。
> 交付物在 `docs/pcg-18-stage-report.html`（自包含，18 张图全内嵌）。

---

## 0. 一句话结论

**能跑通，18 张图全部截到。** 但有三件事必须按本文的做法来，否则
要么截出来是空天，要么把编辑器跑崩：

1. **机位用关卡自带的 11 个 `CineCameraActor`**，不要自己算；
2. **PCG debug 要限量**（每阶段 flag 4 个节点），不能全开；
3. **截图一次调用只发一张**，因为它在下一帧才落盘。

---

## 1. 现状：这些图**已经有 Epic 生成的几何**

加载 `L_CitySamplePCG_Demo` 后，18 个 `PCGVolume` 每个都挂着对应的图，
且**大部分阶段已经有成品几何**（实测）：

| 阶段 | 真实实例 | debug 立方体 |
|---|---|---|
| 1 Terrain | 0 | 785,181 |
| 2 BG Buildings | 394 | 1,389 |
| 3 BG Mountains | 59 | 361 |
| 4 MainTower Footprint | 0 | 18 |
| 5 CentralPark Footprint | 0 | 8 |
| 6 Districts | 0 | 18,218 |
| 7 Roads | 286,221 | 721,190 |
| 8 Highways | 81,684 | 625,049 |
| 9 Lots | 11,255 | 8,343 |
| 10 Ground | 220,128 | 1,571,116 |
| 11 LeftOverLots | 40,882 | 1,570,525 |
| 12 Parkings | 13,495 | 783,936 |
| 13 Buildings | **478,349** | 1,332,360 |
| 14 Rooftops | 27,110 | 0 |
| 15 MainTower Visuals | 26,583 | 1,371,887 |
| 16 CentralPark Visuals | **965,022** | 9,702,657 |
| 17 CityEdge | 20,768 | 1,033,351 |
| 18 OuterForest | 34,661 | 1,045,270 |

**含义**：所谓「跑一遍」其实是**就地重算**，不是从零生成。
阶段 1/4/5/6 产出的是**数据**（样条、区域、点），没有实例化几何 ——
它们的画面里只有地形 + debug 立方体，这是正常的，**不是失败**。

---

## 2. 机位：用关卡自带的电影摄像机

**别自己算机位。** 实测过四种算法，全部失败：

| 来源 | 结果 |
|---|---|
| `Actor.get_actor_bounds()` | ~±96,000,000 单位，完全不能用 |
| `get_actor_bounds_pcg()` | 只有 brush，~±2500，忽略输出 |
| 实例平移的 min/max | ~±9,000,000，离群点主导 |
| 实例平移的 2/98 百分位 | 阶段 3 仍是 17,600,000 宽 |

原因：**这些阶段的几何本身就丢在极远处**。阶段 3 的 59 个
`SM_GiganticSandstoneTerrain_01` 实例真的放在离原点约 **10,000,000** 单位的地方
（它是背景远景），所以任何从包围盒推出来的机位都会飞到 ~21,000,000 单位外，
画面里只剩天。

**关卡自带 11 个 `CineCameraActor`，是唯一好用的机位来源**（实测坐标）：

| 机位 | 位置 | 适合 |
|---|---|---|
| `CineCameraActor_City_WideView_1` | 167971, 12718, 47372 | 全城 / 地形 / 边缘 / 外林 |
| `CineCameraActor_City_WideView_2` | 58471, 1917, 24700 | 全城 / 街区 |
| `CineCameraActor_Building_Edit` | 18891, -969, 31112 | 建筑 / 屋顶 / 主塔 |
| `CineCameraActor_CentralPark_1` | 115956, 47351, 65750 | 中央公园 |
| `CineCameraActor_Street_1` | 68418, 6716, 8417 | 街道 / 道路 |
| `CineCameraActor_Street_2` | 9515, 57195, 5659 | 街道 / 地块 |
| `CineCameraActor_Street_3` | 15504, 5673, 2121 | 街道 / 地面 / 停车 |
| `CineCameraActor_HighWayEdit` | 25589, 77891, 26085 | 高架 |
| `CineCameraActor_Lighting_*` ×3 | — | 光照变体，与阶段无关 |

用法：把机位的 `get_actor_location()` / `get_actor_rotation()` 喂给
`les.set_level_viewport_camera_info(loc, rot, key)`，**机位本身不动**，
只是把视口挪过去。

---

## 3. PCG debug：没有全局开关，且必须限量

**先记结论：没有全局 debug 开关。**

- 所有 `pcg.*` 控制台变量读回来都是空串或 0（`pcg.Debug`、`pcg.ShowDebug`、
  `pcg.DumpData`、`pcg.DebugVisualization`、`pcg.DrawDebug` 等全试过）；
- `PCGComponent` 上**没有任何 debug 成员**；
- 唯一开关是 **`PCGSettings` 上的 `debug` 布尔**（`set_editor_property("debug", True)`）。

开启后**重新生成**，宿主组件会长出 debug 几何。实测（阶段 3）：

```
开 debug 前：1 个 ISM 组件 / 59 实例
开 debug 后：7 个 ISM 组件 / 419 实例
```

多出来的 6 个组件全部是 **`/PCG/DebugObjects/PCG_Cube`** 的 ISM ——
即每 flag 一个节点长一个组件。引擎源码印证：
`IPCGElement::DebugDisplay()` 在没有 `bDebug` 时直接 early-out。

### 3.1 致命约束：全开会把编辑器跑崩

**18 张图的所有节点全 flag → 20,570,859 个 debug 立方体**，
编辑器内存冲到 ~92 GB 后**直接崩**：

```
LogWindows: Error: Fatal error:
  [File:.../UnrealEd/Private/EditorServer.cpp] [Line: 1951]
  World Memory Leaks: 2 leaks objects and packages.
  [Callstack] UEditorEngine::CheckForWorldGCLeaks()
```

→ **每阶段只 flag 4 个节点**（实测够看清），**画面里最多同时显示 3 个
debug 组件**，其余 `set_visibility(False)`。

### 3.2 一个必须知道的坑：**Python 全局里的 UObject 会让下一次切关卡崩掉编辑器**

> **2026-09-24 更正。** 本文原先写的是「重载这个关卡就会崩」，那是**误诊**。
> 重载并不是原因，甚至不算危险；真正的原因见下。

`CheckForWorldGCLeaks()` 的 abort 条件是**关世界未被 GC 回收**。而本项目的桥
用 `exec(compile(...), globals())` 在**常驻的 `__main__` 命名空间**里执行脚本，
所以**顶层变量跨调用存活**：任何留在全局的 world / package / level / actor /
component 包装都会一直引用旧 world，下一次 `load_level` 就命中：

```
World Memory Leaks: 1 leaks objects and packages
  (root) GCObjectReferencer -> FPyReferenceCollector::AddReferencedObjects(Package /Temp/Untitled_1)
Script Stack: /Script/LevelEditor.LevelEditorSubsystem.LoadLevel
```

引用链直接指名：是 Python 侧的引用收集器在钉住旧包。

**实测证据（2026-09-24）**：`pcg_area_demo_recon.py` 的第一版把
`pkg = w.get_outermost()` 留在全局，下一次切关卡就崩了；改成全部局部作用域后，
**同一个关卡照常加载，没有重启编辑器**。另外 `pcg_sa_hostprobe.py` 打印的
`globals_count: 74` 里能看到**多个脚本的常量混在同一个字典**，这就是同一个机制。

**正确规则**：

1. **UObject 只放函数局部** —— world / package / level / actor / component 一律不要赋值给顶层变量。
2. **全局只放 JSON 可序列化的东西** —— 常量、字符串、数字、纯 dict/list。
3. **切关卡前主动清场**：删掉全局里 `unreal.Object` 类型的名字再 `gc.collect()`
   （`pcg_sa_level.py` 的 `purge_uobject_globals()` 就是这个，实测三次调用都报 dropped 为空，
   是廉价的保险）。
4. **全局 dict/list 也要检查里面有没有对象**：递归判断，不要只看容器类型 ——
   一个 `{"pkg": package}` 一样会钉住 world。

**副作用之一**：既然全局跨调用存活，`import X` 会被 `sys.modules` 缓存，
**改了 X 的内容再 import 拿到的是旧代码**。需要热更新就 `sys.modules.pop("X", None)` 再 import。

---

## 4. 截图：一次调用只能发一张

`unreal.AutomationLibrary.take_high_res_screenshot(...)` 会在**下一帧**才写盘。

- **同一次调用里连发多张 → 后面的顶掉前面**，最后只有一张落盘
  （实测一批发 9 张，只落了 2 张，且是最后两张）；
- **正确节奏：一次 `run_unreal_script` 只发一张**，下一次调用再确认文件，
  然后再发下一张；
- 落盘位置固定：`Saved/Screenshots/WindowsEditor/<name>.png`，
  日志里对应 `LogClient: High resolution screenshot saved as ...`；
- **参数只能走关键字**。签名是
  `take_high_res_screenshot(res_x, res_y, filename, camera=None, mask_enabled=False,
  capture_hdr=False, comparison_tolerance=..., comparison_notes="", delay=0.0,
  force_game_view=True)` —— 把 `force_game_view` 按位置传会落到
  `comparison_tolerance` 上，报 `Failed to convert parameter
  'comparison_tolerance'`。

### 4.1 隔离：一阶段一图

18 个 volume **都在世界原点**，输出互相重叠，所以不隔离的话
一张图里是整座城，无法佐证任何单个阶段。

做法：**只显示目标阶段的组件，其余 17 个 volume 的全部组件
`set_visibility(False)`**（实测一次要隐藏 ~1500–1700 个组件），
拍完再 `show_all` 恢复。

---

## 5. 安全：全程不保存，Epic 资产零改动

- 这个关卡是 **Epic 的出厂内容**，整个流程**没有任何保存调用**
  （脚本里 grep 不到 `save_current_level` / `save_all_dirty_levels` /
  `save_asset`）。实测跑完后插件 `Content/` 下**24 小时内 0 个文件被改**，
  关卡 mtime 仍是出厂日期。
- 所有重算只活在内存里，**重载关卡即还原**。
- **自动保存是个隐患**：它会往 `Saved/Autosaves/` 写影子副本，
  并弹「Restore Packages」模态框；**一旦误点恢复，就会把内存里的临时重算
  写回出厂资产**。这个模态框还**卡住游戏线程**，让 MCP 桥整个失去响应
  （实测遇到过一次，用 `PostMessage(WM_CLOSE)` 关掉、且不点恢复）。
  → 每轮结束后 `rm -rf Saved/Autosaves/*` 清掉。

---

## 6. 复现路径（脚本都在 `Content/Python/`）

| 脚本 | 阶段 | 作用 |
|---|---|---|
| `pcg_shots.py` args=`{"phase":"status"}` | 只读 | 当前关卡是不是 demo 关卡 |
| `pcg_shots.py` args=`{"phase":"load"}` | 一次 | 加载 demo 关卡（已是则该步跳过） |
| `pcg_shots.py` args=`{"phase":"run","stage":N}` | 每阶段 | flag N 的 debug + 生成 N + **截 N−1** |
| `pcg_shots.py` args=`{"phase":"shot","stage":N}` | 补拍 | 不生成，只隔离 + 机位 + 截图 |
| `pcg_shots.py` args=`{"phase":"show_all"}` | 收尾 | 恢复全部可见性 |
| `pcg_stage_run.py` args=`{"phase":"debug_off"}` | 收尾 | 把图的 debug flag 全部清掉 |

报告生成（纯本地，不碰编辑器）：

```powershell
python Tools/build_stage_manifest.py                    # 从 census + 截图 生成清单
python Tools/build_pcg_stage_report.py `
    --manifest Saved/Reports/stage_manifest.json `
    --out docs/pcg-18-stage-report.html `
    --max-edge 1200 --quality 80
```

---

## 7. 报告产出的两个实现细节

1. **产物是「片段形态」**：只有 `<title>` / `<link>` / `<style>` / 内容，
   **没有 `<html>` `<head>` `<body>`**。浏览器打开时 `<title>` 会被归入 head，
   页面正常显示、标签页标题也对；而作为 Artifact 发布时，发布端会替它套骨架，
   片段形态正是它要的。
2. **模板用 `str.replace` 填 `__TOKEN__`，不要用 %-格式化**：页面 CSS 里本来
   就有百分号（`width:100%`），%-格式化会直接
   `TypeError: not enough arguments for format string`。卡片同理，用 replace。
