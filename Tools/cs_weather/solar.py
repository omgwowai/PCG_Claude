# solar.py -- sun position (NOAA / Meeus low-precision algorithm, ~0.01 deg) and the photometric helpers used to turn a
# reference photo's EXIF into scene parameters.
#
#   C:\Python314\python.exe Tools/cs_weather/solar.py 2019-06-21T12:00 --tz -5 --lat 41.88 --lon -87.63
#       -> elevation / azimuth (deg, azimuth clockwise from north), air mass, refraction
import argparse
import datetime as dt
import math


def _jd(t_utc):
    a = (14 - t_utc.month) // 12
    y = t_utc.year + 4800 - a
    m = t_utc.month + 12 * a - 3
    jdn = t_utc.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    frac = (t_utc.hour - 12) / 24.0 + t_utc.minute / 1440.0 + t_utc.second / 86400.0
    return jdn + frac


def sun_position(t_local, tz_hours, lat, lon, refraction=True):
    """Returns (elevation_deg, azimuth_deg_from_north_clockwise, declination_deg, equation_of_time_min)."""
    t_utc = t_local - dt.timedelta(hours=tz_hours)
    jc = (_jd(t_utc) - 2451545.0) / 36525.0
    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360.0
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    mr = math.radians(m)
    c = (math.sin(mr) * (1.914602 - jc * (0.004817 + 0.000014 * jc)) + math.sin(2 * mr) * (0.019993 - 0.000101 * jc)
         + math.sin(3 * mr) * 0.000289)
    true_long = l0 + c
    omega = 125.04 - 1934.136 * jc
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    eps0 = 23.0 + (26.0 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60.0) / 60.0
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))
    decl = math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(app_long))))
    y = math.tan(math.radians(eps / 2.0)) ** 2
    l0r = math.radians(l0)
    eot = 4.0 * math.degrees(y * math.sin(2 * l0r) - 2 * e * math.sin(mr) + 4 * e * y * math.sin(mr) * math.cos(2 * l0r)
                             - 0.5 * y * y * math.sin(4 * l0r) - 1.25 * e * e * math.sin(2 * mr))
    minutes = t_utc.hour * 60 + t_utc.minute + t_utc.second / 60.0
    tst = (minutes + eot + 4.0 * lon) % 1440.0
    ha = tst / 4.0 - 180.0
    if ha < -180:
        ha += 360
    latr, decr, har = math.radians(lat), math.radians(decl), math.radians(ha)
    cos_z = math.sin(latr) * math.sin(decr) + math.cos(latr) * math.cos(decr) * math.cos(har)
    zen = math.degrees(math.acos(max(-1.0, min(1.0, cos_z))))
    elev = 90.0 - zen
    az = math.degrees(math.atan2(math.sin(har), math.cos(har) * math.sin(latr) - math.tan(decr) * math.cos(latr))) + 180.0
    if refraction:
        elev += refraction_deg(elev)
    return elev, az % 360.0, decl, eot


def refraction_deg(elev):
    """Bennett-style refraction used by NOAA (degrees to add to the geometric elevation)."""
    if elev > 85.0:
        return 0.0
    te = math.tan(math.radians(elev))
    if elev > 5.0:
        r = 58.1 / te - 0.07 / te ** 3 + 0.000086 / te ** 5
    elif elev > -0.575:
        r = 1735.0 + elev * (-518.2 + elev * (103.4 + elev * (-12.79 + elev * 0.711)))
    else:
        r = -20.772 / te
    return r / 3600.0


def air_mass(elev):
    """Kasten & Young (1989) relative optical air mass; elev in degrees (apparent)."""
    if elev <= -2.0:
        return float("inf")
    return 1.0 / (math.sin(math.radians(elev)) + 0.50572 * (elev + 6.07995) ** -1.6364)


def ev100(fnumber, exposure_s, iso, bias=0.0):
    """Scene EV100 the camera exposed for: log2(N^2/t) - log2(ISO/100). The meter put the scene average there,
    minus the photographer's exposure compensation (bias), so the 'metered' scene EV100 is ev + bias."""
    return math.log2(fnumber * fnumber / exposure_s) - math.log2(iso / 100.0)


def koschmieder_visibility_m(beta_per_m, contrast=0.02):
    return -math.log(contrast) / beta_per_m


def ue_height_fog_density_for_visibility(v_m, contrast=0.02):
    """UE stores FogDensity/1000 per cm and uses exp2 transmittance (SceneCore.cpp 404, HeightFogCommon.ush 394):
    T = 2^(-FogDensity/1000 * L_cm) = 2^(-FogDensity/10 * L_m)  ->  FogDensity = 10 * log2(1/contrast) / V_m."""
    return 10.0 * math.log2(1.0 / contrast) / v_m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("time", help="local time, ISO 8601 (e.g. 2019-06-21T12:00)")
    ap.add_argument("--tz", type=float, required=True, help="UTC offset of the local time, hours")
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    a = ap.parse_args()
    t = dt.datetime.fromisoformat(a.time)
    elev, az, decl, eot = sun_position(t, a.tz, a.lat, a.lon)
    print("elevation %.2f deg  azimuth %.2f deg  declination %.2f  EoT %.2f min  air mass %.2f"
          % (elev, az, decl, eot, air_mass(elev)))


if __name__ == "__main__":
    main()
