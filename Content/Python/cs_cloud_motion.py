# cs_cloud_motion.py -- the motion model of the City Sample cloud director (docs/superpowers/specs/2026-11-12-cs-cloud-
# motion-design.md §3-4): from the simulated time, the two cloud slots and the transition, every value one frame writes.
# Pure Python (no unreal import) and deterministic: the director (cs_cloud_rt.py) calls it every editor tick and for
# every recorded frame; the offline tests (Tools/cs_weather/tests) call it directly.
#
# Units: simulated seconds; wind m/s; distances km; compass headings in degrees, north = +X, east = +Y (a camera's UE
# yaw is its compass heading). A resolved preset is a cs_wx_resolve.resolve() result. A slot is
#   {"preset": name, "base": resolved cloud params, "motion": motion_for(...), "tau0": simulated time at age 0,
#    "vc": its VolumetricCloudComponent values, "clouds_light": its DirectionalLight cast_shadows_on_clouds}
# and a state is {"slots": {"A": slot, "B": slot or None}, "look": the resolved preset whose light / look is on screen,
#                 "trans": None or the running transition}.
import math

import cs_cloud_code as CC

SPEED = 30.0                  # default simulated seconds per wall second
EVO_LOOP = 8.0                # lifetimes per z period of the evolution / phase noises (8 Worley cells per period)
FORM_WINDOW = [0.3, 1.0]      # default share of a transition in which the incoming slot forms
FADE_WINDOW = [0.0, 0.7]      # ... and the outgoing slot dissipates
LIGHT_WINDOW = [0.1, 0.9]     # share of a "full" transition in which the light / look moves
DOME_LUX = 10.0               # the star dome exists while the light is dimmer than this (night transitions)
SAMPLE_SCALE_MAX = 1024.0 / 96.0   # r.VolumetricCloud.ViewRaySampleMaxCount / BaseViewRaySampleCount
FRONT_PUSH_KM = 10.0          # how far a dissipating gust front keeps moving
MIN_TRANSITION_S = 10.0       # shorter transitions (simulated seconds) are refused
LAYER_RAMP = 0.1              # share of a transition over which the cloud component at least moves toward / from the
                              # union; the incoming slot forms only after it, the outgoing one is gone before it
ADV_BUDGET_KM = 13000.0       # |Adv| below which the shape noise keeps < 1/4 texel of float32 quantization (spec §3.6)
LIGHT = "DirectionalLightComponent"
CLOUD = "VolumetricCloudComponent"
WRAPPED = {"DetailOffU", "DetailOffV", "DetailOffW", "Detail2OffU", "Detail2OffV", "Detail2OffW", "EvoPhase",
           "BoilShape", "BoilBillow", "BoilTurret", "MammaPhase", "MackerelPhase", "LumpPhase", "RainFall"}
GLOBAL_PARAMS = ["PixelAngle"] + [n for n, _d, _g in CC.EXTRA_SCALARS]
# motion keys and defaults (None = derived from the preset by motion_for); a preset's "motion" data overrides any of them
MOTION_KEYS = {
    "wind_ms": None, "wind_deg": 250.0, "detail_speed": 1.0, "boil_detail_ms": 0.0, "boil_shape_ms": 0.0,
    "boil_billow_ms": None, "boil_turret_ms": None, "evo_amt": 0.4, "evo_life_min": 20.0, "evo_scale_km": None,
    "mamma_life_min": 10.0, "mackerel_life_min": 15.0, "lump_life_min": 15.0, "rain_fall_ms": 8.0, "clip_speed": 60.0,
    "mods": None, "form_window": None, "fade_window": None,
}


def frac(x):
    return x - math.floor(x)


def heading(deg):
    """Unit vector (x = north, y = east) of a compass heading."""
    a = math.radians(deg)
    return math.cos(a), math.sin(a)


def ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def sub(x, a, b):
    """Eased position of x inside [a, b]: 0 before a, 1 after b."""
    if b <= a:
        return 1.0 if x >= b else 0.0
    return ease((x - a) / (b - a))


def _val(e):
    """A data entry is [value, why]; a plain value passes through."""
    if isinstance(e, list) and len(e) == 2 and isinstance(e[1], str):
        return e[0]
    return e


def _storm(base):
    return base.get("CellStrength", 0.0) > 0.0 and base.get("LensAmt", 0.0) <= 0.0


def motion_for(raw, base):
    """The motion of a slot: MOTION_KEYS, the defaults of spec §3.5 derived from its resolved cloud params `base`, then
    the preset's own "motion" data `raw` ({key: [value, why]}, "mods": [[modulator, why], ...]) on top."""
    m = dict(MOTION_KEYS)
    bottom = base["BottomKm"]
    m["wind_ms"] = 6.0 if bottom < 2.0 else (12.0 if bottom < 6.0 else 30.0)
    m["boil_billow_ms"] = 1.0 if base.get("BillowAmt", 0.0) > 0.0 else 0.0
    m["boil_turret_ms"] = 5.0 if _storm(base) and base.get("TurretAmt", 0.0) > 0.0 else 0.0
    m["evo_scale_km"] = base["WeatherScaleKm"] / 4.0
    m["mods"] = []
    if _storm(base) and base.get("OvershootKm", 0.0) > 0.0:
        m["mods"].append({"param": "OvershootKm", "osc": [0.3 * base["OvershootKm"], 8.0, 0.0]})
    m["form_window"] = [0.0, 1.0] if _storm(base) else list(FORM_WINDOW)
    m["fade_window"] = list(FADE_WINDOW)
    for key, e in (raw or {}).items():
        if key not in MOTION_KEYS:
            raise KeyError("unknown motion key %s" % key)
        if key == "mods":
            m[key] = [_val(item) for item in e]
        else:
            v = _val(e)
            m[key] = list(v) if isinstance(v, list) else v
    return m


def time_params(base, m, tau):
    """The time inputs of one slot at age tau (spec §2.3, §3.2). Wrapped values are computed in double precision."""
    v = m["wind_ms"] * 1.0e-3
    hx, hy = heading(m["wind_deg"])
    ax, ay = v * tau * hx, v * tau * hy
    out = {"AdvX": ax, "AdvY": ay}
    sa = math.radians(base["StretchAngle"])
    sdx, sdy = math.cos(sa), math.sin(sa)
    kd = m["detail_speed"]
    qx = (ax * sdx + ay * sdy) * kd / max(base["StretchX"], 0.001)
    qy = (-ax * sdy + ay * sdx) * kd
    s = base["DetailScaleKm"]
    rise = m["boil_detail_ms"] * 1.0e-3 * tau
    d = (-qx / s, -qy / s, -rise / s)            # the detail lookup samples at x - (air displacement)
    for i, c in enumerate("UVW"):
        out["DetailOff" + c] = frac(d[i])
        out["Detail2Off" + c] = frac(2.71 * d[i])
    out["EvoAmt"] = m["evo_amt"]
    out["EvoScaleKm"] = m["evo_scale_km"]
    out["EvoPhase"] = frac(tau / (EVO_LOOP * m["evo_life_min"] * 60.0))
    out["BoilShape"] = frac(-m["boil_shape_ms"] * 1.0e-3 * tau / base["ShapeScaleKm"])
    out["BoilBillow"] = frac(-m["boil_billow_ms"] * 1.0e-3 * tau / (base["BillowScaleKm"] * 8.0))
    out["BoilTurret"] = frac(-m["boil_turret_ms"] * 1.0e-3 * tau / (base["TurretScaleKm"] * 8.0))
    out["MammaPhase"] = frac(tau / (EVO_LOOP * m["mamma_life_min"] * 60.0))
    out["MackerelPhase"] = frac(tau / (EVO_LOOP * m["mackerel_life_min"] * 60.0))
    out["LumpPhase"] = frac(tau / (EVO_LOOP * m["lump_life_min"] * 60.0))
    out["RainFall"] = frac(0.08 * m["rain_fall_ms"] * 1.0e-3 * tau)
    return out


def apply_mods(params, m, tau):
    """The preset's modulators (spec §3.3); every one leaves params unchanged at tau = 0."""
    for mod in m["mods"]:
        if "osc" in mod:
            amp, period_min, ph = mod["osc"]
            w = 2.0 * math.pi * tau / (period_min * 60.0)
            params[mod["param"]] += amp * (math.sin(w + ph) - math.sin(ph))
        elif "approach" in mod:
            dist, speed, deg = mod["approach"]
            v = speed * 1.0e-3
            d = v * tau if tau < 0.0 else dist * (1.0 - math.exp(-v * tau / max(dist, 1.0e-6)))
            hx, hy = heading(deg)
            ps = mod["params"]
            for i in range(0, len(ps), 2):
                params[ps[i]] += d * hx
                params[ps[i + 1]] += d * hy
        else:
            raise KeyError("unknown modulator %s" % sorted(mod))
    return params


def new_slot(resolved, t, age=0.0):
    """A slot holding the resolved preset at simulated time t, aged `age` at t. The incoming slot of a transition starts
    at minus the transition's length, so it reaches age 0 -- the designed look -- when the transition ends."""
    base = dict(resolved["cloud"])
    light = resolved["components"].get(LIGHT, {})
    return {"preset": resolved["name"], "base": base, "motion": motion_for(resolved.get("motion"), base),
            "tau0": float(t) - float(age), "vc": dict(resolved["components"].get(CLOUD, {})),
            "clouds_light": bool(light.get("cast_shadows_on_clouds", False))}


def slot_params(slot, t):
    """Every material parameter of a slot at simulated time t (no transition tracks)."""
    tau = t - slot["tau0"]
    p = dict(slot["base"])
    p.update(time_params(slot["base"], slot["motion"], tau))
    apply_mods(p, slot["motion"], tau)
    p["SlotOn"] = 1.0
    return p


def adv_km(slot, t):
    """How far the slot's air has moved (km): the float32 precision budget of spec §3.6."""
    return abs(slot["motion"]["wind_ms"] * 1.0e-3 * (t - slot["tau0"]))


def mid_params(pa, pb, glob_a, glob_b, w):
    """The MID's values: slot A under the plain names, slot B under "B_" names (only B_SlotOn = 0 when pb is None), the
    shared parameters (GLOBAL_PARAMS) blended from glob_a to glob_b by w."""
    mid = {n: float(pa[n]) for n in CC.SLOT_NAMES}
    if pb is None:
        mid[CC.slot_name("SlotOn", "B")] = 0.0
    else:
        mid.update({CC.slot_name(n, "B"): float(pb[n]) for n in CC.SLOT_NAMES})
    for n in GLOBAL_PARAMS:
        a = glob_a[n]
        b = glob_b[n] if glob_b is not None else a
        mid[n] = float(a + (b - a) * w)
    return mid


def look_static(r, clouds_light=None):
    """The look of one resolved preset: its component values except the cloud component's, the sun, the post-process
    values and the star dome. clouds_light (the cloud slot's cast_shadows_on_clouds) overrides the light's flag."""
    comps = {s: dict(v) for s, v in r["components"].items() if s != CLOUD}
    if clouds_light is not None and LIGHT in comps:
        comps[LIGHT]["cast_shadows_on_clouds"] = bool(clouds_light)
    night = r.get("night_sky")
    return {"components": comps, "sun": [float(r["sun"][0]), float(r["sun"][1])], "ppv": dict(r["ppv"]),
            "dome": bool(night), "stars": dict(night) if night else None}


def new_state(resolved, t):
    return {"slots": {"A": new_slot(resolved, t), "B": None}, "look": resolved, "trans": None}


def frame(state, t, ppv_defaults):
    """Every value of one frame at simulated time t: {"t", "p", "f", "g", "mid", "vc", "look"}. During a transition the
    outgoing slot follows its fade tracks, the incoming one its form tracks, and the look moves in the light window."""
    a = state["slots"]["A"]
    pa = slot_params(a, t)
    tr = state["trans"]
    if tr is None:
        return {"t": t, "p": None, "f": None, "g": None, "mid": mid_params(pa, None, a["base"], None, 0.0),
                "vc": dict(a["vc"]), "look": look_static(state["look"], a["clouds_light"])}
    b = state["slots"]["B"]
    raw = progress(state, t)
    p = ease(raw)
    fade, form = effective_windows(a["motion"]["fade_window"], b["motion"]["form_window"])
    f = _window(p, fade)
    g = _window(p, form)
    apply_tracks(pa, fade_tracks(a["base"]), f, forming=False)
    apply_push(pa, fade_push(a["base"]), f)
    pa["SlotOn"] = 0.0 if f >= 1.0 else 1.0
    pb = slot_params(b, t)
    apply_tracks(pb, form_tracks(b["base"]), g, forming=True)
    pb["SlotOn"] = 1.0 if g > 0.0 else 0.0
    clouds_light = (a["clouds_light"] and f <= 0.9) or (b["clouds_light"] and g >= 0.1)
    return {"t": t, "p": raw, "f": f, "g": g, "mid": mid_params(pa, pb, a["base"], b["base"], p),
            "vc": vc_at(a["vc"], b["vc"], p, fade, form), "look": look_trans(state, p, ppv_defaults, clouds_light)}


def _window(p, w):
    return min(max((p - w[0]) / (w[1] - w[0]), 0.0), 1.0)


def effective_windows(fade, form):
    """The outgoing slot's fade window ends by 1 - LAYER_RAMP and the incoming slot's form window starts at LAYER_RAMP or
    later, so the cloud component can move from the outgoing layer to the union before the incoming slot is on, and from
    the union to the incoming layer after the outgoing slot is off (vc_at)."""
    fe = min(fade[1], 1.0 - LAYER_RAMP)
    fs = min(fade[0], fe - 0.05)
    gs = max(form[0], LAYER_RAMP)
    ge = max(form[1], gs + 0.05)
    return [fs, fe], [gs, ge]


def _lerp_vc(x, y, w):
    """Blend two cloud-component dicts: numbers linearly, flags on while either is on (the end values at w = 0 / 1)."""
    out = {}
    for k in set(x) | set(y):
        a, b = x.get(k, y.get(k)), y.get(k, x.get(k))
        if isinstance(a, bool) or isinstance(b, bool):
            out[k] = a if w <= 0.0 else (b if w >= 1.0 else bool(a) or bool(b))
        elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
            out[k] = a + (b - a) * w
        else:
            out[k] = b if w >= 0.5 else a
    return out


def vc_at(va, vb, p, fade, form):
    """The cloud component at eased progress p (Task 11 ruling, refining spec §4.4): from the outgoing preset's values to
    the union while the incoming slot is still off ([0, form start]), the union while both may be on, and from the union to
    the incoming preset's values once the outgoing slot is off ([fade end, 1]). Continuous at both ends, and the layer
    contains every slot that is on."""
    u = union_vc(va, vb)
    return _lerp_vc(_lerp_vc(va, u, sub(p, 0.0, form[0])), vb, sub(p, fade[1], 1.0))


def _arc(a, b):
    """Signed shortest turn from heading a to heading b (degrees)."""
    return (b - a + 180.0) % 360.0 - 180.0


def _zero_cov(base):
    """A CoverageBias at which the slot's coverage is 0 everywhere (its maximum is CoverageScale + CoverageBias)."""
    return min(base["CoverageBias"] - 1.0, -base["CoverageScale"] - 0.05)


def form_tracks(base):
    """[(param, g0, g1, start)]: while the slot forms (g from 0 to 1) the param goes from start to its value, eased over
    [g0, g1] (spec §4.3). At g = 0 the slot is empty, so switching it on shows nothing."""
    t = [("CoverageBias", 0.0, 0.8, _zero_cov(base)), ("DensityScale", 0.0, 0.6, 0.4 * base["DensityScale"]),
         ("BillowAmt", 0.4, 1.0, 0.0)]
    if base["TypeMax"] > base["TypeMin"]:
        t.append(("TypeMax", 0.2, 1.0, base["TypeMin"]))
    if base.get("MackerelAmt", 0.0) > 0.0:
        t.append(("MackerelGap", 0.0, 0.8, 1.0))
    if _storm(base):
        t += [("CellStrength", 0.0, 0.15, 0.0), ("CellRadiusKm", 0.0, 0.5, 0.35 * base["CellRadiusKm"]),
              ("CellTopH", 0.05, 0.6, 0.05), ("CellSolid", 0.3, 0.7, 0.0),
              ("AnvilRadiusKm", 0.55, 0.9, base["CellRadiusKm"]), ("AnvilShiftKm", 0.6, 1.0, 0.0),
              ("OvershootKm", 0.75, 0.95, 0.0), ("TurretAmt", 0.4, 1.0, 0.0), ("MammaAmt", 0.85, 1.0, 0.0)]
    if base.get("RainDensity", 0.0) > 0.0:
        t.append(("RainDensity", 0.6, 0.9, 0.0))
    if base.get("FrontAmt", 0.0) > 0.0:
        t.append(("FrontAmt", 0.0, 0.4, 0.0))
    if base.get("LensAmt", 0.0) > 0.0:
        t += [("LensCut", 0.0, 0.7, 1.0), ("LensPlates", 0.4, 1.0, 1.0)]
    return t


def fade_tracks(base):
    """[(param, f0, f1, end)]: while the slot dissipates (f from 0 to 1) the param goes from its value to end, eased over
    [f0, f1]. Not the reverse of forming: a storm loses its updraft first, its column collapses, its anvil goes last.
    At f = 1 the slot is empty, so switching it off shows nothing."""
    t = [("CoverageBias", 0.2, 1.0, _zero_cov(base)), ("DensityScale", 0.0, 0.8, 0.3 * base["DensityScale"]),
         ("BillowAmt", 0.0, 0.5, 0.0)]
    if base["TypeMax"] > base["TypeMin"]:
        t.append(("TypeMax", 0.0, 0.6, base["TypeMin"]))
    if base.get("MackerelAmt", 0.0) > 0.0:
        t.append(("MackerelGap", 0.2, 1.0, 1.0))
    if _storm(base):
        t += [("OvershootKm", 0.0, 0.3, 0.0), ("TurretAmt", 0.0, 0.4, 0.0), ("CellSolid", 0.0, 0.5, 0.0),
              ("CellRadiusKm", 0.2, 0.7, 0.05 * base["CellRadiusKm"]), ("MammaAmt", 0.3, 0.7, 0.0),
              ("CellDensity", 0.6, 1.0, 0.0), ("CellStrength", 0.6, 1.0, 0.0)]
    if base.get("RainDensity", 0.0) > 0.0:
        t.append(("RainDensity", 0.0, 0.4, 0.0))
    if base.get("FrontAmt", 0.0) > 0.0:
        t += [("FrontAmt", 0.2, 1.0, 0.0), ("FrontDensity", 0.2, 1.0, 0.0)]
    if base.get("LensAmt", 0.0) > 0.0:
        t += [("LensCut", 0.0, 0.8, 1.0), ("LensPlates", 0.0, 0.5, 1.0)]
    return t


def fade_push(base):
    """[(params as x, y pairs, km, heading)]: a dissipating gust front (and its rain) keeps moving forward."""
    if base.get("FrontAmt", 0.0) > 0.0:
        return [(["FrontX", "FrontY", "RainX", "RainY"], FRONT_PUSH_KM, base["FrontAngle"])]
    return []


def apply_tracks(params, tracks, x, forming):
    for name, a, b, other in tracks:
        k = sub(x, a, b)
        target = params[name]
        params[name] = other + (target - other) * k if forming else target + (other - target) * k
    return params


def apply_push(params, pushes, f):
    for names, dist, deg in pushes:
        hx, hy = heading(deg)
        d = dist * ease(f)
        for i in range(0, len(names), 2):
            params[names[i]] += d * hx
            params[names[i + 1]] += d * hy
    return params


def union_vc(va, vb):
    """The cloud component in the middle of a transition (spec §4.4; vc_at blends into and out of it): the layer covers
    both slots, the view sample count keeps both slots' step sizes (capped), tracing distances take the larger, flags are
    on if either is on; the rest stays the outgoing one."""
    out = dict(va)
    for k, v in vb.items():
        if isinstance(v, bool):
            out[k] = bool(out.get(k, False)) or v
        elif k in ("tracing_max_distance", "shadow_tracing_distance"):
            out[k] = max(float(out.get(k, v)), float(v))
    bot = min(va["layer_bottom_altitude"], vb["layer_bottom_altitude"])
    top = max(va["layer_bottom_altitude"] + va["layer_height"], vb["layer_bottom_altitude"] + vb["layer_height"])
    out["layer_bottom_altitude"] = bot
    out["layer_height"] = top - bot
    # long in-layer paths take SampleCountMax steps over the whole layer: keep each slot's own step size (capped)
    hu = top - bot
    scale = max(float(va["view_sample_count_scale"]) * hu / max(va["layer_height"], 1.0e-3),
                float(vb["view_sample_count_scale"]) * hu / max(vb["layer_height"], 1.0e-3))
    out["view_sample_count_scale"] = min(scale, SAMPLE_SCALE_MAX)
    return out


def _encoded(v):
    return isinstance(v, dict) and "__t" in v and "v" in v


def lerp_val(a, b, w, key=""):
    """Blend two preset values by type: numbers linearly (a light's intensity in log space), lists and plain dicts per
    element, encoded snapshot values ({"__t": ...}) per element -- against each other when both have the same type, and
    against the plain form of the same shape (a preset's list or dict) keeping the encoded wrapper (final review: the
    snapshot's colours used to switch at the middle); anything else switches at w = 0.5."""
    if isinstance(a, bool) or isinstance(b, bool):
        return b if w >= 0.5 else a
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if key == "intensity" and a > 0.0 and b > 0.0:
            return math.exp(math.log(a) + (math.log(b) - math.log(a)) * w)
        return a + (b - a) * w
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for x, y in zip(a, b):
            v = lerp_val(x, y, w)
            out.append(int(round(v)) if isinstance(x, int) and isinstance(y, int) else v)
        return out
    if _encoded(a) or _encoded(b):
        if _encoded(a) and _encoded(b) and a["__t"] != b["__t"]:
            return b if w >= 0.5 else a
        va = a["v"] if _encoded(a) else a
        vb = b["v"] if _encoded(b) else b
        same_shape = ((isinstance(va, list) and isinstance(vb, list) and len(va) == len(vb))
                      or (isinstance(va, dict) and isinstance(vb, dict)))
        if not same_shape:
            return b if w >= 0.5 else a
        return dict(a if _encoded(a) else b, v=lerp_val(va, vb, w))
    if isinstance(a, dict) and isinstance(b, dict):
        return {k: lerp_val(a.get(k, b.get(k)), b.get(k, a.get(k)), w, k) for k in sorted(set(a) | set(b))}
    return b if w >= 0.5 else a


def dome_state(a, b, intensity):
    """(dome present, star values) during a "full" transition with a night end: the dome exists below DOME_LUX and its
    StarIntensity rises (in log of the light) from 0 there to the night preset's value."""
    night = b if b.get("night_sky") else (a if a.get("night_sky") else None)
    if night is None or intensity is None or intensity >= DOME_LUX:
        return False, None
    i_night = float(night["components"][LIGHT]["intensity"])
    span = math.log(DOME_LUX) - math.log(i_night)
    k = (math.log(DOME_LUX) - math.log(max(float(intensity), 1.0e-9))) / span if span > 0.0 else 1.0
    stars = dict(night["night_sky"])
    stars["StarIntensity"] = night["night_sky"]["StarIntensity"] * ease(k)
    return True, stars


LOCAL_EXPOSURE_CVARS = {"local_exposure_highlight_contrast_scale": "r.DefaultFeature.LocalExposure.HighlightContrastScale",
                        "local_exposure_shadow_contrast_scale": "r.DefaultFeature.LocalExposure.ShadowContrastScale"}


def underlying_ppv(struct_defaults, cvars, volumes):
    """The value each post-process setting has where our volume does not override it, i.e. what a transition must end on
    for a setting only its outgoing preset sets (Task 11 ruling). The view starts from the struct defaults, with the
    local-exposure contrast scales taken from their project-default console variables (SceneView.cpp 2081-2089; 1.0 while
    r.LocalExposure is off, 2180), then applies every other enabled unbound volume in ascending priority, each blended by
    its weight. struct_defaults: {setting: value}; cvars: {name: value}; volumes: [{"priority", "blend_weight",
    "overrides": {setting: value}}]. Only the settings in struct_defaults are returned."""
    out = dict(struct_defaults)
    on = float(cvars.get("r.LocalExposure", 1)) > 0.0
    for key, name in LOCAL_EXPOSURE_CVARS.items():
        if key in out and name in cvars:
            out[key] = min(max(float(cvars[name]), 0.0), 1.0) if on else 1.0
    for vol in sorted(volumes, key=lambda v: v["priority"]):
        wt = min(max(float(vol.get("blend_weight", 1.0)), 0.0), 1.0)
        for key, v in vol["overrides"].items():
            if key in out:
                out[key] = lerp_val(out[key], v, wt, key)
    return out


def look_trans(state, p, ppv_defaults, clouds_light):
    """The look during a transition at eased progress p (spec §4.5). "clouds" keeps the outgoing look."""
    tr = state["trans"]
    a = tr["from_look"]
    if tr["light"] == "clouds":
        return look_static(a, clouds_light)
    b = tr["to"]
    w = sub(p, LIGHT_WINDOW[0], LIGHT_WINDOW[1])
    comps = {}
    for s in sorted(set(a["components"]) | set(b["components"])):
        if s == CLOUD:
            continue
        va, vb = a["components"].get(s, {}), b["components"].get(s, {})
        comps[s] = {k: lerp_val(va.get(k, vb.get(k)), vb.get(k, va.get(k)), w, k) for k in sorted(set(va) | set(vb))}
    if LIGHT in comps:
        comps[LIGHT]["cast_shadows_on_clouds"] = bool(clouds_light)
    sun = [a["sun"][0] + (b["sun"][0] - a["sun"][0]) * w, a["sun"][1] + _arc(a["sun"][1], b["sun"][1]) * w]
    ppv = {}
    for k in sorted(set(a["ppv"]) | set(b["ppv"])):
        va = a["ppv"][k] if k in a["ppv"] else ppv_defaults.get(k, b["ppv"].get(k))
        vb = b["ppv"][k] if k in b["ppv"] else ppv_defaults.get(k, a["ppv"].get(k))
        ppv[k] = lerp_val(va, vb, w, k)
    dome, stars = dome_state(a, b, comps.get(LIGHT, {}).get("intensity"))
    return {"components": comps, "sun": sun, "ppv": ppv, "dome": dome, "stars": stars}


def progress(state, t):
    """Raw progress (0..1) of the running transition at simulated time t (independent of the playback speed)."""
    tr = state["trans"]
    return min(max((t - tr["t_start"]) / tr["dur"], 0.0), 1.0)


def check_target(state, name, names, duration_s, light):
    """Why a transition to `name` cannot start now (a reason string), or None."""
    if state["trans"] is not None:
        return "a transition is running"
    if name not in names:
        return "unknown preset %s" % name
    if name == state["slots"]["A"]["preset"]:
        return "%s is already the current cloud" % name
    if light not in ("full", "clouds"):
        return "light must be \"full\" or \"clouds\""
    if not duration_s >= MIN_TRANSITION_S:
        return "a transition needs at least %.0f simulated seconds" % MIN_TRANSITION_S
    return None


def check_seek(state):
    return "a transition is running" if state["trans"] is not None else None


def start_transition(state, resolved_b, t, duration_s, light="full"):
    why = check_target(state, resolved_b["name"], [resolved_b["name"]], duration_s, light)
    if why:
        raise ValueError(why)
    state["slots"]["B"] = new_slot(resolved_b, t, -float(duration_s))
    state["trans"] = {"to": resolved_b, "from_look": state["look"], "t_start": float(t), "dur": float(duration_s),
                      "light": light}
    return state


def finish_transition(state):
    """The incoming slot becomes slot A (its values are identical, so the frame does not change); a "full" transition
    also hands over the look."""
    tr = state["trans"]
    state["slots"]["A"] = state["slots"]["B"]
    state["slots"]["B"] = None
    if tr["light"] == "full":
        state["look"] = tr["to"]
    state["trans"] = None
    return state


# --- clips (spec §6) -----------------------------------------------------------------------------------------------------
FPS = 30
CLIP_SECONDS = 10.0           # motion clips
TRANS_SECONDS = 16.0          # transition clips: 1 s of the start preset, 14 s of transition, 1 s of the target
TRANS_HOLD_S = 1.0
TRANS_MINUTES = 30.0
STILL_TIMES = [0.0, 1200.0]   # director stills (plan ruling R6)
CLEAR_Z = 60000.0             # cm: a camera that moves sideways does so at least this high (the tallest roof is 438 m)
CRANE_MIN_CM = 30000.0        # cm: shorter sideways moves blend straight


def short_cam(label):
    """Shot-file name of a camera, as cs_weather.py and Tools/cs_weather/regress_shots.py name it."""
    return "hero" if label == "CS_SkyCam" else label.replace("CS_WX_", "").replace("CS_ART_", "").lower()


def camera_pose(c):
    """A camera entry of cs_weather_presets.CAMERAS ("rot" or "target") as loc / rot [pitch, yaw, roll] / fov / aspect /
    res."""
    if "rot" in c:
        rot = [float(c["rot"][0]), float(c["rot"][1]), 0.0]
    else:
        dx, dy, dz = (c["target"][i] - c["loc"][i] for i in range(3))
        rot = [math.degrees(math.atan2(dz, math.hypot(dx, dy))), math.degrees(math.atan2(dy, dx)), 0.0]
    return {"loc": [float(x) for x in c["loc"]], "rot": rot, "fov": float(c["fov"]), "aspect": float(c["aspect"]),
            "res": list(c["res"])}


def camera_at(ca, cb, w):
    """Blend two cameras by w: FOV linearly, pitch and yaw separately (yaw the short way, no roll). The location moves
    straight when the cameras are less than CRANE_MIN_CM apart sideways; otherwise as a crane over the city (Task 11
    ruling, refining spec §6.1): up to max(both heights, CLEAR_Z) over w in [0, 0.3], across at that height over
    [0.3, 0.7], down to the second camera over [0.7, 1] -- a straight line flew through the downtown. One output size per
    clip: aspect and resolution stay the first camera's."""
    a, b = camera_pose(ca), camera_pose(cb)
    la, lb = a["loc"], b["loc"]
    if math.hypot(lb[0] - la[0], lb[1] - la[1]) < CRANE_MIN_CM:
        loc = [la[i] + (lb[i] - la[i]) * w for i in range(3)]
    else:
        top = max(la[2], lb[2], CLEAR_Z)
        m = sub(w, 0.3, 0.7)
        loc = [la[0] + (lb[0] - la[0]) * m, la[1] + (lb[1] - la[1]) * m,
               la[2] + (top - la[2]) * sub(w, 0.0, 0.3) + (lb[2] - top) * sub(w, 0.7, 1.0)]
    return {"loc": loc,
            "rot": [a["rot"][0] + (b["rot"][0] - a["rot"][0]) * w, a["rot"][1] + _arc(a["rot"][1], b["rot"][1]) * w,
                    0.0],
            "fov": a["fov"] + (b["fov"] - a["fov"]) * w, "aspect": a["aspect"], "res": a["res"]}


def clip_list(P):
    """The clips of spec §6.3 from the preset data module P: one motion clip per art preset (its first shot camera, its
    clip_speed) and the transition clips of P.TRANSITION_CLIPS."""
    out = []
    for name in P.ART_ORDER:
        p = P.PRESETS[name]
        speed = _val(p.get("motion", {}).get("clip_speed", MOTION_KEYS["clip_speed"]))
        out.append({"clip": "motion_" + name.replace("art_", ""), "kind": "preset", "preset": name,
                    "seconds": CLIP_SECONDS, "fps": FPS, "speed": float(speed), "cams": [p["shots"][0][0]]})
    for c in P.TRANSITION_CLIPS:
        out.append({"clip": c["clip"], "kind": "transition", "from": c["from"], "to": c["to"], "light": c["light"],
                    "seconds": TRANS_SECONDS, "hold": TRANS_HOLD_S, "minutes": TRANS_MINUTES, "fps": FPS,
                    "cams": list(c["cams"])})
    return out


def stills_list(P, times=None):
    """Director stills per art preset (plan ruling R6): its first shot camera at the given ages, named like weather shots
    (wx_<preset>_<cam>_mid<seconds>) so that regress_shots.py compares them with the finals."""
    times = list(STILL_TIMES if times is None else times)
    out = []
    for name in P.ART_ORDER:
        cam = P.PRESETS[name]["shots"][0][0]
        out.append({"clip": "stills_" + name.replace("art_", ""), "kind": "stills", "preset": name, "times": times,
                    "names": ["wx_%s_%s_mid%d" % (name, short_cam(cam), int(t)) for t in times], "cams": [cam],
                    "fps": 1})
    return out


def clip_frames(clip):
    """Frame timing of a clip: {"n", "dt" (simulated s per frame), "times" (stills), "t_start" / "dur" / "hold_frames" /
    "speed" (transitions)}. A transition clip plays the start preset for `hold` seconds, then the transition, then the
    target for `hold` seconds; its speed follows from the transition's simulated length."""
    if clip["kind"] == "stills":
        return {"n": len(clip["times"]), "dt": None, "times": list(clip["times"]), "t_start": None, "dur": None}
    n = int(round(clip["seconds"] * clip["fps"]))
    if clip["kind"] == "preset":
        return {"n": n, "dt": clip["speed"] / clip["fps"], "times": None, "t_start": None, "dur": None}
    wall = clip["seconds"] - 2.0 * clip["hold"]
    dur = clip["minutes"] * 60.0
    speed = dur / wall
    dt = speed / clip["fps"]
    hold = int(round(clip["hold"] * clip["fps"]))
    return {"n": n, "dt": dt, "times": None, "t_start": hold * dt, "dur": dur, "hold_frames": hold, "speed": speed}
