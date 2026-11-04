"""weather_assets.py -- the generated plugin assets of the seasonal weather system (spec §1.5; plan Task 16), written by
`weather.py assets` into the plugin content /SeasonalWeather (Plugins/SeasonalWeather/Content):

  Materials/MPC_Weather            the parameter collection the subsystem writes every update (MPC_SCALARS, MPC_VECTORS)
  Textures/T_WeatherStars          Saved/Weather/T_WeatherStars.png from Tools/weather/gen_starmap.py (plan ruling P5)
  Materials/M_WeatherStars         unlit two-sided sky material: star map RGB x MPC_Weather.StarIntensity -> emissive
  Data/DA_WeatherType_<Type>       UWeatherTypeAsset, TYPE_LOOKS
  Data/DA_SeasonLook_<Season>      USeasonLookAsset, SEASON_LOOKS
  Orchestrator/ST_WeatherType, ST_Season   built by UWeatherEditorLibrary.BuildOrchestratorStateTrees (C++)

Idempotent (plan ruling P6): it creates what is missing and updates values in place. The MPC is never recreated and its
parameter arrays are never rebuilt, since a material's collection-parameter node stores the parameter's GUID; a later run
appends only the parameters the MPC lacks. The star material's graph is rebuilt on every run. Nothing is saved before the
end: /SeasonalWeather, the re-imported star map included, is saved only when both StateTrees compile (the library marks
their packages dirty even when a compile fails).

The tables and helpers at module level are pure; `unreal` is imported inside the editor functions."""
import os
import re

from weather_ref.sky import LOOK_FIELDS

# Looks in weather_ref.sky.LOOK_FIELDS order: sun, moon, sky_light, fog_density, fog_height_falloff, white_temp_offset,
# saturation, contrast, exposure_bias, cloud_cover.
TYPE_LOOKS = {
    "Clear":        (1.00, 1.00, 1.00, 1.0, 1.0,    0.0, 1.00, 1.00, 0.0, 0.05),
    "FairCumulus":  (0.90, 0.90, 1.00, 1.0, 1.0,    0.0, 1.00, 1.00, 0.0, 0.35),
    "Overcast":     (0.25, 0.30, 0.80, 2.0, 0.8,  500.0, 0.80, 0.90, 0.3, 0.95),
    "FrontalRain":  (0.15, 0.20, 0.65, 3.0, 0.7,  700.0, 0.70, 0.85, 0.5, 1.00),
    "Thunderstorm": (0.08, 0.10, 0.50, 3.5, 0.7,  900.0, 0.65, 0.95, 0.6, 1.00),
    "Fog":          (0.40, 0.40, 0.90, 8.0, 2.5,  300.0, 0.75, 0.80, 0.2, 0.60),
    "Snow":         (0.30, 0.35, 0.90, 2.5, 0.8,  800.0, 0.70, 0.90, 0.3, 0.95),
    "Blizzard":     (0.10, 0.10, 0.70, 6.0, 0.6, 1200.0, 0.55, 0.85, 0.5, 1.00),
}
SEASON_LOOKS = {   # cloud_cover is ignored for seasons (Combine keeps the type's)
    "Spring": (1.0, 1.0, 1.0, 1.0, 1.0, -200.0, 1.05, 1.00, 0.0, 0.0),
    "Summer": (1.0, 1.0, 1.0, 0.9, 1.0, -400.0, 1.10, 1.05, 0.0, 0.0),
    "Autumn": (1.0, 1.0, 1.0, 1.2, 1.0, -600.0, 1.00, 1.00, 0.0, 0.0),
    "Winter": (1.0, 1.0, 1.0, 1.1, 1.0,  600.0, 0.85, 0.95, 0.2, 0.0),
}
# The names the subsystem writes (UWeatherSubsystem::WriteMpc); the values are only the collection's defaults.
MPC_SCALARS = {"TimeOfDay": 12.0, "MoonIllumination": 0.0, "StarIntensity": 0.0, "CloudCover": 0.0}
MPC_VECTORS = {"SeasonWeights": (1, 0, 0, 0), "SunDirection": (0, 0, 1, 0), "MoonDirection": (0, 0, -1, 0),
               "CameraWind": (0, 0, 0, 0), "CameraWeather": (0, 0, 15, 0.6)}

ROOT = "/SeasonalWeather"
MPC = ROOT + "/Materials/MPC_Weather"
MATERIAL = ROOT + "/Materials/M_WeatherStars"
TEXTURE_DIR = ROOT + "/Textures"
TEXTURE = TEXTURE_DIR + "/T_WeatherStars"
DATA_DIR = ROOT + "/Data"
TREES_DIR = ROOT + "/Orchestrator"
STAR_PNG = os.path.join("Saved", "Weather", "T_WeatherStars.png")   # relative to the repository
NO_PNG = "run C:/Python314/python.exe Tools/weather/gen_starmap.py first"


def enum_member(name):
    """The Python name of an EWeatherType / EWeatherSeason member: "FairCumulus" -> "FAIR_CUMULUS"."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).upper()


def look_kwargs(values):
    """A table row as unreal.WeatherLook keyword arguments; a row must hold all of LOOK_FIELDS."""
    return dict(zip(LOOK_FIELDS, values, strict=True))


def missing(table, present):
    """The names of `table` that are not in `present`, in table order."""
    return [n for n in table if n not in present]


def _tools():
    import unreal
    return unreal.AssetToolsHelpers.get_asset_tools()


def _load_or_create(path, cls, factory):
    """(asset, created): the asset at `path` if it exists, otherwise a new one made by `factory`."""
    import unreal
    created = not unreal.EditorAssetLibrary.does_asset_exist(path)
    if created:
        folder, name = path.rsplit("/", 1)
        asset = _tools().create_asset(name, folder, cls, factory)
    else:
        asset = unreal.load_asset(path)
    if not isinstance(asset, cls):
        raise RuntimeError("%s %s" % (path, "could not be created" if created else "is not a %s" % cls.__name__))
    return asset, created


def add_missing_parameters(mpc):
    """Appends the MPC_SCALARS / MPC_VECTORS entries `mpc` lacks and returns their names. The entries already there keep
    their values and GUIDs; the property notification rebuilds the collection's uniform buffer layout."""
    import unreal
    added = []
    for prop, table, cls, value in (
            ("scalar_parameters", MPC_SCALARS, unreal.CollectionScalarParameter, float),
            ("vector_parameters", MPC_VECTORS, unreal.CollectionVectorParameter, lambda v: unreal.LinearColor(*v))):
        params = list(mpc.get_editor_property(prop))
        names = missing(table, {str(p.get_editor_property("parameter_name")) for p in params})
        if not names:
            continue
        for name in names:
            param = cls()
            param.set_editor_property("parameter_name", name)
            param.set_editor_property("default_value", value(table[name]))
            params.append(param)
        mpc.set_editor_property(prop, params)
        added += names
    return added


def _mpc():
    import unreal
    mpc, created = _load_or_create(MPC, unreal.MaterialParameterCollection,
                                   unreal.MaterialParameterCollectionFactoryNew())
    return mpc, {"created": created, "added": add_missing_parameters(mpc)}


def _import_stars(png):
    """Imports (or re-imports over) T_WeatherStars and returns whether this run's import produced it. The task does not
    save: the imported package stays dirty and run() saves it with the other assets, only when the StateTrees compile
    (Controller Ruling 27)."""
    import unreal
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", png)
    task.set_editor_property("destination_path", TEXTURE_DIR)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", False)
    _tools().import_asset_tasks([task])
    return any(str(p).split(".")[0] == TEXTURE for p in task.get_editor_property("imported_object_paths"))


def _link(ok, what):
    if not ok:
        raise RuntimeError("M_WeatherStars: cannot connect %s" % what)


def _star_material(texture, mpc):
    """M_WeatherStars rebuilt from an empty graph: TextureSample(T_WeatherStars).RGB x CollectionParameter(MPC_Weather,
    StarIntensity) -> Emissive Color, unlit, sky, two-sided. Properties are set without notification (traps.md 100) and
    compiled at the end, except the parameter name, whose notification resolves the node's parameter GUID."""
    import unreal
    mel = unreal.MaterialEditingLibrary
    never = unreal.PropertyAccessChangeNotifyMode.NEVER
    m, _ = _load_or_create(MATERIAL, unreal.Material, unreal.MaterialFactoryNew())
    mel.delete_all_material_expressions(m)
    for e in list(mel.get_material_expressions(m)):     # delete_all skips nodes while it removes them (traps.md 104)
        mel.delete_material_expression(m, e)
    if mel.get_num_material_expressions(m):
        raise RuntimeError("M_WeatherStars: %d expressions survived the clear" % mel.get_num_material_expressions(m))
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT, never)
    m.set_editor_property("is_sky", True, never)
    m.set_editor_property("two_sided", True, never)
    tex = mel.create_material_expression(m, unreal.MaterialExpressionTextureSample, -600, 0)
    tex.set_editor_property("texture", texture, never)
    par = mel.create_material_expression(m, unreal.MaterialExpressionCollectionParameter, -600, 300)
    par.set_editor_property("collection", mpc, never)
    # notified: the node's PostEditChangeProperty looks up the parameter's GUID (ParameterId), which it compiles from
    par.set_editor_property("parameter_name", "StarIntensity", unreal.PropertyAccessChangeNotifyMode.ALWAYS)
    mul = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -250, 100)
    _link(mel.connect_material_expressions(tex, "RGB", mul, "A"), "TextureSample.RGB -> Multiply.A")
    _link(mel.connect_material_expressions(par, "", mul, "B"), "StarIntensity -> Multiply.B")
    _link(mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR), "Multiply -> Emissive Color")
    errors = [str(e) for e in mel.recompile_material(m)]
    if errors:
        raise RuntimeError("M_WeatherStars does not compile: %s" % "; ".join(errors))


def _stars(png, mpc):
    import unreal
    imported = _import_stars(png)
    texture = unreal.load_asset(TEXTURE)
    if not isinstance(texture, unreal.Texture2D):
        raise RuntimeError("%s was not imported from %s" % (TEXTURE, png))
    _star_material(texture, mpc)
    return {"imported": imported, "material": MATERIAL}


def _looks():
    """DA_WeatherType_<Type> and DA_SeasonLook_<Season>, created if missing; their type / season and look are set on every
    run (unchanged values leave the asset clean)."""
    import unreal
    counts = {}
    for key, table, cls, prop, enum, prefix in (
            ("types", TYPE_LOOKS, unreal.WeatherTypeAsset, "type", unreal.WeatherType, "DA_WeatherType_"),
            ("seasons", SEASON_LOOKS, unreal.SeasonLookAsset, "season", unreal.WeatherSeason, "DA_SeasonLook_")):
        factory = unreal.DataAssetFactory()
        factory.set_editor_property("data_asset_class", cls)
        counts[key] = 0
        for name, values in table.items():
            asset, _ = _load_or_create("%s/%s%s" % (DATA_DIR, prefix, name), cls, factory)
            asset.set_editor_property(prop, getattr(enum, enum_member(name)))
            asset.set_editor_property("look", unreal.WeatherLook(**look_kwargs(values)))
            counts[key] += 1
    return counts


def run(repo_dir):
    """Generates every asset above and saves /SeasonalWeather when the StateTrees compiled:
    {"mpc": {"created", "added"}, "stars": {"imported", "material"}, "looks": {"types", "seasons"}, "trees": "" or the
    compiler errors, "saved"}; {"abort": ...} when the star map has not been generated."""
    png = os.path.normpath(os.path.join(repo_dir, STAR_PNG))
    if not os.path.isfile(png):
        return {"abort": NO_PNG}
    import unreal
    mpc, mpc_result = _mpc()
    stars = _stars(png, mpc)
    looks = _looks()
    trees = str(unreal.WeatherEditorLibrary.build_orchestrator_state_trees(TREES_DIR))
    saved = trees == "" and bool(unreal.EditorAssetLibrary.save_directory(ROOT, only_if_is_dirty=True, recursive=True))
    return {"mpc": mpc_result, "stars": stars, "looks": looks, "trees": trees, "saved": saved}
