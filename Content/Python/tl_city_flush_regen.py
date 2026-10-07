# tl_city_flush_regen.py -- clean the buildings volume, flush PCG's graph cache,
# then fire a fresh generation. Read the result with tl_verify_city_read.py in a
# separate call.
import json


def main():
    R = {}
    unreal.SystemLibrary.execute_console_command(None, "pcg.FlushCache")
    R["flushed"] = True
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() != "PCGVolume":
            continue
        comp = a.get_component_by_class(unreal.PCGComponent)
        g = comp.get_graph() if comp else None
        if g and g.get_path_name() == "/CitySamplePCG/Levels/PCG/PCG_3_3_1_Buildings.PCG_3_3_1_Buildings":
            comp.cleanup_local(True)
            comp.activate(True)
            comp.generate_local(True)
            R["generated"] = True
            return R
    R["generated"] = False
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
