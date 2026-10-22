"""Per-stage acceptance for the town run (spec 5). No unreal import.

Rulings applied over the Task 27 brief (ledger T27a-e):
  T27a  stage 18 places 0 trees: T_CloudNoise_4k is missing from the project (traps.md 66), so the official
        graph and the port both place nothing. Its rule accepts 0 instances and notes trap 66.
  T27b  stage 1's "city core flat within 500 cm" is false even for the official graph (docs/pypcg/stages/
        s01.md section 5.1: 4 254 cm). `final = hills + (flat - hills) * (1 - CityFlatness)`, so the core
        keeps CityFlatness of the hills' range; the bound below is that, with the hills' range taken as
        HillsHeight (official: range 7 090 cm for HillsHeight 7 001) times a slack.
  T27f  stage 8's box is the union of the city box and the town highway splines' own extent, each plus
        200 m: the layout runs the highway pair past the city on purpose (test_highways_cut_the_north_east_
        corner_30_m_apart); a stage that read the demo's whole city (~-120 000..140 000) still fails.
  T27i  stage 11 requires a TL mesh only when it published MediumRooftops: TL is one of ~20 styles of the
        Medium list only (the Small and Large lists carry none), so the rule records TL present / absent as a
        note and fails only when Medium buildings exist and none of them is TL.
  T27d  the lake bed is written by Write_MeshTerrain as a SimpleWriteModifier component (s16.md section 0;
        Saved/Reports/v2/s16/official.json instances.components: SimpleWriteModifier 1).
"""
from pypcg.profiles import town_layout

LAKE_COMPONENT = "SimpleWriteModifier"     # stage 16's official census (T27d)

RULES = {
    1: {"terrain": True},
    2: {"min_instances": 1},
    3: {"min_instances": 1},
    4: {"data": True, "bbox": True},
    5: {"data": True, "bbox": True},
    6: {"tags": ["ArteryRoads", "CollectorRoads", "localRoads", "SmallDistricts"], "bbox": True},
    7: {"tags": ["RoadFootprints", "ModifiedTerrain"], "min_instances": 1, "bbox": True,
        "upstream": {"Districts": ["localRoads", "CollectorRoads", "ArteryRoads"]}},
    8: {"tags": ["Highway"], "min_instances": 1, "bbox": True, "bbox_splines": ["HighWay_2", "HighWay_3"],
        "upstream": {"Roads": ["RoadFootprints"]}},
    9: {"tags": ["Lots", "reservedLots", "SmallDistrictsBldgFootprints", "UnderHighway"], "bbox": True,
        "upstream": {"Districts": ["SmallDistricts"], "Roads": ["RoadFootprints"], "Highways": ["Highway"]}},
    10: {"min_instances": 1, "bbox": True, "upstream": {"Lots": ["Lots", "reservedLots"]}},
    11: {"min_instances": 1, "bbox": True, "meshes_any_if_tag": {"MediumRooftops": ["/Game/Building/TL/"]},
         "tags": ["SmallRooftops"], "upstream": {"Lots": ["SmallDistrictsBldgFootprints"]}},
    12: {"min_instances": 1, "bbox": True, "upstream": {"Buildings": ["SmallRooftops"]}},
    13: {"min_instances": 1, "bbox": True, "upstream": {"Lots": ["reservedLots"]}},
    # Parkings consumes every item LeftOverLots publishes (Task 25): with none published, 0 is legitimate.
    14: {"min_instances": 1, "bbox": True, "upstream": {"ParkingFootprint": []},
         "zero_ok_without_upstream_items": "ParkingFootprint"},
    15: {"min_instances": 1, "bbox": True, "meshes_all": ["CHC", "CHA", "CHJ"], "upstream": {"MainTower": []}},
    16: {"min_instances": 1, "bbox": True, "components_any": [LAKE_COMPONENT],
         "upstream": {"CentralParkFootprint": [], "Roads": []}},
    17: {"min_instances": 1},
    18: {"min_instances": 0, "note": "0 trees expected: T_CloudNoise_4k is missing (traps.md 66, ruling T27a)"},
}

# Stage 1 (T27b). The official demo values, used when the record carries no override.
CITY_FLATNESS_DEFAULT = 0.6000000238418579
HILLS_HEIGHT_DEFAULT = 7001.0
HILLS_RANGE_SLACK = 1.05   # official hills range / HillsHeight = 7 090 / 7 001 = 1.013
FLAT_SURFACE_CM = 2.0      # the flat surface lies within 2 cm of the city plane (s01.md 5.1)
RELIEF_OUTER_CM = 1000     # the outer ring must differ from the core by at least this (s01.md 5.3: holds)
PLAUSIBLE_MIN, PLAUSIBLE_MAX = 0.5, 2.0    # town density / official density (spec 5.2)


def inner_spread_limit(params=None):
    """The most the city core's heights may spread: CityFlatness x the hills' range, plus the flat surface's
    own 2 cm (s01.md 5.1). 0.6 x 7 001 x 1.05 + 2 = 4 412.6 cm on the demo's values (official: 4 254)."""
    params = params or {}
    flatness = float(params.get("CityFlatness", CITY_FLATNESS_DEFAULT))
    hills = float(params.get("HillsHeight", HILLS_HEIGHT_DEFAULT))
    return max(0.0, flatness) * abs(hills) * HILLS_RANGE_SLACK + FLAT_SURFACE_CM


BBOX_MARGIN_CM = 20000    # the +200 m every bbox rule allows


def widened_box(town_bbox, spline_names, margin_cm=BBOX_MARGIN_CM):
    """T27f: the town box grown to cover the named layout splines (plus the margin)."""
    pts = [p for n in spline_names for p in town_layout.SPLINES[n]["points"]]
    if not pts:
        return town_bbox
    lo = [min([town_bbox[0][i]] + [p[i] - margin_cm for p in pts]) for i in range(2)]
    hi = [max([town_bbox[1][i]] + [p[i] + margin_cm for p in pts]) for i in range(2)]
    return [lo + list(town_bbox[0][2:]), hi + list(town_bbox[1][2:])]


def _inside(box, town):
    return all(town[0][i] <= box[0][i] and box[1][i] <= town[1][i] for i in range(2))


def _tags(rec):
    return {t for it in (rec or {}).get("items", []) for t in it["tags"] if ":" not in t}


def _terrain(rec):
    t = rec.get("terrain")
    if not t or not t.get("inner") or not t.get("outer"):
        return {"status": "unmeasured", "failures": [], "notes": ["terrain heights not measurable; see the screenshot"]}
    inner, outer = t["inner"], t["outer"]
    failures, notes = [], []
    mean = sum(inner) / len(inner)
    spread, limit = max(inner) - min(inner), inner_spread_limit(rec.get("params"))
    notes.append("core spread %.0f cm, limit %.0f cm (CityFlatness x hills range, T27b)" % (spread, limit))
    if spread > limit:
        failures.append("city core not flat enough: spread %.0f cm > %.0f cm" % (spread, limit))
    relief = max(abs(z - mean) for z in outer)
    notes.append("outer relief %.0f cm from the core mean %.0f cm" % (relief, mean))
    if relief < RELIEF_OUTER_CM:
        failures.append("no relief outside the city")
    return {"status": "fail" if failures else "ok", "failures": failures, "notes": notes}


def check(stage, rec, upstream, town_bbox):
    rule = RULES[stage]
    if rule.get("terrain"):
        return _terrain(rec)
    failures, notes = [], []
    if rule.get("note"):
        notes.append(rule["note"])
    if not rec.get("generated"):
        failures.append("volume not generated")
    tags = _tags(rec)
    for tag in rule.get("tags", []):
        if tag not in tags:
            failures.append("missing output tag %s" % tag)
    if rule.get("data") and not rec.get("items"):
        failures.append("no output data")
    total = rec.get("instances", {}).get("total", 0)
    want = rule.get("min_instances", 0)
    if total < want:
        role = rule.get("zero_ok_without_upstream_items")
        if role and total == 0 and (upstream.get(role) or {}).get("generated") and not upstream[role].get("items"):
            notes.append("0 instances: upstream %s published no items" % role)
        else:
            failures.append("instances %d < %d" % (total, want))
    meshes = rec.get("instances", {}).get("per_mesh", {})
    if rule.get("meshes_any") and not any(any(s in m for m in meshes) for s in rule["meshes_any"]):
        failures.append("no mesh matching %s" % rule["meshes_any"])
    for tag, subs in rule.get("meshes_any_if_tag", {}).items():
        found = any(any(s in m for m in meshes) for s in subs)
        notes.append("%s %s (%s %s)" % (subs, "present" if found else "absent", tag,
                                         "published" if tag in tags else "not published"))
        if tag in tags and not found:
            failures.append("no mesh matching %s although %s were published" % (subs, tag))
    for s in rule.get("meshes_all", []):
        if not any(s in m for m in meshes):
            failures.append("no mesh matching %s" % s)
    if rule.get("components_any") and not any(c in rec.get("instances", {}).get("components", {})
                                              for c in rule["components_any"]):
        failures.append("no component of class %s" % rule["components_any"])
    if rule.get("bbox"):
        if rule.get("bbox_splines"):
            town_bbox = widened_box(town_bbox, rule["bbox_splines"])
        for it in rec.get("items", []):
            if it["bbox"] and not _inside(it["bbox"], town_bbox):
                failures.append("output %s outside the town (+200 m): %s" % (it["tags"], it["bbox"]))
                break
        comp = rec.get("component_bounds")
        if comp and not _inside(comp, town_bbox):
            failures.append("instances outside the town (+200 m): %s" % (comp,))
    for role, want_tags in rule.get("upstream", {}).items():
        up = upstream.get(role)
        if up is None or not up.get("generated"):
            failures.append("upstream %s not generated" % role)
            continue
        missing = [t for t in want_tags if t not in _tags(up)]
        if missing:
            failures.append("upstream %s lacks tags %s" % (role, missing))
    return {"status": "fail" if failures else "ok", "failures": failures, "notes": notes}


def plausibility(town, official):
    """spec 5.2: the town's building and road densities must sit within [0.5x, 2x] of the official
    city's (both from V2 records: buildings per km2, road metres per km2)."""
    out = []
    if town["area_m2"] <= 0:                       # stage 6 produced nothing: no density to compare (review M3)
        return ["town area is %s m2 (stage 6 published no district); densities cannot be compared"
                % town["area_m2"]]
    if official["area_m2"] <= 0:
        return ["official area is %s m2 (no stage-6 V2 record); densities cannot be compared"
                % official["area_m2"]]
    for what, key in (("buildings per km2", "buildings"), ("road metres per km2", "road_m")):
        t, o = town[key] / (town["area_m2"] / 1e6), official[key] / (official["area_m2"] / 1e6)
        if not o:
            continue
        ratio = t / o
        if not PLAUSIBLE_MIN <= ratio <= PLAUSIBLE_MAX:
            out.append("%s: town %.1f vs official %.1f (%.2fx, allowed %.1f-%.1f)"
                       % (what, t, o, ratio, PLAUSIBLE_MIN, PLAUSIBLE_MAX))
    return out
