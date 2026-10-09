# tl_probe_corner_usage.py -- READ-ONLY. In the current level's
# PCG_3_3_1_Buildings output, count instances of every corner-type mesh across
# all styles, so the question "does the BDF route ever place half corners
# (CornerExL/R, CornerInL/R)?" is answered from output, not from the graph.
import json
import re


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    per_kind = {}
    per_style = {}
    total = 0
    for a in eas.get_all_level_actors():
        if "PCG_3_3_1_Buildings" not in a.get_actor_label():
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            if sm is None:
                continue
            n = c.get_instance_count()
            total += n
            name = sm.get_name()
            m = re.search(r"(CornerEx[LR]?|CornerIn[LR]?|CornerCap\w*)_\d+", name)
            if not m:
                continue
            kind = m.group(1)
            per_kind[kind] = per_kind.get(kind, 0) + n
            style = name.split("_")[2] if name.startswith("SM_BLDG_") else name
            per_style.setdefault(style, {})
            per_style[style][kind] = per_style[style].get(kind, 0) + n
    return {"total_instances": total, "corner_instances_by_kind": per_kind,
            "by_style": per_style}


mcp_result = json.loads(json.dumps(main(), default=str))
