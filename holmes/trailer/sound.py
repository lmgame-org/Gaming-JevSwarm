"""Synthesise the trailer's soundtrack (original, no samples): python3 trailer/sound.py out.wav

A low string-like drone, a clock that ticks through each chapter, telegraph clicks while the telegram types, a bell
toll for each of the three chapters, a heartbeat under the twist and a closing chord. Times match trailer.html."""
import math
import os
import random
import struct
import sys
import wave

SR, DUR = 44100, 96.0
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


def bell(t, f=196.0, g=0.35):  # inharmonic partials, long decay
    for mult, amp, dec in ((1, 1.0, 1.2), (2.0, 0.5, 1.8), (2.76, 0.35, 2.4), (5.4, 0.2, 3.5)):
        add(t, tone(f * mult, 3.5, decay=dec), g * amp)


def tick(t, g=0.16):
    add(t, noise(0.012, decay=500, lp=0.05), g)
    add(t, tone(2400, 0.02, decay=200), g * 0.4)


def heartbeat(t, g=0.6):
    add(t, tone(58, 0.25, decay=14, f_end=40), g)
    add(t + 0.16, tone(52, 0.25, decay=16, f_end=38), g * 0.7)


if not os.environ.get('NO_PAD'):
    pad(0.0, 16.0, [55, 82.4, 110, 130.8], 0.09)
if not os.environ.get('NO_PAD'):
    pad(16.0, 25.0, [61.7, 92.5, 123.5, 146.8], 0.07)
if not os.environ.get('NO_PAD'):
    pad(25.0, 77.0, [65.4, 98, 130.8, 155.6], 0.06)
if not os.environ.get('NO_PAD'):
    pad(77.0, 96.0, [65.4, 98, 130.8, 164.8, 196], 0.07)
for a, b in ((0.3, 5.0), (27.6, 38.8), (45.6, 56.8), (63.6, 73.4), (77.0, 92.0)):
    t = a
    while t < b:
        tick(t, 0.16 if int(round((t - a) * 2)) % 2 == 0 else 0.1)
        t += 0.5
t = 5.0
while t < 10.5:  # running footsteps under the Irregulars
    add(t, noise(0.03, decay=120, lp=0.4), 0.12)
    t += 0.18 + rnd.random() * 0.08
bell(10.5, 293.7, 0.2)
bell(14.0, 196.0, 0.22)
bell(16.0, 246.9, 0.2)
for t in (25.0, 43.0, 61.0):
    bell(t)
for t in (38.8, 56.8, 74.2):  # each verdict lands
    bell(t, 523.3, 0.16)
bell(84.0, 349.2, 0.18)
bell(92.0, 130.8, 0.45)
add(92.0, tone(65.4, 2.5, decay=0.9), 0.25)

peak = max(1e-9, max(abs(v) for v in buf))
with wave.open(sys.argv[1] if len(sys.argv) > 1 else "sound.wav", "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(b"".join(struct.pack("<h", int(32767 * 0.85 * v / peak)) for v in buf))
