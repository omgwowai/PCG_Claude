# tl_probe_prop_side.py -- READ-ONLY. Settles which side of a facade module
# its props hang on. For CHA L1 Wall_01 / Column_01 instances in the current
# level's buildings output, cluster everything into buildings, then for each
# awning / wall-lamp instance near a module report (in the module's local
# frame): the building centroid's x sign, the prop mesh's bounds-centre x, and
# the prop's projection direction (its local +Y mapped into the module frame).
import json
import math

PROPS = {"SM_BLDG_Prop_BA_Awning_A01_N1": "awning", "SM_BLDG_Prop_Lamp_Wall_A02_N1": "lamp",
         "SM_BLDG_Prop_Lamp_Wall_A01_N1": "lamp1", "SM_BLDG_Prop_AC_Window_A01_N1": "ac"}
MODS = ("SM_BLDG_CHA_L01_A_Wall_01_N1", "SM_BLDG_CHA_L01_A_Column_01_N1",
        "SM_BLDG_CHA_L06_A_Wall_01_N1", "SM_BLDG_CHA_L02_A_Wall_01_N1")


def main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    props, mods, allpts = [], [], []
    bounds = {}
    for a in eas.get_all_level_actors():
        if "PCG_3_3_1_Buildings" not in a.get_actor_label():
            continue
        for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            sm = c.get_editor_property("static_mesh")
            if sm is None:
                continue
            n = sm.get_name()
            if n in PROPS:
                bb = sm.get_bounding_box()
                bounds[n] = ((bb.min.x + bb.max.x) / 2, (bb.min.y + bb.max.y) / 2, (bb.min.z + bb.max.z) / 2)
                for i in range(c.get_instance_count()):
                    props.append((n, c.get_instance_transform(i, True)))
            elif n in MODS:
                for i in range(c.get_instance_count()):
                    t = c.get_instance_transform(i, True)
                    mods.append((n, t))
            if "/Game/Building/CH/A/" in sm.get_path_name():
                for i in range(0, c.get_instance_count(), 3):
                    p = c.get_instance_transform(i, True).translation
                    allpts.append((p.x, p.y))
    # centroid of the CHA module pivots within 40 m of a point
    grid = {}
    for x, y in allpts:
        grid.setdefault((int(x // 4000), int(y // 4000)), []).append((x, y))

    def centroid(x, y):
        pts = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                pts += [p for p in grid.get((int(x // 4000) + dx, int(y // 4000) + dy), ())
                        if (p[0] - x) ** 2 + (p[1] - y) ** 2 < 3000 ** 2]
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) if pts else (x, y)

    mgrid = {}
    for n, t in mods:
        mgrid.setdefault((int(t.translation.x // 400), int(t.translation.y // 400), int(t.translation.z // 400)), []).append((n, t))
    out = {}
    for pn, pt in props:
        kind = PROPS[pn]
        if len(out.get(kind, [])) >= 5:
            continue
        p = pt.translation
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for mn, mt in mgrid.get((int(p.x // 400) + dx, int(p.y // 400) + dy, int(p.z // 400) + dz), ()):
                        lp = mt.inverse_transform_location(p)
                        d = abs(lp.x) + (0 if -330 <= lp.y <= 5 else 500) + (0 if -5 <= lp.z <= 600 else 500)
                        if best is None or d < best[0]:
                            best = (d, mn, mt, lp)
        if best is None or best[0] > 200:
            continue
        _, mn, mt, lp = best
        cx, cy = centroid(mt.translation.x, mt.translation.y)
        cl = mt.inverse_transform_location(unreal.Vector(cx, cy, mt.translation.z))
        bc = bounds[pn]
        cw = pt.transform_location(unreal.Vector(*bc))
        cwl = mt.inverse_transform_location(cw)
        yw = pt.transform_location(unreal.Vector(0, 100, 0))
        y0 = pt.transform_location(unreal.Vector(0, 0, 0))
        dirl = mt.inverse_transform_direction(yw - y0)
        out.setdefault(kind, []).append({
            "module": mn.split("_A_")[0][-3:] + "_" + mn.split("_A_")[1][:9],
            "prop_origin_local": [round(lp.x, 1), round(lp.y, 1), round(lp.z, 1)],
            "prop_bbox_centre_local_x": round(cwl.x, 1),
            "prop_plusY_dir_local": [round(dirl.x, 2), round(dirl.y, 2)],
            "building_centroid_local_x": round(cl.x)})
    return out


mcp_result = json.loads(json.dumps(main(), default=str))
