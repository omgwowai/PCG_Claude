import copy

from weather_ref import params as P

FIELDS_OF_SPEC_1_3 = {"atmos_volume", "coarse_wind", "ground_a", "ground_b", "near_wind", "near_ground_height", "gust_map",
                      "far_weather", "surface_state", "canopy_state", "snow_compression", "rain_depth"}


def test_params_match_schema():
    assert P.problems(P.load(), P.schema()) == []


def test_flat_keys_cover_every_leaf_once():
    keys = P.flat_keys(P.schema())
    assert len(keys) == len(set(keys)) == 33
    assert "calendar.real_seconds_per_game_day" in keys and "fields" in keys and "override_defaults.cloud_cover" in keys


def test_missing_wrong_and_extra_keys_are_reported():
    bad = copy.deepcopy(P.load())
    del bad["calendar"]["base_year"]
    bad["sky"]["sun_lux"] = "bright"
    bad["extra"] = 1
    found = P.problems(bad, P.schema())
    assert "missing calendar.base_year" in found
    assert "sky.sun_lux is not a number" in found
    assert "unexpected section extra" in found


def test_every_field_of_spec_1_3_is_declared():
    assert set(P.load()["fields"]) == FIELDS_OF_SPEC_1_3


def test_field_problems_catch_bad_descriptors():
    both = {"dims": 2, "format": "rgba16f", "size": [8, 8], "cell_m": 1.0, "channels": list("abcd")}
    assert P.field_problems("x", both) == ["x: give exactly one of size and cell_m"]
    volume_by_cell = {"dims": 3, "format": "r16f", "cell_m": 2.0, "channels": ["h"]}
    assert P.field_problems("y", volume_by_cell) == ["y: cell_m needs dims 2 and a positive number"]
    wrong_channels = {"dims": 2, "format": "r32f", "size": [4, 4], "channels": ["a", "b"]}
    assert P.field_problems("z", wrong_channels) == ["z: 1 channel names expected"]


def test_field_size_rounds_level_fields_up_to_multiples_of_eight():
    f = P.load()["fields"]
    assert P.field_size(f["atmos_volume"], 300.0) == (128, 128, 32)
    assert P.field_size(f["surface_state"], 300.0) == (304, 304)
    assert P.field_size(f["canopy_state"], 300.0) == (80, 80)
    assert P.field_size(f["surface_state"], 2048.0) == (2048, 2048)
    assert P.field_size(f["gust_map"], 2.0) == (8, 8)
