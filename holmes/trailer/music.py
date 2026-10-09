"""An original score for the trailer, synthesised from scratch (no samples): python3 trailer/music.py out.wav

A slow Victorian waltz in D minor (3/4, 80 bpm): a string pad, plucked strings (Karplus-Strong) on the waltz beats, a
bowed melody, and a lift into F major for the results before a final D major chord. Sections follow trailer.html."""
import math
import random
import struct
import sys
import wave

SR, DUR = 44100, 95.0
N = int(SR * DUR)
buf = [0.0] * N
rnd = random.Random(7)
BEAT = 0.75
BAR = 3 * BEAT


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def add(t0, samples, gain):
    i0 = int(t0 * SR)
    for k, v in enumerate(samples):
        j = i0 + k
        if 0 <= j < N:
            buf[j] += v * gain


def pluck(m, dur=1.6, bright=0.5):
    """Karplus-Strong plucked string."""
    p = max(2, int(SR / hz(m)))
    ring = [rnd.uniform(-1, 1) for _ in range(p)]
    out, i, n = [], 0, int(dur * SR)
    for k in range(n):
        a = ring[i % p]
        b = ring[(i + 1) % p]
        ring[i % p] = (bright * a + (1 - bright) * b) * 0.996
        out.append(a * min(1.0, (n - k) / (0.05 * SR)))
        i += 1
    return out


def bowed(m, dur, vib=5.5):
    """A soft bowed tone: a few harmonics, slow attack, vibrato."""
    n, out, ph, f0 = int(dur * SR), [], 0.0, hz(m)
    att, rel = min(0.25, dur / 3), min(0.4, dur / 2)
    for k in range(n):
        t = k / SR
        f = f0 * (1 + 0.004 * math.sin(2 * math.pi * vib * t) * min(1, t / 0.3))
        ph += 2 * math.pi * f / SR
        env = min(1.0, t / att, (dur - t) / rel)
        out.append(env * (math.sin(ph) + 0.45 * math.sin(2 * ph) + 0.25 * math.sin(3 * ph) + 0.12 * math.sin(4 * ph)))
    return out


def pad(ms, t0, dur):
    """A string pad: each chord note as two slightly detuned bowed tones."""
    for m in ms:
        for det in (-0.06, 0.06):
            add(t0, bowed(m + det, dur + 0.3, vib=4.0), 0.035)


def timp(t0, g=0.5):
    n = int(1.4 * SR)
    add(t0, [math.sin(2 * math.pi * (52 - 10 * k / n) * k / SR) * math.exp(-3.2 * k / SR) for k in range(n)], g)


MINOR = [[50, 53, 57], [46, 50, 53], [43, 46, 50], [45, 49, 52]]     # Dm  Bb  Gm  A
MAJOR = [[41, 45, 48], [48, 52, 55], [50, 53, 57], [46, 50, 53]]     # F   C   Dm  Bb
TUNE_A = [[(69, 2), (65, 1)], [(70, 2), (74, 1)], [(67, 1.5), (70, 1.5)], [(69, 2), (73, 1)]]
TUNE_B = [[(74, 2), (72, 1)], [(70, 2), (69, 1)], [(67, 2), (70, 1)], [(69, 3)]]
TUNE_M = [[(72, 2), (69, 1)], [(67, 2), (72, 1)], [(74, 2), (72, 1)], [(70, 3)]]


def section(t0, t1, chords, waltz=True, harp=False, tunes=None, level=1.0):
    t, bar = t0, 0
    while t + 0.01 < t1:
        ch = chords[bar % 4]
        pad(ch, t, min(BAR, t1 - t))
        if waltz:
            add(t, pluck(ch[0], 0.8, 0.7), 0.16 * level)                         # a light bass on one
            for b in (1, 2):
                for m in ch:
                    add(t + b * BEAT, pluck(m, 0.9, 0.35), 0.10 * level)          # chord on two and three
        if harp:
            for i, m in enumerate([ch[0], ch[1], ch[2], ch[0] + 12, ch[2], ch[1]]):
                add(t + i * BEAT / 2, pluck(m + 12, 1.4, 0.6), 0.09 * level)
        if tunes:
            tune = tunes[(bar // 4) % len(tunes)][bar % 4]
            s = t
            for m, beats in tune:
                add(s, bowed(m, beats * BEAT * 0.98), 0.05 * level)
                s += beats * BEAT
        t += BAR
        bar += 1


section(0.0, 16.0, MINOR, waltz=False, harp=True, level=0.8)                  # Baker Street, the quotes
section(16.0, 25.0, MINOR, waltz=True, level=0.8)                             # the experiment
section(25.0, 77.0, MINOR, waltz=True, tunes=[TUNE_A, TUNE_B], level=0.9)      # the three chapters
section(77.0, 92.5, MAJOR, waltz=True, harp=True, tunes=[TUNE_M], level=1.0)   # the results
pad([50, 54, 57, 62], 92.5, 2.4)                                              # a final D major chord
add(92.5, pluck(50, 2.0, 0.7), 0.2)
for t in (25.0, 41.0, 59.0, 77.0):
    timp(t, 0.12)

# fade out the last second
for k in range(int(SR * 1.2)):
    buf[N - 1 - k] *= k / (SR * 1.2)
peak = max(1e-9, max(abs(v) for v in buf))
with wave.open(sys.argv[1] if len(sys.argv) > 1 else "music.wav", "w") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(b"".join(struct.pack("<h", int(32767 * 0.8 * v / peak)) for v in buf))
