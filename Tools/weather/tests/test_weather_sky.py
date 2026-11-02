from weather_ref import astronomy as A
from weather_ref import params as P
from weather_ref import sky as S

SKY = P.load()["sky"]


def test_neutral_is_identity():
    t = dict(S.NEUTRAL, sun_intensity=0.25, fog_density=2.0, white_temp_offset=500.0, cloud_cover=0.95)
    assert S.combine(t, S.NEUTRAL) == t
    assert S.lerp(t, S.NEUTRAL, 0.0) == t and S.lerp(t, S.NEUTRAL, 1.0) == S.NEUTRAL


def test_combine_multiplies_adds_and_keeps_the_type_cloud():
    c = S.combine(dict(S.NEUTRAL, saturation=0.8, exposure_bias=0.3, cloud_cover=0.9),
                  dict(S.NEUTRAL, saturation=1.1, exposure_bias=0.2, cloud_cover=0.5))
    assert abs(c["saturation"] - 0.88) < 1e-12 and abs(c["exposure_bias"] - 0.5) < 1e-12 and c["cloud_cover"] == 0.9


def test_noon_clear_against_overcast():
    clear = S.rig(78.4, 180.0, -30.0, 0.0, 0.5, dict(S.NEUTRAL, cloud_cover=0.05), SKY, 0.0)
    over = S.rig(78.4, 180.0, -30.0, 0.0, 0.5, dict(S.NEUTRAL, sun_intensity=0.25, cloud_cover=0.95), SKY, 0.0)
    assert abs(clear["sun_lux"] - 10.0 * (1 - 0.75 * 0.05)) < 1e-12
    assert over["sun_lux"] / clear["sun_lux"] < 0.1
    assert clear["star_intensity"] == 0.0 and clear["moon_lux"] == 0.0


def test_stars_fade_in_with_dusk_and_out_with_cloud():
    look = dict(S.NEUTRAL)
    assert S.rig(-3.0, 270.0, 10.0, 90.0, 1.0, look, SKY, 0.0)["star_intensity"] == 0.0
    assert abs(S.rig(-7.5, 270.0, 10.0, 90.0, 1.0, look, SKY, 0.0)["star_intensity"] - 0.5) < 1e-12
    assert S.rig(-40.0, 270.0, 10.0, 90.0, 1.0, look, SKY, 0.0)["star_intensity"] == 1.0
    cloudy = dict(look, cloud_cover=0.6)
    assert abs(S.rig(-40.0, 270.0, 10.0, 90.0, 1.0, cloudy, SKY, 0.0)["star_intensity"] - 0.4) < 1e-12


def test_moon_light_follows_illumination():
    full = S.rig(-40.0, 0.0, 40.0, 180.0, 1.0, S.NEUTRAL, SKY, 0.0)["moon_lux"]
    half = S.rig(-40.0, 0.0, 40.0, 180.0, 0.5, S.NEUTRAL, SKY, 0.0)["moon_lux"]
    assert abs(full - 0.3) < 1e-12 and abs(half - 0.15) < 1e-12


def test_rig_rotations_are_light_rotations():
    r = S.rig(30.0, 90.0, 10.0, 270.0, 1.0, S.NEUTRAL, SKY, 15.0)
    assert r["sun_rotation"] == A.light_rotation(30.0, 90.0, 15.0)
    assert r["moon_rotation"] == A.light_rotation(10.0, 270.0, 15.0)
