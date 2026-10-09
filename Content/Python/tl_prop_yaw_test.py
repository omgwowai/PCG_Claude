# tl_prop_yaw_test.py -- temporary actors in Lvl_TL_Showcase to read off each
# facade prop's correct yaw on a TL module. Four TL L1 Wall_01 copies side by
# side (facade facing +X, like the kit), each carrying the lamp, blade sign,
# AC unit and awning at yaw 0 / 90 / 180 / -90. Args: {"clear": true} removes
# them. Actors are labelled TLYAW_* and never saved (tl_save_showcase_level.py
# is not run while they exist).
import json

args = mcp_args or {}
ORIGIN = unreal.Vector(9000.0, -2000.0, 0.0)
WALL = "/Game/Building/TL/A/Kit_Bldg_TL_L1_A/Mesh/SM_BLDG_TL_L01_A_Wall_01_N1"
PROPS = {
    "lamp": ("/Game/Prop/BLDG/Kit_Prop_Lamp/Mesh/SM_BLDG_Prop_Lamp_Wall_A02_N1", (6, 60, 330)),
    "blade": ("/Game/Prop/BLDG/B/Kit_Prop_BA/Mesh/SM_BLDG_Prop_BA_Sign_B01_N1", (6, 270, 230)),
    "ac": ("/Game/Prop/BLDG/Kit_Prop_AC/Mesh/SM_BLDG_Prop_AC_Window_A02_N1", (0, 162, 60)),
    "awning": ("/Game/Prop/BLDG/B/Kit_Prop_BA/Mesh/SM_BLDG_Prop_BA_Awning_A01_N1", (4, 162, 420)),
}
YAWS = (0, 90, 180, -90)


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    old = [a for a in eas.get_all_level_actors() if a.get_actor_label().startswith("TLYAW_")]
    for a in old:
        eas.destroy_actor(a)
    if args.get("clear"):
        return {"removed": len(old)}
    EAL = unreal.EditorAssetLibrary
    wall = EAL.load_asset(WALL)
    made = []
    for i, yaw in enumerate(YAWS):
        base = ORIGIN + unreal.Vector(0.0, i * 400.0, 0.0)
        w = eas.spawn_actor_from_object(wall, base)
        w.set_actor_label("TLYAW_wall_%d" % yaw)
        for name, (path, loc) in PROPS.items():
            # AC unit sits on an upper-floor sill; put it on a second wall copy above
            p = eas.spawn_actor_from_object(EAL.load_asset(path), base + unreal.Vector(*loc),
                                            unreal.Rotator(roll=0.0, pitch=0.0, yaw=float(yaw)))
            p.set_actor_label("TLYAW_%s_%d" % (name, yaw))
            made.append(p.get_actor_label())
    return {"made": made}


mcp_result = json.loads(json.dumps(main(), default=str))
