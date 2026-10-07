# tl_city_state.py -- READ-ONLY: report the buildings PCG component's state.
import json


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() != "PCGVolume":
            continue
        comp = a.get_component_by_class(unreal.PCGComponent)
        g = comp.get_graph() if comp else None
        if g and "PCG_3_3_1_Buildings" in g.get_path_name():
            R = {"active": comp.is_active()}
            for m in ("is_generating", "is_cleaning_up"):
                f = getattr(comp, m, None)
                R[m] = f() if f else "n/a"
            for p in ("generated", "activated", "generation_trigger"):
                try:
                    R[p] = str(comp.get_editor_property(p))
                except Exception as e:
                    R[p] = "<%s>" % type(e).__name__
            R["methods"] = [m for m in dir(comp) if "generat" in m.lower() or "refresh" in m.lower()]
            return R
    return {"found": False}


mcp_result = json.loads(json.dumps(main(), default=str))
