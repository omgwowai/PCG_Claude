"""V2 (spec 3): compare what a slim graph produced against the official graph, by tag and by mesh.
Pure Python: census.py feeds it plain records.

A record is {"generated": bool, "items": [describe(...)], "instances": {"total", "per_mesh", "components"}}."""
import json
import os
import statistics

from . import geo

V2_SEEDS = (7, 13, 101, 977, 42)            # 42 last: the downstream check runs on the last slim run
DEFAULTS = {"count": 0.25, "area": 0.10, "length": 0.10, "points": 0.25, "instances": 0.25, "share_pp": 10.0,
            "share_min": 0.01, "deterministic": 0.01, "min_count": 5, "bbox_margin_cm": 20000.0}
THRESHOLDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v2_thresholds.json")
COMPATIBLE = {"polygon": {"polygon"}, "spline": {"spline"}, "points": {"points"}, "param": {"param"},
              "other": {"other", "polygon", "spline", "points"}}


def _bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [[min(xs), min(ys)], [max(xs), max(ys)]] if pts else None


def describe(value, tags, cls=""):
    out = {"tags": sorted(tags), "class": cls, "kind": "other", "area_m2": 0.0, "length_m": 0.0, "points": 0, "bbox": None}
    if isinstance(value, geo.Polygon):
        out.update(kind="polygon", area_m2=geo.area_m2(value), bbox=_bbox(value.outer))
    elif isinstance(value, geo.Spline):
        pts = list(value.polyline or value.points)
        ring = pts + pts[:1] if value.closed else pts
        out.update(kind="spline", length_m=geo.path_length(ring) / 100.0, bbox=_bbox(pts))
    elif isinstance(value, geo.Points):
        out.update(kind="points", points=len(value), bbox=_bbox(value.loc))
    elif isinstance(value, geo.ParamSet):
        out.update(kind="param")
    return out


def summarize(items, tags=None):
    """{tag: {"n", "area_m2", "length_m", "points", "kinds", "bbox"}}.

    tags selects what an item is grouped under (ruling T7c):
      None (the default) -- every non-':' tag of the item, i.e. PCGPrimitives bookkeeping (tags with
          ':') is ignored (ruling N3) and an item that carries no remaining tag is skipped entirely;
      a set   -- each of the item's tags that is in the set (an item with none of them is ignored);
      an empty set -- every item counts under the single group "(all)".
    """
    out = {}
    for it in items:
        if tags is None:
            names = [t for t in it["tags"] if ":" not in t]
        elif tags:
            names = [t for t in it["tags"] if t in tags]
        else:
            names = ["(all)"]
        for t in names:
            s = out.setdefault(t, {"n": 0, "area_m2": 0.0, "length_m": 0.0, "points": 0, "kinds": [], "bbox": None})
            s["n"] += 1
            s["area_m2"] += it["area_m2"]
            s["length_m"] += it["length_m"]
            s["points"] += it["points"]
            if it["kind"] not in s["kinds"]:
                s["kinds"].append(it["kind"])
            if it["bbox"]:
                b = s["bbox"]
                s["bbox"] = it["bbox"] if b is None else [[min(b[0][0], it["bbox"][0][0]), min(b[0][1], it["bbox"][0][1])],
                                                          [max(b[1][0], it["bbox"][1][0]), max(b[1][1], it["bbox"][1][1])]]
    return out


def thresholds(stage):
    th = dict(DEFAULTS)
    if os.path.exists(THRESHOLDS):
        doc = json.load(open(THRESHOLDS, encoding="utf-8"))
        th.update(doc.get("default", {}))
        th.update(doc.get("stages", {}).get(str(stage), {}))
    return th


def _within(inner, outer, margin):
    return (inner[0][0] >= outer[0][0] - margin and inner[0][1] >= outer[0][1] - margin
            and inner[1][0] <= outer[1][0] + margin and inner[1][1] <= outer[1][1] + margin)


def verdict(official, runs, deterministic, th, tags=None):
    so, sr = summarize(official["items"], tags), [summarize(r["items"], tags) for r in runs]
    failures, rows = [], []
    stage_th = th
    for tag, o in sorted(so.items()):
        # A stage may hold a tag to its own limits (`"tags": {tag: {key: value}}` in the stage's entry
        # of v2_thresholds.json): one tag's measured noise then widens that tag only, not the stage.
        th = dict(stage_th)
        th.update((stage_th.get("tags") or {}).get(tag, {}))
        for i, s in enumerate(sr):
            r = s.get(tag)
            if not r:
                failures.append("run %d: tag %s missing" % (i, tag))
                continue
            allowed = set().union(*(COMPATIBLE[k] for k in o["kinds"]))
            if not set(r["kinds"]) <= allowed:
                failures.append("run %d: tag %s is %s, official %s" % (i, tag, r["kinds"], o["kinds"]))
            if o["bbox"] and r["bbox"] and not _within(r["bbox"], o["bbox"], th["bbox_margin_cm"]):
                failures.append("run %d: tag %s outside the official bounds + %.0f m" % (i, tag, th["bbox_margin_cm"] / 100))
        for metric, key, tol in (("count", "n", th["count"]), ("area", "area_m2", th["area"]),
                                 ("length", "length_m", th["length"]), ("points", "points", th["points"])):
            off = o[key]
            if not off:
                continue
            if metric in ("count", "area") and o["n"] < th["min_count"]:
                rows.append({"tag": tag, "metric": metric, "official": off, "skipped": "fewer than %d items" % th["min_count"]})
                continue
            vals = [s.get(tag, {}).get(key, 0) for s in sr]
            med = statistics.median(vals)
            limit = th["deterministic"] if deterministic else tol
            rel = (med - off) / off
            ok = abs(rel) <= limit
            rows.append({"tag": tag, "metric": metric, "official": off, "median": med, "runs": vals, "rel": rel, "limit": limit, "ok": ok})
            if not ok:
                failures.append("tag %s %s: median %.4g vs official %.4g (%+.1f %%, limit %.0f %%)"
                                % (tag, metric, med, off, 100 * rel, 100 * limit))
    th = stage_th
    oi = official["instances"]
    if oi["total"]:
        totals = [r["instances"]["total"] for r in runs]
        med = statistics.median(totals)
        limit = th["deterministic"] if deterministic else th["instances"]
        rel = (med - oi["total"]) / oi["total"]
        rows.append({"tag": "(instances)", "metric": "total", "official": oi["total"], "median": med, "runs": totals,
                     "rel": rel, "limit": limit, "ok": abs(rel) <= limit})
        if abs(rel) > limit:
            failures.append("instances: median %d vs official %d (%+.1f %%)" % (med, oi["total"], 100 * rel))
        meshes = set(oi["per_mesh"]) | {m for r in runs for m in r["instances"]["per_mesh"]}
        for m in sorted(meshes):
            off_share = oi["per_mesh"].get(m, 0) / oi["total"]
            shares = [r["instances"]["per_mesh"].get(m, 0) / r["instances"]["total"] if r["instances"]["total"] else 0.0 for r in runs]
            med_share = statistics.median(shares)
            if max(off_share, med_share) < th["share_min"]:
                continue
            diff_pp = 100 * (med_share - off_share)
            ok = abs(diff_pp) <= th["share_pp"]
            rows.append({"tag": "(mesh)", "metric": m, "official": off_share, "median": med_share, "runs": shares,
                         "rel": diff_pp, "limit": th["share_pp"], "ok": ok})
            if not ok:
                failures.append("mesh %s: share %.1f %% vs official %.1f %%" % (m, 100 * med_share, 100 * off_share))
    return {"pass": not failures, "failures": failures, "rows": rows}


def downstream(pairs):
    """pairs {stage: (official record, record read with the slim upstream)}: each must still generate,
    with instances and outputs where the official one has them (spec 3, V2.3)."""
    out = []
    for k, (o, r) in sorted(pairs.items()):
        if not r["generated"]:
            out.append("stage %d: not generated" % k)
            continue
        if o["instances"]["total"] and not r["instances"]["total"]:
            out.append("stage %d: no instances (official %d)" % (k, o["instances"]["total"]))
        if o["items"] and not r["items"]:
            out.append("stage %d: no outputs (official %d)" % (k, len(o["items"])))
    return out


def same(a, b, tags=None):
    """True when two records summarise identically (counts exact, sizes to 1e-6 relative)."""
    sa, sb = summarize(a["items"], tags), summarize(b["items"], tags)
    if set(sa) != set(sb) or a["instances"]["per_mesh"] != b["instances"]["per_mesh"]:
        return False
    for t in sa:
        for k in ("n", "points"):
            if sa[t][k] != sb[t][k]:
                return False
        for k in ("area_m2", "length_m"):
            if abs(sa[t][k] - sb[t][k]) > 1e-6 * max(1.0, abs(sa[t][k])):
                return False
    return True


def markdown(stage, v, down_failures, notes=()):
    lines = ["# V2 -- stage %d" % stage, "", "Verdict: **%s**" % ("pass" if v["pass"] and not down_failures else "FAIL"), ""]
    lines += ["| Tag | Metric | Official | Median | Runs | Diff | Limit | OK |", "|---|---|---|---|---|---|---|---|"]
    for r in v["rows"]:
        if "skipped" in r:
            lines.append("| %s | %s | %.4g | - | - | - | %s | - |" % (r["tag"], r["metric"], r["official"], r["skipped"]))
        else:
            lines.append("| %s | %s | %.4g | %.4g | %s | %+.3g | %.3g | %s |" % (
                r["tag"], r["metric"], r["official"], r["median"], ", ".join("%.4g" % x for x in r["runs"]),
                r["rel"], r["limit"], "yes" if r["ok"] else "**no**"))
    lines += ["", "Failures:", ""] + ["- " + f for f in v["failures"] + list(down_failures)] if v["failures"] or down_failures else ["", "Failures: none"]
    lines += ["", "Notes:", ""] + ["- " + n for n in notes] if notes else []
    return "\n".join(lines) + "\n"
