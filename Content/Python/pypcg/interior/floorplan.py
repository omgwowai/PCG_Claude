"""PyInterior floor planning around a fixed stair room (spec 2026-10-29 §7).

A multi-storey floor is planned like a single-floor house, but its stair room is already placed. The floor's wings minus
the stair become rectangular blocks; the single-floor zoning (layout's public / private templates) fills them; the stair
joins the floor's connection tree only through the room at its opening. Pure."""
import itertools
from types import SimpleNamespace

from pypcg.interior import doors as D
from pypcg.interior import layout as L
from pypcg.interior import program as P
from pypcg.interior.footprint import EPS, Rect

MIN_PIECE = 250.0            # a block narrower than a wing may be is no use to any room
ENTER = 120.0                # the shared edge a block is entered through (as layout.configs)
SPARE = 3e4                  # a private block this much (cm2) larger than its rooms' share may take a storage room too


def _clip(r, w):
    x0, y0, x1, y1 = max(r.x0, w.x0), max(r.y0, w.y0), min(r.x1, w.x1), min(r.y1, w.y1)
    return Rect(x0, y0, x1, y1) if x1 - x0 > EPS and y1 - y0 > EPS else None


# side cells of the 3 x 3 grid a stair cuts a wing into, as (i0, j0, i1, j1) ranges of grid lines, and the corners that may
# join each: a corner joins one of its two neighbouring sides, which grows to take it
_SIDES = {"B": (1, 0, 2, 1), "T": (1, 2, 2, 3), "L": (0, 1, 1, 2), "R": (2, 1, 3, 2)}
_CORNERS = {(0, 0): ("B", "L"), (2, 0): ("B", "R"), (0, 2): ("T", "L"), (2, 2): ("T", "R")}


def _around(w, s):
    """Every way to cut wing `w` around the stair part `s` into rectangles (lists of Rect)."""
    xs, ys = (w.x0, s.x0, s.x1, w.x1), (w.y0, s.y0, s.y1, w.y1)

    def size(i0, j0, i1, j1):
        return xs[i1] - xs[i0] > EPS and ys[j1] - ys[j0] > EPS
    corners = [c for c in _CORNERS if size(c[0], c[1], c[0] + 1, c[1] + 1)]
    out = []
    for choice in itertools.product(*[_CORNERS[c] for c in corners]):
        ranges = {k: list(v) for k, v in _SIDES.items()}
        for (ci, cj), side in zip(corners, choice):
            r = ranges[side]
            r[0], r[1], r[2], r[3] = min(r[0], ci), min(r[1], cj), max(r[2], ci + 1), max(r[3], cj + 1)
        out.append([Rect(xs[i0], ys[j0], xs[i1], ys[j1]) for i0, j0, i1, j1 in ranges.values() if size(i0, j0, i1, j1)])
    return out


def pieces_options(fp, stair_rect, min_piece=MIN_PIECE):
    """Ways to cut the floor's wings minus the stair room into blocks, fewest pieces and widest first; a way with a block
    narrower than `min_piece` is left out (rulings P1: the 3 x 3 grid holds the cut-across, cut-along and largest-first
    cuts of the spec)."""
    per_wing = []
    for w in fp.wings:
        s = _clip(stair_rect, w)
        per_wing.append(_around(w, s) if s else [[w]])
    out, seen = [], set()
    for combo in itertools.product(*per_wing):
        pieces = [r for part in combo for r in part]
        if any(r.short < min_piece - EPS for r in pieces):
            continue
        key = tuple(sorted((round(r.x0, 3), round(r.y0, 3), round(r.x1, 3), round(r.y1, 3)) for r in pieces))
        if key in seen:
            continue
        seen.add(key)
        out.append(pieces)
    out.sort(key=lambda ps: (len(ps), -min(r.short for r in ps)))
    return out


# ---------------------------------------------------------------- configs

def _enter(entered, todo):
    """[(block, side, span)]: every block of `todo` entered over the longest edge it shares with a block already entered,
    breadth first (as layout.configs); None when one cannot be entered."""
    entered, placed, todo = list(entered), [], list(todo)
    progress = True
    while todo and progress:
        progress = False
        for b in list(todo):
            best = None
            for n in entered:
                s = b.shared(n)
                if s and s[3] - s[2] >= ENTER - EPS and (best is None or s[3] - s[2] > best[3] - best[2]):
                    best = s
            if best is not None:
                S = L.Side(b, L.side_of(b, best))
                placed.append((b, S.side, (S.v_of(best[2]), S.v_of(best[3]))))
                entered.append(b)
                todo.remove(b)
                progress = True
    return None if todo else placed


def _ground_configs(fp, pieces, prog):
    """[(public parts [(block, slots)], private blocks [(block, side, span)])] for one way to cut a ground floor: the entry
    block (the longest front wall) holds every public room, or the living room alone with the kitchen (and dining room) in a
    block next to it; the other blocks are private."""
    entry = max(pieces, key=lambda r: (L._front_len(fp, r), r.area, -r.x0, -r.y0))
    if L._front_len(fp, entry) < L.FRONT_MIN - EPS:
        return []
    living = tuple(s for s in prog.public if s.type in P.ENTRY)
    rest = tuple(s for s in prog.public if s.type not in P.ENTRY)
    ways = [[(entry, prog.public)]]
    if rest:
        for n in pieces:
            s = n.shared(entry) if n is not entry else None
            if s and s[3] - s[2] >= ENTER - EPS:
                ways.append([(entry, living), (n, rest)])
    out = []
    for parts in ways:
        used = [b for b, _slots in parts]
        privs = _enter(used, [b for b in pieces if all(b is not u for u in used)])
        if privs is None or (prog.private and not privs):
            continue
        out.append((parts, privs))
    return out


def _upper_configs(pieces, gate):
    """[(fixed parts, private blocks)] for the ways to enter an upper floor from the stair: the block the stair opens into
    planned with the private templates, entered over the opening; or a landing -- a corridor along that block's whole
    stair side -- with the rest of the block entered from it (a hall can run on into a deep block); or the whole block
    as the landing, when it is too shallow for rooms behind one. The other blocks are entered from those already
    entered."""
    acc = next((b for b in pieces if gate.at(b)), None)
    if acc is None:
        return []
    S = L.Side(acc, L.side_of(acc, (gate.axis, gate.c)))
    others = [b for b in pieces if b is not acc]
    hall = (P.Slot("Corridor", 1.0),)
    out = []
    rest = _enter([acc], others)
    deep = S.U - L.CORRIDOR >= MIN_PIECE - EPS
    if rest is not None:
        out.append(([], [(acc, S.side, tuple(sorted((S.v_of(gate.s0), S.v_of(gate.s1)))))] + rest))
        if others and not deep:
            out.append(([(acc, hall)], rest))
    if deep:
        landing, inner = S.rect(0.0, 0.0, L.CORRIDOR, S.V), S.rect(L.CORRIDOR, 0.0, S.U, S.V)
        rest = _enter([landing, inner], others)
        if rest is not None:
            out.append(([(landing, hall)], [(inner, S.side, (0.0, S.V))] + rest))
    return out


# ---------------------------------------------------------------- candidates

class _Gate:
    """The stair's opening on this floor (axis, c, s0, s1 on its partition line, outward) and the room types that may be
    on its far side: a block that holds the opening keeps only layouts with one such room covering all of it. The ground
    floor reaches the stair from the living room, a corridor or the dining room; an upper floor is entered from it into a
    corridor, the landing -- or, in the smallest program, straight into the bedroom (a loft)."""

    def __init__(self, stair, role, prog):
        self.axis, self.c, self.s0, self.s1 = stair.access(role)
        self.out = stair.access_outward(role)
        if role == "ground":
            self.types = P.ACCESS["Stair"]
        else:
            self.types = ("Corridor", "Bedroom", "Master") if prog.name == P.UPPER[0].name else ("Corridor",)

    def at(self, rect):
        """rect lies beyond the opening, with a side on its line that runs over all of it."""
        if self.axis == "y":
            on, lo, hi = (rect.y0 if self.out > 0 else rect.y1), rect.x0, rect.x1
        else:
            on, lo, hi = (rect.x0 if self.out > 0 else rect.x1), rect.y0, rect.y1
        return abs(on - self.c) < EPS and lo <= self.s0 + EPS and hi >= self.s1 - EPS

    def ok(self, block, cand):
        if not self.at(block):
            return True
        return any(self.at(r) and t in self.types for t, r in cand)


class _Memo:
    """A floor's caches while it is planned (its footprint and walls are fixed): a room's size check and the shape part
    of its score depend only on its type and rectangle, and a private block's best layouts recur in many configs.
    Results are exactly layout._sizes_ok's and layout._score's (the same terms, added in the same order). `shared`, the
    memo of another stair place on the same floor, lends its room checks and shape terms (they hold for every place;
    the block layouts depend on the stair's opening too)."""

    def __init__(self, fp, walls, shared=None):
        self.fp, self.walls, self.blocks = fp, walls, {}
        if shared is not None and shared.fp is fp and shared.walls == walls:
            self.sizes, self.shapes = shared.sizes, shared.shapes
        else:
            self.sizes, self.shapes = {}, {}

    def ok(self, cand):
        for t, r in cand:
            v = self.sizes.get((t, r))
            if v is None:
                v = self.sizes[(t, r)] = L._sizes_ok([(t, r)], self.fp, self.walls)
            if not v:
                return False
        return True

    def _shape(self, t, r):
        """(term, filler): a room's aspect term of layout._score (a corridor's or filler's area term)."""
        v = self.shapes.get((t, r))
        if v is None:
            c = L.clear_rect(r, self.fp, self.walls)
            aspect = c.long / max(c.short, 1.0)
            if t in ("Corridor", "Storage"):
                v = (2.0 * r.area / self.fp.area, True)
            else:
                v = (4.0 * max(0.0, aspect - L.MAX_ASPECT[t]) ** 2 + 0.05 * (aspect - 1.0), False)
            self.shapes[(t, r)] = v
        return v

    def score(self, cand, tgts):
        s = 0.0
        for (t, r), tgt in zip(cand, tgts):
            term, filler = self._shape(t, r)
            if not filler and tgt:
                s += ((r.area - tgt) / tgt) ** 2
            s += term
        return s


def _public(parts, fp, walls, gate, unit, front, memo):
    """Per fixed part (the ground floor's public zone, an upper floor's landing) its best layouts [(score, [(type,
    rect)])], on the ground floor (`front`) the first part's first room taking the front door; None when a part has
    none. `unit`: the target area per unit of room weight, floor-wide."""
    out = []
    for k, (b, slots) in enumerate(parts):
        tg = [unit * s.weight for s in slots]
        cands = []
        for cand in L.public_layouts(b, slots):
            if not memo.ok(cand) or not gate.ok(b, cand):
                continue
            if front and k == 0 and L._part_len(L.front_part(cand[0][1], fp)) < L.FRONT_MIN - EPS:
                continue
            cands.append((memo.score(cand, tg), cand))
        if not cands:
            return None
        cands.sort(key=lambda c: c[0])
        out.append(cands[:L.TOP_K])
    return out


def _by_type(cand, grp, tg):
    """The target areas of a private layout's rooms in its order (types may repeat; corridors and fillers have none)."""
    left = list(zip([s.type for s in grp], tg))
    out = []
    for t, _r in cand:
        hit = next((k for k, (tt, _a) in enumerate(left) if tt == t), None)
        out.append(0.0 if hit is None else left.pop(hit)[1])
    return out


def _private(privs, groups, fp, walls, gate, unit, role, memo):
    """Per private block its best layouts, each reachable from its entry span; None when a block has none. A block no
    room is given is one room: a corridor where the stair opens into it or another block is entered through it, a
    storage room else (spec §7); a block much larger than its rooms' share of the floor may also take a storage room
    for the rest (the blocks are fixed by the stair: a WC alone in a 4 x 3 m block is no WC). The entry span leads from
    the public zone on the ground floor; upstairs from the stair into the block it opens into, from a corridor into the
    others."""
    strips = [(b, L._entry_strip(b, side, span)) for b, side, span in privs]
    out = []
    for (b, side, span), grp in zip(privs, groups):
        etype = "Living" if role == "ground" else ("Stair" if gate.at(b) else "Corridor")
        empty = all(s.type == "Storage" for s in grp)
        through = empty and (gate.at(b) or any(o is not b and st.overlaps(b) for o, st in strips))
        key = (b, side, span, tuple((s.type, s.weight) for s in grp), etype, through, gate.types, unit)
        best = memo.blocks.get(key)
        if best is None:
            best = memo.blocks[key] = _block_layouts(b, side, span, grp, fp, gate, unit, etype, empty, through, memo)
        if not best:
            return None
        out.append(best)
    return out


def _block_layouts(b, side, span, grp, fp, gate, unit, etype, empty, through, memo):
    """A private block's TOP_K best layouts [(score, [(type, rect)])] ([] when none is valid)."""
    strip = L._entry_strip(b, side, span)
    if empty:
        options = [([], [[("Corridor" if through else "Storage", b)]])]
    else:
        options = [(list(grp), L.private_layouts(b, grp, side, span))]
        spare = b.area - unit * sum(s.weight for s in grp)
        if spare >= SPARE - EPS:
            more = list(grp) + [P.Slot("Storage", spare / unit)]
            options.append((more, L.private_layouts(b, more, side, span)))
    cands = []
    for slots, layouts in options:
        tg = [unit * s.weight for s in slots]
        for cand in layouts:
            if memo.ok(cand) and gate.ok(b, cand) and L._local_connect(cand, fp, strip, etype):
                cands.append((memo.score(cand, _by_type(cand, slots, tg)), cand))
    cands.sort(key=lambda c: c[0])
    return cands[:L.TOP_K]


def _side_by_side(a, b):
    """Two rooms that touch and together make one rectangle (a landing and the gallery right behind it: one corridor split
    in two). A corridor meeting another along part of it (an L, a T) is not."""
    hull = Rect(min(a.x0, b.x0), min(a.y0, b.y0), max(a.x1, b.x1), max(a.y1, b.y1))
    return a.shared(b) is not None and abs(hull.area - a.area - b.area) < 1e-6


def _link(fp, rooms, stair, gate, role, walls):
    """(Room list with the stair room last, parents, root id) of a candidate, or None. The ground floor's living room
    takes the front door and roots the tree; an upper floor's tree grows from the stair. Either way the stair joins it
    through the room at its opening alone (gate), and every room is reached through a wall with room for its door. Two
    corridors that make one rectangle (a landing and a gallery right behind it) are not a layout."""
    rs = [L.Room(k, t, r) for k, (t, r) in enumerate(rooms)]
    st = L.Room(len(rs), "Stair", stair.rect)
    rs.append(st)
    acc = next((r for r in rs[:-1] if gate.at(r.rect)), None)
    if acc is None or acc.type not in gate.types:
        return None
    halls = [r.rect for r in rs if r.type == "Corridor"]
    if any(_side_by_side(a, b) for a, b in itertools.combinations(halls, 2)):
        return None
    if role == "ground":
        entries = [r for r in rs if r.type in P.ENTRY]
        if not entries:
            return None
        root = max(entries, key=lambda r: (L._part_len(L.front_part(r.rect, fp)), -r.id))
        if L._part_len(L.front_part(root.rect, fp)) < L.FRONT_MIN - EPS:
            return None
    else:
        root = st
    parents = L.connect(rs, fp, root.id, only={st.id: acc.id})
    if parents is None:
        return None
    # connect asks for enough shared wall; the door also needs its width between the walls' margins and jambs
    where = SimpleNamespace(footprint=fp, walls=walls)
    for rid, pid in parents.items():
        if pid is not None and st.id not in (rid, pid):
            iv = D.interval(where, rs[pid], rs[rid])
            if iv is None or iv[3] - iv[2] < D.MIN_WIDTH - EPS:
                return None
    return rs, parents, root.id


def _one_master(rs, fp, walls):
    """The top floor holds the house's master (spec §5.1): the largest bedroom that meets the master's minimum takes the
    name -- from a smaller master slot, or when the floor's program has none."""
    if any(r.type == "Master" for r in rs):
        L._master_is_largest(rs, fp, walls)
        return
    mt = P.ROOMS["Master"]
    fits = [(c.w * c.h, -r.id, r) for r in rs if r.type == "Bedroom" for c in [L.clear_rect(r.rect, fp, walls)]
            if c.short >= mt.min_short - EPS and c.long >= mt.min_long - EPS]
    if fits:
        max(fits)[2].type = "Master"


# ---------------------------------------------------------------- the plan

def _solve(fp, configs, prog, rng, walls, stair, level, role, memo):
    """The best valid layout of `prog` over these configs (near ties by the seed), as a Plan; None when none is valid."""
    gate = _Gate(stair, role, prog)
    # rooms are scored against the floor's area shared out by weight, not their block's: the blocks are fixed by the
    # stair, and a block-sized target would take a study as large as the living room for a good one
    unit = (fp.area - stair.rect.area) / sum(s.weight for s in prog.public + prog.private)
    best = []
    for parts, privs in configs:
        pub = _public(parts, fp, walls, gate, unit, role == "ground", memo)
        if pub is None:
            continue
        for groups in L.distribute(prog.private, privs) if privs else [[]]:
            per_block = _private(privs, groups, fp, walls, gate, unit, role, memo)
            if per_block is None:
                continue
            for combo in itertools.product(*(pub + per_block)):
                rooms = [rc for _s, c in combo for rc in c]
                linked = _link(fp, rooms, stair, gate, role, walls)
                if linked is not None:
                    best.append((sum(c[0] for c in combo) + L._access_cost(linked[0], linked[1]), rooms))
    if not best:
        return None
    best.sort(key=lambda c: c[0])
    score, rooms = L._near(best, rng)[0]
    rs, parents, root = _link(fp, rooms, stair, gate, role, walls)
    if role != "ground":
        if role == "top":
            _one_master(rs, fp, walls)
        return L.Plan(fp, prog, rs, root, None, dict(walls), [], parents, score, stair, level)
    front = rs[root]
    fpart = L.front_part(front.rect, fp)
    return L.Plan(fp, prog, rs, root, (fpart[0], fpart[1], front.rect.y0), dict(walls), [], parents, score, stair, level)


def _no_fit(fp, prog, walls, stair, level, role):
    """Nothing fits: one open room per wing, reported (as layout.plan)."""
    rooms = [L.Room(k, "Main", w) for k, w in enumerate(fp.wings)]
    fpart = L.front_part(rooms[0].rect, fp) or (rooms[0].rect.x0, rooms[0].rect.x1)
    entry = (fpart[0], fpart[1], rooms[0].rect.y0) if role == "ground" else None
    return L.Plan(fp, prog, rooms, 0, entry, dict(walls), [L.NO_FIT], {0: None}, 0.0, stair, level)


def plan_floor(fp, prog, rng, walls, stair, level, role, mirror=False, skip=(), shared=None):
    """One floor of a multi-storey house around its stair room: the first variant of `prog` (program.fallbacks over the
    floor's table, GROUND or UPPER; upstairs each turned for its floor by program.for_floor) with a valid layout, its best
    layout; `skip`: variants not to use (their required furniture did not fit); nothing fits -> a Plan reporting
    layout.NO_FIT. `role`: "ground" (the living room takes the front door; the stair is reached from it, a corridor or
    the dining room), "middle" or "top" (the floor is entered from the stair; the top floor holds the master).
    `shared`: a _Memo of this floor kept across the stair places tried (its room checks are reused)."""
    walls = dict(L.WALLS, **(walls or {}))
    table = P.GROUND if role == "ground" else P.UPPER
    options = pieces_options(fp, stair.rect)
    memo = _Memo(fp, walls, shared)
    for v in P.fallbacks(prog, table):
        if role != "ground":
            v = P.for_floor(v, role == "top")
        if v in skip:
            continue
        if role == "ground":
            configs = [c for pieces in options for c in _ground_configs(fp, pieces, v)]
        else:
            gate = _Gate(stair, role, v)
            configs = [c for pieces in options for c in _upper_configs(pieces, gate)]
        if mirror:
            configs.reverse()
        plan = _solve(fp, configs, v, rng, walls, stair, level, role, memo)
        if plan is not None:
            return plan
    return _no_fit(fp, table[0], walls, stair, level, role)
