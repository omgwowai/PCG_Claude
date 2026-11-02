"""Looks and the sky rig (spec §1.5 parameter mapping, §6.1 moon, stars and grading). A look holds scales and offsets
on the base sky values of weather_params.json "sky", plus the cloud cover, in LOOK_FIELDS order: a weather type's look
and a season's combine into one, looks blend field by field, and rig turns the sun, the moon and a look into the values
of the sky actors. Angles are in degrees. The plugin's FWeatherLook (Lerp, Combine) and WeatherSky::Compute copy these
formulas operation for operation. Pure."""
from . import astronomy

LOOK_FIELDS = ("sun_intensity", "moon_intensity", "sky_light", "fog_density", "fog_height_falloff",
               "white_temp_offset", "saturation", "contrast", "exposure_bias", "cloud_cover")
ADDITIVE = {"white_temp_offset", "exposure_bias"}   # offsets; every other field but cloud_cover is a scale
NEUTRAL = {f: 0.0 if f in ADDITIVE or f == "cloud_cover" else 1.0 for f in LOOK_FIELDS}


def _clamp(x, lo, hi):
    return min(max(x, lo), hi)


def combine(type_look, season_look):
    """The look of a weather type in a season: scales multiply, ADDITIVE offsets add, and cloud_cover is the type's
    (a season look's cloud_cover is ignored)."""
    out = {}
    for f in LOOK_FIELDS:
        if f == "cloud_cover":
            out[f] = type_look[f]
        elif f in ADDITIVE:
            out[f] = type_look[f] + season_look[f]
        else:
            out[f] = type_look[f] * season_look[f]
    return out


def lerp(a, b, t):
    """Look `a` blended towards look `b` by `t`, every field a + (b - a) * t."""
    return {f: a[f] + (b[f] - a[f]) * t for f in LOOK_FIELDS}


def rig(sun_el, sun_az, moon_el, moon_az, moon_illum, look, sky, north_yaw):
    """The sky actors' values for the sun at `sun_el`, `sun_az` and the moon at `moon_el`, `moon_az` with illumination
    `moon_illum`, under `look` on the base values `sky` (the "sky" section), north turned by `north_yaw`. The cloud
    cover is the look's (M0 has no cloud field): it dims both lights and hides the stars. The stars fade in as the sun
    sinks from star_fade_start_deg to star_fade_range_deg below it; the moon lights only above the horizon."""
    cloud = look["cloud_cover"]
    dim = 1 - sky["cloud_dimming"] * cloud
    fade = _clamp((sky["star_fade_start_deg"] - sun_el) / sky["star_fade_range_deg"], 0.0, 1.0)
    return {
        "sun_lux": sky["sun_lux"] * look["sun_intensity"] * dim,
        "moon_lux": sky["moon_lux"] * look["moon_intensity"] * moon_illum * (1.0 if moon_el > 0 else 0.0) * dim,
        "sky_light_intensity": sky["sky_light_intensity"] * look["sky_light"],
        "fog_density": sky["fog_density"] * look["fog_density"],
        "fog_height_falloff": sky["fog_height_falloff"] * look["fog_height_falloff"],
        "white_temp": sky["white_temp_k"] + look["white_temp_offset"],
        "saturation": look["saturation"],
        "contrast": look["contrast"],
        "exposure_bias": look["exposure_bias"],
        "star_intensity": fade * (1 - cloud),
        "cloud_cover": cloud,
        "sun_rotation": astronomy.light_rotation(sun_el, sun_az, north_yaw),
        "moon_rotation": astronomy.light_rotation(moon_el, moon_az, north_yaw),
    }
