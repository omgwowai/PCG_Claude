# tl_probe_prop_frames.py -- READ-ONLY. For CHA facade props in the current
# level's PCG_3_3_1_Buildings output, find the CHA L1 module instance each
# prop belongs to and report the prop transform in that module's local frame.
# This pins down the frame the Props rows are written in (module mesh frame,
# including any flip the placement applies), so TL rows can be written in the
# same frame. Also reports how many prop instances exist per prop mesh.
import json
import math

PROP_ROOT = "/Game/Prop/BLDG/"
MODULE_KEYS = {"SM_BLDG_CHA_L01_A_Wall_01_N1": "Wall", "SM_BLDG_CHA_L01_A_Column_01_N1": "Pillar",
               "SM_BLDG_CHA_L01_A_Entrance_01_N1": "Entrance", "SM_BLDG_CHA_L01_A_CornerEx_01_N1": "CornerEx"}
LIMIT = 4


def main():
    ML = unreal.MathLibrary
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    props, modules = {}, {}
    for a in eas.get_all_level_actors():
        if "PCG_3_3_1_Buildings" not in a.get_actor_label():
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            if sm is None:
                continue
            path = sm.get_path_name()
            name = sm.get_name()
            if path.startswith(PROP_ROOT):
                props.setdefault(name, [])
                for i in range(c.get_instance_count()):
                    props[name].append(c.get_instance_transform(i, True))
            elif name in MODULE_KEYS:
                modules.setdefault(name, [])
                for i in range(c.get_instance_count()):
                    modules[name].append(c.get_instance_transform(i, True))
    grid = {}
    for name, ts in modules.items():
        for t in ts:
            p = t.translation
            grid.setdefault((int(p.x // 500), int(p.y // 500), int(p.z // 500)), []).append((name, t))
    samples = {}
    for pname in ("SM_BLDG_Prop_BA_Awning_A01_N1", "SM_BLDG_Prop_Lamp_Wall_A02_N1",
                  "SM_BLDG_Prop_BA_Sign_B01_N1", "SM_BLDG_Prop_BA_Sign_E01_N1",
                  "SM_BLDG_Prop_FirehoseConn_Outlet_A01_N1"):
        out = []
        for t in props.get(pname, []):
            p = t.translation
            best = None
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        for mname, mt in grid.get((int(p.x // 500) + dx, int(p.y // 500) + dy, int(p.z // 500) + dz), ()):
                            lp = mt.inverse_transform_location(p)
                            d = math.hypot(lp.x, lp.y - (-162.5 if "Wall" in mname or "Entrance" in mname else 0)) + abs(lp.z) * 0.01
                            if best is None or d < best[0]:
                                best = (d, mname, mt, lp)
            if best is None:
                continue
            d, mname, mt, lp = best
            rel = t * mt.inverse()
            r = rel.rotation.rotator()
            out.append({"module": MODULE_KEYS[mname], "local": [round(lp.x, 1), round(lp.y, 1), round(lp.z, 1)],
                        "rel_yaw": round(r.yaw, 1), "rel_scale": [round(v, 2) for v in rel.scale3d.to_tuple()],
                        "mod_scale": [round(v, 2) for v in mt.scale3d.to_tuple()],
                        "mod_yaw": round(mt.rotation.rotator().yaw, 1)})
            if len(out) >= LIMIT:
                break
        samples[pname] = out
    return {"prop_counts": {k: len(v) for k, v in sorted(props.items(), key=lambda kv: -len(kv[1]))[:30]},
            "module_counts": {k: len(v) for k, v in modules.items()}, "samples": samples}


mcp_result = json.loads(json.dumps(main(), default=str))
