import math

from weather_ref import astronomy as A

SYN = 29.530588853


def test_julian_day_epoch():
    assert A.julian_day(2000, 1, 1) == 2451544.5
    assert A.julian_day(1999, 1, 1) == 2451179.5


def test_solstice_and_equinox_declination():
    assert abs(A.sun(2026, 172, 12.0, 0.0, 0.0, 0.0).declination_deg - 23.44) < 0.02
    assert abs(A.sun(2026, 355, 12.0, 0.0, 0.0, 0.0).declination_deg + 23.44) < 0.02
    assert abs(A.sun(2026, 79, 12.0, 0.0, 0.0, 0.0).declination_deg) < 0.1


def test_equation_of_time_extremes():
    feb = min(A.sun(2026, d, 12.0, 0.0, 0.0, 0.0).eot_min for d in range(30, 60))
    nov = max(A.sun(2026, d, 12.0, 0.0, 0.0, 0.0).eot_min for d in range(290, 330))
    assert abs(feb + 14.2) < 0.3 and abs(nov - 16.4) < 0.3


def test_published_sunrise_and_sunset():
    # London 21 Jun 04:43-21:21 BST, 21 Dec 08:04-15:53 GMT; Tokyo 21 Jun 04:25-19:00, 21 Dec 06:47-16:32 JST
    cases = [(51.5074, -0.1278, 1.0, 172, 4 + 43 / 60, 21 + 21 / 60), (51.5074, -0.1278, 0.0, 355, 8 + 4 / 60, 15 + 53 / 60),
             (35.6895, 139.6917, 9.0, 172, 4 + 25 / 60, 19.0), (35.6895, 139.6917, 9.0, 355, 6 + 47 / 60, 16 + 32 / 60)]
    for lat, lon, tz, doy, rise, sset in cases:
        r, s, _ = A.sunrise_sunset(2026, doy, lat, lon, tz)
        assert abs(r - rise) * 60 < 3.0 and abs(s - sset) * 60 < 3.0, (lat, doy, r, s)


def test_day_length_at_35_north_matches_the_spec():
    assert abs(A.sunrise_sunset(2026, 172, 35.0, 136.0, 9.0)[2] - 14.4) < 0.15
    assert abs(A.sunrise_sunset(2026, 355, 35.0, 136.0, 9.0)[2] - 9.7) < 0.15


def test_polar_day_and_night():
    assert A.sunrise_sunset(2026, 172, 75.0, 0.0, 0.0)[2] == 24.0
    assert A.sunrise_sunset(2026, 355, 75.0, 0.0, 0.0)[2] == 0.0


def test_noon_and_morning_at_35_north():
    noon = A.sun(2026, 172, 12.0, 35.0, 135.0, 9.0)   # on the zone meridian: 90 - 35 + 23.44 (spec §9.1: < 0.1 deg)
    assert abs(noon.elevation_deg - 78.44) < 0.1 and abs(noon.azimuth_deg - 180.0) < 5.0
    assert 60.0 < A.sun(2026, 172, 7.0, 35.0, 135.0, 9.0).azimuth_deg < 100.0


def test_moon_phase_cycle_and_geometry():
    midnight = A.sun(2026, 172, 0.0, 35.0, 136.0, 9.0)
    new, full = A.moon(0.0, midnight, 35.0, SYN, 0.0), A.moon(SYN / 2, midnight, 35.0, SYN, 0.0)
    assert new.illumination < 1e-9 and abs(full.illumination - 1.0) < 1e-9
    assert full.elevation_deg > 0.0 > new.elevation_deg
    again = A.moon(SYN, midnight, 35.0, SYN, 0.0).phase
    assert min(again, 1.0 - again) < 1e-9


def test_light_rotation_points_away_from_the_body():
    pitch, yaw, roll = A.light_rotation(30.0, 90.0, 0.0)
    f = (math.cos(pitch * A.DEG) * math.cos(yaw * A.DEG), math.cos(pitch * A.DEG) * math.sin(yaw * A.DEG), math.sin(pitch * A.DEG))
    d = A.direction(30.0, 90.0, 0.0)
    assert all(abs(fi + di) < 1e-12 for fi, di in zip(f, d)) and roll == 0.0
