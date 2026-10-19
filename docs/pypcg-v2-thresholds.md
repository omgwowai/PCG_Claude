# V2 threshold changes

Every change to `Content/Python/pypcg/v2_thresholds.json` is listed here with its reason (spec 3, V2.4).
The defaults are the spec's: area and length ±10 %, counts ±25 %, per-mesh share ±10 percentage points,
deterministic steps ±1 %, over the median of 5 seeds; tags with fewer than 5 official items compare
structure, length and points only (ruling N10).

| Date | Stage | Key | Old | New | Why |
|---|---|---|---|---|---|
| 2026-10-16 | 6 | length | 0.10 | 0.20 | Districts draws its one split ratio per district from Python's own RNG (range [0.3, 0.7], the official `MaxSplitDistancFromCenter` + `AttributeRemap`), and the official graph's six draws happened to be low (mean 0.460): a ratio moves the split line and with it the 6 collector roads' total length. 150 seeds measured: relative error −7.8 % to +24.7 %, median +8.7 %, with no run below −8 %, i.e. an unbiased spread, not a systematic over-cut. Simulating the median of 5: 62 % of samples pass at 0.10, 90 % at 0.15, 99.5 % at 0.20, 100 % at 0.25. Numbers and method: `Tools/pypcg/data/s06_seed_study.json`. |
| 2026-10-16 | 6 | bbox_margin_cm | 20000 | 50000 | The same ratio decides where each district sits, so a district's bounding box can lag the official one by more than 200 m. Over 150 seeds the worst overshoots are Undividable 1120 m, Large 458 m, Medium 364 m, Small 370 m, CollectorRoads 153 m, localRoads 40 m (the tag that failed was Medium: 321–364 m). 500 m is the smallest round margin that clears the observed spread of the tags that appear in all 5 seeds. Per-tag overshoots: `Tools/pypcg/data/s06_seed_study.json`. |
| 2026-10-19 | 9 | tags.Small Courtyards count / area | 0.25 / 0.10 | 0.50 / 0.55 | Stage 9's plaza reservation (`Subgraph_3 Filter_RandomChoice`, one draw per lot) decides which lots grow a courtyard, and the official draw is a tail draw: 12 courtyards (25 914 m²) against 13–18 (median 16, 35 021 m²) over 99 Python seeds, i.e. below every seed. It is the draw and not the port: replaying the official reservation, V1's oracle gives exactly 12 courtyards and 25 914.03 m². Median of 5 over the study: 99 % within 0.50 (count) and 0.52 (area). |
| 2026-10-19 | 9 | tags.SmallDistrictsBldgFootprints count / area | 0.25 / 0.10 | 0.30 / 0.30 | The same draw removes those lots' footprints: official 77 / 58 382 m² at the 2nd / 9th percentile of the 99 seeds (median 92 / 67 895 m²). Median-of-5 p99: 0.30 / 0.25. With the official reservation the replay gives 75–85 footprints over four split seeds. |
| 2026-10-19 | 9 | tags.LargeDistrictsBldgFootprints area, tags.LargeBuildingSkirt area | 0.10 | 0.20, 0.25 | Reserving a large lot (up to 47 000 m²) removes its pads and skirt; the official draw spared them (pads at the 65th, skirt at the 91st percentile). Median-of-5 p99: 0.17, 0.22. The oracle holds the footprint total (every footprint tag + the skirt) to 0.3 m² on the official reservation. |
| 2026-10-19 | 9 | tags.UnderHighway area | 0.10 | 0.15 | Which lots under the highway are reserved: 79 860–113 235 m² over 99 seeds; median-of-5 p99 0.111. The oracle reproduces the official 103 665.4 m² to 0.01 m². |
| 2026-10-19 | 9 | tags.unbuildableLots count / area | 0.25 / 0.10 | 0.30 / 0.15 | Randomness plus a stated offset: the count spans 20–30 over the seeds (official 21, 1st percentile) because reserved lots never reach the size filters, AND the port's carve of the large lots' 10 m grammar bands leaves 8 zero-area (< 0.001 m²) slivers where the official run leaves 3 (Clipper quantisation at the bands' butt ends; `docs/pypcg/stages/s09.md` §3.3) -- with the official reservation the count is 26 vs 21 while every non-degenerate item matches to 0.05 m². Median-of-5 p99: 0.29 / 0.13. |
| 2026-10-19 | 9 | tags.reservedLots count / area / bbox_margin_cm | 0.25 / 0.10 / 20000 | 0.55 / 0.75 / 35000 | The reserved lots ARE the draw: 4–23 lots, 20 840–349 054 m² over 99 seeds (lots up to 47 000 m² each), anywhere in the city (bounds overshoot up to 318 m). Median-of-5 p99: 0.53 / 0.75. The kept share itself is held by V1 (within 0.10 of `PlazaReservationRatio`), and the oracle matches the official 15 lots item for item. |

**Stage 6: V2 is no longer where the placement evidence lives.** With the 500 m margin, `pypcg/v2.py`'s
bounding-box test can no longer see a systematic placement bias of 500 m or less — the signal is the size
of the noise. For a stage whose layout is a *new* draw this is the honest position, and V1 carries the
evidence instead: `pypcg/checks/s06.py`'s oracle replays the same cut, split, classify and grid with the
six official split ratios recovered from the official collector roads, and holds the resulting areas to
the official ones at 0.05 m² (the V1 run of 2026-10-16 passes with `failures: []`). Any later stage that
needs stage 6's placement checked had better compare the split ratios themselves, not the road lengths
and bounds that follow from them.

**Two known holes in the stage 6 rows, parked, no value changed:**

1. **A wrong grid spacing is only caught in combination.** At limit 0.20 the `localRoads` length check
   passes anything up to 27 880 m against the official 23 232 m. A grid spacing set wrong is still
   caught — `localRoads`' count (limit 0.25) moves with the spacing, and the oracle replays the grid
   with the official parameters — but by the count check and the oracle together, not by the length
   check alone.
2. **The missing-tag rule can fire on a rare draw.** `UndividableDistricts` is absent from 8 of the 150
   studied seeds (5.3 %): under the demo thresholds a district near the 77 499 m² limit can land just
   above it and be classed Small instead. `pypcg/v2.py` fails a verdict whose run lacks a contract tag,
   so an unlucky five-seed draw produces a spurious failure. A documented rarity exemption belongs in
   `v2.py`, not in this stage's thresholds; it is parked for the harness.

**Stage 9: per-tag rows.** `pypcg/v2.py` now reads `"tags": {tag: {key: value}}` inside a stage's entry
(test `test_a_tag_override_widens_that_tag_only`), so the six stage-9 rows widen only the tags whose
seed spread was measured; `Lots`, `Medium Courtyards`, `MediumDistrictsBldgFootprints` and
`UnbuildableFootprints` keep the defaults. As for stage 6, the precision lives in V1: the oracle replays
the official reservation and holds every draw-independent output to 0.05 m² per item and the
draw-redistributed totals to 0.1 %. Study and method: `Tools/pypcg/data/s09_seed_study.json`.
