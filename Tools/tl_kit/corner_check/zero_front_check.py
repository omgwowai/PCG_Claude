# final_scheme_sign.py model at heights where the facade is plain brick (front
# projection f = 0 or tiny). The acute end pier keeps a minimum body t_min so its
# facade face never disappears. Reports worst crack / visible spur over angles.
import math
from final_scheme import rot, in_sector

def run(interior, f, b, t_min, h=0.25, R=250.0, L_end=150.0):
    th = math.radians(interior - 180.0)
    dA, nA = (1.0, 0.0), (0.0, 1.0)
    dB, nB = rot(dA, th), rot(nA, th)
    convex = th < 0
    b_end = max(min(b, f), t_min) if interior < 90.0 else b
    dep = lambda s_abs: b_end if s_abs <= L_end else b
    aA = math.atan2(nA[1], nA[0])
    gap = vis = 0.0
    worst_vis_depth = 0.0
    N = int(R / h)
    for i in range(-N, N + 1):
        for j in range(-N, N + 1):
            x, y = i * h, j * h
            if x * x + y * y > R * R: continue
            sA, tA = x, y
            sB, tB = x * dB[0] + y * dB[1], x * nB[0] + y * nB[1]
            fan = (in_sector(x, y, f, aA, th) if f > 0 else False) if convex else in_sector(x, y, b, aA + math.pi, th)
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
            if cov and not tg and sd > f:
                vis += h * h; worst_vis_depth = max(worst_vis_depth, sd - f)
    return round(gap, 1), round(vis, 1), round(worst_vis_depth, 2)

if __name__ == "__main__":
    ANG = (15, 20, 30, 45, 60, 89, 90, 120, 170, 190, 240, 270, 330, 345)
    for f, b, t in ((0, 30, 1), (0, 30, 2), (1, 30, 1), (2, 30, 1), (0, 34, 1), (0, 45, 1)):
        res = [(a,) + run(a, f, b, t) for a in ANG]
        print("f=%d b=%d t_min=%d: worst crack %s cm2, worst visible spur %s cm2, deepest spur %s cm"
              % (f, b, t, max(r[1] for r in res), max(r[2] for r in res), max(r[3] for r in res)))
