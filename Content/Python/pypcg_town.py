import gc
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
# The bridge keeps sys.modules between calls; drop pypcg so edits to it take effect.
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

# pypcg_town.py -- run the 18 stages in the town level (spec 5). One phase per call.
#   assign                       volumes -> /Game/PyPCG/Town/*, keep their overrides + the town's
#   reset                        cleanup_local on every volume                     (Task 27)
#   gen {"stage"}                activate + generate_local(True)                   (Task 27)
#   read {"stage","pass"}        census + acceptance for that stage                (Task 27)
#   shot {"stage","pass"}        one screenshot of the town so far                 (Task 27)
#   overview {"view"}            top / street / wide                               (Task 27)
#   finish                       compare passes, save level, write census          (Task 28)
LEVEL = "L_PyTown"
REPORTS = os.path.join(_REPO, "Saved", "Reports")
OVERRIDES = os.path.join(REPORTS, "pypcg_town_component_overrides.json")


def _load(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return default


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False, sort_keys=True)


def _current_map():
    """The current map's short name; the current ULevel itself is always named PersistentLevel."""
    lvl = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).get_current_level()
    return lvl.get_path_name().split(":", 1)[0].rsplit(".", 1)[-1] if lvl else ""


def phase_assign():
    from pypcg import census, stages
    from pypcg.profiles import town
    saved = _load(OVERRIDES, {})
    out = {}
    for s in stages.STAGES:
        v = census.volume(s[0])
        pc = v.get_component_by_class(unreal.PCGComponent)
        if s[1] not in saved:                       # the template copy's own overrides, recorded once
            saved[s[1]] = census.overrides(pc)
        pc.set_graph(unreal.EditorAssetLibrary.load_asset("/Game/PyPCG/Town/" + s[1]))
        wanted = dict(saved[s[1]])
        wanted.update(town.COMPONENT_OVERRIDES.get(s[1], {}))
        res = census.apply_overrides(pc, wanted)
        back = census.overrides(pc)
        out[s[1]] = {"graph": pc.get_graph().get_path_name(),
                     "overrides_ok": all(back.get(k) == val for k, val in wanted.items() if k not in res["skipped"]),
                     "skipped": res["skipped"], "overrides": back}
    _save(OVERRIDES, saved)
    return out


PHASES = {"assign": lambda a: phase_assign()}


def run(args):
    if _current_map() != LEVEL:
        return {"abort": "open /Game/PyPCG/%s first (current: %s)" % (LEVEL, _current_map())}
    phase = args.get("phase")
    if phase not in PHASES:
        return {"abort": "unknown phase %r; phases: %s" % (phase, sorted(PHASES))}
    return PHASES[phase](args)


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600])}
gc.collect()
