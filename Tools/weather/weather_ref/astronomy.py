"""Sun and moon (spec §6.1): the NOAA solar-position algorithm (after Meeus, Astronomical Algorithms) for a possibly
fractional day of the year, sunrise and sunset, the moon placed from its phase, and the rotation of a light that shines
away from a body. Angles are in degrees; trigonometry converts with DEG / RAD, never math.radians / math.degrees. The
plugin's WeatherAstronomy copies these formulas operation for operation. Pure."""
import collections
import math

DEG = math.pi / 180.0
RAD = 180.0 / math.pi

Sun = collections.namedtuple(
    "Sun", "elevation_deg azimuth_deg declination_deg eot_min right_ascension_deg hour_angle_deg "
           "ecliptic_longitude_deg obliquity_deg")
Moon = collections.namedtuple("Moon", "phase illumination elevation_deg azimuth_deg declination_deg")


def wrap(x, m):
    """x - m * floor(x / m): x brought into [0, m) for m > 0."""
    return x - m * math.floor(x / m)


def _clamp(x, lo, hi):
    return min(max(x, lo), hi)


def julian_day(year, month, day):
    """Julian day at 00:00 UTC of a Gregorian date (Meeus ch. 7)."""
    if month <= 2:
        year -= 1
        month += 12
    a = math.floor(year / 100)
    b = 2 - a + math.floor(a / 4)
    return math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + b - 1524.5


def date_jd(year, doy, tz):
    """Julian day of local noon of day `doy` (1 = 1 January, may be fractional) in zone `tz` (hours east of UTC). The
    compressed calendar moves the date continuously; the time of day enters only through the hour angle."""
    return julian_day(year, 1, 1) + (doy - 1) + 0.5 - tz / 24


def _elevation_azimuth(lat, decl, ha):
    """Elevation and azimuth (from north, clockwise) of a body at declination `decl` and hour angle `ha`."""
    el = math.asin(_clamp(math.sin(lat * DEG) * math.sin(decl * DEG)
                          + math.cos(lat * DEG) * math.cos(decl * DEG) * math.cos(ha * DEG), -1.0, 1.0)) * RAD
    az = wrap(math.atan2(math.sin(ha * DEG), math.cos(ha * DEG) * math.sin(lat * DEG)
                         - math.tan(decl * DEG) * math.cos(lat * DEG)) * RAD + 180, 360)
    return el, az


def sun(year, doy, local_hour, lat, lon, tz):
    """The sun at `local_hour` (zone time) of day `doy`, seen from `lat`, `lon` (east positive) in zone `tz`. The
    orbital elements, declination and equation of time are those of the day's local noon (date_jd)."""
    jd = date_jd(year, doy, tz)
    t = (jd - 2451545) / 36525

    l0 = wrap(280.46646 + t * (36000.76983 + t * 0.0003032), 360)
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    c = (math.sin(m * DEG) * (1.914602 - t * (0.004817 + 0.000014 * t))
         + math.sin(2 * m * DEG) * (0.019993 - 0.000101 * t) + math.sin(3 * m * DEG) * 0.000289)
    om = 125.04 - 1934.136 * t
    lam = l0 + c - 0.00569 - 0.00478 * math.sin(om * DEG)
    eps = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60 + 0.00256 * math.cos(om * DEG)

    decl = math.asin(math.sin(eps * DEG) * math.sin(lam * DEG)) * RAD
    tan_half = math.tan(eps / 2 * DEG)
    y = tan_half * tan_half
    eot = 4 * RAD * (y * math.sin(2 * l0 * DEG) - 2 * e * math.sin(m * DEG)
                     + 4 * e * y * math.sin(m * DEG) * math.cos(2 * l0 * DEG)
                     - 0.5 * y * y * math.sin(4 * l0 * DEG) - 1.25 * e * e * math.sin(2 * m * DEG))

    tst = wrap(local_hour * 60 + eot + 4 * lon - 60 * tz, 1440)
    ha = tst / 4 - 180
    ra = wrap(math.atan2(math.cos(eps * DEG) * math.sin(lam * DEG), math.cos(lam * DEG)) * RAD, 360)
    el, az = _elevation_azimuth(lat, decl, ha)
    return Sun(el, az, decl, eot, ra, ha, lam, eps)


def sunrise_sunset(year, doy, lat, lon, tz, zenith=90.833):
    """(sunrise, sunset, day length) in hours of zone time; the clamp gives polar day 24 h and polar night 0 h."""
    s = sun(year, doy, 12.0, lat, lon, tz)   # its declination and equation of time do not depend on the hour
    cos_h = _clamp(math.cos(zenith * DEG) / (math.cos(lat * DEG) * math.cos(s.declination_deg * DEG))
                   - math.tan(lat * DEG) * math.tan(s.declination_deg * DEG), -1.0, 1.0)
    h = math.acos(cos_h) * RAD
    noon = (720 - 4 * lon - s.eot_min + 60 * tz) / 60
    return noon - 4 * h / 60, noon + 4 * h / 60, 8 * h / 60


def moon(game_days, sun, lat, synodic_days, offset_days):
    """The moon at `game_days` of game time: its phase (0 new, 0.5 full) counts game days (`synodic_days` a cycle,
    shifted by `offset_days`), and it stands on the ecliptic 360 x phase degrees east of `sun` (the Sun of the same
    moment), seen from `lat`."""
    phase = wrap((game_days + offset_days) / synodic_days, 1)
    illumination = (1 - math.cos(2 * math.pi * phase)) / 2
    eps = sun.obliquity_deg
    lam_m = sun.ecliptic_longitude_deg + 360 * phase
    decl_m = math.asin(math.sin(eps * DEG) * math.sin(lam_m * DEG)) * RAD
    ra_m = wrap(math.atan2(math.cos(eps * DEG) * math.sin(lam_m * DEG), math.cos(lam_m * DEG)) * RAD, 360)
    ha_m = wrap(sun.hour_angle_deg + sun.right_ascension_deg - ra_m + 180, 360) - 180
    el, az = _elevation_azimuth(lat, decl_m, ha_m)
    return Moon(phase, illumination, el, az, decl_m)


def direction(el, az, north_yaw):
    """Unit vector towards a body at elevation `el` and azimuth `az`: world +X is north and +Y east, turned by
    `north_yaw`."""
    return (math.cos(el * DEG) * math.cos((az + north_yaw) * DEG),
            math.cos(el * DEG) * math.sin((az + north_yaw) * DEG), math.sin(el * DEG))


def light_rotation(el, az, north_yaw):
    """(pitch, yaw, roll) of a directional light that shines away from the body, along -direction(el, az, north_yaw)."""
    return -float(el), wrap(az + north_yaw + 180.0, 360), 0.0
