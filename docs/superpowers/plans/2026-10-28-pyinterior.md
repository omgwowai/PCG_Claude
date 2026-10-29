# PyInterior Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rule-driven PCG interior generation for a life-sim house: a footprint spline on a house actor becomes rooms, doors,
windows and furniture, re-planned whenever the footprint changes; verified in a new level `/Game/PyPCG/L_PyInterior`.

**Architecture:** Pure-Python rules in `Content/Python/pypcg/interior/` (footprint → program → layout → doors → windows → furnish →
assemble → checks), one stage module `pypcg/stages/i01_house.py` running in a Python Data Processor node of the generated graph
`/Game/PyPCG/Interior/PCGI_House`, native Static Mesh Spawner for the parts; editor driver `Content/Python/pyinterior.py`.

**Tech Stack:** UE 5.8 PCG + PCGPythonInterop, the project's `pypcg` DSL / host / convert, pytest on system Python 3.14, PIL for
offline plans.

**Spec:** `docs/superpowers/specs/2026-10-28-pyinterior-design.md`

**Rulings (planner = executor, /goal autonomous mode):**
- R1: the plan pins interfaces and tests; implementation code is written directly in the files test-first (writing it twice would
  double the work without a handoff to justify it). Cost if wrong: an interface drifts — mitigated by each task's Interfaces block.
- R2: no commit steps — the user's standing rule is "commit only when asked".
- R3: execution method Native (superpowers:executing-plans): the tasks share one evolving data model (`Rect`, `Room`, `Door`, …);
  one context holding it is cheaper than re-briefing subagents per task.

## Global Constraints

- `pypcg/interior/*` and `stages/i01_house.py` never import `unreal`; all units cm; local frame per spec §4 (front faces −y).
- Suite stays green: `C:\Python314\python.exe -m pytest Tools/pypcg/tests -q` (baseline 1027 passed, 18 skipped) plus the new tests.
- Graph assets are generated from `.py` (`build_slim`, 0 diffs); never hand-edited.
- Never save probe / preview actors; never kill the PCG_Codex editor (command line contains `E:/PCG_Codex/PCG_Codex.uproject`).
- `Content/StarterContent/` is copied by `Tools/pyinterior/starter_closure.py` and gitignored.
- Editor calls: one phase per call, long ones `{"defer": true}`; screenshots with throttle off (traps 88, 96).

## Review Focus

1. Footprints right at a program band edge (34 / 58 / 88 / 130 m²) and thin wings near `MIN_WING`: the downgrade path must still
   give every room its minimum size — test sweep includes band edges and 250–300 cm wings.
2. Very elongated footprints (aspect ≥ 3) and U shapes: every room reachable without passing through a bedroom or bathroom.
3. Rotated houses (yaw 30°, 90°, 217°): world transforms of every part follow the actor; the front door sits on the side the actor faces.
4. Rooms too small for a required item: the item is reported missing, never placed overlapping — tests assert zero overlaps on the
   whole sweep, including deliberately tight rooms.
5. Determinism: same footprint + seed → identical instances; another seed → a valid but different furnishing.

---

### Task 1: Footprint (`interior/footprint.py`, `interior/__init__.py`)

**Interfaces — Produces:**
- `Rect(x0, y0, x1, y1)` frozen dataclass: `w`, `h`, `area`, `cx`, `cy`, `overlaps(o)`, `contains(x, y)`, `shrink(l, b, r, t)`,
  `shared(o) -> (axis, c, a0, a1) | None` (shared edge: axis "x" = vertical line x = c from y a0..a1, "y" = horizontal).
- `Footprint` dataclass: `poly` (CCW local vertices), `cells` (set of (i, j)), `grid`, `wings` (list[Rect]), `origin` (world xyz),
  `yaw` (deg), `area_m2`, `front` (list of (x0, x1, y) exterior segments facing −y), `to_world(x, y, z=0) -> (X, Y, Z)`,
  `yaw_world(local_yaw) -> deg`, `exterior(seg) -> bool` helpers via `edges()` (list of (p, q) CCW).
- `build(points_world, origin, yaw_deg, grid=50.0, min_wing=250.0) -> Footprint | None`.

- [ ] Tests `Tools/pypcg/tests/test_interior_footprint.py`: rectangle 1000 × 800 → 4 vertices, 1 wing, area 80 m²; the same
  rectangle rotated 30° and given with yaw 30° → identical local footprint; L shape → 2 wings, union of wings == cells, no
  overlaps, every wing side ≥ 250; U shape → 3 wings; noisy points (± 12 cm) snap to the grid; a 300 × 300 square → None;
  `to_world` round-trips; `front` lies on y = min of the polygon's −y facing edges.
- [ ] Implement; run the test file; then the whole suite.

### Task 2: Program rules (`interior/program.py`)

**Produces:** `ROOMS` {type: RoomType(zone, min_short, min_long, floor, window, recipe, weight_default)}, `PROGRAMS` (ordered list of
`Program(name, min_area_m2, public, private)` with room entries `(type, weight, optional)`), `ACCESS` {type: (parent types…)},
`STYLES` {name: palettes}, `choose(area_m2) -> Program`, `fallbacks(program) -> iterator[Program]` (drop optional rooms in order,
then the next lower program, ending at Studio).

- [ ] Tests `test_interior_program.py`: band edges pick the right program; areas increasing → program index non-decreasing;
  fallback chain ends in Studio and never grows; every room type used by a program is in `ROOMS` and `ACCESS`; every style has
  every palette key.
- [ ] Implement; run.

### Task 3: Layout (`interior/layout.py`)

**Consumes:** Task 1 `Footprint`, `Rect`; Task 2 `Program`, `ROOMS`.
**Produces:** `Room(id, type, rect, zone, block)`; `Plan(footprint, program, rooms, blocks, front_room, entry, failures)`;
`plan(fp, program, rng) -> Plan` (tries `fallbacks` until a layout passes `valid`); `valid(plan) -> list[str]`.

- [ ] Tests `test_interior_layout.py` over a sweep (rectangles 500..2000 × 450..1400 step 150, aspect up to 3.5; L / T / U shapes;
  seeds 1..3): rooms tile the footprint (sum of areas == footprint area, pairwise no overlap, each inside a wing); each room meets
  its type's minimum (short ≥ min_short − wall allowance); the program never needs more rooms than fit; bigger footprints never get a
  lower program; corridor appears when the private zone needs one (≥ 3 private rooms in a zone deeper than a column); determinism.
- [ ] Implement (public / private templates, multi-wing allocation, scoring, fallbacks); run.

### Task 4: Doors (`interior/doors.py`)

**Produces:** `Door(a, b, axis, c, s0, s1, kind)` — rooms a (parent) → b, on the shared line `axis`/`c` spanning s0..s1, kind
"front" | "door" | "opening" | "doorway"; `connect(plan, rng) -> (doors, failures)`; `swing(door, room) -> Rect` (clear zone).

- [ ] Tests `test_interior_doors.py` on the sweep: BFS from the front door reaches every room; exactly one parent per room; no
  bedroom is entered from a bath / kitchen / bedroom; front door on an exterior −y segment of the entry room; every door within its
  shared segment with ≥ 15 cm margins; public-public links are openings.
- [ ] Implement; run.

### Task 5: Windows (`interior/openings.py`)

**Produces:** `Window(room, axis, c, s0, s1, sill, height, kind, outward)`; `windows(plan, doors) -> list[Window]`.

- [ ] Tests `test_interior_openings.py`: windows only on exterior edges; ≥ 40 cm from corners and from doors; every Living / Bedroom /
  Master / Kitchen / Dining / Study with an exterior wall ≥ 100 cm gets ≥ 1 window; bath windows are high (sill 150).
- [ ] Implement with `world.grammar.solve`; run.

### Task 6: Catalog and furnishing (`interior/catalog.py`, `interior/furnish.py`)

**Produces:** `Item(name, w, d, h, kind, place, front, side, tall, parts, mesh)`; `ITEMS`; `RECIPES` {room type: [groups]};
`Placement(item, room, x, y, yaw, w, d, h)`; `furnish(plan, doors, windows, rng) -> (placements, failures)`;
`clear_rect(room, plan) -> Rect` (room minus wall thickness).

- [ ] Tests `test_interior_furnish.py` on the sweep: required items present (bed per bedroom / master, fridge + sink + stove per kitchen
  or main, toilet + sink + bath-or-shower per bath, sofa per living / main); zero pairwise overlaps; every placement inside its room's
  clear rect; no placement intersects a door swing zone; tall items never in front of a window; kitchen run solved by the grammar.
- [ ] Implement; run.

### Task 7: Assembly (`interior/assemble.py`)

**Produces:** `house(fp, plan, doors, windows, placements, params, style_rng) -> list[dict(loc, rot, scale, mesh, mat, role)]`;
helpers `wall_band(poly, t) -> list[Rect]`, `interior_segments(plan) -> list[seg]`.

- [ ] Tests `test_interior_assemble.py`: `wall_band` rects pairwise disjoint, area == area(poly) − area(inset); interior wall pieces never
  overlap exterior pieces or each other; no wall piece occupies a door / window opening; floors one per room; determinism; world
  transform: a rotated house's parts are the unrotated ones rotated about the origin.
- [ ] Implement; run.

### Task 8: Checks, stage module, graph (`interior/checks.py`, `stages/i01_house.py`, `interior/graphs.py`, `interior/demo.py`)

**Produces:** `checks.validate(...) -> failures`, `checks.summary(...) -> dict`; stage `INPUTS = {"Footprint": "spline", "Volume": "points"}`,
`OUTPUTS = ("Parts", "Rooms", "Summary")`, `PARAMS` (WallHeight, WallCut, Grid, Style, Furnish, Mirror, Density); `graphs.house()`;
`demo.HOUSES`, `demo.SHAPES`.

- [ ] Tests `test_interior_stage.py`: `stage_api.execute(i01_house, inputs, params)` on each demo house → Parts non-empty, Rooms one
  point per room, Summary failures 0; the graph description wires every Python input pin (trap 80).
- [ ] Implement; run the full suite.

### Task 9: Offline plan renderer (`Tools/pyinterior/plan.py`)

- [ ] `python Tools/pyinterior/plan.py --demo` → `Saved/Reports/pyinterior_plan_<house>.png`; `--sweep` → one sheet of footprints from
  5 × 5 to 20 × 14 m. Look at the images; fix rules that produce bad plans (back to Tasks 3–6 with a failing test each time).

### Task 10: Editor assets

- [ ] `Tools/pyinterior/starter_closure.py [--copy]`; `.gitignore` `/Content/StarterContent/`; asset registry scan.
- [ ] `pyinterior_materials.py`: `M_PyInt_Color`, `M_PyInt_WorldTex` + child instances (NEVER notify, one recompile, trap 100).
- [ ] Probe StarterContent mesh bounds (`pyinterior_probe_meshes.py`) → catalog scale factors.

### Task 11: Editor graph, level, houses

- [ ] `pyinterior.py build` (0 diffs) → `level` (Template_Default; L_PyWorld reset first, globals purged) → `houses` → `gen` → `read`.
- [ ] Every house `pass_ok`; PCG log clean.

### Task 12: Screenshots and the dynamic test

- [ ] `shot` top / overview / cutaway / interior; look at every image.
- [ ] `shape` sequence on one house (8 × 6.5 → 10.5 × 8 → 13 × 9 → L) with `read` after each; screenshots.
- [ ] `save` (defer) without probes.

### Task 13: Docs

- [ ] `docs/pyinterior-guide.md` (rules tables, how to run, results, screenshots, limits); trap rows for what the editor taught;
  CLAUDE.md paragraph; memory.
