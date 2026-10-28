# pyworld_kit_catalog.py -- a temporary wall of the Megascans Modular_Building meshes over the sea south of the
# valley, to identify each part's role in a screenshot; {"clear": true} removes it (actors PyWorldKit_*, never saved).
# {"family": "00" | "01" | "02"}: one row per kit folder of that family (rows stacked upwards 6 m apart, parts 6.5 m
# apart along X, exteriors facing +Y). Prints the layout (row -> folder, column -> mesh) and the shot centre.
import json

import unreal

AR = unreal.AssetRegistryHelpers.get_asset_registry()
SM = unreal.TopLevelAssetPath("/Script/Engine", "StaticMesh")
ROOT = "/Game/Megascans/3D_Assets/"
X0, Y0, Z0 = -60000.0, -180000.0, 300.0
DX, DZ = 650.0, 600.0
FAMILY = {
    "00": ["1st_Floor_Kit_00", "1st_Floor_3x4_M_00", "1st_Floor_Wall_3x4_M_00", "1st_Floor_Window_3x3_M_00",
           "2nd_Floor_Kit_00", "3rd_Floor_Kit_00", "1st_Floor_Trim_Kit_00", "4th_Floor_Trim_Kit_00", "Foundation_Kit_00",
           "Base_3x2_5_M_00", "Base_3x2_5_M_01", "Base_Straight_Pillar_00", "Roof_Kit_00", "Door_00", "Gate_4_5x7_5_M_00",
           "Balcony_00", "Window_3x3_5_M_00", "Window_3x4_5_M_00", "Window_3x4_5_M_01"],
    "01": ["1st_Floor_Kit_01", "2nd_Floor_Kit_01", "3rd_Floor_Kit_01", "Gable_Kit_00", "Roof_Kit_01", "Ground_Door_Kit_00",
           "Ground_Floor_Window_Kit_00"],
    "02": ["1st_Floor_Kit_02", "2nd_Floor_Kit_02", "3rd_Floor_Kit_02", "4th_Floor_Kit_00", "5th_Floor_Kit_00",
           "Ground_Corner_Kit_00", "Roof_Trim_Kit_00", "Trim_Kit_00"],
}


def main():
    args = globals().get("mcp_args") or {}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for a in eas.get_all_level_actors():
        if str(a.get_actor_label()).startswith("PyWorldKit_"):
            eas.destroy_actor(a)
    if args.get("clear"):
        print(json.dumps({"cleared": True}))
        return
    rows = FAMILY[args.get("family", "00")]
    if "rows" in args:                                       # a slice of the family: [first, last)
        rows = rows[args["rows"][0]:args["rows"][1]]
    layout, width = {}, 0
    for r, folder in enumerate(rows):
        pkgs = sorted(str(a.package_name) for a in AR.get_assets(unreal.ARFilter(
            package_paths=[ROOT + "Modular_Building_" + folder], recursive_paths=True, class_paths=[SM])))
        layout[r] = {"folder": folder, "meshes": [p.rsplit("/", 1)[1] for p in pkgs]}
        width = max(width, len(pkgs))
        for c, pkg in enumerate(pkgs):
            a = eas.spawn_actor_from_class(unreal.StaticMeshActor, unreal.Vector(X0 + c * DX, Y0, Z0 + r * DZ),
                                           unreal.Rotator())
            mesh = unreal.load_asset(pkg)
            a.static_mesh_component.set_static_mesh(mesh)
            a.set_actor_label("PyWorldKit_%s_%d_%d" % (folder, r, c))
            b = mesh.get_bounding_box()
            t = eas.spawn_actor_from_class(unreal.TextRenderActor, unreal.Vector(X0 + c * DX, Y0 + 200.0, Z0 + r * DZ + 520.0),
                                           unreal.Rotator(0.0, -90.0, 0.0))
            t.set_actor_label("PyWorldKit_label_%d_%d" % (r, c))
            tc = t.text_render
            tc.set_text("%d.%d  %dx%d" % (r, c, round(b.max.x - b.min.x), round(b.max.z - b.min.z)))
            tc.set_world_size(60.0)
            tc.set_text_render_color(unreal.Color(255, 230, 40, 255))
    centre = [X0 + 0.5 * (width - 1) * DX, Y0, Z0 + 0.5 * len(rows) * DZ]
    print(json.dumps({"rows": layout, "centre": centre, "half_extent": max(0.5 * width * DX, 0.5 * len(rows) * DZ)}))


main()
