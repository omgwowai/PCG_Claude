# pyworld_terrain_material.py -- BUILDS AND SAVES /Game/PyPCG/World/M_PyWorldTerrain and MPD_PyWorld: the terrain
# material of MPD_Basic (PCGPrimitives_MeshPartitionInterop, 6 channels Grass Rock ForestFloor Dirt Mud Gravel blended by
# the W9 weights) with each channel's flat colour + text swatch replaced by a photo-scanned Megascans surface
# (world-aligned, two scales against tiling). The engine plugin's own assets are not touched.
# Args: {"assign": true} also puts MPD_PyWorld on the level's MeshPartition actor (L_PyWorld must be open).
import json

import unreal

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
SRC_MAT = "/PCGPrimitives_MeshPartitionInterop/Assets/Materials/M_MeshTerrain_Basic"
SRC_MPD = "/PCGPrimitives_MeshPartitionInterop/Assets/MeshPartitionDefinitions/MPD_Basic"
DST_MAT = "/Game/PyPCG/World/M_PyWorldTerrain"
DST_MPD = "/Game/PyPCG/World/MPD_PyWorld"
S = "/Game/Megascans/Surfaces/"
# channel -> base colour, normal, (roughness texture, channel), (ao texture, channel), tile (cm), tint
LAYERS = {
    "Grass": (S + "MossyGrass/T_MossyGrass_01_BC", S + "MossyGrass/T_MossyGrass_01_N",
              (S + "MossyGrass/T_MossyGrass_01_AoRDp", "G"), (S + "MossyGrass/T_MossyGrass_01_AoRDp", "R"),
              350.0, (0.72, 0.9, 0.55)),
    "Rock": (S + "IcelandicQuarryRock/T_IcelandicQuarryRock_01_BC", S + "RockCliff/T_RockCliff_01_N",
             (S + "IcelandicQuarryRock/T_IcelandicQuarryRock_01_AoRDp", "G"),
             (S + "IcelandicQuarryRock/T_IcelandicQuarryRock_01_AoRDp", "R"), 700.0, (0.75, 0.75, 0.72)),
    "ForestFloor": (S + "NordicMoss/T_NordicMoss_01_BC", S + "NordicMoss/T_NordicMoss_01_N",
                    (S + "NordicMoss/T_NordicMoss_01_AoRDp", "G"), (S + "NordicMoss/T_NordicMoss_01_AoRDp", "R"),
                    300.0, (0.62, 0.58, 0.40)),
    "Dirt": (S + "DriedGrassOnDampSoil/T_DriedGrassOnDampSoil_01_BC", S + "DriedGrassOnDampSoil/T_DriedGrassOnDampSoil_01_N",
             (S + "DriedGrassOnDampSoil/T_DriedGrassOnDampSoil_01_AoRDp", "G"),
             (S + "DriedGrassOnDampSoil/T_DriedGrassOnDampSoil_01_AoRDp", "R"), 400.0, (1.0, 0.95, 0.9)),
    "Mud": (S + "JungleGround/T_JungleGround_01_BC", S + "JungleGround/T_JungleGround_01_N",
            (S + "JungleGround/T_JungleGround_01_AoRDp", "G"), (S + "JungleGround/T_JungleGround_01_AoRDp", "R"),
            300.0, (0.45, 0.4, 0.36)),
    "Gravel": (S + "Gravel_Pebbledash_ugzmbcrn_2K_surface_ms/ugzmbcrn_2K_Albedo",
               S + "Gravel_Pebbledash_ugzmbcrn_2K_surface_ms/ugzmbcrn_2K_Normal",
               (S + "Gravel_Pebbledash_ugzmbcrn_2K_surface_ms/ugzmbcrn_2K_Roughness", "R"),
               (S + "Gravel_Pebbledash_ugzmbcrn_2K_surface_ms/ugzmbcrn_2K_AO", "R"), 250.0, (0.9, 0.88, 0.85)),
}
DESAT = {"Rock": 0.75, "ForestFloor": 0.15}       # take the red out of the quarry rock and the forest floor
TAG = "pyworld_layer"
NEVER = unreal.PropertyAccessChangeNotifyMode.NEVER


def sampler(tex):
    T = unreal.MaterialSamplerType
    vt = bool(tex.get_editor_property("virtual_texture_streaming"))
    cs = tex.get_editor_property("compression_settings")
    if cs == unreal.TextureCompressionSettings.TC_NORMALMAP:
        return T.SAMPLERTYPE_VIRTUAL_NORMAL if vt else T.SAMPLERTYPE_NORMAL
    if cs == unreal.TextureCompressionSettings.TC_ALPHA:
        return T.SAMPLERTYPE_VIRTUAL_ALPHA if vt else T.SAMPLERTYPE_ALPHA
    if cs == unreal.TextureCompressionSettings.TC_GRAYSCALE:
        return T.SAMPLERTYPE_VIRTUAL_GRAYSCALE if vt else T.SAMPLERTYPE_GRAYSCALE
    if cs == unreal.TextureCompressionSettings.TC_MASKS:
        return T.SAMPLERTYPE_VIRTUAL_MASKS if vt else T.SAMPLERTYPE_MASKS
    if not tex.get_editor_property("srgb"):
        return T.SAMPLERTYPE_VIRTUAL_LINEAR_COLOR if vt else T.SAMPLERTYPE_LINEAR_COLOR
    return T.SAMPLERTYPE_VIRTUAL_COLOR if vt else T.SAMPLERTYPE_COLOR


class Builder:
    def __init__(self, m):
        self.m, self.x = m, -3000

    def node(self, cls, y, **props):
        e = MEL.create_material_expression(self.m, cls, self.x, y)
        # NEVER notify: a notified property edit (a texture above all) recompiles the whole material on the spot, and
        # ~100 of them took the editor past 100 GB (2026-10-23). One recompile_material at the end instead.
        e.set_editor_property("desc", TAG, NEVER)
        for k, v in props.items():
            e.set_editor_property(k, v, NEVER)
        return e

    def link(self, a, out, b, inp):
        if not MEL.connect_material_expressions(a, out, b, inp):
            raise RuntimeError("cannot connect %s.%s -> %s.%s" % (a.get_name(), out, b.get_name(), inp))

    def sample(self, path, uv, y):
        tex = unreal.load_asset(path)
        if tex is None:
            raise RuntimeError("missing texture " + path)
        e = self.node(unreal.MaterialExpressionTextureSample, y, texture=tex, sampler_type=sampler(tex))
        self.link(uv, "", e, "UVs")
        return e

    def const(self, v, y):
        return self.node(unreal.MaterialExpressionConstant, y, r=float(v))

    def mask(self, src, out, ch, y):
        e = self.node(unreal.MaterialExpressionComponentMask, y, r=ch == "R", g=ch == "G", b=ch == "B", a=ch == "A")
        self.link(src, out, e, "")
        return e

    def binop(self, cls, a, b, y, aout="", bout=""):
        e = self.node(cls, y)
        self.link(a, aout, e, "A")
        self.link(b, bout, e, "B")
        return e

    def layer(self, name, spec, xy, y0):
        bc, n, (rt, rc), (at, ac), tile, tint = spec
        y = y0
        uv1 = self.binop(unreal.MaterialExpressionMultiply, xy, self.const(1.0 / tile, y), y)
        uv2 = self.binop(unreal.MaterialExpressionMultiply, xy, self.const(1.0 / (tile * 3.7), y + 60), y + 60)
        b1, b2 = self.sample(bc, uv1, y + 120), self.sample(bc, uv2, y + 300)
        lerp = self.node(unreal.MaterialExpressionLinearInterpolate, y + 200)
        self.link(b1, "RGB", lerp, "A")
        self.link(b2, "RGB", lerp, "B")
        self.link(self.const(0.4, y + 260), "", lerp, "Alpha")
        tintc = self.node(unreal.MaterialExpressionConstant3Vector, y + 330, constant=unreal.LinearColor(*tint, 1.0))
        src = lerp
        if DESAT.get(name):
            src = self.node(unreal.MaterialExpressionDesaturation, y + 260)
            self.link(lerp, "", src, "")
            self.link(self.const(DESAT[name], y + 280), "", src, "Fraction")
        base = self.binop(unreal.MaterialExpressionMultiply, src, tintc, y + 220)
        nrm = self.sample(n, uv1, y + 480)
        rough = self.mask(self.sample(rt, uv1, y + 660), "", rc, y + 660)
        ao = self.mask(self.sample(at, uv1, y + 840), "", ac, y + 840) if (at, ac) != (rt, rc) else None
        make = self.node(unreal.MaterialExpressionMakeMaterialAttributes, y + 400)
        self.link(base, "", make, "BaseColor")
        self.link(nrm, "RGB", make, "Normal")
        self.link(rough, "", make, "Roughness")
        if ao is not None:
            self.link(ao, "", make, "AmbientOcclusion")
        self.link(self.const(0.35, y + 900), "", make, "Specular")
        return make


def blend_channels():
    """{blend node name: channel} read from the plugin's own material, where each blend's B input is the channel's
    colour + text swatch (Text_<Channel>); the duplicate keeps the node names."""
    src = unreal.load_asset(SRC_MAT)
    out = {}
    for bl in MEL.get_material_expressions(src):
        if not isinstance(bl, unreal.MaterialExpressionBlendMaterialAttributes):
            continue
        names = [str(n) for n in MEL.get_material_expression_input_names(bl)]
        call = dict(zip(names, MEL.get_inputs_for_material_expression(src, bl))).get("B")
        if call is None:
            continue
        for i in MEL.get_inputs_for_material_expression(src, call):
            if isinstance(i, unreal.MaterialExpressionTextureObject):
                out[bl.get_name()] = i.get_editor_property("texture").get_name().replace("Text_", "")
    return out


def main():
    args = globals().get("mcp_args") or {}
    unreal.AssetRegistryHelpers.get_asset_registry().scan_paths_synchronous(["/Game/Megascans/Surfaces"], True)
    if not EAL.does_asset_exist(DST_MAT):
        EAL.duplicate_asset(SRC_MAT, DST_MAT)
    m = unreal.load_asset(DST_MAT)
    for e in list(MEL.get_material_expressions(m)):          # rebuild: drop what an earlier run added
        if e.get_editor_property("desc") == TAG:
            MEL.delete_material_expression(m, e)
    exprs = list(MEL.get_material_expressions(m))
    calls = [e for e in exprs if isinstance(e, unreal.MaterialExpressionMaterialFunctionCall)
             and "TextureTextColor" in (e.get_editor_property("material_function").get_name()
                                        if e.get_editor_property("material_function") else "")]
    blends = [e for e in exprs if isinstance(e, unreal.MaterialExpressionBlendMaterialAttributes)]
    B = Builder(m)
    wp = B.node(unreal.MaterialExpressionWorldPosition, -400)
    xy = B.mask(wp, "", "R", -300)
    xy.set_editor_property("g", True, NEVER)
    channels = blend_channels()
    done = {}
    for k, bl in enumerate(blends):
        names = [str(n) for n in MEL.get_material_expression_input_names(bl)]
        ins = dict(zip(names, MEL.get_inputs_for_material_expression(m, bl)))
        ch = channels.get(bl.get_name())
        if ch not in LAYERS:
            continue
        B.link(B.layer(ch, LAYERS[ch], xy, k * 1100), "", bl, "B")
        done[ch] = done.get(ch, 0) + 1
    for call in calls:                                       # the flat colour + text swatches, now unused
        MEL.delete_material_expression(m, call)
    if not args.get("compile", True):
        print(json.dumps({"channels": done, "compiled": False}))
        return
    MEL.recompile_material(m)
    EAL.save_asset(DST_MAT, only_if_is_dirty=False)
    if not EAL.does_asset_exist(DST_MPD):
        EAL.duplicate_asset(SRC_MPD, DST_MPD)
    mpd = unreal.load_asset(DST_MPD)
    mpd.set_editor_property("material", m)
    EAL.save_asset(DST_MPD, only_if_is_dirty=False)
    out = {"channels": done, "material": DST_MAT, "mpd": DST_MPD}
    if args.get("assign"):
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        actors = [a for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
                  if "MeshPartition" in a.get_class().get_name()]
        for a in actors:
            try:
                a.set_editor_property("mega_mesh_definition", mpd)
                out.setdefault("assigned", []).append(a.get_actor_label())
            except Exception as ex:
                out.setdefault("assign_errors", []).append(str(ex)[:120])
    print(json.dumps(out, indent=1))


if __name__ != "pyworld_terrain_material":       # importable for its LAYERS table
    main()
