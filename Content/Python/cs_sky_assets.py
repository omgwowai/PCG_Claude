# cs_sky_assets.py -- build the assets of the City Sample clear-sky setup under /Game/CitySampleSky:
#   Textures/T_CS_CloudShape_Atlas, T_CS_CloudDetail_Atlas, T_CS_CloudWeather   (imported from
#       Saved/CitySampleSky/noise/*.png, written by Tools/cs_sky/gen_cloud_noise.py)
#   Textures/VT_CS_CloudShape (128^3 RGBA), Textures/VT_CS_CloudDetail (64^3 RGB)   volume textures from the atlases
#   M_CS_CumulusCloud    volumetric-cloud material (Volume domain, Custom-HLSL cumulus density, multi-scattering output)
#   MI_CS_CumulusCloud_Clear   its instance used by the scene
#   M_CS_NightSky, MI_CS_NightSky   unlit sky material for the night weathers: the atmosphere and the light disk (the
#       moon) drawn by the material, plus the SeasonalWeather star map x StarIntensity (cs_weather.py puts it on a dome)
#
# Always runs deferred on the next Slate tick (the PNG import goes through Interchange, whose synchronous wait trips the
# TaskGraph recursion guard inside a bridge call -- see CLAUDE.md, SeasonalWeather paragraph). The result lands in
# Saved/Reports/cs_weather/assets_result.json.
#
# Args: {"phase": "all" | "textures" | "material" | "nightsky" | "probe"}
#   probe: build the v2 graph into the scratch material M_CS_CloudV2Probe, report its stats, delete it
import gc
import importlib
import json
import os
import time
import traceback

import unreal

import cs_cloud_code as CC

importlib.reload(CC)

ROOT = "/Game/CitySampleSky"
TEX_DIR = ROOT + "/Textures"
MATERIAL = ROOT + "/M_CS_CumulusCloud"
INSTANCE = ROOT + "/MI_CS_CumulusCloud_Clear"
NIGHT_SKY = ROOT + "/M_CS_NightSky"
NIGHT_SKY_MI = ROOT + "/MI_CS_NightSky"
PROBE = ROOT + "/M_CS_CloudV2Probe"            # the spike's scratch material (phase probe), deleted after use
STAR_MAP = "/SeasonalWeather/Textures/T_WeatherStars"     # built by weather.py assets (Tools/weather/gen_starmap.py)
NOISE_DIR = os.path.abspath(os.path.join(unreal.Paths.project_saved_dir(), "CitySampleSky", "noise"))
REPORT = os.path.abspath(os.path.join(unreal.Paths.project_saved_dir(), "Reports", "cs_weather", "assets_result.json"))
NEVER = unreal.PropertyAccessChangeNotifyMode.NEVER

# name -> (png, mips)
TEXTURES = {
    "T_CS_CloudShape_Atlas": ("T_CS_CloudShape_Atlas.png", False),
    "T_CS_CloudDetail_Atlas": ("T_CS_CloudDetail_Atlas.png", False),
    "T_CS_CloudWeather": ("T_CS_CloudWeather.png", True),
}
# volume name -> (atlas name, tile size)
VOLUMES = {"VT_CS_CloudShape": ("T_CS_CloudShape_Atlas", 128), "VT_CS_CloudDetail": ("T_CS_CloudDetail_Atlas", 64)}

# The cloud material's parameter tables and HLSL live in cs_cloud_code.py (v2, 2026-11-12: two slots, absolute altitude,
# time inputs -- docs/superpowers/specs/2026-11-12-cs-cloud-motion-design.md §2).


def _save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, default=str)


def _tools():
    return unreal.AssetToolsHelpers.get_asset_tools()


def _load_or_create(path, cls, factory):
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        return unreal.EditorAssetLibrary.load_asset(path), False
    folder, name = path.rsplit("/", 1)
    return _tools().create_asset(name, folder, cls, factory), True


def _import_texture(name, png):
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", os.path.join(NOISE_DIR, png))
    task.set_editor_property("destination_path", TEX_DIR)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    _tools().import_asset_tasks([task])
    return [str(p) for p in task.get_editor_property("imported_object_paths")]


def _configure_texture(tex, mips):
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP if mips
                            else unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    tex.set_editor_property("never_stream", True)
    tex.set_editor_property("address_x", unreal.TextureAddress.TA_WRAP)
    tex.set_editor_property("address_y", unreal.TextureAddress.TA_WRAP)


def phase_textures():
    out = {}
    for name, (png, mips) in TEXTURES.items():
        imported = _import_texture(name, png)
        tex = unreal.EditorAssetLibrary.load_asset(TEX_DIR + "/" + name)
        if tex is None:
            raise RuntimeError("import of %s produced nothing (%s)" % (png, imported))
        _configure_texture(tex, mips)
        out[name] = {"imported": imported, "class": tex.get_class().get_name()}
    for vname, (atlas, tile) in VOLUMES.items():
        src = unreal.EditorAssetLibrary.load_asset(TEX_DIR + "/" + atlas)
        vt, created = _load_or_create(TEX_DIR + "/" + vname, unreal.VolumeTexture, unreal.VolumeTextureFactory())
        if vt is None:
            raise RuntimeError("cannot create %s" % vname)
        vt.set_editor_property("source2d_texture", src)        # notified: picks a default tile size, rebuilds source
        vt.set_editor_property("source2d_tile_size_x", tile)   # notified: rebuilds the 3D source from the tiles
        vt.set_editor_property("source2d_tile_size_y", tile)
        vt.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
        vt.set_editor_property("srgb", False)
        vt.set_editor_property("address_mode", unreal.TextureAddress.TA_WRAP)
        vt.set_editor_property("never_stream", True)
        out[vname] = {"created": created,
                      "tile": [vt.get_editor_property("source2d_tile_size_x"),
                               vt.get_editor_property("source2d_tile_size_y")]}
    for name in list(TEXTURES) + list(VOLUMES):
        out.setdefault("saved", []).append(
            [name, bool(unreal.EditorAssetLibrary.save_asset(TEX_DIR + "/" + name, only_if_is_dirty=False))])
    return out


def _link(ok, what, material="M_CS_CumulusCloud"):
    if not ok:
        raise RuntimeError("%s: cannot connect %s" % (material, what))


def _clear_graph(m, name):
    mel = unreal.MaterialEditingLibrary
    mel.delete_all_material_expressions(m)
    for e in list(mel.get_material_expressions(m)):     # delete_all skips nodes while it removes them (traps.md 104)
        mel.delete_material_expression(m, e)
    if mel.get_num_material_expressions(m):
        raise RuntimeError("%s: %d expressions survived the clear" % (name, mel.get_num_material_expressions(m)))


LOG = os.path.abspath(os.path.join(unreal.Paths.project_log_dir(), "PCG_Claude.log"))


def _log_mark():
    unreal.SystemLibrary.execute_console_command(None, "FLUSHLOG")
    try:
        return os.path.getsize(LOG)
    except OSError:
        return 0


def _shader_errors(mark, name):
    """The 'Failed to compile Material <name>' warnings the shader compiler logged since mark, each with the error lines
    under it (ShaderCompiler.cpp, ProcessCompiledShaderMaps)."""
    unreal.SystemLibrary.execute_console_command(None, "FLUSHLOG")
    try:
        with open(LOG, "rb") as f:
            f.seek(mark)
            lines = f.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return []
    return [" | ".join(x.strip() for x in lines[i:i + 6])[:1200]
            for i, line in enumerate(lines) if "Failed to compile Material" in line and name in line]


def _compile(m, name):
    """recompile_material returns the translation errors only: the HLSL of the custom node is compiled by the shader
    jobs afterwards. get_statistics waits for those (FinishCompilation), then the log says whether they failed. Raises
    before the caller saves, so a broken material never replaces the one on disk."""
    mel = unreal.MaterialEditingLibrary
    mark = _log_mark()
    errors = [str(e) for e in mel.recompile_material(m)]
    if errors:
        raise RuntimeError("%s does not compile: %s" % (name, "; ".join(errors)[:1500]))
    st = mel.get_statistics(m)
    failed = _shader_errors(mark, name)
    if failed:
        raise RuntimeError("%s shaders fail: %s" % (name, " || ".join(failed)[:3000]))
    return {"ps": st.num_pixel_shader_instructions, "vs": st.num_vertex_shader_instructions, "samplers": st.num_samplers}


def _param(m, cls, name, x, y, group=None):
    mel = unreal.MaterialEditingLibrary
    p = mel.create_material_expression(m, cls, x, y)
    p.set_editor_property("parameter_name", name)          # notified: resolves the parameter id
    if group:
        p.set_editor_property("group", group, NEVER)
    return p


def _build_cloud_material(path, name):
    """Builds the v2 cloud graph (cs_cloud_code) into the material at path and compiles it. Raises before anything is
    saved, so a broken material never replaces the one on disk. Returns (material, created, stats)."""
    mel = unreal.MaterialEditingLibrary
    shape = unreal.EditorAssetLibrary.load_asset(TEX_DIR + "/VT_CS_CloudShape")
    detail = unreal.EditorAssetLibrary.load_asset(TEX_DIR + "/VT_CS_CloudDetail")
    weather = unreal.EditorAssetLibrary.load_asset(TEX_DIR + "/T_CS_CloudWeather")
    if not (shape and detail and weather):
        raise RuntimeError("textures missing; run phase textures first")
    m, created = _load_or_create(path, unreal.Material, unreal.MaterialFactoryNew())
    _clear_graph(m, name)
    m.set_editor_property("material_domain", unreal.MaterialDomain.MD_VOLUME, NEVER)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE, NEVER)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_DEFAULT_LIT, NEVER)
    m.set_editor_property("used_with_volumetric_cloud", True, NEVER)

    cust = mel.create_material_expression(m, unreal.MaterialExpressionCustom, -400, 0)
    cust.set_editor_property("code", CC.generate(), NEVER)
    cust.set_editor_property("description", "CumulusDensity2", NEVER)
    cust.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT1, NEVER)
    inputs = []
    for pin in CC.pins():
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", pin)
        inputs.append(ci)
    cust.set_editor_property("inputs", inputs)
    outs = []
    for out_name in ("Cons", "AO", "Alb"):
        co = unreal.CustomOutput()
        co.set_editor_property("output_name", out_name)
        co.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT1)
        outs.append(co)
    cust.set_editor_property("additional_outputs", outs)

    pos = mel.create_material_expression(m, unreal.MaterialExpressionWorldPosition, -900, -600)
    _link(mel.connect_material_expressions(pos, "", cust, "P"), "WorldPosition -> P", name)
    cam = mel.create_material_expression(m, unreal.MaterialExpressionCameraPositionWS, -900, -700)
    _link(mel.connect_material_expressions(cam, "", cust, "Cam"), "CameraPositionWS -> Cam", name)
    sun = mel.create_material_expression(m, unreal.MaterialExpressionSkyAtmosphereLightDirection, -900, -800)
    sun.set_editor_property("light_index", 0, NEVER)
    _link(mel.connect_material_expressions(sun, "", cust, "L"), "SkyAtmosphereLightDirection -> L", name)
    csa = mel.create_material_expression(m, unreal.MaterialExpressionCloudSampleAttribute, -900, -480)
    _link(mel.connect_material_expressions(csa, "Altitude", cust, "Alt"), "Altitude -> Alt", name)
    _link(mel.connect_material_expressions(csa, "ShadowSampleDistance", cust, "SD"), "ShadowSampleDistance -> SD", name)
    y = -360
    for pin, tex in (("WeatherTex", weather), ("ShapeTex", shape), ("DetailTex", detail)):
        t = _param(m, unreal.MaterialExpressionTextureObjectParameter, pin, -900, y, "Textures")
        t.set_editor_property("texture", tex, NEVER)
        t.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR, NEVER)
        _link(mel.connect_material_expressions(t, "", cust, pin), "%s -> %s" % (pin, pin), name)
        y += 130
    for pname, value, group in CC.scalar_pins():
        p = _param(m, unreal.MaterialExpressionScalarParameter, pname, -900, y, group)
        p.set_editor_property("default_value", value, NEVER)
        _link(mel.connect_material_expressions(p, "", cust, pname), "%s -> custom" % pname, name)
        y += 70
    extra = {}
    y = -600
    for pname, value, group in CC.EXTRA_SCALARS:
        p = _param(m, unreal.MaterialExpressionScalarParameter, pname, 0, y, group)
        p.set_editor_property("default_value", value, NEVER)
        extra[pname] = p
        y += 70

    albedo = _param(m, unreal.MaterialExpressionVectorParameter, "Albedo", 0, -800, "Lighting")
    albedo.set_editor_property("default_value", unreal.LinearColor(1.0, 1.0, 1.0, 1.0), NEVER)
    powder = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, 200, -800)
    _link(mel.connect_material_expressions(albedo, "", powder, "A"), "Albedo -> Multiply.A", name)
    _link(mel.connect_material_expressions(cust, "Alb", powder, "B"), "Alb (powder) -> Multiply.B", name)
    _link(mel.connect_material_property(powder, "", unreal.MaterialProperty.MP_BASE_COLOR),
          "Albedo x Alb -> BaseColor", name)
    _link(mel.connect_material_property(cust, "return", unreal.MaterialProperty.MP_SUBSURFACE_COLOR),
          "sigma -> Extinction", name)
    _link(mel.connect_material_property(cust, "AO", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION), "AO -> AO", name)

    adv = mel.create_material_expression(m, unreal.MaterialExpressionVolumetricAdvancedMaterialOutput, 400, -300)
    adv.set_editor_property("multi_scattering_approximation_octave_count", 2, NEVER)
    adv.set_editor_property("ground_contribution", True, NEVER)
    adv.set_editor_property("gray_scale_material", True, NEVER)
    adv.set_editor_property("ray_march_volume_shadow", True, NEVER)
    adv.set_editor_property("clamp_multi_scattering_contribution", True, NEVER)
    for pin, pname in (("PhaseG", "PhaseG"), ("PhaseG2", "PhaseG2"), ("PhaseBlend", "PhaseBlend"),
                       ("MultiScatteringContribution", "MSContribution"),
                       ("MultiScatteringOcclusion", "MSOcclusion"),
                       ("MultiScatteringEccentricity", "MSEccentricity")):
        _link(mel.connect_material_expressions(extra[pname], "", adv, pin), "%s -> %s" % (pname, pin), name)
    _link(mel.connect_material_expressions(cust, "Cons", adv, "ConservativeDensity"), "Cons -> ConservativeDensity", name)

    t0 = time.time()
    stats = _compile(m, name)
    stats["compile_s"] = round(time.time() - t0, 1)
    return m, created, stats


def phase_material():
    mel = unreal.MaterialEditingLibrary
    m, created, stats = _build_cloud_material(MATERIAL, "M_CS_CumulusCloud")
    unreal.EditorAssetLibrary.save_asset(MATERIAL, only_if_is_dirty=False)
    mi, mi_created = _load_or_create(INSTANCE, unreal.MaterialInstanceConstant,
                                     unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, m)
    mel.update_material_instance(mi)
    unreal.EditorAssetLibrary.save_asset(INSTANCE, only_if_is_dirty=False)
    return {"material_created": created, "instance_created": mi_created, "pins": len(CC.pins()),
            "expressions": mel.get_num_material_expressions(m), "stats": stats,
            "scalars": len(mel.get_scalar_parameter_names(m))}


def phase_probe():
    """The M1 spike (spec §10): build and compile the v2 graph in a scratch material, report, delete the scratch."""
    try:
        m, _created, stats = _build_cloud_material(PROBE, "M_CS_CloudV2Probe")
        return {"stats": stats, "pins": len(CC.pins()), "code_lines": len(CC.generate().splitlines()),
                "expressions": unreal.MaterialEditingLibrary.get_num_material_expressions(m)}
    finally:
        if unreal.EditorAssetLibrary.does_asset_exist(PROBE):
            unreal.EditorAssetLibrary.delete_asset(PROBE)


STAR_CODE = r"""
float3 d = -normalize(V);
float u = atan2(d.y, d.x) * 0.15915494 + 0.5;
float v = acos(clamp(d.z, -1.0, 1.0)) * 0.31830989;
float3 c = Texture2DSampleLevel(StarTex, StarTexSampler, float2(u, v), 0.0).rgb;
float m = max(c.r, max(c.g, c.b));
return c * pow(saturate(m), max(Sharp - 1.0, 0.0)) * saturate(d.z * 12.0);
"""


def phase_nightsky():
    """M_CS_NightSky rebuilt from an empty graph, unlit, sky, two-sided (after M_WeatherStars, weather_assets.py):
    SkyAtmosphereViewLuminance + SkyAtmosphereLightDiskLuminance (light 0: the moon of the night weathers) +
    stars x StarIntensity -> Emissive. A scene with a sky material makes the SkyAtmosphere skip its own sky pixels
    (SkyAtmosphereRendering.cpp, bRenderSkyPixel), so the material draws the atmosphere and the disk itself; being a sky
    material it stays behind the volumetric clouds. The stars: the SeasonalWeather star map (2048 x 1024, equirectangular)
    sampled by view direction at mip 0 (the dome mesh's own UVs stretch it), each texel's value raised to StarSharp so a
    star is a point rather than a bilinear square (and the faint background drops out), faded over the lowest 5 degrees.
    MI_CS_NightSky is the instance the dome uses. SeasonalWeather's M_WeatherStars samples the same way
    (weather_assets.STAR_CODE) and also adds the map's band back as a smooth glow from mip 4."""
    mel = unreal.MaterialEditingLibrary
    name = "M_CS_NightSky"
    stars = unreal.EditorAssetLibrary.load_asset(STAR_MAP)
    if not isinstance(stars, unreal.Texture2D):
        raise RuntimeError("%s missing (weather.py assets builds it)" % STAR_MAP)
    m, created = _load_or_create(NIGHT_SKY, unreal.Material, unreal.MaterialFactoryNew())
    _clear_graph(m, name)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT, NEVER)
    m.set_editor_property("is_sky", True, NEVER)
    m.set_editor_property("two_sided", True, NEVER)
    sky = mel.create_material_expression(m, unreal.MaterialExpressionSkyAtmosphereViewLuminance, -600, -350)
    disk = mel.create_material_expression(m, unreal.MaterialExpressionSkyAtmosphereLightDiskLuminance, -600, -200)
    disk.set_editor_property("light_index", 0, NEVER)
    atmosphere = mel.create_material_expression(m, unreal.MaterialExpressionAdd, -250, -250)
    _link(mel.connect_material_expressions(sky, "", atmosphere, "A"), "SkyAtmosphereViewLuminance -> Add.A", name)
    _link(mel.connect_material_expressions(disk, "", atmosphere, "B"), "SkyAtmosphereLightDiskLuminance -> Add.B", name)
    cust = mel.create_material_expression(m, unreal.MaterialExpressionCustom, -350, 50)
    cust.set_editor_property("code", STAR_CODE.strip(), NEVER)
    cust.set_editor_property("description", "Stars", NEVER)
    cust.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3, NEVER)
    inputs = []
    for pin in ("V", "StarTex", "Sharp"):
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", pin)
        inputs.append(ci)
    cust.set_editor_property("inputs", inputs)
    cam = mel.create_material_expression(m, unreal.MaterialExpressionCameraVectorWS, -700, 0)
    _link(mel.connect_material_expressions(cam, "", cust, "V"), "CameraVectorWS -> V", name)
    tex = _param(m, unreal.MaterialExpressionTextureObjectParameter, "StarTex", -700, 100, "Stars")
    tex.set_editor_property("texture", stars, NEVER)
    _link(mel.connect_material_expressions(tex, "", cust, "StarTex"), "StarTex -> StarTex", name)
    sharp = _param(m, unreal.MaterialExpressionScalarParameter, "StarSharp", -700, 250, "Stars")
    sharp.set_editor_property("default_value", 4.0, NEVER)
    _link(mel.connect_material_expressions(sharp, "", cust, "Sharp"), "StarSharp -> Sharp", name)
    par = _param(m, unreal.MaterialExpressionScalarParameter, "StarIntensity", -350, 300, "Stars")
    par.set_editor_property("default_value", 1.0, NEVER)
    mul = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -150, 100)
    _link(mel.connect_material_expressions(cust, "", mul, "A"), "Stars -> Multiply.A", name)
    _link(mel.connect_material_expressions(par, "", mul, "B"), "StarIntensity -> Multiply.B", name)
    emissive = mel.create_material_expression(m, unreal.MaterialExpressionAdd, -50, 0)
    _link(mel.connect_material_expressions(atmosphere, "", emissive, "A"), "atmosphere -> Add.A", name)
    _link(mel.connect_material_expressions(mul, "", emissive, "B"), "stars -> Add.B", name)
    _link(mel.connect_material_property(emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR), "-> Emissive", name)
    stats = _compile(m, name)
    unreal.EditorAssetLibrary.save_asset(NIGHT_SKY, only_if_is_dirty=False)
    mi, mi_created = _load_or_create(NIGHT_SKY_MI, unreal.MaterialInstanceConstant,
                                     unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(mi, m)
    mel.update_material_instance(mi)
    unreal.EditorAssetLibrary.save_asset(NIGHT_SKY_MI, only_if_is_dirty=False)
    return {"material_created": created, "instance_created": mi_created, "stats": stats,
            "expressions": mel.get_num_material_expressions(m),
            "scalars": [str(n) for n in mel.get_scalar_parameter_names(m)]}


def _run(phase):
    res = {}
    if phase == "probe":
        res["probe"] = phase_probe()
    if phase in ("all", "textures"):
        res["textures"] = phase_textures()
    if phase in ("all", "material"):
        res["material"] = phase_material()
    if phase in ("all", "nightsky"):
        res["nightsky"] = phase_nightsky()
    return res


def _defer(args):
    phase = args.get("phase", "all")
    _save_json(REPORT, {"phase": phase, "state": "queued"})
    handle = {}

    def tick(_dt):
        unreal.unregister_slate_post_tick_callback(handle["h"])
        try:
            _save_json(REPORT, {"phase": phase, "state": "done", "result": _run(phase)})
        except Exception as exc:
            _save_json(REPORT, {"phase": phase, "state": "error",
                                "error": "%s: %s" % (type(exc).__name__, str(exc)[:800]),
                                "trace": traceback.format_exc()[-2000:]})
        gc.collect()

    handle["h"] = unreal.register_slate_post_tick_callback(tick)
    return {"deferred": phase, "result_file": REPORT}


mcp_result = _defer(globals().get("mcp_args") or {})
gc.collect()
