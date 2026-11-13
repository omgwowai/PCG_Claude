# cs_cloud_director.py -- the cloud director's bridge entry, one phase per call (spec §5.1):
#   play   {"preset": "art_towers", "speed": 30, "t": 0}   apply the preset, put the director's MID on the cloud, run
#   pause / resume / speed {"speed": 60} / seek {"t": 600} (refused during a transition) / state / stop {"static": false}
#   to     {"preset": "art_storm", "minutes": 30 | "seconds": 60, "light": "full" | "clouds"}
#   record {"clips": ["motion_towers", ...] | "all" | "stills", "seconds": 1 (quick test), "max_commit_gb": 64}
# Status: Saved/Reports/cs_cloud_motion/director.json. End a session with cs_weather.py restore {"to": "original"}.
import importlib
import json

import cs_cloud_rt as RT

importlib.reload(RT)
PHASES = {"play": RT.phase_play, "pause": RT.phase_pause, "resume": RT.phase_resume, "speed": RT.phase_speed,
          "seek": RT.phase_seek, "state": RT.phase_state, "stop": RT.phase_stop, "to": RT.phase_to,
          "record": RT.phase_record}


def _main(args):
    phase = args.get("phase", "state")
    if phase not in PHASES:
        return {"abort": "unknown phase %r" % phase}
    return json.loads(json.dumps(PHASES[phase](args), default=str))


if "mcp_args" in globals() or __name__ == "__main__":
    mcp_result = _main(globals().get("mcp_args") or {})
