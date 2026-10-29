# pyinterior_materials.py -- PyInterior's materials (docs/superpowers/specs/2026-10-28-pyinterior-design.md 4.9):
# two masters in /Game/PyPCG/Interior/Materials -- M_PyInt_Color (BaseColor / Roughness / Metallic) and M_PyInt_WorldTex
# (a StarterContent texture projected on world XY, so stretched boxes keep one texel density) -- and one instance per
# colour (pypcg.interior.program.COLORS) and per floor (FLOOR_MATERIALS). Args: {"rebuild": true} rebuilds the masters.
# Expression edits use NEVER notify and one recompile per master (traps 100). Saves what it makes.
import json
import sys

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
from pypcg.interior import program as P  # noqa: E402

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
NEVER = unreal.PropertyAccessChangeNotifyMode.NEVER
DIR = "/Game/PyPCG/Interior/Materials"
TEX = "/Game/StarterContent/Textures/"
FLOORS = {     # name: (texture, tile size cm, tint, roughness)
    "Floor_Oak": ("T_Wood_Oak_D", 160.0, (1.0, 1.0, 1.0), 0.55),
    "Floor_Walnut": ("T_Wood_Floor_Walnut_D", 220.0, (1.0, 1.0, 1.0), 0.45),
    "Floor_WalnutWorn": ("T_Wood_Floor_Walnut_D", 220.0, (0.78, 0.74, 0.70), 0.6),
    "Floor_Pine": ("T_Wood_Pine_D", 160.0, (1.0, 1.0, 1.0), 0.6),
    "Tile_White": ("T_Concrete_Tiles_D", 120.0, (1.35, 1.35, 1.32), 0.25),
    "Tile_Checker": ("T_Concrete_Tiles_D", 80.0, (1.2, 1.1, 0.95), 0.3),
    "Tile_Grey": ("T_Concrete_Tiles_D", 120.0, (0.85, 0.86, 0.88), 0.35),
    "Concrete": ("T_Concrete_Poured_D", 300.0, (1.0, 1.0, 1.0), 0.8),
}


def linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def sampler(tex):
    T = unreal.MaterialSamplerType
    vt = bool(tex.get_editor_property("virtual_texture_streaming"))
    if not tex.get_editor_property("srgb"):
        return T.SAMPLERTYPE_VIRTUAL_LINEAR_COLOR if vt else T.SAMPLERTYPE_LINEAR_COLOR
    return T.SAMPLERTYPE_VIRTUAL_COLOR if vt else T.SAMPLERTYPE_COLOR


def node(m, cls, x, y, **props):
    e = MEL.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v, NEVER)
    return e


def link(a, out, b, inp):
    if not MEL.connect_material_expressions(a, out, b, inp):
        raise RuntimeError("cannot connect %s.%s -> %s.%s" % (a.get_name(), out, b.get_name(), inp))


def fresh(name, rebuild):
    path = "%s/%s" % (DIR, name)
    if EAL.does_asset_exist(path):
        m = unreal.load_asset(path)
        if not rebuild:
            return m, False
        MEL.delete_all_material_expressions(m)
        return m, True
    m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DIR, unreal.Material, unreal.MaterialFactoryNew())
    if m is None:
        raise RuntimeError("could not create " + path)
    return m, True


def master_color(rebuild):
    m, build = fresh("M_PyInt_Color", rebuild)
    if build:
        base = node(m, unreal.MaterialExpressionVectorParameter, -500, -100, parameter_name="BaseColor",
                    default_value=unreal.LinearColor(0.7, 0.7, 0.7, 1.0))
        rough = node(m, unreal.MaterialExpressionScalarParameter, -500, 100, parameter_name="Roughness", default_value=0.6)
        metal = node(m, unreal.MaterialExpressionScalarParameter, -500, 200, parameter_name="Metallic", default_value=0.0)
        MEL.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
        MEL.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
        MEL.connect_material_property(metal, "", unreal.MaterialProperty.MP_METALLIC)
        MEL.recompile_material(m)
        EAL.save_asset(m.get_path_name().split(".")[0], only_if_is_dirty=False)
    return m


def master_worldtex(rebuild):
    m, build = fresh("M_PyInt_WorldTex", rebuild)
    if build:
        tex = unreal.load_asset(TEX + "T_Wood_Oak_D")
        if tex is None:
            raise RuntimeError("no StarterContent texture: run Tools/pyinterior/starter_closure.py --copy")
        wp = node(m, unreal.MaterialExpressionWorldPosition, -1200, 0)
        xy = node(m, unreal.MaterialExpressionComponentMask, -1000, 0, r=True, g=True, b=False, a=False)
        link(wp, "", xy, "")
        size = node(m, unreal.MaterialExpressionScalarParameter, -1000, 150, parameter_name="TileSize", default_value=200.0)
        uv = node(m, unreal.MaterialExpressionDivide, -800, 0)
        link(xy, "", uv, "A")
        link(size, "", uv, "B")
        sample = node(m, unreal.MaterialExpressionTextureSampleParameter2D, -600, 0, parameter_name="Albedo", texture=tex,
                      sampler_type=sampler(tex))
        link(uv, "", sample, "UVs")
        tint = node(m, unreal.MaterialExpressionVectorParameter, -600, 250, parameter_name="Tint",
                    default_value=unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
        rgb = node(m, unreal.MaterialExpressionComponentMask, -450, 250, r=True, g=True, b=True, a=False)
        link(tint, "", rgb, "")
        mul = node(m, unreal.MaterialExpressionMultiply, -300, 0)
        link(sample, "RGB", mul, "A")
        link(rgb, "", mul, "B")
        rough = node(m, unreal.MaterialExpressionScalarParameter, -300, 200, parameter_name="Roughness", default_value=0.5)
        MEL.connect_material_property(mul, "", unreal.MaterialProperty.MP_BASE_COLOR)
        MEL.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
        MEL.recompile_material(m)
        EAL.save_asset(m.get_path_name().split(".")[0], only_if_is_dirty=False)
    return m


def instance(name, parent):
    path = "%s/MI_PyInt_%s" % (DIR, name)
    if EAL.does_asset_exist(path):
        mi = unreal.load_asset(path)
    else:
        mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset("MI_PyInt_%s" % name, DIR,
                                                                     unreal.MaterialInstanceConstant,
                                                                     unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, parent)
    return mi, path


def main():
    args = mcp_args or {}
    unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/Game/StarterContent"], True)
    rebuild = bool(args.get("rebuild"))
    color, world = master_color(rebuild), master_worldtex(rebuild)
    made = []
    for name, rgb in P.COLORS.items():
        mi, path = instance(name, color)
        MEL.set_material_instance_vector_parameter_value(mi, "BaseColor",
                                                         unreal.LinearColor(*(linear(c) for c in rgb), 1.0))
        rough, metal = P.SURFACE.get(name, (0.6, 0.0))
        MEL.set_material_instance_scalar_parameter_value(mi, "Roughness", rough)
        MEL.set_material_instance_scalar_parameter_value(mi, "Metallic", metal)
        MEL.update_material_instance(mi)
        EAL.save_loaded_asset(mi, False)
        made.append(name)
    missing_tex = []
    for name in P.FLOOR_MATERIALS:
        tex_name, size, tint, rough = FLOORS[name]
        tex = unreal.load_asset(TEX + tex_name)
        if tex is None:
            missing_tex.append(tex_name)
            continue
        mi, path = instance(name, world)
        MEL.set_material_instance_texture_parameter_value(mi, "Albedo", tex)
        MEL.set_material_instance_scalar_parameter_value(mi, "TileSize", size)
        MEL.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(tint[0], tint[1], tint[2], 1.0))
        MEL.set_material_instance_scalar_parameter_value(mi, "Roughness", rough)
        MEL.update_material_instance(mi)
        EAL.save_loaded_asset(mi, False)
        made.append(name)
    return {"instances": len(made), "missing_textures": missing_tex, "dir": DIR}


mcp_result = json.loads(json.dumps(main(), default=str))
