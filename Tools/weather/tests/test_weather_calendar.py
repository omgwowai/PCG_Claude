from weather_ref import calendar as C
from weather_ref import params as P

CAL = P.load()["calendar"]


def at(day, hour=0.0):
    return day * C.DAY_S + hour * 3600.0


def test_day_zero_is_the_start_season():
    s = C.evaluate(at(0, 12.0), CAL)
    assert (s.season, s.next_season, s.day_in_season, s.in_transition, s.year) == ("Spring", "Summer", 0, False, 2026)
    assert s.hour == 12.0 and s.weights == (1.0, 0.0, 0.0, 0.0)
    assert abs(s.day_of_year - (79 + (0.5 / 7) * (172 - 79))) < 1e-9


def test_last_day_of_a_season_is_the_transition():
    s = C.evaluate(at(6, 12.0), CAL)
    assert s.in_transition and abs(s.transition_progress - 0.5) < 1e-12
    assert s.weights == (0.5, 0.5, 0.0, 0.0)


def test_season_switches_at_day_seven():
    s = C.evaluate(at(7), CAL)
    assert (s.season, s.in_transition, s.transition_progress) == ("Summer", False, 0.0)
    assert abs(s.day_of_year - 172.0) < 1e-9


def test_winter_crosses_new_year():
    s = C.evaluate(at(21 + 5), CAL)
    assert s.season == "Winter" and s.year == 2027
    assert abs(s.day_of_year - (355 + 5 / 7 * 89 - 365)) < 1e-9


def test_second_cycle_spring_is_next_year():
    s = C.evaluate(at(28), CAL)
    assert (s.season, s.year) == ("Spring", 2027)


def test_far_future_stays_consistent():
    for day in (400, 2000):
        s = C.evaluate(at(day, 23.5), CAL)
        assert 1.0 <= s.day_of_year < 366.0 and abs(sum(s.weights) - 1.0) < 1e-12
        assert s.year == 2026 + day // 28 + (1 if s.season == "Winter" and s.day_of_year < 300 else 0)


def test_seconds_for_keeps_the_cycle_and_clamps():
    now = at(30, 15.0)
    assert C.seconds_for(CAL, now, "Winter", 3, 8.0) == at(28 + 21 + 3, 8.0)
    assert C.seconds_for(CAL, now, "Autumn", 99, 25.0) == at(28 + 14 + 6, 23.999999)
    assert C.seconds_for(CAL, now, "Spring", -4, -3.0) == at(28, 0.0)
    assert C.seconds_for(CAL, -500.0, "Summer", 0, 12.0) == at(7, 12.0)


def test_with_hour_and_advance_clamp():
    assert C.with_hour(at(3, 5.0), 24.0) == at(3, 23.999999)
    assert C.with_hour(at(3, 5.0), -1.0) == at(3, 0.0)
    assert C.advance(at(0, 1.0), -7200.0) == 0.0
