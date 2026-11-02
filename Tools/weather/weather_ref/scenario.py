"""Scenario checks (spec §8.4). A scenario of Tools/weather/scenarios.json has steps, which the editor driver weather.py
runs in L_WeatherLab (`set` and `advance` drive the weather, `record` stores its state under a name), and checks on
those records, whose limits are the "@name"s of thresholds.json. A record is the subsystem's state JSON plus the
`actors` block read back from the level. The editor's Python imports this module, so it uses only the standard
library. Pure."""
import json
import os

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Tools/weather
SCENARIOS_PATH = os.path.join(_DIR, "scenarios.json")
THRESHOLDS_PATH = os.path.join(_DIR, "thresholds.json")

STEP_KEYS = ("set", "advance", "record")
_PATH_KEYS = ("value", "ref")

# kind -> (its parameters besides `value`, its test on the value v and the parameters p). `ref` is the path of a second
# recorded value; every other parameter may name a threshold as "@name". Every kind but `equals` compares numbers.
KINDS = {
    "near": (("target", "tol"), lambda v, p: abs(v - p["target"]) <= p["tol"]),
    "equal_to": (("ref", "tol"), lambda v, p: abs(v - p["ref"]) <= p["tol"]),
    "greater": (("ref",), lambda v, p: v > p["ref"]),
    "less": (("ref",), lambda v, p: v < p["ref"]),
    "ratio_below": (("ref", "max_ratio"), lambda v, p: v / p["ref"] < p["max_ratio"]),
    "at_least": (("min",), lambda v, p: v >= p["min"]),
    "at_most": (("max",), lambda v, p: v <= p["max"]),
    "equals": (("literal",), lambda v, p: v == p["literal"]),
}


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_scenarios(path=SCENARIOS_PATH):
    """The scenario file: {"scenarios": {name: {"milestone", "steps", "checks"}}}."""
    return _read(path)


def load_thresholds(path=THRESHOLDS_PATH):
    """The thresholds file: name -> limit."""
    return _read(path)


def resolve(records, path):
    """The value at the dotted `path`: its first part names a record, and a later part is a key, or an index when it
    is a number and the value there a list. Raises KeyError naming the first part that is missing."""
    node = records
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, (list, tuple)) and part.isdecimal() and int(part) < len(node):
            node = node[int(part)]
        else:
            raise KeyError(part)
    return node


def value_of(x, thresholds):
    """thresholds[name] for "@name" (KeyError when it is missing); anything else as it is."""
    if isinstance(x, str) and x.startswith("@"):
        return thresholds[x[1:]]
    return x


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _known(kind):
    return isinstance(kind, str) and kind in KINDS


class _Unusable(Exception):
    """A check that cannot be evaluated; its message says why."""


def _recorded(check, key, records, numeric):
    """The recorded value at the path check[key] ("value" or "ref"), which must be a number when `numeric`."""
    path = check.get(key)
    if not isinstance(path, str):
        raise _Unusable("no %s" % key if path is None else "%s %r is not a path" % (key, path))
    try:
        v = resolve(records, path)
    except KeyError as e:
        name = path.split(".")[0]
        raise _Unusable("%s: no record %s" % (path, name) if name not in records
                        else "%s: %s is missing" % (path, e.args[0])) from None
    if numeric and not _number(v):
        raise _Unusable("%s = %r is not a number" % (path, v))
    return v


def _parameter(check, key, thresholds, numeric):
    """check[key], or the threshold it names as "@name", which must be a number when `numeric`."""
    if key not in check:
        raise _Unusable("no %s" % key)
    try:
        x = value_of(check[key], thresholds)
    except KeyError:
        raise _Unusable("%s %s is not in thresholds" % (key, check[key])) from None
    if numeric and not _number(x):
        raise _Unusable("%s %r is not a number" % (key, x))
    return x


def evaluate(check, records, thresholds):
    """(ok, detail) of one check on `records` (record name -> record); the detail gives the values it compared. A check
    that cannot be evaluated -- an unknown kind; a missing record, path, parameter or threshold; a value of the wrong
    type; a ref of 0 under ratio_below -- fails with a detail that says why. It never raises."""
    kind = check.get("kind")
    if not _known(kind):
        return False, "unknown kind %r" % (kind,)
    params, test = KINDS[kind]
    numeric = kind != "equals"
    try:
        v = _recorded(check, "value", records, numeric)
        p = {k: _recorded(check, k, records, numeric) if k == "ref" else _parameter(check, k, thresholds, numeric)
             for k in params}
        if kind == "ratio_below" and p["ref"] == 0:
            raise _Unusable("ref %s = %r: cannot divide by zero" % (check["ref"], p["ref"]))
    except _Unusable as e:
        return False, str(e)
    shown = ["%s = %r" % (check["value"], v)]
    shown += ["ref %s = %r" % (check["ref"], x) if k == "ref" else "%s %r" % (k, x) for k, x in p.items()]
    return test(v, p), ", ".join(shown)


def run_checks(checks, records, thresholds):
    """Every check evaluated in order: how many passed, the names of those that failed, and one result each."""
    results = []
    for c in checks:
        ok, detail = evaluate(c, records, thresholds)
        results.append({"name": c.get("name"), "ok": ok, "detail": detail})
    return {"passed": sum(r["ok"] for r in results), "failed": [r["name"] for r in results if not r["ok"]],
            "results": results}


def _duplicates(names):
    """The names that occur more than once, each once, in order."""
    out = []
    for i, n in enumerate(names):
        if n in names[:i] and n not in out:
            out.append(n)
    return out


def _starts_recorded(path, recorded):
    return isinstance(path, str) and path.split(".")[0] in recorded


def problems(doc, thresholds):
    """Every way the scenario file `doc` breaks its rules ([] when none): the file needs `scenarios`, and a scenario
    needs milestone, steps and checks; a step has exactly one key, out of STEP_KEYS; record names and check names are
    unique within their scenario; a check's kind is known, its value and ref paths start with a name its scenario
    records, and every "@name" among its parameters is in `thresholds`."""
    if "scenarios" not in doc:
        return ["missing scenarios"]
    out = []
    for s, sc in doc["scenarios"].items():
        out.extend("%s: missing %s" % (s, k) for k in ("milestone", "steps", "checks") if k not in sc)
        recorded = []
        for i, step in enumerate(sc.get("steps") or []):
            if not (isinstance(step, dict) and len(step) == 1 and next(iter(step)) in STEP_KEYS):
                out.append("%s: steps[%d] %r needs exactly one key, out of %s" % (s, i, step, ", ".join(STEP_KEYS)))
            elif "record" in step:
                recorded.append(step["record"])
        out.extend("%s: duplicate record name %r" % (s, n) for n in _duplicates(recorded))
        names = []
        for c in sc.get("checks") or []:
            name = c.get("name")
            names.append(name)
            if not _known(c.get("kind")):
                out.append("%s: check %s: unknown kind %r" % (s, name, c.get("kind")))
            out.extend("%s: check %s: %s %s does not start with a recorded name" % (s, name, k, c[k])
                       for k in _PATH_KEYS if k in c and not _starts_recorded(c[k], recorded))
            out.extend("%s: check %s: %s %s is not in thresholds" % (s, name, k, x) for k, x in c.items()
                       if k not in ("name", "kind") + _PATH_KEYS and isinstance(x, str) and x.startswith("@")
                       and x[1:] not in thresholds)
        out.extend("%s: duplicate check name %r" % (s, n) for n in _duplicates(names))
    return out
