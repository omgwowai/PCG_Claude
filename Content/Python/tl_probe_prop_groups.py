# tl_probe_prop_groups.py -- READ-ONLY. How many rows of one PropGroup spawn on
# one module instance. For each L01 Entrance_01 / CornerEx_01 instance of the
# showcase building, the props whose origin lies in that module's frame, as
# (prop, local y rounded) -- the Entrance_01 lamps at y 14 and y 311 share
# Group_Door_1, the two corner signs share Group_pillar_1.
import json

LABEL = "TL_Showcase_Building"
HOSTS = ("SM_BLDG_TL_L01_A_Entrance_01_N1", "SM_BLDG_TL_L01_A_CornerEx_01_N1")


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next(a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL)
    hosts, props = [], []
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None:
            continue
        n = sm.get_name()
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            if n in HOSTS:
                hosts.append((n.split("_A_")[1], t))
            elif sm.get_path_name().startswith("/Game/Prop/BLDG/"):
                props.append((n.replace("SM_BLDG_Prop_", "").replace("_N1", ""), t))
    out = []
    for hn, ht in hosts:
        found = []
        for pn, pt in props:
            lp = ht.inverse_transform_location(pt.translation)
            if -100 < lp.x < 30 and -10 < lp.y < 335 and 0 < lp.z < 500:
                found.append("%s@y%d" % (pn, round(lp.y)))
        out.append({"host": hn, "props": sorted(found)})
    return out


mcp_result = json.loads(json.dumps(main(), default=str))
