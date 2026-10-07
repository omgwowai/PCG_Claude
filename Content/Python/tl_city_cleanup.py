# tl_city_cleanup.py -- clear the PCG_3_3_1_Buildings volume's generated output,
# so the next generate/read pair cannot be served from a previous run's results.
import json


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() != "PCGVolume":
            continue
        comp = a.get_component_by_class(unreal.PCGComponent)
        g = comp.get_graph() if comp else None
        if g and "PCG_3_3_1_Buildings" in g.get_path_name():
            comp.cleanup_local(True)
            n = 0
            for c in a.get_components_by_class(unreal.PrimitiveComponent):
                try:
                    n += c.get_instance_count() or 0
                except Exception:
                    pass
            return {"cleaned": True, "instances_left": n,
                    "generated_flag": comp.get_editor_property("generated")}
    return {"cleaned": False}


mcp_result = json.loads(json.dumps(main(), default=str))
