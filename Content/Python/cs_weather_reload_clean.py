# cs_weather_reload_clean.py -- after cs_weather.py restore {"to": "original"}: clear the dirty flag of the demo level's
# external actor packages. The restore has put every original value back, but the packages stay dirty, and the editor's
# autosave then writes copies that a crash-restore could write over the real files (CLAUDE.md trap 78). The values are
# verified to equal the snapshot first (any mismatch -> the flag stays and the result says so).
# EditorAssetSubsystem.set_dirty_flag needs an asset object: an external actor's package holds the actor itself
# (IsAsset() is true for an actor in its own external package), so the actor is what it gets.
# Args: {"dry": true} lists the dirty packages without changing anything.
import importlib
import os

import unreal

import cs_wx_lib as lib

importlib.reload(lib)

LEVEL_PREFIX = "/CitySamplePCG/__ExternalActors__/Levels/L_CitySamplePCG_Demo/"
SNAP_CLEAR = os.path.join(lib.SAVED, "Reports", "cs_weather", "original_state.json")
SNAP_EXTRA = os.path.join(lib.REPORT_DIR, "original_extra.json")


def _same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) <= 1e-4 * max(1.0, abs(float(a)), abs(float(b)))
        except (TypeError, ValueError):
            return False
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _verify():
    """Every snapshotted component value equals the live one."""
    bad = []
    for path in (SNAP_EXTRA, SNAP_CLEAR):
        snap = lib.load_json(path, {"components": {}})
        for section, props in snap.get("components", {}).items():
            _, comp = lib.component(section)
            if comp is None:
                bad.append(section + " missing")
                continue
            for prop, val in props.items():
                live = lib.enc(comp.get_editor_property(prop))
                if not _same(live, val):
                    bad.append("%s.%s live %s snap %s" % (section, prop, str(live)[:60], str(val)[:60]))
    return bad


def _main(args):
    eal = unreal.EditorLoadingAndSavingUtils
    dirty = [p.get_name() for p in eal.get_dirty_content_packages() + eal.get_dirty_map_packages()]
    level = [n for n in dirty if n.startswith(LEVEL_PREFIX)]
    out = {"dirty_before": sorted(dirty), "level_pkgs": len(level)}
    if args.get("dry") or not level:
        return out
    bad = _verify()
    if bad:
        out["refused"] = "live values differ from the snapshot; run cs_weather.py restore {\"to\": \"original\"} first"
        out["mismatch"] = bad[:20]
        return out
    sub = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
    cleared = []
    for a in lib.actors():
        pkg = a.get_package()
        name = pkg.get_name() if pkg else ""
        if name in level:
            cleared.append([name, bool(sub.set_dirty_flag(a, False))])
    out["cleared"] = cleared
    out["dirty_after"] = sorted(p.get_name() for p in eal.get_dirty_content_packages() + eal.get_dirty_map_packages())
    return out


if "mcp_args" in globals() or __name__ == "__main__":     # run by the bridge; cs_weather.py imports _main instead
    mcp_result = _main(globals().get("mcp_args") or {})
