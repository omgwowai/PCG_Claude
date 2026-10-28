"""Writes Saved/Reports/kit_test_items.json: a test assembly of the Megascans Modular_Building kit for
Content/Python/pyworld_kit_test.py {"file": "Saved/Reports/kit_test_items.json"} (identification rows, roof material
swatches, a native-scale hip roof from Roof_Kit_00 and a gable roof from Roof_Kit_01). Throwaway exploration aid."""
import json
import math
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KIT = "/Game/Megascans/3D_Assets/Modular_Building_"


def mesh(folder, name):
    return KIT + folder + "/" + name


def inst(folder):
    return KIT + folder + "/Modular_Building_" + folder + "_inst"


F02_G = "Modular_Building_1st_Floor_Kit_LOD0_vcknajsdw_%d"
F02_4 = "Modular_Building_4th_Floor_Kit_LOD0_vb3hcajdw_%d"
F02_5 = "Modular_Building_5th_Floor_Kit_LOD0_vb3hbjjdw_%d"
F01_D = "Modular_Building_Ground_Door_Kit_LOD0_ulytag0dw_Aset_building__M_ulytag0dw_%02d_LOD0"
F01_W = "Modular_Building_Ground_Floor_Window_Kit_LOD0_ulyrfcvdw_Aset_building__M_ulyrfcvdw_%02d_LOD0"
F00_F = "ukjsehbdw_LOD0_Aset_modular__M_ukjsehbdw_%02d_LOD0"
R00 = "ukjsdfvdw_LOD0_Aset_modular__L_ukjsdfvdw_%02d_LOD0"
R01 = "Modular_Building_Roof_Kit_LOD0_ulxqdfsdw_Aset_building__M_ulxqdfsdw_%02d_LOD0"
GAB = "Modular_Building_Gable_Kit_LOD0_ulxqdc1dw_Aset_building__M_ulxqdc1dw_%02d_LOD0"
PLANE = "/Engine/BasicShapes/Plane"


def row(items, z, pieces, x0=0.0, gap=100.0):
    """pieces [(mesh, width, mats)] side by side along +X at height z, facing +Y."""
    x = x0
    for m, w, mats in pieces:
        items.append([m, [x, 0.0, z], 0.0, [1, 1, 1], mats])
        x += w + gap
    return x


def ring_cw(w, d, cx=0.0, cy=0.0):
    hw, hd = 0.5 * w, 0.5 * d
    ccw = [(cx - hw, cy - hd), (cx + hw, cy - hd), (cx + hw, cy + hd), (cx - hw, cy + hd)]
    return ccw[::-1]


def main():
    items = []
    # identification rows (z 0 / 900 / 1800), facing +Y
    row(items, 0.0, [(mesh("1st_Floor_Kit_02", F02_G % 1), 400, []), (mesh("1st_Floor_Kit_02", F02_G % 2), 500, []),
                     (mesh("4th_Floor_Kit_00", F02_4 % 1), 500, []), (mesh("4th_Floor_Kit_00", F02_4 % 2), 400, []),
                     (mesh("5th_Floor_Kit_00", F02_5 % 1), 500, []), (mesh("5th_Floor_Kit_00", F02_5 % 2), 400, [])])
    row(items, 900.0, [(mesh("Ground_Door_Kit_00", F01_D % 0), 350, []),
                       (mesh("Ground_Door_Kit_00", F01_D % 1), 300, [inst("Ground_Door_Kit_00")]),
                       (mesh("Ground_Floor_Window_Kit_00", F01_W % 0), 200, []),
                       (mesh("Ground_Floor_Window_Kit_00", F01_W % 1), 300, [inst("Ground_Floor_Window_Kit_00")]),
                       (KIT + "Door_00/ukjsdaidw_LOD0", 344, []), (KIT + "Gate_4_5x7_5_M_00/ukjsdb1dw_LOD0", 460, [])])
    row(items, 1800.0, [(mesh("Foundation_Kit_00", F00_F % 0), 300, []), (mesh("Foundation_Kit_00", F00_F % 1), 300, []),
                        (mesh("Foundation_Kit_00", F00_F % 2), 300, []),
                        (KIT + "Base_3x2_5_M_00/ukjseeddw_LOD0", 300, []), (KIT + "Base_3x2_5_M_01/ukjscecdw_LOD0", 300, []),
                        ("/Game/Prop/BLDG/Kit_Prop_Lamp/Mesh/SM_BLDG_Prop_Lamp_Wall_A01_N1", 100, []),
                        (KIT + "Balcony_00/ukjsdavdw_LOD0", 280, []),
                        ("/Game/Prop/BLDG/S/Mesh/SM_BLDG_Prop_SA_Awning_A01_N1", 300, []),
                        ("/Game/Prop/BLDG/B/Mesh/SM_BLDG_Prop_BA_Awning_A01_N1", 300, [])])
    # material swatches: 4 x 4 m planes lying flat at x 6000.., y 0
    for i, m in enumerate(["/Game/Environment/RoofTop/Material/MI/MI_Rooftop_RoofTile", inst("Roof_Kit_00"), inst("Roof_Kit_01"),
                           "/Game/Building/Material/MI/Brick/MI_Bldg_BrickOffset_Red",
                           "/Game/Building/SF/D/Material/MI_Bldg_PaintedStone_White",
                           "/Game/Building/CH/A/Material/MI_Bldg_Block_Limestone_Beige"]):
        items.append([PLANE, [6000.0 + 500.0 * i, -1500.0, 0.0], 0.0, [4, 4, 1], [m]])
    # hip roof (Roof_Kit_00) at native scale over a 1800 x 1200 footprint centred at (2000, -2500)
    ring = ring_cw(1800.0, 1200.0, 2000.0, -2500.0)
    for i in range(4):
        p, q = ring[i], ring[(i + 1) % 4]
        yaw = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
        ux, uy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        items.append([mesh("Roof_Kit_00", R00 % 2), [p[0], p[1], 0.0], yaw, [1, 1, 1], []])
        length = math.hypot(q[0] - p[0], q[1] - p[1])
        s = 600.0
        while s < length - 600.0 - 1.0:
            items.append([mesh("Roof_Kit_00", R00 % 4), [p[0] + ux * s, p[1] + uy * s, 0.0], yaw, [1, 1, 1], []])
            s += 300.0
    # gable roof (Roof_Kit_01) at native scale over a 400 x 417.4 footprint at (6000, -4000), ridge along X
    gx, gy, half = 6000.0, -4000.0, 208.7
    for k in range(2):
        items.append([mesh("Roof_Kit_01", R01 % 1), [gx + 200.0 * k, gy + half, 0.0], 0.0, [1, 1, 1], [inst("Roof_Kit_01")]])
        items.append([mesh("Roof_Kit_01", R01 % 1), [gx + 400.0 - 200.0 * k, gy - half, 0.0], 180.0, [1, 1, 1],
                      [inst("Roof_Kit_01")]])
    for end in (0.0, 400.0):
        items.append([mesh("Gable_Kit_00", GAB % 1), [gx + end, gy + half, 0.0], 0.0, [1, 1, 1], [inst("Gable_Kit_00")]])
        items.append([mesh("Gable_Kit_00", GAB % 1), [gx + end, gy - half, 0.0], 180.0, [1, 1, 1], [inst("Gable_Kit_00")]])
    # the dormer slope and the strip next to the gable test
    items.append([mesh("Roof_Kit_01", R01 % 0), [gx + 800.0, gy + half, 0.0], 0.0, [1, 1, 1], []])
    items.append([mesh("Roof_Kit_01", R01 % 2), [gx + 1100.0, gy + half, 0.0], 0.0, [1, 1, 1], [inst("Roof_Kit_01")]])
    items.append([mesh("Gable_Kit_00", GAB % 0), [gx + 1300.0, gy + half, 0.0], 0.0, [1, 1, 1], []])
    items.append([mesh("Gable_Kit_00", GAB % 2), [gx + 1500.0, gy + half, 0.0], 0.0, [1, 1, 1], [inst("Gable_Kit_00")]])
    out = os.path.join(ROOT, "Saved", "Reports", "kit_test_items.json")
    with open(out, "w") as fh:
        json.dump(items, fh, indent=0)
    print(len(items), out)


if __name__ == "__main__":
    sys.exit(main())
