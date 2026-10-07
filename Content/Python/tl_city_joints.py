# tl_city_joints.py -- READ-ONLY. Horizontal fit of TL facade modules in the
# city buildings output. Each module's run spans local Y [ymin, ymax]; both ends
# are taken to world space, and an end counts as "joined" when another module
# on the same level has an end within 2 cm. Modules recentred correctly on
# their slots join neighbours of any width; a missing Size/2 shift leaves gaps
# wherever widths differ. Also repeats the vertical Z-delta check.
import json

LEVEL_OF = {"_L01_": 1, "_L02_": 2, "_L03_": 3}
TOL = 2.0
MATCH = (mcp_args or {}).get("match", "/Game/Building/TL/")


def main():
    ML = unreal.MathLibrary
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = None
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() != "PCGVolume":
            continue
        comp = a.get_component_by_class(unreal.PCGComponent)
        g = comp.get_graph() if comp else None
        if g and "PCG_3_3_1_Buildings" in g.get_path_name():
            vol = a
            break
    if vol is None:
        return {"fatal": "no buildings volume"}

    ends = []          # (level, x, y, z, instance id)
    by_level_xy = {1: {}, 2: {}, 3: {}}
    iid = 0
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        path = sm.get_path_name() if sm else ""
        if MATCH not in path:
            continue
        lv = next((v for k, v in LEVEL_OF.items() if k in path), None)
        if lv is None:
            continue
        bb = sm.get_bounding_box()
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            for y in (bb.min.y, bb.max.y):
                p = ML.transform_location(t, unreal.Vector(0.0, y, 0.0))
                ends.append((lv, p.x, p.y, p.z, iid))
            o = t.translation
            by_level_xy[lv].setdefault((round(o.x), round(o.y)), []).append(o.z)
            iid += 1

    grid = {}
    for e in ends:
        key = (e[0], int(e[1] // TOL), int(e[2] // TOL), int(e[3] // TOL))
        grid.setdefault(key, []).append(e)
    joined = 0
    for e in ends:
        hit = False
        gx, gy, gz = int(e[1] // TOL), int(e[2] // TOL), int(e[3] // TOL)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for f in grid.get((e[0], gx + dx, gy + dy, gz + dz), ()):
                        if f[4] != e[4] and abs(f[1] - e[1]) <= TOL and \
                           abs(f[2] - e[2]) <= TOL and abs(f[3] - e[3]) <= TOL:
                            hit = True
                            break
                    if hit:
                        break
                if hit:
                    break
            if hit:
                break
        joined += hit

    def dz(lo, hi):
        hist = {}
        for key, zs in by_level_xy[hi].items():
            lows = by_level_xy[lo].get(key)
            if not lows:
                continue
            for zh in zs:
                d = round(zh - min(lows, key=lambda zl: abs(zh - zl)), 1)
                hist[d] = hist.get(d, 0) + 1
        return dict(sorted(hist.items(), key=lambda kv: -kv[1])[:4])

    return {"modules": iid, "module_ends": len(ends), "ends_joined": joined,
            "joined_pct": round(100.0 * joined / len(ends), 2) if ends else None,
            "dz_L1_to_L2": dz(1, 2), "dz_L2_to_L3": dz(2, 3)}


R = main()
print(json.dumps(R, indent=1, default=str))
mcp_result = json.loads(json.dumps(R, default=str))
