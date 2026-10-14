"""Editor only: read a PCG graph asset into IR through PyPCGToolsLibrary."""
import json

import unreal

_DEFAULT_SEED_CACHE = {}
LAST_SEED_WARNINGS = []           # class names skipped by the last export() call (strings only; trap 25)


def _default_seed(cls_name):
    """Class default object's Seed for a PCG.<cls_name> settings class, cached. None if the class
    does not load (recorded by the caller as a warning instead of raising).

    NOTE: the ruling's literal snippet -- `cls.get_default_object()` called on the unreal.Class
    instance -- does not work against this engine's Python API: it returns the CDO of UClass
    itself (`/Script/CoreUObject.Default__Class`), not of `cls`, with no error. The free function
    `unreal.get_default_object(cls)` returns the right object; verified live against
    PCGSurfaceSamplerSettings (default seed -1017473487) before using it here."""
    if cls_name in _DEFAULT_SEED_CACHE:
        return _DEFAULT_SEED_CACHE[cls_name]
    cls = unreal.load_class(None, "/Script/PCG." + cls_name)
    seed = None
    if cls is not None:
        cdo = unreal.get_default_object(cls)
        if cdo is not None:
            seed = int(cdo.get_editor_property("seed"))
    _DEFAULT_SEED_CACHE[cls_name] = seed
    return seed


def _fill_default_seeds(ir):
    """Ruling T3a: the exporter omits Seed when it equals the CDO's seed, which is ambiguous with
    the comparator's rule that drops a seed equal to a freshly created node's seed. Make every
    settings node's Seed explicit at extraction time instead. Appends any class name that failed
    to load to module-level LAST_SEED_WARNINGS (skipped rather than failing)."""
    for node in ir.get("nodes", []):
        cls_name = node.get("class")
        if not cls_name:
            continue
        settings = node.get("settings")
        if settings is None:
            settings = node["settings"] = {}
        if "Seed" in settings:
            continue
        seed = _default_seed(cls_name)
        if seed is None:
            if cls_name not in LAST_SEED_WARNINGS:
                LAST_SEED_WARNINGS.append(cls_name)
            continue
        settings["Seed"] = seed


def export(graph):
    ir = json.loads(unreal.PyPCGToolsLibrary.export_graph_ir(graph))
    _fill_default_seeds(ir)
    return ir


def export_path(path):
    g = unreal.EditorAssetLibrary.load_asset(path)
    if g is None:
        raise RuntimeError("cannot load graph %s" % path)
    return export(g)
