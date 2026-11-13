# encode_clips.py -- the cloud director's recorded frames (Saved/Reports/cs_cloud_motion/frames/<clip>/f_00000.png ...)
# -> an H.264 MP4, a poster frame and a frame strip per clip, in Saved/Reports/cs_cloud_motion/clips/.
#   C:\Python314\python.exe -P -E Tools/cs_weather/encode_clips.py [clip ...]      (default: every clip with frames)
import argparse
import glob
import os
import shutil
import subprocess
import sys

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.path.join(ROOT, "Saved", "Reports", "cs_cloud_motion")
FRAMES = os.path.join(BASE, "frames")
CLIPS = os.path.join(BASE, "clips")
WINGET_FFMPEG = (r"C:\Users\JianjunChi\AppData\Local\Microsoft\WinGet\Packages"
                 r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe")


def ffmpeg():
    exe = shutil.which("ffmpeg") or WINGET_FFMPEG
    if not (shutil.which(exe) or os.path.exists(exe)):
        raise SystemExit("ffmpeg not found (looked on PATH and at %s)" % WINGET_FFMPEG)
    return exe


def encode(clip, fps):
    paths = sorted(glob.glob(os.path.join(FRAMES, clip, "f_*.png")))
    if not paths:
        raise SystemExit("%s: no frames" % clip)
    for i, p in enumerate(paths):                  # ffmpeg's image2 pattern needs 0..n-1 without gaps
        if os.path.basename(p) != "f_%05d.png" % i:
            raise SystemExit("%s: frame %d missing (found %s)" % (clip, i, os.path.basename(p)))
    os.makedirs(CLIPS, exist_ok=True)
    mp4 = os.path.join(CLIPS, clip + ".mp4")
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-framerate", str(fps), "-i",
                    os.path.join(FRAMES, clip, "f_%05d.png"), "-c:v", "libx264", "-crf", "20", "-preset", "slow",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", mp4], check=True)
    # the copy the HTML page links (docs/citysample-cloud-motion/): 1280 px wide, CRF 26 -- the CRF 20 masters above run
    # 30-55 MB per clip, ~10x the spec's estimate for the docs folder (Task 11 ruling)
    web = os.path.join(CLIPS, clip + "_web.mp4")
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", mp4, "-vf", "scale=1280:-2", "-c:v", "libx264",
                    "-crf", "26", "-preset", "slow", "-pix_fmt", "yuv420p", "-movflags", "+faststart", web], check=True)
    poster = Image.open(paths[len(paths) // 2]).convert("RGB")
    poster.thumbnail((1280, 1280))
    poster.save(os.path.join(CLIPS, clip + "_poster.jpg"), quality=88)
    tiles = []
    for i in range(6):
        im = Image.open(paths[round(i * (len(paths) - 1) / 5)]).convert("RGB")
        im.thumbnail((320, 320))
        tiles.append(im)
    strip = Image.new("RGB", (sum(t.width for t in tiles) + 4 * 5, max(t.height for t in tiles)), (16, 16, 16))
    x = 0
    for t in tiles:
        strip.paste(t, (x, 0))
        x += t.width + 4
    strip.save(os.path.join(CLIPS, clip + "_strip.jpg"), quality=85)
    return {"clip": clip, "frames": len(paths), "mp4": mp4, "mb": round(os.path.getsize(mp4) / 1e6, 2),
            "web_mb": round(os.path.getsize(web) / 1e6, 2)}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("clips", nargs="*")
    ap.add_argument("--fps", type=int, default=30)
    a = ap.parse_args()
    names = a.clips or sorted(d for d in os.listdir(FRAMES) if os.path.isdir(os.path.join(FRAMES, d)))
    for name in names:
        print(encode(name, a.fps))
    return 0


if __name__ == "__main__":
    sys.exit(main())
