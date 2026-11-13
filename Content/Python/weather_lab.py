"""weather_lab.py -- the lab level /Game/Weather/L_WeatherLab, where the seasonal weather is accepted before it goes into
L_PyWorld (spec §8.4, its first version for M0; plan Task 17). `weather.py lab` calls build().

LAYOUT is the level as data: one row per actor, spawned with its label and the tag TAG. Everything at module level is
pure (Tools/weather/tests/test_weather_lab.py imports this module); `unreal` is imported only inside the editor
functions, and no UObject outlives a call, since one that survives a level switch pins the old world (traps.md 25)."""
from pypcg import level
from weather_assets import MATERIAL as STARS_MATERIAL

LEVEL = "/Game/Weather/L_WeatherLab"
TAG = "WeatherLab"
# Leaving one of these from a script can crash the editor (traps.md 79/83), so the lab phase refuses while one is open.
BIG_LEVELS = (level.DEMO, level.TOWN, level.WORLD, "/Game/PyPCG/L_PyCity", "/Game/PyPCG/L_PyCitySmall")

PLANE = "/Engine/BasicShapes/Plane"         # 100 x 100 cm, pivot at the centre
CUBE = "/Engine/BasicShapes/Cube"           # 100 cm, pivot at the centre
SKY_SPHERE = "/Engine/EngineSky/SM_SkySphere"
STARS_RADIUS_CM = 5000000.0                 # the star sphere's scale is this over the mesh's bounding-sphere radius
DOMAIN_EXTENT_M = 320.0
DOMAIN_REFS = {"sun": "Weather_Sun", "moon": "Weather_Moon", "sky_light": "Weather_SkyLight",   # AWeatherDomain
               "height_fog": "Weather_HeightFog", "post_process": "Weather_PostProcess",       # property -> label
               "stars": "Weather_Stars"}

# The house (cm): a 10 x 8 m footprint (X x Y) centred on (1000, 0); a floor slab from z 0 to 10 (centre z 5); walls
# 30 cm thick and 3 m high standing on it; a 1.2 m door gap centred in the -X wall and a 1.5 m window gap centred in the
# +Y wall; a 12 x 10 x 0.2 m roof slab centred at z 320 that rests on the walls with 1 m eaves all round. The heights of
# the openings are this module's choice: the door and the window head 2.1 m above the floor, the window sill 0.9 m.
HOUSE_X, HOUSE_Y, HOUSE_LX, HOUSE_LY = 1000.0, 0.0, 1000.0, 800.0
FLOOR_T, WALL_T, WALL_H = 10.0, 30.0, 300.0
DOOR_W, DOOR_H = 120.0, 210.0
WINDOW_W, WINDOW_SILL, WINDOW_HEAD = 150.0, 90.0, 210.0
ROOF_LX, ROOF_LY, ROOF_T, ROOF_Z = 1200.0, 1000.0, 20.0, 320.0


def _row(label, what, at=(0, 0, 0), rot=(0, 0, 0), scale=None, **settings):
    """One actor. what: an asset path (a static mesh actor of that mesh) or an unreal class name; at in cm; rot is
    (pitch, yaw, roll) in degrees; scale None keeps the spawned scale; settings are read by the class's _setup branch."""
    return {"label": label, "what": what, "at": tuple(float(v) for v in at), "rot": tuple(float(v) for v in rot),
            "scale": tuple(float(v) for v in scale) if scale else None, "settings": settings}


def _box(label, x0, x1, y0, y1, z0, z1):
    """A Cube row filling [x0, x1] x [y0, y1] x [z0, z1] (cm)."""
    return _row(label, CUBE, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
                scale=((x1 - x0) / 100, (y1 - y0) / 100, (z1 - z0) / 100))


def _house():
    x0, x1 = HOUSE_X - HOUSE_LX / 2, HOUSE_X + HOUSE_LX / 2
    y0, y1 = HOUSE_Y - HOUSE_LY / 2, HOUSE_Y + HOUSE_LY / 2
    yi0, yi1 = y0 + WALL_T, y1 - WALL_T     # the X walls stand between the full-length Y walls
    zf, zt = FLOOR_T, FLOOR_T + WALL_H      # the walls stand on the floor slab and carry the roof
    door, win = DOOR_W / 2, WINDOW_W / 2
    return [
        _box("Lab_House_Floor", x0, x1, y0, y1, 0.0, zf),
        _box("Lab_House_WallNegY", x0, x1, y0, yi0, zf, zt),
        _box("Lab_House_WallPosX", x1 - WALL_T, x1, yi0, yi1, zf, zt),
        _box("Lab_House_WallNegX_1", x0, x0 + WALL_T, yi0, HOUSE_Y - door, zf, zt),      # either side of the door
        _box("Lab_House_WallNegX_2", x0, x0 + WALL_T, HOUSE_Y + door, yi1, zf, zt),
        _box("Lab_House_DoorHead", x0, x0 + WALL_T, HOUSE_Y - door, HOUSE_Y + door, zf + DOOR_H, zt),
        _box("Lab_House_WallPosY_1", x0, HOUSE_X - win, yi1, y1, zf, zt),                # either side of the window
        _box("Lab_House_WallPosY_2", HOUSE_X + win, x1, yi1, y1, zf, zt),
        _box("Lab_House_WindowSill", HOUSE_X - win, HOUSE_X + win, yi1, y1, zf, zf + WINDOW_SILL),
        _box("Lab_House_WindowHead", HOUSE_X - win, HOUSE_X + win, yi1, y1, zf + WINDOW_HEAD, zt),
        _box("Lab_House_Roof", HOUSE_X - ROOF_LX / 2, HOUSE_X + ROOF_LX / 2, HOUSE_Y - ROOF_LY / 2,
             HOUSE_Y + ROOF_LY / 2, ROOF_Z - ROOF_T / 2, ROOF_Z + ROOF_T / 2),
    ]


LAYOUT = [
    _row("Lab_Ground", PLANE, scale=(300, 300, 1)),
    _row("Lab_Slope", CUBE, (-9000, 6000, 1000), rot=(30, 0, 0), scale=(40, 30, 1)),
] + _house() + [
    _row("Weather_Sun", "DirectionalLight", (0, 0, 2000), atmosphere_sun_light_index=0),
    _row("Weather_Moon", "DirectionalLight", (0, 0, 2000), atmosphere_sun_light_index=1, intensity=0.0),
    _row("Weather_SkyAtmosphere", "SkyAtmosphere"),
    _row("Weather_SkyLight", "SkyLight", (0, 0, 500), real_time_capture=True),
    _row("Weather_HeightFog", "ExponentialHeightFog", volumetric_fog=True),
    _row("Weather_PostProcess", "PostProcessVolume", unbound=True),
    _row("Weather_Clouds", "VolumetricCloud"),                                 # the engine's default cloud material
    _row("Weather_Stars", SKY_SPHERE, radius_cm=STARS_RADIUS_CM, material=STARS_MATERIAL),
    _row("Weather_Domain", "WeatherDomain", extent_meters=DOMAIN_EXTENT_M),   # and the references in DOMAIN_REFS
    _row("WeatherCam_overview", "CameraActor", (-6000, -6000, 1500), rot=(-12, 45, 0)),
    _row("WeatherCam_eaves", "CameraActor", (1700, -900, 170), rot=(5, 150, 0)),
    _row("WeatherCam_slope", "CameraActor", (-3000, 1000, 300), rot=(8, 135, 0)),
    _row("Lab_PlayerStart", "PlayerStart", (0, -2000, 100)),
]


def refusal(current_map):
    """None when the lab phase may run with `current_map` (a map's package path) open, else its abort result."""
    if current_map in BIG_LEVELS:
        return {"abort": "%s is open, and leaving it from a script can crash the editor (traps.md 79/83): open an empty "
                         "level (File > New Level > Empty Level) or %s by hand, then run lab again; nothing was changed"
                         % (current_map, LEVEL)}
    return None


def _setup(actor, row):
    """The row's settings on a spawned actor."""
    import unreal
    s, what = row["settings"], row["what"]
    if what == "DirectionalLight":
        light = actor.light_component
        light.set_mobility(unreal.ComponentMobility.MOVABLE)
        light.set_atmosphere_sun_light(True)
        light.set_atmosphere_sun_light_index(s["atmosphere_sun_light_index"])
        if "intensity" in s:
            light.set_intensity(s["intensity"])
    elif what == "SkyLight":
        light = actor.light_component
        light.set_mobility(unreal.ComponentMobility.MOVABLE)
        light.set_real_time_capture(s["real_time_capture"])
    elif what == "ExponentialHeightFog":
        actor.component.set_volumetric_fog(s["volumetric_fog"])           # the property is enable_volumetric_fog
    elif what == "PostProcessVolume":
        actor.set_editor_property("unbound", s["unbound"])
    elif what == "VolumetricCloud":
        cloud = actor.volumetric_cloud_component
        if cloud.get_editor_property("material") is None:                 # the class default is the engine's cloud
            cloud.set_material(unreal.get_default_object(unreal.VolumetricCloudComponent).get_editor_property("material"))
    elif what == SKY_SPHERE:
        mesh = actor.static_mesh_component
        k = s["radius_cm"] / mesh.get_editor_property("static_mesh").get_bounds().sphere_radius
        actor.set_actor_scale3d(unreal.Vector(k, k, k))
        mesh.set_collision_profile_name("NoCollision")
        mesh.set_cast_shadow(False)
        material = unreal.load_asset(s["material"])
        if material is None:   # the slot would keep the sky sphere's own material without a word
            raise RuntimeError("could not load %s for %s (run weather.py assets first)" % (s["material"], row["label"]))
        mesh.set_material(0, material)
    elif what == "WeatherDomain":
        actor.set_editor_property("extent_meters", s["extent_meters"])


def _spawn(eas, row):
    import unreal
    at = unreal.Vector(*row["at"])
    pitch, yaw, roll = row["rot"]
    rot = unreal.Rotator(pitch=pitch, yaw=yaw, roll=roll)
    what = row["what"]
    if what.startswith("/"):
        asset = unreal.load_asset(what)
        actor = eas.spawn_actor_from_object(asset, at, rot) if asset else None
    else:
        actor = eas.spawn_actor_from_class(getattr(unreal, what), at, rot)
    if actor is None:
        raise RuntimeError("could not spawn %s (%s)" % (row["label"], what))
    actor.set_actor_label(row["label"])
    actor.set_editor_property("tags", [TAG])
    if row["scale"]:
        actor.set_actor_scale3d(unreal.Vector(*row["scale"]))
    _setup(actor, row)
    return actor


def _populate(eas):
    """Spawn LAYOUT and point the domain at its sky actors; returns the number of actors spawned."""
    actors = {row["label"]: _spawn(eas, row) for row in LAYOUT}
    domain = actors["Weather_Domain"]
    for prop, label in DOMAIN_REFS.items():
        domain.set_editor_property(prop, actors[label])
    return len(actors)


def _clear(eas):
    """Destroy the actors of an earlier build (those tagged TAG); returns how many."""
    old = [a for a in eas.get_all_level_actors() if TAG in [str(t) for t in a.get_editor_property("tags")]]
    if old and not eas.destroy_actors(old):
        raise RuntimeError("could not destroy the %d %s actors of the earlier build" % (len(old), TAG))
    return len(old)


def build(force=False):
    """Open the lab, or create it, or with `force` rebuild its actors; the level asset itself is never deleted.

    Refused while a big level is open (refusal()), and before a level switch while a map has unsaved changes, since
    new_level and load_level close the current level without saving. If the lab exists and not `force`, opens it when it
    is not current and returns {"opened": LEVEL}. Otherwise creates it (new_level, not partitioned) or opens it, destroys
    the TAG actors of an earlier build, spawns LAYOUT and saves: {"level", "actors", "saved", "created", "removed"}."""
    import gc
    import unreal
    current = level.current_map()
    refused = refusal(current)
    if refused:
        return refused
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    exists = bool(unreal.EditorAssetLibrary.does_asset_exist(LEVEL))
    if current != LEVEL:
        dirty = [str(p.get_name()) for p in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()]
        if dirty:
            return {"abort": "unsaved maps %s: opening or creating the lab would close them without saving; save or "
                             "discard them, then run lab again; nothing was changed" % dirty}
        gc.collect()        # no Python wrapper may keep the closing world alive (traps.md 25)
        how = "load_level" if exists else "new_level"
        ok = les.load_level(LEVEL) if exists else les.new_level(LEVEL, is_partitioned_world=False)
        if not ok or level.current_map() != LEVEL:
            return {"abort": "%s(%s) returned %s; the current map is %s" % (how, LEVEL, ok, level.current_map())}
    if exists and not force:
        return {"opened": LEVEL}
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    removed = _clear(eas)
    actors = _populate(eas)
    return {"level": LEVEL, "actors": actors, "saved": bool(les.save_current_level()), "created": not exists,
            "removed": removed}
