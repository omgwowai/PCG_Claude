"""Per-stage acceptance for the town run (Task 27). The brief's tests, with rulings T27a, T27b, T27d applied."""
from pypcg import town_checks as C
from pypcg.profiles import town_layout as T

BOX = T.city_bbox(20000)
INSIDE = [[-10000, -10000, 0], [10000, 10000, 100]]


def rec(instances=10, tags=(), meshes=None, out=INSIDE, comp=INSIDE, components=None, generated=True, items=None):
    return {"generated": generated, "instances": {"total": instances, "per_mesh": meshes or {"/Game/Building/X": instances},
                                                 "components": components or {}},
            "items": items if items is not None else
            [{"tags": [t], "kind": "polygon", "area_m2": 100.0, "length_m": 0.0, "points": 0, "bbox": out} for t in tags],
            "output_bounds": out, "component_bounds": comp}


def test_bbox_outside_town_fails():
    # Review Focus 1: a stage that read the demo level's whole city shows up far outside the town.
    far = [[-120000, -90000, 0], [140000, 100000, 100]]
    v = C.check(10, rec(instances=1, comp=far), {"Lots": rec(tags=["Lots", "reservedLots"])}, BOX)
    assert v["status"] == "fail" and any("outside" in f for f in v["failures"])
    v = C.check(10, rec(instances=1, tags=["X"], out=far), {"Lots": rec(tags=["Lots", "reservedLots"])}, BOX)
    assert v["status"] == "fail" and any("outside" in f for f in v["failures"])
    assert C.check(10, rec(instances=1), {"Lots": rec(tags=["Lots", "reservedLots"])}, BOX)["status"] == "ok"


def test_required_tags_and_optional_tags():
    tags = ["ArteryRoads", "CollectorRoads", "localRoads", "SmallDistricts"]
    assert C.check(6, rec(instances=0, tags=tags), {}, BOX)["status"] == "ok"
    v = C.check(6, rec(instances=0, tags=tags[:3]), {}, BOX)
    assert v["status"] == "fail" and any("SmallDistricts" in f for f in v["failures"])


def test_bookkeeping_tags_do_not_count():
    v = C.check(6, rec(instances=0, tags=["Type:ArteryRoads", "CollectorRoads", "localRoads", "SmallDistricts"]), {}, BOX)
    assert v["status"] == "fail" and any("ArteryRoads" in f for f in v["failures"])


def test_upstream_must_be_generated_with_its_tags():
    v = C.check(7, rec(tags=["RoadFootprints", "ModifiedTerrain"]), {"Districts": rec(tags=["localRoads"])}, BOX)
    assert v["status"] == "fail" and any("Districts" in f for f in v["failures"])
    up = rec(tags=["localRoads", "CollectorRoads", "ArteryRoads"], generated=False)
    v = C.check(7, rec(tags=["RoadFootprints", "ModifiedTerrain"]), {"Districts": up}, BOX)
    assert v["status"] == "fail" and any("not generated" in f for f in v["failures"])


def test_zero_instances_fail_for_generating_stages():
    assert C.check(12, rec(instances=0), {"Buildings": rec(tags=["SmallRooftops"])}, BOX)["status"] == "fail"


def test_buildings_need_tl():
    up = {"Lots": rec(tags=["SmallDistrictsBldgFootprints"])}
    # (the brief's version omitted the SmallRooftops tag stage 11's own rule requires)
    assert C.check(11, rec(tags=["SmallRooftops"], meshes={"/Game/Building/CH/Kit_A": 5}), up, BOX)["status"] == "fail"
    assert C.check(11, rec(tags=["SmallRooftops"], meshes={"/Game/Building/TL/SM_TL_Wall": 5}), up, BOX)["status"] == "ok"


def test_terrain_unmeasured_is_not_a_failure():
    assert C.check(1, rec(instances=0), {}, BOX)["status"] == "unmeasured"
    flat = dict(rec(instances=0), terrain={"inner": [0.0, 120.0, -80.0], "outer": [4000.0, 2500.0]})
    assert C.check(1, flat, {}, BOX)["status"] == "ok"
    # T27b: beyond CityFlatness x the hills' range, the core is not flattened
    bumpy = dict(rec(instances=0), terrain={"inner": [0.0, 6000.0], "outer": [9000.0]})
    v = C.check(1, bumpy, {}, BOX)
    assert v["status"] == "fail" and any("not flat" in f for f in v["failures"])


def test_terrain_rule_accepts_the_official_core_spread():
    # T27b: the official graph's core spreads 4 254 cm (276 .. 4 530; s01.md 5.1) at CityFlatness 0.6,
    # HillsHeight 7 001; its outer ring sits ~5 000 cm below the core (s01.md 5.3).
    official = dict(rec(instances=0), terrain={"inner": [276.0, 4530.0, 2483.0], "outer": [-2162.7]},
                    params={"CityFlatness": 0.6000000238418579, "HillsHeight": 7001.0})
    assert C.check(1, official, {}, BOX)["status"] == "ok"
    assert 4254 < C.inner_spread_limit(official["params"]) < 0.6 * 7090 * 1.1


def test_terrain_rule_follows_city_flatness():
    # CityFlatness works against its tooltip (s01.md 5.2): 0 gives the flat city, so the limit is the
    # flat surface's own 2 cm; 1 gives the hills unchanged.
    flat_city = {"CityFlatness": 0.0, "HillsHeight": 7001.0}
    assert C.inner_spread_limit(flat_city) == C.FLAT_SURFACE_CM
    r = dict(rec(instances=0), terrain={"inner": [3000.0, 3500.0], "outer": [-2000.0]}, params=flat_city)
    assert C.check(1, r, {}, BOX)["status"] == "fail"
    r["params"] = {"CityFlatness": 1.0, "HillsHeight": 7001.0}
    assert C.check(1, r, {}, BOX)["status"] == "ok"


def test_terrain_needs_relief_outside():
    r = dict(rec(instances=0), terrain={"inner": [3000.0, 3100.0], "outer": [3200.0, 2900.0]})
    v = C.check(1, r, {}, BOX)
    assert v["status"] == "fail" and any("relief" in f for f in v["failures"])


def test_parkings_need_no_footprint_overrides():
    # The town cannot place a parking lot: Parkings consumes whatever LeftOverLots published (Task 25).
    assert C.check(14, rec(instances=3), {"ParkingFootprint": rec(tags=["reservedLots"])}, BOX)["status"] == "ok"


def test_parkings_zero_is_ok_only_when_nothing_was_published():
    v = C.check(14, rec(instances=0), {"ParkingFootprint": rec(items=[])}, BOX)
    assert v["status"] == "ok" and any("published no items" in n for n in v["notes"])
    assert C.check(14, rec(instances=0), {"ParkingFootprint": rec(tags=["reservedLots"])}, BOX)["status"] == "fail"
    assert C.check(14, rec(instances=0), {"ParkingFootprint": rec(items=[], generated=False)}, BOX)["status"] == "fail"


def test_outer_forest_accepts_zero_trees():
    # T27a: T_CloudNoise_4k is missing (traps.md 66), so the official graph places nothing either.
    v = C.check(18, rec(instances=0), {}, BOX)
    assert v["status"] == "ok" and any("66" in n for n in v["notes"])
    assert C.RULES[13]["min_instances"] == 1


def test_lake_component_is_the_terrain_write():
    # T27d: Saved/Reports/v2/s16/official.json instances.components carries SimpleWriteModifier.
    assert C.LAKE_COMPONENT == "SimpleWriteModifier"
    up = {"CentralParkFootprint": rec(tags=["X"]), "Roads": rec(tags=["RoadFootprints"])}
    assert C.check(16, rec(components={"SimpleWriteModifier": 1}), up, BOX)["status"] == "ok"
    v = C.check(16, rec(components={"DynamicMeshComponent": 2}), up, BOX)
    assert v["status"] == "fail" and any("SimpleWriteModifier" in f for f in v["failures"])


def test_plausibility_compares_densities_with_the_official_city():
    town = {"area_m2": 1000000.0, "buildings": 50.0, "road_m": 20000.0}
    official = {"area_m2": 1000000.0, "buildings": 50.0, "road_m": 20000.0}
    assert C.plausibility(town, official) == []
    assert C.plausibility(dict(town, buildings=200.0), official)          # 4x the official density
    assert C.plausibility(dict(town, road_m=3000.0), official)            # 0.15x


def test_no_unreal_import():
    import inspect
    assert "import unreal" not in inspect.getsource(C)
