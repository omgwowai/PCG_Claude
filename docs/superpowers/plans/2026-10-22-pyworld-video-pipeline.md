# PyWorld (视频管线) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把《Building Worlds with Houdini》的世界生成流程做成 9 张 PCG 图（每张一个 Python 节点 + 原生地形/生成节点），在新关卡 `/Game/PyPCG/L_PyWorld` 里按顺序生成一个 2×2 km 的山谷世界。

**Architecture:** 一个阶段 = 一张图 = 一个 PCG volume。阶段逻辑是 `Content/Python/pypcg/stages/wNN_*.py` 里的纯 Python（`run(inputs, params, ctx)`，经 `pypcg.host` 运行），共享算法在 `Content/Python/pypcg/world/`；图由 `pypcg/world/graphs.py` 用 `pypcg.dsl` 描述、`pypcg.build.build_slim` 生成并结构核对；驱动 `Content/Python/pyworld.py` 一次一个阶段。

**Tech Stack:** UE 5.8 PCG + PCGPythonInterop（Python Data Processor）、PCGPrimitives / MeshPartition interop 原语、编辑器内 Python 3.11（无 numpy）、离线 pytest（`C:\Python314\python.exe`）。

**Spec:** `docs/superpowers/specs/2026-10-22-pyworld-video-pipeline-design.md`

## Global Constraints

- 运行时形态：每张图一个 Python Data Processor 节点；地形读写、`Spawn_Assets`、`Assign_ShapeGrammarDefinition`、`Transform_MeshTerrain_Erosion` 保持原生（spec D3、§2.3）。
- 阶段模块不 import unreal；随机只用 `ctx.rng` / `ctx.seed`（spec P3）。
- 图资产只由 `.py` 生成，`build_slim` 结构核对 `diffs: 0` 才保存（P4），资产在 `/Game/PyPCG/World/`。
- 地形：3 km 查询框 `MeshPartitionBoundSize = (300000, 300000, 300000)`；顶点间距 585.9375 cm；读写子优先级 W1 写 1；W3 读 Intermediate 2 写 3；W4 读 4 写 5；W6 读 6 写 7；W9 读 8 写 9；W2/W7/W8 读 Final（spec §2.2）。每次写全部顶点。
- Python 节点的每个输入 pin 都接线（trap 80）；单个 Python 节点目标 < 60 s。
- 关卡 `/Game/PyPCG/L_PyWorld` 由 `/Game/PyPCG/L_PyCity` 模板复制；驱动只在它是当前关卡时写，只保存它；保存的 actor 文件 < 100 MB。
- 既有离线基线不变：`C:\Python314\python.exe -m pytest Tools/pypcg/tests -q` → 762 passed, 18 skipped（加上本计划新增的测试）。
- 编辑器崩溃后先挪 `Saved/Autosaves/*`（trap 78），不要先 `new_blank_map` 再 `load_level`（79、83）。

## Review Focus

1. **上游为空**（阶段在上游没生成时运行、或上游 0 个 item）：每个阶段都要输出空集 + Summary，不抛异常 —— 每个阶段的 `test_empty_inputs`。
2. **A\* 无解**（河源/河口或某个地点被陡坡围住）：W3 原样写回地形、`length_m = 0`；W4 跳过那条路并报 `connected = False`，验收失败而不是崩 —— W3 `test_unreachable_outlet`、W4 `test_blocked_location`。
3. **吸附半径内采不到地面**（地点在地形外）：W2 保持原位置、`Slope = -1` —— W2 `test_location_off_terrain`。
4. **两个聚落半径重叠**：共享的占地索引保证跨聚落不重叠 —— W6 `test_two_close_settlements_never_overlap`。
5. **桥面高于路两侧的地面**：W4 的纵断面在桥上抬到水面 + 2.5 m 且坡度仍不超限 —— W4 `test_bridge_profile_respects_grade`。

---

## File Structure

| File | Responsibility |
|---|---|
| `Content/Python/pypcg/world/__init__.py` | 阶段表、资产路径、tag、网格路径、地形优先级等常量 |
| `Content/Python/pypcg/world/noise.py` | 值噪声、fBm、脊状噪声 |
| `Content/Python/pypcg/world/grid.py` | `Lattice`：顶点格高度场（插值、坡度、粗化） |
| `Content/Python/pypcg/world/hydro.py` | 最小值滤波、D8 汇流 |
| `Content/Python/pypcg/world/geom.py` | 折线、重采样、线段索引、相交、矩形/环与索引 |
| `Content/Python/pypcg/world/astar.py` | 格上 A\*（8 / 16 邻域） |
| `Content/Python/pypcg/world/terraform.py` | 下切河道、路基走廊、平台、垫平 |
| `Content/Python/pypcg/world/points.py` | 点集拷贝/改高、网格点、表格点、Summary |
| `Content/Python/pypcg/world/layout.py` | 控制布局（山谷轴线、地点、河端、出口） |
| `Content/Python/pypcg/world/rules.py` | 聚落规则表、建筑表、生物群系表 |
| `Content/Python/pypcg/world/settle.py` | 聚落 2D 布局 |
| `Content/Python/pypcg/world/scatter.py` | 抖动网格、排除区 |
| `Content/Python/pypcg/world/checks.py` | 每步验收、世界校验 |
| `Content/Python/pypcg/world/graphs.py` | 9 张图的描述 |
| `Content/Python/pypcg/stages/w01_terrain.py` … `w09_surface.py` | 9 个阶段模块 |
| `Content/Python/pyworld.py` | 编辑器驱动 |
| `Content/Python/pypcg/dsl.py` | 改：`SlimGraph(name=)`、`Graph.actor_points` |
| `Content/Python/pypcg/level.py` | 改：`WORLD` |
| `Content/Python/pypcg_library.py`、`pypcg/library.json` | 改：加入 `Transform_MeshTerrain_Erosion` |
| `Tools/pypcg/tests/world_fixtures.py`、`test_world_*.py` | 离线测试 |
| `docs/pyworld-guide.md` | 指南 |

---

### Task 1: Plumbing — 常量包、DSL 两处小改、关卡常量

**Files:**
- Create: `Content/Python/pypcg/world/__init__.py`, `Tools/pypcg/tests/world_fixtures.py`, `Tools/pypcg/tests/test_world_plumbing.py`
- Modify: `Content/Python/pypcg/dsl.py` (`SlimGraph.__init__`, new `Graph.actor_points`), `Content/Python/pypcg/level.py`

**Interfaces:**
- Produces: `pypcg.world.STAGES`, `name(n)`, `module_name(n)`, `asset(n)`, `volume_tag(n)`, `stage_number(module)`, `MESH`, `GRAMMAR`, `WATER_MATERIAL`, `CHANNELS`, `TERRAIN`, `QUERY_BOX`, `VERTEX_CM`, `SEA_Z`, `ROAD_INNER`, `ROAD_BLEND`, `LEVEL`, `TEMPLATE`, `ASSET_DIR`; `dsl.SlimGraph(module, name=...)`; `dsl.Graph.actor_points(tag, title)`; `level.WORLD`; fixtures `terrain(fn, half)`, `Surface(fn)`, `run_stage(module, inputs, **params)`, `table(rows, types, tags)`.

- [ ] **Step 1: Write the failing test** `Tools/pypcg/tests/test_world_plumbing.py`

```python
from pypcg import dsl, ir, level, world as W
from pypcg.stages import s00_probe


def test_stage_table():
    assert [s[0] for s in W.STAGES] == list(range(1, 10))
    assert W.name(4) == "PCGW_04_Roads"
    assert W.asset(4) == "/Game/PyPCG/World/PCGW_04_Roads"
    assert W.volume_tag(4) == "PyWorld_W04"
    assert W.TERRAIN[3] == ("Intermediate", 2, 3)
    assert level.WORLD == W.LEVEL == "/Game/PyPCG/L_PyWorld"
    assert all(p.count(".") == 1 for p in W.MESH.values())


def test_slim_graph_takes_a_name():
    g = dsl.SlimGraph(s00_probe, name="PCGW_Test")
    assert g.name == "PCGW_Test"


def test_actor_points_node():
    g = dsl.Graph("T")
    n = g.actor_points("PyWorld_Location", "Get Locations")
    rec = n._rec
    assert rec["class"] == ir.SELF_NODE
    sel = rec["settings"]["ActorSelector"]
    assert rec["settings"]["Mode"] == "GetSinglePoint"
    assert sel["ActorSelectionTag"] == "PyWorld_Location" and sel["bSelectMultiple"] is True
```

- [ ] **Step 2: Run** `C:\Python314\python.exe -m pytest Tools/pypcg/tests/test_world_plumbing.py -q` — expect FAIL (`No module named pypcg.world`).

- [ ] **Step 3: Implement.** `Content/Python/pypcg/world/__init__.py`:

```python
"""PyWorld: the world-building pipeline of "Building Worlds with Houdini" (Ubisoft Paris) as nine PCG graphs with
Python nodes (docs/superpowers/specs/2026-10-22-pyworld-video-pipeline-design.md). No unreal import."""

STAGES = [
    (1, "PCGW_01_Terrain", "w01_terrain", "地形"),
    (2, "PCGW_02_Locations", "w02_locations", "地点"),
    (3, "PCGW_03_River", "w03_river", "河流"),
    (4, "PCGW_04_Roads", "w04_roads", "道路"),
    (5, "PCGW_05_Bridges", "w05_bridges", "桥"),
    (6, "PCGW_06_Settlements", "w06_settlements", "聚落"),
    (7, "PCGW_07_Vegetation", "w07_vegetation", "植被与岩石"),
    (8, "PCGW_08_Props", "w08_props", "沿路道具"),
    (9, "PCGW_09_Surface", "w09_surface", "地表材质"),
]
STAGE_BASE = 100                       # a world module's STAGE is 100 + n: apart from the city's 1..18
ASSET_DIR = "/Game/PyPCG/World/"
LEVEL = "/Game/PyPCG/L_PyWorld"
TEMPLATE = "/Game/PyPCG/L_PyCity"
VERTEX_CM = 585.9375                   # the mesh terrain's vertex spacing (docs/pypcg/stages/s01.md 0)
QUERY_BOX = {"X": 300000, "Y": 300000, "Z": 300000}
WORLD_HALF_CM = 100000.0               # the 2 km box the roads, settlements and props live in
SEA_Z = -600.0                         # the base terrain's height, under the template's ocean plane (-500)
ROAD_INNER = 600.0                     # a road corridor is flat to half width + this ...
ROAD_BLEND = 1000.0                    # ... and eases back to the ground over this
# stage -> (query type, query sub-priority, write sub-priority) of its mesh terrain read and write
TERRAIN = {1: ("Base", 0, 1), 3: ("Intermediate", 2, 3), 4: ("Intermediate", 4, 5), 6: ("Intermediate", 6, 7),
           9: ("Intermediate", 8, 9)}
CHANNELS = ("Grass", "Rock", "ForestFloor", "Dirt", "Mud", "Gravel")      # MPD_Basic's material channels
MPD_BASIC = "/PCGPrimitives_MeshPartitionInterop/Assets/MeshPartitionDefinitions/MPD_Basic"


def _p(pkg):
    return "%s.%s" % (pkg, pkg.rsplit("/", 1)[1])


_MP = "/CitySamplePCG/Megaplants/Tree_%s/Tree_%s_01/SM_%s_01_%s"
MESH = {
    "Cube": _p("/Engine/BasicShapes/Cube"), "Cylinder": _p("/Engine/BasicShapes/Cylinder"),
    "Cone": _p("/Engine/BasicShapes/Cone"), "Plane": _p("/Engine/BasicShapes/Plane"),
    "LaneCar": _p("/PCGPrimitives/Meshes/SM_Lane_Car_400_500"),            # X -250..250, Y -200..200, Z 0..20
    "Divider": _p("/PCGPrimitives/Meshes/SM_Lane_Divider_15_500"),         # X -250..250, Y -7.5..7.5
    "Path": _p("/PCGPrimitives/Meshes/SM_Lane_Path_300_160"),              # X -80..80, Y -150..150
    "Tile": _p("/PCGPrimitives/Meshes/SM_Square_150_150"),                 # X, Y -75..75, Z 0..20
    "Bench": _p("/PCGPrimitives/Meshes/SM_park_bench_N01"),                # X -114..114 (long), Z 0..95
    "Rail": _p("/Game/Megascans/3D_Assets/Modular_Rail_Guard_4m_00/Modular_Rail_Guard_4m_LOD0_uh1kbcxga"),  # X 0..420
    "Lamp": _p("/Game/Prop/Kit_StreetLamp_A/Mesh/SM_StreetLamp_A_Pole_Small"),  # Z 0..420, arm towards +X
    "MossyRock": _p("/Game/Megascans/3D_Assets/Mossy_Rock_ulldfii/S_Mossy_Rock_ulldfii_lod3_Var1"),
    "Boulder": _p("/PCGBiomeSample/Meshes/PCG_Boulder_01"),
    "Pine": _p("/PCGBiomeSample/Meshes/PCG_Pine_01"), "Spruce": _p("/PCGBiomeSample/Meshes/PCG_Spruce_01"),
    "YoungTree": _p("/PCGBiomeSample/Meshes/PCG_Tree_01"),
}
for _v in "ABCD":
    MESH["Alder" + _v] = _p(_MP % ("Black_Alder", "Black_Alder", "Black_Alder", _v))
    MESH["Hazel" + _v] = _p(_MP % ("Common_Hazel", "Common_Hazel", "Common_Hazel", _v))
    MESH["Beech" + _v] = _p(_MP % ("European_Beech", "European_Beech", "European_Beech", _v))
    MESH["Aspen" + _v] = _p(_MP % ("European_Aspen", "European_Aspen", "European_Aspen", _v))
    MESH["Maple" + _v] = _p("/CitySamplePCG/Megaplants/Tree_Norway_Maple/Tree_Norway_Maple_Forest_01/"
                            "SM_Norway_Maple_Forest_01_" + _v)
for _v in "abcdefgh":
    MESH["Birch" + _v] = _p("/Game/Prop/Kit_Tree_Birch/Mesh/SM_Tree_Birch_" + _v)
for _v in "ABDEFG":
    MESH["Grass" + _v] = _p("/CitySamplePCG/Megascans/Plants/Wild_Grass/Medium/StaticMeshes/SM_Grass_Var" + _v)
WATER_MATERIAL = "/Game/Prop/kit_ocean/Material/MI_ocean.MI_ocean"
GRAMMAR = _p("/PCGPrimitives/Grammar/DataAsset/Bldg_Advanced_Template/SGD_Bldg_B_Advance_Template")


def entry(n):
    for s in STAGES:
        if s[0] == n:
            return s
    raise KeyError("no world stage %r" % (n,))


def name(n):
    return entry(n)[1]


def module_name(n):
    return entry(n)[2]


def asset(n):
    return ASSET_DIR + name(n)


def volume_tag(n):
    return "PyWorld_W%02d" % n


def stage_number(module):
    return int(module.STAGE) - STAGE_BASE
```

`dsl.py` — `SlimGraph.__init__` signature becomes `def __init__(self, stage_module, extra_params=(), more_modules=(), name=None):` and its `super().__init__(stages.name(stage_module.STAGE), ...)` becomes `super().__init__(name or stages.name(stage_module.STAGE), ...)`. Add to `Graph`, after `self_point`:

```python
    def actor_points(self, tag, title="", **kw):
        """Get Actor Data: one point per level actor carrying `tag` -- its transform, bounds and an `ActorReference`
        attribute (Mode GetSinglePoint). The whole selector struct is written, as the exporter reads it back (trap 90)."""
        settings = {"Mode": "GetSinglePoint",
                    "ActorSelector": {"ActorFilter": "AllWorldActors", "bMustOverlapSelf": False,
                                      "bIncludeChildren": False, "IncludeIsolatedActors": "Ignore",
                                      "bDisableFilter": False, "ActorSelection": "ByTag", "ActorSelectionTag": tag,
                                      "ActorSelectionClass": "None", "ActorReferenceSelector": "PCGBegin(@Last)PCGEnd",
                                      "bSelectMultiple": True, "bIgnoreSelfAndChildren": False}}
        return self._add(_ir.SELF_NODE, title, settings, kw)
```

`level.py`: after `TOWN_GRAPHS`, add `WORLD = "/Game/PyPCG/L_PyWorld"                      # the PyWorld valley (pyworld.py)`.

`Tools/pypcg/tests/world_fixtures.py`:

```python
"""Small synthetic inputs for the PyWorld stage tests."""
from pypcg import stage_api
from pypcg.geo import Points
from pypcg.world import VERTEX_CM


def terrain(fn, half=40, s=VERTEX_CM):
    """A (2*half+1)^2 vertex lattice centred on the origin, z = fn(x, y), carrying SourcePositions like the
    engine's Extract_MeshTerrainPoints."""
    p = Points()
    p.declare("SourcePositions", "Vector")
    for j in range(-half, half + 1):
        for i in range(-half, half + 1):
            x, y = i * s, j * s
            p.add((x, y, float(fn(x, y))), SourcePositions=(x, y, -600.0))
    return p


class Surface:
    """Stands in for the engine's terrain surface (pypcg.ue.terrain.Terrain)."""

    def __init__(self, fn, half_cm=None):
        self.fn, self.half = fn, half_cm

    def height(self, x, y):
        if self.half is not None and (abs(x) > self.half or abs(y) > self.half):
            return None
        return float(self.fn(x, y))


def table(rows, types, tags=()):
    from pypcg.world import points as WP
    return (WP.table_points(rows, types), frozenset(tags))


def run_stage(module, inputs, **params):
    p = stage_api.defaults(module)
    p.update(params)
    for pin in module.INPUTS:
        inputs.setdefault(pin, [])
    outputs, ctx = stage_api.execute(module, inputs, p, None)
    return outputs, ctx
```

- [ ] **Step 4: Run** the test file — expect PASS; run the whole suite `C:\Python314\python.exe -m pytest Tools/pypcg/tests -q` — expect 762 + 3 passed, 18 skipped.
- [ ] **Step 5: Commit** `git add -A Content/Python/pypcg/world Content/Python/pypcg/dsl.py Content/Python/pypcg/level.py Tools/pypcg/tests/world_fixtures.py Tools/pypcg/tests/test_world_plumbing.py && git commit -m "PyWorld: stage table, constants and two DSL hooks"`

---

### Task 2: noise、grid、hydro

**Files:** Create `pypcg/world/noise.py`, `pypcg/world/grid.py`, `pypcg/world/hydro.py`, `Tools/pypcg/tests/test_world_field.py`

**Interfaces — Produces:**
- `noise.value(x, y, seed=0) -> float in [0,1]`; `noise.fbm(x, y, seed=0, octaves=5, lacunarity=2.0, gain=0.5) -> [-1,1]`; `noise.ridged(x, y, seed=0, octaves=4, ...) -> [0,1]`
- `grid.Lattice(n, s, x0, y0, z=None)`; `Lattice.from_locs(locs, s) -> (lat, ks)`; methods `copy()`, `k(i,j)`, `inside(i,j)`, `ij(x,y)`, `xy(k)`, `nearest(x,y) -> k|None`, `nearest_valid(x,y,reach=4) -> k|None`, `height(x,y) -> float|None`, `slope_deg(k) -> float`, `cells_in_box(x0,y0,x1,y1)` (yields k with z), `coarse(step, half) -> Lattice`
- `hydro.min_filter(lat, r) -> list`; `hydro.flow_accumulation(lat) -> list[int]`

- [ ] **Step 1: Failing tests** `Tools/pypcg/tests/test_world_field.py`

```python
import math

from pypcg.world import hydro, noise
from pypcg.world.grid import Lattice


def test_noise_ranges_and_determinism():
    vals = [noise.value(x * 0.37, x * 0.61, 3) for x in range(400)]
    assert 0.0 <= min(vals) and max(vals) <= 1.0
    assert noise.value(1.3, 2.7, 3) == noise.value(1.3, 2.7, 3) != noise.value(1.3, 2.7, 4)
    assert abs(noise.value(5.0, 5.0, 1) - noise.value(5.0 + 1e-7, 5.0, 1)) < 1e-5
    f = [noise.fbm(x * 0.13, -x * 0.29, 9) for x in range(400)]
    r = [noise.ridged(x * 0.13, x * 0.07, 9) for x in range(400)]
    assert -1.0 <= min(f) and max(f) <= 1.0 and 0.0 <= min(r) and max(r) <= 1.0


def _lat(fn, n=11, s=100.0):
    locs = [(i * s - 500.0, j * s - 500.0, fn(i * s - 500.0, j * s - 500.0)) for j in range(n) for i in range(n)]
    return Lattice.from_locs(locs, s)


def test_lattice_roundtrip_seams_and_height():
    locs = [(0.0, 0.0, 1.0), (100.0, 0.0, 2.0), (0.0, 100.0, 3.0), (100.0, 100.0, 4.0), (100.0, 0.0, 2.0)]
    lat, ks = Lattice.from_locs(locs, 100.0)
    assert lat.n == 2 and ks[1] == ks[4]
    assert lat.height(50.0, 50.0) == 2.5
    assert lat.height(500.0, 0.0) is None
    assert lat.xy(ks[3]) == (100.0, 100.0)


def test_slope_and_coarse():
    lat, _ = _lat(lambda x, y: 0.5 * x)
    k = lat.nearest(0.0, 0.0)
    assert abs(lat.slope_deg(k) - math.degrees(math.atan(0.5))) < 1e-9
    co = lat.coarse(2, 400.0)
    assert co.n == 5 and co.s == 200.0 and co.xy(co.nearest(0.0, 0.0)) == (0.0, 0.0)
    assert sum(1 for _ in lat.cells_in_box(-100.0, -100.0, 100.0, 100.0)) == 9


def test_min_filter_and_flow():
    lat, _ = _lat(lambda x, y: abs(x) + 0.01 * y)          # a V valley draining towards -y
    m = hydro.min_filter(lat, 1)
    k = lat.nearest(200.0, 0.0)
    assert m[k] == min(lat.z[lat.nearest(x, y)] for x in (100.0, 200.0, 300.0) for y in (-100.0, 0.0, 100.0))
    acc = hydro.flow_accumulation(lat)
    assert acc.index(max(acc)) == lat.nearest(0.0, -500.0)
```

- [ ] **Step 2: Run** — FAIL (missing modules).
- [ ] **Step 3: Implement.**

`noise.py`:

```python
"""Value noise for the world stages: deterministic in (x, y, seed), pure Python."""
import math


def _h(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFFFF) / 16777215.0


def value(x, y, seed=0):
    """Smooth value noise in [0, 1], one lattice cell per unit."""
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    u, v = fx * fx * (3.0 - 2.0 * fx), fy * fy * (3.0 - 2.0 * fy)
    a, b = _h(ix, iy, seed), _h(ix + 1, iy, seed)
    c, d = _h(ix, iy + 1, seed), _h(ix + 1, iy + 1, seed)
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v


def fbm(x, y, seed=0, octaves=5, lacunarity=2.0, gain=0.5):
    """Fractal sum of signed value noise, normalised to [-1, 1]."""
    total, amp, norm, f = 0.0, 1.0, 0.0, 1.0
    for o in range(octaves):
        total += amp * (2.0 * value(x * f, y * f, seed + 1013 * o) - 1.0)
        norm += amp
        amp *= gain
        f *= lacunarity
    return total / norm


def ridged(x, y, seed=0, octaves=4, lacunarity=2.0, gain=0.5):
    """Ridged fractal in [0, 1]: sharp crests where the signed noise crosses zero."""
    total, amp, norm, f = 0.0, 1.0, 0.0, 1.0
    for o in range(octaves):
        r = 1.0 - abs(2.0 * value(x * f, y * f, seed + 7919 * o) - 1.0)
        total += amp * r * r
        norm += amp
        amp *= gain
        f *= lacunarity
    return total / norm
```

`grid.py`:

```python
"""The mesh terrain's vertex lattice as a height field. The engine extracts the terrain as one point per vertex on a
585.9375 cm lattice (docs/pypcg/stages/s01.md 0); the sections' seams repeat a vertex, which maps to one cell here."""
import math


class Lattice:
    """n x n vertices, k = j * n + i at world (x0 + i * s, y0 + j * s); z[k] is None where there is no vertex."""

    def __init__(self, n, s, x0, y0, z=None):
        self.n, self.s, self.x0, self.y0 = int(n), float(s), float(x0), float(y0)
        self.z = list(z) if z is not None else [None] * (self.n * self.n)

    @classmethod
    def from_locs(cls, locs, s):
        """(lattice, ks): ks[i] is the cell of locs[i]."""
        if not locs:
            return cls(0, s, 0.0, 0.0), []
        x0, y0 = min(p[0] for p in locs), min(p[1] for p in locs)
        x1, y1 = max(p[0] for p in locs), max(p[1] for p in locs)
        n = int(round(max(x1 - x0, y1 - y0) / s)) + 1
        lat = cls(n, s, x0, y0)
        ks = []
        for p in locs:
            k = int(round((p[1] - y0) / s)) * n + int(round((p[0] - x0) / s))
            lat.z[k] = float(p[2])
            ks.append(k)
        return lat, ks

    def copy(self):
        return Lattice(self.n, self.s, self.x0, self.y0, self.z)

    def k(self, i, j):
        return j * self.n + i

    def inside(self, i, j):
        return 0 <= i < self.n and 0 <= j < self.n

    def ij(self, x, y):
        return int(round((x - self.x0) / self.s)), int(round((y - self.y0) / self.s))

    def xy(self, k):
        j, i = divmod(k, self.n)
        return self.x0 + i * self.s, self.y0 + j * self.s

    def nearest(self, x, y):
        i, j = self.ij(x, y)
        if not self.inside(i, j):
            return None
        k = j * self.n + i
        return k if self.z[k] is not None else None

    def nearest_valid(self, x, y, reach=4):
        """The closest cell with a vertex within `reach` cells of (x, y), or None (a point off the lattice)."""
        i0, j0 = self.ij(x, y)
        best = None
        for j in range(j0 - reach, j0 + reach + 1):
            for i in range(i0 - reach, i0 + reach + 1):
                if self.inside(i, j) and self.z[j * self.n + i] is not None:
                    d = (i - i0) ** 2 + (j - j0) ** 2
                    if best is None or d < best[0]:
                        best = (d, j * self.n + i)
        return best[1] if best else None

    def height(self, x, y):
        """Bilinear height, the nearest vertex's where a corner is missing, None off the lattice."""
        fx, fy = (x - self.x0) / self.s, (y - self.y0) / self.s
        i, j = math.floor(fx), math.floor(fy)
        n = self.n
        if 0 <= i < n - 1 and 0 <= j < n - 1:
            z = self.z
            a, b, c, d = z[j * n + i], z[j * n + i + 1], z[(j + 1) * n + i], z[(j + 1) * n + i + 1]
            if a is not None and b is not None and c is not None and d is not None:
                u, v = fx - i, fy - j
                return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
        k = self.nearest(x, y)
        return self.z[k] if k is not None else None

    def _at(self, i, j):
        return self.z[j * self.n + i] if self.inside(i, j) else None

    def slope_deg(self, k):
        j, i = divmod(k, self.n)
        z0 = self.z[k]
        if z0 is None:
            return 0.0

        def d(a, b, s):
            if a is not None and b is not None:
                return (b - a) / (2.0 * s)
            if b is not None:
                return (b - z0) / s
            if a is not None:
                return (z0 - a) / s
            return 0.0
        gx = d(self._at(i - 1, j), self._at(i + 1, j), self.s)
        gy = d(self._at(i, j - 1), self._at(i, j + 1), self.s)
        return math.degrees(math.atan(math.hypot(gx, gy)))

    def cells_in_box(self, x0, y0, x1, y1):
        n, s = self.n, self.s
        i0, i1 = max(0, math.ceil((x0 - self.x0) / s)), min(n - 1, math.floor((x1 - self.x0) / s))
        j0, j1 = max(0, math.ceil((y0 - self.y0) / s)), min(n - 1, math.floor((y1 - self.y0) / s))
        z = self.z
        for j in range(j0, j1 + 1):
            row = j * n
            for i in range(i0, i1 + 1):
                if z[row + i] is not None:
                    yield row + i

    def coarse(self, step, half):
        """Every step-th vertex with |x|, |y| <= half, aligned on the vertex at the origin, as a lattice of its own
        (the A* grids of the river and the roads)."""
        ci, cj = self.ij(0.0, 0.0)
        m = int(half // (self.s * step))
        n = 2 * m + 1
        out = Lattice(n, self.s * step, self.x0 + (ci - m * step) * self.s, self.y0 + (cj - m * step) * self.s)
        for b in range(n):
            for a in range(n):
                i, j = ci + (a - m) * step, cj + (b - m) * step
                if self.inside(i, j):
                    out.z[b * n + a] = self.z[j * self.n + i]
        return out
```

`hydro.py`:

```python
"""Field filters for the vegetation layers: a sliding-window minimum (the valley floor under a point) and D8 flow
accumulation (where water gathers: gullies and the river's banks)."""
import math
from collections import deque

_D8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def _min_line(vals, r):
    n = len(vals)
    out = [0.0] * n
    dq = deque()
    for i in range(n + r):
        if i < n:
            while dq and vals[dq[-1]] >= vals[i]:
                dq.pop()
            dq.append(i)
        c = i - r
        if c >= 0:
            while dq[0] < c - r:
                dq.popleft()
            out[c] = vals[dq[0]]
    return out


def min_filter(lat, r):
    """The minimum z over the (2r+1)^2 window around every vertex (separable), None where there is no vertex."""
    n, inf = lat.n, float("inf")
    rows = [_min_line([inf if z is None else z for z in lat.z[j * n:(j + 1) * n]], r) for j in range(n)]
    out = [None] * (n * n)
    for i in range(n):
        col = _min_line([rows[j][i] for j in range(n)], r)
        for j in range(n):
            if lat.z[j * n + i] is not None:
                out[j * n + i] = col[j]
    return out


def flow_accumulation(lat):
    """D8: every vertex passes its count (itself plus everything upstream) to its steepest lower neighbour."""
    n, z = lat.n, lat.z
    acc = [0 if v is None else 1 for v in z]
    for k in sorted((k for k, v in enumerate(z) if v is not None), key=lambda k: -z[k]):
        j, i = divmod(k, n)
        best, drop = None, 0.0
        for di, dj in _D8:
            ii, jj = i + di, j + dj
            if 0 <= ii < n and 0 <= jj < n:
                v = z[jj * n + ii]
                if v is not None:
                    d = (z[k] - v) / math.hypot(di, dj)
                    if d > drop:
                        best, drop = jj * n + ii, d
        if best is not None:
            acc[best] += acc[k]
    return acc
```

- [ ] **Step 4: Run** the test file — PASS.
- [ ] **Step 5: Commit** `git commit -m "PyWorld: noise, the vertex lattice and field filters"` (add the three modules and the test).

---

### Task 3: geom 与 A\*

**Files:** Create `pypcg/world/geom.py`, `pypcg/world/astar.py`, `Tools/pypcg/tests/test_world_geom.py`

**Interfaces — Produces:**
- `geom.dist2d(a,b)`, `length(pts)`, `cumulative(pts)`, `lerp(a,b,t)`, `at_distance(pts, cum, s) -> ((x,y), yaw_deg)`, `resample(pts, step)`, `chaikin(pts, iterations=2)`, `moving_average(vals, half)`, `yaw_deg(a,b)`, `seg_point(px,py,ax,ay,bx,by) -> (d,t)`
- `geom.SegmentIndex(cell=2000.0)`: `add(a,b,payload)`, `add_polyline(pts, payload)`, `nearest(x,y,maxd) -> (d, idx, t)|None`, `payload(idx)`, `segment(idx)`, `candidates(x0,y0,x1,y1)`
- `geom.polyline_intersections(P, Q) -> [(x, y, i, t, j, u)]`
- `geom.point_in_ring(x,y,ring)`, `rect(cx,cy,w,d,yaw_deg)` (w along yaw, CCW), `circle(cx,cy,r,n=24)`, `ring_distance(x,y,ring)`, `probe_points(ring, step)`, `rings_overlap(a,b)` (convex), `centroid(ring)`
- `geom.RingIndex(cell=3000.0)`: `add(ring, payload=None)`, `contains(x,y) -> payload|True|None`, `near(x,y,margin) -> bool`, `overlaps(ring) -> bool`, `rings`
- `astar.MOVES8`, `astar.MOVES16`, `astar.search(lat, starts: dict, goals: set, step_cost(ka,kb,L)->float|None, moves=MOVES8, h_scale=1.0) -> [k]|None`

- [ ] **Step 1: Failing tests** `Tools/pypcg/tests/test_world_geom.py`

```python
import math

from pypcg.world import astar, geom
from pypcg.world.grid import Lattice


def test_resample_chaikin_average():
    pts = geom.resample([(0.0, 0.0), (1000.0, 0.0)], 300.0)
    assert len(pts) == 5 and pts[-1] == (1000.0, 0.0) and abs(geom.dist2d(pts[0], pts[1]) - 250.0) < 1e-9
    c = geom.chaikin([(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)], 1)
    assert c[0] == (0.0, 0.0) and c[-1] == (100.0, 100.0) and len(c) == 6
    assert geom.moving_average([0.0, 0.0, 3.0, 0.0, 0.0], 1)[2] == 1.0
    (x, y), yaw = geom.at_distance([(0.0, 0.0), (0.0, 100.0)], [0.0, 100.0], 40.0)
    assert (x, y) == (0.0, 40.0) and yaw == 90.0


def test_segment_index_and_intersections():
    idx = geom.SegmentIndex(500.0)
    idx.add_polyline([(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0)], 7)
    d, i, t = idx.nearest(500.0, 30.0, 100.0)
    assert abs(d - 30.0) < 1e-9 and idx.payload(i) == 7 and abs(t - 0.5) < 1e-9
    assert idx.nearest(500.0, 300.0, 100.0) is None
    hits = geom.polyline_intersections([(0.0, -50.0), (0.0, 50.0)], [(-50.0, 0.0), (50.0, 0.0)])
    assert len(hits) == 1 and abs(hits[0][0]) < 1e-9 and abs(hits[0][3] - 0.5) < 1e-9


def test_rects_rings():
    r = geom.rect(0.0, 0.0, 400.0, 200.0, 90.0)
    xs, ys = [p[0] for p in r], [p[1] for p in r]
    assert abs(max(ys) - 200.0) < 1e-9 and abs(max(xs) - 100.0) < 1e-9
    area = 0.5 * sum(r[i][0] * r[(i + 1) % 4][1] - r[(i + 1) % 4][0] * r[i][1] for i in range(4))
    assert area > 0
    assert geom.point_in_ring(0.0, 150.0, r) and not geom.point_in_ring(150.0, 0.0, r)
    assert geom.rings_overlap(r, geom.rect(0.0, 190.0, 50.0, 50.0, 0.0))
    assert not geom.rings_overlap(r, geom.rect(0.0, 300.0, 50.0, 50.0, 0.0))
    ri = geom.RingIndex(1000.0)
    ri.add(r, "a")
    assert ri.contains(0.0, 0.0) == "a" and ri.near(130.0, 0.0, 40.0) and not ri.near(200.0, 0.0, 40.0)
    assert ri.overlaps(geom.rect(80.0, 0.0, 50.0, 50.0, 0.0))


def test_astar_prefers_cheap_and_reaches_any_goal():
    lat = Lattice(9, 100.0, 0.0, 0.0, [0.0] * 81)
    wall = {lat.k(4, j) for j in range(0, 8)}

    def cost(a, b, L):
        return None if b in wall else L
    path = astar.search(lat, {lat.k(0, 0): 0.0}, {lat.k(8, 0)}, cost, astar.MOVES8)
    assert path[0] == lat.k(0, 0) and path[-1] == lat.k(8, 0) and lat.k(4, 8) in path
    multi = astar.search(lat, {lat.k(0, 0): 0.0}, {lat.k(2, 0), lat.k(0, 7)}, cost, astar.MOVES16, h_scale=0.0)
    assert multi[-1] == lat.k(2, 0)
    assert astar.search(lat, {lat.k(0, 0): 0.0}, {lat.k(8, 0)}, lambda a, b, L: None) is None
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `geom.py`:

```python
"""2D geometry for the world stages: polylines, a bucketed segment index, intersections, rectangles and a ring index."""
import bisect
import math


def dist2d(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def length(pts):
    return sum(dist2d(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def cumulative(pts):
    out = [0.0]
    for i in range(1, len(pts)):
        out.append(out[-1] + dist2d(pts[i - 1], pts[i]))
    return out


def lerp(a, b, t):
    return tuple(a[c] + (b[c] - a[c]) * t for c in range(len(a)))


def yaw_deg(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def at_distance(pts, cum, s):
    """((x, y), yaw) at arc length s along pts (clamped)."""
    s = min(max(s, 0.0), cum[-1])
    i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(pts) - 2)
    span = cum[i + 1] - cum[i]
    t = 0.0 if span == 0 else (s - cum[i]) / span
    p = lerp(pts[i][:2], pts[i + 1][:2], t)
    return (p[0], p[1]), yaw_deg(pts[i], pts[i + 1])


def resample(pts, step):
    """Evenly spaced points (spacing <= step) from the first to the last; every coordinate is interpolated."""
    pts = [tuple(p) for p in pts]
    if len(pts) < 2:
        return pts
    cum = cumulative(pts)
    total = cum[-1]
    if total == 0:
        return [pts[0]]
    m = max(1, int(math.ceil(total / step)))
    out, seg = [], 0
    for q in range(m + 1):
        s = total * q / m
        while seg < len(pts) - 2 and cum[seg + 1] < s:
            seg += 1
        span = cum[seg + 1] - cum[seg]
        t = 0.0 if span == 0 else (s - cum[seg]) / span
        out.append(lerp(pts[seg], pts[seg + 1], min(1.0, max(0.0, t))))
    return out


def chaikin(pts, iterations=2):
    """Corner cutting that keeps both end points."""
    pts = [tuple(p) for p in pts]
    for _ in range(iterations):
        if len(pts) < 3:
            return pts
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out.append(lerp(a, b, 0.25))
            out.append(lerp(a, b, 0.75))
        out.append(pts[-1])
        pts = out
    return pts


def moving_average(vals, half):
    n = len(vals)
    pre = [0.0]
    for v in vals:
        pre.append(pre[-1] + v)
    out = []
    for i in range(n):
        a, b = max(0, i - half), min(n, i + half + 1)
        out.append((pre[b] - pre[a]) / (b - a))
    return out


def seg_point(px, py, ax, ay, bx, by):
    """(distance, t) from (px, py) to the segment a-b, t the parameter of the closest point."""
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else min(1.0, max(0.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)), t


class SegmentIndex:
    """Segments bucketed on a uniform grid, for nearest-segment queries within a radius."""

    def __init__(self, cell=2000.0):
        self.cell = float(cell)
        self.segs = []
        self.buckets = {}

    def add(self, a, b, payload=None):
        idx = len(self.segs)
        self.segs.append((a[0], a[1], b[0], b[1], payload))
        c = self.cell
        for bx in range(math.floor(min(a[0], b[0]) / c), math.floor(max(a[0], b[0]) / c) + 1):
            for by in range(math.floor(min(a[1], b[1]) / c), math.floor(max(a[1], b[1]) / c) + 1):
                self.buckets.setdefault((bx, by), []).append(idx)
        return idx

    def add_polyline(self, pts, payload=None):
        for i in range(len(pts) - 1):
            self.add(pts[i], pts[i + 1], payload)

    def payload(self, idx):
        return self.segs[idx][4]

    def segment(self, idx):
        s = self.segs[idx]
        return (s[0], s[1]), (s[2], s[3])

    def candidates(self, x0, y0, x1, y1):
        c, seen = self.cell, set()
        for bx in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for by in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                for idx in self.buckets.get((bx, by), ()):
                    if idx not in seen:
                        seen.add(idx)
                        yield idx

    def nearest(self, x, y, maxd):
        best = None
        for idx in self.candidates(x - maxd, y - maxd, x + maxd, y + maxd):
            ax, ay, bx, by, _ = self.segs[idx]
            d, t = seg_point(x, y, ax, ay, bx, by)
            if d <= maxd and (best is None or d < best[0]):
                best = (d, idx, t)
        return best


def seg_intersect(a, b, c, d):
    rx, ry, sx, sy = b[0] - a[0], b[1] - a[1], d[0] - c[0], d[1] - c[1]
    den = rx * sy - ry * sx
    if abs(den) < 1e-12:
        return None
    qx, qy = c[0] - a[0], c[1] - a[1]
    t, u = (qx * sy - qy * sx) / den, (qx * ry - qy * rx) / den
    return (t, u) if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0 else None


def polyline_intersections(P, Q, merge_cm=100.0):
    """[(x, y, i, t, j, u)]: P's segment i at t crosses Q's segment j at u; hits closer than merge_cm are one."""
    idx = SegmentIndex(2000.0)
    for j in range(len(Q) - 1):
        idx.add(Q[j], Q[j + 1], j)
    out = []
    for i in range(len(P) - 1):
        a, b = P[i], P[i + 1]
        for s in idx.candidates(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])):
            c, d = idx.segment(s)
            hit = seg_intersect(a, b, c, d)
            if hit is None:
                continue
            x, y = a[0] + (b[0] - a[0]) * hit[0], a[1] + (b[1] - a[1]) * hit[0]
            if all(math.hypot(x - o[0], y - o[1]) > merge_cm for o in out):
                out.append((x, y, i, hit[0], idx.payload(s), hit[1]))
    return out


def point_in_ring(x, y, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        (ax, ay), (bx, by) = ring[i], ring[(i + 1) % n]
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


def rect(cx, cy, w, d, yaw):
    """The w x d rectangle centred on (cx, cy), w along the yaw direction, counter-clockwise."""
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    hw, hd = 0.5 * w, 0.5 * d
    return [(cx + c * a - s * b, cy + s * a + c * b) for a, b in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))]


def circle(cx, cy, r, n=24):
    return [(cx + r * math.cos(2 * math.pi * q / n), cy + r * math.sin(2 * math.pi * q / n)) for q in range(n)]


def centroid(ring):
    return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)


def ring_distance(x, y, ring):
    n = len(ring)
    return min(seg_point(x, y, ring[i][0], ring[i][1], ring[(i + 1) % n][0], ring[(i + 1) % n][1])[0]
               for i in range(n))


def probe_points(ring, step):
    """The ring's boundary every `step` (corners included) and its centroid: what a plot checks for clearance."""
    out = [centroid(ring)]
    n = len(ring)
    for i in range(n):
        a, b = ring[i], ring[(i + 1) % n]
        m = max(1, int(math.ceil(dist2d(a, b) / step)))
        out.extend(lerp(a, b, q / m) for q in range(m))
    return out


def _bbox(ring):
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def rings_overlap(a, b):
    """Separating axis test for two convex rings."""
    for ring in (a, b):
        n = len(ring)
        for i in range(n):
            ex, ey = ring[(i + 1) % n][0] - ring[i][0], ring[(i + 1) % n][1] - ring[i][1]
            ax, ay = -ey, ex
            pa = [p[0] * ax + p[1] * ay for p in a]
            pb = [p[0] * ax + p[1] * ay for p in b]
            if max(pa) < min(pb) or max(pb) < min(pa):
                return False
    return True


class RingIndex:
    """Convex rings bucketed by bounding box: containment, nearness and overlap queries."""

    def __init__(self, cell=3000.0):
        self.cell = float(cell)
        self.rings, self.payloads, self.boxes = [], [], []
        self.buckets = {}

    def add(self, ring, payload=None):
        idx = len(self.rings)
        self.rings.append(list(ring))
        self.payloads.append(payload)
        box = _bbox(ring)
        self.boxes.append(box)
        c = self.cell
        for bx in range(math.floor(box[0] / c), math.floor(box[2] / c) + 1):
            for by in range(math.floor(box[1] / c), math.floor(box[3] / c) + 1):
                self.buckets.setdefault((bx, by), []).append(idx)
        return idx

    def _cands(self, x0, y0, x1, y1):
        c, seen = self.cell, set()
        for bx in range(math.floor(x0 / c), math.floor(x1 / c) + 1):
            for by in range(math.floor(y0 / c), math.floor(y1 / c) + 1):
                for idx in self.buckets.get((bx, by), ()):
                    if idx not in seen:
                        seen.add(idx)
                        yield idx

    def contains(self, x, y):
        for idx in self._cands(x, y, x, y):
            if point_in_ring(x, y, self.rings[idx]):
                p = self.payloads[idx]
                return True if p is None else p
        return None

    def near(self, x, y, margin):
        for idx in self._cands(x - margin, y - margin, x + margin, y + margin):
            ring = self.rings[idx]
            if point_in_ring(x, y, ring) or ring_distance(x, y, ring) <= margin:
                return True
        return False

    def overlaps(self, ring):
        x0, y0, x1, y1 = _bbox(ring)
        return any(rings_overlap(ring, self.rings[i]) for i in self._cands(x0, y0, x1, y1))
```

`astar.py`:

```python
"""A* on a Lattice. The video's trick for roads that follow the terrain: search more directions than the eight
grid neighbours (MOVES16 adds the knight moves), so paths are not forced into 45-degree zigzags."""
import heapq
import math

MOVES8 = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
MOVES16 = MOVES8 + [(1, 2), (2, 1), (-1, 2), (-2, 1), (1, -2), (2, -1), (-1, -2), (-2, -1)]


def search(lat, starts, goals, step_cost, moves=MOVES8, h_scale=1.0):
    """starts {k: initial cost}, goals {k}; step_cost(ka, kb, length_cm) -> cost or None (blocked). The heuristic is
    h_scale x the straight distance to the nearest goal (only with <= 8 goals; 0 turns it off): keep h_scale at or
    below the cheapest cost per cm for an optimal path. Returns the cells start .. goal, or None."""
    goals = set(goals)
    if not goals:
        return None
    n = lat.n
    gxy = [lat.xy(k) for k in goals] if h_scale > 0 and len(goals) <= 8 else None

    def h(k):
        if not gxy:
            return 0.0
        x, y = lat.xy(k)
        return h_scale * min(math.hypot(x - gx, y - gy) for gx, gy in gxy)

    inf = float("inf")
    g, came, heap, done = {}, {}, [], set()
    for k, g0 in starts.items():
        if k is not None and lat.z[k] is not None:
            g[k] = g0
            heapq.heappush(heap, (g0 + h(k), g0, k))
    steps = [(di, dj, lat.s * math.hypot(di, dj)) for di, dj in moves]
    while heap:
        _f, gk, k = heapq.heappop(heap)
        if k in done or gk > g.get(k, inf):
            continue
        if k in goals:
            path = [k]
            while path[-1] in came:
                path.append(came[path[-1]])
            return path[::-1]
        done.add(k)
        j, i = divmod(k, n)
        for di, dj, length in steps:
            ii, jj = i + di, j + dj
            if not (0 <= ii < n and 0 <= jj < n):
                continue
            kk = jj * n + ii
            if lat.z[kk] is None or kk in done:
                continue
            c = step_cost(k, kk, length)
            if c is None:
                continue
            ng = gk + c
            if ng < g.get(kk, inf):
                g[kk], came[kk] = ng, k
                heapq.heappush(heap, (ng + h(kk), ng, kk))
    return None
```

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `"PyWorld: 2D geometry and A* (16 directions)"`.

---

### Task 4: terraform、points、layout

**Files:** Create `pypcg/world/terraform.py`, `pypcg/world/points.py`, `pypcg/world/layout.py`, `Tools/pypcg/tests/test_world_terraform.py`

**Interfaces — Produces:**
- `terraform.smoothstep(e0,e1,x)`; `carve_river(lat, samples[(x,y,water,width)], depth=150, bank_slope=0.5, reach=2000) -> int`; `flatten_corridor(lat, samples[(x,y,z,hw,skip)], inner=ROAD_INNER, blend=ROAD_BLEND) -> int`; `fit_plane(lat,cx,cy,r,max_slope_deg=4.0) -> (a,b,c)`; `plane_z(plane,cx,cy,x,y)`; `platform(lat,cx,cy,r,plane,keep=None,core=0.75,outer=1.15) -> int`; `pad(lat, ring, z, margin=200, blend=400) -> int`
- `points.MESH_ATTR = "Mesh"`; `copy_points(p)`; `with_heights(src, lat, ks, attrs=None)`; `mesh_points(rows[(loc,rot,scale,mesh)])`; `table_points(rows, types)`; `rows_of(points)`; `summary(values) -> ParamSet`; `values_tagged(inputs, pin, tag)`
- `layout.FLOOR`, `floor_z(y)`, `axis_x(y)`, `valley_points(step)`, `LOCATIONS[(name,x,y,radius)]`, `RIVER_ENDS[(name,x,y)]`, `ROAD_EXITS[(name,x,y)]`, tags `TAG_VALLEY`, `TAG_LOCATION`, `TAG_RIVER_END`, `TAG_EXIT`

- [ ] **Step 1: Failing tests** `Tools/pypcg/tests/test_world_terraform.py`

```python
from pypcg.geo import ParamSet, Points
from pypcg.world import WORLD_HALF_CM, layout as L, points as WP, terraform as T
from pypcg.world.grid import Lattice


def _flat(z=1000.0, n=41, s=100.0):
    return Lattice(n, s, -2000.0, -2000.0, [z] * (n * n))


def test_carve_only_lowers_and_reaches_bed():
    lat = _flat()
    river = [(-2000.0, 0.0, 900.0, 600.0), (2000.0, 0.0, 900.0, 600.0)]
    n = T.carve_river(lat, river, depth=150.0)
    assert n > 0 and abs(lat.z[lat.nearest(0.0, 0.0)] - 750.0) < 1e-9
    assert lat.z[lat.nearest(0.0, 1900.0)] == 1000.0 and max(v for v in lat.z) == 1000.0


def test_corridor_flattens_and_skips_bridges():
    lat = _flat()
    T.flatten_corridor(lat, [(-2000.0, 0.0, 1200.0, 300.0, False), (0.0, 0.0, 1200.0, 300.0, False)], 100.0, 300.0)
    assert lat.z[lat.nearest(-1000.0, 300.0)] == 1200.0
    assert lat.z[lat.nearest(-1000.0, 1000.0)] == 1000.0
    lat2 = _flat()
    T.flatten_corridor(lat2, [(-2000.0, 0.0, 1200.0, 300.0, True), (0.0, 0.0, 1200.0, 300.0, True)])
    assert max(lat2.z) == 1000.0


def test_plane_fit_is_clamped_and_platform_pad():
    lat = Lattice(41, 100.0, -2000.0, -2000.0, [0.0] * 1681)
    for k in range(1681):
        lat.z[k] = 0.5 * lat.xy(k)[0]
    a, b, c = T.fit_plane(lat, 0.0, 0.0, 1000.0, 4.0)
    assert abs(a - 0.0699268119) < 1e-6 and abs(b) < 1e-12 and abs(c) < 1e-6
    T.platform(lat, 0.0, 0.0, 1000.0, (a, b, c))
    assert abs(lat.z[lat.nearest(500.0, 0.0)] - a * 500.0) < 1e-9
    ring = [(-100.0, -100.0), (100.0, -100.0), (100.0, 100.0), (-100.0, 100.0)]
    T.pad(lat, ring, 77.0)
    assert lat.z[lat.nearest(0.0, 0.0)] == 77.0 and lat.z[lat.nearest(300.0, 0.0)] == 77.0


def test_points_helpers():
    src = Points()
    src.declare("SourcePositions", "Vector")
    src.add((0.0, 0.0, 5.0), SourcePositions=(0.0, 0.0, -600.0))
    lat, ks = Lattice.from_locs(src.loc, 100.0)
    lat.z[ks[0]] = 9.0
    out = WP.with_heights(src, lat, ks, {"Mountain": ("Double", [0.5])})
    assert out.loc[0] == (0.0, 0.0, 9.0) and out.attrs["SourcePositions"][0] == (0.0, 0.0, -600.0)
    assert out.attrs["Mountain"] == [0.5] and src.loc[0][2] == 5.0
    m = WP.mesh_points([((1.0, 2.0, 3.0), (0.0, 90.0, 0.0), (2.0, 2.0, 2.0), "/A/B.B")])
    assert m.types[WP.MESH_ATTR] == "SoftObjectPath" and m.attrs["Mesh"] == ["/A/B.B"] and m.rot[0][1] == 90.0
    t = WP.table_points([{"loc": (0.0, 0.0, 0.0), "Kind": "Town", "Radius": 1.0}], {"Kind": "String", "Radius": "Double"})
    assert WP.rows_of(t)[0]["Kind"] == "Town"
    s = WP.summary({"a": 1, "b": 2.0, "c": True, "d": "x"})
    assert isinstance(s, ParamSet) and s.types == {"a": "Int32", "b": "Double", "c": "Bool", "d": "String"}


def test_layout_is_inside_the_world():
    pts = L.valley_points()
    assert all(b[1] > a[1] for a, b in zip(pts, pts[1:]))
    assert L.floor_z(-150000.0) == -800.0 and L.floor_z(0.0) == 2500.0
    for _n, x, y, r in L.LOCATIONS:
        assert abs(x) + r < WORLD_HALF_CM and abs(y) + r < WORLD_HALF_CM
    assert len(L.LOCATIONS) == 5 and len(L.RIVER_ENDS) == 2 and len(L.ROAD_EXITS) == 2
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `terraform.py`:

```python
"""Terrain edits on a Lattice (视频：河道下切、路基、平台、垫平). Each returns how many vertices it changed."""
import math

from . import ROAD_BLEND, ROAD_INNER, geom


def smoothstep(e0, e1, x):
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def _index(samples):
    idx = geom.SegmentIndex(2000.0)
    for a in range(len(samples) - 1):
        idx.add(samples[a], samples[a + 1], a)
    return idx


def _box(samples, reach):
    return (min(s[0] for s in samples) - reach, min(s[1] for s in samples) - reach,
            max(s[0] for s in samples) + reach, max(s[1] for s in samples) + reach)


def carve_river(lat, samples, depth=150.0, bank_slope=0.5, reach=2000.0):
    """samples [(x, y, water_z, width)]. Inside half the width the bed is a parabola `depth` below the water at the
    centre line; outside, the bank rises from the water line at `bank_slope`. A vertex only ever goes down."""
    if len(samples) < 2:
        return 0
    idx = _index(samples)
    far = 0.5 * max(s[3] for s in samples) + reach
    changed = 0
    for k in list(lat.cells_in_box(*_box(samples, far))):
        x, y = lat.xy(k)
        hit = idx.nearest(x, y, far)
        if hit is None:
            continue
        d, a, t = hit
        s0, s1 = samples[a], samples[a + 1]
        water = s0[2] + (s1[2] - s0[2]) * t
        half = 0.5 * (s0[3] + (s1[3] - s0[3]) * t)
        if d > half + reach:
            continue
        target = water - depth * (1.0 - (d / half) ** 2) if d <= half else water + bank_slope * (d - half)
        if target < lat.z[k]:
            lat.z[k] = target
            changed += 1
    return changed


def flatten_corridor(lat, samples, inner=ROAD_INNER, blend=ROAD_BLEND):
    """samples [(x, y, z, half_width, skip)] along one road: flat at the road's height to half width + inner, eased
    back to the ground over `blend`; a segment with a skipped end (a bridge span) leaves the ground alone."""
    if len(samples) < 2:
        return 0
    idx = _index(samples)
    far = max(s[3] for s in samples) + inner + blend
    changed = 0
    for k in list(lat.cells_in_box(*_box(samples, far))):
        x, y = lat.xy(k)
        hit = idx.nearest(x, y, far)
        if hit is None:
            continue
        d, a, t = hit
        s0, s1 = samples[a], samples[a + 1]
        if s0[4] or s1[4]:
            continue
        hw = s0[3] + (s1[3] - s0[3]) * t
        w = 1.0 if d <= hw + inner else 1.0 - smoothstep(hw + inner, hw + inner + blend, d)
        if w <= 0.0:
            continue
        zr = s0[2] + (s1[2] - s0[2]) * t
        lat.z[k] = lat.z[k] + (zr - lat.z[k]) * w
        changed += 1
    return changed


def fit_plane(lat, cx, cy, r, max_slope_deg=4.0):
    """Least-squares plane z = a (x - cx) + b (y - cy) + c over the vertices within r, its slope clamped."""
    pts = []
    for k in lat.cells_in_box(cx - r, cy - r, cx + r, cy + r):
        x, y = lat.xy(k)
        if math.hypot(x - cx, y - cy) <= r:
            pts.append((x - cx, y - cy, lat.z[k]))
    if not pts:
        h = lat.height(cx, cy)
        return 0.0, 0.0, (h if h is not None else 0.0)
    n = float(len(pts))
    mx, my, mz = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n, sum(p[2] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    syy = sum((p[1] - my) ** 2 for p in pts)
    sxy = sum((p[0] - mx) * (p[1] - my) for p in pts)
    sxz = sum((p[0] - mx) * (p[2] - mz) for p in pts)
    syz = sum((p[1] - my) * (p[2] - mz) for p in pts)
    det = sxx * syy - sxy * sxy
    a, b = (0.0, 0.0) if abs(det) < 1e-9 else ((sxz * syy - syz * sxy) / det, (syz * sxx - sxz * sxy) / det)
    g, lim = math.hypot(a, b), math.tan(math.radians(max_slope_deg))
    if g > lim:
        a, b = a * lim / g, b * lim / g
    return a, b, mz - a * mx - b * my


def plane_z(plane, cx, cy, x, y):
    return plane[0] * (x - cx) + plane[1] * (y - cy) + plane[2]


def platform(lat, cx, cy, r, plane, keep=None, core=0.75, outer=1.15):
    """Pull the ground to the plane: fully inside core x r, easing out by outer x r; keep(x, y) in 0..1 scales it
    (1 = full platform, 0 = leave alone: roads and the river)."""
    changed = 0
    for k in list(lat.cells_in_box(cx - outer * r, cy - outer * r, cx + outer * r, cy + outer * r)):
        x, y = lat.xy(k)
        w = 1.0 - smoothstep(core * r, outer * r, math.hypot(x - cx, y - cy))
        if keep is not None and w > 0.0:
            w *= keep(x, y)
        if w <= 0.0:
            continue
        lat.z[k] = lat.z[k] + (plane_z(plane, cx, cy, x, y) - lat.z[k]) * w
        changed += 1
    return changed


def pad(lat, ring, z, margin=200.0, blend=400.0):
    """Level the ground at z under a footprint ring and `margin` around it, easing out over `blend`."""
    reach = margin + blend
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    changed = 0
    for k in list(lat.cells_in_box(min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach)):
        x, y = lat.xy(k)
        d = 0.0 if geom.point_in_ring(x, y, ring) else geom.ring_distance(x, y, ring)
        w = 1.0 if d <= margin else 1.0 - smoothstep(margin, reach, d)
        if w <= 0.0:
            continue
        lat.z[k] = lat.z[k] + (z - lat.z[k]) * w
        changed += 1
    return changed
```

`points.py`:

```python
"""Point-set helpers for the world stages (pypcg.geo values only)."""
from pypcg.geo import ParamSet, Points

MESH_ATTR = "Mesh"         # what the graphs' Spawn_Assets read (UseMeshAttribute, MeshAttribute "Mesh")


def copy_points(p):
    out = Points()
    for c in Points.COLUMNS:
        setattr(out, c, list(getattr(p, c)))
    out.attrs = {k: list(v) for k, v in p.attrs.items()}
    out.types = dict(p.types)
    out.quat = list(p.quat) if getattr(p, "quat", None) else None
    return out


def with_heights(src, lat, ks, attrs=None):
    """src with every point's z taken from its lattice cell (x, y and every attribute -- SourcePositions above all,
    which the terrain writer uses to find the vertex -- unchanged), plus attrs {name: (type, column)}."""
    out = copy_points(src)
    out.loc = [(p[0], p[1], lat.z[k]) for p, k in zip(src.loc, ks)]
    for name, (tname, col) in (attrs or {}).items():
        out.attrs[name] = list(col)
        out.types[name] = tname
    return out


def mesh_points(rows):
    """rows [(loc, rot (pitch, yaw, roll), scale, mesh path)] -> Points carrying each point's mesh."""
    p = Points()
    p.declare(MESH_ATTR, "SoftObjectPath")
    for loc, rot, scale, mesh in rows:
        p.add(tuple(float(v) for v in loc), rot=tuple(float(v) for v in rot), scale=tuple(float(v) for v in scale),
              **{MESH_ATTR: mesh})
    return p


def table_points(rows, types):
    """rows [{"loc": (x, y, z), name: value, ...}] -> one point per row with the attributes `types` declares."""
    p = Points()
    for name, tname in types.items():
        p.declare(name, tname)
    for r in rows:
        p.add(tuple(float(v) for v in r["loc"]), **{k: r[k] for k in types})
    return p


def rows_of(points):
    return [dict({"loc": points.loc[i]}, **{n: col[i] for n, col in points.attrs.items()}) for i in range(len(points))]


def _type(v):
    if isinstance(v, bool):
        return "Bool"
    if isinstance(v, int):
        return "Int32"
    if isinstance(v, float):
        return "Double"
    return "String"


def summary(values):
    """The stage's Summary (read by pyworld.py from the run record): scalars only."""
    return ParamSet(dict(values), {k: _type(v) for k, v in values.items()})


def values_tagged(inputs, pin, tag):
    return [v for v, tags in inputs.get(pin, []) if tag in tags]
```

`layout.py`:

```python
"""The valley's control layout: what `pyworld.py layout` writes into L_PyWorld as level actors (spec 2.2).
x, y, radius in cm; the valley axis's control points carry the floor height in z."""
import math

TAG_VALLEY = "PyWorld_Valley"
TAG_LOCATION = "PyWorld_Location"
TAG_RIVER_END = "PyWorld_RiverEnd"
TAG_EXIT = "PyWorld_RoadExit"

FLOOR = [(-150000.0, -800.0), (-120000.0, 0.0), (-100000.0, 600.0), (0.0, 2500.0), (100000.0, 6000.0),
         (150000.0, 12000.0)]                        # (y, floor z): the valley opens to the sea in the south
AXIS_AMPLITUDE = 8000.0
AXIS_WAVELENGTH = 60000.0

LOCATIONS = [("Town", 14000.0, -30000.0, 22000.0), ("VillageNorth", -15000.0, 42000.0, 14000.0),
             ("VillageEast", 22000.0, 78000.0, 12000.0), ("HamletSouth", -18000.0, -72000.0, 7000.0),
             ("HamletWest", -32000.0, 8000.0, 7000.0)]
RIVER_ENDS = [("RiverSource", -2000.0, 99000.0), ("RiverOutlet", -8000.0, -135000.0)]
ROAD_EXITS = [("ExitSouth", 8000.0, -99000.0), ("ExitNorth", 25000.0, 99000.0)]


def floor_z(y):
    if y <= FLOOR[0][0]:
        return FLOOR[0][1]
    for (y0, z0), (y1, z1) in zip(FLOOR, FLOOR[1:]):
        if y <= y1:
            return z0 + (z1 - z0) * (y - y0) / (y1 - y0)
    return FLOOR[-1][1]


def axis_x(y):
    return AXIS_AMPLITUDE * math.sin(y / AXIS_WAVELENGTH)


def valley_points(step=12500.0):
    n = int(round(300000.0 / step))
    return [(axis_x(-150000.0 + q * step), -150000.0 + q * step, floor_z(-150000.0 + q * step)) for q in range(n + 1)]
```

- [ ] **Step 4: Run** — PASS. (`fit_plane` check: tan 4° = 0.0699268119.) **Step 5: Commit** `"PyWorld: terrain edits, point helpers and the valley layout"`.

---
### Task 5: W1 地形（`w01_terrain`）

**Files:** Create `Content/Python/pypcg/stages/w01_terrain.py`, `Tools/pypcg/tests/test_world_w01.py`

**Interfaces:**
- Consumes: `noise`, `grid.Lattice`, `points.with_heights/summary`, `terraform.smoothstep`, `SEA_Z`, `VERTEX_CM`.
- Produces: stage module (`STAGE 101`, `INPUTS {"MeshTerrain": points, "Valley": spline}`, `OUTPUTS ("Terrain", "Summary")`); `Terrain` carries a Double attribute `Mountain` (0 floor .. 1 walls) for the native erosion's `MaskAttribute`. Functions `axis_table(items)`, `axis_at(table, y) -> (x, floor_z)`, `height(x, y, table, p, seed) -> (z, mountain)`. Summary keys: `points`, `ridge_max_cm`, `floor_err_max_cm`, `nan`.

- [ ] **Step 1: Failing test** `Tools/pypcg/tests/test_world_w01.py`

```python
import math

from pypcg.geo import Spline
from pypcg.stages import w01_terrain as S
from world_fixtures import run_stage, terrain

VALLEY = [(Spline([(0.0, -30000.0, 1000.0), (0.0, 30000.0, 1000.0)], linear=True), frozenset(["PyWorld_Valley"]))]
SMALL = dict(FloorHalfWidth=3000.0, WallWidth=8000.0, RidgeHeight=6000.0, EdgeStart=18000.0, EdgeEnd=23000.0)


def _run(**p):
    src = terrain(lambda x, y: -600.0)
    out, _ = run_stage(S, {"MeshTerrain": [(src, frozenset())], "Valley": VALLEY}, **p)
    return src, out


def test_shape_keeps_vertices_and_rises_from_the_floor():
    src, out = _run(**SMALL)
    t = out["Terrain"][0][0]
    assert len(t) == len(src) and t.attrs["SourcePositions"] == src.attrs["SourcePositions"]
    assert [p[:2] for p in t.loc] == [p[:2] for p in src.loc]
    z = {(round(p[0]), round(p[1])): p[2] for p in t.loc}
    m = t.attrs["Mountain"]
    assert 0.0 <= min(m) and max(m) <= 1.0 and t.types["Mountain"] == "Double"
    assert abs(z[(0, 0)] - 1000.0) < 300.0
    assert z[(11719, 0)] > z[(0, 0)] + 2500.0
    assert abs(z[(23438, 23438)] - (-600.0)) < 1e-6          # past EdgeEnd: the sea floor
    s = out["Summary"][0][0].values
    assert s["points"] == len(src) and s["nan"] == 0 and s["floor_err_max_cm"] < 400.0


def test_seed_changes_the_noise_only():
    _, a = _run(Seed=1, **SMALL)
    _, b = _run(Seed=2, **SMALL)
    _, c = _run(Seed=1, **SMALL)
    za, zb, zc = ([p[2] for p in o["Terrain"][0][0].loc] for o in (a, b, c))
    assert za == zc and za != zb


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Terrain"] == [] and out["Summary"][0][0].values["points"] == 0
```

- [ ] **Step 2: Run** `C:\Python314\python.exe -m pytest Tools/pypcg/tests/test_world_w01.py -q` — FAIL.
- [ ] **Step 3: Implement** `Content/Python/pypcg/stages/w01_terrain.py`:

```python
"""PyWorld W1 -- the valley terrain (视频步骤 0：地形底图).

Every vertex of the base mesh terrain (a 3 km query) gets the valley's height: a floor that follows the
`PyWorld_Valley` axis spline (its control points carry the floor height) with a 2 % cross slope and low noise,
walls rising over `WallWidth` to ridges `RidgeHeight` above the floor (domain-warped value noise for their height,
ridged noise for crests and gullies), and a fall to the sea floor (-600 cm) between EdgeStart and EdgeEnd from the
centre. `Mountain` (0 on the floor .. 1 up the walls) is written for the native erosion that follows, which only
works the mountains (its MaskAttribute). Pure: no unreal import."""
import bisect
import math

from pypcg.geo import Points, Spline
from pypcg.stage_api import Param
from pypcg.world import SEA_Z, VERTEX_CM, noise, points as WP
from pypcg.world.grid import Lattice
from pypcg.world.terraform import smoothstep

STAGE = 101
RECORD = "w01"
DOC = """PyWorld W1 Terrain (地形): the valley floor along the PyWorld_Valley spline, walls up to the ridges, noise on
the mountains and a fall to the sea at the edge; writes Mountain (0 floor .. 1 walls) for the native erosion."""
RANDOM = True
PARAMS = {
    "FloorHalfWidth": Param(25000.0, "Half width of the valley floor (cm)", type="Double"),
    "WallWidth": Param(40000.0, "Horizontal run of the valley walls (cm)", type="Double"),
    "RidgeHeight": Param(18000.0, "Ridge height above the valley floor (cm)", type="Double"),
    "EdgeStart": Param(115000.0, "Distance from the centre where the land starts falling to the sea (cm)", type="Double"),
    "EdgeEnd": Param(148000.0, "Distance from the centre where the land reaches the sea floor (cm)", type="Double"),
}
INPUTS = {"MeshTerrain": "points", "Valley": "spline"}
OUTPUTS = ("Terrain", "Summary")


def axis_table(items):
    """The valley axis as points sorted by y (the engine's polyline when there is one)."""
    pts = []
    for v, _t in items:
        if isinstance(v, Spline):
            pts.extend(tuple(p) for p in (v.polyline or v.points))
    return sorted(pts, key=lambda p: p[1])


def axis_at(table, y):
    """(axis x, floor z) at y, clamped to the axis's ends; (0, 0) without an axis."""
    if not table:
        return 0.0, 0.0
    ys = [p[1] for p in table]
    i = bisect.bisect_left(ys, y)
    if i <= 0:
        return table[0][0], table[0][2]
    if i >= len(table):
        return table[-1][0], table[-1][2]
    a, b = table[i - 1], table[i]
    t = 0.0 if b[1] == a[1] else (y - a[1]) / (b[1] - a[1])
    return a[0] + (b[0] - a[0]) * t, a[2] + (b[2] - a[2]) * t


def height(x, y, table, p, seed):
    """(z, mountain) of one vertex."""
    ax, floor = axis_at(table, y)
    d = abs(x - ax)
    fw, ww = p["FloorHalfWidth"], p["WallWidth"]
    z = floor + 120.0 * noise.fbm(x / 9000.0, y / 9000.0, seed, 3) + 0.02 * min(d, fw)
    t = smoothstep(fw, fw + ww, d)
    if t > 0.0:
        wx = x + 6000.0 * noise.fbm(x / 30000.0, y / 30000.0, seed + 11, 2)
        wy = y + 6000.0 * noise.fbm(x / 30000.0, y / 30000.0, seed + 12, 2)
        ridge = p["RidgeHeight"] * (0.75 + 0.5 * noise.value(wx / 50000.0, wy / 50000.0, seed + 21))
        detail = 0.2 * p["RidgeHeight"] * noise.ridged(wx / 14000.0, wy / 14000.0, seed + 31, 4)
        z += t ** 1.3 * (ridge + detail * t)
    f = smoothstep(p["EdgeStart"], p["EdgeEnd"], max(abs(x), abs(y)))
    return z + (SEA_Z - z) * f, t


def run(inputs, params, ctx):
    table = axis_table(inputs.get("Valley", []))
    out, n, nan, zmax = [], 0, 0, -1e30
    for v, _t in inputs.get("MeshTerrain", []):
        if not isinstance(v, Points) or not len(v):
            continue
        lat, ks = Lattice.from_locs(v.loc, VERTEX_CM)
        mountain = []
        for k, (x, y, _z) in zip(ks, v.loc):
            z, m = height(x, y, table, params, ctx.seed)
            if z != z:
                nan += 1
                z = SEA_Z
            lat.z[k] = z
            mountain.append(m)
            zmax = max(zmax, z)
        n += len(v)
        out.append((WP.with_heights(v, lat, ks, {"Mountain": ("Double", mountain)}), ["Terrain"]))
    err = 0.0
    if table:
        for q in range(9):
            y = table[0][1] + (table[-1][1] - table[0][1]) * (q + 0.5) / 9.0
            ax, floor = axis_at(table, y)
            if max(abs(ax), abs(y)) < params["EdgeStart"]:
                err = max(err, abs(height(ax, y, table, params, ctx.seed)[0] - floor))
    ctx.notes.append("%d vertices, ridge max %.0f cm" % (n, zmax))
    summary = {"points": n, "ridge_max_cm": float(zmax if n else 0.0), "floor_err_max_cm": float(err), "nan": nan}
    return {"Terrain": out, "Summary": [(WP.summary(summary), ["Summary"])]}
```

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `"PyWorld W1: the valley terrain"`.

---

### Task 6: W2 地点（`w02_locations`）+ `rules.kind_of`

**Files:** Create `Content/Python/pypcg/stages/w02_locations.py`, `Content/Python/pypcg/world/rules.py` (only `KIND_RADII` / `kind_of` here; Task 10 adds the rest), `Tools/pypcg/tests/test_world_w02.py`

**Interfaces:**
- Consumes: GetSinglePoint points (one per actor: `loc`, `scale`), a surface with `height(x, y)`.
- Produces: `rules.kind_of(radius_cm) -> "Town"|"Village"|"Hamlet"`. Outputs: `Locations` (tag `Location`; attrs `Id` Int32, `Kind` String, `Radius` Double, `Slope` Double), `RiverEnds` (tag `RiverEnd`; `Role` String Source/Outlet), `Exits` (tag `RoadExit`; `Id` Int32), `Summary` (`locations`, `river_ends`, `exits`, `max_center_slope_deg`, `off_terrain`). A location's radius is its actor's X scale x 10000 cm.

- [ ] **Step 1: Failing test** `Tools/pypcg/tests/test_world_w02.py`

```python
from pypcg.geo import Points
from pypcg.stages import w02_locations as S
from pypcg.world import rules
from world_fixtures import Surface, run_stage


def _actors(rows):
    p = Points()
    for x, y, sc in rows:
        p.add((x, y, 0.0), scale=(sc, sc, 1.0))
    return [(p, frozenset())]


def bowl(x, y):
    return 0.0005 * ((x - 3000.0) ** 2 + y ** 2) / 100.0        # flattest at (3000, 0)


def test_snaps_to_flat_ground_and_classifies():
    out, _ = run_stage(S, {"Locations": _actors([(0.0, 0.0, 2.2), (20000.0, 0.0, 0.7)]),
                           "RiverEnds": _actors([(0.0, 9000.0, 1.0), (0.0, -9000.0, 1.0)]),
                           "Exits": _actors([(5000.0, 9000.0, 1.0), (5000.0, -9000.0, 1.0)]),
                           "Surface": [(Surface(lambda x, y: bowl(x, y) + y * 0.001), frozenset())]})
    locs = out["Locations"][0][0]
    assert locs.attrs["Kind"] == ["Town", "Hamlet"] and locs.attrs["Radius"][0] == 22000.0
    assert abs(locs.loc[0][0] - 3000.0) <= 1500.0
    assert out["RiverEnds"][0][0].attrs["Role"] == ["Outlet", "Source"]     # sorted by y: the south end is lower
    s = out["Summary"][0][0].values
    assert (s["locations"], s["river_ends"], s["exits"], s["off_terrain"]) == (2, 2, 2, 0)
    assert rules.kind_of(14000.0) == "Village"


def test_location_off_terrain():
    out, _ = run_stage(S, {"Locations": _actors([(90000.0, 0.0, 1.0)]),
                           "Surface": [(Surface(lambda x, y: 0.0, half_cm=20000.0), frozenset())]})
    locs = out["Locations"][0][0]
    assert locs.loc[0][:2] == (90000.0, 0.0) and locs.attrs["Slope"] == [-1.0]
    assert out["Summary"][0][0].values["off_terrain"] == 1


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Summary"][0][0].values["locations"] == 0
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** `Content/Python/pypcg/world/rules.py` (first part):

```python
"""PyWorld's rule tables (视频："建筑规则表"、散布规则): settlement kinds, streets, building types and biomes."""

KIND_RADII = (("Town", 20000.0), ("Village", 12000.0), ("Hamlet", 0.0))   # a location's kind by its radius (cm)


def kind_of(radius_cm):
    for kind, r in KIND_RADII:
        if radius_cm >= r:
            return kind
    return "Hamlet"
```

`Content/Python/pypcg/stages/w02_locations.py`:

```python
"""PyWorld W2 -- the locations (视频步骤 2：美术放置的兴趣点).

Reads three kinds of level actor as single points (Get Actor Data, GetSinglePoint): PyWorld_Location (its X scale x
100 m is the radius), PyWorld_RiverEnd and PyWorld_RoadExit. Each location moves, within SnapRadius, to the flattest
ground of the final terrain W1 wrote; its radius gives its kind (Town / Village / Hamlet). The higher river end is
the source. A point the terrain does not cover keeps its place with Slope -1."""
import math

from pypcg.geo import Points
from pypcg.stage_api import Param
from pypcg.world import points as WP, rules

STAGE = 102
RECORD = "w02"
DOC = """PyWorld W2 Locations (地点): the location, river-end and road-exit actors, snapped to flat ground on the
terrain; a location's radius (its X scale x 100 m) gives its kind."""
RANDOM = False
PARAMS = {"SnapRadius": Param(6000.0, "How far a location may move to find flatter ground (cm)", type="Double")}
INPUTS = {"Locations": "points", "RiverEnds": "points", "Exits": "points", "Surface": "surface"}
OUTPUTS = ("Locations", "RiverEnds", "Exits", "Summary")
PROBE_CM = 600.0
STEP_CM = 1500.0


def actors(items):
    """[(loc, scale)] of every point on a pin."""
    out = []
    for v, _t in items:
        if isinstance(v, Points):
            out.extend(zip(v.loc, v.scale))
    return out


def surface_of(items):
    for v, _t in items:
        if hasattr(v, "height"):
            return v
    return None


def slope_at(surface, x, y, h=PROBE_CM):
    zs = [surface.height(x + dx, y + dy) for dx, dy in ((h, 0.0), (-h, 0.0), (0.0, h), (0.0, -h))]
    if any(z is None for z in zs):
        return None
    return math.degrees(math.atan(math.hypot((zs[0] - zs[1]) / (2 * h), (zs[2] - zs[3]) / (2 * h))))


def snap(surface, x, y, radius):
    """(x, y, z, slope): the flattest sample within radius (ties: the closer); the input with z 0, slope -1 when the
    terrain covers none of it."""
    best = None
    m = int(radius // STEP_CM)
    if surface is not None:
        for b in range(-m, m + 1):
            for a in range(-m, m + 1):
                px, py = x + a * STEP_CM, y + b * STEP_CM
                d = math.hypot(px - x, py - y)
                if d > radius:
                    continue
                s = slope_at(surface, px, py)
                if s is not None and (best is None or (s, d) < best[0]):
                    best = ((s, d), px, py)
    if best is None:
        return x, y, 0.0, -1.0
    _key, px, py = best
    return px, py, float(surface.height(px, py)), float(best[0][0])


def run(inputs, params, ctx):
    surface = surface_of(inputs.get("Surface", []))
    locs = sorted(actors(inputs.get("Locations", [])), key=lambda a: (-a[1][0], a[0][1], a[0][0]))
    rows, off, worst = [], 0, 0.0
    for i, (loc, scale) in enumerate(locs):
        radius = float(scale[0]) * 10000.0
        x, y, z, s = snap(surface, loc[0], loc[1], params["SnapRadius"])
        off += s < 0
        worst = max(worst, s)
        rows.append({"loc": (x, y, z), "Id": i, "Kind": rules.kind_of(radius), "Radius": radius, "Slope": s})

    def placed(items):
        out = []
        for loc, _s in sorted(actors(items), key=lambda a: (a[0][1], a[0][0])):
            h = surface.height(loc[0], loc[1]) if surface is not None else None
            out.append((loc[0], loc[1], float(h) if h is not None else 0.0))
        return out
    ends = placed(inputs.get("RiverEnds", []))
    top = max(range(len(ends)), key=lambda i: ends[i][2]) if ends else None
    end_rows = [{"loc": p, "Role": "Source" if i == top else "Outlet"} for i, p in enumerate(ends)]
    exit_rows = [{"loc": p, "Id": i} for i, p in enumerate(placed(inputs.get("Exits", [])))]
    out = {"Locations": [], "RiverEnds": [], "Exits": []}
    if rows:
        types = {"Id": "Int32", "Kind": "String", "Radius": "Double", "Slope": "Double"}
        out["Locations"] = [(WP.table_points(rows, types), ["Location"])]
    if end_rows:
        out["RiverEnds"] = [(WP.table_points(end_rows, {"Role": "String"}), ["RiverEnd"])]
    if exit_rows:
        out["Exits"] = [(WP.table_points(exit_rows, {"Id": "Int32"}), ["RoadExit"])]
    summary = {"locations": len(rows), "river_ends": len(end_rows), "exits": len(exit_rows),
               "max_center_slope_deg": float(worst), "off_terrain": int(off)}
    out["Summary"] = [(WP.summary(summary), ["Summary"])]
    return out
```

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `"PyWorld W2: locations snapped to flat ground"`.

---

### Task 7: W3 河流（`w03_river`）

**Files:** Create `Content/Python/pypcg/stages/w03_river.py`, `Tools/pypcg/tests/test_world_w03.py`

**Interfaces:**
- Consumes: W2 output (via the `Upstream` pin: `Location`, `RiverEnd` tagged point tables); terrain points.
- Produces: `Terrain` (carved, all vertices), `River` (tag `River`; one ordered point per 10 m at the water line; attrs `Width`, `WaterZ`, `BedZ`, `S` Double), `Water` (tag `Water`; Plane mesh points), `Summary` (`length_m`, `samples`, `carved`, `monotone`, `width_min_cm`, `width_max_cm`, `water_drop_cm`). Helper `river_rows(items) -> [(x, y, water, width, bed, s)]` sorted by S (used by W4–W9).

- [ ] **Step 1: Failing test** `Tools/pypcg/tests/test_world_w03.py`

```python
from pypcg.stages import w03_river as S
from world_fixtures import run_stage, table, terrain


def valley(x, y):
    return 1000.0 + 0.02 * y + 0.0004 * x * x / 100.0          # a trough along x = 0 falling to the south


def _ends(sx, sy, ox, oy):
    return table([{"loc": (sx, sy, 0.0), "Role": "Source"}, {"loc": (ox, oy, 0.0), "Role": "Outlet"}],
                 {"Role": "String"}, ["RiverEnd"])


def test_river_follows_the_trough_and_carves():
    src = terrain(valley)
    out, _ = run_stage(S, {"Terrain": [(src, frozenset())], "Upstream": [_ends(2000.0, 20000.0, -2000.0, -20000.0)]})
    s = out["Summary"][0][0].values
    assert s["length_m"] >= 380.0 and s["monotone"] and s["carved"] > 0
    rows = S.river_rows(out["River"])
    assert max(abs(r[0]) for r in rows[3:-3]) < 2500.0
    assert abs(rows[0][3] - 600.0) < 1e-6 and abs(rows[-1][3] - 2000.0) < 1e-6
    before = {p[:2]: p[2] for p in src.loc}
    after = out["Terrain"][0][0]
    assert len(after) == len(src) and all(p[2] <= before[p[:2]] + 1e-9 for p in after.loc)
    assert len(out["Water"][0][0]) == len(rows) - 1


def test_unreachable_outlet():
    src = terrain(valley)
    out, _ = run_stage(S, {"Terrain": [(src, frozenset())], "Upstream": [_ends(0.0, 20000.0, 900000.0, 0.0)]})
    assert out["Summary"][0][0].values["length_m"] == 0.0 and out["River"] == []
    assert [p[2] for p in out["Terrain"][0][0].loc] == [p[2] for p in src.loc]


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Terrain"] == [] and out["Summary"][0][0].values["length_m"] == 0.0
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `Content/Python/pypcg/stages/w03_river.py`:

```python
"""PyWorld W3 -- the river (视频步骤 4：河流与道路同一套寻路模型，只是容差不同).

A* from the river source to the outlet on every second terrain vertex (11.7 m): each step costs its length, more
the higher it lies above the lowest ground, plus a heavy price for climbing, plus a little value noise so the
river meanders; it keeps out of the inner half of every location. The path is smoothed (Chaikin) and resampled every
10 m. The water line is the running minimum of the ground along it, 80 cm under, smoothed and kept non-increasing;
the width grows from WidthStart to WidthEnd. The channel is carved into the terrain (bed `Depth` under the water,
banks at 1:2), and the water surface is laid as stretched Plane meshes (MI_ocean)."""
import math

from pypcg.geo import Points
from pypcg.stage_api import Param
from pypcg.world import MESH, VERTEX_CM, astar, geom, noise, points as WP, terraform as T
from pypcg.world.grid import Lattice

STAGE = 103
RECORD = "w03"
DOC = """PyWorld W3 River (河流): A* from the source to the outlet along low ground, smoothed; the water line falls
monotonically, the width grows downstream; the channel is carved into the terrain and the water surface placed."""
RANDOM = True
PARAMS = {
    "WidthStart": Param(600.0, "River width at the source (cm)", type="Double"),
    "WidthEnd": Param(2000.0, "River width at the outlet (cm)", type="Double"),
    "Depth": Param(150.0, "Bed depth under the water at the centre line (cm)", type="Double"),
    "Meander": Param(0.6, "Strength of the noise that makes the river wander", type="Double"),
    "TownAvoid": Param(20.0, "Extra cost per cm inside the inner half of a location", type="Double"),
}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Terrain", "River", "Water", "Summary")
GRID_HALF = 140000.0
STEP = 1000.0
WATER_UNDER = 80.0


def river_rows(items):
    """[(x, y, water, width, bed, s)] of every `River` point table, ordered by S."""
    rows = []
    for v, tags in items:
        if isinstance(v, Points) and "River" in tags:
            for r in WP.rows_of(v):
                rows.append((r["loc"][0], r["loc"][1], r["WaterZ"], r["Width"], r["BedZ"], r["S"]))
    return sorted(rows, key=lambda r: r[5])


def terrain_sets(items):
    """(lattice, [(points, ks)]) over every point set on the pin."""
    sets = [v for v, _t in items if isinstance(v, Points) and len(v)]
    locs = [p for v in sets for p in v.loc]
    lat, ks = Lattice.from_locs(locs, VERTEX_CM)
    out, at = [], 0
    for v in sets:
        out.append((v, ks[at:at + len(v)]))
        at += len(v)
    return lat, out


def _summary(**kw):
    base = {"length_m": 0.0, "samples": 0, "carved": 0, "monotone": False, "width_min_cm": 0.0, "width_max_cm": 0.0,
            "water_drop_cm": 0.0}
    base.update(kw)
    return [(WP.summary(base), ["Summary"])]


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    up = inputs.get("Upstream", [])
    ends = [r for v in WP.values_tagged(inputs, "Upstream", "RiverEnd") for r in WP.rows_of(v)]
    locs = [(r["loc"][0], r["loc"][1], r["Radius"]) for v in WP.values_tagged(inputs, "Upstream", "Location")
            for r in WP.rows_of(v)]
    terrain_out = lambda: [(WP.with_heights(v, lat, ks), ["Terrain"]) for v, ks in sets]
    src = next((r["loc"] for r in ends if r["Role"] == "Source"), None)
    dst = next((r["loc"] for r in ends if r["Role"] == "Outlet"), None)
    if not sets or src is None or dst is None:
        ctx.notes.append("no terrain or no river ends (%d upstream items)" % len(up))
        return {"Terrain": terrain_out(), "River": [], "Water": [], "Summary": _summary()}
    co = lat.coarse(2, GRID_HALF)
    ka, kb = co.nearest_valid(src[0], src[1]), co.nearest_valid(dst[0], dst[1])
    zmin = min(z for z in co.z if z is not None)
    seed, meander, avoid = ctx.seed, params["Meander"], params["TownAvoid"]

    def cost(a, b, length):
        za, zb = co.z[a], co.z[b]
        x, y = co.xy(b)
        c = length * (1.0 + (zb - zmin) / 800.0 + meander * noise.value(x / 40000.0, y / 40000.0, seed + 5))
        c += 60.0 * max(0.0, zb - za)
        for lx, ly, lr in locs:
            if math.hypot(x - lx, y - ly) < 0.5 * lr:
                c += length * avoid
        return c
    path = astar.search(co, {ka: 0.0}, {kb}, cost, astar.MOVES8) if ka is not None and kb is not None else None
    if not path or len(path) < 2:
        ctx.notes.append("no river path")
        return {"Terrain": terrain_out(), "River": [], "Water": [], "Summary": _summary()}
    pts = geom.resample(geom.chaikin([co.xy(k) for k in path], 3), STEP)
    ground, last = [], None
    for x, y in pts:
        h = lat.height(x, y)
        last = h if h is not None else (last if last is not None else 0.0)
        ground.append(last)
    water = []
    for g in ground:
        water.append(min(water[-1], g - WATER_UNDER) if water else g - WATER_UNDER)
    water = geom.moving_average(water, 6)
    for i in range(1, len(water)):
        water[i] = min(water[i], water[i - 1])
    cum = geom.cumulative(pts)
    total = cum[-1]
    ws, we, depth = params["WidthStart"], params["WidthEnd"], params["Depth"]
    width = [ws + (we - ws) * (s / total if total else 0.0) for s in cum]
    carved = T.carve_river(lat, [(p[0], p[1], w, wd) for p, w, wd in zip(pts, water, width)], depth)
    rows = [{"loc": (p[0], p[1], w), "Width": wd, "WaterZ": w, "BedZ": w - depth, "S": s}
            for p, w, wd, s in zip(pts, water, width, cum)]
    planes = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        length = geom.dist2d(a, b)
        planes.append((((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (water[i] + water[i + 1]) / 2 + 5.0),
                       (0.0, geom.yaw_deg(a, b), 0.0),
                       (length * 1.15 / 100.0, (width[i] + width[i + 1]) / 200.0, 1.0), MESH["Plane"]))
    types = {"Width": "Double", "WaterZ": "Double", "BedZ": "Double", "S": "Double"}
    ctx.notes.append("river %.0f m, %d vertices carved" % (total / 100.0, carved))
    return {"Terrain": terrain_out(), "River": [(WP.table_points(rows, types), ["River"])],
            "Water": [(WP.mesh_points(planes), ["Water"])],
            "Summary": _summary(length_m=total / 100.0, samples=len(pts), carved=carved,
                                monotone=all(b <= a + 1e-9 for a, b in zip(water, water[1:])),
                                width_min_cm=min(width), width_max_cm=max(width), water_drop_cm=water[0] - water[-1])}
```

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `"PyWorld W3: the river, routed, carved and filled"`.

---

### Task 8: W4 道路（`w04_roads`）

**Files:** Create `Content/Python/pypcg/stages/w04_roads.py`, `Tools/pypcg/tests/test_world_w04.py`

**Interfaces:**
- Consumes: `w03_river.river_rows`, `w03_river.terrain_sets`; W2 tables `Location` (`Kind`, `Radius`) and `RoadExit`.
- Produces: `Terrain`; `Roads` (one point table per road, tags `["Road", "Main"|"Secondary"]`; attrs `RoadId` Int32, `Class` String, `Width` Double (full width), `Bridge` Bool, `S` Double; loc z = the road profile); `Modules` (tag `RoadModule`, mesh points); `Summary` (`roads`, `main_roads`, `secondary_roads`, `length_m`, `max_grade_main`, `max_grade_secondary`, `bridge_samples`, `connected`, `unreachable`). Helpers `road_rows(items) -> [dict(id, cls, width, pts [(x,y,z)], bridge [bool])]`, `profile(pts, lat, grade, waters) -> [z]`.

- [ ] **Step 1: Failing test** `Tools/pypcg/tests/test_world_w04.py`

```python
from pypcg.stages import w04_roads as S
from world_fixtures import run_stage, table, terrain

FLAT = lambda x, y: 1000.0
LOC_T = {"Id": "Int32", "Kind": "String", "Radius": "Double", "Slope": "Double"}


def _up(locs, exits, river=None):
    up = [table([{"loc": (x, y, 1000.0), "Id": i, "Kind": k, "Radius": r, "Slope": 0.0}
                 for i, (x, y, k, r) in enumerate(locs)], LOC_T, ["Location"]),
          table([{"loc": (x, y, 1000.0), "Id": i} for i, (x, y) in enumerate(exits)], {"Id": "Int32"}, ["RoadExit"])]
    if river:
        up.append(table([{"loc": (x, y, w), "Width": wd, "WaterZ": w, "BedZ": w - 150.0, "S": s}
                         for x, y, w, wd, s in river], {"Width": "Double", "WaterZ": "Double", "BedZ": "Double",
                                                         "S": "Double"}, ["River"]))
    return up


def test_network_is_connected_and_bridges_respect_grade():
    river = [(0.0, y, 900.0, 1000.0, y + 23000.0) for y in range(-23000, 23001, 1000)]
    up = _up([(-10000.0, 5000.0, "Town", 22000.0), (10000.0, -5000.0, "Village", 14000.0),
              (-12000.0, -15000.0, "Hamlet", 7000.0)], [(-20000.0, -1000.0), (20000.0, 1000.0)], river)
    out, _ = run_stage(S, {"Terrain": [(terrain(FLAT), frozenset())], "Upstream": up})
    s = out["Summary"][0][0].values
    assert s["connected"] and s["unreachable"] == 0 and s["main_roads"] == 3 and s["secondary_roads"] == 1
    assert s["max_grade_main"] <= 0.10 + 1e-9 and s["bridge_samples"] > 0
    roads = S.road_rows(out["Roads"])
    for rd in roads:
        for (x, y, z), br in zip(rd["pts"], rd["bridge"]):
            if br:
                assert z >= 900.0 + 250.0 - 1e-6
    assert len(out["Modules"][0][0]) > 0


def test_blocked_location():
    cliff = lambda x, y: 9000.0 if (x - 12000.0) ** 2 + (y - 12000.0) ** 2 < 4000.0 ** 2 else 1000.0
    up = _up([(-10000.0, 0.0, "Town", 22000.0), (12000.0, 12000.0, "Hamlet", 2000.0)],
             [(-20000.0, -1000.0), (20000.0, 1000.0)])
    out, _ = run_stage(S, {"Terrain": [(terrain(cliff), frozenset())], "Upstream": up})
    s = out["Summary"][0][0].values
    assert s["unreachable"] == 1 and not s["connected"]


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Roads"] == [] and out["Summary"][0][0].values["roads"] == 0
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `Content/Python/pypcg/stages/w04_roads.py`:

```python
"""PyWorld W4 -- the road network (视频步骤 3).

A* on every second terrain vertex with 16 directions (the video's "look in more directions" trick, so roads follow
the terrain instead of zigzagging): a step costs its length x (1 + 6 (grade / MainGrade)^2), steps steeper than
HardGrade are blocked, river cells cost WaterPenalty times more (short, square crossings) and cells already on a
road cost ReuseFactor times less (new roads join the network). The trunk joins the south exit, the towns and
villages by y and the north exit; every hamlet then joins the nearest road (multi-goal Dijkstra). Each road is
smoothed and resampled every 5 m; its profile is the ground averaged over 60 m, cut and filled to the class's grade,
raised to the water + 2.5 m on bridges (ramps keep the grade). The corridor is flattened to the profile except on
bridge spans, and lane meshes are laid every 5 m."""
import math

from pypcg.geo import Points
from pypcg.stage_api import Param
from pypcg.stages.w03_river import river_rows, terrain_sets
from pypcg.world import MESH, astar, geom, points as WP, terraform as T

STAGE = 104
RECORD = "w04"
DOC = """PyWorld W4 Roads (道路): 16-direction A* with grade, water and reuse costs; trunk through the exits, towns
and villages, hamlets joined to the network; graded profiles with bridges over the river; flattened corridors and
lane meshes."""
RANDOM = False
PARAMS = {
    "MainWidth": Param(800.0, "Main road width (cm)", type="Double"),
    "SecondaryWidth": Param(550.0, "Secondary road width (cm)", type="Double"),
    "MainGrade": Param(0.10, "Maximum grade of the main roads", type="Double"),
    "SecondaryGrade": Param(0.14, "Maximum grade of the secondary roads", type="Double"),
    "HardGrade": Param(0.22, "Steps steeper than this are impassable", type="Double"),
    "WaterPenalty": Param(6.0, "Cost multiplier of a step into the river", type="Double"),
    "ReuseFactor": Param(0.35, "Cost multiplier of a step along an existing road", type="Double"),
}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Terrain", "Roads", "Modules", "Summary")
GRID_HALF = 100000.0
STEP = 500.0
BRIDGE_CLEAR = 250.0
BRIDGE_REACH = 400.0
TYPES = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}


def road_rows(items):
    """[dict(id, cls, width, pts [(x, y, z)], bridge [bool])] of every `Road` table, by RoadId."""
    out = []
    for v, tags in items:
        if isinstance(v, Points) and "Road" in tags and len(v):
            rows = sorted(WP.rows_of(v), key=lambda r: r["S"])
            out.append({"id": rows[0]["RoadId"], "cls": rows[0]["Class"], "width": rows[0]["Width"],
                        "pts": [r["loc"] for r in rows], "bridge": [bool(r["Bridge"]) for r in rows]})
    return sorted(out, key=lambda r: r["id"])


def river_index(rows):
    idx = geom.SegmentIndex(2000.0)
    for a, b in zip(rows, rows[1:]):
        idx.add(a[:2], b[:2], (0.5 * (a[2] + b[2]), 0.5 * (a[3] + b[3])))
    return idx


def water_at(idx, x, y, extra):
    """The water z when (x, y) is within half the river's width + extra, else None."""
    hit = idx.nearest(x, y, 3000.0 + extra)
    if hit is None:
        return None
    water, width = idx.payload(hit[1])
    return water if hit[0] < 0.5 * width + extra else None


def _clamp(z, ds, g):
    for i in range(1, len(z)):
        z[i] = min(max(z[i], z[i - 1] - g * ds[i - 1]), z[i - 1] + g * ds[i - 1])
    for i in range(len(z) - 2, -1, -1):
        z[i] = min(max(z[i], z[i + 1] - g * ds[i]), z[i + 1] + g * ds[i])


def _raise(z, ds, g):
    for i in range(1, len(z)):
        z[i] = max(z[i], z[i - 1] - g * ds[i - 1])
    for i in range(len(z) - 2, -1, -1):
        z[i] = max(z[i], z[i + 1] - g * ds[i])


def profile(pts, lat, grade, waters, anchor=None):
    """The road's z: ground averaged over +-30 m, cut/filled to `grade`, bridges raised to water + BRIDGE_CLEAR with
    graded ramps; `anchor` pins the last point (a branch meeting the trunk)."""
    ground, last = [], None
    for x, y in pts:
        h = lat.height(x, y)
        last = h if h is not None else (last if last is not None else 0.0)
        ground.append(last)
    z = geom.moving_average(ground, 6)
    ds = [geom.dist2d(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    if anchor is not None:
        z[-1] = anchor
    _clamp(z, ds, grade)
    for i, w in enumerate(waters):
        if w is not None:
            z[i] = max(z[i], w + BRIDGE_CLEAR)
    _raise(z, ds, grade)
    return z


def max_grade(pts, z):
    g = 0.0
    for i in range(len(pts) - 1):
        d = geom.dist2d(pts[i], pts[i + 1])
        if d > 1.0:
            g = max(g, abs(z[i + 1] - z[i]) / d)
    return g


def modules(pts, z, cls, width):
    rows = []
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        length = geom.dist2d(a, b)
        if length <= 0.0:
            continue
        yaw = geom.yaw_deg(a, b)
        rot = (math.degrees(math.atan2(z[i + 1] - z[i], length)), yaw, 0.0)
        mx, my, mz = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (z[i] + z[i + 1]) / 2 + 2.0
        nx, ny = -math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
        if cls == "Main":
            for off in (-200.0, 200.0):
                rows.append(((mx + nx * off, my + ny * off, mz), rot, (length / 500.0 * 1.02, 1.0, 1.0), MESH["LaneCar"]))
            rows.append(((mx, my, mz + 1.0), rot, (length / 500.0 * 1.02, 1.0, 1.0), MESH["Divider"]))
        else:
            rows.append(((mx, my, mz), rot, (length / 160.0 * 1.02, width / 300.0, 1.0), MESH["Path"]))
    return rows


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    locs = [r for v in WP.values_tagged(inputs, "Upstream", "Location") for r in WP.rows_of(v)]
    exits = sorted((r["loc"] for v in WP.values_tagged(inputs, "Upstream", "RoadExit") for r in WP.rows_of(v)),
                   key=lambda p: p[1])
    river = river_rows(inputs.get("Upstream", []))
    if not sets or len(exits) + len(locs) < 2:
        return {"Terrain": [(WP.with_heights(v, lat, ks), ["Terrain"]) for v, ks in sets], "Roads": [], "Modules": [],
                "Summary": [(WP.summary({"roads": 0, "main_roads": 0, "secondary_roads": 0, "length_m": 0.0,
                                         "max_grade_main": 0.0, "max_grade_secondary": 0.0, "bridge_samples": 0,
                                         "connected": False, "unreachable": 0}), ["Summary"])]}
    co = lat.coarse(2, GRID_HALF)
    ridx = river_index(river)
    water_cells = {k for k in range(len(co.z)) if co.z[k] is not None and water_at(ridx, *co.xy(k), 500.0) is not None}
    road_cells = set()
    p = params

    def cost(a, b, length):
        g = abs(co.z[b] - co.z[a]) / length
        if g > p["HardGrade"]:
            return None
        c = length * (1.0 + 6.0 * (g / p["MainGrade"]) ** 2)
        if b in water_cells:
            c *= p["WaterPenalty"]
        if b in road_cells:
            c *= p["ReuseFactor"]
        return c
    trunk = [exits[0]] if exits else []
    trunk += [r["loc"] for r in sorted(locs, key=lambda r: r["loc"][1]) if r["Kind"] != "Hamlet"]
    trunk += [exits[-1]] if len(exits) > 1 else []
    routes, unreachable = [], 0
    for a, b in zip(trunk, trunk[1:]):
        ka, kb = co.nearest_valid(a[0], a[1]), co.nearest_valid(b[0], b[1])
        path = astar.search(co, {ka: 0.0}, {kb}, cost, astar.MOVES16, h_scale=p["ReuseFactor"]) if ka is not None and kb is not None else None
        if path is None:
            unreachable += 1
            continue
        road_cells.update(path)
        routes.append(("Main", path))
    for r in sorted((r for r in locs if r["Kind"] == "Hamlet"), key=lambda r: -r["Radius"]):
        ka = co.nearest_valid(r["loc"][0], r["loc"][1])
        path = astar.search(co, {ka: 0.0}, road_cells, cost, astar.MOVES16, h_scale=0.0) if ka is not None and road_cells else None
        if path is None:
            unreachable += 1
            continue
        road_cells.update(path)
        routes.append(("Secondary", path))
    # connectivity: routes sharing a cell are joined
    parent = list(range(len(routes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    owner = {}
    for i, (_c, path) in enumerate(routes):
        for k in path:
            if k in owner:
                parent[find(i)] = find(owner[k])
            owner[k] = i
    connected = unreachable == 0 and len({find(i) for i in range(len(routes))}) <= 1
    roads, built = [], geom.SegmentIndex(2000.0)
    for rid, (cls, path) in enumerate(routes):
        if len(path) < 2:
            continue
        pts = geom.resample(geom.chaikin([co.xy(k) for k in path], 2), STEP)
        waters = [water_at(ridx, x, y, BRIDGE_REACH) for x, y in pts]
        anchor = None
        if cls == "Secondary":
            hit = built.nearest(pts[-1][0], pts[-1][1], 5000.0)
            anchor = built.payload(hit[1]) if hit else None
        grade = p["MainGrade"] if cls == "Main" else p["SecondaryGrade"]
        z = profile(pts, lat, grade, waters, anchor)
        for i in range(len(pts) - 1):
            built.add(pts[i], pts[i + 1], 0.5 * (z[i] + z[i + 1]))
        width = p["MainWidth"] if cls == "Main" else p["SecondaryWidth"]
        roads.append({"id": rid, "cls": cls, "width": width, "pts": pts, "z": z, "bridge": [w is not None for w in waters]})
    for rd in sorted(roads, key=lambda r: r["cls"] != "Secondary"):        # secondaries first, the trunk on top
        T.flatten_corridor(lat, [(x, y, z, 0.5 * rd["width"], br) for (x, y), z, br in zip(rd["pts"], rd["z"], rd["bridge"])])
    out_roads, mods, length, grades = [], [], 0.0, {"Main": 0.0, "Secondary": 0.0}
    for rd in roads:
        cum = geom.cumulative(rd["pts"])
        length += cum[-1]
        grades[rd["cls"]] = max(grades[rd["cls"]], max_grade(rd["pts"], rd["z"]))
        rows = [{"loc": (x, y, z), "RoadId": rd["id"], "Class": rd["cls"], "Width": rd["width"], "Bridge": br, "S": s}
                for (x, y), z, br, s in zip(rd["pts"], rd["z"], rd["bridge"], cum)]
        out_roads.append((WP.table_points(rows, TYPES), ["Road", rd["cls"]]))
        mods.extend(modules(rd["pts"], rd["z"], rd["cls"], rd["width"]))
    summary = {"roads": len(roads), "main_roads": sum(r["cls"] == "Main" for r in roads),
               "secondary_roads": sum(r["cls"] == "Secondary" for r in roads), "length_m": length / 100.0,
               "max_grade_main": grades["Main"], "max_grade_secondary": grades["Secondary"],
               "bridge_samples": sum(sum(r["bridge"]) for r in roads), "connected": bool(connected),
               "unreachable": unreachable}
    ctx.notes.append("%d roads, %.0f m, %d unreachable" % (len(roads), length / 100.0, unreachable))
    return {"Terrain": [(WP.with_heights(v, lat, ks), ["Terrain"]) for v, ks in sets], "Roads": out_roads,
            "Modules": [(WP.mesh_points(mods), ["RoadModule"])] if mods else [],
            "Summary": [(WP.summary(summary), ["Summary"])]}
```

- [ ] **Step 4: Run** — PASS (if the bridge test's hamlet route crosses the river first, fine: the assertions are class-agnostic). **Step 5: Commit** `"PyWorld W4: the road network"`.

---

### Task 9: W5 桥（`w05_bridges`）

**Files:** Create `Content/Python/pypcg/stages/w05_bridges.py`, `Tools/pypcg/tests/test_world_w05.py`

**Interfaces:**
- Consumes: `w03_river.river_rows`, `w04_roads.road_rows`.
- Produces: `Bridges` (tag `Bridge`; attrs `Span`, `Yaw`, `Width` Double, `RoadId` Int32; loc = deck centre at road height), `Parts` (tag `BridgePart`, mesh points), `Summary` (`bridges`, `crossings`, `parts`, `max_span_cm`). Helper `bridge_rows(items) -> [dict(x, y, z, span, yaw, width)]`.

- [ ] **Step 1: Failing test** `Tools/pypcg/tests/test_world_w05.py`

```python
from pypcg.stages import w05_bridges as S
from pypcg.world import MESH
from world_fixtures import run_stage, table

RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}
WT = {"Width": "Double", "WaterZ": "Double", "BedZ": "Double", "S": "Double"}


def test_one_crossing_one_bridge():
    road = table([{"loc": (x, 0.0, 1200.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": abs(x) < 900,
                   "S": x + 5000.0} for x in range(-5000, 5001, 500)], RT, ["Road", "Main"])
    river = table([{"loc": (0.0, y, 900.0), "Width": 1600.0, "WaterZ": 900.0, "BedZ": 750.0, "S": y + 5000.0}
                   for y in range(-5000, 5001, 1000)], WT, ["River"])
    out, _ = run_stage(S, {"Upstream": [road, river]})
    s = out["Summary"][0][0].values
    assert s["bridges"] == s["crossings"] == 1
    b = S.bridge_rows(out["Bridges"])[0]
    assert abs(b["span"] - (1600.0 + 1200.0)) < 1e-6 and abs(b["x"]) < 1e-6
    meshes = out["Parts"][0][0].attrs["Mesh"]
    assert meshes.count(MESH["Cube"]) == 3 and meshes.count(MESH["Rail"]) == 14 and meshes.count(MESH["Cylinder"]) == 1


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Bridges"] == [] and out["Summary"][0][0].values["bridges"] == 0
```

(Span 2800 cm: 7 rail pieces each side; deck + two abutments = 3 cubes; one pier because 2800 > 1400.)

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `Content/Python/pypcg/stages/w05_bridges.py`:

```python
"""PyWorld W5 -- bridges (视频步骤 5：路跨河处由专门的工具生成桥).

Every crossing of a road with the river centre line becomes a bridge: span = river width / |sin(angle)| + two
EndClearance (capped at 60 m), deck at the road's height (W4 raised it), a rail every 4 m on both edges, an
abutment at each end and a pier to the river bed when the span is over PierSpan. Grey-box meshes."""
import math

from pypcg.geo import Points
from pypcg.stage_api import Param
from pypcg.stages.w03_river import river_rows
from pypcg.stages.w04_roads import road_rows
from pypcg.world import MESH, geom, points as WP

STAGE = 105
RECORD = "w05"
DOC = """PyWorld W5 Bridges (桥): a deck, rails, abutments and a pier wherever a road crosses the river."""
RANDOM = False
PARAMS = {"EndClearance": Param(600.0, "Deck length beyond the water on each side (cm)", type="Double"),
          "PierSpan": Param(1400.0, "Spans longer than this get a pier (cm)", type="Double")}
INPUTS = {"Upstream": "any"}
OUTPUTS = ("Bridges", "Parts", "Summary")
MAX_SPAN = 6000.0
RAIL_CM = 400.0


def bridge_rows(items):
    out = []
    for v, tags in items:
        if isinstance(v, Points) and "Bridge" in tags:
            for r in WP.rows_of(v):
                out.append({"x": r["loc"][0], "y": r["loc"][1], "z": r["loc"][2], "span": r["Span"], "yaw": r["Yaw"],
                            "width": r["Width"]})
    return out


def frame(x, y, z, yaw, pitch):
    """at(a, l, h): the point `a` along the deck, `l` to its left and `h` above it."""
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))

    def at(a, l, h):
        return (x + a * cp * cy - l * sy - h * sp * cy, y + a * cp * sy + l * cy - h * sp * sy, z + a * sp + h * cp)
    return at


def parts(x, y, z, yaw, pitch, span, width, bed, pier_span):
    at = frame(x, y, z, yaw, pitch)
    rot = (pitch, yaw, 0.0)
    rows = [(at(0.0, 0.0, -27.0), rot, (span / 100.0, (width + 100.0) / 100.0, 0.5), MESH["Cube"])]
    for q in range(int(math.ceil(span / RAIL_CM))):
        for side in (1.0, -1.0):
            rows.append((at(-0.5 * span + RAIL_CM * q, side * (0.5 * width + 40.0), -2.0), rot, (1.0, 1.0, 1.0), MESH["Rail"]))
    for e in (-1.0, 1.0):
        rows.append((at(e * (0.5 * span + 150.0), 0.0, -202.0), (0.0, yaw, 0.0), (3.0, (width + 100.0) / 100.0, 4.0),
                     MESH["Cube"]))
    if span > pier_span and bed is not None:
        h = (z - 52.0) - bed
        if h > 100.0:
            rows.append(((x, y, bed + 0.5 * h), (0.0, 0.0, 0.0), (1.2, 1.2, h / 100.0), MESH["Cylinder"]))
    return rows


def run(inputs, params, ctx):
    up = inputs.get("Upstream", [])
    river = river_rows(up)
    rp = [r[:2] for r in river]
    bridges, rows = [], []
    crossings = 0
    for rd in road_rows(up):
        pts = rd["pts"]
        for x, y, i, t, j, u in geom.polyline_intersections([p[:2] for p in pts], rp) if len(rp) > 1 else []:
            crossings += 1
            a, b = pts[i], pts[i + 1]
            z = a[2] + (b[2] - a[2]) * t
            yaw = geom.yaw_deg(a, b)
            pitch = math.degrees(math.atan2(b[2] - a[2], max(geom.dist2d(a, b), 1e-6)))
            ra, rb = river[j], river[j + 1]
            width = ra[3] + (rb[3] - ra[3]) * u
            bed = ra[4] + (rb[4] - ra[4]) * u
            sin = max(abs(math.sin(math.radians(geom.yaw_deg(ra, rb) - yaw))), 0.25)
            span = min(width / sin + 2.0 * params["EndClearance"], MAX_SPAN)
            rows.extend(parts(x, y, z, yaw, pitch, span, rd["width"], bed, params["PierSpan"]))
            bridges.append({"loc": (x, y, z), "Span": span, "Yaw": yaw, "Width": rd["width"], "RoadId": rd["id"]})
    out = {"Bridges": [], "Parts": [], "Summary": [(WP.summary({
        "bridges": len(bridges), "crossings": crossings, "parts": len(rows),
        "max_span_cm": max((b["Span"] for b in bridges), default=0.0)}), ["Summary"])]}
    if bridges:
        out["Bridges"] = [(WP.table_points(bridges, {"Span": "Double", "Yaw": "Double", "Width": "Double",
                                                      "RoadId": "Int32"}), ["Bridge"])]
        out["Parts"] = [(WP.mesh_points(rows), ["BridgePart"])]
    return out
```

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `"PyWorld W5: bridges where roads cross the river"`.

---
### Task 10: 规则表、聚落布局与 W6（`rules`、`settle`、`w06_settlements`）

**Files:** Modify `Content/Python/pypcg/world/rules.py` (append); Create `Content/Python/pypcg/world/settle.py`, `Content/Python/pypcg/stages/w06_settlements.py`, `Tools/pypcg/tests/test_world_w06.py`

**Interfaces:**
- Produces in `rules`: `STREETS`, `zone_of(fraction)`, `BUILDINGS`, `LANDMARKS`, `TOWER`, `HEIGHT`, `WALL_TOP`, `GROUPS`, `MIN_BUILDINGS`, `pick(zone, kind, counts, rng)`.
- Produces in `settle`: `PLAZA_R`, `STREET_HW`, `Site(roads [dict(pts, hw)], river [(x, y, water, width)], taken RingIndex)`, `layout(loc dict(id, kind, x, y, radius), rng, site) -> dict(id, kind, x, y, r, plaza, streets, buildings [dict(kind, group, ring, x, y, w, d, yaw, special, settlement)], fields)`.
- W6 outputs: `Terrain`; `FootprintsLow|Mid|High|Tower` (closed linear Splines at the pad height, tags `["Footprint", group]`) → one `Assign_ShapeGrammarDefinition` each; `Parts` (foundations, roofs, spires, street modules, plaza tiles; tag `SettlementPart`); `Buildings` (tag `Building`; attrs `Kind`, `Group` String, `Settlement` Int32, `W`, `D`, `Yaw`, `Height` Double); `Streets` (one table per street, tag `Street`, attr `Width`); `Areas` (Polygons tagged `Footprint`, `Plaza`, `Field`); `Summary` (`buildings`, `town_min`, `village_min`, `hamlet_min`, `churches_min`, `overlaps`, `on_road`, `streets`, `plazas`, `fields`).

- [ ] **Step 1: Failing test** `Tools/pypcg/tests/test_world_w06.py`

```python
from pypcg.geo import Polygon, Spline
from pypcg.stages import w06_settlements as S
from pypcg.world import geom
from world_fixtures import run_stage, table, terrain

LOC_T = {"Id": "Int32", "Kind": "String", "Radius": "Double", "Slope": "Double"}
RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}


def _locs(rows):
    return table([{"loc": (x, y, 1000.0), "Id": i, "Kind": k, "Radius": r, "Slope": 0.0}
                  for i, (x, y, k, r) in enumerate(rows)], LOC_T, ["Location"])


def _road():
    return table([{"loc": (x, 0.0, 1000.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": False,
                   "S": x + 23000.0} for x in range(-23000, 23001, 500)], RT, ["Road", "Main"])


def _run(locs, seed=42):
    out, _ = run_stage(S, {"Terrain": [(terrain(lambda x, y: 1000.0 + 0.01 * y), frozenset())],
                           "Upstream": [_locs(locs), _road()]}, Seed=seed)
    return out


def test_village_follows_the_rules():
    out = _run([(0.0, 3000.0, "Village", 14000.0)])
    s = out["Summary"][0][0].values
    assert s["buildings"] >= 20 and s["village_min"] >= 20 and s["churches_min"] == 1
    assert s["overlaps"] == 0 and s["on_road"] == 0 and s["plazas"] == 1
    feet = [v for pin in ("FootprintsLow", "FootprintsMid", "FootprintsHigh", "FootprintsTower") for v, _t in out[pin]]
    assert len(feet) == s["buildings"] and all(isinstance(f, Spline) and f.closed and f.linear for f in feet)
    areas = [v for v, t in out["Areas"] if "Footprint" in t]
    assert all(isinstance(a, Polygon) for a in areas) and len(areas) == s["buildings"]
    assert len(out["Parts"][0][0]) > s["buildings"]


def test_two_close_settlements_never_overlap():
    out = _run([(-6000.0, 4000.0, "Town", 22000.0), (12000.0, -6000.0, "Village", 14000.0)])
    s = out["Summary"][0][0].values
    assert s["overlaps"] == 0 and s["on_road"] == 0 and s["buildings"] > 40


def test_same_seed_same_layout():
    a = _run([(0.0, 3000.0, "Village", 14000.0)], 7)
    b = _run([(0.0, 3000.0, "Village", 14000.0)], 7)
    assert [v.loc for v, _t in a["Buildings"]] == [v.loc for v, _t in b["Buildings"]]


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Summary"][0][0].values["buildings"] == 0
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Append to `rules.py`:

```python
STREETS = {"Town": (5, True), "Village": (3, False), "Hamlet": (2, False)}     # radial streets, ring street
MIN_BUILDINGS = {"Town": 60, "Village": 20, "Hamlet": 5}


def zone_of(fraction):
    """The zone at a distance of `fraction` x radius from the centre (视频：中心 → 外围)."""
    return "core" if fraction < 0.35 else ("residential" if fraction < 0.75 else "outskirts")


# w = frontage (along the street), d = depth, in cm; weights per zone; cap per settlement kind.
BUILDINGS = [
    {"kind": "Shop", "w": (800.0, 1200.0), "d": (900.0, 1200.0), "height": ("Mid", "High"),
     "weights": {"core": 3.0, "residential": 0.5}, "cap": {"Town": 24, "Village": 6, "Hamlet": 0}},
    {"kind": "House", "w": (800.0, 1100.0), "d": (800.0, 1100.0), "height": ("Low", "Mid"),
     "weights": {"core": 2.0, "residential": 5.0, "outskirts": 1.0}, "cap": {"Town": 150, "Village": 50, "Hamlet": 10}},
    {"kind": "Farmhouse", "w": (1000.0, 1400.0), "d": (900.0, 1200.0), "height": ("Low",),
     "weights": {"outskirts": 3.0}, "cap": {"Town": 10, "Village": 6, "Hamlet": 3}, "field": True},
    {"kind": "Barn", "w": (1400.0, 1800.0), "d": (1000.0, 1400.0), "height": ("Mid",),
     "weights": {"outskirts": 1.5}, "cap": {"Town": 6, "Village": 4, "Hamlet": 2}},
    {"kind": "Shed", "w": (500.0, 700.0), "d": (500.0, 700.0), "height": ("Low",),
     "weights": {"outskirts": 2.0, "residential": 0.3}, "cap": {"Town": 12, "Village": 6, "Hamlet": 4}},
]
LANDMARKS = [   # placed first, facing the plaza, in the widest gaps between roads and streets (w is the radial length)
    {"kind": "Church", "settlements": ("Town", "Village"), "w": 2500.0, "d": 1400.0, "height": ("High",), "tower": True},
    {"kind": "TownHall", "settlements": ("Town",), "w": 1800.0, "d": 1300.0, "height": ("High",)},
]
TOWER = {"kind": "BellTower", "height": ("Tower",)}
GROUPS = ("Low", "Mid", "High", "Tower")
HEIGHT = {"Low": 450.0, "Mid": 750.0, "High": 1050.0, "Tower": 2400.0}   # the grammar's Size per group (cm)
WALL_TOP = dict(HEIGHT)          # top of the grammar's walls per group; Task 18 replaces it with the measured tops


def pick(zone, kind, counts, rng):
    """A building type for a plot in `zone` of a `kind` settlement (weighted, below its cap), or None."""
    cands = [(b, b["weights"].get(zone, 0.0)) for b in BUILDINGS
             if b["weights"].get(zone, 0.0) > 0.0 and counts.get(b["kind"], 0) < b["cap"].get(kind, 0)]
    if not cands:
        return None
    x = rng.uniform(0.0, sum(w for _b, w in cands))
    for b, w in cands:
        x -= w
        if x <= 0.0:
            return b
    return cands[-1][0]
```

`Content/Python/pypcg/world/settle.py`:

```python
"""Settlement layout (视频步骤 6): the plaza, radial and ring streets, zones, plots and fields of one location.
Pure and 2D; the terrain work (platform, pads) is W6's."""
import math

from . import geom, rules

PLAZA_R = 1800.0
STREET_HW = 200.0
STREET_STEP = 500.0
SETBACK = {"street": 250.0, "road": 700.0}       # a road's flat corridor reaches half width + 600 (ROAD_INNER)
GAP = (300.0, 600.0)


def angle_gap(a, b):
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def pick_bearings(n, taken, rng, min_sep=35.0):
    """Up to n directions, each as far as possible from `taken` and the ones already chosen (5 degree steps from a
    random start); stops when the best is closer than min_sep to something."""
    chosen = []
    base = rng.uniform(0.0, 360.0)
    for _ in range(n):
        best = None
        for q in range(72):
            a = (base + 5.0 * q) % 360.0
            m = min([angle_gap(a, b) for b in list(taken) + chosen], default=180.0)
            if best is None or m > best[0]:
                best = (m, a)
        if best[0] < min_sep:
            break
        chosen.append(best[1])
    return chosen


def widest_gap(bearings, rng):
    if not bearings:
        return rng.uniform(0.0, 360.0)
    b = sorted(x % 360.0 for x in bearings)
    gaps = [((b[(i + 1) % len(b)] - b[i]) % 360.0 or 360.0, b[i]) for i in range(len(b))]
    g, start = max(gaps)
    return (start + 0.5 * g) % 360.0


def runs_within(pts, cx, cy, r):
    runs, cur = [], []
    for p in pts:
        if math.hypot(p[0] - cx, p[1] - cy) <= r:
            cur.append((p[0], p[1]))
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = []
    if len(cur) >= 2:
        runs.append(cur)
    return runs


class Site:
    """What a plot must keep clear of: roads and streets (with their half widths), the river (with its widths) and
    every ring already placed -- `taken` is shared by all settlements."""

    def __init__(self, roads, river, taken):
        self.roads = roads
        self.lines = geom.SegmentIndex(2000.0)
        for rd in roads:
            self.lines.add_polyline([p[:2] for p in rd["pts"]], rd["hw"])
        self.river = geom.SegmentIndex(2000.0)
        for a, b in zip(river, river[1:]):
            self.river.add(a[:2], b[:2], 0.5 * (a[3] + b[3]))
        self.taken = taken

    def add_street(self, pts):
        self.lines.add_polyline(pts, STREET_HW)

    def near_line(self, x, y, margin):
        hit = self.lines.nearest(x, y, 3000.0 + margin)
        return hit is not None and hit[0] < self.lines.payload(hit[1]) + margin

    def near_river(self, x, y, margin):
        hit = self.river.nearest(x, y, 3000.0 + margin)
        return hit is not None and hit[0] < 0.5 * self.river.payload(hit[1]) + margin

    def free(self, ring, grown, cx, cy, limit):
        for x, y in geom.probe_points(ring, 400.0):
            if math.hypot(x - cx, y - cy) > limit or self.near_line(x, y, 150.0) or self.near_river(x, y, 1000.0):
                return False
        return not self.taken.overlaps(grown)


def road_bearings(cx, cy, r, roads):
    out = []
    for rd in roads:
        for p in rd["pts"]:
            d = math.hypot(p[0] - cx, p[1] - cy)
            if 0.3 * r <= d <= 0.8 * r:
                out.append(math.degrees(math.atan2(p[1] - cy, p[0] - cx)) % 360.0)
    return out


def layout(loc, rng, site):
    cx, cy, r, kind, sid = loc["x"], loc["y"], loc["radius"], loc["kind"], loc["id"]
    n_streets, ring_street = rules.STREETS[kind]
    plaza = (cx, cy, PLAZA_R) if kind != "Hamlet" else None
    start = PLAZA_R if plaza else 600.0
    taken_bearings = road_bearings(cx, cy, r, site.roads)
    bearings = pick_bearings(n_streets, taken_bearings, rng)
    streets = []
    for a in bearings:
        ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
        pts, d = [], start
        while d <= 0.9 * r:
            x, y = cx + ux * d, cy + uy * d
            if site.near_river(x, y, 800.0):
                break
            pts.append((x, y))
            d += STREET_STEP
        if len(pts) >= 2:
            streets.append(pts)
    if ring_street:
        run = []
        for q in range(49):
            x = cx + 0.55 * r * math.cos(2.0 * math.pi * q / 48)
            y = cy + 0.55 * r * math.sin(2.0 * math.pi * q / 48)
            if site.near_river(x, y, 800.0):
                if len(run) >= 2:
                    streets.append(run)
                run = []
            else:
                run.append((x, y))
        if len(run) >= 2:
            streets.append(run)
    for st in streets:
        site.add_street(st)
    buildings, fields, counts = [], [], {}

    def place(spec, bx, by, w, d, yaw, gap, special=None):
        ring = geom.rect(bx, by, w, d, yaw)
        if not site.free(ring, geom.rect(bx, by, w + gap, d + gap, yaw), cx, cy, 0.97 * r):
            return None
        site.taken.add(ring)
        b = {"kind": spec["kind"], "group": rng.choice(spec["height"]), "ring": ring, "x": bx, "y": by, "w": w, "d": d,
             "yaw": yaw, "special": special, "settlement": sid}
        buildings.append(b)
        counts[spec["kind"]] = counts.get(spec["kind"], 0) + 1
        return b

    if plaza:
        dirs = taken_bearings + list(bearings)
        for spec in rules.LANDMARKS:
            if kind not in spec["settlements"]:
                continue
            a = widest_gap(dirs, rng)
            ux, uy = math.cos(math.radians(a)), math.sin(math.radians(a))
            off = PLAZA_R + 300.0 + 0.5 * spec["w"]
            b = place(spec, cx + ux * off, cy + uy * off, spec["w"], spec["d"], a, 300.0, spec["kind"])
            if b is not None and spec.get("tower"):
                px, py = -uy, ux
                tx = cx + ux * (PLAZA_R + 600.0) + px * (0.5 * spec["d"] + 350.0)
                ty = cy + uy * (PLAZA_R + 600.0) + py * (0.5 * spec["d"] + 350.0)
                place(rules.TOWER, tx, ty, 600.0, 600.0, a, 100.0, "BellTower")
            dirs.append(a)
    fronts = [(st, STREET_HW, "street") for st in streets]
    for rd in site.roads:
        fronts += [(run, rd["hw"], "road") for run in runs_within(rd["pts"], cx, cy, r)]
    for pts, hw, what in fronts:
        cum = geom.cumulative(pts)
        total = cum[-1]
        for side in (1.0, -1.0):
            s = 300.0
            while s < total - 300.0:
                (x, y), _yaw = geom.at_distance(pts, cum, s)
                spec = rules.pick(rules.zone_of(math.hypot(x - cx, y - cy) / r), kind, counts, rng)
                if spec is None:
                    s += 400.0
                    continue
                w, d, gap = rng.uniform(*spec["w"]), rng.uniform(*spec["d"]), rng.uniform(*GAP)
                (mx, my), yaw = geom.at_distance(pts, cum, min(total, s + 0.5 * w))
                nx, ny = -math.sin(math.radians(yaw)) * side, math.cos(math.radians(yaw)) * side
                off = hw + SETBACK[what] + 0.5 * d
                b = place(spec, mx + nx * off, my + ny * off, w, d, yaw, gap)
                if b is None:
                    s += 400.0
                    continue
                if spec.get("field"):
                    fw, fd = rng.uniform(2500.0, 4000.0), rng.uniform(3000.0, 5000.0)
                    o2 = off + 0.5 * d + 400.0 + 0.5 * fd
                    fr = geom.rect(mx + nx * o2, my + ny * o2, fw, fd, yaw)
                    if site.free(fr, fr, cx, cy, 1.3 * r):
                        site.taken.add(fr)
                        fields.append(fr)
                s += w + gap
    return {"id": sid, "kind": kind, "x": cx, "y": cy, "r": r, "plaza": plaza, "streets": streets,
            "buildings": buildings, "fields": fields}
```

`Content/Python/pypcg/stages/w06_settlements.py`:

```python
"""PyWorld W6 -- settlements (视频步骤 6：平整地形、内部路网连到最近道路、从中心向外分区、建筑规则表).

Largest first, each location gets: a platform (a plane fitted to its ground, slope clamped to MaxPlatformSlope,
kept off the roads and the river), a plaza (towns and villages), radial streets in the directions free of roads
(and a ring street in towns), the church (with its bell tower) and town hall facing the plaza, and plots along the
streets and the roads through it, typed by zone from the rule table (core: shops and houses, residential: houses,
outskirts: farmhouses with a field behind, barns, sheds). Each plot is padded flat; the road corridors are restored
on top. Footprints go to four grammar nodes by height group; foundations, pitched roofs, the spire, street modules
and plaza tiles are meshes."""
import math

from pypcg.geo import Points, Polygon, Spline
from pypcg.stage_api import Param
from pypcg.stages.w03_river import river_rows, terrain_sets
from pypcg.stages.w04_roads import road_rows
from pypcg.world import MESH, ROAD_INNER, geom, points as WP, rules, settle, terraform as T

STAGE = 106
RECORD = "w06"
DOC = """PyWorld W6 Settlements (聚落): platforms, plazas, streets, zones and plots from the building rule table;
footprints to the building grammar by height group, plus foundations, roofs, spires, street modules and plaza tiles."""
RANDOM = True
PARAMS = {"MaxPlatformSlope": Param(4.0, "Steepest slope a settlement platform keeps (degrees)", type="Double")}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Terrain", "FootprintsLow", "FootprintsMid", "FootprintsHigh", "FootprintsTower", "Parts", "Buildings",
           "Streets", "Areas", "Summary")
TYPES = {"Kind": "String", "Group": "String", "Settlement": "Int32", "W": "Double", "D": "Double", "Yaw": "Double",
         "Height": "Double"}


def _h(lat, x, y, fallback=0.0):
    h = lat.height(x, y) if lat.n else None
    return h if h is not None else fallback


def keep_fn(road_idx, river_idx):
    """1 away from roads and the river, 0 on their corridors: where the platform may work."""
    def keep(x, y):
        w = 1.0
        hit = road_idx.nearest(x, y, 3000.0)
        if hit is not None:
            hw = road_idx.payload(hit[1])
            w *= T.smoothstep(hw + ROAD_INNER, hw + 2000.0, hit[0])
        hit = river_idx.nearest(x, y, 5000.0)
        if hit is not None:
            half = 0.5 * river_idx.payload(hit[1])
            w *= T.smoothstep(half + 1000.0, half + 3000.0, hit[0])
        return w
    return keep


def roof(b, top):
    """A cube turned 45 degrees about the ridge: its upper half is a pitched roof over the shorter span."""
    length, span, ry = (b["w"], b["d"], b["yaw"]) if b["w"] >= b["d"] else (b["d"], b["w"], b["yaw"] + 90.0)
    side = (span + 60.0) / math.sqrt(2.0)
    return ((b["x"], b["y"], top), (0.0, ry, 45.0), ((length + 60.0) / 100.0, side / 100.0, side / 100.0), MESH["Cube"])


def street_modules(pts3):
    rows = []
    for a, b in zip(pts3, pts3[1:]):
        length = geom.dist2d(a, b)
        if length <= 0.0:
            continue
        rows.append((((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2 + 2.0),
                     (math.degrees(math.atan2(b[2] - a[2], length)), geom.yaw_deg(a, b), 0.0),
                     (length / 160.0 * 1.02, 2.0 * settle.STREET_HW / 300.0, 1.0), MESH["Path"]))
    return rows


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    up = inputs.get("Upstream", [])
    locs = sorted((r for v in WP.values_tagged(inputs, "Upstream", "Location") for r in WP.rows_of(v)),
                  key=lambda r: (-r["Radius"], r["Id"]))
    roads = road_rows(up)
    river = [(r[0], r[1], r[2], r[3]) for r in river_rows(up)]
    road_idx, river_idx = geom.SegmentIndex(2000.0), geom.SegmentIndex(2000.0)
    for rd in roads:
        road_idx.add_polyline([p[:2] for p in rd["pts"]], 0.5 * rd["width"])
    for a, b in zip(river, river[1:]):
        river_idx.add(a[:2], b[:2], 0.5 * (a[3] + b[3]))
    site = settle.Site([{"pts": rd["pts"], "hw": 0.5 * rd["width"]} for rd in roads], river, geom.RingIndex())
    keep = keep_fn(road_idx, river_idx)
    plans, parts, street_tables = [], [], []
    for r in locs:
        cx, cy, rad = r["loc"][0], r["loc"][1], r["Radius"]
        plan = settle.layout({"id": r["Id"], "kind": r["Kind"], "x": cx, "y": cy, "radius": rad}, ctx.rng, site)
        plans.append(plan)
        if lat.n:
            T.platform(lat, cx, cy, rad, T.fit_plane(lat, cx, cy, rad, params["MaxPlatformSlope"]), keep)
        for st in plan["streets"]:
            zs = geom.moving_average([_h(lat, x, y) for x, y in st], 3)
            pts3 = [(x, y, z) for (x, y), z in zip(st, zs)]
            if lat.n:
                T.flatten_corridor(lat, [(x, y, z, settle.STREET_HW, False) for x, y, z in pts3], 100.0, 400.0)
            parts += street_modules(pts3)
            cum = geom.cumulative(st)
            street_tables.append(([{"loc": p, "Width": 2.0 * settle.STREET_HW, "S": s} for p, s in zip(pts3, cum)]))
        if plan["plaza"]:
            zc = _h(lat, cx, cy)
            if lat.n:
                T.pad(lat, geom.circle(cx, cy, settle.PLAZA_R, 32), zc, 200.0, 600.0)
            plan["plaza_z"] = zc
            for gy in range(-12, 13):
                for gx in range(-12, 13):
                    if math.hypot(150.0 * gx, 150.0 * gy) <= settle.PLAZA_R - 75.0:
                        parts.append(((cx + 150.0 * gx, cy + 150.0 * gy, zc + 1.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0),
                                      MESH["Tile"]))
        for b in plan["buildings"]:
            zs = [z for z in (lat.height(x, y) if lat.n else None for x, y in b["ring"] + [(b["x"], b["y"])])
                  if z is not None]
            b["z"] = sum(zs) / len(zs) if zs else 0.0
            if lat.n:
                T.pad(lat, b["ring"], b["z"], 200.0, 400.0)
    if lat.n:
        for rd in sorted(roads, key=lambda r: r["cls"] != "Secondary"):
            T.flatten_corridor(lat, [(p[0], p[1], p[2], 0.5 * rd["width"], br) for p, br in zip(rd["pts"], rd["bridge"])])
    feet = {g: [] for g in rules.GROUPS}
    rows, areas, check = [], [], geom.RingIndex()
    per, overlaps, on_road = {}, 0, 0
    for plan in plans:
        per[plan["id"]] = {"kind": plan["kind"], "n": len(plan["buildings"]),
                           "churches": sum(b["kind"] == "Church" for b in plan["buildings"])}
        for b in plan["buildings"]:
            top = b["z"] + rules.WALL_TOP[b["group"]]
            ring3 = [(x, y, b["z"]) for x, y in b["ring"]]
            feet[b["group"]].append((Spline(ring3, closed=True, linear=True), ["Footprint", b["group"]]))
            areas.append((Polygon(list(b["ring"]), [], b["z"]), ["Footprint"]))
            parts.append(((b["x"], b["y"], b["z"] - 90.0), (0.0, b["yaw"], 0.0),
                          ((b["w"] + 40.0) / 100.0, (b["d"] + 40.0) / 100.0, 2.2), MESH["Cube"]))
            if b["group"] == "Tower":
                parts.append(((b["x"], b["y"], top + 400.0), (0.0, b["yaw"], 0.0), (6.4, 6.4, 8.0), MESH["Cone"]))
            else:
                parts.append(roof(b, top))
            rows.append({"loc": (b["x"], b["y"], b["z"]), "Kind": b["kind"], "Group": b["group"],
                         "Settlement": b["settlement"], "W": b["w"], "D": b["d"], "Yaw": b["yaw"],
                         "Height": rules.HEIGHT[b["group"]]})
            overlaps += check.overlaps(b["ring"])
            check.add(b["ring"])
            on_road += any(road_idx.nearest(x, y, 3000.0) is not None and
                           road_idx.nearest(x, y, 3000.0)[0] < road_idx.payload(road_idx.nearest(x, y, 3000.0)[1])
                           for x, y in geom.probe_points(b["ring"], 400.0))
        if plan["plaza"]:
            areas.append((Polygon(geom.circle(plan["x"], plan["y"], settle.PLAZA_R, 32), [], plan["plaza_z"]), ["Plaza"]))
        for fr in plan["fields"]:
            areas.append((Polygon(list(fr), [], _h(lat, *geom.centroid(fr))), ["Field"]))

    def least(kind, key="n"):
        vals = [p[key] for p in per.values() if p["kind"] in kind]
        return min(vals) if vals else -1
    summary = {"buildings": len(rows), "town_min": least(("Town",)), "village_min": least(("Village",)),
               "hamlet_min": least(("Hamlet",)), "churches_min": least(("Town", "Village"), "churches"),
               "overlaps": int(overlaps), "on_road": int(on_road), "streets": len(street_tables),
               "plazas": sum(1 for p in plans if p["plaza"]), "fields": sum(len(p["fields"]) for p in plans)}
    ctx.notes.append("%d settlements, %d buildings" % (len(plans), len(rows)))
    out = {"Terrain": [(WP.with_heights(v, lat, ks), ["Terrain"]) for v, ks in sets],
           "Parts": [(WP.mesh_points(parts), ["SettlementPart"])] if parts else [],
           "Buildings": [(WP.table_points(rows, TYPES), ["Building"])] if rows else [],
           "Streets": [(WP.table_points(t, {"Width": "Double", "S": "Double"}), ["Street"]) for t in street_tables],
           "Areas": areas, "Summary": [(WP.summary(summary), ["Summary"])]}
    for g in rules.GROUPS:
        out["Footprints" + g] = feet[g]
    return out
```

- [ ] **Step 4: Run** — PASS. If `test_village_follows_the_rules` falls short of 20 buildings, print `s` and the plan (streets count, frontage lengths) before touching any number; the rule caps are the knobs, not the test.
- [ ] **Step 5: Commit** `"PyWorld W6: settlements from the rule table"`.

---

### Task 11: 散布与 W7 植被岩石（`scatter`、`rules.BIOMES`、`w07_vegetation`）

**Files:** Modify `rules.py` (append); Create `Content/Python/pypcg/world/scatter.py`, `Content/Python/pypcg/stages/w07_vegetation.py`, `Tools/pypcg/tests/test_world_w07.py`

**Interfaces:**
- Produces in `rules`: `BIOMES {name: dict(kind, density, clump, species [(meshes, weight, (smin, smax))], sink)}`, `GRASS`, `biome_of(sample dict(z, slope, rel, acc, river)) -> name|None`, `pick_species(spec, rng) -> (mesh, scale)`.
- Produces in `scatter`: `jittered(x0, y0, x1, y1, cell, rng)`, `Exclusions(roads [(pts2, hw)], streets [(pts2, hw)], river [(x, y, water, width)], rings)` with `line_gap(x, y)`, `river_gap(x, y)`, `clear(x, y, line_margin, river_margin, ring_margin)`; `upstream_exclusions(items) -> Exclusions` (reads `Road`, `Street`, `River`, `Bridge`, `Footprint`/`Plaza`/`Field` Polygons).
- W7 outputs: `Trees` (tag `Tree`), `Rocks` (tag `Rock`), `Grass` (tag `Grass`) mesh points; `Summary` (`trees`, `rocks`, `grass`, `biome_<name>` counts, `alder_share_riparian`, `alder_share_all`, `excluded`).

- [ ] **Step 1: Failing test** `Tools/pypcg/tests/test_world_w07.py`

```python
import math

from pypcg.stages import w07_vegetation as S
from pypcg.world import MESH, scatter
from world_fixtures import Surface, run_stage, table, terrain

RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}
WT = {"Width": "Double", "WaterZ": "Double", "BedZ": "Double", "S": "Double"}


def ground(x, y):
    return 1000.0 + (0.9 * (x - 8000.0) if x > 8000.0 else 0.0) + (0.15 * (x - 2000.0) if x > 2000.0 else 0.0)


def _inputs():
    road = table([{"loc": (-12000.0, y, 1000.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": False,
                   "S": y + 23000.0} for y in range(-23000, 23001, 500)], RT, ["Road", "Main"])
    river = table([{"loc": (-4000.0, y, 950.0), "Width": 1000.0, "WaterZ": 950.0, "BedZ": 800.0, "S": y + 23000.0}
                   for y in range(-23000, 23001, 1000)], WT, ["River"])
    return {"Terrain": [(terrain(ground), frozenset())], "Surface": [(Surface(ground), frozenset())],
            "Upstream": [road, river]}


def test_biomes_exclusions_and_grounding():
    out, _ = run_stage(S, _inputs(), Seed=3)
    s = out["Summary"][0][0].values
    assert s["trees"] > 100 and s["rocks"] > 0 and s["grass"] > 0
    assert s["alder_share_riparian"] > s["alder_share_all"]
    ex = scatter.Exclusions([([(-12000.0, -23000.0), (-12000.0, 23000.0)], 400.0)], [],
                            [(-4000.0, -23000.0, 950.0, 1000.0), (-4000.0, 23000.0, 950.0, 1000.0)], [])
    trees = out["Trees"][0][0]
    for (x, y, z) in trees.loc:
        assert ex.line_gap(x, y) >= 300.0 and ex.river_gap(x, y) >= 150.0
        assert abs(z - (ground(x, y) - 15.0)) < 1e-6
    rocks = out["Rocks"][0][0]
    assert all(x > 7500.0 for x, _y, _z in rocks.loc)


def test_deterministic():
    a, _ = run_stage(S, _inputs(), Seed=5)
    b, _ = run_stage(S, _inputs(), Seed=5)
    assert a["Trees"][0][0].loc == b["Trees"][0][0].loc


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Trees"] == [] and out["Summary"][0][0].values["trees"] == 0
```

(The ground: flat west of x = 2 km, 8.5° from 2 to 8 km, 46° past 8 km → meadow / forest / rock.)

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** Append to `rules.py`:

```python
from . import MESH, SEA_Z


def _m(*keys):
    return tuple(MESH[k] for k in keys)


BIOMES = {   # density = probability per 7 m cell; clump mixes in low-frequency noise (0: none, 1: all)
    "rock": {"kind": "Rock", "density": 0.10, "clump": 0.0, "sink": 25.0,
             "species": [(_m("Boulder"), 1.0, (0.6, 1.5)), (_m("MossyRock"), 2.0, (2.0, 5.0))]},
    "riparian": {"kind": "Tree", "density": 0.30, "clump": 0.3, "sink": 15.0,
                 "species": [(_m(*("Alder" + v for v in "ABCD")), 3.0, (0.7, 1.05)),
                             (_m(*("Hazel" + v for v in "ABCD")), 2.0, (0.8, 1.2))]},
    "alpine": {"kind": "Tree", "density": 0.22, "clump": 0.4, "sink": 15.0,
               "species": [(_m("Pine"), 3.0, (0.8, 1.2)), (_m("Spruce"), 3.0, (2.2, 3.2)), (_m("YoungTree"), 1.0, (0.9, 1.3))]},
    "forest": {"kind": "Tree", "density": 0.35, "clump": 0.6, "sink": 15.0,
               "species": [(_m(*("Beech" + v for v in "ABCD")), 3.0, (0.6, 0.9)),
                           (_m(*("Maple" + v for v in "ABCD")), 2.0, (0.8, 1.1)),
                           (_m(*("Aspen" + v for v in "ABCD")), 2.0, (0.8, 1.1)),
                           (_m(*("Hazel" + v for v in "ABCD")), 1.0, (0.8, 1.2))]},
    "meadow": {"kind": "Tree", "density": 0.06, "clump": 1.0, "sink": 15.0,
               "species": [(_m(*("Birch" + v for v in "abcdefgh")), 2.0, (0.9, 1.2)),
                           (_m(*("Beech" + v for v in "ABCD")), 1.0, (0.5, 0.7)),
                           (_m(*("Aspen" + v for v in "ABCD")), 1.0, (0.8, 1.0))]},
}
GRASS = {"meshes": _m(*("Grass" + v for v in "ABDEFG")), "density": 0.35, "scale": (0.8, 1.3), "sink": 3.0}
ALDERS = frozenset(_m(*("Alder" + v for v in "ABCD")))


def biome_of(s):
    """The biome at a sample: sea, rock (> 34 deg), riparian (25 m from the bank or a gully), alpine (120 m above the
    valley floor), forest (slopes over 7 deg or 25 m up), else meadow."""
    if s["z"] < SEA_Z + 100.0:
        return None
    if s["slope"] >= 34.0:
        return "rock"
    if (s["river"] < 2500.0 and s["slope"] < 22.0) or (s["acc"] >= 300 and s["slope"] < 25.0):
        return "riparian"
    if s["rel"] >= 12000.0:
        return "alpine"
    if s["slope"] >= 7.0 or s["rel"] >= 2500.0:
        return "forest"
    return "meadow"


def pick_species(spec, rng):
    x = rng.uniform(0.0, sum(w for _m_, w, _s in spec["species"]))
    for meshes, w, (lo, hi) in spec["species"]:
        x -= w
        if x <= 0.0:
            return rng.choice(meshes), rng.uniform(lo, hi)
    meshes, _w, (lo, hi) = spec["species"][-1]
    return rng.choice(meshes), rng.uniform(lo, hi)
```

`Content/Python/pypcg/world/scatter.py`:

```python
"""Jittered-grid scattering and the exclusion zones (视频步骤 7：区域遮罩 + 散布规则；沿路清空)."""
from pypcg.geo import Points, Polygon

from . import geom


def jittered(x0, y0, x1, y1, cell, rng):
    """One uniformly jittered point per cell of a grid over the box, row by row."""
    nx, ny = int((x1 - x0) // cell), int((y1 - y0) // cell)
    for j in range(ny):
        for i in range(nx):
            yield x0 + (i + rng.random()) * cell, y0 + (j + rng.random()) * cell


class Exclusions:
    """Roads and streets (with half widths), the river (with widths) and the rings to keep clear."""

    def __init__(self, roads, streets, river, rings):
        self.lines = geom.SegmentIndex(2000.0)
        for pts, hw in list(roads) + list(streets):
            self.lines.add_polyline([p[:2] for p in pts], hw)
        self.river = geom.SegmentIndex(2000.0)
        for a, b in zip(river, river[1:]):
            self.river.add(a[:2], b[:2], 0.5 * (a[3] + b[3]))
        self.rings = geom.RingIndex()
        for r in rings:
            self.rings.add(r)

    def line_gap(self, x, y):
        hit = self.lines.nearest(x, y, 4000.0)
        return hit[0] - self.lines.payload(hit[1]) if hit else 1e9

    def river_gap(self, x, y):
        hit = self.river.nearest(x, y, 6000.0)
        return hit[0] - 0.5 * self.river.payload(hit[1]) if hit else 1e9

    def clear(self, x, y, line_margin, river_margin, ring_margin):
        return (self.line_gap(x, y) >= line_margin and self.river_gap(x, y) >= river_margin
                and not self.rings.near(x, y, ring_margin))


def upstream_exclusions(items):
    from pypcg.world import points as WP
    from pypcg.stages.w03_river import river_rows
    from pypcg.stages.w04_roads import road_rows
    from pypcg.stages.w05_bridges import bridge_rows
    roads = [(rd["pts"], 0.5 * rd["width"]) for rd in road_rows(items)]
    streets = [([r["loc"] for r in WP.rows_of(v)], 0.5 * WP.rows_of(v)[0]["Width"])
               for v, tags in items if isinstance(v, Points) and "Street" in tags and len(v)]
    river = [(r[0], r[1], r[2], r[3]) for r in river_rows(items)]
    rings = [v.outer for v, tags in items if isinstance(v, Polygon) and tags & {"Footprint", "Plaza", "Field"}]
    rings += [geom.rect(b["x"], b["y"], b["span"], b["width"] + 200.0, b["yaw"]) for b in bridge_rows(items)]
    return Exclusions(roads, streets, river, rings)
```

`Content/Python/pypcg/stages/w07_vegetation.py`:

```python
"""PyWorld W7 -- vegetation and rocks (视频步骤 7：放弃生态模拟，改用区域遮罩 + 散布规则；沿路清空；密度可控).

Data layers from the final terrain: slope, height above the valley floor (a 586 m sliding minimum) and D8 flow
accumulation (gullies). A jittered 7 m grid over the land picks a biome per sample from the rule table (rock,
riparian by the river and in gullies, alpine high up, forest on slopes, meadow with clumps of birch), keeps it with
the biome's density (x Density), clears roads, streets, the river, bridges, footprints, plazas and fields, and
places the species at the exact terrain height (the surface's own ray) sunk a little. Grass tufts on a 4.5 m grid
in meadows and by the river."""
import math

from pypcg.stage_api import Param
from pypcg.stages.w03_river import terrain_sets
from pypcg.world import hydro, noise, points as WP, rules, scatter

STAGE = 107
RECORD = "w07"
DOC = """PyWorld W7 Vegetation (植被与岩石): biome rules on slope, height above the valley, flow and the river;
jittered scattering with clearings for roads, river, bridges and settlements; trees, rocks and grass."""
RANDOM = True
PARAMS = {"Density": Param(1.0, "Multiplies every biome's density", type="Double"),
          "GrassDensity": Param(1.0, "Multiplies the grass density", type="Double"),
          "Extent": Param(135000.0, "Half size of the square that is scattered (cm)", type="Double")}
INPUTS = {"Terrain": "points", "Surface": "surface", "Upstream": "any"}
OUTPUTS = ("Trees", "Rocks", "Grass", "Summary")
BASE_CELL = 700.0
GRASS_CELL = 450.0
GRASS_HALF = 100000.0
FLOOR_CELLS = 100
CLUMP_CM = 15000.0


def _summary(**kw):
    base = {"trees": 0, "rocks": 0, "grass": 0, "alder_share_riparian": 0.0, "alder_share_all": 0.0, "excluded": 0}
    base.update({"biome_" + b: 0 for b in rules.BIOMES})
    base.update(kw)
    return [(WP.summary(base), ["Summary"])]


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    if not sets:
        return {"Trees": [], "Rocks": [], "Grass": [], "Summary": _summary()}
    surface = next((v for v, _t in inputs.get("Surface", []) if hasattr(v, "height")), None)
    slope = [lat.slope_deg(k) if z is not None else None for k, z in enumerate(lat.z)]
    floor = hydro.min_filter(lat, FLOOR_CELLS)
    acc = hydro.flow_accumulation(lat)
    ex = scatter.upstream_exclusions(inputs.get("Upstream", []))
    rng, seed = ctx.rng, ctx.seed
    half = (lat.n - 1) * lat.s / 2.0
    cx, cy = lat.x0 + half, lat.y0 + half
    e = min(params["Extent"], half)
    trees, rocks, grass, counts = [], [], [], {b: 0 for b in rules.BIOMES}
    alder = {"riparian": 0, "all": 0}
    excluded = 0

    def sample(x, y):
        k = lat.nearest(x, y)
        if k is None:
            return None
        return {"z": lat.z[k], "slope": slope[k], "rel": lat.z[k] - floor[k], "acc": acc[k], "river": ex.river_gap(x, y)}

    def height(x, y):
        h = surface.height(x, y) if surface is not None else None
        return h if h is not None else lat.height(x, y)
    for x, y in scatter.jittered(cx - e, cy - e, cx + e, cy + e, BASE_CELL, rng):
        s = sample(x, y)
        b = rules.biome_of(s) if s else None
        if b is None:
            continue
        spec = rules.BIOMES[b]
        clump = noise.value(x / CLUMP_CM, y / CLUMP_CM, seed + 3)
        p = spec["density"] * ((1.0 - spec["clump"]) + spec["clump"] * 2.0 * clump) * params["Density"]
        if rng.random() >= p:
            continue
        tree = spec["kind"] == "Tree"
        if not ex.clear(x, y, 300.0 if tree else 150.0, 150.0 if tree else 0.0, 300.0 if tree else 150.0):
            excluded += 1
            continue
        mesh, sc = rules.pick_species(spec, rng)
        h = height(x, y)
        if h is None:
            continue
        yaw = rng.uniform(0.0, 360.0)
        if tree:
            trees.append(((x, y, h - spec["sink"]), (0.0, yaw, 0.0), (sc, sc, sc), mesh))
            alder["all"] += mesh in rules.ALDERS
            if b == "riparian":
                alder["riparian"] += mesh in rules.ALDERS
        else:
            rocks.append(((x, y, h - spec["sink"]), (rng.uniform(-8.0, 8.0), yaw, rng.uniform(-8.0, 8.0)), (sc, sc, sc), mesh))
        counts[b] += 1
    g = rules.GRASS
    ge = min(GRASS_HALF, half)
    for x, y in scatter.jittered(cx - ge, cy - ge, cx + ge, cy + ge, GRASS_CELL, rng):
        s = sample(x, y)
        if not s or rules.biome_of(s) not in ("meadow", "riparian") or s["slope"] >= 15.0:
            continue
        c2 = noise.value(x / 4000.0, y / 4000.0, seed + 7)
        if rng.random() >= g["density"] * params["GrassDensity"] * (0.4 + 0.6 * c2):
            continue
        if not ex.clear(x, y, 50.0, 0.0, 100.0):
            continue
        h = height(x, y)
        if h is None:
            continue
        sc = rng.uniform(*g["scale"])
        grass.append(((x, y, h - g["sink"]), (0.0, rng.uniform(0.0, 360.0), 0.0), (sc, sc, sc), rng.choice(g["meshes"])))
    n_rip = counts["riparian"]
    summary = dict(trees=len(trees), rocks=len(rocks), grass=len(grass), excluded=excluded,
                   alder_share_riparian=alder["riparian"] / n_rip if n_rip else 0.0,
                   alder_share_all=alder["all"] / len(trees) if trees else 0.0,
                   **{"biome_" + b: n for b, n in counts.items()})
    ctx.notes.append("%d trees, %d rocks, %d grass" % (len(trees), len(rocks), len(grass)))
    return {"Trees": [(WP.mesh_points(trees), ["Tree"])] if trees else [],
            "Rocks": [(WP.mesh_points(rocks), ["Rock"])] if rocks else [],
            "Grass": [(WP.mesh_points(grass), ["Grass"])] if grass else [], "Summary": _summary(**summary)}
```

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `"PyWorld W7: biome rules, clearings and scattering"`.

---

### Task 12: W8 沿路道具（`w08_props`）

**Files:** Create `Content/Python/pypcg/stages/w08_props.py`, `Tools/pypcg/tests/test_world_w08.py`

**Interfaces:**
- Consumes: `road_rows`, W2 `Location`, W6 `Street` tables and `Plaza` Polygons, a surface.
- Produces: `Props` (tag `Prop`, mesh points), `Summary` (`poles`, `wire_segments`, `lamps`, `rails`, `benches`, `pole_spacing_mean_m`). Functions `wire(a, b, sag) -> rows`, `z_at(pts, cum, s)`.

- [ ] **Step 1: Failing test** `Tools/pypcg/tests/test_world_w08.py`

```python
from pypcg.geo import Polygon
from pypcg.stages import w08_props as S
from pypcg.world import geom
from world_fixtures import Surface, run_stage, table

RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}


def _road():
    return table([{"loc": (x, 0.0, 1000.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": False,
                   "S": x + 20000.0} for x in range(-20000, 20001, 500)], RT, ["Road", "Main"])


def _street():
    return table([{"loc": (x, 8000.0, 1000.0), "Width": 400.0, "S": float(x)} for x in range(0, 6001, 500)],
                 {"Width": "Double", "S": "Double"}, ["Street"])


def test_poles_wires_lamps_benches():
    plaza = (Polygon(geom.circle(0.0, -8000.0, 1800.0, 32), [], 1000.0), frozenset(["Plaza"]))
    out, _ = run_stage(S, {"Surface": [(Surface(lambda x, y: 1000.0), frozenset())],
                           "Upstream": [_road(), _street(), plaza]})
    s = out["Summary"][0][0].values
    assert s["poles"] == 11 and abs(s["pole_spacing_mean_m"] - 40.0) < 1e-6
    assert s["wire_segments"] == 10 * 2 * 16 and s["lamps"] == 3 and s["benches"] == 6 and s["rails"] == 0


def test_rails_where_the_road_is_on_an_embankment():
    out, _ = run_stage(S, {"Surface": [(Surface(lambda x, y: 1000.0 if abs(y) < 500.0 else 700.0), frozenset())],
                           "Upstream": [_road()]})
    assert out["Summary"][0][0].values["rails"] > 150


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Props"] == [] and out["Summary"][0][0].values["poles"] == 0
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `Content/Python/pypcg/stages/w08_props.py`:

```python
"""PyWorld W8 -- props along the roads (视频：最早的工具是电线杆间的电线；道路轨迹复用于电线、旗子).

The road polylines are reused: a power pole every PoleSpacing on the right of every road outside settlements and off
bridges, two wires sagging between consecutive poles (a parabola, a thin box every 2.5 m), guard rails where the
ground 3 m beside the road drops or rises more than RailDrop, street lamps along settlement streets and benches
around the plazas."""
import bisect
import math

from pypcg.geo import Points, Polygon
from pypcg.stage_api import Param
from pypcg.stages.w04_roads import road_rows
from pypcg.world import MESH, geom, points as WP

STAGE = 108
RECORD = "w08"
DOC = """PyWorld W8 Props (沿路道具): power poles and wires along the roads, guard rails on embankments, street
lamps in the settlements and benches round the plazas."""
RANDOM = False
PARAMS = {"PoleSpacing": Param(4000.0, "Distance between power poles (cm)", type="Double"),
          "LampSpacing": Param(3000.0, "Distance between street lamps (cm)", type="Double"),
          "Sag": Param(80.0, "Wire sag at mid span (cm)", type="Double"),
          "RailDrop": Param(150.0, "Height difference beside the road that calls for a rail (cm)", type="Double")}
INPUTS = {"Surface": "surface", "Upstream": "any"}
OUTPUTS = ("Props", "Summary")
POLE_H = 900.0
ARM = 70.0
WIRE_STEP = 250.0
RAIL_CM = 400.0


def z_at(pts, cum, s):
    s = min(max(s, 0.0), cum[-1])
    i = min(max(bisect.bisect_right(cum, s) - 1, 0), len(pts) - 2)
    span = cum[i + 1] - cum[i]
    t = 0.0 if span == 0 else (s - cum[i]) / span
    return pts[i][2] + (pts[i + 1][2] - pts[i][2]) * t, i


def wire(a, b, sag):
    """Thin boxes along a parabola from a to b (3D), one per WIRE_STEP of horizontal length."""
    m = max(1, int(math.ceil(geom.dist2d(a, b) / WIRE_STEP)))
    pts = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t - 4.0 * sag * t * (1.0 - t))
           for t in (q / m for q in range(m + 1))]
    rows = []
    for p, q in zip(pts, pts[1:]):
        dx, dy, dz = q[0] - p[0], q[1] - p[1], q[2] - p[2]
        h = math.hypot(dx, dy)
        rows.append((((p[0] + q[0]) / 2, (p[1] + q[1]) / 2, (p[2] + q[2]) / 2),
                     (math.degrees(math.atan2(dz, h)), math.degrees(math.atan2(dy, dx)), 0.0),
                     (math.hypot(h, dz) / 100.0, 0.03, 0.03), MESH["Cube"]))
    return rows


def run(inputs, params, ctx):
    up = inputs.get("Upstream", [])
    surface = next((v for v, _t in inputs.get("Surface", []) if hasattr(v, "height")), None)
    locs = [(r["loc"][0], r["loc"][1], r["Radius"]) for v in WP.values_tagged(inputs, "Upstream", "Location")
            for r in WP.rows_of(v)]

    def ground(x, y, fallback):
        h = surface.height(x, y) if surface is not None else None
        return h if h is not None else fallback

    def in_town(x, y):
        return any(math.hypot(x - lx, y - ly) < lr for lx, ly, lr in locs)
    rows, poles, wires, rails, spacings = [], 0, 0, 0, []
    for rd in road_rows(up):
        pts = rd["pts"]
        pts2 = [p[:2] for p in pts]
        cum = geom.cumulative(pts2)
        hw = 0.5 * rd["width"]
        near_bridge = lambda i: any(rd["bridge"][q] for q in range(max(0, i - 2), min(len(pts), i + 4)))
        run_, s = [], 0.0

        def flush():
            nonlocal wires
            for (pa, na), (pb, nb) in zip(run_, run_[1:]):
                spacings.append(geom.dist2d(pa, pb))
                for side in (1.0, -1.0):
                    w = wire((pa[0] + na[0] * side * ARM, pa[1] + na[1] * side * ARM, pa[2]),
                             (pb[0] + nb[0] * side * ARM, pb[1] + nb[1] * side * ARM, pb[2]), params["Sag"])
                    rows.extend(w)
                    wires += len(w)
            run_.clear()
        while s <= cum[-1] + 1e-6:
            (x, y), yaw = geom.at_distance(pts2, cum, s)
            zr, i = z_at(pts, cum, s)
            if near_bridge(i) or in_town(x, y):
                flush()
                s += params["PoleSpacing"]
                continue
            nx, ny = -math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
            px, py = x - nx * (hw + 250.0), y - ny * (hw + 250.0)
            z0 = ground(px, py, zr)
            rows.append(((px, py, z0 + 0.5 * POLE_H - 30.0), (0.0, 0.0, 0.0), (0.28, 0.28, POLE_H / 100.0), MESH["Cylinder"]))
            rows.append(((px, py, z0 + POLE_H - 70.0), (0.0, yaw + 90.0, 0.0), (1.6, 0.12, 0.12), MESH["Cube"]))
            run_.append(((px, py, z0 + POLE_H - 60.0), (nx, ny)))
            poles += 1
            s += params["PoleSpacing"]
        flush()
        s = 0.0
        while s <= cum[-1]:
            (x, y), yaw = geom.at_distance(pts2, cum, s)
            zr, i = z_at(pts, cum, s)
            if not near_bridge(i) and not in_town(x, y):
                nx, ny = -math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
                pitch = math.degrees(math.atan2(pts[i + 1][2] - pts[i][2], max(cum[i + 1] - cum[i], 1e-6)))
                for side in (1.0, -1.0):
                    g = ground(x + nx * side * (hw + 300.0), y + ny * side * (hw + 300.0), zr)
                    if abs(g - zr) > params["RailDrop"]:
                        rows.append(((x + nx * side * (hw + 50.0), y + ny * side * (hw + 50.0), zr), (pitch, yaw, 0.0),
                                     (1.0, 1.0, 1.0), MESH["Rail"]))
                        rails += 1
            s += RAIL_CM
    lamps = 0
    for v, tags in up:
        if not (isinstance(v, Points) and "Street" in tags and len(v) > 1):
            continue
        st = sorted(WP.rows_of(v), key=lambda r: r["S"])
        pts2 = [r["loc"][:2] for r in st]
        cum = geom.cumulative(pts2)
        hw = 0.5 * st[0]["Width"]
        s, side = 0.0, 1.0
        while s <= cum[-1] + 1e-6:
            (x, y), yaw = geom.at_distance(pts2, cum, s)
            nx, ny = -math.sin(math.radians(yaw)) * side, math.cos(math.radians(yaw)) * side
            lx, ly = x + nx * (hw + 80.0), y + ny * (hw + 80.0)
            rows.append(((lx, ly, ground(lx, ly, st[0]["loc"][2])), (0.0, yaw - 90.0 * side, 0.0), (1.0, 1.0, 1.0), MESH["Lamp"]))
            lamps += 1
            s += params["LampSpacing"]
            side = -side
    benches = 0
    for v, tags in up:
        if isinstance(v, Polygon) and "Plaza" in tags:
            cx, cy = geom.centroid(v.outer)
            rad = sum(geom.dist2d((cx, cy), p) for p in v.outer) / len(v.outer) - 250.0
            for q in range(6):
                a = 60.0 * q
                bx, by = cx + rad * math.cos(math.radians(a)), cy + rad * math.sin(math.radians(a))
                rows.append(((bx, by, ground(bx, by, v.z)), (0.0, a + 90.0, 0.0), (1.0, 1.0, 1.0), MESH["Bench"]))
                benches += 1
    summary = {"poles": poles, "wire_segments": wires, "lamps": lamps, "rails": rails, "benches": benches,
               "pole_spacing_mean_m": (sum(spacings) / len(spacings) / 100.0) if spacings else 0.0}
    return {"Props": [(WP.mesh_points(rows), ["Prop"])] if rows else [], "Summary": [(WP.summary(summary), ["Summary"])]}
```

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `"PyWorld W8: poles, wires, rails, lamps and benches"`.

---

### Task 13: W9 地表材质（`w09_surface`）

**Files:** Create `Content/Python/pypcg/stages/w09_surface.py`, `Tools/pypcg/tests/test_world_w09.py`

**Interfaces:**
- Consumes: terrain points, `road_rows`, `river_rows`, `Street` tables, `Plaza`/`Field` Polygons, `Tree` mesh points.
- Produces: `Terrain` (positions unchanged; one Float attribute per channel of `CHANNELS`, summing to 1), `Summary` (`channels`, `weight_sum_err_max`, `cover_<channel>` means). Function `weights(sample) -> dict`.

- [ ] **Step 1: Failing test** `Tools/pypcg/tests/test_world_w09.py`

```python
from pypcg.geo import Polygon
from pypcg.stages import w09_surface as S
from pypcg.world import CHANNELS, MESH, geom, points as WP
from world_fixtures import run_stage, table, terrain

RT = {"RoadId": "Int32", "Class": "String", "Width": "Double", "Bridge": "Bool", "S": "Double"}
WT = {"Width": "Double", "WaterZ": "Double", "BedZ": "Double", "S": "Double"}


def ground(x, y):
    return 1000.0 + (1.5 * (x - 15000.0) if x > 15000.0 else 0.0)


def test_channels():
    road = table([{"loc": (x, -10000.0, 1000.0), "RoadId": 0, "Class": "Main", "Width": 800.0, "Bridge": False,
                   "S": x + 23000.0} for x in range(-23000, 23001, 500)], RT, ["Road", "Main"])
    river = table([{"loc": (-15000.0, y, 950.0), "Width": 1200.0, "WaterZ": 950.0, "BedZ": 800.0, "S": y + 23000.0}
                   for y in range(-23000, 23001, 1000)], WT, ["River"])
    trees = (WP.mesh_points([((x, y, 1000.0), (0, 0, 0), (1, 1, 1), MESH["BeechA"])
                             for x in range(0, 6000, 400) for y in range(4000, 10000, 400)]), frozenset(["Tree"]))
    field = (Polygon(geom.rect(8000.0, -18000.0, 3000.0, 3000.0, 0.0), [], 1000.0), frozenset(["Field"]))
    out, _ = run_stage(S, {"Terrain": [(terrain(ground), frozenset())], "Upstream": [road, river, trees, field]})
    t = out["Terrain"][0][0]
    at = {(round(p[0]), round(p[1])): i for i, p in enumerate(t.loc)}

    def w(x, y):
        i = at[(round(x), round(y))]
        return {c: t.attrs[c][i] for c in CHANNELS}
    assert all(t.types[c] == "Float" for c in CHANNELS)
    assert w(0.0, -9960.9375)["Dirt"] > 0.9                           # on the road
    assert w(-14648.4375, 0.0)["Gravel"] > 0.9                        # river bed
    assert w(21094.0, 0.0)["Rock"] > 0.9                              # 56 degrees
    assert w(2930.0, 7031.0)["ForestFloor"] > 0.5
    assert w(-21094.0, 21094.0)["Grass"] > 0.99
    s = out["Summary"][0][0].values
    assert s["channels"] == 6 and s["weight_sum_err_max"] < 1e-6


def test_empty_inputs():
    out, _ = run_stage(S, {})
    assert out["Terrain"] == [] and out["Summary"][0][0].values["channels"] == 0
```

Lattice coordinates: the fixture's vertices sit on multiples of 585.9375; the test looks up `round(x)` of those multiples (`-9961`, `21094`, `2930`, `7031`, `-21094`) — adjust any key the run reports missing to the nearest multiple rather than changing the stage.

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement** `Content/Python/pypcg/stages/w09_surface.py`:

```python
"""PyWorld W9 -- the surface materials (视频步骤 9：道路、河流、平整、手绘的遮罩合成地表材质).

One weight per material channel of the mesh terrain (MPD_Basic: Grass, Rock, ForestFloor, Dirt, Mud, Gravel) for
every vertex: Rock with slope (RockSlopeStart..RockSlopeFull), ForestFloor where W7's trees stand dense, Dirt on roads,
streets, plazas and fields, Mud on the river banks, Gravel in the river bed and on the main roads' shoulders, Grass
for the rest; the weights sum to 1. The native writer paints them (Write_MeshTerrain, Channels)."""
from pypcg.geo import Points, Polygon
from pypcg.stage_api import Param
from pypcg.stages.w03_river import river_rows, terrain_sets
from pypcg.stages.w04_roads import road_rows
from pypcg.world import CHANNELS, geom, points as WP
from pypcg.world.terraform import smoothstep

STAGE = 109
RECORD = "w09"
DOC = """PyWorld W9 Surface (地表材质): Grass, Rock, ForestFloor, Dirt, Mud and Gravel weights per vertex from the
slope, the trees, the roads, streets, plazas, fields and the river."""
RANDOM = False
PARAMS = {"RockSlopeStart": Param(28.0, "Slope where rock starts showing (degrees)", type="Double"),
          "RockSlopeFull": Param(40.0, "Slope that is all rock (degrees)", type="Double"),
          "ForestCell": Param(2000.0, "Cell over which tree density is counted (cm)", type="Double")}
INPUTS = {"Terrain": "points", "Upstream": "any"}
OUTPUTS = ("Terrain", "Summary")


def compose(raw):
    """raw {channel: 0..1} without Grass -> weights summing to 1, Grass taking what is left."""
    total = sum(raw.values())
    if total > 1.0:
        out = {c: v / total for c, v in raw.items()}
        out["Grass"] = 0.0
    else:
        out = dict(raw)
        out["Grass"] = 1.0 - total
    return out


def run(inputs, params, ctx):
    lat, sets = terrain_sets(inputs.get("Terrain", []))
    if not sets:
        return {"Terrain": [], "Summary": [(WP.summary({"channels": 0, "weight_sum_err_max": 0.0}), ["Summary"])]}
    up = inputs.get("Upstream", [])
    lines = geom.SegmentIndex(2000.0)
    for rd in road_rows(up):
        lines.add_polyline([p[:2] for p in rd["pts"]], (0.5 * rd["width"], rd["cls"] == "Main"))
    for v, tags in up:
        if isinstance(v, Points) and "Street" in tags and len(v) > 1:
            lines.add_polyline([p[:2] for p in v.loc], (0.5 * v.attrs["Width"][0], False))
    river = geom.SegmentIndex(2000.0)
    rr = river_rows(up)
    for a, b in zip(rr, rr[1:]):
        river.add(a[:2], b[:2], 0.5 * (a[3] + b[3]))
    plazas, fields = geom.RingIndex(), geom.RingIndex()
    for v, tags in up:
        if isinstance(v, Polygon):
            if "Plaza" in tags:
                plazas.add(v.outer)
            elif "Field" in tags:
                fields.add(v.outer)
    cell = params["ForestCell"]
    buckets = {}
    for v, tags in up:
        if isinstance(v, Points) and "Tree" in tags:
            for x, y, _z in v.loc:
                key = (int(x // cell), int(y // cell))
                buckets[key] = buckets.get(key, 0) + 1
    cache = {}

    def weights(k):
        if k in cache:
            return cache[k]
        x, y = lat.xy(k)
        rock = smoothstep(params["RockSlopeStart"], params["RockSlopeFull"], lat.slope_deg(k))
        dirt = gravel = mud = 0.0
        hit = lines.nearest(x, y, 1500.0)
        if hit is not None:
            hw, main = lines.payload(hit[1])
            dirt = 1.0 - smoothstep(hw + 100.0, hw + 500.0, hit[0])
            if main and hw <= hit[0] < hw + 150.0:
                gravel = 0.6
        if plazas.contains(x, y):
            dirt = 1.0
        elif fields.contains(x, y):
            dirt = max(dirt, 0.8)
        hit = river.nearest(x, y, 4000.0)
        if hit is not None:
            half = river.payload(hit[1])
            if hit[0] < half:
                gravel = 1.0
            else:
                mud = 1.0 - smoothstep(half, half + 600.0, hit[0])
        bx, by = int(x // cell), int(y // cell)
        dens = sum(buckets.get((bx + i, by + j), 0) for i in (-1, 0, 1) for j in (-1, 0, 1)) / 9.0
        ff = smoothstep(1.0, 4.0, dens)
        w = compose({"Rock": rock, "ForestFloor": ff * (1.0 - rock), "Dirt": dirt, "Mud": mud * (1.0 - dirt),
                     "Gravel": gravel})
        cache[k] = w
        return w
    out, err, cover, n = [], 0.0, {c: 0.0 for c in CHANNELS}, 0
    for v, ks in sets:
        cols = {c: [] for c in CHANNELS}
        for k in ks:
            w = weights(k)
            for c in CHANNELS:
                cols[c].append(w[c])
                cover[c] += w[c]
            err = max(err, abs(sum(w.values()) - 1.0))
            n += 1
        out.append((WP.with_heights(v, lat, ks, {c: ("Float", cols[c]) for c in CHANNELS}), ["Terrain"]))
    summary = {"channels": len(CHANNELS), "weight_sum_err_max": err}
    summary.update({"cover_" + c: cover[c] / n for c in CHANNELS})
    return {"Terrain": out, "Summary": [(WP.summary(summary), ["Summary"])]}
```

- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `"PyWorld W9: surface material weights"`.

---
### Task 14: 验收规则与 9 张图的描述（`checks`、`graphs`、库条目）

**Files:** Create `Content/Python/pypcg/world/checks.py`, `Content/Python/pypcg/world/graphs.py`, `Tools/pypcg/tests/test_world_graphs.py`; Modify `Content/Python/pypcg/library.json` (add `Transform_MeshTerrain_Erosion`), `Content/Python/pypcg_library.py` (`EXTRA_SUBGRAPHS`)

**Interfaces:**
- Produces: `checks.accept(n, summary, extra) -> [failure strings]`; `checks.intrusions(points, exclusions) -> dict(on_line, in_river, in_ring)`; `checks.crossings(roads, river) -> int`; `checks.roads_connected(roads, nodes) -> bool`; `checks.max_grades(roads) -> {cls: grade}`; `graphs.graph(n) -> dsl.SlimGraph`, `graphs.GRAPHS`.
- Graph wiring (per spec §2.2): every terrain read/write uses `W.TERRAIN`; upstream reads are `Get_ActorData` by `PyWorld_WNN`; spawners `Spawn_Assets(UseMeshAttribute, MeshAttribute "Mesh")`.

- [ ] **Step 1: Failing test** `Tools/pypcg/tests/test_world_graphs.py`

```python
import pytest

from pypcg import ir, stage_api, world as W
from pypcg.world import checks, graphs


@pytest.mark.parametrize("n", range(1, 10))
def test_graph_description(n):
    out = graphs.graph(n).to_ir(None)                  # raises on an unwired Python input pin
    assert out["graph"] == W.name(n) and out["params"][0]["name"] == stage_api.SEED
    py = [x for x in out["nodes"] if x["class"] == ir.PYTHON_NODE]
    assert len(py) == 1
    used = {(src, pin) for x in out["nodes"] for p in x.get("inputs", []) for src, pin in p["edges"]}
    for pin in py[0]["settings"]["OutputDynamicPins"]:
        assert (py[0]["name"], pin) in used, pin
    getters = {x["getter_param"] for x in out["nodes"] if x.get("getter_param")}
    assert {p["name"] for p in out["params"]} <= getters


def _subs(n, alias):
    return [x for x in graphs.graph(n).to_ir(None)["nodes"] if (x.get("subgraph") or "").endswith(alias + "." + alias)]


def test_terrain_priorities():
    for n, (query, read_sub, write_sub) in W.TERRAIN.items():
        get = _subs(n, "Get_MeshTerrain")[0]["overrides"]
        assert get.get("MeshPartitionQueryType", "Base") == query and get.get("ModifierSubPriority", 0) == read_sub
        assert _subs(n, "Write_MeshTerrain")[0]["overrides"]["ModifierSubPriority"] == write_sub
    assert _subs(9, "Write_MeshTerrain")[0]["overrides"]["Channels"] == list(W.CHANNELS)
    for n in (2, 7, 8):
        assert _subs(n, "Get_MeshTerrain")[0]["overrides"]["MeshPartitionQueryType"] == "Final"


def test_acceptance_rules():
    good4 = {"connected": True, "unreachable": 0, "max_grade_main": 0.1, "max_grade_secondary": 0.13, "roads": 6}
    assert checks.accept(4, good4, {"instances": 10}) == []
    bad = dict(good4, connected=False, max_grade_main=0.2)
    assert len(checks.accept(4, bad, {"instances": 0})) == 3
    assert checks.accept(6, None, {}) == ["no Summary: the Python node did not run or its record is missing"]


def test_world_checks():
    roads = [{"cls": "Main", "width": 800.0, "pts": [(0.0, 0.0, 0.0), (1000.0, 0.0, 50.0)], "bridge": [False, False]},
             {"cls": "Secondary", "width": 500.0, "pts": [(500.0, 0.0, 25.0), (500.0, 900.0, 25.0)], "bridge": [False, False]}]
    river = [(-100.0, 500.0, 0.0, 600.0), (2000.0, 500.0, 0.0, 600.0)]
    assert checks.crossings(roads, river) == 1
    assert checks.roads_connected(roads, [(0.0, 0.0, 100.0), (500.0, 900.0, 100.0)])
    assert not checks.roads_connected(roads, [(5000.0, 5000.0, 100.0)])
    assert abs(checks.max_grades(roads)["Main"] - 0.05) < 1e-12
```

- [ ] **Step 2: Run** — FAIL.
- [ ] **Step 3: Implement.** First add the erosion primitive to the library, with the pins and parameters the 2026-10-22 probe (`pyworld_probe_assets.py`) read from the asset:

```bash
C:/Python314/python.exe -c "import json; p='Content/Python/pypcg/library.json'; d=json.load(open(p,encoding='utf-8')); params={'InputsProcessingGraph':'SoftObject','InputsFallbackGraph':'SoftObject','CoreProcessGraph':'SoftObject','PrepareOutputsGraph':'SoftObject','ErosionOctaves':'Int32','ErosionScale':'Double','ErosionGain':'Double','ErosionLacunarity':'Double','ErosionStrength':'Double','ErosionSlopeStength':'Double','ErosionBranchStrength':'Double','MaskAttribute':'String'}; d['subgraphs']['Transform_MeshTerrain_Erosion']={'path':'/PCGPrimitives_MeshPartitionInterop/Primitives/Transform/Transform_MeshTerrain_Erosion.Transform_MeshTerrain_Erosion','inputs':sorted(list(params)+['PrimaryInput','Execution Dependency','Overrides','SubgraphOverride']),'outputs':['Out'],'params':params}; f=open(p,'w',encoding='utf-8'); json.dump(d,f,indent=1,sort_keys=True,ensure_ascii=False); f.write('\n')"
```

In `pypcg_library.py`, after `EXTRA_CLASSES`, add

```python
# Subgraphs no official stage graph uses but PyWorld does (pypcg/world/graphs.py).
EXTRA_SUBGRAPHS = ("/PCGPrimitives_MeshPartitionInterop/Primitives/Transform/Transform_MeshTerrain_Erosion."
                   "Transform_MeshTerrain_Erosion",)
```

and before `tmp = unreal.new_object(...)` add

```python
    for path in EXTRA_SUBGRAPHS:
        seen_sub.setdefault(pir.alias_of(path), {"path": path, "inputs": set(), "outputs": set()})
```

(Task 15 regenerates the library in the editor; `git diff` then shows whether the hand-written entry matched.)

`Content/Python/pypcg/world/checks.py`:

```python
"""Acceptance of each PyWorld step (spec §5) and the world checks of W10. Pure."""
import math

from . import geom, layout, rules


def accept(n, s, extra=None):
    """Failures of step n from its Summary `s` and the driver's measurements `extra` ({"instances": int, ...});
    [] passes."""
    if not s:
        return ["no Summary: the Python node did not run or its record is missing"]
    extra = extra or {}
    inst = extra.get("instances", 0)
    f = []

    def need(ok, msg):
        if not ok:
            f.append(msg)
    if n == 1:
        need(s["points"] > 0 and s["nan"] == 0, "terrain: %d vertices, %d NaN" % (s["points"], s["nan"]))
        need(s["floor_err_max_cm"] <= 500.0, "valley floor off its axis height by %.0f cm" % s["floor_err_max_cm"])
        need(s["ridge_max_cm"] >= 12000.0, "ridges only %.0f cm high" % s["ridge_max_cm"])
        if extra.get("traced_floor_err_cm") is not None:
            need(extra["traced_floor_err_cm"] <= 800.0, "traced floor off by %.0f cm" % extra["traced_floor_err_cm"])
    elif n == 2:
        need(s["locations"] == len(layout.LOCATIONS), "locations %d" % s["locations"])
        need(s["river_ends"] == 2 and s["exits"] == 2, "river ends %d, exits %d" % (s["river_ends"], s["exits"]))
        need(s["off_terrain"] == 0, "%d locations off the terrain" % s["off_terrain"])
        need(s["max_center_slope_deg"] <= 6.0, "a location centre slopes %.1f deg" % s["max_center_slope_deg"])
    elif n == 3:
        need(s["length_m"] >= 1500.0, "river only %.0f m" % s["length_m"])
        need(s["monotone"], "water line rises somewhere")
        need(s["carved"] > 0, "nothing carved")
        need(inst > 0, "no water surface instances")
    elif n == 4:
        need(s["connected"] and s["unreachable"] == 0, "network not connected (%d unreachable)" % s["unreachable"])
        need(s["max_grade_main"] <= 0.10 + 1e-6 and s["max_grade_secondary"] <= 0.14 + 1e-6,
             "grades %.3f / %.3f" % (s["max_grade_main"], s["max_grade_secondary"]))
        need(inst > 0, "no road instances")
    elif n == 5:
        need(s["bridges"] >= 1 and s["bridges"] == s["crossings"], "bridges %d for %d crossings" % (s["bridges"], s["crossings"]))
        need(inst > 0, "no bridge instances")
    elif n == 6:
        for key, kind in (("town_min", "Town"), ("village_min", "Village"), ("hamlet_min", "Hamlet")):
            need(s[key] == -1 or s[key] >= rules.MIN_BUILDINGS[kind], "%s %d < %d" % (key, s[key], rules.MIN_BUILDINGS[kind]))
        need(s["churches_min"] >= 1, "a town or village without its church")
        need(s["overlaps"] == 0 and s["on_road"] == 0, "overlaps %d, on roads %d" % (s["overlaps"], s["on_road"]))
        need(inst > 0, "no settlement instances")
    elif n == 7:
        need(s["trees"] >= 20000, "only %d trees" % s["trees"])
        need(s["alder_share_riparian"] > s["alder_share_all"], "alders not concentrated by the river")
        need(inst > 0, "no vegetation instances")
    elif n == 8:
        need(s["poles"] > 0 and s["wire_segments"] > 0, "no poles or wires")
        need(35.0 <= s["pole_spacing_mean_m"] <= 45.0, "pole spacing %.1f m" % s["pole_spacing_mean_m"])
        need(inst > 0, "no prop instances")
    elif n == 9:
        need(s["channels"] == 6 and s["weight_sum_err_max"] < 1e-3, "channels %d, weight error %g" % (s["channels"], s["weight_sum_err_max"]))
    return f


def intrusions(points, exclusions):
    """How many points stand on a road or street, in the river, or inside a footprint, plaza, field or bridge."""
    out = {"on_line": 0, "in_river": 0, "in_ring": 0}
    for p in points:
        out["on_line"] += exclusions.line_gap(p[0], p[1]) < 0.0
        out["in_river"] += exclusions.river_gap(p[0], p[1]) < 0.0
        out["in_ring"] += bool(exclusions.rings.contains(p[0], p[1]))
    return out


def crossings(roads, river):
    rp = [r[:2] for r in river]
    return sum(len(geom.polyline_intersections([p[:2] for p in rd["pts"]], rp)) for rd in roads) if len(rp) > 1 else 0


def roads_connected(roads, nodes, touch=300.0):
    """Every node (x, y, radius) has a road point within its radius, and the roads form one network (two roads touch
    where a point of one is within `touch` of the other)."""
    idx = [geom.SegmentIndex(2000.0) for _ in roads]
    for i, rd in enumerate(roads):
        idx[i].add_polyline([p[:2] for p in rd["pts"]])
    parent = list(range(len(roads)))

    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for i, a in enumerate(roads):
        for j in range(len(roads)):
            if j != i and any(idx[j].nearest(p[0], p[1], touch) for p in a["pts"]):
                parent[find(i)] = find(j)
    if len({find(i) for i in range(len(roads))}) > 1:
        return False
    return all(any(math.hypot(p[0] - x, p[1] - y) <= r for rd in roads for p in rd["pts"]) for x, y, r in nodes)


def max_grades(roads):
    out = {}
    for rd in roads:
        g = 0.0
        for a, b in zip(rd["pts"], rd["pts"][1:]):
            d = geom.dist2d(a, b)
            if d > 1.0:
                g = max(g, abs(b[2] - a[2]) / d)
        out[rd["cls"]] = max(out.get(rd["cls"], 0.0), g)
    return out
```

`Content/Python/pypcg/world/graphs.py`:

```python
"""The nine PyWorld graphs (spec 2.2): parameter getters -> scene reads -> one Python node -> native terrain writers,
grammars and spawners. pyworld.py build writes them to /Game/PyPCG/World/ (pypcg.build.build_slim, 0 diffs)."""
from pypcg import dsl
from pypcg import world as W
from pypcg.stages import (w01_terrain, w02_locations, w03_river, w04_roads, w05_bridges, w06_settlements,
                          w07_vegetation, w08_props, w09_surface)
from pypcg.world import layout as L, rules


def _graph(module):
    return dsl.SlimGraph(module, name=W.name(W.stage_number(module)))


def _terrain(g, n=None, final=False):
    s = {"MeshPartitionBoundSize": dict(W.QUERY_BOX)}
    if final:
        s["MeshPartitionQueryType"] = "Final"
        title = "Get Mesh Terrain (Final)"
    else:
        query, sub, _w = W.TERRAIN[n]
        if query != "Base":
            s["MeshPartitionQueryType"] = query
        if sub:
            s["ModifierSubPriority"] = sub
        title = "Get Mesh Terrain (%s %d)" % (query, sub)
    return g.sub("Get_MeshTerrain", title, set=s)


def _points(g, terrain):
    return g.sub("Extract_MeshTerrainPoints", "Extract Terrain Points", PrimaryInput=terrain)


def _write(g, n, src, channels=None):
    s = {"MeshPartitionBoundSize": dict(W.QUERY_BOX), "ModifierSubPriority": W.TERRAIN[n][2]}
    if channels:
        s["Channels"] = list(channels)
    return g.sub("Write_MeshTerrain", "Write Terrain (sub-priority %d)" % W.TERRAIN[n][2], set=s, PrimaryInput=src)


def _spawn(g, srcs, title, material=None):
    s = {"UseMeshAttribute": True, "MeshAttribute": "Mesh", "Assets": [W.MESH["Cube"]]}
    if material:
        s["MaterialOverride"] = material
    return g.sub("Spawn_Assets", title, set=s, PrimaryInput=srcs)


def _upstream(g, stages):
    return [g.actor_by_tag(W.volume_tag(m), "Get W%02d Output (%s)" % (m, W.entry(m)[3])) for m in stages]


def build_w01():
    g = _graph(w01_terrain)
    g.connect(_points(g, _terrain(g, 1)), g.py, "MeshTerrain")
    g.connect(g.actor_by_tag(L.TAG_VALLEY, "Get Valley Axis"), g.py, "Valley")
    erode = g.sub("Transform_MeshTerrain_Erosion", "Erode the Mountains", set={"MaskAttribute": "Mountain"},
                  PrimaryInput=g.py["Terrain"])
    _write(g, 1, erode)
    g.out(g.py["Summary"])
    return g


def build_w02():
    g = _graph(w02_locations)
    g.connect(g.actor_points(L.TAG_LOCATION, "Get Locations"), g.py, "Locations")
    g.connect(g.actor_points(L.TAG_RIVER_END, "Get River Ends"), g.py, "RiverEnds")
    g.connect(g.actor_points(L.TAG_EXIT, "Get Road Exits"), g.py, "Exits")
    g.connect(_terrain(g, final=True), g.py, "Surface")
    for pin in w02_locations.OUTPUTS:
        g.out(g.py[pin])
    return g


def build_w03():
    g = _graph(w03_river)
    g.connect(_points(g, _terrain(g, 3)), g.py, "Terrain")
    g.connect(_upstream(g, [2]), g.py, "Upstream")
    _write(g, 3, g.py["Terrain"])
    _spawn(g, g.py["Water"], "Spawn Water Surface", W.WATER_MATERIAL)
    g.out(g.py["River"], g.py["Summary"])
    return g


def build_w04():
    g = _graph(w04_roads)
    g.connect(_points(g, _terrain(g, 4)), g.py, "Terrain")
    g.connect(_upstream(g, [2, 3]), g.py, "Upstream")
    _write(g, 4, g.py["Terrain"])
    _spawn(g, g.py["Modules"], "Spawn Road Lanes")
    g.out(g.py["Roads"], g.py["Summary"])
    return g


def build_w05():
    g = _graph(w05_bridges)
    g.connect(_upstream(g, [3, 4]), g.py, "Upstream")
    _spawn(g, g.py["Parts"], "Spawn Bridge Parts")
    g.out(g.py["Bridges"], g.py["Summary"])
    return g


def build_w06():
    g = _graph(w06_settlements)
    g.connect(_points(g, _terrain(g, 6)), g.py, "Terrain")
    g.connect(_upstream(g, [2, 3, 4]), g.py, "Upstream")
    _write(g, 6, g.py["Terrain"])
    for group in rules.GROUPS:
        g.sub("Assign_ShapeGrammarDefinition", "Buildings (%s)" % group,
              set={"ShapeGrammarDefinition": W.GRAMMAR, "Size": rules.HEIGHT[group]},
              PrimaryInput=g.py["Footprints" + group])
    _spawn(g, g.py["Parts"], "Spawn Foundations, Roofs, Streets and Plazas")
    g.out(g.py["Buildings"], g.py["Streets"], g.py["Areas"], g.py["Summary"])
    return g


def build_w07():
    g = _graph(w07_vegetation)
    terrain = _terrain(g, final=True)
    g.connect(_points(g, terrain), g.py, "Terrain")
    g.connect(terrain, g.py, "Surface")
    g.connect(_upstream(g, [3, 4, 5, 6]), g.py, "Upstream")
    _spawn(g, [g.py["Trees"], g.py["Rocks"], g.py["Grass"]], "Spawn Trees, Rocks and Grass")
    g.out(g.py["Trees"], g.py["Summary"])
    return g


def build_w08():
    g = _graph(w08_props)
    g.connect(_terrain(g, final=True), g.py, "Surface")
    g.connect(_upstream(g, [2, 4, 5, 6]), g.py, "Upstream")
    _spawn(g, g.py["Props"], "Spawn Poles, Wires, Rails, Lamps and Benches")
    g.out(g.py["Summary"])
    return g


def build_w09():
    g = _graph(w09_surface)
    g.connect(_points(g, _terrain(g, 9)), g.py, "Terrain")
    g.connect(_upstream(g, [3, 4, 6, 7]), g.py, "Upstream")
    _write(g, 9, g.py["Terrain"], W.CHANNELS)
    g.out(g.py["Summary"])
    return g


GRAPHS = {1: build_w01, 2: build_w02, 3: build_w03, 4: build_w04, 5: build_w05, 6: build_w06, 7: build_w07,
          8: build_w08, 9: build_w09}


def graph(n):
    return GRAPHS[n]()
```

Note `_write(g, 4, …)` / `_write(g, 6, …)` index `W.TERRAIN` by the stage that reads and writes (4 → write 5, 6 → write 7): the dict's key is the stage.

- [ ] **Step 4: Run** the new test, then the full suite: `C:\Python314\python.exe -m pytest Tools/pypcg/tests -q` — expect the 762 baseline plus every new test passing, 18 skipped.
- [ ] **Step 5: Commit** `"PyWorld: acceptance rules, world checks and the nine graph descriptions"`.

---

### Task 15: 驱动 `pyworld.py` 与编辑器内构建

**Files:** Create `Content/Python/pyworld.py`; regenerate `Content/Python/pypcg/library.json` in the editor.

**Interfaces:** phases `build {"stages"}`, `make`, `layout`, `assign`, `reset {"from"}`, `gen {"stage", "pass"}`, `read {"stage", "pass"}`, `tops`, `shot {"stage"|"view"}`, `check`, `compare`, `save`; any phase takes `{"defer": true}` → result in `Saved/Reports/pyworld_deferred.json`.

- [ ] **Step 1: Write** `Content/Python/pyworld.py`:

```python
import gc
import json
import os
import sys
import time

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
# The bridge keeps sys.modules between calls; drop pypcg so edits to it take effect.
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pyworld.py -- the PyWorld valley (docs/superpowers/specs/2026-10-22-pyworld-video-pipeline-design.md), one phase
# per call, every phase but build/make only in /Game/PyPCG/L_PyWorld:
#   build {"stages": "all"|[n]}   describe -> /Game/PyPCG/World/PCGW_*, structural check, save on 0 diffs
#   make                          create L_PyWorld as a copy of L_PyCity (or open it)
#   layout                        drop the city's volumes and controls, reuse one spline as the valley axis, MPD_Basic,
#                                 spawn the control points and the nine volumes
#   assign                        graphs on the volumes, on-demand generation, seed 42
#   reset {"from": n}             cleanup_local on W9 .. Wn
#   gen {"stage": n, "pass": k}   generate one stage (refuses if an earlier one is not generated)
#   read {"stage": n, "pass": k}  run record Summary + instances + log -> acceptance (pypcg.world.checks)
#   tops                          grammar wall tops per height group, from W6's instances
#   shot {"stage": n}|{"view"}    one screenshot (top / wide / valley / street)
#   check                         W10: intrusions, crossings, connectivity, grades, grounding
#   compare                       pass 1 against pass 2, instances per mesh per stage
#   save                          save L_PyWorld (only its own volumes and graphs)
REPORTS = os.path.join(_REPO, "Saved", "Reports")
RUNS = os.path.join(_REPO, "Saved", "PyPCG", "runs")
LOG = os.path.join(_REPO, "Saved", "Logs", "PCG_Claude.log")
CITY_TAGS = {"City", "Arteries", "Highway", "HighRise", "LandmarkPark", "USER_SPLINE", "LAKE", "FOREST_EXCLUSION",
             "Terrain_shaping_1", "PyCity_MainTowerFootprint", "PyCity_CentralParkFootprint"}
VIEWS = {"top": ((0.0, 0.0, 2000.0), 100000.0, 0.0, 88.0, 1.25), "wide": ((0.0, 0.0, 2000.0), 100000.0, -60.0, 32.0, 1.7),
         "valley": ((0.0, -20000.0, 2000.0), 90000.0, -95.0, 16.0, 1.5),
         "street": ((14000.0, -30000.0, 2600.0), 9000.0, -120.0, 9.0, 1.6)}


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True, default=str)


def _report(name):
    return os.path.join(REPORTS, "pyworld_%s.json" % name)


def _require(what):
    from pypcg import level, world as W
    return level.require(W.LEVEL, "pyworld.py " + what)


def _eas():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def _les():
    return unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)


def _tags(a):
    return {str(t) for t in a.get_editor_property("tags")}


def _volume(n):
    from pypcg import world as W
    for a in _eas().get_all_level_actors():
        if W.volume_tag(n) in _tags(a):
            return a
    raise RuntimeError("no volume tagged %s; run layout" % W.volume_tag(n))


def _pc(n):
    return _volume(n).get_component_by_class(unreal.PCGComponent)


def _log_size():
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def _log_since(offset):
    try:
        with open(LOG, "rb") as fh:
            fh.seek(offset)
            lines = fh.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return {}
    errors = [ln[-300:] for ln in lines if "LogPCG: Error" in ln or "LogPython: Error" in ln]
    return {"errors": len(errors), "first_errors": errors[:6], "pypcg": [ln[-200:] for ln in lines if "PyPCG w" in ln][-4:],
            "crash": any("Crash in runnable thread" in ln for ln in lines)}


def _trace_z(x, y):
    """Ground height under (x, y): the first visibility hit from above (traps.md 51), None on a miss."""
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    res = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, 500000.0), unreal.Vector(x, y, -500000.0),
                                                 unreal.TraceTypeQuery.ECC_VISIBILITY, True, [],
                                                 unreal.DrawDebugTrace.NONE, True)
    hit = res[-1] if isinstance(res, tuple) else res
    if hit is None:
        return None
    parts = hit.to_tuple()
    return float(parts[4].z) if parts[0] else None


def phase_build(args):
    from pypcg import build, compare, world as W
    from pypcg.world import graphs
    wanted = [s[0] for s in W.STAGES] if args.get("stages", "all") == "all" else [int(n) for n in args["stages"]]
    rows = []
    for n in wanted:
        ir = graphs.graph(n).to_ir(None)
        diffs = build.build_slim(ir, W.asset(n), save=bool(args.get("save", True)))
        rows.append({"stage": n, "asset": W.asset(n), "nodes": len(ir["nodes"]), "diffs": len(diffs),
                     "first": compare.format_diffs(diffs, 10)})
    _save(_report("build"), rows)
    return rows


def phase_make(args):
    from pypcg import level, world as W
    if level.current_map() == level.DEMO:
        return {"abort": "the demo is current; open another level first"}
    dirty = [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
    if dirty:
        return {"abort": "unsaved maps %s; not switching levels" % dirty}
    ael = unreal.EditorAssetLibrary
    if ael.does_asset_exist(W.LEVEL):
        ok, how = bool(_les().load_level(W.LEVEL)), "load_level"
    else:
        ok, how = bool(_les().new_level_from_template(W.LEVEL, W.TEMPLATE)), "new_level_from_template"
    return {"how": how, "ok": ok, "current": level.current_map(), "gate": level.current_map() == W.LEVEL}


def _write_spline(actor, pts):
    sc = actor.get_component_by_class(unreal.SplineComponent)
    sc.set_spline_points([unreal.Vector(*p) for p in pts], unreal.SplineCoordinateSpace.WORLD, False)
    sc.set_closed_loop(False, False)
    for i in range(len(pts)):
        sc.set_spline_point_type(i, unreal.SplinePointType.CURVE, False)
    sc.update_spline()
    back = [sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD) for i in range(sc.get_number_of_spline_points())]
    if len(back) != len(pts):
        return 1e9
    return round(max(abs(a.x - b[0]) + abs(a.y - b[1]) + abs(a.z - b[2]) for a, b in zip(back, pts)), 4)


def phase_layout(args):
    from pypcg import world as W
    from pypcg.world import layout as L
    refused = _require("layout")
    if refused:
        return refused
    eas = _eas()
    actors = eas.get_all_level_actors()
    valley = next((a for a in actors if str(a.get_actor_label()) == L.TAG_VALLEY), None) or \
        next((a for a in actors if str(a.get_actor_label()) == "CityShape"), None)
    if valley is None:
        return {"abort": "no spline actor (CityShape or PyWorld_Valley) to reuse for the valley axis"}
    out = {"destroyed": [], "spawned": []}
    for a in list(actors):
        if a == valley:
            continue
        tags = _tags(a)
        if a.get_component_by_class(unreal.PCGComponent) is not None or tags & CITY_TAGS or \
                any(t.startswith("PyWorld_") for t in tags):
            label = str(a.get_actor_label())
            if eas.destroy_actor(a):
                out["destroyed"].append(label)
    valley.set_actor_label(L.TAG_VALLEY)
    valley.set_editor_property("tags", [L.TAG_VALLEY])
    valley.set_actor_location(unreal.Vector(0.0, 0.0, 0.0), False, False)
    out["valley_error_cm"] = _write_spline(valley, L.valley_points())
    mp = next((a for a in eas.get_all_level_actors() if a.get_class().get_name() == "MeshPartition"), None)
    out["mpd"] = None
    if mp is not None and args.get("mpd", True):
        try:
            before = mp.get_editor_property("mega_mesh_definition")
            mp.set_editor_property("mega_mesh_definition", unreal.EditorAssetLibrary.load_asset(W.MPD_BASIC))
            after = mp.get_editor_property("mega_mesh_definition")
            out["mpd"] = {"before": before.get_path_name() if before else None, "after": after.get_path_name() if after else None}
        except Exception as ex:
            out["mpd"] = {"error": "%s: %s" % (type(ex).__name__, str(ex)[:300])}

    def point(label, tag, x, y, scale=1.0):
        a = eas.spawn_actor_from_class(unreal.TargetPoint, unreal.Vector(x, y, 0.0), unreal.Rotator())
        a.set_actor_label(label)
        a.set_editor_property("tags", [tag])
        a.set_actor_scale3d(unreal.Vector(scale, scale, 1.0))
        a.set_folder_path("PyWorld/Controls")
        out["spawned"].append(label)
    for name, x, y, r in L.LOCATIONS:
        point(name, L.TAG_LOCATION, x, y, r / 10000.0)
    for name, x, y in L.RIVER_ENDS:
        point(name, L.TAG_RIVER_END, x, y)
    for name, x, y in L.ROAD_EXITS:
        point(name, L.TAG_EXIT, x, y)
    for n, label, _m, _t in W.STAGES:
        vol = eas.spawn_actor_from_class(unreal.PCGVolume, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator())
        vol.set_actor_label(label)
        vol.set_editor_property("tags", [W.volume_tag(n)])
        vol.set_folder_path("PyWorld/Volumes")
        bb = vol.get_editor_property("brush_builder")
        for k, v in (("x", 300000.0), ("y", 300000.0), ("z", 100000.0)):
            bb.set_editor_property(k, v)
        pc = vol.get_component_by_class(unreal.PCGComponent)
        pc.set_editor_property("regenerate_in_editor", False)
        out["spawned"].append(label)
    carriers = {}
    for a in eas.get_all_level_actors():
        for t in _tags(a):
            carriers.setdefault(t, []).append(str(a.get_actor_label()))
    out["tags"] = {t: sorted(v) for t, v in carriers.items() if t.startswith("PyWorld_")}
    out["ok"] = len(out["tags"].get(L.TAG_LOCATION, [])) == len(L.LOCATIONS) and \
        all(len(out["tags"].get(W.volume_tag(n), [])) == 1 for n, _l, _m, _t in W.STAGES) and out["valley_error_cm"] < 1.0
    return out


def phase_assign(args):
    from pypcg import census, world as W
    refused = _require("assign")
    if refused:
        return refused
    out = {}
    for n, _l, _m, _t in W.STAGES:
        pc = _pc(n)
        pc.set_editor_property("regenerate_in_editor", False)
        pc.set_graph(unreal.EditorAssetLibrary.load_asset(W.asset(n)))
        try:
            pc.set_editor_property("generation_trigger", unreal.PCGComponentGenerationTrigger.GENERATE_ON_DEMAND)
        except Exception as ex:
            out["trigger_error"] = str(ex)[:200]
        pc.set_editor_property("seed", 42)
        res = census.apply_overrides(pc, (args.get("overrides") or {}).get(str(n), {}))
        out[n] = {"graph": pc.get_graph().get_path_name(), "skipped": res["skipped"]}
    return out


def phase_reset(args):
    from pypcg import world as W
    refused = _require("reset")
    if refused:
        return refused
    start = int(args.get("from", 1))
    for n in range(len(W.STAGES), start - 1, -1):
        pc = _pc(n)
        pc.set_editor_property("regenerate_in_editor", False)
        pc.activate(True)
        pc.cleanup_local(True)
    return {"cleaned": list(range(start, len(W.STAGES) + 1))}


def phase_gen(args):
    from pypcg import stage_api, world as W
    refused = _require("gen")
    if refused:
        return refused
    n, k = int(args["stage"]), int(args.get("pass", 1))
    pc = _pc(n)
    g = pc.get_graph()
    if g is None or g.get_path_name().split(".")[0] != W.asset(n):
        return {"abort": "W%02d does not hold %s (run assign)" % (n, W.asset(n))}
    missing = [m for m in range(1, n) if not _pc(m).get_editor_property("generated")]
    if missing and not args.get("force"):
        return {"abort": "earlier stages not generated: %s" % missing}
    os.environ[stage_api.RECORD_ENV] = "1"
    _save(_report("w%02d_gen" % n), {"gen_at": time.time(), "log_offset": _log_size(), "pass": k})
    pc.activate(True)
    pc.generate_local(True)
    return {"stage": n, "pass": k, "graph": g.get_path_name()}


def phase_read(args):
    from pypcg import census
    from pypcg.world import checks, layout as L
    refused = _require("read")
    if refused:
        return refused
    n, k = int(args["stage"]), int(args.get("pass", 1))
    gen = _load(_report("w%02d_gen" % n), {})
    path = os.path.join(RUNS, "w%02d.json" % n)
    rec = _load(path, {})
    fresh = os.path.exists(path) and os.path.getmtime(path) >= gen.get("gen_at", 0)
    summary = None
    for item in (rec.get("outputs") or {}).get("Summary", []):
        summary = item[0].get("values")
    inst = census.instances(_volume(n))
    extra = {"instances": inst["total"]}
    if n == 1:
        errs = []
        for y in range(-90000, 90001, 30000):
            z = _trace_z(L.axis_x(y), float(y))
            if z is not None:
                errs.append(abs(z - L.floor_z(y)))
        extra["traced_floor_err_cm"] = max(errs) if errs else None
    fails = checks.accept(n, summary, extra)
    log = _log_since(gen.get("log_offset", 0))
    out = {"stage": n, "pass": k, "fresh_record": fresh, "seconds": rec.get("seconds"), "notes": rec.get("notes"),
           "summary": summary, "extra": extra, "meshes": len(inst["per_mesh"]),
           "since_gen_s": round(time.time() - gen["gen_at"], 1) if "gen_at" in gen else None,
           "generated": bool(_pc(n).get_editor_property("generated")), "log": log, "failures": fails,
           "pass_ok": bool(fresh and not fails and not log.get("crash"))}
    book = _load(_report("pass%d" % k), {})
    book[str(n)] = dict(out, per_mesh=inst["per_mesh"])
    _save(_report("pass%d" % k), book)
    return out


def phase_tops(args):
    """Wall top above the pad per height group: each grammar instance's top (mesh bounds x scale) is given to the
    nearest W6 building; the median per group is what rules.WALL_TOP should hold."""
    from pypcg import census
    from pypcg.ue import convert
    refused = _require("tops")
    if refused:
        return refused
    pc = _pc(6)
    buildings = []
    for td in pc.get_generated_graph_output().get_editor_property("tagged_data"):
        if "Building" in [str(t) for t in td.get_editor_property("tags")]:
            v = convert.from_pcg(td.get_editor_property("data").get_editor_property("data"))
            for i in range(len(v)):
                buildings.append((v.loc[i], v.attrs["Group"][i]))
    tops = {}
    for c in _volume(6).get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None or "/PCGPrimitives/Meshes/" not in sm.get_path_name():
            continue
        zmax = sm.get_bounding_box().max.z
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            x, y, z = t.translation.x, t.translation.y, t.translation.z + zmax * t.scale3d.z
            if not buildings:
                break
            loc, group = min(buildings, key=lambda b: (b[0][0] - x) ** 2 + (b[0][1] - y) ** 2)
            key = (round(loc[0]), round(loc[1]))
            tops.setdefault(group, {}).setdefault(key, []).append(z - loc[2])
    out = {}
    for group, per in tops.items():
        vals = sorted(max(v) for v in per.values())
        out[group] = {"buildings": len(vals), "median_top_cm": vals[len(vals) // 2] if vals else None,
                      "min": vals[0] if vals else None, "max": vals[-1] if vals else None}
    _save(_report("tops"), out)
    return out


def phase_shot(args):
    for m in ("pcg_sa_shots", "pcg_sa_geom"):
        sys.modules.pop(m, None)
    import pcg_sa_geom as G
    import pcg_sa_shots as S
    refused = _require("shot")
    if refused:
        return refused
    view = args.get("view", "wide")
    centre, radius, az, elev, mult = VIEWS[view]
    loc, rot = G.orbit_camera(list(centre), radius, az, elev, mult, min_height=centre[2] + 800.0)
    les = _les()
    les.set_level_viewport_camera_info(unreal.Vector(*loc), unreal.Rotator(pitch=rot[0], yaw=rot[1], roll=rot[2]),
                                       les.get_active_viewport_config_key())
    name = "pyworld_w%02d_%s.png" % (int(args["stage"]), view) if "stage" in args else "pyworld_%s.png" % view
    return {"fired": S.fire(name, les)}


def _outputs(n):
    from pypcg.ue import convert
    items = []
    for td in _pc(n).get_generated_graph_output().get_editor_property("tagged_data"):
        try:
            v = convert.from_pcg(td.get_editor_property("data").get_editor_property("data"))
        except TypeError:
            continue
        items.append((v, frozenset(str(t) for t in td.get_editor_property("tags"))))
    return items


def phase_check(args):
    from pypcg.geo import Points
    from pypcg.stages.w03_river import river_rows
    from pypcg.stages.w04_roads import road_rows
    from pypcg.stages.w05_bridges import bridge_rows
    from pypcg.world import checks, rules, scatter, points as WP
    refused = _require("check")
    if refused:
        return refused
    up = [it for n in (2, 3, 4, 5, 6) for it in _outputs(n)]
    roads, river = road_rows(up), river_rows(up)
    nodes = [(r["loc"][0], r["loc"][1], max(r.get("Radius", 0.0), 1500.0))
             for v, t in up if isinstance(v, Points) and t & {"Location", "RoadExit"} for r in WP.rows_of(v)]
    trees = [p for v, t in _outputs(7) if isinstance(v, Points) and "Tree" in t for p in v.loc]
    out = {"intrusions": checks.intrusions(trees, scatter.upstream_exclusions(up)),
           "crossings": checks.crossings(roads, river), "bridges": len(bridge_rows(up)),
           "connected": checks.roads_connected(roads, nodes), "grades": checks.max_grades(roads)}
    tree_meshes = {m for spec in rules.BIOMES.values() if spec["kind"] == "Tree" for ms, _w, _s in spec["species"] for m in ms}
    sink = {m: spec["sink"] for spec in rules.BIOMES.values() for ms, _w, _s in spec["species"] for m in ms}
    from pypcg import world as W
    lamp = W.MESH["Lamp"].split(".")[0]
    errors, sampled = [], 0
    for n in (7, 8):
        for c in _volume(n).get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            path = sm.get_path_name() if sm else ""
            full = path if "." in path else path
            key = next((m for m in tree_meshes if m.split(".")[0] == path.split(".")[0]), None)
            if key is None and path.split(".")[0] != lamp:
                continue
            count = c.get_instance_count()
            for i in range(0, count, max(1, count // 150)):
                t = c.get_instance_transform(i, True).translation
                z = _trace_z(t.x, t.y)
                if z is None:
                    continue
                sampled += 1
                err = abs(t.z + (sink[key] if key else 0.0) - z)
                if err > 30.0:
                    errors.append([path.rsplit("/", 1)[-1], round(t.x), round(t.y), round(err, 1)])
    out["grounding"] = {"sampled": sampled, "over_30cm": len(errors), "first": errors[:10]}
    out["ok"] = (sum(out["intrusions"].values()) == 0 and out["crossings"] == out["bridges"] and out["connected"]
                 and out["grades"].get("Main", 0.0) <= 0.10 + 1e-6 and out["grades"].get("Secondary", 0.0) <= 0.14 + 1e-6
                 and not errors)
    _save(_report("check"), out)
    return out


def phase_compare(args):
    a, b = _load(_report("pass1"), {}), _load(_report("pass2"), {})
    out = {}
    for n in sorted(set(a) | set(b), key=int):
        pa, pb = a.get(n, {}).get("per_mesh", {}), b.get(n, {}).get("per_mesh", {})
        diff = {m: [pa.get(m, 0), pb.get(m, 0)] for m in set(pa) | set(pb) if pa.get(m, 0) != pb.get(m, 0)}
        out[n] = {"instances": [sum(pa.values()), sum(pb.values())], "differing_meshes": len(diff),
                  "first": dict(list(diff.items())[:5])}
    out["identical"] = all(v["differing_meshes"] == 0 for v in out.values() if isinstance(v, dict))
    _save(_report("compare"), out)
    return out


def phase_save(args):
    from pypcg import census, world as W
    refused = _require("save")
    if refused:
        return refused
    graphs = {}
    for a in census.volumes():
        g = a.get_component_by_class(unreal.PCGComponent).get_graph()
        graphs[str(a.get_actor_label())] = g.get_path_name() if g else None
    bad = {k: v for k, v in graphs.items() if not (v and v.startswith(W.ASSET_DIR))}
    if bad or len(graphs) != len(W.STAGES):
        return {"abort": "refusing to save: PCG actors %s" % graphs, "saved": False}
    for a in census.volumes():
        a.modify()
    saved = bool(_les().save_current_level())
    folder = os.path.join(_REPO, "Content", "__ExternalActors__", "PyPCG", "L_PyWorld")
    sizes = []
    for root, _d, files in os.walk(folder):
        sizes += [os.path.getsize(os.path.join(root, f)) for f in files]
    return {"saved": saved, "files": len(sizes), "largest_mb": round(max(sizes) / 1e6, 1) if sizes else 0.0,
            "total_mb": round(sum(sizes) / 1e6, 1)}


PHASES = {"build": phase_build, "make": phase_make, "layout": phase_layout, "assign": phase_assign,
          "reset": phase_reset, "gen": phase_gen, "read": phase_read, "tops": phase_tops, "shot": phase_shot,
          "check": phase_check, "compare": phase_compare, "save": phase_save}
DEFERRED = _report("deferred")


def _defer(phase, args):
    """Run a long phase on the next editor tick (a long bridge call loses its reply: traps.md 88)."""
    _save(DEFERRED, {"phase": phase, "state": "queued"})
    handle = {}

    def tick(_dt):
        unreal.unregister_slate_post_tick_callback(handle["h"])
        try:
            _save(DEFERRED, {"phase": phase, "state": "done", "result": PHASES[phase](args)})
        except Exception as exc:
            _save(DEFERRED, {"phase": phase, "state": "error", "error": "%s: %s" % (type(exc).__name__, str(exc)[:800])})
        gc.collect()
    handle["h"] = unreal.register_slate_post_tick_callback(tick)
    return {"deferred": phase, "result_file": DEFERRED}


def run(args):
    phase = args.get("phase")
    if phase not in PHASES:
        return {"abort": "unknown phase %r; phases: %s" % (phase, sorted(PHASES))}
    if args.get("defer"):
        return _defer(phase, {k: v for k, v in args.items() if k != "defer"})
    return PHASES[phase](args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
```

- [ ] **Step 2: Regenerate the library in the editor** — `run_unreal_script("pypcg_library.py")`; then `git diff --stat Content/Python/pypcg/library.json`. Expected: only the erosion entry differs from the hand-written one, if at all; take the editor's version and re-run `pytest Tools/pypcg/tests -q`.
- [ ] **Step 3: Build the graphs** — `run_unreal_script("pyworld.py", {"phase": "build", "defer": true})`, wait ~60 s, read `Saved/Reports/pyworld_deferred.json`. Expected: nine rows, `diffs: 0` each. A diff on a struct override → write the whole struct as the exporter reads it back (trap 90); an unknown pin → re-check `library.json`.
- [ ] **Step 4: Commit** `"PyWorld: editor driver and the nine graph assets"` (`pyworld.py`, `library.json`, the nine `.uasset` under `Content/PyPCG/World/`).

---

### Task 16: 关卡 `L_PyWorld`（make / layout / assign）

**Files:** `Content/PyPCG/L_PyWorld.umap` and its external actors (generated).

- [ ] **Step 1:** `run_unreal_script("pyworld.py", {"phase": "make"})`. The editor currently has `L_PyCitySmall` open, a large level (traps 79/83): `make` refuses with dirty maps; if the editor crashes on the switch, move `Saved/Autosaves/*` aside (trap 78), ask the user to restart, and run `make` again (it then opens `L_PyCity` → copy). Expected: `gate: true`.
- [ ] **Step 2:** `{"phase": "layout"}`. Expected `ok: true`: 2 PCG volumes + city splines destroyed, valley spline error < 1 cm, 9 TargetPoints and 9 volumes spawned. Note `mpd`: an `after` path ending in `MPD_Basic` means the six channels are available; an `error` means W9 falls back (Task 18 Step 6).
- [ ] **Step 3:** `{"phase": "assign"}` — every volume holds `/Game/PyPCG/World/PCGW_0N_*`. Then `{"phase": "save"}` (first save: no generated output yet).
- [ ] **Step 4: Commit** `"PyWorld: the L_PyWorld level with its controls and volumes"`.

---

### Task 17: 编辑器运行 W1–W5

For each stage n in 1..5: `gen {"stage": n}` → wait (W1 ~60–120 s: 261 k vertices through Python twice plus erosion; others 20–90 s) → `read {"stage": n}` → if `since_gen_s` is short and instances look low, read again (traps 59, 65) → `shot {"stage": n}` → look at the screenshot.

- [ ] **Step 1: W1.** Acceptance from `read`. Also look at `seconds` (target < 60 s). Expected risks and the fix for each:
  - Erosion flattens the valley or does nothing → read `traced_floor_err_cm`; if > 800 set the erosion's `ErosionStrength` lower in `graphs.build_w01` (`set={"MaskAttribute": "Mountain", "ErosionStrength": 250.0}`), rebuild W1, re-run. If the node fails, drop it from the graph and record the deviation in the guide.
  - Python > 60 s → measure where (notes), cache the axis lookup per row of y.
- [ ] **Step 2: W2.** `locations 5, exits 2, river_ends 2, off_terrain 0`. If a location's centre slope > 6°, move it in `layout.LOCATIONS` (layout + assign + reset from 2).
- [ ] **Step 3: W3.** Confirms three unmeasured mechanisms at once — `Get_ActorData` reading another volume's output (W2's items arrive), `Write_MeshTerrain` with every vertex at sub-priority 3, `Spawn_Assets` by the `Mesh` attribute with `MaterialOverride`. If `Upstream` arrives empty, check the volume tag and the `DeleteTags` substring rule (`input`) before anything else.
- [ ] **Step 4: W4.** `connected`, grades within limits, lanes visible on the road corridors in the shot. If a road is unreachable, look at `HardGrade` against the terrain at that place before loosening anything.
- [ ] **Step 5: W5.** `bridges == crossings ≥ 1`. Shot of a bridge close up (`view` street centred on the first bridge: add a one-off `{"phase": "shot", "view": "street"}` after editing `VIEWS["street"]` centre to the bridge from `read`'s summary if needed).
- [ ] **Step 6: Commit** any fixes with the test that pins each one.

---

### Task 18: 编辑器运行 W6–W9（含建筑语法实测）

- [ ] **Step 1: W6** `gen` / `read`. Then `{"phase": "tops"}`: the median wall top per height group. Write the four medians into `rules.WALL_TOP` (keep `HEIGHT` as the grammar `Size`), rerun `pytest`, `reset {"from": 6}`, `gen 6`, `read 6`, shot `street`. Roofs must sit on the walls.
- [ ] **Step 2:** If the grammar spawns nothing (0 instances from `/PCGPrimitives/Meshes/`), check the footprint winding (reverse the ring order in W6 — trap 41) and that the spline is closed; record which one fixed it.
- [ ] **Step 3: W7.** `trees ≥ 20 000`; `seconds` < 60 (else lower the base grid cost: cache `noise.value` per 15 m cell).
- [ ] **Step 4: W8.** poles every 40 ± 5 m; shot `street`.
- [ ] **Step 5: W9.** `channels 6`. Shot `top`: roads and river must show Dirt / Gravel / Mud colours.
- [ ] **Step 6:** If `layout` reported an MPD error, or W9's shot shows no material change, switch `W.CHANNELS` to the template's `("Mat_GrassDry", "Mat_Dirt", "Mat_Mud")` mapping (Grass+Rock+ForestFloor → Mat_GrassDry, Dirt+Gravel → Mat_Dirt, Mud → Mat_Mud) in `w09_surface.compose`'s caller, with a test, rebuild W9, rerun.
- [ ] **Step 7: Commit** the fixes and `rules.WALL_TOP`.

---

### Task 19: W10 校验、第二遍、总览、保存

- [ ] **Step 1:** `{"phase": "check", "defer": true}` → `ok: true` (0 intrusions, crossings == bridges, connected, grades, 0 instances grounded worse than 30 cm). Each failure is fixed in its stage with a test, then `reset {"from": stage}` and regenerate onwards.
- [ ] **Step 2: Pass 2.** `reset {"from": 1}`, then `gen`/`read` with `"pass": 2` for 1..9; `{"phase": "compare"}` → `identical: true`.
- [ ] **Step 3:** Overview shots `top`, `wide`, `valley`, `street` (one per call; check each on disk on the next call).
- [ ] **Step 4:** `{"phase": "save"}` → `saved: true`, `largest_mb < 100`. If over, `reset {"from": 1}`, save the cleaned level, and say in the guide that the world is regenerated on open (as `L_PyCity`).
- [ ] **Step 5: Commit** the level and reports summary (`Saved/` stays untracked).

---

### Task 20: 文档与收尾

**Files:** Create `docs/pyworld-guide.md`; Modify `.claude/skills/city-sample-pcg-city-builder/references/traps.md` (new facts measured in Tasks 15–19, numbered from 92), `CLAUDE.md` (one paragraph: PyWorld, its driver and level), memory.

- [ ] **Step 1:** `docs/pyworld-guide.md`: the video breakdown table (spec §1), the stage table (what each does, its graph, its Python node, its native nodes), the driver commands, how to move a location / change a parameter / rerun from a stage, the results (per-stage acceptance values, instance counts, timings, the four overview shots), deviations and known limits (no tunnels; anything measured as different from the spec).
- [ ] **Step 2:** Full suite `C:\Python314\python.exe -m pytest Tools/pypcg/tests -q` and `C:\Python314\python.exe Tools/pypcg/baseline.py check` — paste the outputs into the final report.
- [ ] **Step 3: Commit** `"PyWorld: guide, traps and project notes"`.



