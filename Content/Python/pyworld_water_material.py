# pyworld_water_material.py -- BUILDS AND SAVES /Game/PyPCG/World/M_PyWorldStream, the material of the continuous
# river surface W3 emits (a dynamic mesh: UV0 in metres, U downstream; vertex colour R = 1 on the centre line .. 0 at
# the water's edge, G = flow speed 0..1). Single Layer Water: refraction, scattering and absorption, so the gravel bed
# shows through the shallows and the middle of the channel darkens to green; two normal maps panning downstream at
# different scales and speeds (the classic flowing-water trick of river shaders), faster in the middle and on steep
# reaches; a little foam only where the water runs fast near the banks.
#
# Two measured traps (2026-10-26/27, traps 102-104):
# - SLW coefficients are per CENTIMETRE (MaterialExpressionSingleLayerWaterMaterialOutput.h): clear-to-greenish
#   stream water is ~0.01-0.03 /cm; values of 1+ /cm make every centimetre opaque, and depth never shows.
# - the SLW Opacity input defaults to 1 = an opaque surface (a dark mirror): wire it (0 = volumetric water).
# - a PCG dynamic mesh component reports no texture streaming data, so a streamed normal map stays at its lowest,
#   flat mips: the surface is a perfect mirror. The normal map is copied into /Game with NeverStream.
# Built node by node with NEVER notification and one compile (trap 100). {"scatter": [r, g, b], "absorb": [..],
# "nflat": k} override the constants; {"debug_emissive": "uv" | "normal"} shows UV / the normal as an opaque colour.
import json

import unreal

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
PATH = "/Game/PyPCG/World/M_PyWorldStream"
NEVER = unreal.PropertyAccessChangeNotifyMode.NEVER
SCATTER = (0.0025, 0.0045, 0.0035)          # 1/cm
ABSORB = (0.03, 0.012, 0.016)               # 1/cm: red goes first, so depth turns the water green
NFLAT = 1.0                                 # the summed normals' x, y scale: < 1 calms the surface, > 1 roughens it
SOURCE_NORMAL = "/Water/Textures/Normals/T_Water_TilingNormal_Waves_02"
NORMAL = "/Game/PyPCG/World/T_PyWorldWaterNormal"


class G:
    def __init__(self, m):
        self.m = m

    def node(self, cls, x, y, **props):
        e = MEL.create_material_expression(self.m, cls, x, y)
        for k, v in props.items():
            e.set_editor_property(k, v, NEVER)
        return e

    def c(self, v, x, y):
        return self.node(unreal.MaterialExpressionConstant, x, y, r=float(v))

    def v3(self, rgb, x, y):
        return self.node(unreal.MaterialExpressionConstant3Vector, x, y, constant=unreal.LinearColor(*rgb, 1.0))

    def link(self, a, out, b, inp):
        if not MEL.connect_material_expressions(a, out, b, inp):
            raise RuntimeError("cannot connect %s.%s -> %s.%s" % (a.get_name(), out, b.get_name(), inp))

    def op(self, cls, a, b, x, y, aout="", bout=""):
        e = self.node(cls, x, y)
        self.link(a, aout, e, "A")
        self.link(b, bout, e, "B")
        return e


def normal_texture():
    """The water normal map, copied into /Game with NeverStream (a dynamic mesh never asks the streamer for mips)."""
    if not EAL.does_asset_exist(NORMAL):
        EAL.duplicate_asset(SOURCE_NORMAL, NORMAL)
    t = unreal.load_asset(NORMAL)
    if not t.get_editor_property("never_stream"):
        t.set_editor_property("never_stream", True)
        EAL.save_asset(NORMAL, only_if_is_dirty=False)
    return t


def main():
    args = globals().get("mcp_args") or {}
    scatter, absorb = tuple(args.get("scatter", SCATTER)), tuple(args.get("absorb", ABSORB))
    nflat = float(args.get("nflat", NFLAT))
    # rebuild in place: deleting a material a mesh still uses leaves the old object behind and create_asset then
    # returns None
    if EAL.does_asset_exist(PATH):
        m = unreal.load_asset(PATH)
        MEL.delete_all_material_expressions(m)
        # delete_all leaves custom outputs (the Single Layer Water output) behind; a second one fails the compile
        for e in list(MEL.get_material_expressions(m)):
            MEL.delete_material_expression(m, e)
        if MEL.get_material_expressions(m):
            raise RuntimeError("%d expressions survived the clear" % len(MEL.get_material_expressions(m)))
    else:
        m = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            PATH.rsplit("/", 1)[1], PATH.rsplit("/", 1)[0], unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_SINGLE_LAYER_WATER, NEVER)
    m.set_editor_property("two_sided", False, NEVER)
    # world-space normal: the surface is near horizontal, and the tangents of a PCG dynamic mesh are a fallback basis
    m.set_editor_property("tangent_space_normal", False, NEVER)
    g = G(m)
    nrm_tex = normal_texture()
    uv = g.node(unreal.MaterialExpressionTextureCoordinate, -2400, 0)
    vc = g.node(unreal.MaterialExpressionVertexColor, -2400, 400)
    t = g.node(unreal.MaterialExpressionTime, -2400, 800)
    centre = g.node(unreal.MaterialExpressionComponentMask, -2200, 400, r=True, g=False, b=False, a=False)
    g.link(vc, "", centre, "")
    flow = g.node(unreal.MaterialExpressionComponentMask, -2200, 500, r=False, g=True, b=False, a=False)
    g.link(vc, "", flow, "")
    # speed: (0.35 + 0.65 x centre weight) x (0.6 + flow speed); U runs downstream
    sp = g.op(unreal.MaterialExpressionMultiply, g.op(unreal.MaterialExpressionAdd, g.c(0.35, -2100, 300),
                                                       g.op(unreal.MaterialExpressionMultiply, centre,
                                                            g.c(0.65, -2100, 450), -2000, 400), -1900, 350),
              g.op(unreal.MaterialExpressionAdd, flow, g.c(0.6, -2100, 600), -2000, 550), -1800, 450)
    layers = []
    # scale = tiles per metre, speed = tiles per second at sp = 1: ~2.5 m swells at ~1 m/s and ~0.8 m ripples
    for k, (scale, speed, y0) in enumerate(((0.4, 0.42, 0), (1.25, 1.1, 700))):
        su = g.op(unreal.MaterialExpressionMultiply, uv, g.c(scale, -1700, y0 - 100), -1600, y0)
        shift = g.op(unreal.MaterialExpressionMultiply, g.op(unreal.MaterialExpressionMultiply, t, sp, -1600, y0 + 200),
                     g.c(-speed, -1700, y0 + 300), -1500, y0 + 250)
        off = g.node(unreal.MaterialExpressionAppendVector, -1400, y0 + 250)
        g.link(shift, "", off, "A")
        g.link(g.c(0.03 * k, -1500, y0 + 350), "", off, "B")
        uvk = g.op(unreal.MaterialExpressionAdd, su, off, -1300, y0)
        s = g.node(unreal.MaterialExpressionTextureSample, -1150, y0, texture=nrm_tex,
                   sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
        g.link(uvk, "", s, "UVs")
        layers.append(s)
    nsum = g.op(unreal.MaterialExpressionAdd, layers[0], layers[1], -900, 300, "RGB", "RGB")
    flat = g.op(unreal.MaterialExpressionMultiply, nsum, g.v3((nflat, nflat, 1.0), -900, 450), -750, 350)
    nn = g.node(unreal.MaterialExpressionNormalize, -600, 350)
    g.link(flat, "", nn, "")
    MEL.connect_material_property(nn, "", unreal.MaterialProperty.MP_NORMAL)
    # foam: only near the edges where the water runs fast, broken up by the small ripples
    edge = g.op(unreal.MaterialExpressionSubtract, g.c(1.0, -1000, 900), centre, -900, 900)
    edge2 = g.node(unreal.MaterialExpressionPower, -800, 950)
    g.link(edge, "", edge2, "Base")
    g.link(g.c(8.0, -900, 1000), "", edge2, "Exp")
    brk = g.op(unreal.MaterialExpressionMultiply, edge2, layers[1], -650, 950, "", "R")
    fast = g.op(unreal.MaterialExpressionMultiply, brk, flow, -560, 950)
    foam = g.node(unreal.MaterialExpressionSaturate, -500, 950)
    g.link(g.op(unreal.MaterialExpressionMultiply, fast, g.c(1.6, -650, 1050), -540, 1000), "", foam, "")
    base = g.node(unreal.MaterialExpressionLinearInterpolate, -400, 1150)
    g.link(g.v3((0.02, 0.03, 0.025), -600, 1150), "", base, "A")
    g.link(g.v3((0.55, 0.57, 0.55), -600, 1250), "", base, "B")
    g.link(foam, "", base, "Alpha")
    MEL.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    rough = g.node(unreal.MaterialExpressionLinearInterpolate, -400, 1350)
    g.link(g.c(0.04, -600, 1350), "", rough, "A")
    g.link(g.c(0.5, -600, 1420), "", rough, "B")
    g.link(foam, "", rough, "Alpha")
    MEL.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(g.c(0.35, -400, 1500), "", unreal.MaterialProperty.MP_SPECULAR)
    # SLW opacity: 0 = volumetric water over the refracted bed, 1 = an opaque surface; only the foam is opaque
    MEL.connect_material_property(foam, "", unreal.MaterialProperty.MP_OPACITY)
    if args.get("debug_emissive"):
        if args["debug_emissive"] == "uv":
            fr = g.node(unreal.MaterialExpressionFrac, -300, 1900)
            g.link(uv, "", fr, "")
            show = g.op(unreal.MaterialExpressionMultiply, fr, g.c(0.3, -300, 2000), -100, 2000)
        else:
            half = g.op(unreal.MaterialExpressionMultiply, nn, g.v3((0.3, 0.3, 0.0), -300, 2000), -200, 2000)
            show = g.op(unreal.MaterialExpressionAdd, half, g.c(0.2, -300, 2100), -100, 2000)
        MEL.connect_material_property(show, "", unreal.MaterialProperty.MP_BASE_COLOR)
        MEL.connect_material_property(g.c(1.0, -300, 2200), "", unreal.MaterialProperty.MP_OPACITY)
    w = g.node(unreal.MaterialExpressionSingleLayerWaterMaterialOutput, -200, 1700)
    names = [str(n) for n in MEL.get_material_expression_input_names(w)]
    g.link(g.v3(scatter, -500, 1650), "", w, names[0])      # scattering (1/cm)
    g.link(g.v3(absorb, -500, 1750), "", w, names[1])       # absorption (1/cm)
    g.link(g.c(0.15, -500, 1850), "", w, names[2])          # phase G
    MEL.recompile_material(m)
    EAL.save_asset(PATH, only_if_is_dirty=False)
    st = MEL.get_statistics(m)
    print(json.dumps({"inputs": names, "pixel_instructions": st.num_pixel_shader_instructions,
                      "normal_never_stream": bool(nrm_tex.get_editor_property("never_stream")),
                      "scatter": scatter, "absorb": absorb}, indent=1))


main()
