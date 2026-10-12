# Mixed corners: wall A's end pier and wall B's end pier may use different body
# depths (thin = front depth f, normal = b). The fan is chosen by sign only and
# always uses the NORMAL profile (convex: front fan radius f; concave: back fan
# radius b). Target = union of what each wall needs: wall A band [-depA, f] on its
# side, wall B band [-depB, f] on its side, round outer joins. Reports crack and
# visible spur (outside the outer offset line f), worst over angles.
import math
from final_scheme import rot, in_sector

def run(interior, f, b, thinA, thinB, h=0.5, R=250.0, L_end=150.0):
    th = math.radians(interior - 180.0)
    dA, nA = (1.0, 0.0), (0.0, 1.0)
    dB, nB = rot(dA, th), rot(nA, th)
    convex = th < 0
    eA = f if thinA else b
    eB = f if thinB else b
    depA = lambda s: eA if s <= L_end else b
    depB = lambda s: eB if s <= L_end else b
    aA = math.atan2(nA[1], nA[0])
    gap = vis = 0.0
    N = int(R / h)
    for i in range(-N, N + 1):
        for j in range(-N, N + 1):
            x, y = i * h, j * h
            if x * x + y * y > R * R: continue
            sA, tA = x, y
            sB, tB = x * dB[0] + y * dB[1], x * nB[0] + y * nB[1]
            fan = in_sector(x, y, f, aA, th) if convex else in_sector(x, y, b, aA + math.pi, th)
            cov = (sA <= 0 and -depA(-sA) <= tA <= f) or (sB >= 0 and -depB(sB) <= tB <= f) or fan
            # outer offset line (visible boundary): signed distance > f is outside
            best = None
            for d, n, first, dep in ((dA, nA, True, depA), (dB, nB, False, depB)):
                s = x * d[0] + y * d[1]
                if (first and s <= 0) or (not first and s >= 0):
                    t = x * n[0] + y * n[1]; cand = (abs(t), t, abs(s), dep)
                else:
                    r = math.hypot(x, y); sd = x * (nA[0] + nB[0]) + y * (nA[1] + nB[1])
                    cand = (r, r if sd > 0 else -r, 0.0, (lambda s: min(eA, eB)))
                if best is None or cand[0] < best[0]: best = cand
            sd, s, dep = best[1], best[2], best[3]
            tg = -dep(s) <= sd <= f
            if tg and not cov: gap += h * h
            if cov and sd > f: vis += h * h
    return round(gap), round(vis)

if __name__ == "__main__":
    ANG = (15, 30, 45, 60, 89, 90, 120, 170, 190, 240, 270, 330, 345)
    for name, f, b in (("L1", 6, 30), ("L1top", 16, 30), ("L2", 8, 30), ("L4", 34, 34), ("L4top", 6, 34)):
        for thinA, thinB in ((True, True), (True, False), (False, True)):
            res = [(a,) + run(a, f, b, thinA, thinB) for a in ANG]
            bad = [r for r in res if r[1] or (r[2] and r[0] >= 15)]
            print("%-6s thinA=%d thinB=%d: worst crack %d, worst visible %d %s" %
                  (name, thinA, thinB, max(r[1] for r in res), max(r[2] for r in res), bad[:4]))
