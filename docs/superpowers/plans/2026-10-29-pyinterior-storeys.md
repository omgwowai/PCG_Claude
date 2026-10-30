# PyInterior 多层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Multi-storey PCG houses (1–3 floors): one footprint spline per floor (by height), upper floors clipped to the floor below
(setbacks), a stair chosen first and aligned through all floors, each floor planned around it by per-floor rule tables, exposed roofs
as walkable terraces; single-floor houses unchanged; verified on a second street of `/Game/PyPCG/L_PyInterior`.

**Architecture:** New pure-Python modules beside the single-floor rules — `interior/storeys.py` (floors from splines, the building
loop), `interior/stairs.py` (stair types, candidates, parts), `interior/floorplan.py` (planning one floor around the fixed stair room,
reusing `layout`'s templates), `interior/terrace.py` (terrace door, furniture, parts). Single-floor modules get additive changes only
(default-argument hooks, appended table entries), guarded by golden digests of today's output. The stage dispatches: one floor →
today's path; two or three → `storeys`.

**Tech Stack:** UE 5.8 PCG + PCGPythonInterop, the project's `pypcg` DSL / host / convert, pytest on system Python 3.14, PIL for offline
plans.

**Spec:** `docs/superpowers/specs/2026-10-29-pyinterior-storeys-design.md` (single-floor rules: `docs/superpowers/specs/2026-10-28-pyinterior-design.md`,
`docs/pyinterior-guide.md`).

**Rulings (planner = executor):**
- R1: the plan pins interfaces, rules and tests; implementation is written test-first directly in the files (writing it twice in the
  plan would double the work without a handoff to justify it). Cost if wrong: an interface drifts — mitigated by each task's
  Interfaces block and the golden digests.
- R2: no commit steps — the user's standing rule is "commit only when asked".
- P1: the spec's three block cuts (greedy max-rect, cut-across-first, cut-along-first) are produced by one enumeration: the stair
  room's four lines cut each wing it overlaps into a 3 × 3 grid, and each corner cell joins one of its two neighbouring side cells.
  For a stair inside one wing this contains all three. Cost if wrong: a few more options to try per floor (time, measured in Task 8).
- P2: terrace furniture reuses catalogue items `Table_2` (StarterContent round table), `Armchair` (StarterContent lounge chair) and
  `Plant` — they already have real meshes and primitive fallbacks. Cost if wrong: none.
- P3: single-floor code paths are not restructured; multi-floor planning lives in the new modules and calls `layout`'s helpers.
  Cost if wrong: some duplication between `layout._try` and `floorplan._solve`.

## Global Constraints

- `pypcg/interior/*` and `stages/i01_house.py` never import `unreal`; units cm; house-local frame per the single-floor spec (front
  faces −y).
- **Single-floor output identical**: every house with one spline and `Floors` 0 or 1 produces exactly today's Parts (golden digests,
  Task 1).
- Suite stays green: `C:\Python314\python.exe -m pytest Tools/pypcg/tests -q -p no:cacheprovider` (baseline 1943 passed, 18 skipped)
  plus the new tests.
- Floor height H = `WallHeight` + 30; floor k at z = actor z + k·H; at most 3 floors.
- Stair: 17 risers per floor for H = 300 (rise = H / ceil(H / 18)), tread 27, flight 100 wide; U 220 × 330, L 330 × 300, Straight
  110 × 450 (clear); three-floor houses U only.
- Graph assets are generated from `.py` (`build_slim`, 0 diffs) and never hand-edited; run `assign` after every `build`.
- Never save probe / preview actors; never kill the PCG_Codex editor (its command line contains `E:/PCG_Codex/PCG_Codex.uproject`);
  never `load_level` in a bridge call that destroyed actors (trap 123); move `Saved/Autosaves` aside after a crash.
- Editor calls: one phase per call; long ones `{"defer": true}`; screenshots one at a time with throttle off (traps 88, 96).
- Performance: a multi-storey house plans in 0.1–0.6 s typically, ≤ 1.5 s worst (measured by the census, Task 8 / Task 11).

## Review Focus

1. **Setbacks that leave an awkward upper floor** (an L-shaped 2F, a 2F narrower than 5 m, a setback line right next to the best stair
   spot): the stair stays inside the top floor, every kept floor plans clean, and a floor that cannot be planned is dropped with a
   report — never a broken floor. Tests: Task 8 `test_awkward_setbacks_plan_clean_or_drop_with_a_note`.
2. **Rotated multi-storey houses** (yaw 30°, 90°, 217°): every floor, the stair and the terraces turn with the actor and stack at
   actor z + k·H. Test: Task 9 `test_a_turned_building_is_the_same_building_turned`.
3. **Upper-floor circulation**: every upper-floor room is reached from the stair arrival without passing through a bedroom, bath, WC
   or laundry (Upper_S's loft bedroom is the one exception), and a stair opening never faces an exterior wall or a wet room. Test:
   Task 6 `test_upper_floor_circulation`.
4. **Single-floor regression** — legacy houses (one spline) and odd inputs (`Floors` 1 with two splines; a spline below the actor;
   two splines on one level) produce today's output or a reported note, never a different single-floor house. Tests: Task 1
   `test_single_floor_houses_are_unchanged`, Task 10 `test_stage_odd_spline_sets`.
5. **Determinism and degenerate counts**: the same splines + seed give identical parts; `Floors` above what fits (3 floors on a
   6 × 6 m house) drops floors with notes; `ShowFloors` larger than the floor count shows everything. Tests: Task 8
   `test_deterministic`, `test_three_floors_on_a_small_house_drop_with_notes`; Task 9 `test_show_floors_bounds`.

---

## File Structure

| File | Responsibility |
|---|---|
| `Content/Python/pypcg/interior/storeys.py` (new) | `levels`, `floor_footprints`, `terrace_rects`, `plan_building`, `parts`, `validate`, `summary`, `room_rows` |
| `Content/Python/pypcg/interior/stairs.py` (new) | `TYPES`, `Stair`, `candidates`, `parts` |
| `Content/Python/pypcg/interior/floorplan.py` (new) | `pieces_options`, `plan_floor` (ground / middle / top) |
| `Content/Python/pypcg/interior/terrace.py` (new) | `Terrace`, `plan_terraces` (door, furniture), `parts` (slab, deck, railing) |
| `interior/footprint.py` | `from_cells` (build's tail, reused for clipped floors) |
| `interior/program.py` | `GROUND`, `UPPER`, `choose_floor`, `fallbacks(..., table=)`, `ROOMS["Stair"]`, appended ACCESS |
| `interior/layout.py` | `Plan.stair`, `Plan.level` (defaults), `connect(..., only=None)`, `passage` → "stair" |
| `interior/doors.py` | front door only when `plan.entry`; stair passages at the access span; `terrace_doors`; kinds "stair", "terrace" |
| `interior/furnish.py` | `approach`: 100 cm, full span, for "stair" passages |
| `interior/assemble.py` | `Level` / `StairRoom` params: slab instead of foundation, no floor in an upper stair room; "stair" / "terrace" doors; `_Out.bar` |
| `interior/checks.py` | no front door required on upper floors |
| `interior/demo.py` | `STOREYS`, `storeys()`, `floor_points` |
| `pypcg/stages/i01_house.py` | params `Floors`, `ShowFloors`, `StairType`; splines by level; dispatch; `Floor` on Rooms |
| `Content/Python/pyinterior.py` | multi-spline houses (`houses {"set": "storeys"}`), `shape {"floor"}`, `view`, `read` / `status` / `site` for storeys |
| `Content/Python/pyinterior_materials.py` | `Floor_Deck` |
| `Tools/pyinterior/plan.py`, `census.py` | `--storeys` |
| `Tools/pypcg/tests/test_interior_regression.py` (new) | golden digests of today's single-floor output |
| `Tools/pypcg/tests/test_interior_storeys.py`, `test_interior_stairs.py`, `test_interior_floorplan.py` (new) | multi-storey tests |

---

### Task 1: Golden digests, floors from splines, clipping, terrace regions

**Files:**
- Create: `Tools/pypcg/tests/test_interior_regression.py`, `Content/Python/pypcg/interior/storeys.py`, `Tools/pypcg/tests/test_interior_storeys.py`
- Modify: `Content/Python/pypcg/interior/footprint.py` (extract `from_cells`)

**Interfaces — Produces:**
- `footprint.from_cells(cells, grid, frame, min_wing=250.0) -> Footprint | None` — clean, drop thin wings, check the minimum, build
  wings / outline (exactly `build`'s tail; `build` calls it).
- `storeys.SLAB = 30.0`, `storeys.MAX_FLOORS = 3`, `storeys.floor_height(wall_height) -> float`.
- `storeys.Levels(outlines: tuple, notes: tuple)` — `outlines[k]` = world points of floor k's spline, or `None` (copy the floor below).
- `storeys.levels(splines, origin_z, wall_height, floors_param) -> Levels` — `splines`: `[[(x, y, z), ...], ...]`.
- `storeys.floor_footprints(lv, origin, yaw, grid, wall_height) -> (fps: list[Footprint], dropped: list[str])` — floor k's frame
  origin is raised k·H; cells clipped to floor k−1 then `from_cells`; a floor below the minimum ends the list.
- `storeys.terrace_rects(fps) -> {k: [Rect]}` — for k ≥ 1, rectangles of `cells[k-1] − cells[k]` (decompose), house-local.

- [ ] **Step 1: Record the golden digests before touching anything.** Write `test_interior_regression.py` with a `digest(out)` over
  the stage's Parts (loc rounded to 1e-3, rot to 1e-3, scale to 1e-4, `Mesh`, `Mat0`) and `GOLDEN = {}`; run once with a print helper
  to fill `GOLDEN` for the 8 demo houses and for six sweep footprints (rect 5×4.5 m, 9×6, 12×8, 15×10, L 14×11, U 16×10), seeds 1–2.

```python
import hashlib
import pytest
from pypcg import stage_api
from pypcg.interior import demo
from pypcg.stages import i01_house
from test_interior_stage import inputs_for

GOLDEN = {}   # filled in step 1 from main 9252cb7: {name or "sweep-<w>x<h>-<seed>": sha1}

def digest(out):
    p = out["Parts"][0][0]
    rows = [(tuple(round(v, 3) for v in p.loc[i]), tuple(round(v, 3) for v in p.rot[i]),
             tuple(round(v, 4) for v in p.scale[i]), p.attrs["Mesh"][i], p.attrs["Mat0"][i]) for i in range(len(p))]
    return hashlib.sha1(repr(rows).encode()).hexdigest()

@pytest.mark.parametrize("name, shape, loc, yaw, style, seed", demo.houses())
def test_single_floor_houses_are_unchanged(name, shape, loc, yaw, style, seed):
    out, _ctx = stage_api.execute(i01_house, inputs_for(shape, loc, yaw),
                                  dict(stage_api.defaults(i01_house), Style=style, Seed=seed), None)
    assert digest(out) == GOLDEN[name]
```

- [ ] **Step 2: Run it** — Expected: 8 + 12 passed (digests just recorded).
- [ ] **Step 3: Write the failing storeys tests** (`test_interior_storeys.py`):

```python
from pypcg.interior import storeys as S
from pypcg.interior.footprint import Rect

def box(w, h, x0=0.0, y0=0.0):                 # world points (z 0) of a local box for an actor at the origin, yaw 0
    from test_interior_footprint import world_of
    return world_of([(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)], (0, 0, 0), 0.0)

def with_z(pts, z):
    return [(x, y, z) for x, y, _ in pts]

def test_levels_group_splines_by_height():
    lv = S.levels([box(1000, 800), with_z(box(1000, 800), 300.0)], 0.0, 270.0, 0)
    assert len(lv.outlines) == 2 and all(o is not None for o in lv.outlines) and not lv.notes

def test_floors_param_copies_the_floor_below():
    lv = S.levels([box(900, 800)], 0.0, 270.0, 2)
    assert len(lv.outlines) == 2 and lv.outlines[1] is None

def test_lowest_spline_becomes_the_ground_floor():
    lv = S.levels([with_z(box(900, 800), 300.0), with_z(box(900, 800), 600.0)], 0.0, 270.0, 0)
    assert len(lv.outlines) == 2 and lv.notes

def test_two_splines_on_one_level_keep_the_largest():
    lv = S.levels([box(900, 800), box(600, 500)], 0.0, 270.0, 0)
    assert len(lv.outlines) == 1 and lv.notes and len(lv.outlines[0]) == 4

def test_at_most_three_floors():
    lv = S.levels([box(900, 800)], 0.0, 270.0, 5)
    assert len(lv.outlines) == 3 and lv.notes

def test_upper_floor_is_clipped_and_raised():
    lv = S.levels([box(1000, 800), with_z(box(1400, 600), 300.0)], 0.0, 270.0, 0)
    fps, dropped = S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)
    assert len(fps) == 2 and not dropped
    assert fps[1].cells <= fps[0].cells and fps[1].to_world(0, 0, 0)[2] == 300.0

def test_too_small_upper_floor_is_dropped():
    lv = S.levels([box(1000, 800), with_z(box(400, 400), 300.0)], 0.0, 270.0, 0)
    fps, dropped = S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)
    assert len(fps) == 1 and dropped

def test_terraces_are_the_uncovered_roof():
    lv = S.levels([box(1000, 900), with_z(box(1000, 600, y0=300), 300.0)], 0.0, 270.0, 0)
    fps, _ = S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)
    rects = S.terrace_rects(fps)[1]
    assert sum(r.area for r in rects) == 1000 * 300 and all(r.y1 <= 300 for r in rects)
```

  (`box` builds local coordinates with `world_of` so the actor frame is the identity used everywhere; local y = 0 is the front.)
- [ ] **Step 4: Run** `-k storeys` — Expected: FAIL (`storeys` not defined).
- [ ] **Step 5: Implement** `footprint.from_cells` (move `build`'s clean / thin loop / minimum / wings / outline into it; `build`
  becomes rasterise + `from_cells`) and `storeys.levels`, `floor_footprints`, `terrace_rects`:
  - level of a spline = round((mean z − origin_z) / H); shift so the lowest is 0 (note); per level the largest-area spline (note the
    others); N = `floors_param` or (highest level + 1), clamped to 1..3 (note when clamped); levels ≥ N ignored (note).
  - floor k ≥ 1: rasterise its outline (or reuse floor k−1's cells), intersect with floor k−1's cells, `from_cells` with
    `Frame((ox, oy, oz + k·H), yaw)`; `None` → this floor and the ones above are dropped (`"2F: smaller than 4.5 x 5 m / 20 m2"`).
- [ ] **Step 6: Run** the storeys tests and the regression file — Expected: PASS; regression digests unchanged.

### Task 2: Floor programs and the stair room type

**Files:** Modify `Content/Python/pypcg/interior/program.py`; Test `Tools/pypcg/tests/test_interior_program.py`

**Interfaces — Produces:**
- `P.GROUND`, `P.UPPER` (tuples of `Program`, spec §5.2); `P.ROOMS["Stair"] = RoomType("circulation", 100.0, 100.0, "wood", None,
  "neutral", "楼梯间")`.
- `P.choose_floor(area_m2, level, top) -> Program` — `GROUND` for level 0, `UPPER` otherwise; on an upper floor that is not the top,
  every `Master` slot becomes `Bedroom` (same weight).
- `P.fallbacks(program, table=PROGRAMS)` — same walk, inside `table` (default keeps today's behaviour).
- ACCESS: append `"Stair"` to `Corridor`, `Master`, `Bedroom` (at the end — single-floor access costs unchanged); new
  `ACCESS["Stair"] = ("Living", "Corridor", "Dining")`.

- [ ] **Step 1: Failing tests:**

```python
def test_floor_tables_choose_by_area():
    assert P.choose_floor(20.0, 0, False).name == "Ground_S" and P.choose_floor(40.0, 0, False).name == "Ground_M"
    assert P.choose_floor(60.0, 0, False).name == "Ground_L"
    assert [P.choose_floor(a, 1, True).name for a in (20.0, 35.0, 55.0, 80.0)] == ["Upper_S", "Upper_M", "Upper_L", "Upper_XL"]

def test_one_master_per_house():
    assert "Master" in P.choose_floor(55.0, 2, True).types()
    assert "Master" not in P.choose_floor(55.0, 1, False).types() and P.choose_floor(55.0, 1, False).types().count("Bedroom") == 3

def test_floor_fallbacks_stay_in_their_table():
    for v in P.fallbacks(P.choose_floor(70.0, 0, False), P.GROUND):
        assert v.name.startswith("Ground_") and {"Living", "Kitchen"} <= set(v.types())
    for v in P.fallbacks(P.choose_floor(90.0, 1, True), P.UPPER):
        assert v.name.startswith("Upper_") and "Bath" in v.types() and {"Master", "Bedroom"} & set(v.types())

def test_single_floor_tables_are_unchanged():
    assert [p.name for p in P.PROGRAMS] == ["Studio", "OneBed", "TwoBed", "ThreeBed", "FourBed"]
    assert P.ACCESS["Bedroom"][:4] == ("Corridor", "Living", "Dining", "Main")
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** program tests + regression — PASS, digests unchanged.

### Task 3: Stair types and candidates

**Files:** Create `Content/Python/pypcg/interior/stairs.py`, `Tools/pypcg/tests/test_interior_stairs.py`

**Interfaces — Produces:**
- `StairType(name, clear_w, clear_l, max_floors)`; `TYPES = {"U": (220, 330, 3), "L": (330, 300, 2), "Straight": (110, 450, 2)}`.
- `Stair(type, rect, clear, orient, n_floors)` (frozen). `orient` 0..3 = direction u from the access end into the stair: +y, −x, −y,
  +x. Methods:
  - `access(role) -> (axis, c, s0, s1)` — the opening on a floor of role `"ground"`, `"middle"`, `"top"` (U: ground = flight A's half
    of the open end, middle and top = the whole open end; Straight: ground = near end, top = far end; L: ground = near end, top = the
    far corner of the long inner side).
  - `void(role) -> (axis, c, s0, s1) | None` — U top floor: flight A's half (gets a guard rail).
  - `cells(grid) -> frozenset` — the 50 cm cells the stair room overlaps.
- `candidates(fps, stair_type="Auto") -> (list[Stair], list[str] notes)` — every type allowed for len(fps) floors (forced type kept
  only when allowed, else a note and Auto); each top-floor exterior segment, each orientation with one stair side on the segment and
  the openings not on an exterior side, placed at the segment's start, end and middle (10 cm snap); the stair room = clear size +
  25 on exterior sides + 6 on interior sides; kept when the room lies inside the top floor and the cells across each opening it uses
  are in that floor; sorted by: touches the ground floor's front (+1.0), bottom opening's distance to the front's centre (×0.6 /
  max extent), stair centre's distance to the top floor's centre (×0.6 / max extent), clear area (×0.3 / 10 m²); ties by position.

- [ ] **Step 1: Failing tests:**

```python
from pypcg.interior import stairs as ST, storeys as S
from test_interior_storeys import box, with_z

def two_floors(w, h, n=2):
    lv = S.levels([box(w, h)], 0.0, 270.0, n)
    return S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)[0]

def test_types():
    assert ST.TYPES["U"].max_floors == 3 and ST.TYPES["L"].max_floors == 2 and ST.TYPES["Straight"].max_floors == 2

def test_candidates_stay_inside_and_on_an_outer_wall():
    fps = two_floors(1000, 800)
    cands, _ = ST.candidates(fps)
    assert cands
    for s in cands:
        assert s.cells(50.0) <= fps[-1].cells
        r = s.rect
        assert abs(r.x0) < 1e-6 or abs(r.x1 - 1000) < 1e-6 or abs(r.y0) < 1e-6 or abs(r.y1 - 800) < 1e-6   # on an outer wall
        for role in ("ground", "top"):
            axis, c, s0, s1 = s.access(role)
            assert 0 < c < (1000 if axis == "x" else 800)            # never on the outline

def test_three_floors_use_u_only():
    cands, notes = ST.candidates(two_floors(600, 1100, 3), "Straight")
    assert cands and {s.type for s in cands} == {"U"} and notes

def test_access_spans():
    s = next(c for c in ST.candidates(two_floors(1000, 800))[0] if c.type == "U")
    g, t = s.access("ground"), s.access("top")
    assert abs((g[3] - g[2]) - 110.0) < 1e-6 and abs((t[3] - t[2]) - 220.0) < 1e-6 and s.void("top") is not None

def test_first_candidate_keeps_off_the_front():
    s = ST.candidates(two_floors(1000, 800))[0][0]
    assert s.rect.y0 > 1e-6
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.

### Task 4: Blocks around the stair; connect restricted to the access room

**Files:** Create `Content/Python/pypcg/interior/floorplan.py`, `Tools/pypcg/tests/test_interior_floorplan.py`; Modify
`Content/Python/pypcg/interior/layout.py`

**Interfaces — Produces:**
- `floorplan.pieces_options(fp, stair_rect, min_piece=250.0) -> list[list[Rect]]` — rulings P1; options with a piece whose short side
  < `min_piece` are dropped; deduplicated; ordered by (fewer pieces, larger smallest side).
- `layout.connect(rooms, fp, front_room, only=None)` — `only = {room id: the one neighbour id it may join through}` (both directions).
- `layout.Plan` gains `stair: object = None`, `level: int = 0`; `layout.passage` returns `"stair"` when either type is `Stair`;
  `layout.SPAN["stair"] = 100.0`.

- [ ] **Step 1: Failing tests:**

```python
from pypcg.interior import floorplan as FP, layout as L, stairs as ST
from test_interior_stairs import two_floors

def test_pieces_tile_the_floor_without_the_stair():
    fps = two_floors(1000, 800)
    for s in ST.candidates(fps)[0][:6]:
        for opt in FP.pieces_options(fps[0], s.rect):
            assert abs(sum(r.area for r in opt) - (fps[0].area - s.rect.area)) < 1e-6
            assert all(not a.overlaps(b) for i, a in enumerate(opt) for b in opt[i + 1:])
            assert all(not r.overlaps(s.rect) and r.short >= 250.0 - 1e-6 for r in opt)

def test_a_mid_side_stair_offers_both_cuts():
    fps = two_floors(1200, 900)
    s = next(c for c in ST.candidates(fps)[0] if c.rect.x0 > 300 and c.rect.x1 < 900)
    shapes = {tuple(sorted((round(r.w), round(r.h)) for r in opt)) for opt in FP.pieces_options(fps[0], s.rect)}
    assert len(shapes) >= 2

def test_connect_only_joins_through_the_named_room():
    rooms = [L.Room(0, "Living", L.Rect(0, 0, 500, 400)), L.Room(1, "Corridor", L.Rect(500, 0, 700, 400)),
             L.Room(2, "Stair", L.Rect(500, 400, 700, 700)), L.Room(3, "Dining", L.Rect(0, 400, 500, 700))]
    from test_interior_layout import fp_of
    fp = fp_of([(0, 0), (700, 0), (700, 700), (0, 700)])
    parents = L.connect(rooms, fp, 0, only={2: 1})
    assert parents[2] == 1
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** (nine-grid per overlapped wing; corner → side merges; `only` checked in the
  candidate filter of `connect`). **Step 4: Run** floorplan + layout + regression tests — PASS, digests unchanged.

### Task 5: Plan the ground floor around the stair

**Files:** Modify `floorplan.py`, `test_interior_floorplan.py`

**Interfaces — Produces:** `floorplan.plan_floor(fp, prog, rng, walls, stair, level, role, mirror=False, skip=()) -> Plan` for
`role="ground"`: pieces options → configs where the entry piece (longest front) holds every public room, or Living there and Kitchen
(+ Dining) in each piece adjacent to it; other pieces private (existing `distribute`, Storage when empty); candidates through
`layout.public_layouts` / `private_layouts`, `_sizes_ok`, `_score`; the stair room added (type `Stair`, fixed rect); `connect` from the
Living with `only = {stair: the room covering stair.access("ground")}`, whose type must be in `ACCESS["Stair"]`; best by score, near
ties by `rng` (as `layout._near`); fallbacks over `P.GROUND`; nothing fits → `Plan` with `[L.NO_FIT]`. `Plan.stair = stair`,
`Plan.level = level`, `Plan.entry` / `front_room` as single-floor.

- [ ] **Step 1: Failing tests** (sweep of two-floor boxes 8–14 × 7–10 m, first three stair candidates each, seeds 1–2):

```python
CASES = [(w, h) for w in (800, 1000, 1200, 1400) for h in (700, 850, 1000)]

@pytest.mark.parametrize("w, h", CASES)
def test_ground_floor_invariants(w, h):
    import random
    from pypcg.interior import program as P
    fps = two_floors(w, h)
    for s in ST.candidates(fps)[0][:3]:
        prog = P.choose_floor((fps[0].area - s.rect.area) / 1e4, 0, False)
        plan = FP.plan_floor(fps[0], prog, random.Random(1), dict(L.WALLS), s, 0, "ground")
        if plan.failures:
            continue
        by = {r.id: r for r in plan.rooms}
        st = next(r for r in plan.rooms if r.type == "Stair")
        assert by[plan.parents[st.id]].type in P.ACCESS["Stair"]
        assert by[plan.front_room].type == "Living" and len(plan.parents) == len(plan.rooms)
        for r in plan.rooms:
            if r.type != "Stair":
                c = L.clear_rect(r.rect, plan.footprint, plan.walls)
                assert c.short >= P.ROOMS[r.type].min_short - 1e-6
        return
    pytest.fail("no stair candidate gives a ground floor")

def test_townhouse_ground_floor_has_living_front_kitchen_back():
    import random
    from pypcg.interior import program as P
    fps = two_floors(550, 1100, 3)
    s = ST.candidates(fps)[0][0]
    plan = FP.plan_floor(fps[0], P.choose_floor((fps[0].area - s.rect.area) / 1e4, 0, False), random.Random(1),
                         dict(L.WALLS), s, 0, "ground")
    assert not plan.failures
    liv = next(r for r in plan.rooms if r.type == "Living")
    kit = next(r for r in plan.rooms if r.type == "Kitchen")
    assert liv.rect.cy < kit.rect.cy
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement** `_solve(fp, configs, prog, rng, walls, stair, role)`. **Step 4: Run** — PASS.

### Task 6: Plan the upper floors (middle and top)

**Files:** Modify `floorplan.py`, `test_interior_floorplan.py`

**Interfaces — Produces:** `plan_floor(..., role in ("middle", "top"))`: blocks entered breadth-first from the stair through the piece
covering `stair.access(role)` (its side and span), the others through shared edges ≥ 120 (as `layout.configs`); all rooms private
(`private_layouts`), `distribute` over the blocks; the stair room is the root (`front_room`), `entry = None`; the access room must be a
`Corridor` covering the whole access span — or, for `Upper_S` only, a `Bedroom` / `Master`; fallbacks over `P.UPPER`; on the top
floor `_master_is_largest`.

- [ ] **Step 1: Failing tests** (the module also imports `from pypcg.interior import storeys as S` and
  `from test_interior_storeys import box, with_z`):

```python
@pytest.mark.parametrize("w, h", CASES)
def test_upper_floor_circulation(w, h):
    """Review Focus 3: every room reached from the stair without passing a bedroom or a wet room (the loft excepted)."""
    import random
    from pypcg.interior import program as P
    fps = two_floors(w, h)
    for s in ST.candidates(fps)[0][:3]:
        prog = P.choose_floor((fps[1].area - s.rect.area) / 1e4, 1, True)
        plan = FP.plan_floor(fps[1], prog, random.Random(1), dict(L.WALLS), s, 1, "top")
        if plan.failures:
            continue
        by = {r.id: r for r in plan.rooms}
        assert by[plan.front_room].type == "Stair" and plan.entry is None
        first = [r for r in plan.rooms if plan.parents.get(r.id) == plan.front_room]
        assert len(first) == 1 and (first[0].type == "Corridor" or plan.program.name == "Upper_S")
        for r in plan.rooms:
            pid = plan.parents[r.id]
            while pid is not None and pid != plan.front_room:
                assert by[pid].type not in ("Bath", "WC", "Laundry") and \
                    (by[pid].type not in ("Master", "Bedroom") or r.type == "Bath")
                pid = plan.parents[pid]
        assert "Bath" in {r.type for r in plan.rooms}
        return
    pytest.fail("no stair candidate gives an upper floor")

def test_small_top_floor_is_a_loft():
    import random
    from pypcg.interior import program as P
    lv = S.levels([box(900, 800), with_z(box(600, 600), 300.0)], 0.0, 270.0, 0)
    fps, _ = S.floor_footprints(lv, (0.0, 0.0, 0.0), 0.0, 50.0, 270.0)
    ok = False
    for s in ST.candidates(fps)[0][:6]:
        plan = FP.plan_floor(fps[1], P.choose_floor((fps[1].area - s.rect.area) / 1e4, 1, True), random.Random(1),
                             dict(L.WALLS), s, 1, "top")
        ok = ok or (not plan.failures and plan.program.name == "Upper_S")
    assert ok
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** — PASS.

### Task 7: Doors, windows and furniture per floor; terrace doors

**Files:** Modify `doors.py`, `furnish.py`, `checks.py`; Create `Content/Python/pypcg/interior/terrace.py`; Test
`test_interior_floorplan.py`, `test_interior_doors.py`

**Interfaces — Produces:**
- `doors.connect(plan, rng)`: no front door when `plan.entry is None`; a tree passage that has the stair room on one side is placed
  at `plan.stair.access(role)` with kind `"stair"` (no leaf) — role from `plan.level` and the floor count (`plan.stair.n_floors`).
- `Door.kind` adds `"stair"` (no leaf) and `"terrace"` (leaf, sliding, glass); `Door.sliding` true for `"bath"` and `"terrace"`.
- `doors.terrace_doors(plan, rects) -> [Door]` — for each terrace rect, the room of `plan` sharing ≥ 120 cm with it (order: Living,
  Master, Bedroom, Corridor, Study, Dining), a 90 cm door centred on that wall's clear part (`a=None`, `b=room id`, `tree=False`).
- `furnish.approach`: for `"stair"` 100 cm deep over the whole span.
- `checks.validate`: "no front door" only when `plan.entry` is not `None`.
- `terrace.Terrace(level, rect, door, places)`; `terrace.plan_terraces(fp, rects, plan, doors, rng) -> [Terrace]` — furniture by the
  spec's sizes (`Table_2` + 2–4 `Armchair` + `Plant`; `Plant` from 3 m²; nothing under 120 cm short side or without a door).

- [ ] **Step 1: Failing tests:**

```python
def test_front_door_only_on_the_ground_floor(): ...       # plan_floor ground + top on a 10 x 8 box; connect; kinds
def test_stair_openings_sit_at_the_access_spans(): ...    # the "stair" door's (axis, c, s0, s1) == stair.access(role)
def test_terrace_door_faces_the_terrace(): ...            # 1F 10 x 9, 2F 10 x 6 at the back: one "terrace" door on y = 300,
                                                          # no window overlapping it, the room is Living/Master/Bedroom/...
def test_upper_floor_furniture_keeps_every_rule(): ...    # furnish the top floor; check_placements from test_interior_furnish
def test_stair_landing_is_kept_free(): ...                # nothing in the 100 cm in front of every "stair" opening
```

  (Each body follows the pattern of Task 5/6: plan the floor, `D.connect`, `O.windows`, `FU.furnish`, assert. `check_placements` is
  imported from `test_interior_furnish`.)
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** floorplan + doors + furnish + regression — PASS, digests
  unchanged.

### Task 8: The building loop

**Files:** Modify `storeys.py`, `demo.py` (`STOREYS` table only), `test_interior_storeys.py`

**Interfaces — Produces:**
- `demo.STOREYS`: the seven houses of spec §10.1 as `(name, [outline per floor or None], floors, stair_type, style, seed)`, local cm.
- `storeys.FloorResult(level, fp, plan, doors, wins, places, fails, terraces)`; `storeys.Building(floors, stair, notes, dropped)`.
- `storeys.plan_building(splines, origin, yaw, params, rng) -> Building | None` — `None` when one floor is left (the caller runs the
  single-floor path on floor 0's spline); else: `stairs.candidates`, for the first K = 6 plan every floor (`P.choose_floor` on the
  floor area minus the stair room; `plan_floor`; doors with terrace doors; windows; furnish; a floor whose required furniture fails
  tries its next program variant like `house.plan_house`), keep candidates whose floors all pass, stop at 3, score = Σ floor scores +
  stair area / 1e5 + corridor area / 1e5, near ties by `rng`; none → drop the top floor (note) and retry.
- `storeys.validate(b) -> [failure]` (per floor `K.validate` + the stair on every floor with its openings + one Master + a Bath on
  every floor with bedrooms + a door on every terrace that touches a room); `storeys.summary(b, parts, failures) -> dict`;
  `storeys.room_rows(b) -> [row]` (rooms, stair, terraces, with `Floor`).

- [ ] **Step 1: Failing tests:**

```python
@pytest.mark.parametrize("house", demo.STOREYS, ids=[h[0] for h in demo.STOREYS])
def test_demo_storey_houses_plan_clean(house):
    b = plan_demo(house, seed=house[5])                      # helper: world splines per floor -> S.plan_building
    assert b is not None and not S.validate(b)
    assert len(b.floors) == expected_floors(house)           # 2, 2, 2, 3, 3, 2, 2
    assert sum(1 for f in b.floors for r in f.plan.rooms if r.type == "Master") == 1

def test_stair_is_aligned_on_every_floor(): ...             # the Stair room rect is b.stair.rect on every floor
def test_awkward_setbacks_plan_clean_or_drop_with_a_note(): ...   # Review Focus 1: L-shaped 2F, 2F 5 m wide, setback at the stair
def test_three_floors_on_a_small_house_drop_with_notes(): ... # Review Focus 5: 6 x 6 m, Floors 3 -> fewer floors, dropped notes
def test_deterministic(): ...                                # two runs, same seed -> same rooms, doors, places on every floor
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.**
- [ ] **Step 4: Run; measure** the seven demo houses' plan time (print) — Expected: PASS; ≤ 1.5 s each. If slower: ledger a ruling
  and lower K / the early stop (spec §6.2 values) until it holds.

### Task 9: Assembly — floors, slabs, stairs, terraces, ShowFloors

**Files:** Modify `assemble.py`, `stairs.py` (`parts`), `terrace.py` (`parts`), `storeys.py` (`parts`); Test `test_interior_storeys.py`,
`test_interior_stairs.py`

**Interfaces — Produces:**
- `A.house(..., params)`: `Level` (0), `StairRoom` (id or None): level 0 → foundation over `decompose(cells)` (identical to today's
  wings for a single floor); level ≥ 1 → a 30 cm `slab` (facade material) over `fp.wings` (the pieces: the stair room left open) and no
  floor / skirting in the stair room; `"stair"` passages without frames; `"terrace"` doors: frame + closed glass leaf, exterior wall
  thickness.
- `_Out.bar(p0, p1, t, mat, role)` — a sloped bar (pitch, yaw).
- `stairs.parts(stair, out, level, shown_above, top_shown, H, pal)` — flights from `level` to `level + 1` when that floor is shown
  (treads rise + 15 thick, landings 20 thick, wood), a handrail per flight, the U top floor's guard rail over `void`.
- `terrace.parts(terraces, out, pal)` — slab (30, facade), deck (2, `Floor_Deck`), railing 105 on the edges whose outside is not in the
  lower floor (posts ≤ 150 apart, top and mid rails).
- `storeys.parts(b, params, rng) -> [item]` — floors 0..S−1 (`ShowFloors` S, 0 = all, clamped), `WallCut` only on floor S−1.

- [ ] **Step 1: Failing tests:**

```python
def test_floors_stack_at_floor_height(): ...      # every part of floor k between k*H - 30 and k*H + 270 (+ furniture/rail heights)
def test_slab_leaves_the_stair_open(): ...        # no slab part over the stair room on floors >= 1; foundation covers it on floor 0
def test_stair_parts(): ...                       # 17 treads per flight pair inside the stair clear rect; stacked clearance >= 200
def test_terrace_railing_on_outer_edges_only(): ...
def test_show_floors_bounds(): ...                # ShowFloors 1: nothing above H; 5 on two floors: everything; WallCut on the top shown only
def test_walls_never_overlap_on_any_floor(): ...
def test_a_turned_building_is_the_same_building_turned(): ...   # Review Focus 2: yaw 30 / 90 / 217
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** + regression — PASS, digests unchanged.

### Task 10: Stage, graph and materials

**Files:** Modify `stages/i01_house.py`, `Content/Python/pyinterior_materials.py`, `program.py` (`FLOOR_MATERIALS` adds `Floor_Deck`);
Test `test_interior_stage.py`

**Interfaces — Produces:** PARAMS `Floors` (Int32 0), `ShowFloors` (Int32 0), `StairType` (String "Auto"); `run`: splines with z →
`storeys.levels` / `plan_building`; `None` → today's path on floor 0's spline (Summary adds `floors` 1 and `notes`); else
`storeys.parts` / `validate` / `summary` / `room_rows`; Rooms declare `Floor` (Int32) for both paths.

- [ ] **Step 1: Failing tests:**

```python
def test_stage_runs_a_two_storey_house():
    ins = inputs_two_floors()                         # two splines at z 0 and 300 over a 10 x 8 box
    out, _ = stage_api.execute(i01_house, ins, dict(stage_api.defaults(i01_house), Seed=1), None)
    s = out["Summary"][0][0].values
    rooms = out["Rooms"][0][0]
    assert s["floors"] == 2 and s["failures"] == 0 and set(rooms.attrs["Floor"]) == {0, 1}

def test_stage_odd_spline_sets(): ...                 # Review Focus 4: Floors 1 + two splines -> single-floor digest + note;
                                                      # a spline below the actor -> shifted note; two on one level -> note
def test_graph_description_has_the_new_params(): ...  # Floors, ShowFloors, StairType among IG.house().to_ir()["params"]
```

- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run the full suite** — PASS (1943 + new), digests unchanged.

### Task 11: Demo positions, driver, offline tools

**Files:** Modify `demo.py`, `Content/Python/pyinterior.py`, `Tools/pyinterior/plan.py`, `Tools/pyinterior/census.py`; Test
`test_interior_storeys.py`

**Interfaces — Produces:**
- `demo.storeys() -> [(name, outlines, loc, yaw, floors, stair_type, style, seed)]` — a second street south of the first (road along
  world X; 11–14 on its north side facing it, 15–17 on its south side); `demo.floor_points(outline, loc, yaw, k, H) -> world points`.
- `pyinterior.py`: `houses {"set": "storeys"}` (destroys and re-creates only houses tagged `PyInterior_Storeys`; one spline per given
  floor at z = loc z + k·H); `assign` covers both sets (`Floors`, `StairType` overrides for the storeys); `shape {"house", "floor"}`;
  `view {"house", "floors", "wallcut"}` (overrides + regenerate; shot in a later call); `read` adds `floors`, programs, `stair`,
  `terraces`, `dropped`; `status` lists splines per house; `site` paves the second street.
- `plan.py --storeys` (each demo house's floors side by side, the stair and terraces marked); `census.py --storeys` (two floors
  6–16 × 6–12 m step 100, three floors 5–8 × 9–14 m, setbacks 200 / 300 / 400 front, back and side; three seeds; failures, drops,
  max time).

- [ ] **Step 1: Failing tests:** `test_storey_demo_houses_sit_on_the_second_street` (no overlap with `demo.houses()` footprints, all
  in front of their street), `test_floor_points_are_raised` (z = loc z + k·H).
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** the tests; **run** `census.py --storeys` — Expected: 0 failures,
  drops listed, max time ≤ 1.5 s; `plan.py --storeys` — look at every sheet and fix rules that read wrong (back to Tasks 5–9 with a
  failing test each time).

### Task 12: Editor

- [ ] `pyinterior_materials.py` (adds `Floor_Deck`); `pyinterior.py build` (0 diffs) → `site` → `houses {"set": "storeys"}` →
  `assign` → `gen` → `read` — Expected: all 15 houses `pass_ok`, the 8 single-floor houses' instance counts unchanged
  (143, 237, 355, 540, 483, 490, 486, 604), no PCG warnings.
- [ ] Screenshots, one per call, each looked at: the second street; every storey house `view` floors 1 / 2 / 3 with walls down; a
  terrace; eye height on the ground floor towards the stair and on the 2F landing.
- [ ] Dynamic: House_11 `shape {"floor": 1, "size": [1000, 550]}` → a front terrace appears and every floor re-plans (read + shots);
  House_16 `Floors` 2 → 3 (assign + gen + read).
- [ ] Live edit: a notified edit of a 2F spline regenerates the house (probe with ALWAYS notify); adding a spline component and lifting
  it 300 cm — record whether it regenerates by itself.
- [ ] `save` (level saved generated; no probe or preview actors).

### Task 13: Docs and final checks

- [ ] `docs/pyinterior-guide.md`: chapter "多层" (rules tables, stair types, terraces, parameters, results, screenshots, limits);
  traps for what the editor taught; CLAUDE.md PyInterior paragraph; memory.
- [ ] Full suite + `census.py` (single) + `census.py --storeys` — record the numbers in the ledger.
