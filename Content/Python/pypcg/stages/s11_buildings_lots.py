"""Stage 11 -- Buildings, first Python node: the three classes' building footprints (`s11_buildings_lots`).

`FilterTags_SmallDistricts` / `_MediumDistricts` / `_LargeDistricts` (`Filter_Tags`, exact tag) split the
stage-9 volume's items into the three classes. Each footprint is handed back as the very object it was read
as (`convert.passed_through`), so the native texture writes that follow (`Subgraph_2_SmallDistrict` ..., kept:
the texture's pixels are not readable from Python) see the official data, frame and stored local vertices
included (traps.md 68). `docs/pypcg/stages/s11.md` step 1."""
from pypcg.geo import Polygon

STAGE = 11
RECORD = "s11_lots"
DOC = """Buildings (建筑), lot split: the stage-9 building footprints by exact class tag."""
RANDOM = False
PARAMS = {}
INPUTS = {"Lots": "area"}
OUTPUTS = ("SmallLots", "MediumLots", "LargeLots")

# FilterTags_SmallDistricts / FilterTags_MediumDistricts / FilterTags_LargeDistricts (`FilteredInputTags`)
CLASS_TAGS = (("SmallLots", "SmallDistrictsBldgFootprints"), ("MediumLots", "MediumDistrictsBldgFootprints"),
              ("LargeLots", "LargeDistrictsBldgFootprints"))
# `Filter_Tags` tags its sides Selected / Unselected and `DeleteTags_*` removes both after the texture write
DROPPED_TAGS = ("Selected", "Unselected")


def split(items):
    """{pin: [(polygon, tags)]}: every polygon carrying a class tag, in input order, tags as read less the
    two bookkeeping tags."""
    out = {pin: [] for pin in OUTPUTS}
    for v, tags in items:
        if not isinstance(v, Polygon):
            continue
        for pin, tag in CLASS_TAGS:
            if tag in tags:
                out[pin].append((v, sorted(t for t in tags if t not in DROPPED_TAGS)))
    return out


def run(inputs, params, ctx):
    out = split(inputs.get("Lots", []))
    ctx.notes.append("lots: %s" % ", ".join("%s %d" % (p, len(v)) for p, v in out.items()))
    return out
