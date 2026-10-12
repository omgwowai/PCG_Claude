# Plan-view coverage of a TL storey at one corner, for three end-cap schemes.
# Walls butt at the vertex V (the official shape-grammar demo's scheme); each wall
# section is depth t in [-b, p] (p = moulding in front of the facade, b = body).
# A "cap" is the wall's end profile revolved about the vertical axis through V.
#   V1 sign-agnostic : every wall end gets one cap = front AND body revolved 90 deg
#                      forward (past the end). Same mesh at every corner.
#   V2 by sign       : every wall end gets one cap; convex = front revolved 90 deg
#                      forward, concave = body revolved 90 deg forward.
#   V3 one per vertex: only the starting wall gets a cap (the BDF route places one
#                      corner piece per vertex); by sign, revolved 180 deg.
# "gap" = target (offset band with round outer joins) not covered = a crack.
# "spur" = covered but outside the target = material poking out.
# "spur_walls" = the part of spur produced by the straight walls themselves.
import math

def rot(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)

def sector(x, y, r, start, sweep_deg):
    d = math.hypot(x, y)
    if d == 0: return True
    if d > r: return False
    a0 = math.atan2(start[1], start[0])
    a = (math.atan2(y, x) - a0 + math.pi) % (2 * math.pi) - math.pi
    sw = math.radians(sweep_deg)
    return (0 <= a <= sw) if sw >= 0 else (sw <= a <= 0)

def toward(frm, to):
    """signed 90-deg sweep from direction frm toward direction to."""
    a = (math.atan2(to[1], to[0]) - math.atan2(frm[1], frm[0]) + math.pi) % (2 * math.pi) - math.pi
    return 90.0 if a > 0 else -90.0

def run(th_deg, p, b, scheme, h=0.5, R=300.0):
    th = math.radians(th_deg)            # > 0 concave (turn toward A's exterior), < 0 convex
    dA, nA = (1.0, 0.0), (0.0, 1.0)
    dB, nB = rot(dA, th), rot(nA, th)
    neg = lambda v: (-v[0], -v[1])
    concave = th > 0
    ends = [(nA, dA), (nB, neg(dB))]      # (exterior normal, direction past the wall end)
    def cap(x, y):
        use = ends if scheme in ("V1", "V2") else ends[1:]
        for n, past in use:
            fw_front = toward(n, past)
            fw_body = toward(neg(n), past)
            if scheme == "V1":
                if sector(x, y, p, n, fw_front) or sector(x, y, b, neg(n), fw_body): return True
            elif scheme == "V2":
                if concave:
                    if sector(x, y, b, neg(n), fw_body): return True
                elif sector(x, y, p, n, fw_front): return True
            else:
                if concave:
                    if sector(x, y, b, neg(n), 2 * fw_body): return True
                elif sector(x, y, p, n, 2 * fw_front): return True
        return False
    def target(x, y):
        best = None
        for d, n, first in ((dA, nA, True), (dB, nB, False)):
            s = x * d[0] + y * d[1]
            if (first and s <= 0) or (not first and s >= 0):
                t = x * n[0] + y * n[1]; cand = (abs(t), t)
            else:
                r = math.hypot(x, y)
                side = x * (nA[0] + nB[0]) + y * (nA[1] + nB[1])
                cand = (r, r if side > 0 else -r)
            if best is None or cand[0] < best[0]: best = cand
        return -b <= best[1] <= p
    gap = spur = spur_w = 0.0
    N = int(R / h)
    for i in range(-N, N + 1):
        for j in range(-N, N + 1):
            x, y = i * h, j * h
            if x * x + y * y > R * R: continue
            sA, tA = x, y
            sB, tB = x * dB[0] + y * dB[1], x * nB[0] + y * nB[1]
            walls = (sA <= 0 and -b <= tA <= p) or (sB >= 0 and -b <= tB <= p)
            cov = walls or cap(x, y)
            tg = target(x, y)
            if tg and not cov: gap += h * h
            if cov and not tg:
                spur += h * h
                if walls: spur_w += h * h
    return round(gap), round(spur), round(spur_w)

if __name__ == "__main__":
    LEVELS = (("L4", 34, 30), ("L1", 16, 30), ("L2/L3", 8, 30))
    for scheme in ("V1", "V2", "V3"):
        print("=====", scheme)
        for name, p, b in LEVELS:
            row = []
            for th in (-150, -120, -90, -60, -30, 30, 60, 90, 120, 150):
                g, s, sw = run(th, p, b, scheme)
                row.append("%s%3d:g%d/s%d(w%d)" % ("X" if th < 0 else "V", 180 - abs(th) if th < 0 else 180 + th, g, s, sw))
            print(" ", name, " ".join(row))
