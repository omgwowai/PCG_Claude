"""Fixture generator for stage 3, BG_Mountains (`pypcg/stages/s03_bg_mountains.py`) -- REGENERATE ONLY
when the data asset or a generation layer changes, then re-run the offline suite.

Writes two files, both from the editor, read-only (it generates nothing and saves nothing; the stage-3
volume must hold its OFFICIAL graph and have generated, e.g. right after V2's `restore`):

  Tools/pypcg/data/s03_vista_cliffs.json     -- the VistaCliffs_PCG points, as pypcg.geo JSON: the
                                                stage's input, used by the tests and the V1 check.
  Tools/pypcg/data/s03_official_instances.json -- the transforms of the 59 instances the official graph's
                                                StaticMeshSpawner_0 placed: the stage's offline oracle.

Run through the bridge with no args: run_unreal_script("pypcg_cliffs_fixture.py", {})."""
import json
import os
import sys

import unreal

_PY = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir() + "Python")
if _PY not in sys.path:
    sys.path.insert(0, _PY)
for _m in [m for m in sys.modules if m == "pypcg" or m.startswith("pypcg.")]:
    del sys.modules[_m]
_REPO = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())

ASSET = "/CitySamplePCG/PCG/DataAssets/VistaCliffs_PCG"
STAGE = 3
AUTHOR = "Content/Python/pypcg_cliffs_fixture.py"


def _asset_fixture():
    from pypcg import geo
    from pypcg.ue import convert
    asset = unreal.EditorAssetLibrary.load_asset(ASSET)
    items = []
    for td in asset.get_editor_property("data").get_editor_property("tagged_data"):
        d = td.get_editor_property("data").get_editor_property("data")
        items.append([geo.to_json(convert.points_of(d)), sorted(str(t) for t in td.get_editor_property("tags"))])
    return {"source": ASSET, "read_by": AUTHOR, "Cliffs": items}


def _instance_fixture():
    from pypcg import census
    a = census.volume(STAGE)
    g = census.component(STAGE).get_graph()
    rows = []
    for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
        sm = c.get_editor_property("static_mesh")
        path = sm.get_path_name() if sm else ""
        for i in range(c.get_instance_count()):
            t = c.get_instance_transform(i, True)
            r = t.rotation.rotator()
            rows.append([path, [t.translation.x, t.translation.y, t.translation.z],
                         [r.pitch, r.yaw, r.roll], [t.scale3d.x, t.scale3d.y, t.scale3d.z]])
    rows.sort(key=lambda r: (r[0], r[1]))
    return {"source": "the demo level's official PCG_1_3_BG_Mountains volume", "read_by": AUTHOR,
            "graph": g.get_path_name() if g else None, "instances": rows}


def run(args):
    out = {}
    for name, doc, n in (("s03_vista_cliffs.json", _asset_fixture(), None),
                         ("s03_official_instances.json", _instance_fixture(), None)):
        path = os.path.join(_REPO, "Tools", "pypcg", "data", name)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=0)
        out[name] = {"path": path, "n": len(doc.get("instances") or doc.get("Cliffs") or [])}
    return out


try:
    mcp_result = json.loads(json.dumps(run(mcp_args or {}), default=str))
except Exception as _exc:
    import traceback
    mcp_result = {"error": "%s: %s" % (type(_exc).__name__, str(_exc)[:600]), "tb": traceback.format_exc()[-1200:]}
