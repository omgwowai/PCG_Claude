# Exact final scheme, plan view per measured height band:
#  * walls run vertex to vertex; first/last 150 cm of each wall is an end pier
#    with a flat end face (official shape-grammar demo's half-corner layout);
#  * at a convex corner with interior < 90 deg both end piers use the "acute"
#    variant: body behind the facade cut to the band's front depth f;
#  * ONE fan per corner, the same mesh for convex and concave: the end pier's
#    end profile (front f along +n, body along -n) revolved from nA to nB.
# Reports worst crack, worst visible spur (outside the outer offset line) and
# worst hidden excess (inside the building, beyond the body depth) over angles.
import math

def rot(v, a):
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)

def in_sector(x, y, r, a_from, sw):
    d = math.hypot(x, y)
    if d == 0: return True
    if d > r: return False
    a = (math.atan2(y, x) - a_from + math.pi) % (2 * math.pi) - math.pi
    return (0 <= a <= sw) if sw >= 0 else (sw <= a <= 0)

def run(interior, f, b, h=0.5, R=300.0, L_end=150.0):
    th = math.radians(interior - 180.0)          # turn: < 0 convex, > 0 concave
    dA, nA = (1.0, 0.0), (0.0, 1.0)
    dB, nB = rot(dA, th), rot(nA, th)
    acute = interior < 90.0
    b_end = min(b, f) if acute else b
    dep = lambda s_abs: b_end if s_abs <= L_end else b
    aA = math.atan2(nA[1], nA[0])
    sw = th                                        # sweep nA -> nB
    gap = vis = hid = 0.0
    N = int(R / h)
    for i in range(-N, N + 1):
        for j in range(-N, N + 1):
            x, y = i * h, j * h
            if x * x + y * y > R * R: continue
            sA, tA = x, y
            sB, tB = x * dB[0] + y * dB[1], x * nB[0] + y * nB[1]
            cov = ((sA <= 0 and -dep(-sA) <= tA <= f) or (sB >= 0 and -dep(sB) <= tB <= f)
                   or in_sector(x, y, f, aA, sw) or in_sector(x, y, b_end, aA + math.pi, sw))
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

BANDS = (("L0", 4, 45), ("L0", 7, 45), ("L1", 6, 30), ("L1", 10, 30), ("L1", 16, 30),
         ("L2", 8, 30), ("L3", 5, 30), ("L3", 8, 30), ("L4", 18, 34), ("L4", 34, 34), ("L4", 6, 34))
ANG = (15, 20, 30, 45, 60, 75, 89, 90, 91, 120, 150, 170, 178, 182, 190, 210, 240, 270, 300, 330, 345)
if __name__ == "__main__":
  for name, f, b in BANDS:
      wg = wv = wh = 0; notes = []
      for a in ANG:
          g, v, hd = run(a, f, b)
          wg, wv, wh = max(wg, g), max(wv, v), max(wh, hd)
          if g or v: notes.append((a, g, v))
      print("%-3s front %2d body %2d: crack %d, visible spur %d, hidden excess %d cm2 %s" % (name, f, b, wg, wv, wh, notes))
