# TL Spline Building (any-angle seamless corners) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A closed spline drawn in a level drives a TL building whose corners close without a crack at any angle from 15° to 345°: walls butt at each vertex (the official PCGPrimitives shape-grammar layout) and a fan of ≤10° slices fills the wedge that TL's projecting mouldings leave.

**Architecture:** Three layers, each testable on its own. (1) Pure Python: `corner_math.py` (which pier, which grammar, which fan slices for each vertex/edge) and `kit_geometry.py` (how a fan or an acute pier is cut from a storey's profile), both under pytest. (2) Art + data: Blender builds 18 new kit meshes from those modules; `tl_make_bdf.py` adds their rows to `BDF_WithTL`. (3) A PCG graph, `PCG_TL_SplineBuilding`, written by a Python script. Wherever Epic's `BDF_BuildingFromSpline` already has the step we need, the script **copies Epic's node** (`UPCGGraph.add_node_copy`, which carries private inline defaults); new steps use explicit constant nodes. The graph's output is checked instance by instance against `corner_math.py`.

**Tech Stack:** Blender 5.2.1 headless (`E:/Blender/blender-5.2.1-windows-x64/blender.exe -b -P`), UE 5.8.2 editor Python through the `run_unreal_script` MCP bridge (127.0.0.1:8777), PCG + PCGPrimitives + CitySamplePCG content, pytest (`mcp_server/.venv`).

**Spec:** `docs/superpowers/specs/2026-10-09-tl-spline-building-design.md` (commit `e7fc782`). Geometry evidence: `Tools/tl_kit/corner_check/`.

## Global Constraints

- **Scope is TL only.** Never modify any Epic graph or data asset (`/CitySamplePCG/...`, `/PCGPrimitives/...`); they are read, duplicated or node-copied, never saved. The city stage, `Lvl_TL_Showcase` and the SGD route must behave exactly as before (regression: `Lvl_TL_Showcase` still 1,562 module instances).
- **Corner rule (spec §4.1).** Walls run vertex to vertex. Every storey ≥ 1 wall starts with a 150 cm end pier and ends with one. Convex corner → front fan; concave → back fan; convex with turn > 90° (interior < 90°) → both adjoining piers are the acute variant. Fan slices ≤ 10°, n = ⌈|turn|/10°⌉, scale `sx = cos a / cos 5°`, `sy = sin a / sin 5°`, pivot at the vertex, local +X = slice centre direction.
- **Collinear threshold 1°**: `CleanSpline` removes vertices with |turn| < 1°.
- **Support range 15°–345° interior.** Outside it is not guaranteed.
- **Winding.** The graph forces the footprint with `SplineDirection = ForceClockwise`. In UE's `IsClockwiseXY` (shoelace with the cross term negated) that is a **positive** standard shoelace area, i.e. what `corner_math.signed_area > 0` calls counter-clockwise. With it: convex ⇔ `SplineToSegment` angle > 0, and the module's exterior (+X after `MakeRotFromYZ`) is right of travel. Do not "fix" this mismatch of names.
- **Units:** cm in UE and in `corner_math.py`; metres in Blender / `kit_geometry.py` / `tl_kit_spec.json`.
- **PCG generation is asynchronous**: generate in one bridge call, read in the next (traps 18/19, node-classes §0.6). `activate(True)` before `generate_local`. Run `pcg.FlushCache` after any data-asset edit, in a different call from the save (trap 38).
- **`add_edge` fails silently** (trap 14). Every edge goes through `GraphKit.edge`, which checks the edge count and raises with the real pin labels.
- **Never delete then reimport a kit mesh** (references null out); new meshes go through `tl_kit_rebuild_meshes.py`.
- **Scripts live under `Content/Python/`**; pure-Python modules and their tests under `Tools/tl_kit/`.
- **Do not save any level that holds `TLPROBE_*` actors**, and never save the CitySample demo level.
- **Commits** end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`. No push without the user's choice.

## Rulings (decisions this plan makes where the spec is silent or wrong)

- **R1 Short edges.** The spec says "an edge shorter than 300 cm gets one stretched WS1". `[EL][WS1][ER]` cannot fit below 150 + 325 + 150 = **625 cm** (subdivision only stretches, never shrinks). So: storey edges < 625 cm and foundation edges < 200 cm get **one filler scaled to the edge length** (it may shrink); edges in [625, FLengths.x) get `[EL][WS1][ER]`. Cost if wrong: short edges between 300 and 625 cm lose their piers; still crack-free because the fans are placed regardless.
- **R2 One pier mesh for L and R.** A flat-ended pier has no moulding return, so its left and right versions are the same geometry. Each storey gets **2 pier meshes** (`EndPier_01`, `EndPierAcute_01`); the symbols `EL`/`ER` share the first, `EAL`/`EAR` the second (same pattern as `C_CE`/`C_E` sharing a corner mesh today). New parts: 4 per storey × 4 + 2 fans at L0 = **18** (spec said 26). Cost if wrong: one more Blender kind and 8 more meshes.
- **R3 Fans have Modules rows.** Fans get symbols `FF` (front) / `FB` (back), `Size` 1 cm, so the graph finds their mesh per level from `BDF_WithTL` (data stays in one place). No grammar references `FF`/`FB`, `EL`…`EAR`, so the BDF route is unaffected.
- **R4 Height parameter is named `Height`.** PCG user parameters cannot be added from Python, so the graph is made by duplicating `/CitySamplePCG/PCG/DataAssets/Buildings/PCG_Bldg_SGD_test` (which owns a `Height` double) and clearing its nodes. Per-building height is a graph-instance override on the component.
- **R5 Roof offset is a constant −50 cm** (TL's `RoofData.Y`), not read from the data at runtime.
- **R6 Props use TL's zero `PropOffset`**, so Epic's PropOffset-rotation nodes are not copied.

## Review Focus

1. **A footprint whose vertices are not all at the same Z** (a spline drawn on uneven ground): the expected behaviour is a level building at the first point's height. Test owner: Task 11 adds a footprint with one vertex raised 50 cm; the probe asserts every storey's modules share one Z.
2. **Reversing the spline in the editor** (winding flips): the building must be identical. Test owner: Task 2 (`test_fan_directions_do_not_depend_on_winding`, `test_square_both_windings`) and Task 11 (the probe regenerates the L-shape with reversed point order and compares instance transforms).
3. **Two adjacent acute corners on one short edge** (< 625 cm): no crack. Test owner: Task 2 (`test_storey_edge_grammar_bands` covers the short rule) and Task 11 (the pentagon has a 20° corner next to a 400 cm edge).
4. **A building lower than one full storey stack** (`Height` below `MinBldgHeight` 1600): the expected behaviour is a building of the minimum stack, not an empty result. Test owner: Task 11 sets `Height = 1000` on one building and asserts L1 and L4 instances exist.
5. **A vertex inside the 1°–2° band**: kept, one slice. Test owner: Task 2 (`test_collinear_vertices_are_dropped`).

---

## File Structure

| File | Create / Modify | Responsibility |
|---|---|---|
| `Tools/tl_kit/corner_math.py` | Create | Reference model: classify vertices, fan slices, per-edge grammar |
| `Tools/tl_kit/test_corner_math.py` | Create | pytest for the model |
| `Tools/tl_kit/kit_geometry.py` | Create | Profile section, acute clip, fan rings, sector outlines (no bpy) |
| `Tools/tl_kit/test_kit_geometry.py` | Create | pytest for the geometry |
| `Tools/tl_kit/kit_common.py` | Modify | `END_PIER_CM`, 61 parts, new symbols, `NON_RULE_SYMBOLS` |
| `Tools/tl_kit/tl_kit_spec.json` | Modify | 18 new parts |
| `Tools/tl_kit/test_kit_spec.py` | Modify | New kinds, counts, symbol rules |
| `Tools/tl_kit/build_tl_kit.py` | Modify | `CollectBuilder`, `prism`, builders for the 4 new kinds |
| `Content/Python/tl_kit_rebuild_meshes.py` | Modify | Bounds checks for the new kinds |
| `Content/Python/tl_make_rules.py` | Modify | Skip the new symbols (SGD route unchanged) |
| `Content/Python/tl_make_bdf.py` | Modify | Rows for `EL ER EAL EAR FF FB` |
| `Content/Python/tl_spike_graph_api.py` | Exists (uncommitted) | One-off answers about the graph API |
| `Content/Python/tl_graph_kit.py` | Create | Graph-authoring helpers used by the graph script |
| `Content/Python/tl_make_spline_graph.py` | Create | Builds `/Game/PCG/TL/PCG_TL_SplineBuilding` |
| `Content/Python/tl_spline_level.py` | Create | Creates/loads `/Game/Map/Lvl_TL_Spline` and places the test buildings |
| `Content/Python/tl_probe_spline_building.py` | Create | Reads every test building, checks A1–A6 against `corner_math` |
| `Content/Python/tl_spline_shot.py` | Create | A7 close-up screenshots |
| `docs/tl-kit-mesh-checklist.md`, `.claude/skills/city-sample-pcg-city-builder/references/traps.md` | Modify | Record what was learned |

---

### Task 1: Editor back up, and the graph-API spike

The editor for this project is **not running** (checked 2026-10-12 12:24). A relaunch exited: `UnrealBuildTool.dll` was rebuilt at 11:11 today, the project's editor modules are out of date, and the automatic rebuild stops with `Result: Failed (FailedDueToEngineChange)` because it would modify engine files (`UnrealEditor-NetCore.dll`, many `UnrealEditor.modules`). The other open editor (PID 36728, "PCG_Codex") shares the engine. `Saved/Autosaves` was moved to `Saved/Autosaves_bak_20261012_restore` so a restore dialog cannot block the bridge.

**Files:** `Content/Python/tl_spike_graph_api.py` (already written, not committed).

- [ ] **Step 1: Ask the user before rebuilding the engine.** Rebuilding modifies `E:\UnrealEngine` binaries that the PCG_Codex editor also uses. Ask: "The engine's build tool was updated at 11:11 today, so PCG_Claude's editor can't start until the engine and project are rebuilt. OK to close nothing, run the build now, and relaunch? (PCG_Codex may need restarting afterwards.)" Wait for yes.

- [ ] **Step 2: Build** (after yes)

```powershell
& "E:\UnrealEngine\Engine\Build\BatchFiles\Build.bat" PCG_ClaudeEditor Win64 Development -Project="E:\PCG_Claude\PCG_Claude.uproject" -WaitMutex
```
Expected: exit 0, `Result: Succeeded`. If UBT refuses because PCG_Codex holds engine DLLs, stop and report the exact message.

- [ ] **Step 3: Launch and wait for the bridge**

```bash
("/e/UnrealEngine/Engine/Binaries/Win64/UnrealEditor.exe" "E:/PCG_Claude/PCG_Claude.uproject" > /dev/null 2>&1 &)
for i in $(seq 1 60); do netstat -ano | grep -q "127.0.0.1:8777.*LISTENING" && { echo up; break; }; sleep 10; done
```
Expected: `up`. Then run `tl_editor_no_throttle.py` once (background throttling stalls screenshots).

- [ ] **Step 4: Run the spike**: `run_unreal_script("tl_spike_graph_api.py")`.
Record in the task report the exact values of: `q1_import_text`, `q1_new_selector`, `q1_output`, `q1_operation`, `maths_inputs`, `q2_const`, `const_outputs`, `q3_*`, `q4_edges`, `q5_*`. Decision rules for Task 7:
  - If `q1_import_text` reads back `PCGBegin(NextAngle)PCGEnd`, selectors are set with `import_text("PCGBegin(<x>)PCGEnd")` (the default in `tl_graph_kit.py`). If not, but `q1_new_selector` shows `Foo`, switch `_set_selector` to `unreal.PCGAttributePropertySelectorBlueprintHelpers.set_attribute_name` for plain names and stop on `$`/`@` selectors with the report.
  - `q4_edges` must be `[0, 1]`; `maths_inputs` gives the binary maths pin names (expected `["InA", "InB", ...]`).
  - `q5_inputs` gives the three string-op pin names (expected `InA`, `InB`, `InC`). Put the real names into `STRING3_PINS` in `tl_graph_kit.py`.

- [ ] **Step 5: Clean up**: `run_unreal_script("tl_spike_graph_api.py", {"clear": true})` → `{"deleted": true}`.

- [ ] **Step 6: Commit the spike script**

```bash
git add Content/Python/tl_spike_graph_api.py
git commit -m "Add the graph-API spike for the spline building graph" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Reference corner model (pure Python, TDD)

**Files:**
- Modify: `Tools/tl_kit/kit_common.py` (append)
- Create: `Tools/tl_kit/corner_math.py`, `Tools/tl_kit/test_corner_math.py`

**Interfaces — Produces** (used by Tasks 7, 9, 11):
- `corner_math.clean(pts) -> list[(x, y)]`
- `corner_math.classify(pts) -> list[{"turn": float, "convex": bool, "acute": bool}]`
- `corner_math.fan(pts, i) -> list[{"k", "yaw", "a", "sx", "sy", "kind"}]`
- `corner_math.edge_plan(pts, i, level) -> {"length", "short", "symbol", "scale", "grammar"}`
- `kit_common.END_PIER_CM = 150.0`

- [ ] **Step 1: Append to `Tools/tl_kit/kit_common.py`**

```python

# Spline building (docs/superpowers/specs/2026-10-09-tl-spline-building-design.md).
# End piers replace the corner pieces: one 150 cm pier at each end of every
# wall, flat-ended, so two walls butt at the vertex at any angle.
END_PIER_CM = 150.0
```

- [ ] **Step 2: Write the failing test** `Tools/tl_kit/test_corner_math.py`

```python
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corner_math as cm
import kit_common


def regular(n, r=3000.0):
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def poly_with_corner(interior_deg, arm=4000.0):
    """A counter-clockwise quad whose vertex 0 has the given interior angle."""
    h = math.radians(interior_deg) / 2
    return [(0.0, 0.0), (arm * math.cos(h), -arm * math.sin(h)),
            (arm * 1.6, 0.0), (arm * math.cos(h), arm * math.sin(h))]


def rect(w, d):
    return [(0.0, 0.0), (w, 0.0), (w, d), (0.0, d)]


def test_square_both_windings():
    sq = rect(6000, 3000)
    for pts in (sq, sq[::-1]):
        c = cm.classify(pts)
        assert all(v["convex"] and not v["acute"] for v in c)
        assert all(abs(abs(v["turn"]) - 90) < 1e-9 for v in c)
        f = cm.fan(pts, 0)
        assert len(f) == 9
        assert all(abs(s["sx"] - 1) < 1e-12 and abs(s["sy"] - 1) < 1e-12 for s in f)
        assert {s["kind"] for s in f} == {"front"}


def test_hexagon_slices_are_full_size():
    pts = regular(6)
    for i in range(6):
        f = cm.fan(pts, i)
        assert len(f) == 6
        assert all(abs(s["a"] - 5) < 1e-9 for s in f)


def test_slices_tile_the_turn_exactly():
    for interior in (15, 20, 30, 45, 60, 89, 91, 120, 150, 178):
        pts = poly_with_corner(interior)
        f = cm.fan(pts, 0)
        c = cm.classify(pts)[0]
        assert abs(sum(2 * s["a"] for s in f) - abs(c["turn"])) < 1e-9
        for s0, s1 in zip(f, f[1:]):          # neighbours abut edge to edge
            gap = abs(cm.wrap(s1["yaw"] - s0["yaw"])) - (s0["a"] + s1["a"])
            assert abs(gap) < 1e-9
        assert all(s["a"] <= cm.SLICE_HALF_DEG + 1e-12 for s in f)
        assert len(f) <= cm.MAX_FAN_SLICES


def test_slice_scale_matches_its_half_angle():
    pts = poly_with_corner(135)               # turn 45 -> 5 slices of 9 deg
    f = cm.fan(pts, 0)
    assert len(f) == 5
    a = math.radians(4.5)
    assert abs(f[0]["sx"] - math.cos(a) / math.cos(math.radians(5))) < 1e-12
    assert abs(f[0]["sy"] - math.sin(a) / math.sin(math.radians(5))) < 1e-12


def test_acute_threshold():
    assert cm.classify(poly_with_corner(89))[0]["acute"]
    assert not cm.classify(poly_with_corner(90.5))[0]["acute"]
    assert cm.classify(poly_with_corner(15))[0]["acute"]


def test_l_shape_has_one_concave_back_fan():
    L = [(0, 0), (6000, 0), (6000, 3000), (3000, 3000), (3000, 6000), (0, 6000)]
    for pts in (L, L[::-1]):
        c = cm.classify(pts)
        assert sum(not v["convex"] for v in c) == 1
        i = next(k for k, v in enumerate(c) if not v["convex"])
        assert {s["kind"] for s in cm.fan(pts, i)} == {"back"}
        assert not c[i]["acute"]


def test_collinear_vertices_are_dropped():
    pts = [(0, 0), (3000, 0), (6000, 30), (6000, 3000), (0, 3000)]   # 0.57 deg kink
    assert len(cm.clean(pts)) == 4
    pts = [(0, 0), (3000, 0), (6000, 80), (6000, 3000), (0, 3000)]   # 1.53 deg kink
    cleaned = cm.clean(pts)
    assert len(cleaned) == 5 and len(cm.fan(cleaned, 1)) == 1


def test_fan_directions_do_not_depend_on_winding():
    pts = regular(5)
    a = sorted(round(s["yaw"], 6) for i in range(5) for s in cm.fan(pts, i))
    r = pts[::-1]
    b = sorted(round(s["yaw"], 6) for i in range(5) for s in cm.fan(r, i))
    assert a == b


def test_fan_sweeps_from_incoming_to_outgoing_normal():
    sq = rect(6000, 3000)                      # CCW: exterior right of travel
    f = cm.fan(sq, 1)                          # the corner at (6000, 0)
    assert abs(f[0]["yaw"] - (-85.0)) < 1e-9   # from -90, the bottom edge's normal
    assert abs(f[-1]["yaw"] - (-5.0)) < 1e-9   # to 0, the right edge's normal


def test_storey_edge_grammar_bands():
    f0, f1, f2 = kit_common.level_grammars(1)
    for length, want in ((624.9, None), (625.0, "[EL][WS1][ER]"), (949.0, "[EL][WS1][ER]"),
                         (950.0, f0), (3725.0, f1), (5400.0, f2)):
        p = cm.edge_plan(rect(length, 4000), 0, 1)
        if want is None:
            assert p["short"] and p["symbol"] == "WS1"
            assert abs(p["scale"] - length / 325.0) < 1e-12
        else:
            assert not p["short"]
            assert p["grammar"] == want.replace("[FC", "[EL").replace("[LC", "[ER"), (length, p)


def test_foundation_edges_have_no_piers():
    p = cm.edge_plan(rect(6000, 4000), 0, 0)
    assert p["grammar"] == "[FS2]+"
    short = cm.edge_plan(rect(150, 4000), 0, 0)
    assert short["short"] and short["symbol"] == "FS2" and abs(short["scale"] - 0.75) < 1e-12


def test_acute_ends_use_the_acute_piers():
    pts = poly_with_corner(30)
    assert cm.edge_plan(pts, 0, 1)["grammar"].startswith("[EAL]")
    assert cm.edge_plan(pts, 3, 1)["grammar"].endswith("[EAR]")
    assert cm.edge_plan(pts, 1, 1)["grammar"].startswith("[EL]")


def test_cornice_level_uses_its_own_grammar():
    g = cm.edge_plan(rect(6000, 4000), 0, 4)["grammar"]
    assert "[E1]" not in g and g.startswith("[EL]") and g.endswith("[ER]")
```

- [ ] **Step 3: Run it, expect failure**

Run: `./mcp_server/.venv/Scripts/python.exe -m pytest Tools/tl_kit/test_corner_math.py -q`
Expected: `ModuleNotFoundError: No module named 'corner_math'`.

- [ ] **Step 4: Write `Tools/tl_kit/corner_math.py`**

```python
"""corner_math.py -- pure-Python reference model of the corner and edge rules in
/Game/PCG/TL/PCG_TL_SplineBuilding
(docs/superpowers/specs/2026-10-09-tl-spline-building-design.md, section 4, and
docs/superpowers/plans/2026-10-12-tl-spline-building.md, rulings R1-R3).

Units are cm; coordinates are UE world XY treated as a plain 2D plane. A
footprint is the closed facade line as a list of (x, y) vertices, either
winding. The graph is checked against this model (acceptance A1-A6), so every
rule the graph applies to a corner or an edge is written here first.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_common  # noqa: E402

COLLINEAR_DEG = 1.0        # |turn| below this: the vertex is dropped (CleanSpline)
SLICE_MAX_DEG = 10.0       # one fan slice covers at most this much turn
SLICE_HALF_DEG = 5.0       # the fan meshes are modelled as +-5 deg wedges
MAX_FAN_SLICES = 18        # template points per corner: ceil(180 / 10)
ACUTE_TURN_DEG = 90.0      # a convex corner turning more than this is acute


def level_rules(level):
    """Edge rules for one storey. pier_cm: end pier run (0 = no piers);
    filler_cm: the stretchable filler's native run; mid_grammar: the grammar
    for edges too short for F0 but long enough for two piers and a filler."""
    if level == 0:
        return {"pier_cm": 0.0, "filler_cm": 200.0, "filler": "FS2",
                "mid_grammar": "[FC][FS2]+[LC]", "foundation": True,
                "grammars": kit_common.level_grammars(0),
                "flengths": kit_common.level_flengths_cm(0)}
    return {"pier_cm": kit_common.END_PIER_CM, "filler_cm": 325.0, "filler": "WS1",
            "mid_grammar": "[FC][WS1][LC]", "foundation": False,
            "grammars": kit_common.level_grammars(level),
            "flengths": kit_common.level_flengths_cm(level)}


def signed_area(pts):
    """Shoelace area; > 0 when the vertices wind counter-clockwise with x to
    the right and y up."""
    n = len(pts)
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
                     for i in range(n))


def wrap(deg):
    """Wrap an angle to (-180, 180]."""
    d = (deg + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def turn_deg(prev, cur, nxt):
    """Signed turn at `cur` from edge prev->cur to edge cur->nxt, degrees;
    > 0 is a left turn in the same convention as signed_area."""
    a_in = math.degrees(math.atan2(cur[1] - prev[1], cur[0] - prev[0]))
    a_out = math.degrees(math.atan2(nxt[1] - cur[1], nxt[0] - cur[0]))
    return wrap(a_out - a_in)


def clean(pts, collinear_deg=COLLINEAR_DEG):
    """Drop coincident vertices and vertices whose |turn| < collinear_deg,
    repeating until stable (what CleanSpline does with the same threshold)."""
    out = [tuple(map(float, p)) for p in pts]
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            prev, cur, nxt = out[i - 1], out[i], out[(i + 1) % len(out)]
            if (math.hypot(cur[0] - prev[0], cur[1] - prev[1]) < 1e-6
                    or abs(turn_deg(prev, cur, nxt)) < collinear_deg):
                del out[i]
                changed = True
                break
    return out


def classify(pts):
    """Per vertex: the signed turn, whether the corner is convex (it turns the
    same way the footprint winds) and whether it is acute (convex, interior
    angle < 90 deg)."""
    s = 1.0 if signed_area(pts) > 0 else -1.0
    res = []
    for i in range(len(pts)):
        t = turn_deg(pts[i - 1], pts[i], pts[(i + 1) % len(pts)])
        convex = t * s > 0
        res.append({"turn": t, "convex": convex,
                    "acute": convex and abs(t) > ACUTE_TURN_DEG})
    return res


def exterior_normal_deg(p0, p1, area_sign):
    """Direction (deg) of the exterior normal of edge p0->p1: right of travel
    for a counter-clockwise footprint, left of travel for a clockwise one."""
    a = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
    return wrap(a - 90.0 * area_sign)


def fan(pts, i):
    """The fan slices at vertex i: one dict per slice with its centre direction
    `yaw` (deg, world; the slice mesh's local +X), the half angle `a`, the mesh
    scales `sx`, `sy`, and `kind` ('front' at a convex corner, 'back' at a
    concave one). The slices sweep from the incoming edge's exterior normal to
    the outgoing edge's; the slice mesh's pivot is the vertex."""
    s = 1.0 if signed_area(pts) > 0 else -1.0
    prev, cur, nxt = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
    na = exterior_normal_deg(prev, cur, s)
    nb = exterior_normal_deg(cur, nxt, s)
    sweep = wrap(nb - na)
    if abs(sweep) < COLLINEAR_DEG:
        return []
    n = max(1, math.ceil(abs(sweep) / SLICE_MAX_DEG - 1e-9))
    a = abs(sweep) / (2.0 * n)
    sx = math.cos(math.radians(a)) / math.cos(math.radians(SLICE_HALF_DEG))
    sy = math.sin(math.radians(a)) / math.sin(math.radians(SLICE_HALF_DEG))
    kind = "front" if classify(pts)[i]["convex"] else "back"
    return [{"k": k, "yaw": wrap(na + sweep * (k + 0.5) / n), "a": a,
             "sx": sx, "sy": sy, "kind": kind} for k in range(n)]


def edge_plan(pts, i, level):
    """The edge from vertex i to i+1 on one storey: its length and either the
    grammar the graph writes for it or, for an edge too short for two piers
    and a filler, one stretched filler (`short`, with its run scale)."""
    r = level_rules(level)
    p0, p1 = pts[i], pts[(i + 1) % len(pts)]
    length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    short_cm = r["filler_cm"] + 2.0 * r["pier_cm"]
    if length < short_cm:
        return {"length": length, "short": True, "symbol": r["filler"],
                "scale": length / r["filler_cm"], "grammar": None}
    fl = r["flengths"]
    if length >= fl[2]:
        g = r["grammars"][2]
    elif length >= fl[1]:
        g = r["grammars"][1]
    elif length >= fl[0]:
        g = r["grammars"][0]
    else:
        g = r["mid_grammar"]
    if r["foundation"]:
        g = g.replace("[FC]", "").replace("[LC]", "")
    else:
        cls = classify(pts)
        g = g.replace("[FC", "[EAL" if cls[i]["acute"] else "[EL")
        g = g.replace("[LC", "[EAR" if cls[(i + 1) % len(pts)]["acute"] else "[ER")
    return {"length": length, "short": False, "symbol": None, "scale": 1.0, "grammar": g}
```

- [ ] **Step 5: Run the tests, expect pass**

Run: `./mcp_server/.venv/Scripts/python.exe -m pytest Tools/tl_kit/test_corner_math.py Tools/tl_kit/test_kit_spec.py -q`
Expected: `28 passed` (13 new + 15 existing). This exact model was prototyped on 2026-10-12 and passed.

- [ ] **Step 6: Commit**

```bash
git add Tools/tl_kit/kit_common.py Tools/tl_kit/corner_math.py Tools/tl_kit/test_corner_math.py
git commit -m "Add the reference model for spline building corners and edges" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Kit piece geometry (pure Python, TDD)

**Files:** Create `Tools/tl_kit/kit_geometry.py`, `Tools/tl_kit/test_kit_geometry.py`

**Interfaces — Produces** (used by Task 4):
- `section(boxes, y_probe) -> list[(x0, x1, z0, z1, slot)]`
- `front_at(sec, z0, z1) -> float`
- `acute_clip(boxes, sec) -> list[box]`
- `fan_rings(sec, kind) -> list[(r0, r1, z0, z1, slot)]`, `kind in ("front", "back")`
- `ring_sector_xy(r0, r1, kind) -> list[(x, y)]` (counter-clockwise outline)

- [ ] **Step 1: Write the failing test** `Tools/tl_kit/test_kit_geometry.py`

```python
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_geometry as kg

# The L1 filler as build_tl_kit.build_filler(level=1) emits it for w = 1.5:
# brick slab, then ground_base's three stone strips, plus one short ornament.
L1 = [(-0.30, 0.0, 0.0, 1.5, 0.0, 5.0, "TL_Brick"),
      (0.0, 0.06, 0.0, 1.5, 0.0, 0.45, "TL_Stone"),
      (0.0, 0.10, 0.0, 1.5, 3.60, 4.30, "TL_Stone"),
      (0.0, 0.16, 0.0, 1.5, 4.18, 4.30, "TL_Stone"),
      (0.02, 0.05, 0.10, 0.20, 1.0, 1.1, "TL_Stone")]


def _signed_area(pts):
    n = len(pts)
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))


def test_section_keeps_only_continuous_boxes():
    sec = kg.section(L1, 0.75)
    assert len(sec) == 4
    assert all(len(s) == 5 for s in sec)


def test_front_depth_per_band():
    sec = kg.section(L1, 0.75)
    assert kg.front_at(sec, 0.0, 0.45) == 0.06
    assert kg.front_at(sec, 1.0, 3.0) == 0.0
    assert kg.front_at(sec, 4.18, 4.30) == 0.16


def test_acute_clip_thins_the_body_to_the_front_depth():
    sec = kg.section(L1, 0.75)
    out = kg.acute_clip(L1, sec)
    body = [b for b in out if b[0] < 0]
    for x0, x1, y0, y1, z0, z1, slot in body:
        want = max(kg.front_at(sec, z0, z1), kg.ACUTE_MIN_BODY_M)
        assert abs(-x0 - want) < 1e-9, (z0, z1, x0)
    spans = sorted((b[4], b[5]) for b in body)
    assert spans[0][0] == 0.0 and spans[-1][1] == 5.0
    assert all(abs(a[1] - b[0]) < 1e-9 for a, b in zip(spans, spans[1:]))
    assert [b for b in out if b[0] >= 0] == [b for b in L1 if b[0] >= 0]


def test_fan_rings_split_front_and_back():
    sec = kg.section(L1, 0.75)
    front = kg.fan_rings(sec, "front")
    back = kg.fan_rings(sec, "back")
    assert sorted(r[1] for r in front) == [0.06, 0.10, 0.16]
    assert back == [(0.0, 0.30, 0.0, 5.0, "TL_Brick")]


def test_sector_edges_lie_on_the_5_degree_rays():
    for kind in ("front", "back"):
        for r0, r1 in ((0.0, 0.34), (0.06, 0.16)):
            pts = kg.ring_sector_xy(r0, r1, kind)
            assert _signed_area(pts) > 0
            for x, y in pts:
                if math.hypot(x, y) < 1e-9:
                    continue
                ang = math.degrees(math.atan2(y, x if kind == "front" else -x))
                assert abs(abs(ang) - 5.0) < 1e-9, (kind, x, y)
                assert min(abs(math.hypot(x, y) - r0), abs(math.hypot(x, y) - r1)) < 1e-9
```

- [ ] **Step 2: Run, expect `ModuleNotFoundError: No module named 'kit_geometry'`**

Run: `./mcp_server/.venv/Scripts/python.exe -m pytest Tools/tl_kit/test_kit_geometry.py -q`

- [ ] **Step 3: Write `Tools/tl_kit/kit_geometry.py`**

```python
"""kit_geometry.py -- pure-Python geometry for the spline building's new kit
pieces (end piers, acute end piers, front / back fans). No bpy: build_tl_kit.py
collects the boxes a facade builder emits, hands them here, and turns the
returned boxes / sectors into mesh. Tested by test_kit_geometry.py.

Frames are the kit's UE frame: x outward (facade plane x = 0, relief x > 0,
body x < 0), y along the run, z up. Lengths are metres, like build_tl_kit.py.
A box is (x0, x1, y0, y1, z0, z1, slot); a section box drops y:
(x0, x1, z0, z1, slot).
"""
import math

FAN_HALF_DEG = 5.0          # every fan mesh is a +-5 deg wedge about local +X
ACUTE_MIN_BODY_M = 0.01     # an acute pier keeps at least 1 cm of body


def section(boxes, y_probe):
    """The cross-section of a straight run at y = y_probe: every box whose
    run spans y_probe, with y dropped. Boxes that do not span it (dentils,
    joints, short ornaments) are not part of the continuous profile."""
    return [(b[0], b[1], b[4], b[5], b[6]) for b in boxes if b[2] < y_probe < b[3]]


def z_breaks(sec):
    return sorted({z for s in sec for z in (s[2], s[3])})


def front_at(sec, z0, z1):
    """Largest projection in front of the facade over the band [z0, z1]."""
    return max([s[1] for s in sec if s[1] > 0.0 and s[2] < z1 and s[3] > z0] + [0.0])


def acute_clip(boxes, sec):
    """The acute end pier: every box keeps its front part, and its part behind
    the facade is cut to max(front depth of that height band, 1 cm). Boxes are
    split at the section's z breaks so each piece sees one band."""
    zs = z_breaks(sec)
    out = []
    for x0, x1, y0, y1, z0, z1, slot in boxes:
        if x0 >= 0.0:
            out.append((x0, x1, y0, y1, z0, z1, slot))
            continue
        cuts = [z for z in zs if z0 < z < z1]
        for a, b in zip([z0] + cuts, cuts + [z1]):
            depth = max(front_at(sec, a, b), ACUTE_MIN_BODY_M)
            nx0 = max(x0, -depth)
            if x1 - nx0 > 1e-6:
                out.append((nx0, x1, y0, y1, a, b, slot))
    return out


def fan_rings(sec, kind):
    """Annular rings to revolve for a fan: (r0, r1, z0, z1, slot). 'front'
    takes the part of each section box in front of the facade (x > 0);
    'back' takes the part behind it, with r measured from the facade."""
    rings = []
    for x0, x1, z0, z1, slot in sec:
        if kind == "front" and x1 > 0.0:
            rings.append((max(x0, 0.0), x1, z0, z1, slot))
        elif kind == "back" and x0 < 0.0:
            rings.append((max(-x1, 0.0), -x0, z0, z1, slot))
    return rings


def ring_sector_xy(r0, r1, kind, half_deg=FAN_HALF_DEG):
    """Plan-view outline (counter-clockwise, UE frame) of one ring revolved
    over +-half_deg about local +X. A front ring sits at +X, a back ring at -X
    (the mesh's local +X stays the slice's exterior direction). r0 == 0 gives
    a triangle with its apex on the vertex."""
    h = math.radians(half_deg)
    sgn = 1.0 if kind == "front" else -1.0

    def p(r, a):
        return (sgn * r * math.cos(a), sgn * r * math.sin(a))
    pts = [p(r1, -h), p(r1, h)]
    pts += [p(r0, h), p(r0, -h)] if r0 > 1e-9 else [(0.0, 0.0)]
    # the back ring is the front ring turned 180 deg, which keeps the winding
    return pts
```

- [ ] **Step 4: Run, expect `5 passed`** (prototyped 2026-10-12).

Run: `./mcp_server/.venv/Scripts/python.exe -m pytest Tools/tl_kit/test_kit_geometry.py -q`

- [ ] **Step 5: Commit**

```bash
git add Tools/tl_kit/kit_geometry.py Tools/tl_kit/test_kit_geometry.py
git commit -m "Add the geometry for end piers and corner fans" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Kit spec, symbols and Blender builders

**Files:** Modify `Tools/tl_kit/tl_kit_spec.json`, `Tools/tl_kit/kit_common.py`, `Tools/tl_kit/test_kit_spec.py`, `Tools/tl_kit/build_tl_kit.py`, `Content/Python/tl_make_rules.py`, `Content/Python/tl_kit_rebuild_meshes.py`

**Interfaces — Consumes:** `kit_geometry.*` (Task 3). **Produces:** 18 parts named `SM_BLDG_TL_L%02d_A_<Part>_N1` with parts `EndPier_01`, `EndPierAcute_01` (levels 1–4), `FanFront_01`, `FanBack_01` (levels 0–4); kinds `end_pier`, `end_pier_acute`, `fan_front`, `fan_back`; symbols `EL`, `EAL`, `FF`, `FB` in `PART_TO_SYMBOL`.

- [ ] **Step 1: Add the failing tests to `Tools/tl_kit/test_kit_spec.py`**

Replace the `KNOWN_KINDS` set and append the tests:

```python
KNOWN_KINDS = {
    "foundation", "foundation_corner",
    "shopfront", "filler", "entrance", "pilaster", "pilaster_thin",
    "window", "window_top", "feature_window", "feature_window_top",
    "corner_ex", "corner_in", "corner_half",
    "cornice", "cornice_pier", "cornice_corner_ex", "cornice_corner_in", "cornice_half",
    "end_pier", "end_pier_acute", "fan_front", "fan_back",
}
```

```python
def test_spline_building_parts():
    spec = load()
    for lv in (1, 2, 3, 4):
        p = parts_at(spec, lv)
        assert p["EndPier_01"]["kind"] == "end_pier"
        assert p["EndPierAcute_01"]["kind"] == "end_pier_acute"
        assert p["EndPier_01"]["width_m"] * 100 == kit_common.END_PIER_CM
        assert p["EndPierAcute_01"]["width_m"] * 100 == kit_common.END_PIER_CM
    for lv in (0, 1, 2, 3, 4):
        p = parts_at(spec, lv)
        assert p["FanFront_01"]["kind"] == "fan_front"
        assert p["FanBack_01"]["kind"] == "fan_back"
    assert "EndPier_01" not in parts_at(spec, 0)


def test_spline_symbols_never_reach_the_rules():
    # RULE_TL_* (the SGD route) must not change: the new symbols are skipped there.
    assert {"EL", "EAL", "FF", "FB"} <= kit_common.NON_RULE_SYMBOLS
    for s in kit_common.NON_RULE_SYMBOLS:
        for lv in range(5):
            for g in kit_common.level_grammars(lv):
                assert "[%s]" % s not in g
```

Leave `test_no_duplicate_symbols_within_a_level` as it is (the new symbols are unique per level).

- [ ] **Step 2: Run, expect failures** (`KeyError: 'EndPier_01'`, missing `NON_RULE_SYMBOLS`, part count 43 ≠ 61).

Run: `./mcp_server/.venv/Scripts/python.exe -m pytest Tools/tl_kit/test_kit_spec.py -q`

- [ ] **Step 3: `kit_common.py`** — set `EXPECTED_PART_COUNT = 61` (update the comment: "+18 spline-building parts: per storey L1-L4 EndPier_01, EndPierAcute_01, FanFront_01, FanBack_01; L0 the two fans") and extend:

```python
PART_TO_SYMBOL.update({
    "EndPier_01": "EL", "EndPierAcute_01": "EAL",     # ER / EAR share these meshes
    "FanFront_01": "FF", "FanBack_01": "FB",
})
# Symbols of the spline building only. tl_make_rules.py skips them, so the
# RULE_TL_* assets (SGD route) stay exactly as before.
NON_RULE_SYMBOLS = {"EL", "ER", "EAL", "EAR", "FF", "FB"}
```

- [ ] **Step 4: `tl_kit_spec.json`** — append to `"parts"` (one object per line shown; `height_m` copies the level's height, `mesh_name` follows the convention):

```python
# Run once from the repo root to append the 18 parts (keeps the file's formatting style):
import json
p = "Tools/tl_kit/tl_kit_spec.json"
spec = json.load(open(p, encoding="utf-8"))
h = {int(k): v["height_m"] for k, v in spec["levels"].items()}
new = []
for lv in (1, 2, 3, 4):
    new += [("EndPier_01", "end_pier", 1.5, lv), ("EndPierAcute_01", "end_pier_acute", 1.5, lv)]
for lv in (0, 1, 2, 3, 4):
    new += [("FanFront_01", "fan_front", 0.0, lv), ("FanBack_01", "fan_back", 0.0, lv)]
for part, kind, w, lv in new:
    spec["parts"].append({"level": lv, "part": part, "kind": kind, "width_m": w,
                          "height_m": h[lv], "mesh_name": "SM_BLDG_TL_L%02d_A_%s_N1" % (lv, part)})
json.dump(spec, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
```
Fans have `width_m` 0.0 (they have no run). Check `test_heights_follow_the_level_table` still passes (L0 height 2.5 for the L0 fans).

- [ ] **Step 5: `build_tl_kit.py`** — add the collector, the prism primitive and the four builders. Insert after `class Builder` (inside the class add `prism`):

```python
    def prism(self, pts_xy, z0, z1, slot):
        """A vertical prism over a counter-clockwise plan outline (UE frame)."""
        if z1 - z0 < 1e-4 or len(pts_xy) < 3:
            return
        bot = [self.bm.verts.new(self.xf(x, y, z0)) for x, y in pts_xy]
        top = [self.bm.verts.new(self.xf(x, y, z1)) for x, y in pts_xy]
        faces = [self._face(list(reversed(bot)), slot), self._face(top, slot)]
        n = len(pts_xy)
        for i in range(n):
            j = (i + 1) % n
            faces.append(self._face([bot[i], bot[j], top[j], top[i]], slot))
        bmesh.ops.recalc_face_normals(self.bm, faces=faces)


class CollectBuilder(Builder):
    """Records boxes instead of meshing them, so a facade builder's output can
    be cut (acute pier) or revolved (fan) by kit_geometry. Panes are dropped:
    end piers and fans carry no glass."""

    def __init__(self):
        super().__init__()
        self.boxes = []

    def box(self, x0, x1, y0, y1, z0, z1, slot):
        if x1 - x0 < 1e-4 or y1 - y0 < 1e-4 or z1 - z0 < 1e-4:
            return
        self.boxes.append((x0, x1, y0, y1, z0, z1, slot))

    def pane(self, *a, **k):
        return
```

Add near the corner builders (needs `import kit_geometry` next to `import kit_common`):

```python
# ---------------------------------------------------------------- spline building
# docs/superpowers/specs/2026-10-09-tl-spline-building-design.md section 5.
# The pier is a 1.5 m stretch of the storey's filler profile with flat ends;
# the fans revolve that profile +-5 deg about the vertical axis through the
# vertex (the mesh origin), so slices placed side by side close any turn.

def _filler_boxes(level, w, h):
    c = CollectBuilder()
    build_filler(c, w, h, level)
    return c.boxes


def build_end_pier(b, w, h, level, acute):
    boxes = _filler_boxes(level, w, h)
    if acute:
        boxes = kit_geometry.acute_clip(boxes, kit_geometry.section(boxes, w / 2.0))
    for x0, x1, y0, y1, z0, z1, slot in boxes:
        b.box(x0, x1, y0, y1, z0, z1, slot)


def build_fan(b, h, level, kind):
    sec = kit_geometry.section(_filler_boxes(level, 1.0, h), 0.5)
    for r0, r1, z0, z1, slot in kit_geometry.fan_rings(sec, kind):
        b.prism(kit_geometry.ring_sector_xy(r0, r1, kind), z0, z1, slot)
```

Note: `build_filler(level=0)` is centred on y = 0 (`build_foundation`), so for L0 call `kit_geometry.section(boxes, 0.0)` — handle it in `build_fan`: `y_probe = 0.0 if level == 0 else 0.5`. Register in `BUILDERS`:

```python
    "end_pier": lambda b, p: build_end_pier(b, p["width_m"], p["height_m"], p["level"], False),
    "end_pier_acute": lambda b, p: build_end_pier(b, p["width_m"], p["height_m"], p["level"], True),
    "fan_front": lambda b, p: build_fan(b, p["height_m"], p["level"], "front"),
    "fan_back": lambda b, p: build_fan(b, p["height_m"], p["level"], "back"),
```

In `main()`'s layout loop, fans have `width_m` 0: use `x += max(part["width_m"], 0.5) + 1.0`.

- [ ] **Step 6: `tl_make_rules.py`** — in the per-level part loop (line ~246, `for p in parts:`), skip spline symbols before mapping:

```python
        if PART_TO_SYMBOL.get(p["part"]) in kit_common.NON_RULE_SYMBOLS:
            continue    # spline-building pieces are BDF-only; RULE_TL_* stay as they were
```
Apply the same skip in the second loop at line ~272.

- [ ] **Step 7: `tl_kit_rebuild_meshes.py`** — kinds without a [0, w] run: add `"fan_front", "fan_back"` to `CORNER_KINDS` (skips the run check) and to `BELOW_GRADE_KINDS` only for level 0 — replace the z check with:

```python
        below = p["kind"] in BELOW_GRADE_KINDS or (p["kind"].startswith("fan_") and p["level"] == 0)
        if below:
```

- [ ] **Step 8: Run all kit tests, expect pass**

Run: `./mcp_server/.venv/Scripts/python.exe -m pytest Tools/tl_kit -q`
Expected: all pass (15 + 2 spec, 13 corner, 5 geometry).

- [ ] **Step 9: Build in Blender and check every new part**

```bash
"E:/Blender/blender-5.2.1-windows-x64/blender.exe" -b --factory-startup -P Tools/tl_kit/build_tl_kit.py -- --spec Tools/tl_kit/tl_kit_spec.json --out E:/Blender/TL_Kit 2>&1 | grep -E "###EXPORTED###|###REPORT###|Error" | head -5
```
Expected: `###EXPORTED### 61`. From `###REPORT###` check, for each new part: `glass_faces` 0; end piers `ue_bounds_m` y ∈ [0, 1.5]; fans have every vertex within ±5° of local +X (front, x ≥ 0) or −X (back, x ≤ 0), and the max radius equals the storey's deepest projection (L4 front 0.34, L1 front 0.16, back 0.30, L0 back 0.45).

- [ ] **Step 10: Commit**

```bash
git add Tools/tl_kit Content/Python/tl_make_rules.py Content/Python/tl_kit_rebuild_meshes.py
git commit -m "Add the end piers and corner fans to the TL kit" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Import the 18 meshes into UE

**Files:** none new (uses `tl_kit_rebuild_meshes.py`).

- [ ] **Step 1: Import only the new parts**

`run_unreal_script("tl_kit_rebuild_meshes.py", {"only": [<the 18 mesh names>]})`
Expected: `"ok": true`, `n` 18, `meshes_on_disk` 61, every record `"created": true`, no `error`.
If `created` meshes fail (`duplicate_loaded_asset` returned None), stop and report: the first-import path is untested (spec risk 6).

- [ ] **Step 2: Confirm the existing 43 meshes were not touched**

`git status --short Content/Building/TL` must list only new `.uasset` files (no `M`).

- [ ] **Step 3: Commit the new meshes**

```bash
git add Content/Building/TL
git commit -m "Import the TL end piers and corner fans" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: BDF rows for the new symbols

**Files:** Modify `Content/Python/tl_make_bdf.py`

**Interfaces — Produces:** in `BDF_WithTL` Modules, for L1–L4 the rows `EL`, `ER` (mesh `EndPier_01`), `EAL`, `EAR` (mesh `EndPierAcute_01`), `Size` 150, not scalable, `HasProps` False, `PivotOffset (0, -75, -h/2)`; for L0–L4 `FF`/`FB` with `Size` 1, `PivotOffset (0, 0, 0)`.

- [ ] **Step 1: In `tl_modules()`** (line ~384), the generic row already covers `EL`, `EAL`, `FF`, `FB` through `PART_TO_SYMBOL`. Fans need a zero pivot and a 1 cm size; add after the row is appended and before the WS1 block:

```python
        if sym in ("FF", "FB"):
            rows[-1] = dict(rows[-1], Size=1.0, PivotOffset=unreal.Vector(0.0, 0.0, 0.0))
        if sym in ("EL", "EAL"):
            # ER / EAR share the flat-ended pier mesh (ruling R2)
            rows.append(dict(rows[-1], Symbol={"EL": "ER", "EAL": "EAR"}[sym], PtID=ptid))
            ptid += 1
```

- [ ] **Step 2: Run** `run_unreal_script("tl_make_bdf.py")`.
Expected: `errors` empty, `patched` true, `replaced_tl_module_rows` = 48 + 4·4 + 5·2 = **74**, Modules total 2,990, `epic_source_untouched` true.

- [ ] **Step 3: Regression on the showcase** (separate calls): `tl_new_showcase_level.py` (loads it) → `tl_showcase_setup.py` → next call `tl_showcase_read.py`.
Expected: `cats` L00 120, L01 80, L02 1054, L03 154, L04 154 (1,562 total). Do **not** save the level.

- [ ] **Step 4: Commit**

```bash
git add Content/Python/tl_make_bdf.py Content/PCG/DataAssets/BDF/BDF_WithTL.uasset
git commit -m "Register the spline building symbols in BDF_WithTL" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Graph kit and graph segments A–C (data, storeys, edge grammars)

**Files:** Create `Content/Python/tl_graph_kit.py`, `Content/Python/tl_make_spline_graph.py`, `Content/Python/tl_probe_spline_graph.py`

**Interfaces — Produces:**
- `tl_graph_kit.GraphKit(graph)` with `node`, `sub`, `loop`, `copy`, `const`, `edge`, `maths`, `pins`.
- In `tl_make_spline_graph.py`: `build_segments_abc(K) -> dict` returning the ports `{"levels", "modules", "props", "bdf", "footprint", "segs", "walls_in"}` (a port is `(node, pin_label)`).

- [ ] **Step 1: Write `Content/Python/tl_graph_kit.py`**

```python
# tl_graph_kit.py -- helpers for authoring a PCG graph from Python.
# Every edge is verified (traps.md 14: add_edge fails silently and returns a
# truthy node). Selectors are written as "PCGBegin(<text>)PCGEnd" through the
# struct's import_text (Task 1 spike). Nodes that exist in Epic's
# BDF_BuildingFromSpline are copied with add_node_copy, which carries the
# private inline pin defaults Python cannot set.
import unreal

EPIC_BLDG = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/BDF_BuildingFromSpline"
STRING3_PINS = ("InA", "InB", "InC")      # Task 1, q5_inputs


def cls(name):
    c = unreal.load_class(None, "/Script/PCG." + name)
    if c is None:
        raise RuntimeError("no PCG class " + name)
    return c


class Sel(str):
    """An attribute/property selector value, e.g. Sel("$BoundsMax.X")."""


class Txt(str):
    """A struct value written with import_text, e.g. Txt('(Type=Double,DoubleValue=2)')."""


def pin_labels(node, which):
    return [str(p.get_editor_property("properties").get_editor_property("label"))
            for p in node.get_editor_property(which)]


class GraphKit:
    def __init__(self, graph):
        self.g = graph
        self._copied = {}

    # ---- properties
    def _set_selector(self, st, prop, text):
        s = st.get_editor_property(prop)
        s.import_text("PCGBegin(%s)PCGEnd" % text)
        st.set_editor_property(prop, s)
        got = st.get_editor_property(prop).export_text()
        if text not in got:
            raise RuntimeError("selector %s on %s did not take %r (got %s)"
                               % (prop, st.get_class().get_name(), text, got))

    def set(self, st, prop, value):
        if isinstance(value, Sel):
            self._set_selector(st, prop, str(value))
        elif isinstance(value, Txt):
            v = st.get_editor_property(prop)
            v.import_text(str(value))
            st.set_editor_property(prop, v)
        elif isinstance(value, list) and value and isinstance(value[0], Sel):
            arr = []
            for text in value:
                s = unreal.PCGAttributePropertyInputSelector()
                s.import_text("PCGBegin(%s)PCGEnd" % text)
                arr.append(s)
            st.set_editor_property(prop, arr)
        else:
            st.set_editor_property(prop, value)

    # ---- nodes
    def node(self, cls_name, **props):
        n, st = self.g.add_node_of_type(cls(cls_name))
        for k, v in props.items():
            self.set(st, k, v)
        return n

    def sub(self, graph_path, loop=False, **params):
        n, st = self.g.add_node_of_type(cls("PCGLoopSettings" if loop else "PCGSubgraphSettings"))
        st.set_subgraph(unreal.EditorAssetLibrary.load_asset(graph_path))
        inst = st.get_editor_property("subgraph_instance")
        H = unreal.PCGGraphParametersHelpers
        for k, v in params.items():
            if isinstance(v, bool):
                H.set_bool_parameter(inst, k, v)
            elif isinstance(v, float):
                H.set_double_parameter(inst, k, v)
            else:
                H.set_string_parameter(inst, k, v)
        return n

    def loop(self, graph_path, **params):
        return self.sub(graph_path, loop=True, **params)

    def copy(self, node_name, graph_path=EPIC_BLDG, **props):
        """Copy one node's settings out of another graph (that graph is only read)."""
        src = unreal.EditorAssetLibrary.load_asset(graph_path)
        for n in src.get_editor_property("nodes"):
            if n.get_name() == node_name:
                new, st = self.g.add_node_copy(n.get_settings())
                for k, v in props.items():
                    self.set(st, k, v)
                return new
        raise RuntimeError("%s has no node %s" % (graph_path, node_name))

    def const(self, typ, value, name):
        """A one-entry attribute set. typ: Double, Integer32, Boolean, String, Vector."""
        val = {"Double": "DoubleValue=%r" % float(value) if not isinstance(value, str) else "DoubleValue=" + value,
               "Integer32": "Int32Value=%d" % int(value) if not isinstance(value, str) else "",
               "Boolean": "BoolValue=%s" % ("True" if value else "False"),
               "String": 'StringValue="%s"' % value,
               "Vector": "VectorValue=%s" % value}[typ]
        return (self.node("PCGCreateAttributeSetSettings",
                          attribute_types=Txt("(Type=%s,%s)" % (typ, val)),
                          output_target=Sel(name)), "Out")

    # ---- edges
    def edge(self, src, dst, dst_pin):
        """src is a (node, out_pin) port."""
        before = len(self.g.get_all_edges())
        self.g.add_edge(src[0], src[1], dst, dst_pin)
        if len(self.g.get_all_edges()) <= before:
            raise RuntimeError("edge %s.%s -> %s.%s not created; out pins %s, in pins %s"
                               % (src[0].get_name(), src[1], dst.get_name(), dst_pin,
                                  pin_labels(src[0], "output_pins"), pin_labels(dst, "input_pins")))

    # ---- shorthands
    def maths(self, src, op, a, b, out):
        """out = a <op> b on src's data. a is an attribute selector; b is a number
        (wired as a constant) or a Sel (same data)."""
        kw = dict(operation=getattr(unreal.PCGMetadataMathsOperation, op),
                  input_source1=Sel(a), output_target=Sel(out))
        if isinstance(b, Sel):
            kw["input_source2"] = b
            n = self.node("PCGMetadataMathsSettings", **kw)
            self.edge(src, n, "InA")
            self.edge(src, n, "InB")
        elif b is None:
            n = self.node("PCGMetadataMathsSettings", **kw)
            self.edge(src, n, "In")
        else:
            n = self.node("PCGMetadataMathsSettings", **kw)
            self.edge(src, n, "InA")
            self.edge(self.const("Double", b, "C"), n, "InB")
        return (n, "Out")

    def filt(self, src, attr, op, value=None, against=None):
        """Point filter: attr <op> constant value, or attr <op> another attribute."""
        kw = dict(target_attribute=Sel(attr),
                  operator=getattr(unreal.PCGAttributeFilterOperator, op))
        if against is not None:
            kw.update(use_constant_threshold=False, threshold_attribute=Sel(against))
        else:
            kind, txt = value
            kw.update(use_constant_threshold=True, attribute_types=Txt("(Type=%s,%s)" % (kind, txt)))
        n = self.node("PCGAttributeFilteringSettings", **kw)
        self.edge(src, n, "In")
        return (n, "InsideFilter"), (n, "OutsideFilter")

    def merge(self, *ports):
        n = self.node("PCGMergeSettings")
        for p in ports:
            self.edge(p, n, "In")
        return (n, "Out")
```

- [ ] **Step 2: Write `Content/Python/tl_make_spline_graph.py` (segments A–C, plus `main`)**

```python
# tl_make_spline_graph.py -- build /Game/PCG/TL/PCG_TL_SplineBuilding.
# docs/superpowers/specs/2026-10-09-tl-spline-building-design.md section 6 and
# docs/superpowers/plans/2026-10-12-tl-spline-building.md Tasks 7-10.
# Args: {"segments": "abc" | "abcd" | "abcde" | "all"} -- build up to that segment
# (each task extends the graph and verifies before the next).
import importlib
import json
import sys

sys.path.insert(0, unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python"))
import tl_graph_kit
importlib.reload(tl_graph_kit)
from tl_graph_kit import GraphKit, Sel, Txt

args = mcp_args or {}
DEST = "/Game/PCG/TL/PCG_TL_SplineBuilding"
TEMPLATE = "/CitySamplePCG/PCG/DataAssets/Buildings/PCG_Bldg_SGD_test"   # owns the Height parameter (R4)
SUB = "/CitySamplePCG/PCG/Primitives/Buildings/Subgraphs/"
PIER_FILLER_CM = 625.0     # 150 + 325 + 150 (ruling R1)
FOUND_FILLER_CM = 200.0


def fresh_graph():
    EAL = unreal.EditorAssetLibrary
    if EAL.does_asset_exist(DEST):
        if not EAL.delete_asset(DEST) or EAL.does_asset_exist(DEST):
            raise RuntimeError("could not delete the previous %s (traps.md 17)" % DEST)
    g = EAL.duplicate_asset(TEMPLATE, DEST)
    if g is None:
        raise RuntimeError("duplicate_asset returned None")
    keep = None
    doomed = []
    for n in g.get_editor_property("nodes"):
        st = n.get_settings()
        if st.get_class().get_name() == "PCGGenericUserParameterGetSettings" and \
                str(st.get_editor_property("property_path")) == "Height":
            keep = n
        else:
            doomed.append(n)
    g.remove_nodes(doomed)
    if keep is None:
        raise RuntimeError("template has no Height getter")
    return g, keep


def tl_group(K, load, tag, token_type):
    f = K.node("PCGFilterByTagSettings", operation=unreal.PCGFilterByTagOperation.KEEP_TAGGED,
               selected_tags=tag)
    K.edge(load, f, "In")
    inside, _ = K.filt((f, "InsideFilter"), "BuildingToken", "EQUAL",
                       value=(token_type, '%sValue="TL"' % token_type))
    return inside


def build_segments_abc(K, height_node):
    P = {}
    # ---- A. data
    load = (K.sub(SUB + "LoadCitySampleData"), "Out")
    P["levels"] = tl_group(K, load, "Levels", "Name")       # Levels.BuildingToken is a Name
    P["modules"] = tl_group(K, load, "Modules", "String")
    P["props"] = tl_group(K, load, "Props", "String")
    P["bdf"] = tl_group(K, load, "BDF", "String")

    # ---- B. footprint and storeys
    spl = K.node("PCGGetSplineSettings")                    # actor selector defaults to Self
    clean = K.node("PCGCleanSplineSettings", fuse_colocated_control_points=True,
                   remove_collinear_control_points=True, collinear_angle_threshold=1.0)
    cw = K.node("PCGReverseSplineSettings", operation=unreal.PCGReverseSplineOperation.FORCE_CLOCKWISE)
    K.edge((spl, "Out"), clean, "In")
    K.edge((clean, "Out"), cw, "In")
    P["footprint"] = (cw, "Out")
    hvec = K.node("PCGMetadataMathsSettings", operation=unreal.PCGMetadataMathsOperation.MULTIPLY,
                  input_source1=Sel("@Last"), output_target=Sel("ExtrudeVector"))
    K.edge((height_node, "Out"), hvec, "InA")
    K.edge(K.const("Vector", "(X=0.0,Y=0.0,Z=1.0)", "Up"), hvec, "InB")
    addext = K.node("PCGAddAttributeSettings", input_source=Sel("ExtrudeVector"),
                    output_target=Sel("@Data.ExtrudeVector"))
    K.edge(P["footprint"], addext, "In")
    K.edge((hvec, "Out"), addext, "Attributes")
    vg = K.node("PCGCopyAttributesSettings", input_source=Sel("VerticalGrammar"),
                output_target=Sel("@Data.VerticalGrammar"))
    K.edge((addext, "Out"), vg, "Target")
    K.edge(P["bdf"], vg, "Source")
    # Levels as module info: Epic adds Scalable=False and casts Size to Double first
    scal = K.copy("AddAttribute_6")
    K.edge(P["levels"], scal, "In")
    cast = K.copy("AttributeCast_3")
    K.edge((scal, "Out"), cast, "In")
    lvl_info = K.node("PCGConvertToAttributeSetSettings")
    K.edge((cast, "Out"), lvl_info, "In")
    dcs = K.copy("DuplicateCrossSections_1", extrude_vector_attribute=Sel("@Data.ExtrudeVector"))
    K.edge((vg, "Out"), dcs, "In")
    K.edge((lvl_info, "Out"), dcs, "ModulesInfo")

    # ---- C. segments and their grammars
    seg = K.copy("SplineToSegment_0")
    K.edge((dcs, "Out"), seg, "In")
    hz = K.copy("AttributeMathsOp_0")                        # $BoundsMax.Z = Size.Z
    K.edge((seg, "Out"), hz, "InA")
    K.edge((seg, "Out"), hz, "InB")
    mas = K.copy("MatchAndSetAttributes_0")                  # FloorSymbol -> Levels row
    K.edge((hz, "Out"), mas, "In")
    K.edge((lvl_info, "Out"), mas, "Match Data")
    seglen = K.maths((mas, "Out"), "MULTIPLY", "$BoundsMax.X", 2.0, "SegLen")
    sscale = K.node("PCGAddAttributeSettings", output_target=Sel("ShortScale"),
                    attribute_types=Txt("(Type=Double,DoubleValue=1.000000)"))
    K.edge(seglen, sscale, "In")
    P["segs"] = (sscale, "Out")

    found, storeys = K.filt(P["segs"], "LevelNumber", "EQUAL", value=("Integer32", "Int32Value=0"))

    def short_branch(src, filler_symbol, filler_cm):
        g = K.node("PCGAddAttributeSettings", output_target=Sel("FloorGrammar"),
                   attribute_types=Txt('(Type=String,StringValue="[%s]")' % filler_symbol))
        K.edge(src, g, "In")
        s = K.maths((g, "Out"), "DIVIDE", "SegLen", filler_cm, "ShortScale")
        return K.maths(s, "POW", "ShortScale", -1.0, "$Scale.X")   # subdivision then sees filler_cm

    def const_grammar(src, text):
        g = K.node("PCGAddAttributeSettings", output_target=Sel("FloorGrammar"),
                   attribute_types=Txt('(Type=String,StringValue="%s")' % text))
        K.edge(src, g, "In")
        return (g, "Out")

    # storeys >= 1
    s_short, s_long = K.filt(storeys, "SegLen", "LESSER", value=("Double", "DoubleValue=%f" % PIER_FILLER_CM))
    in2, out2 = K.filt(s_long, "SegLen", "GREATER_OR_EQUAL", against="FLengths.Z")
    in1, out1 = K.filt(out2, "SegLen", "GREATER_OR_EQUAL", against="FLengths.Y")
    in0, mid = K.filt(out1, "SegLen", "GREATER_OR_EQUAL", against="FLengths.X")
    picked = []
    for src, f in ((in2, "F2"), (in1, "F1"), (in0, "F0")):
        r = K.node("PCGMetadataRenameSettings", attribute_to_rename=Sel(f), new_attribute_name="FloorGrammar")
        K.edge(src, r, "In")
        picked.append((r, "Out"))
    picked.append(const_grammar(mid, "[FC][WS1][LC]"))
    long_merged = K.merge(*picked)
    drop = K.node("PCGDeleteAttributesSettings",
                  operation=unreal.PCGAttributeFilterOperation.DELETE_SELECTED_ATTRIBUTES,
                  selected_attributes="F0,F1,F2")
    K.edge(long_merged, drop, "In")

    def replace(src, token, acute_attr, acute_tok, plain_tok):
        a_in, a_out = K.filt(src, acute_attr, "GREATER", value=("Double", "DoubleValue=90.000000"))
        outs = []
        for port, rep in ((a_in, acute_tok), (a_out, plain_tok)):
            n = K.node("PCGMetadataStringOpSettings",
                       operation=unreal.PCGMetadataStringOperation.REPLACE,
                       input_source1=Sel("FloorGrammar"), input_source2=Sel("@Last"),
                       input_source3=Sel("@Last"), output_target=Sel("FloorGrammar"))
            K.edge(port, n, tl_graph_kit.STRING3_PINS[0])
            K.edge(K.const("String", token, "Find"), n, tl_graph_kit.STRING3_PINS[1])
            K.edge(K.const("String", rep, "With"), n, tl_graph_kit.STRING3_PINS[2])
            outs.append((n, "Out"))
        return K.merge(*outs)

    starts = replace((drop, "Out"), "[FC", "PreviousAngle", "[EAL", "[EL")
    ends = replace(starts, "[LC", "NextAngle", "[EAR", "[ER")
    storey_short = short_branch(s_short, "WS1", 325.0)

    # foundation: no piers, grammar [FS2]+ (ruling R1 for short edges)
    f_short, f_long = K.filt(found, "SegLen", "LESSER", value=("Double", "DoubleValue=%f" % FOUND_FILLER_CM))
    found_long = const_grammar(f_long, "[FS2]+")
    found_short = short_branch(f_short, "FS2", FOUND_FILLER_CM)

    P["walls_in"] = K.merge(ends, storey_short, found_long, found_short)
    return P


def main():
    g, height_node = fresh_graph()
    K = GraphKit(g)
    P = build_segments_abc(K, height_node)
    seg = args.get("segments", "abc")
    if seg == "abc":
        # expose the edge stream for the probe; Task 8 replaces this
        K.edge(P["walls_in"], g.get_output_node(), "Out")
    ok = unreal.EditorAssetLibrary.save_asset(DEST, only_if_is_dirty=False)
    return {"saved": ok, "nodes": len(g.get_editor_property("nodes")),
            "edges": len(g.get_all_edges()), "segments": seg}


mcp_result = json.loads(json.dumps(main(), default=str))
```

Pin names used here that come from Epic's own edges and are therefore known: `LoadCitySampleData.Out`; `DuplicateCrossSections In/ModulesInfo`; `MatchAndSet In/Match Data`; `Maths InA/InB`; `AddAttribute In/Attributes`; `CopyAttributes Source/Target`; filters `In/InsideFilter/OutsideFilter`; `Merge In`. `GetSpline.Out`, `CleanSpline In/Out`, `ReverseSpline In/Out`, `ConvertToAttributeSet In/Out`, `Rename In/Out`, `DeleteAttributes In/Out`, `CreateAttributeSet Out` follow the same convention; `GraphKit.edge` prints the real labels if any differ — fix the label and rerun.

- [ ] **Step 3: Write the probe `Content/Python/tl_probe_spline_graph.py`**

It places a temporary host for an unsaved run (the real host comes in Task 11). A spline needs an actor with a SplineComponent; this probe uses the BP from Task 11 if it exists, otherwise stops.

```python
# tl_probe_spline_graph.py -- READ-ONLY on assets. Generate (phase "gen") or read
# (phase "read") PCG_TL_SplineBuilding on the actor labelled TLPROBE_Spline in
# the current level, and compare the edge stream (segments abc) against
# Tools/tl_kit/corner_math.py. Args: {"phase": "gen" | "read"}
import json
import sys

sys.path.insert(0, "E:/PCG_Claude/Tools/tl_kit")
import importlib
import corner_math
importlib.reload(corner_math)

args = mcp_args or {}
LABEL = "TLPROBE_Spline"


def actor():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    return next((a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL), None)


def footprint(a):
    sc = a.get_component_by_class(unreal.SplineComponent)
    return [tuple(sc.get_location_at_spline_point(i, unreal.SplineCoordinateSpace.WORLD).to_tuple()[:2])
            for i in range(sc.get_number_of_spline_points())]


def main():
    a = actor()
    if a is None:
        return {"error": "no %s actor; run tl_spline_level.py first" % LABEL}
    comp = a.get_component_by_class(unreal.PCGComponent)
    if args.get("phase") == "gen":
        comp.set_graph(unreal.EditorAssetLibrary.load_asset("/Game/PCG/TL/PCG_TL_SplineBuilding"))
        unreal.SystemLibrary.execute_console_command(None, "pcg.FlushCache")
        comp.activate(True)
        comp.cleanup_local(True)
        comp.generate_local(True)
        return {"fired": True}
    coll = comp.get_generated_graph_output()
    rows = []
    MA = unreal.PCGMetadataAccessorHelpers
    for td in coll.get_editor_property("tagged_data"):
        d = td.get_editor_property("data")
        if not isinstance(d, unreal.PCGBasePointData):
            continue
        md = d.get_const_metadata() if hasattr(d, "get_const_metadata") else d.mutable_metadata()
        for pt in d.get_points():
            rows.append({"lv": MA.get_integer32_attribute(pt, md, "LevelNumber"),
                         "len": round(MA.get_double_attribute(pt, md, "SegLen"), 2),
                         "g": MA.get_string_attribute(pt, md, "FloorGrammar"),
                         "scale": round(MA.get_double_attribute(pt, md, "ShortScale"), 4),
                         "prev": round(MA.get_double_attribute(pt, md, "PreviousAngle"), 3)})
    pts = corner_math.clean(footprint(a))
    want = sorted((lv, round(corner_math.edge_plan(pts, i, lv)["length"], 2),
                   corner_math.edge_plan(pts, i, lv)["grammar"] or "[%s]" % corner_math.edge_plan(pts, i, lv)["symbol"])
                  for lv in sorted({r["lv"] for r in rows}) for i in range(len(pts)))
    got = sorted((r["lv"], r["len"], r["g"]) for r in rows)
    bad = [w for w in want if w not in got]
    return {"n_rows": len(rows), "n_want": len(want), "mismatches": bad[:20], "sample": rows[:6]}


mcp_result = json.loads(json.dumps(main(), default=str))
```

- [ ] **Step 4: Build segments A–C**: `run_unreal_script("tl_make_spline_graph.py", {"segments": "abc"})`.
Expected: `saved: true`, no exception. If `GraphKit.edge` raises, correct the pin label from the printed list and rerun.

- [ ] **Step 5: Verify against the model** — this needs the host from Task 11 Step 1 (`tl_spline_level.py` with `{"probe_only": true}` places one `TLPROBE_Spline` L-shape). Run `tl_probe_spline_graph.py {"phase":"gen"}`, then in the next call `{"phase":"read"}`.
Expected: `n_rows == n_want` and `mismatches == []`. If the grammars differ only in `[EL]`/`[EAL]` swaps, the angle sign convention is the other way round: record it in traps.md, invert the comparisons (`LESSER` against −90) and rerun.

- [ ] **Step 6: Commit**

```bash
git add Content/Python/tl_graph_kit.py Content/Python/tl_make_spline_graph.py Content/Python/tl_probe_spline_graph.py
git commit -m "Build the spline building graph up to the per-edge grammars" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Segment D — walls (subdivide, place, spawn)

**Files:** Modify `Content/Python/tl_make_spline_graph.py`

**Interfaces — Consumes:** `P["walls_in"]`, `P["modules"]`. **Produces:** `build_segment_d(K, P) -> port` (`P["walls"]`, placed module points with a `Mesh` attribute) and `build_spawner(K, *ports)`.

- [ ] **Step 1: Add**

```python
def build_segment_d(K, P):
    part = K.node("PCGMetadataPartitionSettings", partition_attribute_selectors=[Sel("LevelNumber")])
    K.edge(P["walls_in"], part, "In")
    minfo = K.node("PCGConvertToAttributeSetSettings")
    K.edge(P["modules"], minfo, "In")
    loop = K.copy("Loop_0")                               # Loop_Subdivide, as Epic wires it
    K.edge((part, "Out"), loop, "In")
    K.edge((minfo, "Out"), loop, "NewPin")
    # placement: copied from BDF_BuildingFromSpline (MeshForwardAxis == 2, TL's only value)
    fwd = K.node("PCGCopyAttributesSettings", input_source=Sel("$Rotation.Forward"),
                 output_target=Sel("ForwardDir"))
    K.edge((loop, "Out"), fwd, "Target")
    K.edge((loop, "Out"), fwd, "Source")
    swap = K.copy("AttributeMathsOp_17")                  # $Scale = $Scale.yxz
    K.edge((fwd, "Out"), swap, "InA")
    K.edge((fwd, "Out"), swap, "InB")
    rot = K.copy("MakeRotatorAttribute_3")                # MakeRotFromYZ(ForwardDir, $Rotation.Up)
    K.edge((swap, "Out"), rot, "Y")
    K.edge((swap, "Out"), rot, "Z")
    short = K.maths((rot, "Out"), "MULTIPLY", "$Scale.Y", Sel("ShortScale"), "$Scale.Y")
    piv = K.copy("AttributeMathsOp_22")                   # PivotOffset *= $Scale
    K.edge(short, piv, "InA")
    K.edge(short, piv, "InB")
    tdir = K.copy("AttributeVectorOp_3")                  # PivotOffset into world
    K.edge((piv, "Out"), tdir, "In")
    K.edge((piv, "Out"), tdir, "Transform")
    add = K.copy("AttributeMathsOp_23")                   # $Position += PivotOffset
    K.edge((tdir, "Out"), add, "InA")
    K.edge((tdir, "Out"), add, "InB")
    P["walls"] = (add, "Out")
    return P["walls"]


def build_spawner(K, *ports):
    sp = K.copy("StaticMeshSpawner_3", synchronous_load=True)   # mesh by attribute "Mesh" (traps.md 4)
    K.edge(K.merge(*ports), sp, "In")
    return sp
```
and in `main()`: if `seg` in ("abcd", "abcde", "all") call `build_segment_d(K, P)`; for `"abcd"` call `build_spawner(K, P["walls"])`.

- [ ] **Step 2: Build and generate**: `tl_make_spline_graph.py {"segments":"abcd"}`, then `tl_probe_spline_graph.py {"phase":"gen"}`, then next call `tl_showcase_read.py`-style counting — use the Task 11 probe's `counts` phase if Task 11 is done; otherwise read ISM components on `TLPROBE_Spline` with this one-liner script body (save as `Content/Python/tl_probe_spline_counts.py`):

```python
# tl_probe_spline_counts.py -- READ-ONLY. Instances per mesh on TLPROBE_Spline.
import json
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
a = next(x for x in eas.get_all_level_actors() if x.get_actor_label() == "TLPROBE_Spline")
out = {}
for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
    sm = c.get_editor_property("static_mesh")
    if sm:
        out[sm.get_name()] = out.get(sm.get_name(), 0) + c.get_instance_count()
mcp_result = {"meshes": out, "total": sum(out.values())}
```
Expected for the probe L-shape: every storey has `EndPier_01` instances = 2 × (edges ≥ 625 cm); no `CornerEx`/`CornerIn` meshes; `Foundation_01` present; total > 0.

- [ ] **Step 3: Commit**

```bash
git add Content/Python/tl_make_spline_graph.py Content/Python/tl_probe_spline_counts.py
git commit -m "Place and spawn the spline building walls" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Segment E — corner fans

**Files:** Modify `Content/Python/tl_make_spline_graph.py`

**Interfaces — Consumes:** `P["segs"]` (one point per storey edge, with `PreviousAngle`, `SegLen`, `LevelNumber`, `$Rotation`, `$Position` at storey base), `P["modules"]`. **Produces:** `build_segment_e(K, P) -> port` (`P["fans"]`).

The fan at a vertex is built from the edge that **starts** there: its `PreviousAngle` is the turn at that vertex; the vertex is `$Position − Forward·SegLen/2`; with the footprint forced clockwise (positive shoelace) the incoming exterior normal is `yaw_out − turn − 90`, and the sweep equals the turn (`corner_math.fan` with `area_sign = +1`).

- [ ] **Step 1: Add**

(Add `import math` to the script's top-level imports.)

```python
def build_segment_e(K, P):
    s = K.maths(P["segs"], "ABS", "PreviousAngle", None, "AbsTurn")
    s, _ = K.filt(s, "AbsTurn", "GREATER_OR_EQUAL", value=("Double", "DoubleValue=1.000000"))
    s = K.maths(s, "MULTIPLY", "SegLen", 0.5, "HalfLen")
    s = K.maths(s, "MULTIPLY", "$Rotation.Forward", Sel("HalfLen"), "HalfVec")
    s = K.maths(s, "SUBTRACT", "$Position", Sel("HalfVec"), "VPos")
    s = K.maths(s, "DIVIDE", "AbsTurn", 10.0, "N")
    s = K.maths(s, "CEIL", "N", None, "N")
    s = K.maths(s, "DIVIDE", "AbsTurn", Sel("N"), "HalfA")
    s = K.maths(s, "MULTIPLY", "HalfA", 0.5, "HalfA")
    s = K.maths(s, "SUBTRACT", "$Rotation.Yaw", Sel("PreviousAngle"), "Yaw0")
    s = K.maths(s, "SUBTRACT", "Yaw0", 90.0, "Yaw0")
    for op, a, out in (("DEG_TO_RAD", "HalfA", "HalfRad"), ("COS", "HalfRad", "CosA"), ("SIN", "HalfRad", "SinA")):
        n = K.node("PCGMetadataTrigSettings", operation=getattr(unreal.PCGMetadataTrigOperation, op),
                   input_source1=Sel(a), output_target=Sel(out))
        K.edge(s, n, "In")
        s = (n, "Out")
    s = K.maths(s, "DIVIDE", "CosA", math.cos(math.radians(5.0)), "Sx")
    s = K.maths(s, "DIVIDE", "SinA", math.sin(math.radians(5.0)), "Sy")
    corners = s
    # 18 template points, K = 0..17 (ceil(180 / 10))
    pts = []
    for k in range(18):
        p = unreal.PCGPoint()
        p.set_editor_property("transform", unreal.Transform(location=unreal.Vector(100.0 * k, 0.0, 0.0)))
        pts.append(p)
    tmpl = K.node("PCGCreatePointsSettings", points_to_create=pts,
                  coordinate_space=unreal.PCGCoordinateSpace.WORLD)
    kk = K.maths((tmpl, "Out"), "DIVIDE", "$Position.X", 100.0, "K")
    cp = K.node("PCGCopyPointsSettings",
                attribute_inheritance=unreal.PCGCopyPointsMetadataInheritanceMode.SOURCE_FIRST)
    K.edge(kk, cp, "Source")
    K.edge(corners, cp, "Target")
    s, _ = K.filt((cp, "Out"), "K", "LESSER", against="N")
    s = K.maths(s, "ADD", "K", 0.5, "KH")
    s = K.maths(s, "DIVIDE", "PreviousAngle", Sel("N"), "Step")
    s = K.maths(s, "MULTIPLY", "KH", Sel("Step"), "YawD")
    s = K.maths(s, "ADD", "Yaw0", Sel("YawD"), "Yaw")
    rot = K.node("PCGMetadataMakeRotatorSettings",
                 operation=unreal.PCGMetadataMakeRotatorOp.MAKE_ROT_FROM_ANGLES,
                 input_source1=Sel("@Last"), input_source2=Sel("@Last"), input_source3=Sel("Yaw"),
                 output_target=Sel("$Rotation"))
    K.edge(K.const("Double", 0.0, "Zero"), rot, "Roll")
    K.edge(K.const("Double", 0.0, "Zero"), rot, "Pitch")
    K.edge(s, rot, "Yaw")
    vec = K.node("PCGMetadataMakeVectorSettings", input_source1=Sel("Sx"), input_source2=Sel("Sy"),
                 input_source3=Sel("@Last"), output_target=Sel("$Scale"))
    K.edge((rot, "Out"), vec, "X")
    K.edge((rot, "Out"), vec, "Y")
    K.edge(K.const("Double", 1.0, "One"), vec, "Z")
    pos = K.node("PCGCopyAttributesSettings", input_source=Sel("VPos"), output_target=Sel("$Position"))
    K.edge((vec, "Out"), pos, "Target")
    K.edge((vec, "Out"), pos, "Source")
    convex, concave = K.filt((pos, "Out"), "PreviousAngle", "GREATER", value=("Double", "DoubleValue=0.000000"))
    outs = []
    for port, sym in ((convex, "FF"), (concave, "FB")):
        tab, _ = K.filt(P["modules"], "Symbol", "EQUAL", value=("String", 'StringValue="%s"' % sym))
        tab_set = K.node("PCGConvertToAttributeSetSettings")
        K.edge(tab, tab_set, "In")
        m = K.node("PCGMatchAndSetAttributesSettings", match_attributes=True,
                   input_attribute=Sel("LevelNumber"), match_attribute=Sel("Level"), keep_unmatched=False)
        K.edge(port, m, "In")
        K.edge((tab_set, "Out"), m, "Match Data")
        outs.append((m, "Out"))
    P["fans"] = K.merge(*outs)
    return P["fans"]
```
In `main()`: for `"abcde"` and `"all"` call `build_segment_e(K, P)`; for `"abcde"` call `build_spawner(K, P["walls"], P["fans"])`.

Pins that are not taken from Epic edges and must be confirmed by `GraphKit.edge`: `CopyPoints Source/Target`, `CreatePoints Out`, `MetadataTrig In`, `MakeRotator Roll/Pitch/Yaw` (Epic's `MakeRotatorAttribute_4` wires `Roll`, `Pitch`, `Yaw` — known), `MakeVector X/Y/Z`. Enum member names are the Python upper-snake forms of the C++ enums read from the engine headers (`EPCGMetadataTrigOperation::DegToRad` → `DEG_TO_RAD`).

- [ ] **Step 2: Build, generate, read**: `tl_make_spline_graph.py {"segments":"abcde"}` → probe `gen` → next call `tl_probe_spline_counts.py`.
Expected: for the probe L-shape (5 convex 90° + 1 concave 90°) each storey has `FanFront` = 5 × 9 = 45 and `FanBack` = 9 instances; L0 too.

- [ ] **Step 3: Commit**

```bash
git add Content/Python/tl_make_spline_graph.py
git commit -m "Place the corner fans in the spline building graph" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Props and roof

**Files:** Modify `Content/Python/tl_make_spline_graph.py`

**Interfaces — Consumes:** `P["walls"]`, `P["props"]`, `P["footprint"]`, `P["segs"]`. **Produces:** `build_props(K, P) -> port`, `build_roof(K, P)`.

- [ ] **Step 1: Add props (copied from Epic, PropOffset step dropped — ruling R6)**

```python
def build_props(K, P):
    has, _ = K.filt(P["walls"], "HasProps", "EQUAL", value=("Boolean", "BoolValue=True"))
    ren = K.copy("AttributeRename_0")                     # ModuleName -> Mod_Name
    K.edge(P["props"], ren, "In")
    part = K.copy("AttributePartition_5")                 # by Mod_Name
    K.edge((ren, "Out"), part, "In")
    loop = K.copy("Loop_3")                               # Loop_GroupedPropsCopy
    K.edge((part, "Out"), loop, "Props")
    K.edge(has, loop, "Modules")
    win = K.copy("AttributeFilter_21")                    # WindowHelper == False
    K.edge((loop, "Props"), win, "In")
    tp = K.copy("TransformPoints_1")
    K.edge((win, "InsideFilter"), tp, "In")
    merge3 = K.copy("MergeAttributes_1")
    for c in ("CreateConstant_26", "CreateConstant_27", "CreateConstant_28"):
        K.edge((K.copy(c), "Out"), merge3, "In")
    add3 = K.copy("AddAttribute_3")
    K.edge((tp, "Out"), add3, "In")
    K.edge((merge3, "Out"), add3, "Attributes")
    clutter = K.copy("Subgraph_0")                        # ASM_Clutter_Behavior, Epic's overrides
    K.edge((add3, "Out"), clutter, "Points In")
    decal = K.copy("AttributeFilter_22")                  # Decal == False
    K.edge((clutter, "Points Out"), decal, "In")
    P["props_out"] = (decal, "InsideFilter")
    return P["props_out"]
```

- [ ] **Step 2: Add the roof**

```python
# Before writing this, confirm the node names: run tl_probe_node_settings.py on
# PCG_TL_Building_BDF and use the names of its Create_Mesh_Planar and rooftop
# Fill subgraph nodes (Subgraph_2 / Subgraph_5 below are the expected names).
BLDG_BDF_GRAPH = "/Game/PCG/TL/PCG_TL_Building_BDF"     # holds the planar-mesh and rooftop-fill nodes


def build_roof(K, P):
    top = K.maths(P["segs"], "ADD", "$Position.Z", Sel("Size"), "TopZ")
    red = K.node("PCGAttributeReduceSettings", input_source=Sel("TopZ"),
                 operation=unreal.PCGAttributeReduceOperation.MAX, output_attribute_name="RoofZ")
    K.edge(top, red, "In")
    roofz = K.maths((red, "Out"), "ADD", "RoofZ", -50.0, "RoofZ")        # RoofData.Y (ruling R5)
    poly = K.node("PCGCreatePolygon2DSettings")
    K.edge(P["footprint"], poly, "In")
    off = K.node("PCGOffsetPolygon2DSettings", offset=-20.0,
                 join_type=unreal.PCGPolygonJoinType.MITER)
    K.edge((poly, "Out"), off, "In")
    pts = K.node("PCGCollapseSettings")
    K.edge((off, "Out"), pts, "In")
    setz = K.node("PCGMetadataMathsSettings", operation=unreal.PCGMetadataMathsOperation.SET,
                  input_source1=Sel("$Position.Z"), input_source2=Sel("RoofZ"),
                  output_target=Sel("$Position.Z"))
    K.edge((pts, "Out"), setz, "InA")
    K.edge(roofz, setz, "InB")
    spl = K.node("PCGCreateSplineSettings", closed_loop=True, linear=True)
    K.edge((setz, "Out"), spl, "In")
    planar = K.copy("Subgraph_2", graph_path=BLDG_BDF_GRAPH)            # Create_Mesh_Planar, bitumen
    K.edge((spl, "Out"), planar, "PrimaryInput")
    fill = K.copy("Subgraph_5", graph_path=BLDG_BDF_GRAPH)              # 14 rooftop assemblies
    K.edge((spl, "Out"), fill, "PrimaryInput")
```
In `main()` for `"all"`: `build_segment_d`, `build_segment_e`, `build_props`, `build_roof`, then `build_spawner(K, P["walls"], P["fans"], P["props_out"])`.

- [ ] **Step 3: Build, generate, read**: `{"segments":"all"}` → probe `gen` → `tl_probe_spline_counts.py`.
Expected: prop meshes present (`Prop_` names, count > 0), `SM_Plane_NN_A`/rooftop meshes present, one dynamic-mesh roof (check `DynamicMeshComponent` count ≥ 1 on the actor).

- [ ] **Step 4: Commit**

```bash
git add Content/Python/tl_make_spline_graph.py
git commit -m "Add facade props and the roof to the spline building graph" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Host actor, test level, acceptance A1–A7

**Files:** Create `Content/Python/tl_spline_level.py`, `Content/Python/tl_probe_spline_building.py`, `Content/Python/tl_spline_shot.py`

**Interfaces — Consumes:** `corner_math` (Task 2), the graph (Tasks 7–10).

- [ ] **Step 1: Write `tl_spline_level.py`** — creates `/Game/PCG/TL/BP_TL_SplineBuilding` (parent `Actor`; components `SplineComponent` "Footprint" and `PCGComponent` with the graph) through `unreal.SubobjectDataSubsystem`, creates/loads `/Game/Map/Lvl_TL_Spline` from `Template_Default` (same purge-then-switch code as `tl_new_showcase_level.py`, `DEST = "/Game/Map/Lvl_TL_Spline"`), and places the buildings:

```python
BUILDINGS = {   # label: (origin, vertices (cm, local), Height)
    "TL_Hex":  ((0, 0, 0), [(3000 * math.cos(math.radians(60 * k)), 3000 * math.sin(math.radians(60 * k))) for k in range(6)], 3000.0),
    "TL_Pent": ((12000, 0, 0), [(0, 0), (4000, 0), (4400, 1300), (3000, 1300 + 400 * math.tan(math.radians(70))), (0, 2600)], 3000.0),
    "TL_L":    ((0, 12000, 0), [(0, 0), (6000, 0), (6000, 3000), (3000, 3000), (3000, 6000), (0, 6000)], 3000.0),
    "TL_Rect": ((12000, 12000, 0), [(0, 0), (6000, 0), (6000, 3000), (0, 3000)], 3000.0),
    "TL_Low":  ((24000, 0, 0), [(0, 0), (3000, 0), (3000, 2000), (0, 2000)], 1000.0),          # Review Focus 4
    "TL_Tilt": ((24000, 12000, 0), [(0, 0), (4000, 0), (4000, 3000), (0, 3000)], 3000.0),      # vertex 2 raised 50 cm, Review Focus 1
}
```
Write the pentagon so it holds one 20° convex corner next to a 400 cm edge (Review Focus 3): adjust the third/fourth vertices until `corner_math.classify` reports exactly one corner with interior 20° ± 0.5 and `edge_plan` reports `short` for the 400 cm edge — assert both in the script before placing. Each building: spawn the BP, set spline points (`clear_spline_points`, `add_spline_point(Vector, WORLD)`, `set_spline_point_type(i, LINEAR)`, `set_closed_loop(True)`, `update_spline()`), set the instance's `Height` with `PCGGraphParametersHelpers.set_double_parameter(graph_instance, "Height", h)`, `activate(True)`, `generate_local(True)`. `{"probe_only": true}` places only `TLPROBE_Spline` (the L-shape) for Tasks 7–10.
If `SubobjectDataSubsystem` cannot add the components, **stop and ask the user** to create `BP_TL_SplineBuilding` in the editor (Actor + Spline + PCG components, 1 minute); do not work around it.

- [ ] **Step 2: Write `tl_probe_spline_building.py`** (phase `read`; reads every building in the level):
  - **A1** For each `EndPier_01`/`EndPierAcute_01` instance, world positions of local (0,0,0) and (0,150,0) on the facade line; one of them is a cleaned footprint vertex within 0.05 cm.
  - **A2** Group `FanFront_01`/`FanBack_01` instances per storey and vertex; compare with `corner_math.fan(clean(footprint), i)`: same count, kind; yaw within 0.01°; scale X/Y within 1e-4.
  - **A3** Within each group, sorted by yaw: consecutive yaw difference = `a_k + a_{k+1}` within 0.01°, first edge = incoming normal, last = outgoing normal (from A2's model values).
  - **A4** `TL_Rect` L1: the run positions of W1/WS1/P1/E1 instances along the 6000 cm edge equal those of a temporary `TLPROBE_Bdf` volume running `/Game/PCG/TL/PCG_TL_Building_BDF` with WingA = WingB = 6000 × 3000 (corner pieces mapped to piers) within 0.05 cm. The temporary volume is destroyed at the end of the probe.
  - **A5** Every pier next to a vertex with `acute == True` is `EndPierAcute_01`, and no other pier is.
  - **A6** Per storey edge, the multiset of placed wall symbols equals the expansion `corner_math.edge_plan` predicts (compare symbol counts, not order).
  - **Review Focus 1** All modules of one storey of `TL_Tilt` share one Z.
  - **Review Focus 2** Reverse `TL_L`'s spline point order (`gen_reverse` phase), regenerate, read: the sorted list of (mesh, rounded transform) is identical.
  - **Review Focus 4** `TL_Low` has L1 and L4 instances.
  Output: per check `pass`/`fail` with the worst value.

- [ ] **Step 3: Run**: `tl_spline_level.py` → next call `tl_probe_spline_building.py {"phase":"read"}` → `{"phase":"gen_reverse"}` → next call `{"phase":"read_reverse"}`.
Expected: every check `pass`.

- [ ] **Step 4: A7 screenshots** — `tl_spline_shot.py` (same body as `tl_showcase_shot.py`, label filter removed so all buildings stay visible): one close-up per corner type: hexagon convex, pentagon 20° acute, L-shape concave, rectangle 90°, plus one top view of a concave corner's parapet. Names `sp_hex_corner`, `sp_acute20`, `sp_concave`, `sp_rect90`, `sp_concave_top`; wait with `Saved/wait_shot.sh`. Look at each: no visible crack; send them to the user.

- [ ] **Step 5: Save the test level** (only after all `TLPROBE_*` actors are gone): a `tl_save_spline_level.py` that refuses unless the world is `/Game/Map/Lvl_TL_Spline` and no actor label starts with `TLPROBE_`.

- [ ] **Step 6: Commit**

```bash
git add Content/Python/tl_spline_level.py Content/Python/tl_probe_spline_building.py Content/Python/tl_spline_shot.py Content/Python/tl_save_spline_level.py Content/PCG/TL
git commit -m "Add the spline building test level and its acceptance probe" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```
(`Content/Map/` is gitignored; `Lvl_TL_Spline` stays local, like the showcase.)

---

### Task 12: Regression, docs, memory

**Files:** Modify `docs/tl-kit-mesh-checklist.md`, `.claude/skills/city-sample-pcg-city-builder/references/traps.md`; memory `tl-building-style-state.md`

- [ ] **Step 1: Regression**: `pytest Tools/tl_kit -q` all pass; `Lvl_TL_Showcase` regenerate + read = 1,562 module instances; `tl_make_bdf.py` report `epic_source_untouched: true`.
- [ ] **Step 2: Docs**: checklist section 10 "Spline building" (the 18 parts, rulings R1–R6, acceptance numbers). traps.md section 7: the `IsClockwiseXY` naming inversion, `add_node_copy` as the way to carry inline defaults, the PCG user-parameter limitation (R4), and whatever Task 1's spike measured.
- [ ] **Step 3: Memory**: update `tl-building-style-state.md` with the spline building's paths, the rulings and how to regenerate.
- [ ] **Step 4: Commit**

```bash
git add docs/tl-kit-mesh-checklist.md .claude/skills/city-sample-pcg-city-builder/references/traps.md
git commit -m "Record the spline building in the TL docs and traps" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```
