# cs_wx_lib.py -- shared helpers of the City Sample weather presets (cs_weather.py, cs_weather_shots.py).
# No side effects at import: the bridge execs each driver's source in its own globals, so shared code lives here.
import json
import math
import os
import time

import unreal

LEVEL = "/CitySamplePCG/Levels/L_CitySamplePCG_Demo"
SAVED = os.path.abspath(unreal.Paths.project_saved_dir())
REPORT_DIR = os.path.join(SAVED, "Reports", "cs_weather2")
SHOT_DIR = os.path.join(SAVED, "Screenshots", "WindowsEditor")
SHOT_STATUS = os.path.join(REPORT_DIR, "shots_status.json")
SHOT_TIMEOUT_S = 120.0


# --- world / actors -------------------------------------------------------------------------------------------------
def world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def actors():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()


def find_label(label):
    for a in actors():
        if a.get_actor_label() == label:
            return a
    return None


def component(cls_name):
    cls = getattr(unreal, cls_name)
    for a in actors():
        comps = a.get_components_by_class(cls)
        if comps:
            return a, comps[0]
    return None, None


def require_level():
    w = world().get_path_name()
    if not w.startswith(LEVEL + "."):
        return {"abort": "current level is %s, not %s" % (w, LEVEL)}
    return None


# --- values ---------------------------------------------------------------------------------------------------------
def enc(v):
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
    if isinstance(v, unreal.TentDistribution):
        return {"__t": "Tent", "v": {"tip_altitude": v.tip_altitude, "tip_value": v.tip_value, "width": v.width}}
    if isinstance(v, unreal.Vector4):
        return {"__t": "Vector4", "v": [v.x, v.y, v.z, v.w]}
    if isinstance(v, unreal.Object):
        return {"__t": "Object", "v": v.get_path_name()}
    if isinstance(v, unreal.EnumBase):
        return {"__t": "Enum", "cls": type(v).__name__, "v": v.name}
    return {"__t": "str", "v": str(v)}


def _struct(cls, d):
    s = cls()
    for k, val in d.items():
        s.set_editor_property(k, float(val))
    return s


def dec(v):
    if isinstance(v, dict) and "__t" in v:
        t, x = v["__t"], v["v"]
        if t == "LinearColor":
            return unreal.LinearColor(*x)
        if t == "Color":
            return unreal.Color(r=int(x[0]), g=int(x[1]), b=int(x[2]), a=int(x[3]))
        if t == "Rotator":
            return unreal.Rotator(roll=x[2], pitch=x[0], yaw=x[1])
        if t == "Fog":
            return _struct(unreal.ExponentialHeightFogData, x)
        if t == "Tent":
            return _struct(unreal.TentDistribution, x)
        if t == "Vector4":
            return unreal.Vector4(*x)
        if t == "Object":
            return unreal.load_object(None, x) if x else None
        if t == "Enum":
            return getattr(getattr(unreal, v["cls"]), x)
    return v


def value_for(obj, prop, val):
    """Turns a preset value (JSON-ish) into what set_editor_property wants, by the type of the current value."""
    cur = obj.get_editor_property(prop)
    if isinstance(val, dict) and "__t" in val:
        return dec(val)
    if isinstance(cur, unreal.LinearColor):
        return unreal.LinearColor(*val)
    if isinstance(cur, unreal.Color):
        return unreal.Color(r=int(val[0]), g=int(val[1]), b=int(val[2]), a=int(val[3]))
    if isinstance(cur, unreal.Vector4):
        return unreal.Vector4(*val)
    if isinstance(cur, unreal.ExponentialHeightFogData):
        return _struct(unreal.ExponentialHeightFogData, val)
    if isinstance(cur, unreal.TentDistribution):
        return _struct(unreal.TentDistribution, val)
    if isinstance(cur, unreal.EnumBase) and isinstance(val, str):
        return getattr(type(cur), val)
    if isinstance(val, str) and val.startswith("/"):
        return unreal.load_asset(val)
    if isinstance(cur, bool):
        return bool(val)
    if isinstance(cur, float):
        return float(val)
    if isinstance(cur, int):
        return int(val)
    return val


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, default=str, ensure_ascii=False)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --- console / editor settings --------------------------------------------------------------------------------------
def cvar_get(name):
    return unreal.SystemLibrary.get_console_variable_float_value(name)


def cvar_set(name, value):
    unreal.SystemLibrary.execute_console_command(world(), "%s %s" % (name, value))


def autosave_cdo():
    return unreal.get_default_object(unreal.load_class(None, "/Script/UnrealEd.EditorLoadingSavingSettings"))


def perf_cdo():
    """Editor Preferences > Performance. Its bThrottleCPUWhenNotForeground (default on) turns every viewport's realtime
    off while the editor window has no focus (EditorEngine.cpp 1807): no frame is drawn, so a HighResShot never fires."""
    return unreal.get_default_object(unreal.load_class(None, "/Script/UnrealEd.EditorPerformanceSettings"))


THROTTLE = "bThrottleCPUWhenNotForeground"   # raw C++ name: the class is not Python-exposed


def process_memory_gb():
    """Working set and private commit of this editor process in GB (Windows, K32GetProcessMemoryInfo), or None.
    The 2026-11-11 crash was the system commit limit (editor private bytes 90 GB), not VRAM."""
    try:
        import ctypes
        from ctypes import wintypes

        class _PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(pmc)
        if not k32.K32GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return None
        g = float(1 << 30)
        return {"ws": round(pmc.WorkingSetSize / g, 2), "commit": round(pmc.PagefileUsage / g, 2),
                "peak_commit": round(pmc.PeakPagefileUsage / g, 2)}
    except Exception:
        return None


def guarded(fn):
    """Wraps a Slate post-tick callback so it cannot run inside itself. Anything that opens a slow-task dialog (an
    asset save, a compile wait) ticks Slate from inside the callback, and Slate's post-tick then calls it again: on
    2026-11-11 the batch applied and saved three presets nested in one frame before the editor ran out of memory."""
    state = {"busy": False}

    def tick(dt):
        if state["busy"]:
            return
        state["busy"] = True
        try:
            fn(dt)
        finally:
            state["busy"] = False
    return tick


# --- sun / cameras --------------------------------------------------------------------------------------------------
def sun_rotation(elev, azim):
    """North is +X and +Y is east, so a compass azimuth is a UE yaw; the light points away from the sun."""
    return unreal.Rotator(roll=0.0, pitch=-elev, yaw=azim - 180.0)


def look_rotation(loc, target):
    dx, dy, dz = (target[0] - loc[0], target[1] - loc[1], target[2] - loc[2])
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    return pitch, yaw


def helper_camera(label, loc, rot, fov, aspect):
    """Spawns or moves a CineCamera: rot = [pitch, yaw, roll], fov = horizontal degrees on a 36 mm wide sensor."""
    cam = find_label(label)
    r = unreal.Rotator(roll=rot[2], pitch=rot[0], yaw=rot[1])
    if cam is None:
        cam = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(
            unreal.CineCameraActor, unreal.Vector(*loc), r)
        cam.set_actor_label(label)
    cam.set_actor_location_and_rotation(unreal.Vector(*loc), r, False, False)
    comp = cam.get_cine_camera_component()
    fb = comp.get_editor_property("filmback")
    fb.set_editor_property("sensor_width", 36.0)
    fb.set_editor_property("sensor_height", 36.0 / float(aspect))
    comp.set_editor_property("filmback", fb)
    comp.set_editor_property("constrain_aspect_ratio", False)
    comp.set_editor_property("current_focal_length", 18.0 / math.tan(math.radians(fov) * 0.5))
    fs = comp.get_editor_property("focus_settings")
    fs.set_editor_property("focus_method", unreal.CameraFocusMethod.DISABLE)
    comp.set_editor_property("focus_settings", fs)
    return cam


# --- shot queue -----------------------------------------------------------------------------------------------------
def shot_status():
    return load_json(SHOT_STATUS, {"state": "none"})


def shot_queue_busy():
    st = shot_status()
    return st.get("state") == "running" and time.time() - st.get("heartbeat", 0) < 30


def start_shot_queue(shots, settle=20):
    """Takes [{"name", "camera", "res"}] one after another from a Slate post-tick callback: UE keeps one pending
    HighResShot only (a second request replaces the first), so each waits until the previous PNG is complete."""
    if shot_queue_busy():
        return {"refused": "a shot queue is still running", "status": shot_status()}
    for s in shots:
        if find_label(s["camera"]) is None:
            return {"error": "no camera labelled %s" % s["camera"]}
    st = {"state": "running", "queue": list(shots), "done": [], "errors": [], "heartbeat": time.time(),
          "settle": int(settle), "phase": "settle", "t0": time.time()}
    save_json(SHOT_STATUS, st)
    handle = {}

    def tick(_dt):
        try:
            if st["phase"] == "settle":
                st["settle"] -= 1
                if st["settle"] <= 0:
                    st["phase"] = "fire"
            elif st["phase"] == "fire":
                if not st["queue"]:
                    st["state"] = "done"
                    unreal.unregister_slate_post_tick_callback(handle["h"])
                else:
                    s = st["queue"][0]
                    path = os.path.join(SHOT_DIR, s["name"] + ".png")
                    if os.path.exists(path):
                        os.remove(path)
                    res = s.get("res", [1920, 1080])
                    unreal.AutomationLibrary.take_high_res_screenshot(int(res[0]), int(res[1]), s["name"],
                                                                      camera=find_label(s["camera"]),
                                                                      force_game_view=True)
                    st["phase"], st["fired_at"], st["path"], st["size"] = "wait", time.time(), path, -1
            elif st["phase"] == "wait":
                path = st["path"]
                if os.path.exists(path):
                    size = os.path.getsize(path)
                    if size > 0 and size == st["size"]:
                        st["done"].append(st["queue"].pop(0)["name"])
                        st["phase"], st["settle"] = "settle", 3
                    st["size"] = size
                elif time.time() - st["fired_at"] > SHOT_TIMEOUT_S:
                    st["errors"].append(st["queue"].pop(0)["name"])
                    st["phase"] = "fire"
            st["heartbeat"] = time.time()
            save_json(SHOT_STATUS, st)
        except Exception as exc:
            st["state"], st["error"] = "error", "%s: %s" % (type(exc).__name__, exc)
            save_json(SHOT_STATUS, st)
            unreal.unregister_slate_post_tick_callback(handle["h"])

    handle["h"] = unreal.register_slate_post_tick_callback(guarded(tick))
    return {"queued": [s["name"] for s in shots], "status_file": SHOT_STATUS}
