"""Synthesise the trailer's soundtrack (original, no samples): python3 trailer/sound.py out.wav

A low pulse that builds through the acts, typewriter clicks while text types, hits on the splashes, thuds for the
stamps, a gavel for the verdict and a rising sweep before "Objection!". Times match trailer.html."""
import math
import random
import struct
import sys
import wave

SR, DUR = 44100, 45.0
N = int(SR * DUR)
buf = [0.0] * N
rnd = random.Random(1)


def add(t0, samples, gain=1.0):
    i0 = int(t0 * SR)
    for k, v in enumerate(samples):
        if 0 <= i0 + k < N:
            buf[i0 + k] += v * gain


def tone(freq, dur, decay=6.0, shape=math.sin, f_end=None):
    n = int(dur * SR)
    out, ph = [], 0.0
    for k in range(n):
        f = freq if f_end is None else freq + (f_end - freq) * k / n
        ph += 2 * math.pi * f / SR
        out.append(shape(ph) * math.exp(-decay * k / SR))
    return out


def noise(dur, decay=20.0, lp=0.5):
    n, y, out = int(dur * SR), 0.0, []
    for k in range(n):
        y = lp * y + (1 - lp) * (rnd.random() * 2 - 1)
        out.append(y * math.exp(-decay * k / SR))
    return out


def kick(t, g=0.9):
    add(t, tone(110, 0.35, decay=9, f_end=42), g)


def click(t, g=0.18):
    add(t, noise(0.018, decay=300, lp=0.1), g)


def hit(t, g=1.0):  # splash: boom + crash
    add(t, tone(70, 1.2, decay=3.5, f_end=38), g)
    add(t, noise(0.9, decay=5, lp=0.2), 0.55 * g)
    add(t, tone(880, 0.5, decay=8), 0.12 * g)


def thud(t, g=0.9):
    add(t, tone(90, 0.4, decay=12, f_end=50), g)
    add(t, noise(0.12, decay=40, lp=0.6), 0.5 * g)


def typing(a, b, rate=16):
    t = a
    while t < b:
        click(t, 0.12 + rnd.random() * 0.08)
        t += (0.6 + rnd.random() * 0.8) / rate


def pad(a, b, freqs, g=0.06):  # a soft chord bed
    n = int((b - a) * SR)
    out = []
    for k in range(n):
        tt = k / SR
        env = min(1.0, tt / 0.6, (b - a - tt) / 0.6)
        out.append(env * sum(math.sin(2 * math.pi * f * tt) for f in freqs) / len(freqs))
    add(a, out, g)


# the beds: minor, darker for the Holmesian case, major lift for the verdict
pad(0.0, 4.0, [55, 82.4, 110], 0.10)
pad(5.2, 21.0, [65.4, 98, 130.8, 155.6], 0.05)
pad(22.0, 35.7, [61.7, 92.5, 123.5, 146.8], 0.06)
pad(37.0, 45.0, [65.4, 98, 130.8, 164.8], 0.06)
# pulse: sparse, then steady, then driving through the cross-examination
for a, b, step in ((5.2, 15.5, 0.75), (15.5, 21.0, 0.5), (24.0, 34.2, 0.375), (37.0, 42.2, 0.5)):
    t = a
    while t < b:
        kick(t, 0.55)
        t += step
# typing
typing(0.3, 2.6, 30)
for a in (25.8, 26.95, 28.1):
    typing(a, a + 0.9, 22)
typing(29.4, 30.2, 22)
typing(31.3, 34.0, 26)
# splashes, stamps, gavel, sweep
for t in (4.0, 21.0, 35.7):
    hit(t)
add(34.6, tone(200, 1.1, decay=0.5, f_end=1400), 0.08)
thud(30.25)
thud(42.2)
for k in range(3):
    thud(37.0 + k * 0.18, 0.8)
add(43.1, tone(65.4, 1.9, decay=1.2), 0.25)

peak = max(1e-9, max(abs(v) for v in buf))
with wave.open(sys.argv[1] if len(sys.argv) > 1 else "sound.wav", "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(b"".join(struct.pack("<h", int(32767 * 0.85 * v / peak)) for v in buf))
