# tl_probe_corner_props.py -- READ-ONLY. Do the CornerEx_01 prop anchors spawn?
# For every blade sign / hose outlet instance on the showcase building, the
# nearest L01 module instance (by origin) and the distance to it.
import json

LABEL = "TL_Showcase_Building"
PROPS = ("SM_BLDG_Prop_BA_Sign_B01_N1", "SM_BLDG_Prop_FirehoseConn_Outlet_A01_N1")


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next(a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL)
    mods, props = [], []
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None:
            continue
        n = sm.get_name()
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            if "_TL_L01_" in n:
                mods.append((n.split("_A_")[1], t))
            elif n in PROPS:
                props.append((n, t))
    out = []
    for n, t in props:
        best = None
        for mn, mt in mods:
            lp = mt.inverse_transform_location(t.translation)
            if -120 < lp.x < 60 and -120 < lp.y < 345 and 0 < lp.z < 520:
                d = abs(lp.x) + abs(lp.y - 60)
                if best is None or d < best[0]:
                    best = (d, mn, [round(v) for v in lp.to_tuple()])
        out.append({"prop": n.split("Prop_")[1], "module": best[1] if best else None,
                    "local": best[2] if best else None})
    return {"n_corner_modules": sum(1 for m, _ in mods if m.startswith("CornerEx")), "props": out}


mcp_result = json.loads(json.dumps(main(), default=str))
