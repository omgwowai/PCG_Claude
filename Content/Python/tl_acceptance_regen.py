# tl_acceptance_regen.py -- regenerate the TL building in Lvl_TL_Building from
# its saved volume, so the read reflects the current RULE/SGD/BDF assets.
# Fire-and-return; read with tl_verify_task10_read.py in a separate call.
import json


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if a.get_actor_label() != "TL_Building_Volume":
            continue
        comp = a.get_component_by_class(unreal.PCGComponent)
        g = comp.get_graph()
        comp.cleanup_local(True)
        comp.activate(True)
        comp.generate_local(True)
        return {"generated": True, "graph": g.get_path_name() if g else None}
    return {"generated": False, "error": "TL_Building_Volume not found"}


mcp_result = json.loads(json.dumps(main(), default=str))
