# tl_probe_corner_context.py -- READ-ONLY. For corner instances of a style in
# the city buildings output, find the wall-type instances whose run endpoints
# touch the corner (within tol), and report, in the corner's local frame, where
# those wall endpoints are and which local direction each wall runs. Tells us
# how the BDF route places C_E / C_I relative to the two walls it joins.
import json

args = mcp_args or {}
STYLE = args.get("style", "/Game/Building/CH/A/Kit_Bldg_CHA_L2_A/")
CORNERS = ("CornerEx_01_N1", "CornerIn_01_N1")
WALLS = ("Wall_01_N1", "Column_01_N1", "Entrance_01_N1")
TOL = float(args.get("tol", 40.0))
LIMIT = int(args.get("limit", 6))


def main():
    ML = unreal.MathLibrary
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    vol = None
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() == "PCGVolume" and "PCG_3_3_1_Buildings" in a.get_actor_label():
            vol = a
    corners, ends = [], []
    for c in vol.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        path = sm.get_path_name() if sm else ""
        if STYLE not in path:
            continue
        name = path.split(".")[-1]
        bb = sm.get_bounding_box()
        if any(k in name for k in CORNERS):
            for i in range(c.get_instance_count()):
                corners.append((name, c.get_instance_transform(i, True), bb))
        elif any(k in name for k in WALLS):
            for i in range(c.get_instance_count()):
                t = c.get_instance_transform(i, True)
                a = ML.transform_location(t, unreal.Vector(0, bb.min.y, 0))
                b = ML.transform_location(t, unreal.Vector(0, bb.max.y, 0))
                ends.append((name, t, a, b))
    grid = {}
    for e in ends:
        for p in (e[2], e[3]):
            grid.setdefault((int(p.x // 200), int(p.y // 200), int(p.z // 200)), []).append((e, p))
    out = []
    per_kind = {}
    for name, t, bb in corners:
        kind = name.split("_A_")[-1]
        if per_kind.get(kind, 0) >= LIMIT:
            continue
        o = t.translation
        hits = []
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                for dz in (0,):
                    for e, p in grid.get((int(o.x // 200) + dx, int(o.y // 200) + dy, int(o.z // 200) + dz), ()):
                        lp = t.inverse_transform_location(p)
                        if abs(lp.z) > 5:
                            continue
                        if lp.x < bb.min.x - TOL or lp.x > bb.max.x + TOL or lp.y < bb.min.y - TOL or lp.y > bb.max.y + TOL:
                            continue
                        # wall run direction in corner-local frame
                        wa = t.inverse_transform_location(e[2])
                        wb = t.inverse_transform_location(e[3])
                        far = wb if (wb.x - lp.x) ** 2 + (wb.y - lp.y) ** 2 > 1 else wa
                        if (far.x - lp.x) ** 2 + (far.y - lp.y) ** 2 < 1:
                            far = wa
                        d = (far.x - lp.x, far.y - lp.y)
                        hits.append({"wall": e[0].split("_A_")[-1], "touch_local": [round(lp.x), round(lp.y)],
                                     "runs_local": [round(d[0]), round(d[1])]})
        if hits:
            per_kind[kind] = per_kind.get(kind, 0) + 1
            out.append({"corner": kind, "bb_xy": [round(bb.min.x), round(bb.max.x), round(bb.min.y), round(bb.max.y)],
                        "scale": [round(t.scale3d.x, 2), round(t.scale3d.y, 2)], "walls": hits[:4]})
    return {"corners_total": len(corners), "samples": out}


R = main()
mcp_result = json.loads(json.dumps(R, default=str))
