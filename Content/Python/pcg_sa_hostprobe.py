# pcg_sa_hostprobe.py — read-only. What does the bridge's exec environment look like to
# the scripts it runs? Needed to guard a module's "main" block so that importing it from
# another script does not execute it.
#
# Why it matters: pcg_sa_shots.py does `import pcg_sa_run` to reuse the runner's helpers
# (the plan requires one definition of the volume/instance logic). That import executed
# pcg_sa_run's top-level block, which printed a stray
# `{"ok": true, "data": {"abort": "phase probe needs a stage"}}` line into the same stdout
# the caller parses, and called run() with default arguments. It was harmless only because
# the default phase (probe) is read-only.
#
# The guard must be right for BOTH cases:
#   * direct execution of pcg_sa_run.py by the bridge  -> block MUST run
#   * `import pcg_sa_run` from pcg_sa_shots.py          -> block MUST NOT run
# `if __name__ == "__main__":` does that only if the bridge execs with __name__ set to
# "__main__"; `"mcp_args" in globals()` does it only if mcp_args is always present. So
# measure instead of guessing.

import gc
import json

R = {
    "dunder_name": __name__,
    "name_is_main": __name__ == "__main__",
    "has_mcp_args": "mcp_args" in globals(),
    "mcp_args_type": type(globals().get("mcp_args")).__name__,
    "has_builtins_name": "__builtins__" in globals(),
    "globals_count": len(globals()),
    "sample_globals": sorted(k for k in globals().keys())[:25],
}
print(json.dumps(R, ensure_ascii=False, indent=1, default=str))
mcp_result = R
del R
gc.collect()
