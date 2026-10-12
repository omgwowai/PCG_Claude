# Variant of final_scheme.py: the fan is chosen by the corner's sign only.
#   convex  -> "front fan": only the moulding part of the end profile (0..f),
#              revolved from nA to nB
#   concave -> "back fan":  only the body part (0..b), revolved from -nA to -nB
# End piers next to a convex corner with interior < 90 deg use the acute variant
# (body behind the facade cut to the band's front depth f).
import math
from final_scheme import rot, in_sector, BANDS

def run(interior, f, b, h=0.5, R=300.0, L_end=150.0):
    th = math.radians(interior - 180.0)
    dA, nA = (1.0, 0.0), (0.0, 1.0)
    dB, nB = rot(dA, th), rot(nA, th)
    convex = th < 0
    b_end = min(b, f) if interior < 90.0 else b
    dep = lambda s_abs: b_end if s_abs <= L_end else b
    aA = math.atan2(nA[1], nA[0])
    gap = vis = hid = 0.0
    N = int(R / h)
    for i in range(-N, N + 1):
        for j in range(-N, N + 1):
            x, y = i * h, j * h
            if x * x + y * y > R * R: continue
            sA, tA = x, y
            sB, tB = x * dB[0] + y * dB[1], x * nB[0] + y * nB[1]
            fan = in_sector(x, y, f, aA, th) if convex else in_sector(x, y, b, aA + math.pi, th)
            cov = (sA <= 0 and -dep(-sA) <= tA <= f) or (sB >= 0 and -dep(sB) <= tB <= f) or fan
            best = None
            for d, n, first in ((dA, nA, True), (dB, nB, False)):
                s = x * d[0] + y * d[1]
                if (first and s <= 0) or (not first and s >= 0):
                    t = x * n[0] + y * n[1]; cand = (abs(t), t, abs(s))
                else:
                    r = math.hypot(x, y); sd = x * (nA[0] + nB[0]) + y * (nA[1] + nB[1])
                    cand = (r, r if sd > 0 else -r, 0.0)
                if best is None or cand[0] < best[0]: best = cand
            sd, s = best[1], best[2]
            tg = -dep(s) <= sd <= f
            if tg and not cov: gap += h * h
            if cov and not tg:
                if sd > f: vis += h * h
                else: hid += h * h
    return round(gap), round(vis), round(hid)

ANG = (15, 20, 30, 45, 60, 75, 89, 90, 91, 120, 150, 170, 178, 182, 190, 210, 240, 270, 300, 330, 345)
if __name__ == "__main__":
    for name, f, b in BANDS:
        wg = wv = wh = 0; notes = []
        for a in ANG:
            g, v, hd = run(a, f, b)
            wg, wv, wh = max(wg, g), max(wv, v), max(wh, hd)
            if g or v: notes.append((a, g, v))
        print("%-3s front %2d body %2d: crack %d, visible spur %d, hidden excess %d cm2 %s" % (name, f, b, wg, wv, wh, notes))


def run_L0(interior, f, b, h=0.5, R=300.0):
    """L0 foundation: FS2 straight ends, no acute variant. Returns (crack, spur) cm2."""
    th = math.radians(interior - 180.0)
    dA, nA = (1.0, 0.0), (0.0, 1.0)
    dB, nB = rot(dA, th), rot(nA, th)
    aA = math.atan2(nA[1], nA[0])
    gap = vis = 0.0
    N = int(R / h)
    for i in range(-N, N + 1):
        for j in range(-N, N + 1):
            x, y = i * h, j * h
            if x * x + y * y > R * R: continue
            sA, tA = x, y
            sB, tB = x * dB[0] + y * dB[1], x * nB[0] + y * nB[1]
            fan = in_sector(x, y, f, aA, th) if th < 0 else in_sector(x, y, b, aA + math.pi, th)
            cov = (sA <= 0 and -b <= tA <= f) or (sB >= 0 and -b <= tB <= f) or fan
            best = None
            for d, n, first in ((dA, nA, True), (dB, nB, False)):
                s = x * d[0] + y * d[1]
                if (first and s <= 0) or (not first and s >= 0):
                    t = x * n[0] + y * n[1]; cand = (abs(t), t)
                else:
                    r = math.hypot(x, y); sd = x * (nA[0] + nB[0]) + y * (nA[1] + nB[1])
                    cand = (r, r if sd > 0 else -r)
                if best is None or cand[0] < best[0]: best = cand
            if -b <= best[1] <= f and not cov: gap += h * h
            if cov and best[1] > f: vis += h * h
    return round(gap), round(vis)
