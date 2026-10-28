"""Which map the editor has open, and the guards every editor driver puts in front of a write.

The parsing is pure (pytest runs it); `unreal` is imported only inside the editor-side functions.
A map is named by its full PACKAGE path ("/Game/PyPCG/L_PyTown"), never its short name: any map
called L_PyTown would pass a short-name check (final review M14).
"""
DEMO = "/CitySamplePCG/Levels/L_CitySamplePCG_Demo"   # V2, V1 oracles, measure and probe scripts
TOWN = "/Game/PyPCG/L_PyTown"                         # the town run (pypcg_town*.py)
TOWN_GRAPHS = "/Game/PyPCG/Town/"                     # the only graphs a saved town volume may hold
WORLD = "/Game/PyPCG/L_PyWorld"                       # the PyWorld valley (pyworld.py)


def map_package(level_path_name):
    """'/Game/PyPCG/L_PyTown.L_PyTown:PersistentLevel' -> '/Game/PyPCG/L_PyTown'. The current ULevel is
    always named PersistentLevel, so the map is the package part of its path."""
    return (level_path_name or "").split(":", 1)[0].split(".", 1)[0]


def current_map():
    """The package path of the map being edited ("" when none)."""
    import unreal
    lvl = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).get_current_level()
    return map_package(lvl.get_path_name()) if lvl else ""


def refusal(current, package, what):
    """None when `current` is `package`, else the abort result the drivers return."""
    if current == package:
        return None
    return {"abort": "%s runs only in %s (current map: %s); nothing was changed" % (what, package, current or "none")}


def require(package, what):
    """refusal() against the editor's current map."""
    return refusal(current_map(), package, what)


def graphs_outside(graphs, prefix):
    """{volume label: graph path or None} -> the sorted labels whose graph is missing or not under prefix."""
    return sorted(label for label, g in graphs.items() if not (g and g.startswith(prefix)))


def save_problems(graphs, stage_labels, template=None):
    """Why a town level may not be saved; [] when it may.

    graphs        {label: graph path or None} for EVERY PCG volume of the level (pcg_volume_graphs()).
    stage_labels  the 18 stage volume labels (stages.names()).
    template      {label: the template graph's package path}, or None. None means the town's graphs must
                  already be assigned: every stage volume under TOWN_GRAPHS. With a template, a level whose
                  stage volumes ALL still hold their template graphs also passes (a save before assign).
    Anything else -- a probe / slim / retired-official copy, a mix of the two states, a missing stage volume,
    or a PCG volume that is not a stage volume -- is a problem."""
    problems = []
    extra = sorted(set(graphs) - set(stage_labels))
    if extra:
        problems.append("PCG volumes that are not stage volumes (probe leftovers?): %s" % extra)
    missing = sorted(set(stage_labels) - set(graphs))
    if missing:
        problems.append("stage volumes missing: %s" % missing)
    stage = {label: graphs[label] for label in stage_labels if label in graphs}
    outside = graphs_outside(stage, TOWN_GRAPHS)
    if not outside:
        return problems
    if template is not None and len(outside) == len(stage):
        wrong = sorted(label for label, g in stage.items() if not g or g.split(".", 1)[0] != template.get(label))
        if wrong:
            problems.append("graphs that are neither the template's own nor under %s: %s"
                            % (TOWN_GRAPHS, {label: stage[label] for label in wrong}))
        return problems
    problems.append("graphs not under %s: %s" % (TOWN_GRAPHS, {label: stage[label] for label in outside}))
    return problems


def pcg_volume_graphs():
    """{actor label: its PCG component's graph path or None} for every actor of the current level that
    carries a PCGComponent (the stage volumes and any probe volume)."""
    import unreal
    from pypcg import census
    out = {}
    for a in census.volumes():
        g = a.get_component_by_class(unreal.PCGComponent).get_graph()
        out[str(a.get_actor_label())] = g.get_path_name() if g else None
    return out
