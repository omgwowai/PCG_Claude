# pyg_probe_actor_refs.py -- READ-ONLY. Which level is open, and do the
# hard-coded ActorReferences inside the official stage graphs (soft paths into
# L_CitySamplePCG_Demo) resolve to live actors in it? Also lists the open
# level's PCGVolumes with their graph, so a role -> actor map can be designed.
# Nothing is modified or saved.
import json
import re

REFS = [
    "PCGVolume_UAID_387C7649839438DB02_2022637616",
    "PCGVolume_UAID_387C7649839438DB02_2022633615",
    "1_CentralPark_Footprint_2gania7pfoeg2_UAID_387C764983945CDF02_1296577182",
    "Spline_UAID_387C76498394B3DF02_1392886487",
]


def main():
    R = {}
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    R["world"] = world.get_path_name()
    demo = "/CitySamplePCG/Levels/L_CitySamplePCG_Demo.L_CitySamplePCG_Demo:PersistentLevel."
    R["resolve_demo_path"] = {}
    for r in REFS:
        o = unreal.find_object(None, demo + r)
        R["resolve_demo_path"][r] = o.get_path_name() if o else None
    acts = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
    by_name = {a.get_name(): a for a in acts}
    R["same_name_in_open_level"] = {r: (by_name[r].get_path_name() if r in by_name else None) for r in REFS}
    vols = []
    for a in acts:
        if a.get_class().get_name() != "PCGVolume":
            continue
        pc = a.get_component_by_class(unreal.PCGComponent)
        g = pc.get_graph() if pc else None
        vols.append({"name": a.get_name(), "label": a.get_actor_label(),
                     "graph": g.get_name() if g else None})
    R["volumes"] = sorted(vols, key=lambda v: str(v["graph"]))
    del acts, by_name, world
    return R


mcp_result = json.loads(json.dumps(main(), default=str))
