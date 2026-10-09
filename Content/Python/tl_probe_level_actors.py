# tl_probe_level_actors.py -- READ-ONLY. List the current level's actors with
# class, label, location, and for PCG volumes the graph and the graph-instance
# parameter overrides.
import json


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    out = []
    for a in eas.get_all_level_actors():
        rec = {"label": a.get_actor_label(), "class": a.get_class().get_name(),
               "loc": [round(v) for v in a.get_actor_location().to_tuple()]}
        comp = a.get_component_by_class(unreal.PCGComponent)
        if comp is not None:
            g = comp.get_graph()
            rec["graph"] = g.get_path_name() if g else None
            try:
                gi = comp.get_editor_property("graph_instance")
                rec["params"] = gi.get_editor_property("parameters_overrides").export_text()[:2000]
            except Exception as e:
                rec["params_err"] = str(e)
            rec["bounds"] = [round(v) for v in a.get_actor_bounds(False)[1].to_tuple()]
        out.append(rec)
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    return {"world": w.get_path_name(), "actors": [r for r in out if r["class"] not in ("StaticMeshActor",)][:80],
            "n": len(out)}


mcp_result = json.loads(json.dumps(main(), default=str))
