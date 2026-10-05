"""Mix the trailer soundtrack: score (music.py) and narration (voice.py),
with the music ducked under the voice. python3 trailer/mix.py out.wav"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main(out):
    b = os.path.join(HERE, "build")
    subprocess.run([sys.executable, os.path.join(HERE, "music.py"), os.path.join(b, "music.wav")], check=True)
    lines = json.load(open(os.path.join(HERE, "voice", "lines.json")))
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", os.path.join(b, "music.wav")]
    for ln in lines:
        cmd += ["-i", ln["file"]]
    parts = []
    for i, ln in enumerate(lines):
        ms = int(ln["t"] * 1000)
        parts.append(f"[{i + 1}:a]aresample=44100,aformat=channel_layouts=mono,volume=1.6,adelay={ms}|{ms}[v{i}]")
    vs = "".join(f"[v{i}]" for i in range(len(lines)))
    parts.append(f"{vs}amix=inputs={len(lines)}:normalize=0,apad=whole_dur=100[voice]")
    parts.append("[voice]asplit=2[vk][vm]")
    parts.append("[0:a]volume=0.55[mus]")
    parts.append("[mus][vk]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=400[duck]")
    parts.append("[duck][vm]amix=inputs=2:normalize=0,alimiter=limit=0.95,atrim=0:100[out]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]", "-ar", "44100", "-ac", "1", out]
    subprocess.run(cmd, check=True)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "build", "mix.wav"))
