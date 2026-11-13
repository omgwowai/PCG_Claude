# cs_wx_resolve.py -- what a City Sample weather preset sets, as plain values (pure Python, no unreal import).
# cs_weather.py apply writes the result into the level, the cloud director (cs_cloud_rt.py, cs_cloud_motion.py) blends
# two results, the offline tests check it. The rule is the one cs_weather.py has used since 2026-11-11: a managed property
# takes the call's override, else the preset's value, else the 10:00 base value, else the level's original value from the
# snapshot (Saved/Reports/cs_weather2/original_extra.json), else it is left alone.
import cs_weather_presets as P

SECTIONS = ["DirectionalLightComponent", "SkyAtmosphereComponent", "SkyLightComponent", "VolumetricCloudComponent",
            "ExponentialHeightFogComponent"]
BASE_PRESET = {"title": "上午 10:00 晴天积云（基线）", "sun": P.BASE_SUN + [""], "set": {},
               "cloud": {"mi": "MI_CS_CumulusCloud_Clear", "params": {}}, "ppv": {}, "shots": []}


def preset(name):
    return BASE_PRESET if name == "base" else P.PRESETS[name]


def names():
    """Every preset the driver knows: the 10:00 base, the photo weathers, the art weathers."""
    return ["base"] + list(P.ORDER) + list(P.ART_ORDER)


def managed(extra_keys=()):
    """{section: properties}: the 10:00 base properties, every property any preset sets, and extra_keys."""
    out = {s: set(P.BASE.get(s, {})) for s in SECTIONS}
    keys = [k for p in P.PRESETS.values() for k in p.get("set", {})] + list(extra_keys)
    for key in keys:
        section, prop = key.split(".", 1)
        out.setdefault(section, set()).add(prop)
    return out


def managed_ppv():
    keys = set(P.BASE["PPV"]) | set(P.CAMERA_LOOK)
    for p in P.PRESETS.values():
        keys |= set(p.get("ppv", {}))
    return keys


def resolve(name, snapshot, overrides=None):
    """Everything preset `name` sets. overrides = an apply call's {"set", "cloud", "ppv", "sun"}."""
    o = overrides or {}
    p = preset(name)
    over_set = o.get("set") or {}
    comps = {}
    for section, props in managed(over_set.keys()).items():
        vals = {}
        for prop in sorted(props):
            key = section + "." + prop
            if key in over_set:
                vals[prop] = over_set[key]
            elif key in p.get("set", {}):
                vals[prop] = p["set"][key][0]
            elif prop in P.BASE.get(section, {}):
                vals[prop] = P.BASE[section][prop]
            else:
                v = (snapshot or {}).get("components", {}).get(section, {}).get(prop)
                if v is not None:
                    vals[prop] = v
        comps[section] = vals
    sun = o.get("sun") or p["sun"][:2]
    params = p["cloud"].get("params", {})
    cloud = dict(P.BASE_CLOUD)
    cloud.update(P.CLOUD_NEUTRAL)
    cloud.update({k: v[0] for k, v in params.items()})
    over_cloud = dict(o.get("cloud") or {})
    layer = comps.get("VolumetricCloudComponent", {})
    if "LayerKm" not in over_cloud and "LayerKm" not in params:
        cloud["LayerKm"] = layer["layer_height"]
    if "BottomKm" not in over_cloud and "BottomKm" not in params:
        cloud["BottomKm"] = layer["layer_bottom_altitude"]
    cloud.update(over_cloud)
    ppv = dict(P.BASE["PPV"])
    if name != "base":
        ppv.update({k: v[0] for k, v in P.CAMERA_LOOK.items()})
    ppv.update({k: v[0] for k, v in p.get("ppv", {}).items()})
    ppv.update(o.get("ppv") or {})
    night = {k: v[0] for k, v in p["night_sky"].items()} if p.get("night_sky") else None
    cvars = dict(P.BASE_CVARS)
    cvars.update(p.get("cvars", {}))
    return {"name": name, "sun": [float(sun[0]), float(sun[1])], "components": comps,
            "cloud": {k: float(v) for k, v in cloud.items()}, "mi": p["cloud"]["mi"], "ppv": ppv,
            "night_sky": night, "cvars": cvars, "motion": p.get("motion")}
