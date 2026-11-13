# cs_weather_save_mis.py -- save this project's own cloud material instances (/Game/CitySampleSky/MI_*) that the batch
# left modified in memory (it applies presets with save_mi=False, because a save inside a Slate tick re-enters it).
# Never touches the demo level's packages. A direct bridge call, not a tick callback.
import unreal

ROOT = "/Game/CitySampleSky/"


def _main():
    eal = unreal.EditorLoadingAndSavingUtils
    dirty = [p.get_name() for p in eal.get_dirty_content_packages()]
    mine = [n for n in dirty if n.startswith(ROOT)]
    saved = [[n, bool(unreal.EditorAssetLibrary.save_asset(n, only_if_is_dirty=False))] for n in mine]
    after = sorted(p.get_name() for p in eal.get_dirty_content_packages() + eal.get_dirty_map_packages())
    return {"saved": saved, "dirty_after": after}


mcp_result = _main()
