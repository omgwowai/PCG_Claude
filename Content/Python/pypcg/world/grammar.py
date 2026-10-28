"""Facade grammar (视频 / City Sample 的建筑语法): the syntax of the engine's PCG grammar (PCGGrammar.h), a subset --
`[A,B]` a module sequence, `*` repeated any number of times, `+` at least once, `3` a fixed count, `{A:2,B:1}` one symbol
drawn by weight per repetition. `solve` fills a wall of a given length: it picks the repetition counts whose scalable
modules (window bays) need the scale closest to 1, sharing the count between two repeated parts so that what sits
between them (a door) stays centred -- what City Sample's BDF does with its F0 / F1 / F2 grammars and scalable modules.
`expand` unrolls a vertical grammar (`[G][U]*[RT]`) for a number of repeated levels. Pure."""
import itertools
import math
import random
import re
from dataclasses import dataclass

TOKEN = re.compile(r"\s*(?:(\[[^\[\]{}]*\])|(\{[^\[\]{}]*\}))\s*(\*|\+|\d+)?\s*")


@dataclass(frozen=True)
class Part:
    symbols: tuple = ()        # a sequence [A,B]
    choices: tuple = ()        # or a stochastic module {A:2,B:1}: ((symbol, weight), ...)
    rep: object = 1            # an int, "*" (0 or more) or "+" (1 or more)


def _symbol(s):
    s = s.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s):
        raise ValueError("bad grammar symbol %r" % s)
    return s


def parse(text):
    parts, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ValueError("bad grammar %r at %d" % (text, pos))
        seq, choice, rep = m.group(1), m.group(2), m.group(3)
        rep = 1 if rep is None else (rep if rep in ("*", "+") else int(rep))
        if seq is not None:
            body = seq[1:-1].strip()
            if not body:
                raise ValueError("empty module in %r" % text)
            parts.append(Part(symbols=tuple(_symbol(s) for s in body.split(",")), rep=rep))
        else:
            ch = []
            for item in choice[1:-1].split(","):
                if ":" not in item:
                    raise ValueError("stochastic module needs symbol:weight in %r" % text)
                s, w = item.split(":", 1)
                w = float(w)
                if w <= 0.0:
                    raise ValueError("weights must be positive in %r" % text)
                ch.append((_symbol(s), w))
            parts.append(Part(choices=tuple(ch), rep=rep))
        pos = m.end()
    if not parts:
        raise ValueError("empty grammar")
    return parts


def _draw(choices, rng):
    x = rng.uniform(0.0, sum(w for _s, w in choices))
    for s, w in choices:
        x -= w
        if x <= 0.0:
            return s
    return choices[-1][0]


def _reps(part, rng, n):
    """The symbols of `n` repetitions of the part (stochastic ones drawn once, in order)."""
    if part.symbols:
        return [list(part.symbols) for _ in range(n)]
    return [[_draw(part.choices, rng)] for _ in range(n)]


def solve(parts, length, widths, scalable, rng=None, smin=0.85, smax=1.2, max_rep=40, slack=False):
    """Symbols filling `length` (cm) and the common scale of the scalable ones: {"symbols", "scale", "ok", "counts",
    "slack"}. ok is False when no count keeps the scale within [smin, smax] (the closest is returned). With
    slack=True a count that would need more than smax keeps smax and leaves the rest as `slack` (cm, >= 0) for the
    caller to fill with plain wall; the least slack wins, then the scale closest to 1."""
    rng = rng or random.Random(0)
    reps, ranges = [], []
    for p in parts:
        n = p.rep if isinstance(p.rep, int) else max_rep
        reps.append(_reps(p, rng, n))
    sums = []
    for p, rr in zip(parts, reps):
        a = b = 0.0
        acc = [(0.0, 0.0)]
        for r in rr:
            for s in r:
                if s in scalable:
                    b += widths[s]
                else:
                    a += widths[s]
            acc.append((a, b))
        sums.append(acc)
        if isinstance(p.rep, int):
            ranges.append([p.rep])
        else:
            lo = 1 if p.rep == "+" else 0
            hi = lo
            while hi < len(rr) and acc[hi][0] + acc[hi][1] * smin <= length:
                hi += 1
            ranges.append(list(range(lo, max(lo, hi) + 1)))
    starred = [i for i, p in enumerate(parts) if not isinstance(p.rep, int)]
    best = None
    for counts in itertools.product(*ranges):
        a = sum(sums[i][c][0] for i, c in enumerate(counts))
        b = sum(sums[i][c][1] for i, c in enumerate(counts))
        rest = 0.0
        if b > 0.0:
            s = (length - a) / b
            if s <= 0.0:
                continue
            if slack and s > smax:
                s, rest = smax, length - a - b * smax
        elif abs(length - a) < 0.5:
            s = 1.0
        elif slack and a < length:
            s, rest = 1.0, length - a
        else:
            continue
        spread = (max(counts[i] for i in starred) - min(counts[i] for i in starred)) if len(starred) > 1 else 0
        ok = smin <= s <= smax
        key = (not ok, round(rest, 6), abs(math.log(s)) + 0.05 * spread)
        if best is None or key < best[0]:
            best = (key, counts, s, ok, rest)
    if best is None:
        return {"symbols": [], "scale": 1.0, "ok": False, "counts": [], "slack": 0.0}
    _key, counts, s, ok, rest = best
    symbols = [sym for i, c in enumerate(counts) for r in reps[i][:c] for sym in r]
    return {"symbols": symbols, "scale": s, "ok": ok, "counts": list(counts), "slack": rest}


def positions(res, widths, scalable):
    """[(x0, x1)] of each solved symbol along the wall, from 0."""
    out, x = [], 0.0
    for s in res["symbols"]:
        w = widths[s] * (res["scale"] if s in scalable else 1.0)
        out.append((x, x + w))
        x += w
    return out


def expand(parts, repeats):
    """A vertical grammar unrolled: each `*` part `repeats` times (`+` at least once), fixed counts as written; a
    stochastic part contributes its first choice."""
    out = []
    for p in parts:
        n = p.rep if isinstance(p.rep, int) else (max(1, repeats) if p.rep == "+" else repeats)
        syms = list(p.symbols) if p.symbols else [p.choices[0][0]]
        for _ in range(n):
            out.extend(syms)
    return out
