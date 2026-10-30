"""PyInterior checks (spec 2026-10-28 §7): the invariants a house must keep, and its Summary."""
from pypcg.interior import catalog as C
from pypcg.interior import doors as D
from pypcg.interior import furnish as FU
from pypcg.interior import layout as L

TUCK = {("chair", "dining_table"), ("chair", "desk"), ("island", "stool")}


def validate(plan, doors, wins, places):
    """[failure]: unreachable rooms, missing passages, furniture overlaps, furniture in a door's sweep or a passage's
    approach, habitable rooms without a window (a terrace's glass door counts). An upper floor (no entry) has no front
    door."""
    out = list(plan.failures)
    by = {r.id: r for r in plan.rooms}
    if len(plan.parents) != len(plan.rooms):
        out.append("unreachable rooms: %d of %d reached" % (len(plan.parents), len(plan.rooms)))
    into = {}
    for d in doors:
        if d.tree and d.kind != "front":
            into[d.b] = into.get(d.b, 0) + 1
    missing = [by[r.id].type for r in plan.rooms if r.id != plan.front_room and into.get(r.id, 0) != 1]
    if missing:
        out.append("no single passage into %s" % ", ".join(missing))
    if plan.entry is not None and not any(d.kind == "front" for d in doors):
        out.append("no front door")
    solid = [p for p in places if C.ITEMS[p.item].kind != "rug" and p.z < 100.0]
    overlaps = 0
    for i, a in enumerate(solid):
        for b in solid[i + 1:]:
            if a.room == b.room and a.rect().overlaps(b.rect()) and \
                    tuple(sorted((C.ITEMS[a.item].kind, C.ITEMS[b.item].kind))) not in TUCK:
                overlaps += 1
    if overlaps:
        out.append("%d furniture overlaps" % overlaps)
    blocked = 0
    for d in doors:
        for rid in (d.a, d.b):
            if rid is None:
                continue
            z = D.swing(d, by[rid], plan) if (d.leaf and rid == d.b) else FU.approach(d, by[rid], plan)
            blocked += sum(1 for p in solid if p.room == rid and p.rect().overlaps(z))
    if blocked:
        out.append("%d pieces in a door's way" % blocked)
    lit = {w.room for w in wins} | {d.b for d in doors if d.kind == "terrace"}
    dark = [r.type for r in plan.rooms if r.type in L.HABITABLE and r.id not in lit]
    if dark:
        out.append("no window in %s" % ", ".join(dark))
    return out


def summary(plan, doors, wins, places, parts, failures):
    rooms = plan.rooms
    return {"program": plan.program.name, "area_m2": round(plan.footprint.area_m2, 2), "wings": len(plan.footprint.wings),
            "rooms": len(rooms), "bedrooms": sum(1 for r in rooms if r.type in ("Master", "Bedroom")),
            "corridors": sum(1 for r in rooms if r.type == "Corridor"),
            "room_types": ",".join(r.type for r in rooms),
            "doors": sum(1 for d in doors if d.leaf), "openings": sum(1 for d in doors if not d.leaf),
            "windows": len(wins), "items": len(places), "parts": len(parts), "failures": len(failures),
            "first_failure": failures[0] if failures else "", "error": ""}
