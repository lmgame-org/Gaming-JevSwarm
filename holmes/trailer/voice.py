"""Narration for the trailer: OpenAI text-to-speech, one clip per line, cached in trailer/voice/ (python3 trailer/voice.py).
The key file is read at call time (swarmcore.keys) and never printed."""
import json
import os
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "common"))
from swarmcore.keys import CHAT_KEY_CANDIDATES, first_key  # noqa: E402

VOICE, MODEL = "onyx", "gpt-4o-mini-tts"
STYLE = ("Narrate a film trailer for a Victorian detective mystery. Deep, calm, British, measured and slightly "
         "theatrical; leave small pauses between sentences.")
# (start time in the trailer, file stem, text). Each clip must end before the next starts.
LINES = [
    (0.6, "01_london", "London. Eighteen ninety."),
    (5.3, "02_secret", "Holmes's secret was never one mind."),
    (10.8, "03_ai", "One genius, or many minds? Astra, or a swarm of Jev?"),
    (16.9, "04_setup", "We sent AI to Baker Street. A hundred murders. Find the culprit, the motive, and the hideout."),
    (27.8, "05_lone", "First, the lone genius. One brilliant model, one door at a time."),
    (38.9, "06_unsolved", "Unsolved."),
    (45.8, "07_holmes", "Next, Holmes and his Irregulars. Holmes thinks. Twelve small, quick boys run the errands."),
    (56.9, "08_solved", "Solved."),
    (63.8, "09_swarm", "Finally, the Jev swarm. A hundred boys, no leader. They vote."),
    (74.3, "10_wrong", "Unsolved. The wrong man."),
    (78.0, "11_casebook", "Across a hundred cases, Holmes and his Irregulars solve ninety-six."),
    (84.3, "12_lies", "Then somebody lies. Astra, leading the Jev swarm, sees through it. Counting gets almost none right."),
]


def tts(text, out):
    key = open(os.path.expanduser(first_key(CHAT_KEY_CANDIDATES))).read().strip()
    body = json.dumps({"model": MODEL, "voice": VOICE, "input": text, "instructions": STYLE, "response_format": "wav"}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/audio/speech", data=body,
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as f:
        f.write(r.read())


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                capture_output=True, text=True).stdout)


def main():
    meta = []
    for i, (t, stem, text) in enumerate(LINES):
        out = os.path.join(HERE, "voice", stem + ".wav")
        if not os.path.exists(out):
            tts(text, out)
        d = duration(out)
        nxt = LINES[i + 1][0] if i + 1 < len(LINES) else 96.0
        meta.append({"t": t, "file": out, "dur": round(d, 2), "fits": t + d <= nxt - 0.2})
        print(f"{t:5.1f}s {d:4.1f}s {'ok ' if t + d <= nxt - 0.2 else 'LONG'} {text}")
    with open(os.path.join(HERE, "voice", "lines.json"), "w") as f:
        json.dump(meta, f, indent=1)


if __name__ == "__main__":
    main()
