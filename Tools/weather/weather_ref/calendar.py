"""The calendar (spec §6.1): game seconds -> day and hour, the season and its transition into the next one, and the
compressed date (year, day of year). The plugin's WeatherCalendar copies these rules operation for operation. Pure."""
import collections
import math

from .params import SEASONS

DAY_S = 86400.0
_LAST_HOUR = 23.999999   # hour inputs are clamped to 0.._LAST_HOUR

CalendarState = collections.namedtuple(
    "CalendarState", "game_seconds day_index hour season next_season day_in_season season_fraction in_transition "
                     "transition_progress weights year day_of_year")


def _clamp(x, lo, hi):
    return min(max(x, lo), hi)


def evaluate(game_seconds, cal):
    """The calendar at `game_seconds` (0 = midnight of day 0, the first day of `start_season`). `weights` are the four
    season weights in SEASONS order; over the last `transition_days` of a season they cross-fade into the next one."""
    L, T = cal["season_length_days"], cal["transition_days"]
    start = SEASONS.index(cal["start_season"])

    total = game_seconds / DAY_S
    day_index = math.floor(total)
    hour = (total - day_index) * 24

    ord_ = day_index // L
    seq = start + ord_
    season = seq % 4
    next_ = (season + 1) % 4
    day_in_season = day_index - ord_ * L
    pos = day_in_season + hour / 24
    fraction = pos / L

    in_transition = T > 0 and pos >= L - T
    progress = min(1.0, (pos - (L - T)) / T) if in_transition else 0.0
    weights = [0.0, 0.0, 0.0, 0.0]
    weights[season] = 1 - progress
    weights[next_] += progress

    d0, d1 = cal["season_start_doy"][SEASONS[season]], cal["season_start_doy"][SEASONS[next_]]
    if d1 <= d0:
        d1 += 365
    doy = d0 + fraction * (d1 - d0)
    year = cal["base_year"] + seq // 4
    if doy >= 366:
        doy -= 365
        year += 1

    return CalendarState(game_seconds, day_index, hour, SEASONS[season], SEASONS[next_], day_in_season, fraction,
                         in_transition, progress, tuple(weights), year, doy)


def seconds_for(cal, current_seconds, season, day_in_season, hour):
    """Game seconds of `hour` on day `day_in_season` of `season` (a name in SEASONS), in the cycle of four seasons that
    holds `current_seconds` (a negative time counts as 0). Day and hour are clamped to the season and the day."""
    L = cal["season_length_days"]
    start = SEASONS.index(cal["start_season"])
    current = max(0.0, current_seconds)
    cycle = (math.floor(current / DAY_S) // L) // 4
    ord_ = cycle * 4 + (SEASONS.index(season) - start) % 4
    day = _clamp(day_in_season, 0, L - 1)
    hour = _clamp(hour, 0.0, _LAST_HOUR)
    return (ord_ * L + day) * DAY_S + hour * 3600


def with_hour(current_seconds, hour):
    """The same game day at `hour`, clamped to 0.._LAST_HOUR."""
    return math.floor(current_seconds / DAY_S) * DAY_S + _clamp(hour, 0.0, _LAST_HOUR) * 3600


def advance(current_seconds, delta_seconds):
    """Game time moved on by `delta_seconds`; it never goes below 0."""
    return max(0.0, current_seconds + delta_seconds)
