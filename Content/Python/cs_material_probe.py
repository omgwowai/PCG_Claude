# Read-only probe: describe materials / material instances / textures by asset path.
# args: {"assets": ["/Game/...", ...]}
import unreal


def _s(v):
    return v if isinstance(v, (bool, int, float, str)) or v is None else str(v)


def _describe(path):
    a = unreal.EditorAssetLibrary.load_asset(path)
    if a is None:
        return {"path": path, "error": "not found"}
    d = {"path": path, "class": a.get_class().get_name()}
    mel = unreal.MaterialEditingLibrary
    if isinstance(a, unreal.MaterialInterface):
        base = a.get_base_material()
        d["base"] = base.get_path_name() if base else None
        if isinstance(a, unreal.MaterialInstance):
            d["parent"] = a.get_editor_property("parent").get_path_name()
        for prop in ("material_domain", "blend_mode", "shading_model", "two_sided",
                     "used_with_volumetric_cloud" if hasattr(base, "used_with_volumetric_cloud") else None):
            if prop:
                try:
                    d[prop] = _s(base.get_editor_property(prop))
                except Exception as e:
                    d[prop] = "?" + str(e)[:60]
        try:
            d["scalars"] = {str(n): mel.get_material_instance_scalar_parameter_value(a, n)
                            if isinstance(a, unreal.MaterialInstance) else mel.get_material_default_scalar_parameter_value(a, n)
                            for n in mel.get_scalar_parameter_names(a)}
            d["vectors"] = {str(n): _s(mel.get_material_instance_vector_parameter_value(a, n)
                                       if isinstance(a, unreal.MaterialInstance) else mel.get_material_default_vector_parameter_value(a, n))
                            for n in mel.get_vector_parameter_names(a)}
            tex = {}
            for n in mel.get_texture_parameter_names(a):
                t = (mel.get_material_instance_texture_parameter_value(a, n) if isinstance(a, unreal.MaterialInstance)
                     else mel.get_material_default_texture_parameter_value(a, n))
                tex[str(n)] = t.get_path_name() if t else None
            d["textures"] = tex
            d["static_switches"] = [str(n) for n in mel.get_static_switch_parameter_names(a)]
        except Exception as e:
            d["param_error"] = str(e)[:200]
        if isinstance(a, unreal.Material):
            try:
                d["num_expressions"] = mel.get_num_material_expressions(a)
            except Exception:
                pass
            try:
                st = mel.get_statistics(a)
                d["stats"] = {"ps": st.num_pixel_shader_instructions, "samplers": st.num_samplers}
            except Exception:
                pass
    if isinstance(a, unreal.Texture):
        for prop in ("compression_settings", "srgb", "lod_group", "filter", "address_x", "address_y"):
            try:
                d[prop] = _s(a.get_editor_property(prop))
            except Exception:
                pass
        for m in ("blueprint_get_size_x", "blueprint_get_size_y"):
            if hasattr(a, m):
                d[m[-6:]] = getattr(a, m)()
        if isinstance(a, unreal.VolumeTexture):
            for prop in ("source2d_texture", "source2d_tile_size_x", "source2d_tile_size_y", "address_mode"):
                try:
                    d[prop] = _s(a.get_editor_property(prop))
                except Exception:
                    pass
        try:
            d["imported_size"] = _s(a.get_editor_property("imported_size"))
        except Exception:
            pass
    return d


mcp_result = [_describe(p) for p in (globals().get("mcp_args") or {}).get("assets", [])]
