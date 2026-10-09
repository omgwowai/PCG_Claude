# TL 建筑按 spline 生成 + 任意角度转角 —— 设计文档

- 日期：2026-10-09
- 状态：待用户复核
- 项目：`E:\PCG_Claude`（UE 5.8.2 源码版引擎 `E:\UnrealEngine`）
- 前置：TL 样式已完成（`docs/superpowers/specs/2026-09-24-tl-building-style-design.md`，
  最近提交 `0e988d9`），展示关卡 `Lvl_TL_Showcase` 用的是 Epic 的 BDF 路线。

---

## 1. 目标与非目标

### 1.1 目标

在关卡里画一条闭合 spline，TL 建筑沿着它生成，spline 一改建筑就跟着改。
spline 上任意角度的转角都要正确收口：

- **外凸转角**做成半径 1.5 m 的圆弧，腰线、檐口、基座绕着弧连续走；
- **内凹转角**做成尖角，两面墙直接交到顶点。

### 1.2 非目标

- 不支持曲线边。spline 只当折线用，切线弧度忽略。
- 不做二层缩进的错层体量。以后可以在缩进后的轮廓上再跑同一套逻辑。
- 不接进城市流程（`PCG_3_3_1_Buildings`），不修改任何 Epic 的图或数据资产。
- 转角半径不做成可调参数。弧片是按 1.5 m 建模的，换半径线脚就对不上。
- 圆弧上不放立面道具。

---

## 2. 用户已确认的决定（2026-10-09）

| 问题 | 决定 |
|---|---|
| 用在哪里 | 只用在关卡里手画的 spline 上；只改 TL 专用的资产 |
| 边的形状 | 只要直边，转角任意角度 |
| 外凸转角的样子 | 圆弧倒角，R = 1.5 m；90° 转角也变成圆角 |
| 内凹转角 | 尖角，两墙互相插入，不另做内角件 |
| 实现方式 | **C：纯 PCG 图，不写 C++**（图由 Python 脚本生成） |
| 第一、二部分设计 | 已确认（本文第 10 节更正了其中两个数字） |

---

## 3. 关键事实（全部实测，2026-10-09）

### 3.1 现有 BDF 路线不支持任意角度

- `BDF_BuildingFromSpline` 用 `RoundSegmentAngles`（`Precision = 5`）把每个转角取整到 5°。
  之后只按转角的凹凸替换语法里的 `[FC]`/`[LC]`：凸的换成 `C_E`，凹的换成 `C_I`。角度本身不参与放置。
- 全部 28 个样式在 Modules 组里一共只有这几种转角符号：`C_E*`、`C_I*`、`C_CE*`、`C_SL*`、
  `C_SR*`、`C_IL*`、`C_IR*`、`C_CI`、`B_I`（`tl_probe_symbol_census.py`）。没有一个和角度有关。
- 探测：复制 Epic 的 `Building_Staggered_HexagonShape`（转角 44.8° 与 67.6°），改成只生成 TL。
  6 个外角**全部没合上**，角件第二翼与墙之间留了 58–115 cm 的缝（`tl_probe_corner_joints.py`，
  截图 `Saved/Screenshots/WindowsEditor/probe_hex_a.png`）。临时资产已删除。

### 3.2 TL 套件的截面深度（局部 x，外立面在 0，外侧为 +X）

`tl_probe_kit_depths.py` 的结果：

| 层 | 墙体 x 范围 (cm) | 外凸最多 |
|---|---|---|
| L0 Foundation_01 | −45 … +7 | 7 |
| L1 Wall_01 / Wall_02 | −30 … +16 | 16 |
| L2/L3 Wall_01 / Wall_02 | −30 … +8 | 8 |
| L4 Wall_01（檐口） | −34 … +34 | 34 |
| L1 Entrance_01 | −66 … +110 | 110（门罩） |

可见墙的外皮在一条线上，突出物最多 34 cm（檐口），只有入口门罩是例外。

### 3.3 可用的引擎节点（本版引擎里已核对）

- `SplineToSegment`：每段输出一个点，点在段中点，extents 是半段长；可附带前后转角的角度、前后段索引、顺逆时针。
- `Offset Polygon2D`：有 `Open` 运算（先收再放），转角连接方式可选 `Round`。
  先收 150 cm 再放 150 cm，效果正好是：凸角变成 R=150 的圆弧，凹角保持尖角。
  它的圆角细分密度是引擎内定的，不能调。
- 其余可用：`MetadataTrig`（Sin/Cos/Tan/Atan2）、`MetadataVectorOp`（RotateAroundAxis、TransformDirection 等）、
  `MetadataMaths`、`CopyPoints`、`AttributeGetFromIndex`、`MatchAndSetAttributes`、`DuplicateCrossSections`、
  `SubdivideSegment`、`StaticMeshSpawner`。
- Epic 的子图 `Loop_Subdivide`、`Loop_GroupedPropsCopy`、`ASM_Clutter_Behavior`、`Create_Mesh_Planar`、
  `Fill_Areas_WithFittingAssets` 都能作为子图调用，不需要修改。

---

## 4. 几何规则

所有计算都在**外立面线**上做，也就是 spline 本身（墙模块局部 x = 0 那条线）。
先用 `SplineDirection` 把 spline 统一成顺时针，这样转角角度的正负号就直接表示凹凸。
第一步要先探测确认这个符号约定（见第 9 节风险 1）。

### 4.1 转角分类

对每个控制点，转向角 θ = 180° − 内角（内角在建筑内部一侧量）。

| θ | 处理 |
|---|---|
| \|θ\| < 2° | 当成直线：不裁端，不放弧 |
| 外凸，2° ≤ θ ≤ 170° | 圆弧（4.2） |
| 外凸，θ > 170°（内角 < 10°） | 不支持：照样生成，但会有穿插，第 8 节只做记录 |
| 内凹 | 尖角（4.4） |

### 4.2 外凸转角：圆弧

设计半径 R = 150 cm。两侧墙各让出的长度（切线长）：

```
d_c = min( R·tan(θ/2),  L_in / 2,  L_out / 2 )
R'_c = d_c / tan(θ/2)          （实际半径，一般等于 R）
```

其中 L_in、L_out 是这个转角两侧两条**原始边**的长度。每端最多让出半条边，
这样一条边两头的让出量永远不会重叠。

参考数值：

| 内角 | θ | d（R'=R 时） |
|---|---|---|
| 120°（正六边形） | 60° | 86.6 cm |
| 90° | 90° | 150 cm |
| 60° | 120° | 259.8 cm |
| 30° | 150° | 559.8 cm |

90° 时让出 150 cm，正好等于现有外角件单翼的宽度。所以矩形楼的直墙开间排布和现在完全一样（验收项 A5）。

**圆心**：C = V + b·R'/cos(θ/2)。V 是顶点，b 是指向建筑内部的角平分线单位向量。

**弧片**：

- 片数 n = ⌈θ / 10°⌉，每片张角 2a，a = θ/(2n) ≤ 5°。
- 第 k 片（k = 0 … n−1）的径向朝外方向：把入射墙的外法线 n₁ 朝出射墙外法线 n₂ 旋转 (2k+1)·a。
- 每片都以圆心 C 为枢轴放置：局部 +X 指向这片的径向朝外方向，Z 向上。缩放为：

```
sx = (R'/R) · cos(a) / cos(5°)
sy = (R'/R) · sin(a) / sin(5°)
sz = 1
```

弧片模型的两条侧边都在 ±5° 的径向线上，边上每个顶点到圆心的距离是 R + x（x 是截面深度）。
按上式缩放后，侧边上的点正好落在 ±a 的径向线上，到圆心的距离是 R'·(R + x)/R。因此：

- R' = R 时，侧边截面和直墙端面完全重合。直墙端面垂直于墙，过切点，也是径向线。
  相邻两片之间同样完全重合。误差只来自浮点。
- R' < R 时，外立面那条线（x = 0）仍然精确对上，但深度为 x 的突出物会错开 x·(1 − R'/R)。
  例如 R' = 120 cm 时，34 cm 的檐口错开 6.8 cm。这种情况只出现在短边上（见 4.6）。

### 4.3 直墙段

每条边在两端扣掉 d：外凸端扣 d_c，内凹端和近似直线的端点不扣。
得到裁过的段 [起点 + d_start, 终点 − d_end]，长度 L' = L − d_start − d_end。

然后套原来的开间语法：

1. 语法串去掉 `[FC]`、`[LC]`；
2. 按 L' 选语法，门槛是原来的 FLengths 减 300：

| 条件 | 用的语法 |
|---|---|
| L' ≥ 5100 | F2 |
| L' ≥ 3425 | F1 |
| L' ≥ 650 | F0 |
| L' < 650 | 单独一块 `[WS1]`，拉伸到 L' |

3. 余量照旧由可拉伸的 WS1 吸收（L0 层是 FS2）。

L0 的语法 `[FC][FS2]+[LC]` 去掉首尾后是 `[FS2]+`，各档门槛都是 0。

### 4.4 内凹转角：尖角

两条边在这个顶点处都不裁，墙一直铺到顶点。

按第 3.2 节的截面推算：

- 外侧那一圈突出物（腰线、檐口、基座）在凹角处互相重叠，合起来就是一条斜接线；
- 一面墙伸到顶点处的端头，要么插进另一面墙的墙体里，要么插进建筑内部。两种情况从外面都看不到。

这是推算，不是实测，由第 8 节 L 形楼的近景截图（A8）核对。
外部楔形角很窄（< 30°）时没有验证过，不作保证。

重叠的那一小块是两个线脚顶面共面，大约 34 × 34 cm，可能闪烁（第 9 节风险 6）。

### 4.5 竖向

竖向语法照用 `BDF_WithTL` 的 `[LV0][LV1][LV2]*[LV3][LV4]`，层高 0.5 / 500 / 300 / 300 / 120 cm。
用 `DuplicateCrossSections` 按建筑高度参数切出各层轮廓，和 Epic 的链用法一样。
每层的直墙和弧片都按这一层的轮廓、用这一层的部件生成。

### 4.6 短边与退化情况

- 一个外凸角的 d 被 L/2 限住时，这个角就是“缩小角”（R' < R），突出物错开量见 4.2。验收时会把每个缩小角的 R' 和错开量都列出来。
- 一条边两头都是外凸角时，扣完之后 L' 可能是 0：这条边上不放直墙，只有两段圆弧。
- 近似直线的点（|θ| < 2°）不裁、不放弧，两条边的直墙直接相接，角度差会让墙端留一个最多约 1 cm 的楔形缝，可以接受。

### 4.7 屋顶

屋顶轮廓 = `Offset Polygon2D`（Open，150 cm，Round）作用在外立面多边形上。
Open 就是先收 150 cm 再放 150 cm，效果是凸角变成 R = 150 的圆弧、凹角保持尖角。
注意它会把轮廓里宽度不到 3 m 的窄条整个削掉。

在这之上，屋顶的内缩量与高度照搬 BDF 路线对 `RoofData` 的用法：
`RoofData.XYY` 复制到 `RoofOffset`，`ZWW` 复制到 `RoofInset`，屋面高度 = MaxHeight + RoofOffset.Y（TL 是 −50 cm）。
`RoofInset` 在 `BDF_BuildingFromSpline` 里具体怎么作用还没读出来，实施计划第一步读出后照搬。

- 平面网格用 `Create_Mesh_Planar`（MI_Rooftop_BitumenRoofing）。
- 屋顶设备用 `Fill_Areas_WithFittingAssets`，用 BDF 测试图里的同一组 14 个 Rooftop 组合。

缩小角（R' < R）处，屋顶仍按 R = 150 圆角，所以屋顶边会比墙线多往里缩一点。
如果从上面能看到缝，就按风险 4 的退路，改用第 5 段算出的弧点拼屋顶轮廓。

### 4.8 立面道具

直墙模块照用 `BDF_WithTL` 的 Props 组。流程和 BDF 路线一样：
HasProps 过滤 → `Loop_GroupedPropsCopy` → WindowHelper/Decal 过滤 → `ASM_Clutter_Behavior` → 生成。

挂在 `CornerEx_01` 上的转角招牌和消防接口在这条路线上不出现，因为没有外角件了。

---

## 5. 资产与数据

| 资产 | 新建 / 修改 | 内容 |
|---|---|---|
| `/Game/PCG/TL/PCG_TL_SplineBuilding` | 新建 | 生成图，由 `Content/Python/tl_make_spline_graph.py` 生成，可重跑 |
| `/Game/PCG/TL/BP_TL_SplineBuilding` | 新建 | 蓝图 Actor：一个闭合 SplineComponent 加一个 PCGComponent（图如上）；用户参数 `BuildingHeight`（cm）、`Seed` |
| `SM_BLDG_TL_L0x_A_CornerArc_01_N1` ×5 | 新建 | L0–L4 每层一片弧片 |
| `Tools/tl_kit/tl_kit_spec.json` | 修改 | 加 5 个 `CornerArc_01` 部件，kind = `corner_arc`，宽 26.15 cm（10° 的弦长） |
| `Tools/tl_kit/kit_common.py` | 修改 | `EXPECTED_PART_COUNT` 改为 48；`PART_TO_SYMBOL` 加 `"CornerArc_01": "C_ARC"`；加转角常量（R、片张角、门槛减量） |
| `Tools/tl_kit/build_tl_kit.py` | 修改 | 加 `corner_arc` 的建模函数（第 7 节） |
| `Tools/tl_kit/corner_math.py` | 新建 | 纯 Python 参考实现（第 8 节） |
| `/Game/PCG/DataAssets/BDF/BDF_WithTL` | 修改 | Modules 组加 5 行 `C_ARC`（每层一行，Mod_Name 指向弧片，不可拉伸，无道具）。没有任何语法引用 `C_ARC`，老 BDF 路线不受影响 |
| `/Game/Map/Lvl_TL_Spline` | 新建 | 测试关卡，放三栋（第 8 节） |

**数据只放一份**：语法、层高、模块尺寸、道具表都在运行时从 `BDF_WithTL` 的 TL 行读出。
`[FC]`/`[LC]` 的去除和门槛减量在图里做，数据表本身不改。

`RULE_TL_*` 与 `SGD_TL_A`（SGD 路线）不变，不加弧片。

---

## 6. 图的结构（`PCG_TL_SplineBuilding`）

图分七段，每段之间用 Named Reroute 连接。脚本按段搭建，每搭完一段都可以单独读回中间属性。

1. **数据**：`LoadDataAsset`（BDF_WithTL）→ 按标签分出 BDF / Levels / Modules / Props 四组 → 每组过滤 `BuildingToken == "TL"`。
2. **轮廓与分层**：`Get Spline Data`（Self）→ `SplineDirection`（强制顺时针）→ `DuplicateCrossSections`（竖向语法 + 层高，拉伸向量 = (0, 0, BuildingHeight)）。
3. **转角**：每层轮廓 → `SplineToSegment`（角度、连接关系）。逐个转角算出 θ、凹凸、d_c、R'_c、n、圆心。
   每个转角需要两侧原边的长度，用前后段索引 + `AttributeGetFromIndex` 取。
4. **直墙**：每段按两端的 d 裁短，也就是平移 $Position、改 $Extents.X → 按 L' 选语法（4.3）→
   调 `Loop_Subdivide` 拆开间 → 按 Modules 行加 PivotOffset 定位。
5. **圆弧**：每个外凸转角用 `CopyPoints` 复制一组 18 个模板点（k = 0…17，可覆盖到 180°）→
   只保留 k < n → 每点算出朝向（Atan2）和缩放（4.2）→ 把 Mesh 设为这一层的 `C_ARC` 行。
6. **道具与生成**：直墙模块走 4.8 的道具流程；直墙模块、弧片、道具一起进 `StaticMeshSpawner`（按属性选网格）。
7. **屋顶**：第 2 段的顶层轮廓 → 4.7。

`Seed` 传给道具的概率抽取，这一点和 BDF 路线一样。

---

## 7. 弧片建模（`build_tl_kit.py`）

- 每层的弧片用这一层补长件的同一个建模函数生成：L0 用 Foundation_01；L1–L3 用 Wall_02；L4 用 Wall_01（檐口）。
  宽度取 w = 2·R·sin 5° = 26.15 cm。生成的是一段直的窄条，局部 y ∈ [−w/2, w/2]。
  - L4 的齿饰按窄条自己的宽度重新排，所以每片窄条的内容都一样，一整段弧上齿饰是均匀的。
- 弯曲：窄条上每个顶点 (x, y, z) 映射成 r = R + x、φ = (y / (w/2))·5°、位置 (r·cos φ, r·sin φ, z)。
  原点在圆心，所以导入后网格的局部原点就是圆心。两条侧边精确落在 ±5° 的径向线上。
  外立面跟着弯成弧；如果某个面只有两端两个顶点，它就是一条弦，弦高 0.57 cm。
- 材质槽与现有部件相同（砖 / 石 / 玻璃 / 金属四个）。
- `tl_kit_rebuild_meshes.py` 要能处理**新建**资产，不只是替换已有的。
  这一点在实施计划第一步核实，不行的话改用首次导入的路径。

---

## 8. 测试与验收

### 8.1 参考实现（`Tools/tl_kit/corner_math.py`，纯 Python）

输入一个按顺序排列的折线顶点列表，输出：

- 每个转角：θ、凹凸、d、R'、n、圆心、每片的朝向与缩放 (sx, sy)；
- 每条边：裁过的段（起点、终点、L'）和选中的语法；
- 屋顶轮廓的采样点。

pytest（`Tools/tl_kit/test_corner_math.py`）覆盖这些用例：

- 正方形、正六边形、带一个 30° 锐角的五边形、L 形（含凹角）；
- 两头都是外凸角、需要缩小 R 的短边；
- 近乎共线的点；
- 顺时针与逆时针输入给出相同结果。

### 8.2 编辑器内验收（`Lvl_TL_Spline`）

关卡里放四栋：

1. **正六边形**；
2. **不规则五边形**：含一个 30° 锐角和一条短边，短边会触发缩小 R；
3. **L 形**：含一个凹角；
4. **60 × 30 m 矩形**。

读回探测脚本 `tl_probe_spline_building.py` 对每栋读出实例，和参考实现比对：

| # | 验收项 | 标准 |
|---|---|---|
| A1 | 直墙两端到切点（或顶点）的距离 | ≤ 0.5 mm |
| A2 | 每个转角的弧片片数，以及每片的朝向、sx、sy | 片数一致；朝向 ≤ 0.01°；缩放 ≤ 1e-4 |
| A3 | 拼缝：R' = R 的角上，弧片与弧片、弧片与直墙在外立面线上的端点距离 | ≤ 0.5 mm |
| A4 | 缩小角：逐个列出 R' 和突出物错开量 | 和 4.2 的公式一致（≤ 0.5 mm） |
| A5 | 矩形楼四个立面的直墙模块序列，和同尺寸矩形走现有 BDF 路线的结果对比 | 完全相同 |
| A6 | 每段选中的语法 | 和参考实现一致 |
| A7 | 屋顶网格轮廓（只比 R' = R 的角） | 与参考轮廓偏差 ≤ 1 cm（受 Offset 节点的圆角细分精度限制） |
| A8 | 截图检查：每种转角至少一张近景 | 弧上线脚连续；凹角无闪烁；无缝隙 |

### 8.3 回归

- `Lvl_TL_Showcase`（BDF 路线）：模块实例数仍是 1,562，各层计数不变。
- `Tools/tl_kit/test_kit_spec.py` 与新的 `test_corner_math.py` 全过。
- `BDF_WithTL` 里其他 27 个样式的行逐字节不变。`tl_make_bdf.py` 已有核对 Epic 源资产的检查，这次再加一项：TL 以外的行数不变。

---

## 9. 风险与先排查的顺序

1. **SplineToSegment 输出的转角角度带不带正负号、零点在哪**：凹凸判断全靠它。
   排查：第一步用已知形状（L 形，正反两个方向）读出它的角度属性，写进 `traps.md` 后再搭第 3 段。
2. **几十个属性运算节点靠 Python 拼**：出错难查。
   应对：按第 6 节的七段逐段搭；每搭完一段就读回中间属性（如 θ、d、L'、朝向），和 `corner_math.py` 对一次再往下走。
3. **Epic 子图的输入属性名约定**（`LevelToken`、`FloorSymbol`、`FloorGrammar`、`Mod_Name` 等）：
   调用 `Loop_Subdivide`、`Loop_GroupedPropsCopy` 之前先导出它们的输入和用到的属性。
4. **屋顶圆弧点过密**：`Offset Polygon2D` 的圆角细分密度改不了。
   如果点数太多（每个角 > 64 个点）或偏差超过 1 cm，就改用第 5 段算出的弧点自己拼屋顶轮廓。
5. **用 Python 建带组件的蓝图**：`SubobjectDataSubsystem` 可能不顺。
   退路：关卡里放一个带标签的 spline Actor，加一个按标签读它的 PCGVolume，用法基本一样。
6. **凹角处线脚顶面共面闪烁**：如果出现，就让相邻两段墙在 z 上错开 0.5 mm。
7. **新建弧片网格**：如果 `tl_kit_rebuild_meshes.py` 只能替换已有资产，就补一条首次导入的路径。

---

## 10. 对第一、二部分（对话里已确认的设计）的两处更正

1. **弧片缩放**：第二部分写的是“Y 方向缩放 tan(θ/2n)/tan(5°)”。这样做弧片边会和墙端错开，最多 4.3 mm。
   正确做法是 X、Y 两个方向都缩放，系数见 4.2 的 sx、sy。这样 R' = R 时拼缝是精确的，就是第一部分承诺的“< 0.1 mm”。
2. **缩小角的错开量**：第一部分写的是“约 1–3 cm”。实际上外立面线仍然精确，
   但深度为 x 的突出物会错开 x·(1 − R'/R)，R' = 120 cm 时檐口错开 6.8 cm。
   这只出现在两头都有外凸角、而且长度短于 R·(tan(θ₁/2) + tan(θ₂/2)) 的边上（90° 两角之间就是短于 3 m 的边）。
