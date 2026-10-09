# tl_probe_tl_prop_fit.py -- READ-ONLY. For each prop instance on the showcase
# building, find the TL ground/upper-floor module it belongs to and report the
# prop's mesh bounds expressed in that module's local frame (facade at x = 0,
# exterior +X, run along +Y). A prop sitting correctly on the facade has
# min x >= ~0 (outside the wall) and an upright z extent.
import json

LABEL = "TL_Showcase_Building"
MODS = ("_L01_A_Wall_01", "_L01_A_Entrance_01", "_L01_A_Column_01", "_L01_A_CornerEx_01",
        "_L02_A_Wall_01", "_L02_A_Entrance_01", "_L03_A_Wall_01", "_L03_A_Entrance_01")


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = next(a for a in eas.get_all_level_actors() if a.get_actor_label() == LABEL)
    mods, props = [], []
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        if sm is None:
            continue
        n = sm.get_name()
        if any(k in n for k in MODS):
            for i in range(c.get_instance_count()):
                mods.append((n, c.get_instance_transform(i, True)))
        elif sm.get_path_name().startswith("/Game/Prop/BLDG/"):
            bb = sm.get_bounding_box()
            for i in range(min(c.get_instance_count(), 3)):
                props.append((n, c.get_instance_transform(i, True), bb))
    out = []
    for pn, pt, bb in props:
        best = None
        for mn, mt in mods:
            lp = mt.inverse_transform_location(pt.translation)
            if -200 < lp.x < 200 and -20 < lp.y < 345 and -10 < lp.z < 520:
                d = abs(lp.x)
                if best is None or d < best[0]:
                    best = (d, mn, mt, lp)
        if best is None:
            out.append({"prop": pn, "module": None})
            continue
        _, mn, mt, lp = best
        xs, zs = [], []
        for x in (bb.min.x, bb.max.x):
            for y in (bb.min.y, bb.max.y):
                for z in (bb.min.z, bb.max.z):
                    q = mt.inverse_transform_location(pt.transform_location(unreal.Vector(x, y, z)))
                    xs.append(q.x)
                    zs.append(q.z)
        up = mt.inverse_transform_direction(pt.transform_direction(unreal.Vector(0, 0, 100)))
        out.append({"prop": pn.replace("SM_BLDG_Prop_", ""), "module": mn.split("_TL_")[1][:18],
                    "origin_local": [round(lp.x), round(lp.y), round(lp.z)],
                    "x_extent_local": [round(min(xs)), round(max(xs))],
                    "z_extent_local": [round(min(zs)), round(max(zs))],
                    "prop_up_in_module": [round(up.x), round(up.y), round(up.z)]})
    return out


mcp_result = json.loads(json.dumps(main(), default=str))
