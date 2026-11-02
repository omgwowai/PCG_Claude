"""Golden files for the C++ twins: weather_ref run on fixed cases and written as JSON to Tools/weather/golden, which
the plugin's automation tests SeasonalWeather.Calendar.Golden, Astronomy.Golden and Sky.Golden read back.
Deterministic: fixed case lists, sorted keys and float repr (it round-trips, so the C++ side reads the same doubles).
Rerun it after a change to weather_ref or weather_params.json; test_weather_golden.py fails while a file is stale."""
import itertools
import json
import os

from weather_ref import astronomy as A
from weather_ref import calendar as C
from weather_ref import params as P
from weather_ref import sky as S

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")

# calendar_cases.json: the *_DAYS lists are game days, written as game seconds (x DAY_S)
EVALUATE_DAYS = (0.0, 0.5, 3.25, 6.0, 6.5, 6.999, 7.0, 13.9, 20.5, 21.0, 24.75, 27.99, 28.0, 418.979, 2000.5)
SECONDS_FOR_DAYS = (0.0, 30.625, 400.0)
SECONDS_FOR_TARGETS = ((0, 0.0), (3, 12.5), (99, 25.0), (-1, -2.0))   # (day in season, hour), the last two clamped
WITH_HOUR_DAYS = (0.0, 3.2, 400.7)
WITH_HOUR_HOURS = (0.0, 9.75, 24.0, -1.0)

# astronomy_cases.json
YEAR = 2026
DOYS = (1.0, 42.0, 79.0, 120.5, 172.0, 200.25, 265.0, 307.0, 355.0, 365.0)
HOURS = (0.0, 6.5, 12.0, 18.25)
PLACES = ((35.0, 136.0, 9.0), (51.5074, -0.1278, 0.0), (-33.87, 151.21, 10.0), (75.0, 0.0, 0.0))   # (lat, lon, tz)
MOON_DAYS = (0.0, 3.7, 7.38, 14.765, 22.1, 29.53, 100.2)
MOON_SUNS = (0, 37, 81, 150)   # indices into the sun cases

# sky_cases.json
OVERCAST = dict(S.NEUTRAL, sun_intensity=0.25, sky_light=0.8, fog_density=2.0, white_temp_offset=500.0, saturation=0.8,
                cloud_cover=0.95)
WINTER = dict(S.NEUTRAL, saturation=0.85, exposure_bias=0.2, white_temp_offset=600.0)
LOOKS = (S.NEUTRAL, OVERCAST, WINTER)
LERP_TS = (0.0, 0.3, 1.0)
RIG_SUN_ELEVATIONS = (78.4, 10.0, -3.0, -7.5, -40.0)
RIG_SUN_AZIMUTH = 180.0
RIG_MOONS = ((40.0, 180.0, 1.0), (-5.0, 90.0, 0.5))   # (elevation, azimuth, illumination)
RIG_LOOKS = (S.NEUTRAL, OVERCAST)
RIG_NORTH_YAWS = (0.0, 15.0)


def calendar_cases():
    """evaluate at EVALUATE_DAYS, seconds_for at SECONDS_FOR_DAYS x season x target and with_hour at WITH_HOUR_DAYS x
    WITH_HOUR_HOURS, on the parameter file's calendar section, which the file carries as "params"."""
    cal = P.load()["calendar"]
    evaluate = []
    for day in EVALUATE_DAYS:
        seconds = day * C.DAY_S
        expect = C.evaluate(seconds, cal)._asdict()
        del expect["game_seconds"]
        evaluate.append({"game_seconds": seconds, "expect": expect})
    seconds_for = [{"current": days * C.DAY_S, "season": season, "day": day, "hour": hour,
                    "expect": C.seconds_for(cal, days * C.DAY_S, season, day, hour)}
                   for days, season, (day, hour)
                   in itertools.product(SECONDS_FOR_DAYS, P.SEASONS, SECONDS_FOR_TARGETS)]
    with_hour = [{"current": days * C.DAY_S, "hour": hour, "expect": C.with_hour(days * C.DAY_S, hour)}
                 for days, hour in itertools.product(WITH_HOUR_DAYS, WITH_HOUR_HOURS)]
    return {"params": cal, "evaluate": evaluate, "seconds_for": seconds_for, "with_hour": with_hour}


def astronomy_cases():
    """The sun at DOYS x HOURS x PLACES, sunrise and sunset at DOYS x PLACES (the parameter file's zenith), and the
    moon at MOON_DAYS x MOON_SUNS, from that sun case's Sun and latitude and the parameter file's synodic month and
    phase offset."""
    ast = P.load()["astronomy"]
    zenith, synodic, offset = ast["sunrise_zenith_deg"], ast["synodic_month_game_days"], ast["moon_phase_offset_days"]
    sun, suns = [], []
    for doy, hour, (lat, lon, tz) in itertools.product(DOYS, HOURS, PLACES):
        s = A.sun(YEAR, doy, hour, lat, lon, tz)
        suns.append(s)
        sun.append({"year": YEAR, "doy": doy, "hour": hour, "lat": lat, "lon": lon, "tz": tz, "expect": s._asdict()})
    sunrise = []
    for doy, (lat, lon, tz) in itertools.product(DOYS, PLACES):
        rise, sset, length = A.sunrise_sunset(YEAR, doy, lat, lon, tz, zenith)
        sunrise.append({"year": YEAR, "doy": doy, "lat": lat, "lon": lon, "tz": tz, "zenith": zenith,
                        "expect": {"sunrise": rise, "sunset": sset, "day_length": length}})
    moon = []
    for days, i in itertools.product(MOON_DAYS, MOON_SUNS):
        lat = sun[i]["lat"]
        moon.append({"game_days": days, "sun": i, "lat": lat, "synodic": synodic, "offset": offset,
                     "expect": A.moon(days, suns[i], lat, synodic, offset)._asdict()})
    return {"sun": sun, "sunrise": sunrise, "moon": moon}


def sky_cases():
    """combine on every ordered pair of LOOKS, lerp on the same pairs at every LERP_TS, and rig at RIG_SUN_ELEVATIONS x
    RIG_MOONS x RIG_LOOKS x RIG_NORTH_YAWS with the sun at RIG_SUN_AZIMUTH, on the parameter file's sky section."""
    sky = P.load()["sky"]
    pairs = list(itertools.product(LOOKS, LOOKS))
    combine = [{"type": type_look, "season": season_look, "expect": S.combine(type_look, season_look)}
               for type_look, season_look in pairs]
    lerp = [{"a": a, "b": b, "t": t, "expect": S.lerp(a, b, t)} for (a, b), t in itertools.product(pairs, LERP_TS)]
    rig = [{"sun_el": el, "sun_az": RIG_SUN_AZIMUTH, "moon_el": moon_el, "moon_az": moon_az, "moon_illum": illum,
            "look": look, "north_yaw": north,
            "expect": S.rig(el, RIG_SUN_AZIMUTH, moon_el, moon_az, illum, look, sky, north)}
           for el, (moon_el, moon_az, illum), look, north
           in itertools.product(RIG_SUN_ELEVATIONS, RIG_MOONS, RIG_LOOKS, RIG_NORTH_YAWS)]
    return {"sky": sky, "combine": combine, "lerp": lerp, "rig": rig}


_FILES = (("calendar_cases.json", calendar_cases), ("astronomy_cases.json", astronomy_cases),
          ("sky_cases.json", sky_cases))


def write(out_dir=GOLDEN_DIR):
    """Write the golden files into `out_dir`, which is created when missing, and return their paths. LF line ends and
    a final newline on every platform; NaN or infinity raises instead of writing invalid JSON."""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for name, build in _FILES:
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(build(), fh, indent=1, sort_keys=True, allow_nan=False)
            fh.write("\n")
        paths.append(path)
    return paths


if __name__ == "__main__":
    print("wrote %d golden files" % len(write()))
