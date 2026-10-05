"""Render the trailer to an mp4: python3 trailer/render.py [--fps 30] [--only 12.5,30.3] [--jobs 8]

Each frame is one headless-Chrome screenshot of trailer.html?t=<seconds> (render(t) is a pure function of t), then
ffmpeg joins the frames and the soundtrack (mix.py: score, effects and narration)."""
import argparse
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DUR = 100.0


def build():
    with open(os.path.join(HERE, "trailer_data.json")) as f:
        data = f.read()
    with open(os.path.join(HERE, "trailer.html")) as f:
        html = f.read()
    html = html.replace("<script>\n/* The Irregulars", f"<script>window.DATA = {data};</script>\n<script>\n/* The Irregulars", 1)
    out = os.path.join(HERE, "build", "trailer_build.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write(html)
    return out


def shot(page, t, path, profile):
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--mute-audio",
           f"--user-data-dir={profile}", "--window-size=1920,1080", "--force-device-scale-factor=1",
           "--virtual-time-budget=1500", f"--screenshot={path}", f"file://{page}?t={t:.4f}"]
    for _ in range(6):  # Chrome writes the screenshot but often does not exit: wait for the file, then stop it
        if os.path.exists(path):
            os.remove(path)
        pr = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0, last = time.time(), -1
        while time.time() - t0 < 40:
            time.sleep(0.15)
            size = os.path.getsize(path) if os.path.exists(path) else -1
            if size > 1500 and size == last:
                break
            last = size
        pr.kill()
        pr.wait()
        if os.path.exists(path) and os.path.getsize(path) > 1500:
            return path
    raise RuntimeError(f"frame at t={t} failed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--resume", action="store_true", help="keep frames already rendered")
    ap.add_argument("--only", default="", help="comma-separated times: render just these stills")
    a = ap.parse_args()
    page = build()
    frames = os.path.join(HERE, "build", "frames")
    if a.only:
        os.makedirs(os.path.join(HERE, "build", "stills"), exist_ok=True)
        ts = [float(x) for x in a.only.split(",")]
        paths = [os.path.join(HERE, "build", "stills", f"t{t:06.2f}.png") for t in ts]
    else:
        if not a.resume:
            shutil.rmtree(frames, ignore_errors=True)
        os.makedirs(frames, exist_ok=True)
        n = int(DUR * a.fps)
        ts = [i / a.fps for i in range(n)]
        paths = [os.path.join(frames, f"f{i:05d}.png") for i in range(n)]
    profiles = [os.path.join(HERE, "build", f"profile{j}") for j in range(a.jobs)]
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        todo = [(t, p) for t, p in zip(ts, paths) if not (a.resume and os.path.exists(p) and os.path.getsize(p) > 1500)]
        futs = [ex.submit(shot, page, t, p, profiles[i % a.jobs]) for i, (t, p) in enumerate(todo)]
        for k, f in enumerate(cf.as_completed(futs)):
            f.result()
            if k % 90 == 0:
                print(f"{k}/{len(futs)} frames", flush=True)
    if a.only:
        print("\n".join(paths))
        return
    wav = os.path.join(HERE, "build", "mix.wav")
    subprocess.run([sys.executable, os.path.join(HERE, "mix.py"), wav], check=True)
    out = os.path.join(HERE, "the_irregulars_trailer.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(a.fps), "-i", os.path.join(frames, "f%05d.png"),
                    "-i", wav, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
    print(out)


if __name__ == "__main__":
    main()
