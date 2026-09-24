# Tools/run_sa_stages.ps1
# The call sequence for the 18-stage small-area run, printed so the run is
# reproducible by hand and so the log file has one line per call.
#
# WHAT CHANGED FROM THE PLAN'S VERSION, and why it matters:
#
# The plan assumed gen -> shot_debug -> shot_geom per stage, with the generation
# settling inside the gap between two MCP round trips and a capture's file check
# answering in the same call. Measurement on 2026-09-24 showed both assumptions wrong:
#
#   * CAPTURE LATENCY IS ~1-2 MINUTES. `take_high_res_screenshot` queues an
#     AutomationEditorTask that writes on a much later frame. Stage 1's two frames
#     landed at 14:12 and 14:23 after being fired around 14:10 and 14:20, and six
#     captures were wrongly recorded as failures because their `exists` check ran in
#     the same call. So a capture is verified on the NEXT call, from disk.
#   * A SINGLE ROUND TRIP IS NOT ALWAYS ENOUGH FOR GENERATION. Stage 1's first probe
#     read `generated: false` one call after `gen` returned fired=true, because it
#     writes a mesh terrain. So `generated` is re-read until true rather than trusted
#     once.
#
# Therefore each stage is FOUR calls, not three:
#   gen N -> shot_debug N -> shot_geom N -> verify N-1
# and the driver (pcg_sa_drive.py) does one stage per call in two phases, printing a
# single line so ~70 calls stay affordable in context.
#
# This script does not talk to the bridge: run_unreal_script is a tool the agent
# calls. It prints the sequence and writes it to disk.

param([switch]$PrintOnly)

$lines = @()
$lines += "# stage 1 is already captured and verified; the run starts at stage 2"
foreach ($n in 2..18) {
    $lines += "pcg_sa_drive.py {`"stage`": $n, `"phase`": `"debug`", `"verify_from`": $($n - 1)}"
    $lines += "pcg_sa_drive.py {`"stage`": $n, `"phase`": `"geom`",  `"verify_from`": $($n - 1)}"
}
$lines += "pcg_sa_drive.py {`"stage`": 18, `"phase`": `"geom`", `"verify_from`": 18}   # final verify pass"
$lines += "pcg_sa_shots.py {`"phase`": `"census`"}"
$lines += "pcg_sa_drive.py {`"stage`": 18, `"phase`": `"finish`"}"
$lines += "# host-side between debug and geom of each stage: wait until the frame lands"
$lines += "# (Saved/Screenshots/WindowsEditor/sa_stage_NN_<graph>_{debug,geometry}.png)"

if ($PrintOnly) { $lines | ForEach-Object { Write-Output $_ }; exit 0 }

$out = "Saved/Reports/sa_call_sequence.txt"
New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null
$lines | Set-Content -Encoding utf8 $out
Write-Output "wrote $out ($($lines.Count) lines)"
