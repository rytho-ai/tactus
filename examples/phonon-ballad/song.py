"""An original, deterministic instrumental pop ballad inspired by a reference's arc.

The reference recording is never sampled, imported, or used by this renderer.
Run with: uv run python examples/phonon-ballad/song.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import soundfile as sf

RATE = 32_000
BPM = 120
BEAT = 60.0 / BPM
BAR = 4 * BEAT
SEED = 41377
OUT = Path(__file__).resolve().parents[2] / "dist" / "phonon-ballad"

SECTIONS = [
    ("intro", 4),
    ("verse_1", 12),
    ("pre_1", 4),
    ("chorus_1", 8),
    ("interlude", 4),
    ("verse_2", 8),
    ("pre_2", 4),
    ("chorus_2", 8),
    ("bridge", 8),
    ("final_chorus", 8),
    ("outro", 8),
]

# Four-chord cycles are original to this piece. Chord tones are MIDI pitches.
VERSE = [
    ("Bm7", 47, (59, 62, 66, 69)),
    ("Gmaj7", 43, (55, 59, 62, 66)),
    ("Dadd9", 50, (57, 62, 66, 64)),
    ("Aadd9", 45, (57, 61, 64, 71)),
]
PRE = [
    ("Em7", 40, (52, 55, 59, 62)),
    ("Gmaj7", 43, (55, 59, 62, 66)),
    ("F#m7", 42, (54, 57, 61, 64)),
    ("Aadd9", 45, (57, 61, 64, 71)),
]
CHORUS = [
    ("Dadd9", 50, (57, 62, 66, 64)),
    ("A/C#", 49, (57, 61, 64, 69)),
    ("Bm7", 47, (59, 62, 66, 69)),
    ("Gmaj7", 43, (55, 59, 62, 66)),
    ("Em7", 40, (52, 55, 59, 62)),
    ("Gmaj7", 43, (55, 59, 62, 66)),
    ("Asus4", 45, (57, 62, 64, 69)),
    ("Aadd9", 45, (57, 61, 64, 71)),
]
BRIDGE = [
    ("Em7", 40, (52, 55, 59, 62)),
    ("Bm7", 47, (59, 62, 66, 69)),
    ("Gmaj7", 43, (55, 59, 62, 66)),
    ("Aadd9", 45, (57, 61, 64, 71)),
]


def hz(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def envelope(n: int, attack: float, release: float) -> np.ndarray:
    a = min(n, max(1, int(attack * RATE)))
    r = min(n, max(1, int(release * RATE)))
    env = np.ones(n, dtype=np.float32)
    env[:a] *= np.linspace(0, 1, a, dtype=np.float32)
    env[-r:] *= np.linspace(1, 0, r, dtype=np.float32)
    return env


def piano(midi: int, seconds: float) -> np.ndarray:
    n = max(1, int((seconds + 0.35) * RATE))
    t = np.arange(n, dtype=np.float32) / RATE
    f = hz(midi)
    wave = np.zeros(n, dtype=np.float32)
    for partial in range(1, 7):
        detune = 1 + 0.00012 * partial * partial
        decay = np.exp(-t * (1.1 + 0.53 * partial))
        wave += np.sin(2 * np.pi * f * partial * detune * t) * decay / partial**1.35
    hammer = np.sin(2 * np.pi * f * 8 * t) * np.exp(-t * 85) * 0.07
    return (wave + hammer) * envelope(n, 0.006, 0.18) * 0.17


def guitar(midi: int, seconds: float) -> np.ndarray:
    n = max(1, int((seconds + 0.15) * RATE))
    t = np.arange(n, dtype=np.float32) / RATE
    f = hz(midi)
    wave = np.zeros(n, dtype=np.float32)
    for partial in range(1, 8):
        wave += np.sin(2 * np.pi * f * partial * t + partial * 0.19) * np.exp(
            -t * (2.1 + partial * 0.74)
        ) / partial**1.1
    return wave * envelope(n, 0.003, 0.10) * 0.10


def strings(midi: int, seconds: float) -> np.ndarray:
    n = max(1, int((seconds + 0.6) * RATE))
    t = np.arange(n, dtype=np.float32) / RATE
    f = hz(midi)
    vibrato = 0.0023 * np.sin(2 * np.pi * 5.1 * t)
    phase = 2 * np.pi * f * (t + vibrato)
    wave = np.sin(phase) + 0.35 * np.sin(2.003 * phase) + 0.15 * np.sin(3.001 * phase)
    return wave.astype(np.float32) * envelope(n, 0.45, 0.55) * 0.055


def lead(midi: int, seconds: float) -> np.ndarray:
    n = max(1, int((seconds + 0.2) * RATE))
    t = np.arange(n, dtype=np.float32) / RATE
    f = hz(midi)
    vibrato = 0.0018 * np.sin(2 * np.pi * 5.4 * t) * np.clip((t - 0.25) * 3, 0, 1)
    phase = 2 * np.pi * f * (t + vibrato)
    wave = np.sin(phase) + 0.38 * np.sin(2 * phase) + 0.19 * np.sin(3 * phase)
    wave += 0.07 * np.sin(4 * phase)
    return wave.astype(np.float32) * envelope(n, 0.06, 0.19) * 0.13


def bass(midi: int, seconds: float) -> np.ndarray:
    n = max(1, int((seconds + 0.1) * RATE))
    t = np.arange(n, dtype=np.float32) / RATE
    phase = 2 * np.pi * hz(midi) * t
    wave = np.sin(phase) + 0.29 * np.sin(2 * phase) * np.exp(-t * 4)
    return wave.astype(np.float32) * np.exp(-t * 0.9) * envelope(n, 0.007, 0.10) * 0.20


def drum(kind: str, rng: np.random.Generator) -> np.ndarray:
    duration = {"kick": 0.34, "snare": 0.26, "hat": 0.09, "ride": 0.65}[kind]
    n = int(duration * RATE)
    t = np.arange(n, dtype=np.float32) / RATE
    if kind == "kick":
        phase = 2 * np.pi * (57 * t + 70 * (1 - np.exp(-t * 36)) / 36)
        return np.sin(phase) * np.exp(-t * 20) * 0.43
    noise = rng.standard_normal(n).astype(np.float32)
    noise -= np.convolve(noise, np.ones(23, dtype=np.float32) / 23, mode="same")
    if kind == "snare":
        tone = np.sin(2 * np.pi * 178 * t) * np.exp(-t * 17)
        return (0.22 * noise * np.exp(-t * 24) + 0.12 * tone).astype(np.float32)
    if kind == "ride":
        return (noise * np.exp(-t * 7) * 0.038).astype(np.float32)
    return (noise * np.exp(-t * 45) * 0.055).astype(np.float32)


def add(bus: np.ndarray, sound: np.ndarray, start: float, gain: float = 1.0, pan: float = 0) -> None:
    position = max(0, round(start * RATE))
    end = min(position + len(sound), len(bus))
    if end <= position:
        return
    angle = (pan + 1) * np.pi / 4
    bus[position:end, 0] += sound[: end - position] * gain * np.cos(angle)
    bus[position:end, 1] += sound[: end - position] * gain * np.sin(angle)


def section_at(bar: int) -> tuple[str, int, int]:
    cursor = 0
    for name, bars in SECTIONS:
        if cursor <= bar < cursor + bars:
            return name, bar - cursor, bars
        cursor += bars
    raise IndexError(bar)


def harmony(name: str, local_bar: int) -> tuple[str, int, tuple[int, ...]]:
    if name.startswith("pre"):
        return PRE[local_bar % len(PRE)]
    if "chorus" in name:
        return CHORUS[local_bar % len(CHORUS)]
    if name == "bridge":
        return BRIDGE[local_bar % len(BRIDGE)]
    return VERSE[local_bar % len(VERSE)]


VERSE_MELODY = [
    [(0.5, 1.0, 71), (2.0, 0.6, 69), (3.0, 0.8, 66)],
    [(0.2, 1.3, 67), (2.0, 0.7, 71), (3.0, 0.8, 69)],
    [(0.5, 0.8, 66), (1.5, 0.8, 69), (2.6, 1.0, 74)],
    [(0.0, 1.3, 73), (2.0, 1.7, 69)],
]
PRE_MELODY = [
    [(0, 1, 71), (1.5, 0.8, 74), (2.5, 1.1, 76)],
    [(0, 1.5, 74), (2, 1.6, 78)],
    [(0, 0.8, 76), (1, 0.8, 74), (2, 1.8, 73)],
    [(0, 1.5, 73), (2, 1.8, 76)],
]
CHORUS_MELODY = [
    [(0, 1.3, 74), (1.8, 0.8, 78), (2.9, 0.9, 76)],
    [(0, 1.9, 76), (2.3, 1.4, 73)],
    [(0, 1.8, 78), (2, 0.8, 76), (3, 0.8, 74)],
    [(0, 0.9, 71), (1.2, 2.3, 74)],
    [(0, 1.2, 76), (1.5, 0.8, 74), (2.5, 1.0, 71)],
    [(0.2, 1.5, 74), (2, 1.7, 79)],
    [(0, 1.1, 78), (1.5, 1.1, 76), (3, 0.7, 74)],
    [(0, 3.5, 73)],
]
BRIDGE_MELODY = [
    [(0, 1.8, 71), (2.2, 1.5, 74)],
    [(0, 1.5, 73), (2, 1.6, 71)],
    [(0, 1.2, 69), (1.6, 1.1, 71), (3, 0.8, 74)],
    [(0, 3.5, 76)],
]


def ambience(signal: np.ndarray, wet: float) -> np.ndarray:
    result = signal.copy()
    for seconds, gain, swap in [(0.093, 0.42, True), (0.167, 0.32, False),
                                (0.293, 0.22, True), (0.419, 0.14, False)]:
        offset = int(seconds * RATE)
        tail = signal[:-offset, ::-1] if swap else signal[:-offset]
        result[offset:] += tail * gain * wet
    return result


def render() -> dict:
    rng = np.random.default_rng(SEED)
    total_bars = sum(bars for _, bars in SECTIONS)
    frames = int((total_bars * BAR + 2) * RATE)
    buses = {name: np.zeros((frames, 2), dtype=np.float32)
             for name in ("piano", "guitar", "strings", "lead", "bass", "drums")}
    timeline = []
    for bar in range(total_bars):
        name, local, section_bars = section_at(bar)
        chord_name, root, notes = harmony(name, local)
        start = bar * BAR
        is_chorus = "chorus" in name
        is_pre = name.startswith("pre")
        is_verse = name.startswith("verse")
        timeline.append({"bar": bar + 1, "section": name, "chord": chord_name})

        # Broken-chord piano stays present as the intimate center of the mix.
        pattern = [0, 2, 1, 3, 0, 2, 1, 3]
        for step, index in enumerate(pattern):
            velocity = 0.78 if step % 4 else 1.0
            if is_chorus:
                velocity *= 1.12
            if name == "outro":
                velocity *= 0.70 * (1 - local / (section_bars + 2))
            velocity *= float(rng.uniform(0.93, 1.07))
            timing = float(rng.normal(0, 0.006))
            add(buses["piano"], piano(notes[index], 0.58),
                start + step * BEAT / 2 + timing, velocity, -0.24 + 0.48 * (step % 2))

        if name not in ("intro", "outro"):
            for beat, index in [(0.5, 1), (1.5, 2), (2.5, 3), (3.5, 1)]:
                add(buses["guitar"], guitar(notes[index] + 12, 0.38),
                    start + beat * BEAT, 0.67 if is_verse else 0.88, 0.46)

        if is_chorus or is_pre or name == "bridge" or name == "outro":
            pad_gain = 0.68 if is_pre else 1.0 if is_chorus else 0.57
            for index in (0, 1, 2):
                add(buses["strings"], strings(notes[index], BAR - 0.3),
                    start, pad_gain, [-0.65, 0.0, 0.65][index])

        if name not in ("intro", "interlude", "outro"):
            if is_chorus:
                phrase = CHORUS_MELODY[local % 8]
            elif is_pre:
                phrase = PRE_MELODY[local % 4]
            elif name == "bridge":
                phrase = BRIDGE_MELODY[local % 4]
            else:
                phrase = VERSE_MELODY[local % 4]
            for beat, length, pitch in phrase:
                # Small first-verse restraint; the final chorus is the emotional peak.
                gain = 0.70 if name == "verse_1" else 1.22 if name == "final_chorus" else 1.0
                add(buses["lead"], lead(pitch, length * BEAT),
                    start + beat * BEAT, gain, -0.06)
            if name == "final_chorus" and local in (0, 4):
                add(buses["guitar"], guitar(notes[2] + 12, 1.1 * BEAT),
                    start + 3 * BEAT, 0.95, 0.7)

        if name not in ("intro", "outro"):
            for beat, pitch, length in [(0, root, 1.35), (2, root + 7, 1.25)]:
                add(buses["bass"], bass(pitch, length * BEAT), start + beat * BEAT,
                    0.7 if is_verse else 1.0)

        # Half-time verse, wider backbeat in the chorus; never four-on-the-floor.
        if name not in ("intro", "outro", "interlude"):
            kick_beats = (0, 2.5) if is_verse or is_pre else (0, 2, 3.5)
            snare_beats = (2,) if is_verse or is_pre else (1, 3)
            for beat in kick_beats:
                add(buses["drums"], drum("kick", rng), start + beat * BEAT,
                    0.72 if is_verse else 1.0)
            for beat in snare_beats:
                add(buses["drums"], drum("snare", rng), start + beat * BEAT,
                    0.62 if is_verse else 0.95)
            for step in range(8):
                add(buses["drums"], drum("hat", rng), start + step * BEAT / 2,
                    0.34 if is_verse else 0.48, 0.35)
            if is_chorus and local in (0, 4):
                add(buses["drums"], drum("ride", rng), start, 1.0, -0.47)
            if (is_pre or name == "bridge") and local == section_bars - 1:
                for beat, gain in [(2.5, 0.28), (3.0, 0.38), (3.5, 0.55)]:
                    add(buses["drums"], drum("snare", rng), start + beat * BEAT,
                        gain, 0.12)

    buses["piano"] = ambience(buses["piano"], 0.36)
    buses["guitar"] = ambience(buses["guitar"], 0.28)
    buses["strings"] = ambience(buses["strings"], 0.44)
    buses["lead"] = ambience(buses["lead"], 0.62)
    outro_start = int((total_bars - SECTIONS[-1][1]) * BAR * RATE)
    outro_end = int(total_bars * BAR * RATE)
    fade = np.linspace(1, 0, outro_end - outro_start, dtype=np.float32)[:, None]
    for signal in buses.values():
        signal[outro_start:outro_end] *= fade

    # Source code, not a saved DAW state, defines every musical decision.
    mix = sum(buses.values())
    mix = np.tanh(mix * 1.25).astype(np.float32)
    mix *= 0.88 / max(float(np.max(np.abs(mix))), 1e-9)
    OUT.mkdir(parents=True, exist_ok=True)
    sf.write(OUT / "mix.wav", mix, RATE, subtype="PCM_24")
    for name, signal in buses.items():
        sf.write(OUT / f"{name}.wav", np.clip(signal, -1, 1), RATE, subtype="PCM_24")
    receipt = {
        "title": "The Space Between Replies",
        "tempo_bpm": BPM,
        "key": "D major / B minor",
        "duration_seconds": round(total_bars * BAR, 3),
        "rendered_duration_seconds": round(frames / RATE, 3),
        "seed": SEED,
        "reference_audio_used_in_render": False,
        "sections": SECTIONS,
        "timeline": timeline,
        "mix_sha256": hashlib.sha256((OUT / "mix.wav").read_bytes()).hexdigest(),
    }
    (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    print(json.dumps({k: v for k, v in render().items() if k != "timeline"}, indent=2))
