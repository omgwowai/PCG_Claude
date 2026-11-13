# _quit_editor.py -- close the editor cleanly on the next Slate tick: QUIT_EDITOR is the normal close path (it asks to
# save any dirty package), deferred so that this bridge call returns before the editor starts shutting down.
import unreal

_handle = {}


def _tick(_dt):
    unreal.unregister_slate_post_tick_callback(_handle["h"])
    unreal.SystemLibrary.quit_editor()


_handle["h"] = unreal.register_slate_post_tick_callback(_tick)
mcp_result = {"quit": "on the next tick"}
