# cs_clear_sky.py -- a 10:00 clear-sky look with rich cumulus for the City Sample demo level
# (/CitySamplePCG/Levels/L_CitySamplePCG_Demo), applied in memory to the level's own sky actors.
#
# Phases (one per call):
#   apply   {"phase": "apply", "set": {"Section.prop": value, ...}}   snapshot the originals once, then apply LOOK
#           (with the optional overrides); spawns an unbound PostProcessVolume "CS_ClearSky_PPV"; sets the quality
#           cvars; turns editor autosave off in memory (the demo level is Epic content: never autosave it, CLAUDE.md)
#           The cloud shadow map is the fine one of report section 8 (extent 10 km, no spatial filtering);
#           {"fix_cloud_shadow": false} applies UNFIXED_LOOK / UNFIXED_CVARS instead, the first version's blocky
#           78 m map, for A/B shots
#   state   {"phase": "state"}       current values of everything LOOK touches, plus the cvars
#   restore {"phase": "restore"}     puts every snapshotted value back, deletes CS_ClearSky_PPV and CS_SkyCam,
#                                    restores the cvars and autosave
# The level is never saved by this script. The cloud material instance /Game/CitySampleSky/MI_CS_CumulusCloud_Clear
# is a project asset and is saved after its parameters are set.
import gc
import json
import math
import os

import unreal

REPORT_DIR = os.path.abspath(os.path.join(unreal.Paths.project_saved_dir(), "Reports", "cs_weather"))
SNAPSHOT = os.path.join(REPORT_DIR, "original_state.json")
LEVEL = "/CitySamplePCG/Levels/L_CitySamplePCG_Demo"
CLOUD_MI = "/Game/CitySampleSky/MI_CS_CumulusCloud_Clear"
# The demo level draws its sky pixels with a sky-dome mesh (SM_SkySphere, /Engine/EngineSky/M_SimpleSkyDome), whose
# material reads the 192x104 SkyViewLut; while it is visible the SkyAtmosphere pass skips sky pixels, so
# r.SkyAtmosphere.FastSkyLUT 0 has no effect there. Hiding it lets the SkyAtmosphere pass ray-march the sky per pixel.
HIDE_LABELS = ["SM_SkySphere"]
PPV_LABEL = "CS_ClearSky_PPV"
CAM_LABEL = "CS_SkyCam"

# --- the look -------------------------------------------------------------------------------------------------------
# Sun: 10:00 local solar time on 2026-11-09 at latitude 35 N (declination -16.6 deg) -> elevation 31.1, azimuth 146
# (clockwise from north). North is +X, so azimuth maps straight to UE yaw; the light points away from the sun.
SUN_ELEVATION = 31.1
SUN_AZIMUTH = 146.0

LOOK = {
    "DirectionalLightComponent": {
        "intensity": 120000.0,                # lux at the top of the atmosphere; SkyAtmosphere applies transmittance
        "use_temperature": True, "temperature": 5800.0,
        "light_source_angle": 0.5357,
        "atmosphere_sun_light": True, "atmosphere_sun_light_index": 0,
        "per_pixel_atmosphere_transmittance": True,
        "cast_shadows_on_atmosphere": True,   # opaque shadow map sampled by the sky / aerial-perspective LUTs
        "cast_shadows_on_clouds": False,
        "cast_cloud_shadows": True,
        "cloud_shadow_strength": 1.0,
        "cloud_shadow_on_atmosphere_strength": 1.0,
        "cloud_shadow_on_surface_strength": 1.0,
        "cloud_shadow_extent": 10.0,          # km; the map covers +-2 x this (40 km square), 9.8 m texels (section 8)
        "cloud_shadow_map_resolution_scale": 8.0,   # 512 x 8 = 4096 (r.VolumetricCloud.ShadowMap.MaxResolution)
        "cloud_shadow_ray_sample_count_scale": 4.0,
        "cast_volumetric_shadow": True,
        "volumetric_scattering_intensity": 2.0,  # brighter sun shafts in the volumetric fog
        "enable_light_shaft_occlusion": True,
        "enable_light_shaft_bloom": False,
    },
    "SkyAtmosphereComponent": {
        "multi_scattering_factor": 1.0,
        "trace_sample_count_scale": 2.0,
        "mie_scattering_scale": 0.012,        # 3x the clean-air default: a light morning haze for the shafts
        "mie_anisotropy": 0.8,
    },
    "SkyLightComponent": {
        "real_time_capture": True,
        "cubemap_resolution": 256,
        "cloud_ambient_occlusion": True,
        "cloud_ambient_occlusion_strength": 1.0,
        "cloud_ambient_occlusion_extent": 60.0,
        "cloud_ambient_occlusion_map_resolution_scale": 2.0,
        "cloud_ambient_occlusion_aperture_scale": 0.05,
        "intensity": 1.0,
    },
    "VolumetricCloudComponent": {
        "material": CLOUD_MI,
        "layer_bottom_altitude": 1.4,         # km above the planet ground (the atmosphere's top, z = -60 m)
        "layer_height": 4.0,
        "tracing_max_distance": 40.0,
        "view_sample_count_scale": 4.0,
        "shadow_view_sample_count_scale": 4.0,
        "reflection_view_sample_count_scale_value": 2.0,
        "shadow_reflection_view_sample_count_scale_value": 2.0,
        "shadow_tracing_distance": 15.0,
        "stop_tracing_transmittance_threshold": 0.001,
        "sky_light_cloud_bottom_occlusion": 0.6,
    },
    "ExponentialHeightFogComponent": {
        "fog_density": 0.006,
        "fog_height_falloff": 0.04,           # density halves every 250 m
        "second_fog_data": {"fog_density": 0.003, "fog_height_falloff": 0.006, "fog_height_offset": 0.0},
        "enable_volumetric_fog": True,
        "volumetric_fog_scattering_distribution": 0.8,   # strong forward scattering toward the sun
        "volumetric_fog_albedo": [255, 255, 255, 255],
        "volumetric_fog_extinction_scale": 1.0,
        "volumetric_fog_distance": 600000.0,  # 6 km of froxels
        "volumetric_fog_start_distance": 0.0,
        "volumetric_fog_static_lighting_scattering_intensity": 1.0,
    },
    "PPV": {                                  # unbound PostProcessVolume CS_ClearSky_PPV
        "auto_exposure_method": "AEM_HISTOGRAM",
        "auto_exposure_min_brightness": 13.4,     # EV100; min == max fixes the exposure
        "auto_exposure_max_brightness": 13.4,
        "auto_exposure_bias": 0.0,
    },
    "CloudMI": {
        "WeatherScaleKm": 32.0, "ShapeScaleKm": 3.5, "DetailScaleKm": 0.6, "WarpKm": 1.5, "WarpScaleKm": 15.0,
        "CoverageBias": 0.0, "CoverageScale": 0.8, "DetailStrength": 0.6, "DensityScale": 2.5,
        "TypeMin": 0.3, "TypeMax": 1.0, "BottomRamp": 0.02, "TopRamp": 0.7,
        "WindX": 21.5, "WindY": 23.5, "PixelAngle": 0.0007,           # weather-map offset (km) picked by Tools/cs_sky/coverage_map.py --search
        "ExtinctionMax": 0.12, "PhaseG": 0.6, "PhaseG2": -0.2, "PhaseBlend": 0.25,
        "MSContribution": 0.6, "MSOcclusion": 0.5, "MSEccentricity": 0.5,
    },
}

CVARS = {
    # sky atmosphere: per-pixel ray marching, high-quality multi-scattering LUT, all LUTs every frame
    "r.SkyAtmosphere.StateVersioning": 0,
    "r.SkyAtmosphere.FastSkyLUT": 0,
    "r.SkyAtmosphere.AerialPerspectiveLUT.FastApplyOnOpaque": 0,
    "r.SkyAtmosphere.SampleCountMax": 128,     # the project's own Epic-scalability value; never lower it
    "r.SkyAtmosphere.MultiScatteringLUT.HighQuality": 1,
    "r.SkyAtmosphere.MultiScatteringLUT.SampleCount": 30,
    "r.SkyAtmosphere.TransmittanceLUT.SampleCount": 30,
    "r.SkyAtmosphere.AerialPerspectiveLUT.Width": 64,
    "r.SkyAtmosphere.AerialPerspectiveLUT.DepthResolution": 32,
    "r.SkyAtmosphere.AerialPerspectiveLUT.SampleCountMaxPerSlice": 4,
    "r.SkyAtmosphere.LUT32": 1,
    # volumetric clouds
    "r.VolumetricRenderTarget.Mode": 3,   # cinematic: clouds traced at full resolution
    "r.VolumetricCloud.ViewRaySampleMaxCount": 1024,
    "r.VolumetricCloud.Shadow.ViewRaySampleMaxCount": 128,
    "r.VolumetricCloud.SampleMinCount": 4,
    "r.VolumetricCloud.HighQualityAerialPerspective": 1,
    "r.VolumetricCloud.ShadowMap.MaxResolution": 4096,
    "r.VolumetricCloud.ShadowMap.RaySampleMaxCount": 256,
    "r.VolumetricCloud.ShadowMap.SpatialFiltering": 0,   # each iteration is a 2x2 downsample, not a blur
    "r.VolumetricCloud.ShadowMap.SnapLength": 1,         # km; keeps the 40 km map centred on the camera
    # km; the shadow trace starts on a plane this far toward the sun (default 2 x CloudShadowExtent = 20 km, which
    # cuts into the 1.4-5.4 km cloud layer for points more than ~11 km toward a 31 deg sun)
    "r.VolumetricCloud.ShadowMap.LightDistanceOverride": 80,
    "r.VolumetricCloud.SkyAO.MaxResolution": 2048,
    # volumetric fog
    "r.VolumetricFog.GridPixelSize": 4,
    "r.VolumetricFog.GridSizeZ": 128,
    "r.VolumetricFog.HistoryMissSupersampleCount": 8,
    # sky light: capture all faces every frame
    "r.SkyLight.RealTimeReflectionCapture.TimeSlice": 0,
}


# --- helpers --------------------------------------------------------------------------------------------------------
def _world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def _actors():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()


def _find_label(label):
    for a in _actors():
        if a.get_actor_label() == label:
            return a
    return None


def _component(cls_name):
    cls = getattr(unreal, cls_name)
    for a in _actors():
        comps = a.get_components_by_class(cls)
        if comps:
            return a, comps[0]
    return None, None


def _enc(v):
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if isinstance(v, unreal.LinearColor):
        return {"__t": "LinearColor", "v": [v.r, v.g, v.b, v.a]}
    if isinstance(v, unreal.Color):
        return {"__t": "Color", "v": [v.r, v.g, v.b, v.a]}
    if isinstance(v, unreal.Rotator):
        return {"__t": "Rotator", "v": [v.pitch, v.yaw, v.roll]}
    if isinstance(v, unreal.ExponentialHeightFogData):
        return {"__t": "Fog", "v": {"fog_density": v.fog_density, "fog_height_falloff": v.fog_height_falloff,
                                    "fog_height_offset": v.fog_height_offset}}
    if isinstance(v, unreal.Object):
        return {"__t": "Object", "v": v.get_path_name()}
    if isinstance(v, unreal.EnumBase):
        return {"__t": "Enum", "cls": type(v).__name__, "v": v.name}
    return {"__t": "str", "v": str(v)}


def _dec(v, current=None):
    if isinstance(v, dict) and "__t" in v:
        t, x = v["__t"], v["v"]
        if t == "LinearColor":
            return unreal.LinearColor(*x)
        if t == "Color":
            return unreal.Color(r=x[0], g=x[1], b=x[2], a=x[3])
        if t == "Rotator":
            return unreal.Rotator(roll=x[2], pitch=x[0], yaw=x[1])
        if t == "Fog":
            return _fog(x)
        if t == "Object":
            return unreal.load_object(None, x) if x else None
        if t == "Enum":
            return getattr(getattr(unreal, v["cls"]), x)
    return v


def _fog(d):
    f = unreal.ExponentialHeightFogData()
    for k, val in d.items():
        f.set_editor_property(k, float(val))
    return f


def _value_for(comp, prop, val):
    """Turns a LOOK value into what set_editor_property wants, by the type of the current value."""
    cur = comp.get_editor_property(prop)
    if isinstance(cur, unreal.LinearColor):
        return unreal.LinearColor(*val)
    if isinstance(cur, unreal.Color):
        return unreal.Color(r=val[0], g=val[1], b=val[2], a=val[3])
    if isinstance(cur, unreal.ExponentialHeightFogData):
        return _fog(val)
    if isinstance(val, str) and val.startswith("/"):
        return unreal.load_asset(val)
    if isinstance(cur, float):
        return float(val)
    if isinstance(cur, int) and not isinstance(cur, bool):
        return int(val)
    return val


def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, default=str)


def _autosave_cdo():
    return unreal.get_default_object(unreal.load_class(None, "/Script/UnrealEd.EditorLoadingSavingSettings"))


def _cvar_get(name):
    return unreal.SystemLibrary.get_console_variable_float_value(name)


def _cvar_set(name, value):
    unreal.SystemLibrary.execute_console_command(_world(), "%s %s" % (name, value))


def _merged(overrides):
    look = json.loads(json.dumps(LOOK))
    for key, val in (overrides or {}).items():
        section, prop = key.split(".", 1)
        look.setdefault(section, {})[prop] = val
    return look


def _sun_rotation(elev, azim):
    return unreal.Rotator(roll=0.0, pitch=-elev, yaw=azim - 180.0)


def _require_level():
    w = _world().get_path_name()
    if not w.startswith(LEVEL + "."):
        return {"abort": "current level is %s, not %s" % (w, LEVEL)}
    return None


# --- phases ---------------------------------------------------------------------------------------------------------
def _snapshot():
    if os.path.exists(SNAPSHOT):
        return False
    snap = {"components": {}, "cvars": {}, "autosave": None}
    for cls_name, props in LOOK.items():
        if cls_name in ("PPV", "CloudMI"):
            continue
        actor, comp = _component(cls_name)
        if comp is None:
            continue
        snap["components"][cls_name] = {p: _enc(comp.get_editor_property(p)) for p in props}
        if cls_name == "DirectionalLightComponent":
            snap["sun_rotation"] = _enc(actor.get_actor_rotation())
    for name in CVARS:
        snap["cvars"][name] = _cvar_get(name)
    snap["autosave"] = bool(_autosave_cdo().get_editor_property("bAutoSaveEnable"))
    snap["hide"] = _visibility()
    _save(SNAPSHOT, snap)
    return True


def _visibility():
    out = {}
    for label in HIDE_LABELS:
        a = _find_label(label)
        if a is not None:
            out[label] = [bool(c.is_visible()) for c in a.get_components_by_class(unreal.PrimitiveComponent)]
    return out


def _snapshot_add_hide():
    """Older snapshots predate HIDE_LABELS and the cloud shadow cvars: add what the level / console had before we
    changed it. The cloud shadow cvars are recorded at their engine defaults, which the project does not override."""
    with open(SNAPSHOT, encoding="utf-8") as f:
        snap = json.load(f)
    changed = False
    if "hide" not in snap:
        snap["hide"] = _visibility()
        changed = True
    for name, default in UNFIXED_CVARS.items():
        if name not in snap["cvars"]:
            snap["cvars"][name] = default
            changed = True
    if changed:
        _save(SNAPSHOT, snap)


# Cloud shadow map (report section 8): the map covers +-2 x CloudShadowExtent (the ortho matrix gets the diameter as
# its half-width) and each SpatialFiltering iteration halves its resolution. The first version of this look used
# 40 km with the engine's single iteration: 78 m texels (78 x 151 m on the ground at a 31 deg sun) and blocky
# shadows. LOOK / CVARS now use 10 km and no iteration: 9.8 m at the same trace cost, SnapLength 1 km keeps the
# smaller map centred on the camera. The trace of every texel starts on the light's near plane, LightDistance
# (default 2 x Extent) toward the sun from the ground under the camera; at 20 km that plane is inside the cloud
# layer for the sun-side third of the map, so LightDistanceOverride puts it back at the first version's 80 km.
# {"fix_cloud_shadow": false} puts the first version back, for A/B comparisons.
UNFIXED_LOOK = {"DirectionalLightComponent": {"cloud_shadow_extent": 40.0}}
UNFIXED_CVARS = {"r.VolumetricCloud.ShadowMap.SpatialFiltering": 1,   # the engine defaults
                 "r.VolumetricCloud.ShadowMap.SnapLength": 20,
                 "r.VolumetricCloud.ShadowMap.LightDistanceOverride": 0}


def _apply_ppv(cfg):
    ppv = _find_label(PPV_LABEL)
    if ppv is None:
        ppv = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
            unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
        ppv.set_actor_label(PPV_LABEL)
    ppv.set_editor_property("unbound", True)
    ppv.set_editor_property("priority", 10.0)
    s = ppv.get_editor_property("settings")
    for prop, val in cfg.items():
        if prop == "auto_exposure_method":
            val = getattr(unreal.AutoExposureMethod, val)
        s.set_editor_property("override_" + prop, True)
        s.set_editor_property(prop, val)
    ppv.set_editor_property("settings", s)
    return ppv.get_actor_label()


def _apply_cloud_mi(cfg):
    mi = unreal.EditorAssetLibrary.load_asset(CLOUD_MI)
    mel = unreal.MaterialEditingLibrary
    for name, val in cfg.items():
        mel.set_material_instance_scalar_parameter_value(mi, name, float(val))
    mel.update_material_instance(mi)
    unreal.EditorAssetLibrary.save_asset(CLOUD_MI, only_if_is_dirty=False)
    return len(cfg)


def phase_apply(args):
    refused = _require_level()
    if refused:
        return refused
    fresh = _snapshot()
    _snapshot_add_hide()
    fix = bool(args.get("fix_cloud_shadow", True))
    overrides = {}
    if not fix:
        for section, props in UNFIXED_LOOK.items():
            overrides.update({"%s.%s" % (section, k): v for k, v in props.items()})
    overrides.update(args.get("set") or {})
    look = _merged(overrides)
    out = {"snapshot_written": fresh, "set": {}, "fix_cloud_shadow": fix}
    cdo = _autosave_cdo()
    cdo.set_editor_property("bAutoSaveEnable", False, unreal.PropertyAccessChangeNotifyMode.NEVER)
    cvars = dict(CVARS)
    if not fix:
        cvars.update(UNFIXED_CVARS)
    for name, value in cvars.items():
        _cvar_set(name, value)
    out["cvars"] = {n: _cvar_get(n) for n in cvars}
    with unreal.ScopedEditorTransaction("CS clear sky"):
        out["cloud_mi_params"] = _apply_cloud_mi(look["CloudMI"])
        for cls_name, props in look.items():
            if cls_name in ("PPV", "CloudMI"):
                continue
            actor, comp = _component(cls_name)
            if comp is None:
                out["set"][cls_name] = "missing"
                continue
            comp.modify()
            for prop, val in props.items():
                comp.set_editor_property(prop, _value_for(comp, prop, val))
            out["set"][cls_name] = len(props)
            if cls_name == "DirectionalLightComponent":
                elev = float(args.get("sun_elevation", SUN_ELEVATION))
                azim = float(args.get("sun_azimuth", SUN_AZIMUTH))
                actor.set_actor_rotation(_sun_rotation(elev, azim), False)
                out["sun"] = {"elevation": elev, "azimuth": azim}
        out["ppv"] = _apply_ppv(look["PPV"])
        for label in HIDE_LABELS:
            a = _find_label(label)
            if a is not None:
                for c in a.get_components_by_class(unreal.PrimitiveComponent):
                    c.modify()
                    c.set_visibility(False, True)
                out.setdefault("hidden", []).append(label)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_invalidate_viewports()
    return out


def phase_state(args):
    look = LOOK
    out = {"components": {}, "cvars": {n: _cvar_get(n) for n in CVARS}}
    for cls_name, props in look.items():
        if cls_name in ("PPV", "CloudMI"):
            continue
        actor, comp = _component(cls_name)
        if comp is None:
            continue
        out["components"][cls_name] = {p: _enc(comp.get_editor_property(p)) for p in props}
        if cls_name == "DirectionalLightComponent":
            r = actor.get_actor_rotation()
            out["sun_rotation"] = [r.pitch, r.yaw, r.roll]
    out["autosave"] = bool(_autosave_cdo().get_editor_property("bAutoSaveEnable"))
    out["ppv"] = bool(_find_label(PPV_LABEL))
    return out


def phase_restore(args):
    if not os.path.exists(SNAPSHOT):
        return {"abort": "no snapshot at %s" % SNAPSHOT}
    with open(SNAPSHOT, encoding="utf-8") as f:
        snap = json.load(f)
    out = {"restored": {}}
    with unreal.ScopedEditorTransaction("CS clear sky restore"):
        for cls_name, props in snap["components"].items():
            actor, comp = _component(cls_name)
            if comp is None:
                continue
            comp.modify()
            for prop, val in props.items():
                comp.set_editor_property(prop, _dec(val))
            out["restored"][cls_name] = len(props)
            if cls_name == "DirectionalLightComponent" and "sun_rotation" in snap:
                actor.set_actor_rotation(_dec(snap["sun_rotation"]), False)
        for label, vis in snap.get("hide", {}).items():
            a = _find_label(label)
            if a is not None:
                for c, v in zip(a.get_components_by_class(unreal.PrimitiveComponent), vis):
                    c.modify()
                    c.set_visibility(bool(v), True)
                out.setdefault("shown", []).append(label)
        eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
        for label in (PPV_LABEL, CAM_LABEL):
            a = _find_label(label)
            if a is not None:
                eas.destroy_actor(a)
                out.setdefault("deleted", []).append(label)
    for name, value in snap["cvars"].items():
        _cvar_set(name, int(value) if float(value).is_integer() else value)
    _autosave_cdo().set_editor_property("bAutoSaveEnable", bool(snap["autosave"]),
                                        unreal.PropertyAccessChangeNotifyMode.NEVER)
    out["autosave"] = snap["autosave"]
    return out


PHASES = {"apply": phase_apply, "state": phase_state, "restore": phase_restore}


def _main(args):
    phase = args.get("phase", "state")
    if phase not in PHASES:
        return {"abort": "unknown phase %r" % phase}
    return json.loads(json.dumps(PHASES[phase](args), default=str))


mcp_result = _main(globals().get("mcp_args") or {})
gc.collect()
