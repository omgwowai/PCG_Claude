# check_art.py -- offline checks of the art-directed cloud weathers (Content/Python/cs_weather_art.py) before they go to
# the editor: parameter names against the material, the neutral values, cameras, layer heights, and where the sun and
# the placed features (storm cell, front, rain, lens region) fall in each designed shot.
#
#   C:\Python314\python.exe -P -E Tools/cs_weather/check_art.py          -> report on stdout, exit 1 on a problem
import math
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "Content", "Python"))
import cs_weather_presets as P  # noqa: E402

R_EARTH_KM = 6360.0
SECTIONS = {"DirectionalLightComponent", "SkyAtmosphereComponent", "SkyLightComponent", "VolumetricCloudComponent",
            "ExponentialHeightFogComponent"}


def material_scalars():
    """(SCALARS, the other material scalars) of the cloud material, from cs_cloud_code.py (pure Python)."""
    import cs_cloud_code as CC
    return CC.SCALARS, CC.EXTRA_SCALARS + CC.SLOT_EXTRA


def cam_view(c):
    """(heading deg, pitch deg, horizontal half-FOV, vertical half-FOV) of a camera entry."""
    if "rot" in c:
        pitch, yaw = c["rot"][0], c["rot"][1]
    else:
        dx, dy, dz = (c["target"][i] - c["loc"][i] for i in range(3))
        yaw, pitch = math.degrees(math.atan2(dy, dx)), math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    hh = c["fov"] / 2.0
    vh = math.degrees(math.atan(math.tan(math.radians(hh)) / c["aspect"]))
    return yaw % 360.0, pitch, hh, vh


def rel(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def bearing_to(cam, xy_km):
    dx, dy = xy_km[0] - cam["loc"][0] * 1e-5, xy_km[1] - cam["loc"][1] * 1e-5
    return math.degrees(math.atan2(dy, dx)) % 360.0, math.hypot(dx, dy)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    problems = []
    scalars, extra = material_scalars()
    names = {s[0] for s in scalars} | {s[0] for s in extra}
    art_defaults = {}
    seen = False
    for n, v, _g in scalars:
        if seen:
            art_defaults[n] = v
        seen = seen or n == "CellSolid"
    if art_defaults != P.CLOUD_NEUTRAL:
        problems.append("CLOUD_NEUTRAL differs from the material defaults: %s" % sorted(
            k for k in set(art_defaults) | set(P.CLOUD_NEUTRAL) if art_defaults.get(k) != P.CLOUD_NEUTRAL.get(k)))
    for name in P.ART_ORDER:
        p = P.PRESETS[name]
        for k in p["cloud"]["params"]:
            if k not in names:
                problems.append("%s: cloud param %s is not a material parameter" % (name, k))
        for k in p["set"]:
            if k.split(".", 1)[0] not in SECTIONS:
                problems.append("%s: set key %s outside the managed sections" % (name, k))
        for label, _ref in p["shots"]:
            if label not in P.CAMERAS:
                problems.append("%s: shot camera %s missing from CAMERAS" % (name, label))

        def cfg(key, default=None):
            v = p["set"].get("VolumetricCloudComponent." + key)
            return v[0] if v else P.BASE["VolumetricCloudComponent"].get(key, default)

        def cp(key):
            v = p["cloud"]["params"].get(key)
            if v is not None:
                return v[0]
            return P.CLOUD_NEUTRAL.get(key, P.BASE_CLOUD.get(key))

        bottom, layer = cfg("layer_bottom_altitude"), cfg("layer_height")
        base_km = cp("BaseKm")
        ck = layer - base_km
        elev, az = p["sun"][0], p["sun"][1]
        cam = P.CAMERAS[p["shots"][0][0]]
        yaw, pitch, hh, vh = cam_view(cam)
        print("\n== %s  %s" % (name, p["title"]))
        print("  layer %.2f-%.2f km (clouds from %.2f km)  shot %s heading %.0f pitch %.1f fov +-%.1f / +-%.1f"
              % (bottom, bottom + layer, bottom + base_km, p["shots"][0][0], yaw, pitch, hh, vh))
        ds, dp_ = rel(az, yaw), elev - pitch
        where = "in frame" if abs(ds) <= hh and abs(dp_) <= vh else "outside"
        print("  sun elev %.1f az %.0f: %+.0f deg right / %+.1f deg up of centre (%s)" % (elev, az, ds, dp_, where))
        if elev < 0:
            dep = math.radians(-elev)
            print("  earth shadow above the camera: %.2f km (clouds above it are still sunlit there)"
                  % (R_EARTH_KM * (1.0 / math.cos(dep) - 1.0)))
        if cp("CellStrength") > 0:
            b, d = bearing_to(cam, (cp("CellX"), cp("CellY")))
            top = bottom + base_km + cp("CellTopH") * ck
            print("  cell at %.1f km, bearing %.0f (%+.0f deg from centre), top %.1f km (+%.1f overshoot)"
                  % (d, b, rel(b, yaw), top, cp("OvershootKm")))
            if cp("CellTopH") + cp("OvershootKm") / max(ck, 0.01) > 1.0:
                problems.append("%s: overshooting top leaves the layer" % name)
            if cp("LensAmt") <= 0:
                ang = math.degrees(math.atan2(top - cam["loc"][2] * 1e-5, d))
                print("    cell top seen %.1f deg up (frame top %.1f deg)" % (ang, pitch + vh))
            if cp("AnvilShiftKm"):
                sa = math.radians(cp("StretchAngle"))
                ax, ay = cp("CellX") + cp("AnvilShiftKm") * math.cos(sa), cp("CellY") + cp("AnvilShiftKm") * math.sin(sa)
                b2, d2 = bearing_to(cam, (ax, ay))
                print("    anvil centre at %.1f km, radius %.0f km (camera %s it)"
                      % (d2, cp("AnvilRadiusKm"), "under" if d2 < cp("AnvilRadiusKm") else "outside"))
        if cp("FrontAmt") > 0:
            b, d = bearing_to(cam, (cp("FrontX"), cp("FrontY")))
            print("  front at %.1f km, bearing %.0f (%+.0f deg), base %.1f top %.1f km, faces %.0f"
                  % (d, b, rel(b, yaw), cp("FrontBaseKm") + bottom, cp("FrontTopKm") + bottom, cp("FrontAngle")))
            if cp("FrontTopKm") > layer:
                problems.append("%s: front top above the layer" % name)
        if cp("RainDensity") > 0:
            b, d = bearing_to(cam, (cp("RainX"), cp("RainY")))
            print("  rain shaft at %.1f km, bearing %.0f (%+.0f deg), beta %.4f /m"
                  % (d, b, rel(b, yaw), cp("RainDensity") * cp("ExtinctionMax")))
            if base_km <= 0:
                problems.append("%s: rain needs BaseKm > 0" % name)
        if cp("LensAmt") > 0:
            topk = cp("LensBaseKm") + (cp("LensPlates") - 1) * cp("LensSpacingKm") + cp("LensThickKm") + cp("LensJitterKm")
            print("  lens plates %.1f-%.1f km" % (bottom + cp("LensBaseKm"), bottom + topk))
            if topk > layer or cp("LensBaseKm") - cp("LensJitterKm") - cp("LensThickKm") < 0:
                problems.append("%s: lens plates leave the layer" % name)
            if cp("CellStrength") > 0:
                b, d = bearing_to(cam, (cp("CellX"), cp("CellY")))
                print("    lens region at %.1f km (radius %.0f), bearing %.0f (%+.0f deg)"
                      % (d, cp("CellRadiusKm"), b, rel(b, yaw)))
        if base_km >= layer:
            problems.append("%s: BaseKm above the layer" % name)
        ppv = p.get("ppv", {})
        print("  EV100 %.1f" % ppv.get("auto_exposure_min_brightness", [P.BASE["PPV"]["auto_exposure_min_brightness"]])[0])
    print()
    for prob in problems:
        print("PROBLEM:", prob)
    print("%d presets, %d problems" % (len(P.ART_ORDER), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
