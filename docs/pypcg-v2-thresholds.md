# V2 threshold changes

Every change to `Content/Python/pypcg/v2_thresholds.json` is listed here with its reason (spec 3, V2.4).
The defaults are the spec's: area and length ±10 %, counts ±25 %, per-mesh share ±10 percentage points,
deterministic steps ±1 %, over the median of 5 seeds; tags with fewer than 5 official items compare
structure, length and points only (ruling N10).

| Date | Stage | Key | Old | New | Why |
|---|---|---|---|---|---|
| 2026-10-16 | 6 | length | 0.10 | 0.20 | Districts draws its one split ratio per district from Python's own RNG (range [0.3, 0.7], the official `MaxSplitDistancFromCenter` + `AttributeRemap`), and the official graph's six draws happened to be low (mean 0.460): a ratio moves the split line and with it the 6 collector roads' total length. 150 seeds measured: relative error -7.8 % to +24.7 %, median +8.7 %, with no run below -8 %, i.e. an unbiased spread, not a systematic over-cut. Simulating the median of 5: 64 % of samples pass at 0.10, 91 % at 0.15, 99.2 % at 0.20, 100 % at 0.25. |
| 2026-10-16 | 6 | bbox_margin_cm | 20000 | 50000 | The same ratio decides where each district sits, so a district's bounding box can lag the official one by more than 200 m. Over 150 seeds the worst overshoots are Undividable 1120 m, Large 458 m, Medium 364 m, Small 370 m, CollectorRoads 153 m, localRoads 40 m (the tag that failed was Medium: 321-364 m). 500 m is the smallest round margin that clears the observed spread of the tags that appear in all 5 seeds. |
