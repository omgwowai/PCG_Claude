# cs_atmo_probe.py -- read-only dump of the sky components' settings in the current level, for the talk's
# "parameters -> image" slides. Returns plain values (colours as [r, g, b, a] floats, structs as dicts).
# Args: none. Touches nothing.
import unreal

COMPONENTS = {
    "SkyAtmosphereComponent": [
        "transform_mode", "bottom_radius", "atmosphere_height", "ground_albedo", "multi_scattering_factor",
        "rayleigh_scattering", "rayleigh_scattering_scale", "rayleigh_exponential_distribution",
        "mie_scattering", "mie_scattering_scale", "mie_absorption", "mie_absorption_scale", "mie_anisotropy",
        "mie_exponential_distribution", "other_absorption", "other_absorption_scale", "other_tent_distribution",
        "sky_luminance_factor", "sky_and_aerial_perspective_luminance_factor", "aerial_pespective_view_distance_scale",
        "height_fog_contribution", "transmittance_min_light_elevation_angle", "aerial_perspective_start_depth",
        "trace_sample_count_scale"],
    "VolumetricCloudComponent": [
        "layer_bottom_altitude", "layer_height", "tracing_start_max_distance", "tracing_start_distance_from_camera",
        "tracing_max_distance", "tracing_max_distance_mode", "planet_radius", "ground_albedo",
        "usage_per_sample_atmospheric_light_transmittance", "sky_light_cloud_bottom_occlusion",
        "view_sample_count_scale", "reflection_view_sample_count_scale_value", "shadow_view_sample_count_scale",
        "shadow_reflection_view_sample_count_scale_value", "shadow_tracing_distance", "stop_tracing_transmittance_threshold",
        "aerial_pespective_rayleigh_scattering_start_distance", "aerial_pespective_mie_scattering_start_distance"],
    "ExponentialHeightFogComponent": [
        "fog_density", "fog_height_falloff", "fog_inscattering_luminance", "fog_inscattering_color",
        "sky_atmosphere_ambient_contribution_color_scale", "directional_inscattering_luminance",
        "directional_inscattering_exponent", "directional_inscattering_start_distance", "fog_max_opacity", "start_distance",
        "fog_cutoff_distance", "enable_volumetric_fog", "volumetric_fog_scattering_distribution", "volumetric_fog_albedo",
        "volumetric_fog_emissive", "volumetric_fog_extinction_scale", "volumetric_fog_distance",
        "volumetric_fog_start_distance", "volumetric_fog_near_fade_in_distance", "second_fog_data", "height_offset"],
    "DirectionalLightComponent": [
        "intensity", "light_color", "temperature", "use_temperature", "light_source_angle", "atmosphere_sun_light",
        "per_pixel_atmosphere_transmittance", "cast_shadows_on_atmosphere", "cast_shadows_on_clouds", "cast_cloud_shadows",
        "cloud_shadow_extent", "cloud_shadow_map_resolution_scale", "cloud_shadow_ray_sample_count_scale",
        "cloud_shadow_on_atmosphere_strength", "cloud_shadow_on_surface_strength", "cloud_scattered_luminance_scale",
        "volumetric_scattering_intensity", "enable_light_shaft_occlusion", "enable_light_shaft_bloom"],
    "SkyLightComponent": [
        "real_time_capture", "cubemap_resolution", "intensity", "lower_hemisphere_is_black", "lower_hemisphere_color",
        "cloud_ambient_occlusion", "cloud_ambient_occlusion_strength", "cloud_ambient_occlusion_extent",
        "cloud_ambient_occlusion_map_resolution_scale", "cloud_ambient_occlusion_aperture_scale", "sky_distance_threshold",
        "capture_emissive_only"],
}


def _plain(v):
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if isinstance(v, unreal.LinearColor):
        return [v.r, v.g, v.b, v.a]
    if isinstance(v, unreal.Color):
        return [v.r, v.g, v.b, v.a]
    if isinstance(v, unreal.Object):
        return v.get_path_name()
    if isinstance(v, unreal.EnumBase):
        return str(v)
    if isinstance(v, unreal.StructBase):
        out = {}
        for name in dir(v):
            if name.startswith("_") or name in ("cast", "copy", "assign", "export_text", "import_text", "static_struct",
                                                "get_editor_property", "set_editor_property", "set_editor_properties"):
                continue
            try:
                attr = getattr(v, name)
            except Exception:
                continue
            if callable(attr):
                continue
            out[name] = _plain(attr)
        return out
    return str(v)


def _main():
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    out = {}
    for cls_name, props in COMPONENTS.items():
        cls = getattr(unreal, cls_name)
        comp = None
        for a in eas.get_all_level_actors():
            comps = a.get_components_by_class(cls)
            if comps:
                comp = comps[0]
                out.setdefault("_actors", {})[cls_name] = a.get_actor_label()
                break
        if comp is None:
            out[cls_name] = "missing"
            continue
        vals = {}
        for p in props:
            try:
                vals[p] = _plain(comp.get_editor_property(p))
            except Exception as e:
                vals[p] = "n/a"
        out[cls_name] = vals
    return out


mcp_result = _main()
