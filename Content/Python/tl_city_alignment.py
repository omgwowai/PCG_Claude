# tl_city_alignment.py -- READ-ONLY. Vertical bay alignment of a style's facade.
# For each pilaster (Column_01) and entrance/feature bay (Entrance_01) on level
# N+1, check whether the same part sits directly below on level N: same XY
# pivot (within tol) and the same facing. Aligned bays give ~100%.
import json

args = mcp_args or {}
MATCH = args.get("match", "/Game/Building/TL/")
VOLUME = args.get("volume", "PCG_3_3_1_Buildings")
TOL = float(args.get("tol", 3.0))
LEVEL_OF = {"_L01_": 1, "_L02_": 2, "_L03_": 3, "_L04_": 4}
PARTS = ("Column_01", "Entrance_01")


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    pts = {}
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() != "PCGVolume" or VOLUME not in a.get_actor_label():
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            path = sm.get_path_name() if sm else ""
            if MATCH not in path:
                continue
            lv = next((v for k, v in LEVEL_OF.items() if k in path), None)
            part = next((p for p in PARTS if "_" + p + "_" in path), None)
            if lv is None or part is None:
                continue
            for i in range(c.get_instance_count()):
                t = c.get_instance_transform(i, True)
                yaw = round(t.rotation.rotator().yaw) % 360
                pts.setdefault((part, lv), []).append((t.translation.x, t.translation.y, yaw))
    R = {}
    for part in PARTS:
        for lv in (2, 3, 4):
            upper = pts.get((part, lv), [])
            lower = pts.get((part, lv - 1), [])
            if part == "Entrance_01" and lv == 4:
                continue
            grid = {}
            for x, y, yaw in lower:
                grid.setdefault((int(x // 50), int(y // 50)), []).append((x, y, yaw))
            hit = 0
            for x, y, yaw in upper:
                ok = False
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for lx, ly, lyaw in grid.get((int(x // 50) + dx, int(y // 50) + dy), ()):
                            if abs(lx - x) <= TOL and abs(ly - y) <= TOL and lyaw == yaw:
                                ok = True
                hit += ok
            R["%s L%d over L%d" % (part, lv, lv - 1)] = {
                "upper": len(upper), "aligned": hit,
                "pct": round(100.0 * hit / len(upper), 1) if upper else None}
    return R


R = main()
print(json.dumps(R, indent=1))
mcp_result = R
