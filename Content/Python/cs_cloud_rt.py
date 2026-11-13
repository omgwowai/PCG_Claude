# cs_cloud_rt.py -- the cloud director's editor side (docs/superpowers/specs/2026-11-12-cs-cloud-motion-design.md §5-6).
# One Director drives the City Sample demo level's volumetric cloud from a Slate post-tick: the simulated clock, one
# MaterialInstanceDynamic on the cloud component (both material slots), the cloud layer, the light and look of "full"
# transitions and the star dome. The motion itself is cs_cloud_motion (pure Python); cs_cloud_director.py is the bridge
# entry. The running Director lives in a holder module that is never reloaded, so a later bridge call finds it; after
# editing this file, stop and play again (a running instance keeps the code it was created with).
import importlib
import os
import sys
import time
import types

import unreal

import cs_cloud_code as CC
import cs_cloud_motion as M
import cs_weather_presets as P
import cs_wx_lib as lib
import cs_wx_resolve as R

for _mod in (CC, M, P, lib, R):
    importlib.reload(_mod)

OUT_DIR = os.path.join(lib.SAVED, "Reports", "cs_cloud_motion")
STATUS = os.path.join(OUT_DIR, "director.json")
FRAMES = os.path.join(OUT_DIR, "frames")
SNAP_EXTRA = os.path.join(lib.REPORT_DIR, "original_extra.json")
CURRENT = os.path.join(lib.REPORT_DIR, "current.json")
MATERIAL = "/Game/CitySampleSky/M_CS_CumulusCloud"
PPV_LABEL = "CS_ClearSky_PPV"
NIGHT_LABEL = "CS_WX_NightSky"
NIGHT_MI = "/Game/CitySampleSky/MI_CS_NightSky"
CAM = "CS_MOTION_Cam"
LIVE_MODE = 0            # r.VolumetricRenderTarget.Mode while playing live (spec §5.4)
STILL_MODE = 3           # while recording and after a stop (cs_weather_presets.BASE_CVARS)
HEARTBEAT_S = 2.0
SHOT_TIMEOUT_S = 120.0
MAX_SHOT_RETRIES = 10
FIRST_SETTLE = 60       # ticks before the first frame of a (resumed) clip: a preset switch needs the static batch's settle


def holder():
    """A module that survives reloads of this one: it keeps the running Director."""
    h = sys.modules.get("_cs_cloud_holder")
    if h is None:
        h = types.ModuleType("_cs_cloud_holder")
        h.director = None
        sys.modules["_cs_cloud_holder"] = h
    return h


def current():
    return holder().director


def _weather(reload=False):
    """cs_weather.py as a module (its bridge entry is guarded, so importing it runs no phase). Reloaded at phase entry,
    never inside a tick."""
    import cs_weather
    if reload:
        importlib.reload(cs_weather)
    return cs_weather


def _same(a, b):
    try:
        return abs(float(a) - float(b)) <= 1.0e-6 * max(1.0, abs(float(a)), abs(float(b)))
    except (TypeError, ValueError):
        return a == b


def _ppv_value(v):
    if isinstance(v, unreal.Vector4):
        return [v.x, v.y, v.z, v.w]
    if isinstance(v, unreal.LinearColor):
        return [v.r, v.g, v.b, v.a]
    if isinstance(v, unreal.EnumBase):
        return v.name
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    return v


def read_ppv_defaults():
    """The value of every managed post-process setting where our volume does not override it -- what a setting falls back
    to when only one end of a transition sets it (cs_cloud_motion.underlying_ppv): the struct defaults, the project's
    local-exposure defaults (console variables) and the level's other enabled unbound volumes. JSON-ish like the preset
    data."""
    keys = sorted(R.managed_ppv())
    s = unreal.PostProcessSettings()
    struct = {key: _ppv_value(s.get_editor_property(key)) for key in keys}
    cvars = {name: lib.cvar_get(name) for name in list(M.LOCAL_EXPOSURE_CVARS.values()) + ["r.LocalExposure"]}
    volumes = []
    for a in unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors():
        if not isinstance(a, unreal.PostProcessVolume) or a.get_actor_label() == PPV_LABEL:
            continue
        if not (a.get_editor_property("enabled") and a.get_editor_property("unbound")):
            continue
        vs = a.get_editor_property("settings")
        volumes.append({"priority": float(a.get_editor_property("priority")),
                        "blend_weight": float(a.get_editor_property("blend_weight")),
                        "overrides": {key: _ppv_value(vs.get_editor_property(key)) for key in keys
                                      if vs.get_editor_property("override_" + key)}})
    return M.underlying_ppv(struct, cvars, volumes)


class Director:
    def __init__(self, speed):
        self.speed = float(speed)
        self.t = 0.0
        self.paused = False
        self.state = None
        self.snapshot = lib.load_json(SNAP_EXTRA, {"components": {}})
        self.ppv_defaults = read_ppv_defaults()
        self.cache = {}
        self.refs = {}
        self.handle = None
        self.mid = None
        self.dome_mid = None
        self.ticks = []
        self.error = None
        self.last_beat = 0.0
        self.last_frame = None
        self.job = None          # the clip being recorded (Task 10)
        self.queue = []          # clips still to record
        self.max_commit = 64.0

    # --- setup -------------------------------------------------------------------------------------------------------
    def _find_refs(self):
        self.refs = {section: lib.component(section) for section in R.SECTIONS}
        self.refs["ppv"] = lib.find_label(PPV_LABEL)

    def _make_mid(self):
        _actor, cloud = self.refs[M.CLOUD]
        mid = unreal.MaterialLibrary.create_dynamic_material_instance(cloud, unreal.load_asset(MATERIAL))
        cloud.set_editor_property("material", mid)
        return mid

    def _prime(self, r):
        """cs_weather.py apply has just set preset r: record its values as already written, so the first frame writes
        only the MID (a new MID starts at the material's defaults, so its parameters are all written once)."""
        look = M.look_static(r, self.state["slots"]["A"]["clouds_light"])
        for section, vals in look["components"].items():
            for prop, v in vals.items():
                self.cache[(section, prop)] = v
        for prop, v in r["components"].get(M.CLOUD, {}).items():
            self.cache[(M.CLOUD, prop)] = v
        self.cache["sun"] = [round(look["sun"][0], 6), round(look["sun"][1], 6)]
        self.cache["ppv"] = dict(look["ppv"])
        self.cache["dome"] = False       # the dome's MID is made by the first frame that needs the dome

    def start(self, preset, t):
        self._find_refs()
        self.t = float(t)
        r = R.resolve(preset, self.snapshot)
        self.state = M.new_state(r, self.t)
        self.cache = {}
        self._prime(r)
        self.mid = self._make_mid()
        lib.cvar_set("r.VolumetricRenderTarget.Mode", LIVE_MODE)
        self.apply_frame()
        self.handle = unreal.register_slate_post_tick_callback(lib.guarded(self.tick))
        self.save_status()

    # --- writes: only values that changed since the last frame --------------------------------------------------------
    def write_mid(self, values):
        for name, v in values.items():
            key = ("mid", name)
            if key in self.cache and _same(self.cache[key], v):
                continue
            self.mid.set_scalar_parameter_value(name, float(v))
            self.cache[key] = v

    def write_prop(self, section, prop, value):
        """One component property: the Blueprint setter when the component has one and is not Static (verified by
        reading back, plan ruling R5), else set_editor_property."""
        key = (section, prop)
        if key in self.cache and self.cache[key] == value:
            return
        _actor, comp = self.refs.get(section, (None, None))
        if comp is None:
            return
        new = lib.value_for(comp, prop, value)
        done = False
        setter = getattr(comp, "set_" + prop, None)
        if setter is not None and comp.get_editor_property("mobility") != unreal.ComponentMobility.STATIC:
            try:
                setter(new)
                done = _same(comp.get_editor_property(prop), new) if isinstance(new, float) else True
            except Exception:
                done = False
        if not done:
            comp.set_editor_property(prop, new)
        self.cache[key] = value

    def write_vc(self, vc):
        for prop, v in vc.items():
            self.write_prop(M.CLOUD, prop, v)

    def write_ppv(self, values):
        if self.cache.get("ppv") == values:
            return
        ppv = self.refs.get("ppv")
        if ppv is None:
            # the static apply spawns CS_ClearSky_PPV; without it exposure and grading would silently stay unchanged
            raise RuntimeError("%s missing: the look's post-process values cannot be written" % PPV_LABEL)
        s = ppv.get_editor_property("settings")
        for prop in R.managed_ppv():
            s.set_editor_property("override_" + prop, prop in values)
        for prop, val in values.items():
            if prop == "auto_exposure_method":
                val = getattr(unreal.AutoExposureMethod, val)
            elif isinstance(val, list):
                val = unreal.Vector4(*val) if len(val) == 4 else unreal.LinearColor(*val)
            s.set_editor_property(prop, val)
        ppv.set_editor_property("settings", s)
        self.cache["ppv"] = dict(values)

    def write_dome(self, present, stars):
        """The night weathers' star dome (cs_weather._night_sky spawns / removes it). While it exists, its material is
        a MID so that StarIntensity can change every frame."""
        if not present:
            if self.cache.get("dome"):
                _weather()._night_sky(None)
                self.dome_mid = None
            self.cache["dome"] = False
            return
        if not self.cache.get("dome"):
            _weather()._night_sky(stars, write_mi=False)
            smc = lib.find_label(NIGHT_LABEL).static_mesh_component
            self.dome_mid = unreal.MaterialLibrary.create_dynamic_material_instance(smc, unreal.load_asset(NIGHT_MI))
            smc.set_material(0, self.dome_mid)
            self.cache["dome"] = True
            for k in [k for k in self.cache if isinstance(k, tuple) and k[0] == "dome"]:
                del self.cache[k]
        for k, v in stars.items():
            key = ("dome", k)
            if key in self.cache and _same(self.cache[key], v):
                continue
            self.dome_mid.set_scalar_parameter_value(k, float(v))
            self.cache[key] = v

    def write_look(self, look):
        for section, vals in look["components"].items():
            for prop, v in vals.items():
                self.write_prop(section, prop, v)
        sun = [round(float(look["sun"][0]), 6), round(float(look["sun"][1]), 6)]
        if self.cache.get("sun") != sun:
            actor, _comp = self.refs[M.LIGHT]
            actor.set_actor_rotation(lib.sun_rotation(sun[0], sun[1]), False)
            self.cache["sun"] = sun
        self.write_ppv(look["ppv"])
        self.write_dome(look["dome"], look["stars"])

    # --- frame / tick ------------------------------------------------------------------------------------------------
    def apply_frame(self):
        st = self.state
        if st["trans"] is not None and M.progress(st, self.t) >= 1.0:
            M.finish_transition(st)
        fr = M.frame(st, self.t, self.ppv_defaults)
        self.write_mid(fr["mid"])
        self.write_vc(fr["vc"])
        self.write_look(fr["look"])
        self.last_frame = {"t": round(fr["t"], 3), "p": fr["p"], "f": fr.get("f"), "g": fr.get("g")}

    def tick(self, dt):
        t0 = time.perf_counter()
        try:
            if self.job is not None:
                self.record_tick()
            else:
                if not self.paused:
                    self.t += float(dt) * self.speed
                self.apply_frame()
        except Exception as exc:
            self.error = "%s: %s" % (type(exc).__name__, exc)
            self.stop_tick()
            self.save_status("error")
            return
        self.ticks.append((time.perf_counter() - t0) * 1000.0)
        del self.ticks[:-100]
        if time.time() - self.last_beat > HEARTBEAT_S:
            self.save_status()

    def stop_tick(self):
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None

    def stop(self, static=False, reason="stop"):
        self.stop_tick()
        lib.cvar_set("r.VolumetricRenderTarget.Mode", STILL_MODE)
        out = {"stopped": reason, "t": round(self.t, 2)}
        if static and self.state is not None:
            tr = self.state["trans"]
            out["apply"] = _weather().phase_apply({"preset": tr["to"]["name"] if tr else self.state["slots"]["A"]["preset"],
                                                   "by_director": True})
        self.save_status("stopped")
        if holder().director is self:
            holder().director = None
        return out

    def summary(self):
        st = self.state
        slots = {}
        if st is not None:
            for k in ("A", "B"):
                s = st["slots"][k]
                if s is not None:
                    adv = M.adv_km(s, self.t)
                    slots[k] = {"preset": s["preset"], "tau": round(self.t - s["tau0"], 1), "adv_km": round(adv, 1),
                                "adv_budget_km": round(M.ADV_BUDGET_KM - adv, 1)}
        tr = st["trans"] if st is not None else None
        ms = sorted(self.ticks)
        job = None if self.job is None else {k: self.job[k] for k in ("clip", "k", "n", "phase", "errors")}
        return {"t": round(self.t, 2), "speed": self.speed, "paused": self.paused, "slots": slots,
                "look": st["look"]["name"] if st is not None else None,
                "trans": None if tr is None else {"to": tr["to"]["name"], "light": tr["light"], "dur": tr["dur"],
                                                   "p": round(M.progress(st, self.t), 4)},
                "frame": self.last_frame,
                "tick_ms": {"n": len(ms), "mean": round(sum(ms) / len(ms), 3) if ms else None,
                            "p95": round(ms[int(0.95 * (len(ms) - 1))], 3) if ms else None,
                            "max": round(ms[-1], 3) if ms else None},
                "dome": bool(self.cache.get("dome")), "error": self.error, "job": job,
                "queue": [c["clip"] for c in self.queue], "heartbeat": time.time()}

    def save_status(self, state="running"):
        s = self.summary()
        s["state"] = state
        lib.save_json(STATUS, s)
        self.last_beat = time.time()


    # --- recording (spec §6.1): set the frame with the clock frozen, let HighResShot render it, wait for the file ----
    def next_clip(self):
        """Sets up the next queued clip: apply its (first) preset statically, a fresh state and cache, the frames
        folder. Runs inside the tick: the apply saves nothing (save_mi False, trap 132)."""
        if not self.queue:
            self.job = None
            self.stop(reason="recorded")
            return
        clip = self.queue.pop(0)
        first = clip["from"] if clip["kind"] == "transition" else clip["preset"]
        applied = _weather().phase_apply({"preset": first, "save_mi": False, "by_director": True})
        if "abort" in applied or "refused" in applied:
            raise RuntimeError("apply %s: %s" % (first, applied))
        self._find_refs()              # the apply may have spawned CS_ClearSky_PPV (fresh level, after restore)
        self.snapshot = lib.load_json(SNAP_EXTRA, {"components": {}})
        r = R.resolve(first, self.snapshot)
        self.t = 0.0
        self.state = M.new_state(r, 0.0)
        self.cache = {}
        self._prime(r)
        if self.mid is None:
            self.mid = self._make_mid()
        else:
            self.refs[M.CLOUD][1].set_editor_property("material", self.mid)
        lib.cvar_set("r.VolumetricRenderTarget.Mode", STILL_MODE)
        folder = os.path.join(FRAMES, clip["clip"])
        if clip["kind"] != "stills":
            os.makedirs(folder, exist_ok=True)
        plan = M.clip_frames(clip)
        self.job = {"clip": clip["clip"], "def": clip, "plan": plan, "n": plan["n"], "k": 0, "phase": "set",
                    "wait": 0, "folder": folder, "cams": [P.CAMERAS[c] for c in clip["cams"]], "errors": [],
                    "fired": 0.0, "size": -1, "path": None, "started": False, "cam": None, "pose": None,
                    "fresh": True}

    def _frame_path(self, k):
        job = self.job
        if job["def"]["kind"] == "stills":
            return os.path.join(lib.SHOT_DIR, job["def"]["names"][k] + ".png")
        return os.path.join(job["folder"], "f_%05d.png" % k)

    def _camera(self, k):
        job = self.job
        plan = job["plan"]
        if len(job["cams"]) == 1 or plan["t_start"] is None:
            pose = M.camera_pose(job["cams"][0])
        else:
            w = M.ease(min(max((k * plan["dt"] - plan["t_start"]) / plan["dur"], 0.0), 1.0))
            pose = M.camera_at(job["cams"][0], job["cams"][1], w)
        job["cam"] = lib.helper_camera(CAM, pose["loc"], pose["rot"], pose["fov"], pose["aspect"])
        job["pose"] = pose

    def record_tick(self):
        job = self.job
        plan = job["plan"]
        stills = job["def"]["kind"] == "stills"
        if job["phase"] == "set":
            k = job["k"]
            if k >= job["n"]:
                self.next_clip()
                return
            if not stills and os.path.exists(self._frame_path(k)):
                job["k"] += 1                       # resumed clip: keep the frames already taken
                return
            self.t = plan["times"][k] if stills else k * plan["dt"]
            if plan["t_start"] is not None and not job["started"] and self.t >= plan["t_start"] - 1.0e-9:
                c = job["def"]
                M.start_transition(self.state, R.resolve(c["to"], self.snapshot), plan["t_start"], plan["dur"],
                                   c["light"])
                job["started"] = True
            self.apply_frame()
            self._camera(k)
            job["phase"], job["wait"] = "settle", FIRST_SETTLE if job["fresh"] else 2
            job["fresh"] = False
        elif job["phase"] == "settle":
            job["wait"] -= 1
            if job["wait"] <= 0:
                name = job["def"]["names"][job["k"]] if stills else "cm_%s_f%05d" % (job["clip"], job["k"])
                path = os.path.join(lib.SHOT_DIR, name + ".png")
                if os.path.exists(path):
                    os.remove(path)
                res = job["pose"]["res"]
                unreal.AutomationLibrary.take_high_res_screenshot(int(res[0]), int(res[1]), name, camera=job["cam"],
                                                                  force_game_view=True)
                job.update(phase="wait", fired=time.time(), path=path, size=-1)
        elif job["phase"] == "wait":
            path = job["path"]
            if os.path.exists(path):
                size = os.path.getsize(path)
                if size > 0 and size == job["size"]:
                    if not stills:
                        os.replace(path, self._frame_path(job["k"]))
                    job["k"] += 1
                    job["phase"] = "set"
                    if job["k"] % 30 == 0:
                        mem = lib.process_memory_gb()
                        if mem and mem["commit"] > self.max_commit:
                            raise RuntimeError("editor private commit %.1f GB > %.1f GB" % (mem["commit"],
                                                                                          self.max_commit))
                job["size"] = size
            elif time.time() - job["fired"] > SHOT_TIMEOUT_S:
                job["errors"].append(job["k"])
                if len(job["errors"]) > MAX_SHOT_RETRIES:
                    raise RuntimeError("%s: %d shots timed out" % (job["clip"], len(job["errors"])))
                job["phase"] = "set"


# --- phases (cs_cloud_director.py) -------------------------------------------------------------------------------------
def _preflight():
    refused = lib.require_level()
    if refused:
        return refused
    if lib.shot_queue_busy():
        return {"refused": "a shot queue is running"}
    b = lib.load_json(os.path.join(lib.REPORT_DIR, "batch_status.json"), {})
    if b.get("state") == "running" and time.time() - b.get("heartbeat", 0) < 60:
        return {"refused": "a cs_weather.py batch is running"}
    return None


def _need():
    d = current()
    if d is None:
        return None, {"refused": "the director is not running; call play first"}
    if d.handle is None:
        return None, {"refused": "the director's tick has stopped: %s" % d.error}
    return d, None


def stop_current(reason):
    d = current()
    return d.stop(reason=reason) if d is not None else None


def phase_play(args):
    """{"preset": name (default: the preset cs_weather.py applied last), "speed": 30, "t": 0}"""
    refused = _preflight()
    if refused:
        return refused
    stop_current("replaced by play")
    W = _weather(reload=True)
    name = args.get("preset") or lib.load_json(CURRENT, {}).get("preset") or "base"
    if name == "original":
        name = "base"
    if name not in R.names():
        return {"abort": "unknown preset %s" % name}
    if not float(args.get("speed", M.SPEED)) > 0.0:
        return {"abort": "speed must be > 0"}
    applied = W.phase_apply({"preset": name})
    if "abort" in applied or "refused" in applied:
        return applied
    d = Director(args.get("speed", M.SPEED))
    d.start(name, float(args.get("t", 0.0)))
    holder().director = d
    return {"play": name, "speed": d.speed, "t": d.t, "status": STATUS}


def phase_pause(args):
    d, err = _need()
    if err:
        return err
    d.paused = True
    d.save_status()
    return {"paused": True, "t": round(d.t, 2)}


def phase_resume(args):
    d, err = _need()
    if err:
        return err
    d.paused = False
    d.save_status()
    return {"paused": False, "t": round(d.t, 2)}


def phase_speed(args):
    d, err = _need()
    if err:
        return err
    speed = float(args.get("speed", M.SPEED))
    if not speed > 0.0:
        return {"refused": "speed must be > 0"}
    d.speed = speed
    return {"speed": d.speed}


def phase_seek(args):
    d, err = _need()
    if err:
        return err
    why = M.check_seek(d.state)
    if why:
        return {"refused": why}
    d.t = float(args["t"])
    return {"t": d.t}


def phase_to(args):
    """{"preset": name, "minutes": 30 (simulated) | "seconds": 60 (wall), "light": "full" | "clouds"} (spec §4.1)"""
    d, err = _need()
    if err:
        return err
    if d.job is not None:
        return {"refused": "recording"}
    name = args.get("preset")
    dur = float(args["seconds"]) * d.speed if "seconds" in args else float(args.get("minutes", 30.0)) * 60.0
    light = args.get("light", "full")
    why = M.check_target(d.state, name, R.names(), dur, light)
    if why:
        return {"refused": why}
    M.start_transition(d.state, R.resolve(name, d.snapshot), d.t, dur, light)
    d.save_status()
    return {"to": name, "light": light, "sim_s": dur, "wall_s": round(dur / d.speed, 1)}


def phase_state(args):
    d = current()
    if d is None:
        return {"running": False, "last": lib.load_json(STATUS, None)}
    s = d.summary()
    s["running"] = d.handle is not None
    return s


def phase_stop(args):
    d = current()
    if d is None:
        return {"stopped": None}
    return d.stop(static=bool(args.get("static", False)), reason="stop")


def phase_record(args):
    """{"clips": [names] | "all" | "stills", "seconds": s (motion clips only: a quick test), "max_commit_gb": 64}
    Records the clips one after another from the tick. Frames already on disk are kept, so a stopped run resumes."""
    refused = _preflight()
    if refused:
        return refused
    known = {c["clip"]: c for c in M.clip_list(P) + M.stills_list(P)}
    sel = args.get("clips")
    if sel == "all":
        names = [c["clip"] for c in M.clip_list(P)]
    elif sel == "stills":
        names = [c["clip"] for c in M.stills_list(P)]
    else:
        names = list(sel or [])
    unknown = [n for n in names if n not in known]
    if unknown or not names:
        return {"abort": ("unknown clips %s" % unknown) if unknown else "no clips given"}
    queue = []
    for n in names:
        c = dict(known[n])
        if "seconds" in args and c["kind"] == "preset":
            c["seconds"] = float(args["seconds"])
        queue.append(c)
    stop_current("replaced by record")
    _weather(reload=True)
    d = Director(M.SPEED)
    d._find_refs()
    d.queue = queue
    d.max_commit = float(args.get("max_commit_gb", 64.0))
    holder().director = d
    d.next_clip()
    d.handle = unreal.register_slate_post_tick_callback(lib.guarded(d.tick))
    d.save_status()
    return {"record": names, "status": STATUS}
