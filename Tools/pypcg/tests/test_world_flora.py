import os

import pytest

from pypcg.world import flora

ROOTS = {"/Game/": r"E:\PCG_Claude\Content", "/CitySamplePCG/": r"E:\PCG_Claude\Plugins\CitySamplePCG\Content",
         "/PCGBiomeSample/": r"E:\UnrealEngine\Engine\Plugins\Experimental\PCGBiomeSample\Content"}


def _file(path):
    pkg = path.split(".")[0]
    for prefix, root in ROOTS.items():
        if pkg.startswith(prefix):
            return os.path.join(root, *pkg[len(prefix):].split("/")) + ".uasset"
    return None


@pytest.mark.skipif(not os.path.isdir(os.path.join(ROOTS["/Game/"], "Megascans", "3D_Plants")),
                    reason="the Electric Dreams vegetation is not copied in (Tools/pyworld/ed_closure.py --copy)")
def test_every_mesh_exists():
    missing = [m for m in flora.all_meshes() if not os.path.isfile(_file(m) or "")]
    assert missing == []


def test_palette_shape():
    assert len(flora.SPECIES) >= 40
    for name, s in flora.SPECIES.items():
        assert s["meshes"] and s["layer"] in ("tree", "shrub", "grass", "ground", "debris", "rock"), name
        lo, hi = s["scale"]
        assert 0.0 < lo <= hi, name
        if s["layer"] in ("tree", "shrub"):
            assert s["space"] > 0.0, name
        if s["layer"] == "rock":
            assert all(m in flora.HEIGHT for m in s["meshes"]), name
    assert flora.TREE_SINK and all(m in flora.TREE_SINK for m in flora.TREE_MESHES)
