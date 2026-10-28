"""The building kit (BDF modules, 建筑模块): the Megascans Modular_Building meshes of the project as City Sample-style
module tables -- per family, per level: height, the bay / pier / corner modules with their slot widths, and the
material each module takes for a facade colour. Measured in the editor (pyworld_probe_megascans_kit.py,
pyworld_kit_test.py, 2026-10-27): a module runs along its local +X from 0 to its slot width, its facade faces +Y and
its wall body lies towards -Y; a corner's pivot is the corner point, it covers `cx` of the edge it starts and `cy` of
the edge before. Family 01's sub-meshes _01.._04 lost their material on import (WorldGridMaterial): `fix` modules always
take the kit's own instance. Pure (paths only); pyworld_town_materials.py builds the tinted instances."""

KIT = "/Game/Megascans/3D_Assets/Modular_Building_"
TOWN = "/Game/PyPCG/World/Town/"


def _p(pkg):
    return "%s.%s" % (pkg, pkg.rsplit("/", 1)[1])


def mesh(folder, name):
    return _p(KIT + folder + "/" + name)


def inst(folder):
    return _p("%s%s/Modular_Building_%s_inst" % (KIT, folder, folder))


def tinted(folder, tint):
    return _p("%sMI_%s_%s" % (TOWN, folder, tint))


# Facade colours (MS_DefaultMaterial "Albedo Tint", linear); "Base" keeps the kit's own material.
TINTS = {
    "Plaster": {"Base": None, "Ochre": (1.0, 0.8, 0.55), "Rose": (1.0, 0.76, 0.7), "Sage": (0.8, 0.9, 0.76),
                "Mist": (0.8, 0.85, 0.93), "Butter": (1.0, 0.93, 0.62)},
    "Brick": {"Base": None, "Umber": (0.7, 0.6, 0.55), "Sand": (1.0, 0.88, 0.72)},
    "Stone": {"Base": None, "Grey": (0.85, 0.87, 0.9), "Warm": (1.0, 0.9, 0.78)},
    # the slate's albedo is near white: the roof colours are dark (measured on the preview street, 2026-10-27)
    "Roof": {"Slate": (0.16, 0.17, 0.19), "BlueSlate": (0.14, 0.17, 0.23), "Terracotta": (0.62, 0.22, 0.12),
             "Brown": (0.3, 0.19, 0.12)},
}


def _m(folder, name, w, fix=False, **kw):
    d = {"mesh": mesh(folder, name), "w": float(w), "kit": folder, "fix": fix}
    d.update(kw)
    return d


def _corner(folder, name, cx, cy, fix=False, **kw):
    return _m(folder, name, cx, fix, cx=float(cx), cy=float(cy), **kw)


# ---- family 02: cream plaster with shutters (1st/2nd/3rd_Floor_Kit_02, 4th/5th_Floor_Kit_00, Trim, Roof_Trim) ----
def _f02(folder, stem, h, s, l, p, c, storey=True, **kw):
    lv = {"h": float(h), "storey": storey,
          "mods": {"S": _m(folder, stem % s, 400), "L": _m(folder, stem % l, 500), "P": _m(folder, stem % p, 50)},
          "corner": _corner(folder, stem % c, 50, 50)}
    lv.update(kw)
    return lv


_G2 = "Modular_Building_1st_Floor_Kit_LOD0_vcknajsdw_%d"
DOOR_00 = _m("Door_00", "ukjsdaidw_LOD0", 300, h=650.0)               # the stone doorway: a 300 slot, 650 tall
GATE = _m("Gate_4_5x7_5_M_00", "ukjsdb1dw_LOD0", 400, h=757.0)        # bay + its two piers, base + 1st floor + trim
F02 = {
    "palette": "Plaster", "end": 50.0, "bays": {"S": 400.0, "L": 500.0, "P": 50.0},
    "levels": {
        "G": _f02("1st_Floor_Kit_02", _G2, 400, 1, 2, 4, 3),
        "TR": _f02("Trim_Kit_00", "Modular_Building_Trim_Kit_LOD0_vcdxfcjdw_%d", 105, 2, 1, 5, 3, storey=False),
        "N": _f02("4th_Floor_Kit_00", "Modular_Building_4th_Floor_Kit_LOD0_vb3hcajdw_%d", 400, 2, 1, 5, 4),
        "U": _f02("2nd_Floor_Kit_02", "Modular_Building_2nd_Floor_Kit_LOD0_vb3hccbdw_%d", 350, 1, 2, 3, 4),
        "U3": _f02("3rd_Floor_Kit_02", "Modular_Building_3rd_Floor_Kit_LOD0_vb3hcczdw_%d", 300, 1, 2, 3, 5),
        "A": _f02("5th_Floor_Kit_00", "Modular_Building_5th_Floor_Kit_LOD0_vb3hbjjdw_%d", 250, 2, 1, 5, 3),
        "RT": _f02("Roof_Trim_Kit_00", "Modular_Building_Roof_Trim_Kit_LOD0_vcegditdw_%d", 100, 1, 2, 5, 4, storey=False),
    },
    # the ground floor's door: the stone doorway at 400 / 650 of its size (a 185 slot), never tinted
    "door": dict(DOOR_00, w=300.0 * 400.0 / 650.0, s=400.0 / 650.0, own=True),
}
# rusticated ground floor: the 1st floor bays between Ground_Corner_Kit_00's deep piers and quoins
F02["levels"]["GC"] = dict(F02["levels"]["G"], mods=dict(
    F02["levels"]["G"]["mods"], P=_m("Ground_Corner_Kit_00", "Modular_Building_Ground_Corner_Kit_LOD0_vb3hca1dw_1", 50)),
    corner=_corner("Ground_Corner_Kit_00", "Modular_Building_Ground_Corner_Kit_LOD0_vb3hca1dw_3", 50, 50))


# ---- family 01: orange brick with cream window surrounds (Ground_*, 1st/2nd/3rd_Floor_Kit_01) ----
def _f01(folder, stem, w, p, c, alt=None, h=350.0):
    lv = {"h": h, "storey": True, "mods": {"W": _m(folder, stem % w, 200), "P": _m(folder, stem % p, 50, fix=True)},
          "corner": _corner(folder, stem % c, 50, 50, fix=True)}
    if alt is not None:
        lv["mods"]["X"] = _m(folder, stem % alt, 200, fix=True)
        lv["alt"] = {"W": ["X"]}
    return lv


_GW = "Modular_Building_Ground_Floor_Window_Kit_LOD0_ulyrfcvdw_Aset_building__M_ulyrfcvdw_%02d_LOD0"
_GD = "Modular_Building_Ground_Door_Kit_LOD0_ulytag0dw_Aset_building__M_ulytag0dw_%02d_LOD0"
F01 = {
    "palette": "Brick", "end": 50.0, "bays": {"W": 200.0, "P": 50.0},
    "levels": {
        "G": _f01("Ground_Floor_Window_Kit_00", _GW, 0, 4, 3),
        "U": _f01("1st_Floor_Kit_01", "Modular_Building_1st_Floor_Kit_LOD0_ulxqchsdw_Aset_building__M_ulxqchsdw_%02d_LOD0",
                  0, 4, 2, alt=1),
        "U2": _f01("2nd_Floor_Kit_01", "Modular_Building_2nd_Floor_Kit_LOD0_ulypdc2dw_Aset_building__M_ulypdc2dw_%02d_LOD0",
                   0, 4, 2, alt=1),
        "T": _f01("3rd_Floor_Kit_01", "Modular_Building_3rd_Floor_Kit_LOD0_ulxqdjodw_Aset_building__M_ulxqdjodw_%02d_LOD0",
                  0, 1, 3),
        # cream stone bands borrowed from family 02 (always their own colour; solved on their own, not on the bay grid)
        "TR": dict(F02["levels"]["TR"], band=True),
        "RT": dict(F02["levels"]["RT"], band=True),
    },
    "door": _m("Ground_Door_Kit_00", _GD % 1, 300, fix=True),             # wooden double door
}
F01["levels"]["G"]["mods"].update({"V": _m("Ground_Floor_Window_Kit_00", _GW % 1, 300, fix=True),   # wide window
                                   "H": _m("Ground_Door_Kit_00", _GD % 0, 350)})                     # door + shop window


# ---- family 00: limestone classical (Foundation, 1st..3rd_Floor_Kit_00, trims, Door_00, Gate) ----
def _f00(folder, stem, h, w, p, c, cx, cy, storey=True, alt=(), extra=None, corner_mesh=True):
    lv = {"h": float(h), "storey": storey, "mods": {"W": _m(folder, stem % w, 300), "P": _m(folder, stem % p, 50)},
          "corner": _corner(folder, stem % c, cx, cy) if corner_mesh else {"mesh": None, "w": cx, "cx": cx, "cy": cy,
                                                                             "kit": folder}}
    if alt:
        for sym, idx in alt:
            lv["mods"][sym] = _m(folder, stem % idx, 300)
        lv["alt"] = {"W": [sym for sym, _i in alt]}
    lv.update(extra or {})
    return lv


F00 = {
    "palette": "Stone", "end": 150.0, "bays": {"W": 300.0, "P": 50.0},
    "levels": {
        "FND": _f00("Foundation_Kit_00", "ukjsehbdw_LOD0_Aset_modular__M_ukjsehbdw_%02d_LOD0", 250, 0, 3, 4, 144, 143,
                    storey=False, alt=(("N", 1), ("O", 2))),
        # the 1st floor's corner pier is 505 tall: it also covers the trim above (T1 has no corner of its own)
        "L1": _f00("1st_Floor_Kit_00", "ukjsefadw_LOD0_Aset_modular__M_ukjsefadw_%02d_LOD0", 400, 1, 2, 0, 129, 142),
        "T1": _f00("1st_Floor_Trim_Kit_00", "ukjsdiodw_LOD0_Aset_modular__M_ukjsdiodw_%02d_LOD0", 100, 0, 1, 0, 129, 142,
                   storey=False, corner_mesh=False),
        "L2": _f00("2nd_Floor_Kit_00", "ukjsdhndw_LOD0_Aset_modular__M_ukjsdhndw_%02d_LOD0", 300, 0, 1, 2, 115, 116),
        "L3": _f00("3rd_Floor_Kit_00", "ukjseahdw_LOD0_Aset_modular__M_ukjseahdw_%02d_LOD0", 450, 0, 1, 3, 106, 106,
                   alt=(("V", 2),)),
        "CR": _f00("4th_Floor_Trim_Kit_00", "ukjsdgodw_LOD0_Aset_modular__M_ukjsdgodw_%02d_LOD0", 163, 3, 2, 1, 150, 150,
                   storey=False),
    },
    "door": DOOR_00, "gate": GATE,
}
FAMILIES = {"F00": F00, "F01": F01, "F02": F02}

# ---- roof: Roof_Kit_00, a hipped slate roof. Measured through its vertices (pyworld_probe_roof_geometry.py): _01 is
# the hip corner -- eaves along both edges through its pivot, the ridge end at (-600, -600); _02 is a valley; a run
# (_04 300, _00 150, _03 300 with a dormer) has its eave on its pivot line (y 0) and the ridge at y -600 ----
_R = "ukjsdfvdw_LOD0_Aset_modular__L_ukjsdfvdw_%02d_LOD0"
ROOF = {"kit": "Roof_Kit_00", "depth": 600.0, "rise": 257.5,
        "corner": _m("Roof_Kit_00", _R % 1, 600), "run": _m("Roof_Kit_00", _R % 4, 300),
        "dormer": _m("Roof_Kit_00", _R % 3, 300)}

# ---- facade props (City Sample's building props) and plain parts ----
BALCONY = _m("Balcony_00", "ukjsdavdw_LOD0", 269)                     # centred, slab top at 0, 138 out
_BP = "/Game/Prop/BLDG/"
LAMPS = [_p(_BP + "Kit_Prop_Lamp/Mesh/SM_BLDG_Prop_Lamp_Wall_%s_N1" % v) for v in ("A01", "A02", "B01", "C01")]
PLAQUES = [_p(_BP + "Kit_Prop_Plaque/Mesh/SM_BLDG_Prop_Plaque_Sign_%s01_N1" % v) for v in "ABCD"]
_AWN_KITS = [("B", "BA"), ("B", "BB"), ("B", "BC"), ("H", "HA"), ("R", "RA"), ("S", "SA"), ("S", "SB"), ("S", "SC")]
AWNINGS = [_p("%s%s/Kit_Prop_%s/Mesh/SM_BLDG_Prop_%s_Awning_%s01_N1" % (_BP, d, k, k, v))
           for d, k in _AWN_KITS for v in "ABCD"]                     # 287 wide, hung from its top edge at z 0
AWNING_W = 287.0
BANNERS = [_p("%s%s/Kit_Prop_%s/Mesh/SM_BLDG_Prop_%s_Banner_A01_N1" % (_BP, d, k, k)) for d, k in _AWN_KITS]
CUBE = _p("/Engine/BasicShapes/Cube")                                 # 100 cm, centred
# the street cross-section (City Sample's sidewalk kit): 300 x 300 slabs, pivot on a corner (x, y 0..300); the plaza
# squares are a 4 cm skin at z 16..20, the sidewalk a 20 cm slab at z 0..20 (pyworld_probe_paving.py)
PAVER = _p("/Game/Road/Kit_Sidewalk_A/Mesh/SM_Plaza_Square_E")        # cobbled setts: the carriageway
SIDEWALK = _p("/Game/Road/Kit_Sidewalk_A/Mesh/SM_Sidewalk_3_3_A")     # light flagstones: the sidewalks
PLAZA_STONE = _p("/Game/Road/Kit_Sidewalk_A/Mesh/SM_Plaza_Square_A")  # hexagonal stone: the plaza
SLAB = 300.0
BRICK = _p("/Game/Building/Material/MI/Brick/MI_Bldg_BrickOffset_Red")
LIMESTONE = _p("/Game/Building/CH/C/Material/MI_Bldg_Block_Limestone_Grey")
# the block behind the windows wears the kit's glass: family 01's frames are open, and a dark block reads as holes
INTERIOR = _p("/Game/Megascans/3D_Assets/Modular_Building_1st_Floor_Kit_01/M_Bldg_glass")


def material(m, tint):
    """Mat0 of one module instance: "" keeps the mesh's own slot-0 material."""
    if tint in (None, "Base") or m.get("own"):
        return inst(m["kit"]) if m.get("fix") else ""
    return tinted(m["kit"], tint)


def materials_needed():
    """[(path, parent, colour)] of every tinted instance the families and the roof can ask for."""
    out, seen = [], set()

    def add(folder, tint, color):
        path = tinted(folder, tint)
        if path not in seen:
            seen.add(path)
            out.append((path, inst(folder), color))
    for f in FAMILIES.values():
        mods = [m for lv in f["levels"].values() if not lv.get("band") for m in list(lv["mods"].values()) + [lv["corner"]]]
        for m in mods + [f[k] for k in ("door", "gate") if k in f]:
            if m.get("mesh") and not m.get("own"):
                for tint, color in TINTS[f["palette"]].items():
                    if color is not None:
                        add(m["kit"], tint, color)
    for tint, color in TINTS["Roof"].items():
        add(ROOF["kit"], tint, color)
    return out
