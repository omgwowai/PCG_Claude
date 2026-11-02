"""The shared weather parameters (spec §2.6): load Tools/weather/weather_params.json, check it against
params_schema.json, flatten the schema's keys and resolve field sizes. The plugin's FWeatherParams reads the same file.
Pure."""
import json
import math
import os

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Tools/weather
PARAMS_PATH = os.path.join(_DIR, "weather_params.json")
SCHEMA_PATH = os.path.join(_DIR, "params_schema.json")

SEASONS = ("Spring", "Summer", "Autumn", "Winter")
WEATHER_TYPES = ("Clear", "FairCumulus", "Overcast", "FrontalRain", "Thunderstorm", "Fog", "Snow", "Blizzard")
FORMATS = ("rgba16f", "r16f", "r32f")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load(path=PARAMS_PATH):
    """The parameter file as a dict, sections and keys in file order."""
    return _read(path)


def schema(path=SCHEMA_PATH):
    """section -> {key: type name}, or one type name for a section checked as a whole ("fields")."""
    return _read(path)


def flat_keys(schema):
    """"section.key" for every leaf, in schema order; a section whose schema is a type name is one key."""
    keys = []
    for s, spec in schema.items():
        if isinstance(spec, str):
            keys.append(s)
        else:
            keys.extend("%s.%s" % (s, k) for k in spec)
    return keys


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _integer(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _season_doy_map(v):
    return isinstance(v, dict) and set(v) == set(SEASONS) and all(_number(d) and 1 <= d <= 365 for d in v.values())


def _field_map(v):
    return isinstance(v, dict) and all(isinstance(d, dict) and not field_problems(n, d) for n, d in v.items())


_CHECKS = {"number": _number, "integer": _integer, "season": lambda v: v in SEASONS,
           "season_doy_map": _season_doy_map, "field_map": _field_map}


def problems(params, schema):
    """Every way `params` departs from `schema` ([] when it matches). A top-level "version" is allowed."""
    out = []
    for s, spec in schema.items():
        if s not in params:
            out.append("missing section %s" % s)
        elif isinstance(spec, str):
            if not _CHECKS[spec](params[s]):
                out.append("%s is not a %s" % (s, spec))
        elif not isinstance(params[s], dict):
            out.append("%s is not a section" % s)
        else:
            section = params[s]
            for k, t in spec.items():
                if k not in section:
                    out.append("missing %s.%s" % (s, k))
                elif not _CHECKS[t](section[k]):
                    out.append("%s.%s is not a %s" % (s, k, t))
            out.extend("unexpected %s.%s" % (s, k) for k in section if k not in spec)
    out.extend("unexpected section %s" % s for s in params if s not in schema and s != "version")
    return out


def _list_of(v, n, ok):
    return isinstance(v, (list, tuple)) and len(v) == n and all(ok(x) for x in v)


def field_problems(name, desc):
    """What is wrong with the descriptor of field `name` ([] when nothing), in a fixed order. The size check needs
    valid dims and the channel check a valid format, so each waits until its prerequisite is right."""
    out = []
    dims, fmt = desc.get("dims"), desc.get("format")
    dims_ok = _integer(dims) and dims in (2, 3)
    if not dims_ok:
        out.append("%s: dims must be 2 or 3" % name)
    if fmt not in FORMATS:
        out.append("%s: format must be one of %s" % (name, FORMATS))
    if ("size" in desc) == ("cell_m" in desc):
        out.append("%s: give exactly one of size and cell_m" % name)
    if "size" in desc and dims_ok and not _list_of(desc["size"], dims, lambda n: _integer(n) and n > 0):
        out.append("%s: size must be %d positive integers" % (name, dims))
    if "cell_m" in desc and not (dims == 2 and _number(desc["cell_m"]) and desc["cell_m"] > 0):
        out.append("%s: cell_m needs dims 2 and a positive number" % name)
    if fmt in FORMATS:
        want = 4 if fmt == "rgba16f" else 1
        if not _list_of(desc.get("channels"), want, lambda c: isinstance(c, str)):
            out.append("%s: %d channel names expected" % (name, want))
    return out


def field_size(desc, extent_m):
    """Texel size of a field: `size` as given; a `cell_m` field covers the level's extent (m) with n = ceil(extent /
    cell_m) texels a side, rounded up to a multiple of 8 and at least 8, as (n, n)."""
    if "size" in desc:
        return tuple(desc["size"])
    n = math.ceil(extent_m / desc["cell_m"])
    n = max(8, ((n + 7) // 8) * 8)
    return (n, n)
