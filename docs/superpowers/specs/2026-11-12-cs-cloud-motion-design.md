# City Sample 体积云：时间演变与预设间平滑过渡 设计

> 2026-11-12，分支 `seasonal-weather`。City Sample 天气的工作（`cs_*.py`、`Tools/cs_weather/`、两份报告）都还没提交，
> 本文也先不提交，等用户决定。
>
> 用户目标（/goal 原话）：**"之前我们在city sample的场景实现了不同类型和形状的云，我现在希望这个云能随着时间不断变化，比如在我们之前做的
> 10种体积云效果，它能在时间上有一定的形状的变化，并且我期望我能从当前的体积云平滑的过渡到目标的体积云，正式开始前我需要你评估我的需求，
> 不确定的可以问我，给出可行性分析和实现方案，等我确认后再开始"**。
>
> 可行性分析、三种过渡做法和五个待定问题在 2026-11-12 的对话里给出，用户回复"按推荐确认"。本文把那份方案细化到可以写实施计划。
> 前序工作：10:00 晴天（`cs_clear_sky.py`，报告 `docs/citysample-clear-sky-renderdoc.html`）、11 个照片天气
> （`cs_weather_presets.py`，报告 `docs/citysample-weather-presets.html`）、10 个美术天气（`cs_weather_art.py`，报告
> `docs/citysample-cloud-art.html`）。

---

## 0. 目标、范围与决定

### 0.1 目标

演示关卡 `/CitySamplePCG/Levels/L_CitySamplePCG_Demo` 上的体积云：

1. **随时间变化**：每种云按自己的物理有形状上的变化（风推移、原地生灭、各云型特有的动作），不只是整体平移。
2. **平滑过渡**：从当前的云（任一预设）过渡到目标预设的云，中间不跳变；默认连光照和整套画面一起过渡，也可以只换云。

**成功标准**（细则见 §8）：

1. 导演不运行时，22 个静态外观（10:00 基线、11 个照片天气、10 个美术天气）和现有 final 图相比不变（差在渲染噪声内）。
2. 10 个美术天气在视口里按 §3.4 的方式动起来，导演每帧的 CPU 开销平均不超过 2 ms。
3. 过渡在录制帧上检查不出跳变（§6.2），离线测试证明参数轨迹连续、端点精确。
4. 交付 10 段演变视频、5 段过渡视频和一页 HTML 说明页，用户看过通过。

### 0.2 范围

**做**：云材质 v2（两个参数槽、按绝对高度、时间输入）；纯 Python 的运动模型；编辑器里的导演（实时播放、过渡、逐帧录制）；
10 个美术天气的运动数据（其它 12 个预设用通用默认值）；视频和说明页；离线测试。

**不做**：

- PIE、打包游戏、Sequencer、Movie Render Queue 里运行（导演是编辑器里的 Python；以后需要时再移植成 C++，见 §9）。
- 物理模拟。这里是运动学动画；模拟驱动的云是 SeasonalWeather M3（Atmos）的事，本设计不改那个插件。
- 预设播放期间的昼夜推进：播放时太阳不动，光照只在 `light: "full"` 的过渡里变化。
- 闪电、雨雪粒子、声音。
- 过渡进行中改目标（§4.7）。
- 保存演示关卡（Epic 的内容，从来只在内存里改）。

### 0.3 选定方案

| 决定 | 选择 |
|---|---|
| 过渡时的光照 | 两种都做：默认 `light: "full"`（太阳/月亮、大气、雾、曝光、调色、星空一起过渡），可切到 `light: "clouds"`（只换云） |
| 过渡方式 | 双云场重叠过渡：材质同时算 A、B 两个云场，A 按自己的方式消散，B 按自己的方式生成，可以同时存在 |
| 运行方式 | 编辑器内 Python 导演，Slate tick 每帧写一个动态材质实例（MID）和少量组件属性 |
| 时间演变 | 每种云按自己的物理各有动作（§3.4） |
| 交付 | 系统 + 10 段演变视频 + 5 段过渡视频 + HTML 说明页 |

### 0.4 前提与约束

**已在 UE 5.8 源码里核对的事实**（决定了上面的方案）：

- 一个场景只渲染一个体积云：后加的 `VolumetricCloudSceneProxy` 顶掉先加的（`VolumetricCloudRendering.cpp` 592–630）。
  两种云不能用两个组件叠化，只能在同一个材质里合成。
- 视线步进步数 = max(`SampleCountMin`, min(96 × `ViewSampleCountScale`, `r.VolumetricCloud.ViewRaySampleMaxCount`) ×
  saturate(层内路径长 / `r.VolumetricCloud.DistanceToSampleMaxCount`))（`VolumetricCloud.usf` 710；默认 15 km；
  本场景 96 × 4 = 384，上限 1024）。云层加厚后，陡视线上薄云分到的样本变少。
- 高级输出的相位和多次散射参数是逐像素求值的（`VolumetricCloud.usf` 746–771），不开逐样本相位时两种云只能共用一套。
- `CloudSampleAttribute` 的 `Altitude` 输出是样本的绝对海拔（cm，`VolumetricCloudMaterialPixelCommon.ush` 61–64），
  材质可以直接按绝对高度工作。
- 组件的蓝图 setter（`SetLayerHeight` 等）对已注册的 Static 组件静默无效（`SceneComponent.h` 1363 `AreDynamicDataChangesAllowed`）。
- 现在的云不会动：`WindX/WindY` 只是固定的 km 偏移，材质里没有时间。

**项目约束**（都是已记录的陷阱）：

- 演示关卡不保存；导演运行期间 autosave 关闭（trap 78）；每次结束都 `cs_weather.py restore {"to": "original"}`。
- 演示关卡开着时重建云材质，编辑器内存曾冲到 98 GB、桥接的回复丢失（trap 136）：延迟执行、轮询结果文件、不重跑。
- Slate tick 回调里不保存资产（trap 132）；导演的 tick 什么都不保存，并且防重入（`cs_wx_lib.guarded`）。
- 编辑器在后台时视口不刷新（trap 133）：导演开着时关掉 `bThrottleCPUWhenNotForeground`（和 `apply` 一样）。
- 离线工具用系统 Python 3.14（`C:\Python314\python.exe`，有 numpy 和 Pillow）；ffmpeg 8.1.1 已装（winget）。

---

## 1. 总体架构

### 1.1 部件

| 文件 | 新 / 改 | 职责 | 依赖 |
|---|---|---|---|
| `Content/Python/cs_cloud_code.py` | 新，纯 Python | 云材质的 HLSL 生成器：参数表、v2 模板、把一份代码展开成 A、B 两段 | 无 |
| `Content/Python/cs_sky_assets.py` | 改 | `material` 阶段按 `cs_cloud_code` 建 v2 图（插针、`Altitude`、输出） | `cs_cloud_code` |
| `Content/Python/cs_wx_resolve.py` | 新，纯 Python | 预设解析：给预设名和原始值快照，得到这个预设的完整画面（组件属性、太阳、云参数、后期、星空） | `cs_weather_presets` |
| `Content/Python/cs_weather.py` | 改 | `apply` 改用解析器（行为不变），并多写 `BottomKm`；`restore` 先停导演 | `cs_wx_resolve` |
| `Content/Python/cs_cloud_motion.py` | 新，纯 Python | 运动模型：给模拟时间、两个槽和过渡状态，算出这一帧要写的全部值 | `cs_wx_resolve`、`cs_cloud_code` |
| `Content/Python/cs_cloud_director.py` | 新，编辑器 | 导演：phase 分发、时钟、Slate tick、MID、写组件、录制 | 上面两个纯模块、`cs_wx_lib` |
| `Content/Python/cs_weather_art.py` | 改 | 10 个美术天气加 `motion` 数据（每个值带 `[值, 原因]`，说明页读同一份） | 无 |
| `Tools/cs_weather/tests/` | 新 | 离线测试：材质契约、解析器、运动模型 | 上面的纯模块 |
| `Tools/cs_weather/encode_clips.py`、`motion_check.py` | 新 | 帧序列转 MP4；跳变检查 | ffmpeg、numpy、Pillow |
| `Tools/cs_weather/build_motion_report.py`、`motion_text.py` | 新 | 生成 `docs/citysample-cloud-motion.html` | 数据、片段 |
| `Tools/cs_weather/check_art.py` | 改 | 参数表改从 `cs_cloud_code` 读（现在用 ast 读 `cs_sky_assets.py`） | `cs_cloud_code` |

`cs_sky_assets.py` 和 `cs_weather.py` 在 import 时就会执行（桥接把脚本整个 exec），所以新的共用逻辑都放进没有副作用的模块，
测试也只 import 这些模块。

### 1.2 每帧的数据流

```
时钟（模拟秒 t，倍数 speed）
  └─> 运动模型 frame(t, 槽 A, 槽 B, 过渡)            纯 Python，可离线测试
        ├─ MID 参数：A 槽、B 槽（按名）、全局参数     ─> 云组件的材质（MID）
        ├─ 组件属性：云层、采样、追踪距离             ─> 只在过渡开始和结束时写
        ├─ 光照和画面（full 模式过渡中）：太阳、光强、色温、大气、雾、后期、曝光
        └─ 星空球：在不在、StarIntensity
  └─> 导演只写和上一帧不同的值，记录每帧耗时
```

### 1.3 和现有工具链的关系

- 静态预设照旧用 `cs_weather.py apply`；它写入的 MI（`MI_CS_Art_*`、`MI_CS_Cloud_*`、`MI_CS_CumulusCloud_Clear`）继续有效。
- 导演 `play` 先用同一个解析器把场景设成起始预设（等价于 `apply`），再把云组件的材质换成导演自己的 MID。
- 导演停止时可以留住当前画面（MID 不动），或者调用 `apply` 回到这个预设的静态 MI。
- `cs_weather.py restore` 先停导演（否则 tick 会继续往组件里写），再照旧恢复。

---

## 2. 云材质 v2（`M_CS_CumulusCloud`）

### 2.1 两个参数槽

- **槽 A** 用现在的参数名（`CoverageBias`、`CellX` ……），所以现有 MI 不用改就是"只有 A 槽"。
- **槽 B** 是同一套参数加前缀 `B_`（`B_CoverageBias` ……）。
- 每个槽的参数 = `SCALARS` 里除 `PixelAngle` 以外的 83 个 + `ExtinctionMax`（从节点外的乘法挪进节点）+ §2.3 的新参数。
- **全局**（两个槽共用）：`PixelAngle`、`PhaseG`、`PhaseG2`、`PhaseBlend`、`MSContribution`、`MSOcclusion`、
  `MSEccentricity`、`Albedo`（没有预设改它）。过渡时由导演插值。
- 新开关 `SlotOn`（默认 1）、`B_SlotOn`（默认 0）：为 0 的槽完全不算。这是统一参数上的分支，不过渡时只算一个槽，开销和现在相同。

**代码怎么展开**：`cs_cloud_code.py` 保存一份密度代码（就是现在的 `CODE` 加 §2.2–2.5 的改动），生成时展开成两段：
A 段用原名，B 段把每个槽参数名换成 `B_` 前缀（按词边界替换已知参数名）。两段各包在 `if (SlotOn > 0) { ... }` 里、各有自己的局部变量，
最后在外面合成（§2.4）。不用"循环加按槽选择"的写法，因为每个样本要多 100 多次选择运算；展开后选择在编译时就定了。
插针总数约 217（每槽约 104，全局 9）。

### 2.2 按绝对高度

- 插针 `H`（`NormAltitudeInLayer`）换成 `Alt`（`CloudSampleAttribute.Altitude`，cm）。
- 每个槽多两个参数：`BottomKm`（这个槽的云层底的绝对海拔，km），`LayerKm`（这个槽的云层高度，km；现在就有）。
- 槽内：`habs = Alt × 1e-5`，`hk = habs − BottomKm`，`lk = LayerKm`；`hk < 0` 或 `hk > lk` 时这个槽没有贡献；`h = hk / lk`。
  后面所有用到 `h / hk / lk / bk / hc / under` 的代码不变。
- **意义**：组件的云层只决定"在哪一段高度里步进"，每个槽的云长在自己的高度上。过渡时把组件的云层扩成两者的并集（§4.4），画面不跳。
- **静态兼容**：`cs_weather.py apply` 给每个预设写 `BottomKm` = 组件的 `layer_bottom_altitude`（`LayerKm` 现在已经自动等于
  `layer_height`），这样 `hk = AltitudeInLayer` = 现在的 `H × LayerKm`，只差舍入。

### 2.3 时间输入

所有新参数默认 0（`EvoAmt` 为 0 时演变项不起作用），所以没有导演时云和现在一样不动。

| 每个槽的参数 | 单位 | 进入哪里 | 由导演怎么算 |
|---|---|---|---|
| `AdvX`, `AdvY` | km | 所有"随空气走"的噪声在 `pn = pkm − Adv` 处取样：扭曲、天气图（两次）、鱼鳞胞、行、外形、鼓包、演变、雨束 | 风速 × 槽龄 τ（§3.2） |
| `DetailOffU/V/W` | UV | 第一层细节噪声的偏移（含推移和上升） | 双精度算好再取小数，见 §3.6 |
| `Detail2OffU/V/W` | UV | 第二层细节噪声（×2.71 那一层）的偏移 | 同上，由未取小数的值 × 2.71 再取小数 |
| `EvoAmt`, `EvoScaleKm`, `EvoPhase` | –, km, 0–1 | 新的演变项：覆盖率乘上外形噪声 G 通道在 z = `EvoPhase` 处的切片 | `EvoPhase = frac(τ / (8 × 寿命))` |
| `BoilShape`, `BoilBillow`, `BoilTurret` | UV（z） | 外形、鼓包、对流泡噪声在 z 方向的偏移：热泡上升 | `frac(−w τ / 该噪声 z 周期)` |
| `MammaPhase`, `MackerelPhase`, `LumpPhase` | UV（z） | 乳状云、鱼鳞胞、雷暴单体轮廓噪声的 z（现在是常数 0.23 / 0.61 / 固定） | `frac(τ / (8 × 寿命))` |
| `RainFall` | UV（z） | 雨束噪声的 z（现在是 `hk × 0.08`）：雨束下落 | `frac(0.08 × 落速 × τ)` |
| `SlotOn`, `BottomKm` | –, km | §2.1、§2.2 | 预设的组件值 |

**哪些不跟风走**：雷暴单体（`CellX/Y`、柱、砧、对流泡、单体轮廓、乳状云的位置）、荚状云的透镜场、弧状云的锋面、雨幕圆盘，
仍在 `pkm` 上算，只通过导演改它们的位置参数（§3.3）。驻波就是这样不动的：荚状云的透镜场不跟风走，只有它的高度抖动
（扭曲噪声 `wn`）随风流过。

**演变项**（新）：在天气图覆盖率算出之后，

```
euv = pn.xy / EvoScaleKm
ev  = ShapeTex(float3(euv, EvoPhase)).g                     // 外形噪声 G：Worley FBM，每个周期 8 个胞
e0  = ShapeTex(float3(euv, 0)).g                            // 同一处在相位 0 的值
cov = cov × (1 + 2 × EvoAmt × (smoothstep(0.25, 0.75, ev) − smoothstep(0.25, 0.75, e0)))
```

- 每朵云所在处的 `ev` 会随 `EvoPhase` 起落，单朵云自己长出来再散掉。
- `EvoPhase` 走 1/8 个周期大约换一批图案，所以寿命 ≈ 周期 / 8；z 方向是周期的，循环是无缝的。
- 用和相位 0 的差而不是 `ev` 本身，是为了 τ = 0 时这一项正好为 1：过渡结束的那一帧（`τ_B = 0`）仍是设计画面，每过 8 个寿命又回到设计画面。代价是多一次纹理采样。
- `EvoAmt = 0` 时没有任何变化。具体曲线在调参时可以改，但这两条性质要保留。

### 2.4 两槽合成

- 每个槽算出 `outD_s`、`Cons_s`、`AO_s`、`Alb_s`。
- 消光：`σ = Σ outD_s × ExtinctionMax_s`。两种云在同一处时消光相加，这是物理上的叠加。
- `Cons = max(Cons_A, Cons_B)`：保守密度不能漏掉任何一个槽有云的地方。关掉的槽、以及样本在槽的云层之外时，这个槽的 `Cons` 为 0。
- `AO`、`Alb` 按 `σ_s` 加权平均；`σ` 为 0 时两者都取 1（没有散射，取什么都不影响画面）。
- 自定义节点直接输出 σ 接 `SubsurfaceColor`（消光），节点外原来乘 `ExtinctionMax` 的那个乘法去掉。参数名 `ExtinctionMax` 不变（现在是 A 槽的插针），现有 MI 照样有效。

### 2.5 其它小改动

- **`LensPlates` 的小数部分**：最上面一片按小数部分变薄（`th *= saturate(npl − i)`）。现在 `LensPlates` 跨过整数时会多出或少一整片，
  过渡里会跳；整数值时这一行等于乘 1，和现在相同。
- 现在的 `wind`（`WindX/WindY` 的静态偏移，加在拉伸坐标里）原样保留，和时间推移 `Adv` 互不影响。

### 2.6 兼容与回归验收

- 默认值（`SlotOn` = 1、`B_SlotOn` = 0、时间输入 = 0、`EvoAmt` = 0）加上 `apply` 写的 `BottomKm`，A 槽的密度与现在相同。
- 建好 v2 后，用 `cs_weather.py batch` 把 22 个预设的 final 镜头重拍（tag `v2`），用 `Tools/cs_weather/diff_shots.py` 和 final 比。
- **噪声底**：改材质之前，先用旧材质把两个预设（`base`、`art_storm`）各重拍一次，和它们的 final 比，得到"同一场景拍两次"的差。
- **标准**：v2 每张图的 `mean_rgb` 和 `p999_luma8` 不超过噪声底的 1.5 倍。超了就停下查原因。
- 通过后重新保存 MI（`cs_weather_save_mis.py`），让磁盘上的 MI 也带上 `BottomKm`。

### 2.7 重建流程

- `cs_sky_assets.py {"phase": "material"}` 本来就延迟执行，结果写在 `Saved/Reports/cs_weather/assets_result.json`。只轮询这个文件，不重跑。
- 能选的话，在编辑器刚启动、还没打开演示关卡时重建；从小关卡切到演示关卡是安全的（危险的是从大关卡切走，trap 79/83）。
- 第一步是 spike（§10 M1）：在临时材质 `M_CS_CloudV2Probe` 上生成 v2 代码并编译，确认约 217 个插针能编、记下编译时间和指令数，然后删掉临时材质。

---

## 3. 时间演变

### 3.1 时钟

- **模拟时间** `t`（秒）每帧前进 `dt × speed`，`speed` 默认 30（实时下云移动得太慢）；可以暂停、调倍数、跳到某个时刻。
- **槽龄** `τ`：每个槽从装进它的预设开始计时，推移和演变都用 τ。
- 过渡开始时，目标预设装进 B 槽，`τ_B` 从 `−过渡时长` 起算。这样过渡结束的那一刻正好 `τ_B = 0`，画面就是设计好的那一帧，之后继续动。
- 录制时 `t` 按帧精确步进（§6.1），每帧在拍照期间冻结。

### 3.2 三种通用机制

1. **风推移**：`Adv(τ) = v × τ × (cos θ, sin θ)`（km；θ 是空气移动的指向，罗盘角，北 = +X、东 = +Y，和镜头 yaw 一致）。
2. **原地生灭**：演变项（§2.3），参数是 `EvoAmt`（幅度）、`EvoScaleKm`（单朵云的尺度）、寿命（分钟）。
3. **翻滚**：细节噪声相对空气的移动。
   - 细节噪声可以比空气快一点：`detail_speed`，默认 1.0。
   - 积云的热泡往上冒：细节、外形、鼓包、对流泡噪声的 z 偏移，用上升速度 m/s 描述。
   - 乳状云和鱼鳞胞在原地变形：`MammaPhase`、`MackerelPhase`。
   - 雨束往下落：`RainFall`。

### 3.3 特有动作：调制器

在预设参数上叠加随 τ 变化的量，数据里每条都带原因：

- `osc`：`值 = 基值 + 幅度 × (sin(2π τ / 周期 + 初相) − sin(初相))`，τ = 0 时为 0，用于上冲云顶起伏、云砧伸缩、荚状云呼吸、冰晶幡摆动、云海顶面起伏。
- `approach`：一组位置参数沿指向移动，τ ≥ 0 时位移为 `D × (1 − e^(−v τ / D))`：先按速度 v 推进，最后停在距离 D 处。
  τ < 0 时（过渡期间目标槽的年龄）按速度 v 线性外推（位移 v τ，在上风方向），两段在 τ = 0 处位置和速度都连续。
  弧状云的锋面和它后面的雨幕用它：推进有界，长时间播放也不会穿过城市、跑出构图。
- 调制器在 τ = 0 时都不改变参数，所以槽龄为 0 的画面就是预设本身。
- 调制器的输出再经过 §4 的生成/消散轨道（过渡时）。

### 3.4 10 种美术天气的运动

下表是初值，写进 `cs_weather_art.py` 每个预设的 `motion`；M4 里看实时画面再调。

| 预设 | 风（速度 → 指向） | 原地生灭 | 翻滚 / 特有动作 | 片段倍数 |
|---|---|---|---|---|
| 鱼鳞天 | 15 m/s → 300°（横穿鱼鳞行，即风切变方向；离镜头而去） | 幅度 0.35，寿命 12 min | 鱼鳞胞原地变形（`MackerelPhase`，12 min）；行随风横移 | 60 |
| 云海 | 2 m/s → 200° | 幅度 0.1（几乎满覆盖），15 min | 云顶鼓包上冒 0.5 m/s；`TypeMax` 起伏 ±0.03、20 min | 60 |
| 浓积云塔 | 6 m/s → 250° | 幅度 0.6，30 min（一座座长高、衰减） | 鼓包上冒 3 m/s，外形 1 m/s，细节 2 m/s | 120 |
| 雨后云隙光 | 8 m/s → 300°（云层往太阳那边漂） | 幅度 0.4，25 min（云缝开合，光束跟着扫） | — | 60 |
| 远方雷暴 | 低层 5 m/s → 200°（周围淡积云和雨束）；单体不动 | 周围淡积云 0.5，20 min | 对流泡上冒 6 m/s；`OvershootKm` 起伏 ±0.4 km、8 min；`AnvilShiftKm` 伸缩 ±1.5 km、20 min；乳状云变形 10 min；雨束下落 8 m/s；单体轮廓变形 15 min | 60 |
| 卷云余晖 | 40 m/s → 255°（顺着纤维，高空急流） | 幅度 0.3，30 min | `ShearKm` 摆动 ±0.8、15 min（冰晶幡的钩随风切变摆） | 30 |
| 积云街 | 8 m/s → 280°（顺街） | 幅度 0.5，15 min（上风端生成、下风端消散） | 胞元变形 15 min；鼓包上冒 1.5 m/s；行不动（风顺着行） | 60 |
| 弧状云 | 低层入流 6 m/s → 280°（流向锋面） | — | 锋面和雨幕 `approach`：12 m/s → 100°，D = 2.5 km；细节上冒 3 m/s（低云碎片被抬进云墙） | 30 |
| 荚状云 | 25 m/s → 209°（横穿山脊） | — | 透镜场不动（驻波）；透镜的高度抖动随风流过；`LensCut` 呼吸 ±0.03、12 min | 60 |
| 月光积云 | 5 m/s → 250° | 幅度 0.5，20 min | 鼓包上冒 1 m/s | 60 |

### 3.5 没有 `motion` 数据的预设

10:00 基线和 11 个照片天气用 `cs_cloud_motion.MOTION_DEFAULT` 按参数自动配：

- **风速按云层底高度**：低于 2 km 为 6 m/s，2–6 km 为 12 m/s，6 km 以上为 30 m/s；指向 250°。
- **原地生灭**：幅度 0.4，寿命 20 min，尺度 = `WeatherScaleKm / 4`。
- **鼓包**：有鼓包（`BillowAmt` > 0）的上冒 1 m/s。
- **雷暴单体**：有单体的加对流泡上冒；有上冲云顶（`OvershootKm` > 0）的加上冲起伏。

它们都可以当过渡的起点和终点。

### 3.6 精度

- 浮点数据（float32）在坐标很大时会丢精度。离坐标原点越远，同样的偏移在纹理上的精度越差。
- 两层细节噪声的纹素最小（约 1.4–9 m），所以它们的偏移由导演用双精度算好、取小数后再传（`DetailOff*`）。
- 其它噪声的纹素都在 6 m 以上，直接用 `pn = pkm − Adv`。外形噪声在最小尺度（0.8 km / 128）下，`|Adv|` 到约 13 000 km 时量化误差才到 1/4 纹素。
  按 30 倍播放，最快的相关预设（鱼鳞天 15 m/s、外形尺度 1 km）连续播约 10 小时才到这个程度。
- `state` 报告每个槽的 `|Adv|` 和剩余余量；`seek {"t": 0}` 重置。

---

## 4. 过渡

### 4.1 流程

`to {"preset": B, "minutes": 30, "light": "full"}`：

- 时长用模拟分钟，默认 30；也可以给 `"seconds"` 表示墙钟秒。按默认 30 倍播放时，30 模拟分钟就是 60 秒。
- 过渡中不能 `seek`（会被拒绝）。
- 过渡中 `stop` 会中止过渡：默认停在当前帧；`static: true` 时直接 `apply` 目标预设 B。

步骤：

1. **开始**：
   - B 的完整值装进 B 槽，取生成阶段 0 的值，`τ_B = −时长`，`B_SlotOn = 1`。
   - 组件的云层扩成并集，采样和追踪距离按 §4.4 调。
   - 用 `light: "full"` 时，记下 A、B 两端的光照和画面。
2. **进行**：
   - 总进度 `p` 从 0 到 1，加 smoothstep 缓动。
   - A 槽按消散轨道走，B 槽按生成轨道走（§4.2、§4.3）。
   - 光照和画面按 §4.5 插值。
3. **结束**：
   - 同一帧里把 B 槽整套复制进 A 槽，连同它的槽龄 τ 和运动数据，然后 `B_SlotOn = 0`（两段代码相同，画面不变）。
   - 组件云层和采样设成 B 的值，画面停在 B（full），或者保持原来的光照（clouds）。
   - 之后 A 槽就是"当前预设"，继续播放。

### 4.2 时间窗

在总进度 `p` 上，默认：

| | 区间 |
|---|---|
| A 消散 | `p ∈ [0, 0.7]` |
| B 生成 | `p ∈ [0.3, 1]` |
| 光照（full） | `p ∈ [0.1, 0.9]` |

中间一段两者并存。预设可以在 `motion.form_window` / `motion.fade_window` 里改窗口；比如雷暴的生成最好占满整段。

### 4.3 生成和消散轨道

生成进度 `g` 和消散进度 `f` 都在各自的窗里从 0 走到 1。

- **一条轨道** = (参数, 子区间, 起点规则, 缓动)。在子区间里，参数从起点值走到预设值（生成），或者从预设值走到终点值（消散）。
- **默认轨道**由 `cs_cloud_motion` 按预设用到的部件自动生成，预设可以覆盖。
- 消散不是生成的倒放：

| 部件 | 生成（g: 0 → 1） | 消散（f: 0 → 1） |
|---|---|---|
| 覆盖率（所有云） | `CoverageBias` 从预设值 − 1 升到预设值 [0, 0.8]：从最浓的核心向外凝结；`DensityScale` 从 0.4 倍升起 [0, 0.6] | `CoverageBias` 降到预设值 − 1 [0.2, 1]：从边缘蒸发；`DensityScale` 降到 0.3 倍 [0, 0.8] |
| 垂直发展（积云类，`TypeMax` > `TypeMin`） | `TypeMax` 从 `TypeMin` 升起 [0.2, 1]：云塔长高 | `TypeMax` 降到 `TypeMin` [0, 0.6]：塔顶塌下 |
| 鼓包、对流泡 | `BillowAmt`、`TurretAmt` 从 0 升起 [0.4, 1]：云成熟才有花椰菜 | 降到 0 [0, 0.5] |
| 鱼鳞胞 | `MackerelGap` 从 1 降到预设值 [0, 0.8]：胞从中心长出 | 升回 1 [0.2, 1] |
| 雷暴单体 | `CellStrength` 0→1 [0, 0.15]；`CellRadiusKm` 从 0.35 倍升起 [0, 0.5]；`CellTopH` 从云底往上长 [0.05, 0.6]；`CellSolid` 升起 [0.3, 0.7]；`AnvilRadiusKm` 从柱半径铺到预设值 [0.55, 0.9]；`AnvilShiftKm` [0.6, 1]；`OvershootKm` [0.75, 0.95]；`RainDensity` [0.6, 0.9]；`MammaAmt` [0.85, 1] | 上升气流先停：`OvershootKm`→0 [0, 0.3]，`TurretAmt`→0 [0, 0.4]，`RainDensity`→0 [0, 0.4]，`CellSolid`→0 [0, 0.5]；柱塌下：`CellRadiusKm`→0.05 倍 [0.2, 0.7]（砧那一段的半径由 `AnvilRadiusKm` 决定，所以砧还在）；`MammaAmt`→0 [0.3, 0.7]；砧最后变薄消失：`CellDensity`、`CellStrength`→0 [0.6, 1] |
| 弧状云 | 锋面的位置由 `approach` 调制器给出：τ 为负时在上风方向 v·\|τ\| 处（30 分钟过渡约 21.6 km），τ = 0 时到达预设位置；`FrontAmt` 0→1 [0, 0.4] | 继续向前推进 10 km，`FrontAmt`、`FrontDensity`→0 [0.2, 1] |
| 荚状云 | `LensCut` 从 1 降到预设值 [0, 0.7]：透镜从核心长大；`LensPlates` 从 1 升起 [0.4, 1]：一片片叠上去 | `LensCut`→1 [0, 0.8]，`LensPlates`→1 [0, 0.5] |
| 雨幕（单体以外，如弧状云后的雨） | `RainDensity` [0.6, 0.9]：云成熟才下 | `RainDensity`→0 [0, 0.4]：云散之前先停 |

- **结构参数不插值**（`RollAmt`、`MackerelAmt`、`LensAmt`、`StretchX`、`StretchAngle`、`ShearKm`、尺度类参数）：每个槽始终是自己预设的值，
  靠覆盖率和上面的轨道出现、消失。这正是双槽的好处：不用把一种云的结构"变形"成另一种。
- A、B 用到同一种部件时（比如都有雷暴单体）各在各的槽里，表现为旧的散掉、新的在别处长起来。

### 4.4 并集云层与采样

**开始时**：

| 属性 | 值 |
|---|---|
| `layer_bottom_altitude` | min(A 底, B 底) |
| `layer_height` | max(A 顶, B 顶) − 底 |
| `view_sample_count_scale` | 4 × clamp(并集高 / max(A 高, B 高), 1, 10.67 / 4)，上限对应 `ViewRaySampleMaxCount` 1024 |
| `tracing_max_distance`、`shadow_tracing_distance` | 两者取大 |

**结束时**：设成 B 的值。

- 这几个属性只在开始和结束各写一次。用编辑器属性写入（`set_editor_property`），不用蓝图 setter，因为组件可能是 Static。
- **开销**：跨高度很大的过渡（比如云海 0–0.4 km 到卷云 8.5–10 km）采样数会到上限，云的开销是平时的数倍，只在过渡期间。

### 4.5 光照和画面

**`light: "full"`**（默认），按光照窗里的进度插值。范围是解析器给出的每一个受管理的属性（预设之间实际不同的有：大气的
`mie_scattering_scale / mie_scattering / mie_absorption(_scale) / mie_anisotropy / mie_exponential_distribution /
other_absorption(_scale) / multi_scattering_factor / sky_and_aerial_perspective_luminance_factor`，雾的密度、衰减、第二层雾和
体积雾散射分布，方向光的光强、色温，云组件的属性）。规则按类型：

- **数值**线性插值；**光强**按对数插值（月光 0.25 lux 到白天 120 000 lux 之间按"档"走）。
- **颜色**逐分量、**结构**（第二层雾）逐字段线性插值。
- **太阳**：仰角、方位分别插值，方位走短弧。
- **曝光**：所有预设都锁定曝光（min = max，EV100），按 EV 线性插值，也就是按档。
- **后期**：每个受管理的设置都插值。只有一端覆盖了的设置，另一端取引擎默认值：导演启动时从一个默认的 `PostProcessSettings` 读出，传给运动模型。
  覆盖开关在任一端覆盖时打开，结束时设成 B 的开关。
- **全局材质参数**（`PhaseG` 等）线性插值。
- **开关和枚举**：
  - `use_per_sample_atmospheric_light_transmittance` 在任一端为开时全程开，结束时设成 B 的值。
  - `cast_shadows_on_clouds` 跟着拥有它的那个槽：它的阶段（A 槽看 1 − f，B 槽看 g）低于 0.1 时关、高于 0.1 时开。
  - 其余开关和枚举在 `p = 0.5` 切换。
- 云组件的属性（云层、采样、追踪距离）不在这里插值，按 §4.4 在开始和结束各写一次。

**`light: "clouds"`**：太阳、光强、色温、大气、雾、后期、曝光、星空都保持当前预设的值。

- 只有云自己的东西过渡：两个槽、组件云层、采样、追踪距离，以及云的光学参数（相位、多次散射），因为它们属于云的种类（水滴、冰晶）。
- 过渡结束后，画面的光照来源仍是原来的预设；以后再做 full 过渡时，从这个光照出发。

### 4.6 星空球

- 一端是夜景（有 `night_sky`）时，用 full 模式过渡：
  - 光强降到 10 lux 以下时生成星空球，之后 `StarIntensity` 从 0 升到目标值。
  - 白天 120 000 lux 到月光 0.25 lux 按对数插值，10 lux 大约在光照进度 0.72 处。
  - 离开夜景时反过来：`StarIntensity` 先降到 0，光强升过 10 lux 时删掉星空球。
- **风险**：星空球是天空材质，生成或删掉的那一帧会把"大气自己画天空像素"换成"星空球用 SkyViewLUT 画天空"，天空渐变可能跳一次。
- M5 用跳变检查（§6.2）实测。跳得明显就改成：只要是进出夜景的过渡，星空球从开始到结束一直在，跳变挪到过渡开始那一帧，并在说明页里写明。

### 4.7 不做：中途改目标

过渡进行中再发 `to` 会被拒绝，并报告当前进度；要么等它结束，要么 `stop`。两个槽都占着时再接新目标要第三个槽或者强行收尾，v1 不做。

---

## 5. 导演（`cs_cloud_director.py`）

### 5.1 phase

一次调用一个 phase，和项目里其它驱动一样。状态文件在 `Saved/Reports/cs_cloud_motion/director.json`。

| phase | 参数 | 作用 |
|---|---|---|
| `play` | `preset`（缺省为当前预设）、`speed`（30）、`t`（0） | 把场景设成该预设（同 `apply`），云组件换成导演的 MID，开始走时钟 |
| `pause` / `resume` | — | 时钟停 / 走（tick 继续，画面不动） |
| `speed` | `speed` | 改倍数 |
| `seek` | `t` | 跳到模拟时刻 |
| `to` | `preset`、`minutes` 或 `seconds`、`light`（`full`/`clouds`） | 开始过渡（§4） |
| `state` | — | 时钟、倍数、两个槽（预设、τ、阶段）、过渡（p、模式、起止）、每帧耗时（最近 100 帧的平均和最大）、`|Adv|` 余量、星空球、错误 |
| `stop` | `static`（false） | 停 tick；`static: true` 时回到该预设的静态 MI（`apply`） |
| `record` | 见 §6.1 | 逐帧录制 |

### 5.2 每帧

1. 读墙钟 `dt`，更新 `t`。
2. 运动模型算这一帧的全部值。
3. 只写有变化的：MID 标量/向量参数、组件属性、太阳旋转、后期、星空球。
4. 记录耗时，每 2 秒写一次心跳。

- tick 用 `cs_wx_lib.guarded` 防重入；不开 `ScopedEditorTransaction`、不调 `modify()`（每帧都开事务会把撤销栈撑爆，也没必要）。
- **MID**：父材质是 `M_CS_CumulusCloud`，具体用哪个创建接口实现时按 skill 的做法现场确认
  （`KismetMaterialLibrary.create_dynamic_material_instance` 或 `MaterialInstanceDynamic` 的工厂函数）。
- **后期**：每帧整体写 `settings` 结构的开销在 M4 测；太贵的话只在 full 过渡期间写。

### 5.3 安全

- **拒绝运行**：当前关卡不是演示关卡时（`cs_wx_lib.require_level`）；或者有截图队列、批处理在跑时。
- **开始时**：和 `apply` 一样关掉 autosave 和 CPU 节流。
- **出错时**：tick 抛异常就自停，错误写进状态文件。心跳超过 5 秒没更新，说明 tick 已经不在了（比如编辑器重载了 Python），`state` 会这样报告。
- `cs_weather.py restore` 先停导演；导演自己不恢复关卡。

### 5.4 实时显示

- 实时播放时，导演把 `r.VolumetricRenderTarget.Mode` 设成 0（四分之一分辨率追踪 + 时域重建，游戏里移动的云就是这样画的）；停下或录制时恢复成 3。
- M4 里对比两种模式下移动的云，确认 0 更稳。倍数大时实时画面会有拖影，成片没有（§6.1）。

---

## 6. 录制与成片

### 6.1 逐帧录制

```
record {"clip": "motion_art_storm", "preset": "art_storm",                    # 或者 "transition": {"from": A, "to": B,
        "seconds": 10, "fps": 30, "speed": 60,                                 #   "minutes": 30, "light": "full"}
        "camera": "CS_ART_Storm",                                              # 或者 {"from": 镜头, "to": 镜头}
        "res": [1920, 1080], "max_commit_gb": 64}
```

- 第 k 帧的模拟时刻 `t_k = t_0 + k × speed / fps`。
- 每一帧：把值设好并冻结时钟，再走现在静态出图的路子：Mode 3 + `r.HighResScreenshotDelay 32` 帧，HighResShot 拍下，等 PNG 写完再进下一帧。
  冻结期间时域累积收敛到静止画面，所以成片没有拖影、没有颗粒。
- 帧文件名带片段名前缀，存在 `Saved/Screenshots/WindowsEditor/`；编码脚本把它们收进 `Saved/Reports/cs_cloud_motion/frames/<clip>/`。
- 可以中断后续拍，已有的帧跳过。
- 和批处理一样，编辑器的私有提交内存超过 `max_commit_gb` 就自停（trap 132 的教训）。
- **镜头**：可以固定一个，也可以从 A 的镜头移到 B 的镜头。用辅助相机 `CS_MOTION_Cam`：位置线性插值，俯仰和朝向分别插值（朝向走短弧，相机没有滚转），
  FOV 线性插值，用同一个缓动进度。一段片段只有一个输出尺寸，取第一个镜头的分辨率和宽高比。
- **用户相机**：录制只动辅助相机，不碰 `CS_SkyCam` 和用户的视口。

### 6.2 编码与跳变检查

- `Tools/cs_weather/encode_clips.py <clip>`：ffmpeg 转 H.264 MP4（`libx264`，CRF 20，`preset slow`，`yuv420p`）。
  每段同时出一张海报帧，再出一条缩略帧带供说明页用。
- `Tools/cs_weather/motion_check.py <clip>`：
  - 每帧先 8× 盒式缩小（和 `diff_shots.py` 一样，抹掉云的采样噪声），再算相邻帧的平均亮度差 `d_k`。
  - 过渡段里任何一帧的 `d_k` 超过整段中位数的 3 倍，就算跳变，列出帧号。
  - 输出 JSON 和一张 `d_k` 曲线图。

### 6.3 片单

- **演变**：10 个美术天气各 10 秒，30 fps，用各自的主镜头（`shots` 里的第一个），倍数按 §3.4。
- **过渡**：5 段，各 16 秒：前 1 秒播放 A，中间 14 秒是 30 模拟分钟的过渡，最后 1 秒播放 B。
  过渡片段的倍数由过渡时长和 14 秒推出（约 129 倍），`record` 里的 `speed` 对过渡片段不起作用。

| # | 过渡 | 看点 | 光照 | 镜头 |
|---|---|---|---|---|
| 1 | 浓积云塔 → 远方雷暴 | 积云长成积雨云：柱长高、砧铺开、乳状云和雨最后出现；太阳同时落下 | full | `CS_ART_Towers` → `CS_ART_Storm` |
| 2 | 鱼鳞天 → 云海 | 中层的高积云散掉，地面的雾海长起来（并集层 0–4.5 km）；日出前到日出后 | full | `CS_ART_Wide` → `CS_ART_Sea` |
| 3 | 积云街 → 卷云余晖 | 低云散去、高空卷云出现（并集层 1.1–10 km）；上午到黄昏 | full | `CS_ART_Streets` → `CS_ART_Up` |
| 4 | 雨后云隙光 → 月光积云 | 傍晚到夜里：光强降 19 档，星空球出现，星星亮起 | full | `CS_ART_Rays` → `CS_ART_Moon` |
| 5 | 荚状云 → 弧状云 | 驻波透镜收缩消失，阵风锋从远处推进过来；光照保持日落不变 | clouds | `CS_ART_Lens` → `CS_ART_Wide` |

### 6.4 采集时间

- 每帧约 2–3 秒（32 帧延迟加渲染加写 PNG），1 秒成片大约要采 1–1.5 分钟。
- 全部 15 段（10 × 10 秒 + 5 × 16 秒 = 180 秒）约 3–4 小时，无人值守。

---

## 7. 说明页

`docs/citysample-cloud-motion.html`，由 `Tools/cs_weather/build_motion_report.py` + `motion_text.py` 生成，读和导演同一份数据（`[值, 原因]`）。

- **时间怎么进入云材质**：两个槽、绝对高度、三种通用机制、调制器、精度处理。
- **10 种云**：每种云为什么这样动（物理）、参数值、片段（`<video>` 和海报帧）。
- **5 段过渡**：各部件的生成/消散时间线图、片段、看点、跳变检查曲线。
- **开销**：播放和过渡时的 ProfileGPU 数字、导演每帧耗时。
- **局限**：只在编辑器里、精度余量、实时画面的拖影、星空球的处理。

视频放在旁边的 `docs/citysample-cloud-motion/`，用相对路径引用（嵌进 HTML 会有上百 MB）；海报帧和时间线图仍嵌在页面里。
单段 10 秒 1080p 约 3–6 MB，总共约 60–90 MB。

---

## 8. 测试与验收

| 项目 | 怎么验 | 标准 |
|---|---|---|
| 材质契约 | pytest：`cs_cloud_code` 生成的代码 | 每个槽参数都有 A、B 两个插针；B 段里没有漏改名的参数；全局参数只出现一次；默认值是静态兼容的那一组 |
| 预设解析 | pytest：`cs_wx_resolve` 对 22 个预设 | 和 `cs_weather.py apply` 现在的取值规则一致（预设 > 基线 > 原始快照） |
| 运动模型 | pytest：`cs_cloud_motion` | `p = 0` 时等于 A，`p = 1` 时等于 B 的预设值且 `τ_B = 0`；30 fps 下每个参数每帧的变化不超过它的界限；`DetailOff*` 在 [0, 1)；并集层包住两端；22 × 21 对过渡每对抽 50 个进度点都是有限值；调制器有界（锋面位移 ≤ D） |
| 材质 v2 兼容 | 22 个预设重拍 vs final（`diff_shots.py`） | 不超过噪声底的 1.5 倍（§2.6） |
| 导演开销 | `state` 的耗时统计 | 每帧平均 ≤ 2 ms |
| 不过渡时的 GPU | ProfileGPU：播放 vs 同一预设静态 | 云相关各 pass 差 ≤ 10%（同一会话、同样条件，trap：两个编辑器抢 GPU 会抬高读数） |
| 过渡无跳变 | `motion_check.py` 对 5 段过渡 | 没有超过中位数 3 倍的帧 |
| 观感 | 用户看 15 段视频和说明页 | 用户通过 |

现有套件不受影响：`pypcg`、`weather`、MCP、两套 C++ 自动化都不碰。
新套件 `C:\Python314\python.exe -m pytest Tools/cs_weather/tests -q`。CLAUDE.md 的套件表等 City Sample 天气的工作提交时再一起更新。

---

## 9. 风险

| 风险 | 后果 | 应对 |
|---|---|---|
| 约 217 个插针的自定义节点编不过或编得极慢 | 材质 v2 做不出来 | M1 先做 spike；不行就把 B 槽参数打包成向量参数（每个 float4 装 4 个），A 槽保持标量名不变 |
| 重建材质时内存冲高（trap 136） | 编辑器卡死或崩溃 | 延迟执行、轮询结果文件；尽量在小关卡里重建 |
| 过渡时云的开销翻倍，跨高度的过渡采样到上限 | 视口帧率在过渡时明显下降 | 只在过渡期间；可临时降云阴影采样（`cloud_shadow_ray_sample_count_scale`）；录制不受影响 |
| v2 改变了静态外观 | 22 张 final 失效 | §2.6 的回归验收；不通过不往下做 |
| 实时画面里快速移动的云有拖影 | 实时观感差 | 实时用 Mode 0；倍数可调；成片逐帧冻结 |
| 进出夜景时天空跳一次（星空球） | 第 4 段过渡有一帧跳变 | §4.6 的改法，实测后定 |
| Python 每帧写参数太慢 | 编辑器卡顿 | 只写变化的值；后期只在过渡时写；超过 2 ms 就把写入压到每 2 帧一次，或改成参数集合（MPC） |
| 长时间无人值守录制内存上涨 | 崩溃 | 内存上限自停、可续拍；结束后 `restore` |
| 以后要在 PIE、游戏、MRQ 里用 | 需要重做运行方式 | 运动模型是纯函数，移植成 C++ 时照抄，并用同一套 Python 测试当参考，像 SeasonalWeather 的做法 |

---

## 10. 里程碑

每个里程碑结束时做它的检查，通过再往下走。实施计划按这些里程碑写（`docs/superpowers/plans/2026-11-12-cs-cloud-motion.md`）。

| # | 内容 | 检查 |
|---|---|---|
| M1 | Spike（丢弃）：临时材质编译 v2 代码；Python 建 MID 并每帧写 200 个参数的耗时；云组件和太阳的 mobility；用旧材质重拍 `base` 和 `art_storm` 的 final 镜头，得到噪声底（§2.6） | 编译通过并记下时间和指令数；写参数耗时；噪声底数值；方案不需要改，或者记下要改什么 |
| M2 | `cs_cloud_code` + `cs_sky_assets` v2；`cs_wx_resolve` + `cs_weather.py`（`BottomKm`、`restore` 先停导演）；`check_art.py` 改读源 | 契约和解析器测试通过；22 个预设回归通过；MI 重新保存 |
| M3 | `cs_cloud_motion`（时钟、三种机制、调制器、默认规则）+ `cs_weather_art.py` 的 `motion` 数据 | 运动模型测试通过（不含过渡部分） |
| M4 | 导演：`play / pause / resume / speed / seek / state / stop`，实时显示设置 | 10 个美术天气在视口里动起来（截图和短录屏给用户看），每帧耗时达标，不过渡时 GPU 达标 |
| M5 | 过渡：`to`、并集层、生成/消散轨道、full / clouds、星空球 | 过渡测试通过；5 段过渡实时跑通，跳变检查通过 |
| M6 | 录制、编码、跳变检查；录 15 段 | 15 段 MP4；5 段过渡的跳变检查报告 |
| M7 | 说明页；traps.md 记下新陷阱；记忆更新 | 说明页给用户看，用户通过 |
