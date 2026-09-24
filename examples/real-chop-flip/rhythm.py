"""Source-owned drum patterns and bass notes; no framework taste or mix rules."""

import numpy as np
from chops import ORDER
from scipy.signal import butter, sosfilt

# Authored provisional notes, informed by existing source transcription around 54–68 s.
# They are musical choices to audition, not automatically inferred ground truth.
ROOTS = ((29, 28), (28, 28), (29, 33), (33, 33))


def kick_positions(bar: int) -> tuple[float, ...]:
    return (0, 1.75, 2.5) if bar % 2 == 0 else (0, 2.5, 3.5)


def place(out: np.ndarray, sound: np.ndarray, at: int, gain: float = 1) -> None:
    end = min(len(out), at + len(sound))
    out[at:end] += sound[: end - at] * gain


def drums(rate: int, beat: int, frames: int) -> np.ndarray:
    rng = np.random.default_rng(20260924)
    t = np.arange(round(0.32 * rate)) / rate
    kick = 0.6 * np.sin(2 * np.pi * (52 * t + 1.8 * (1 - np.exp(-t / 0.018))))
    kick *= (1 - np.exp(-1800 * t)) * np.exp(-20 * t)
    t = np.arange(round(0.22 * rate)) / rate
    noise = rng.normal(0, 1, len(t))
    noise = sosfilt(butter(2, [900, 8500], "bandpass", fs=rate, output="sos"), noise)
    snare = (noise * 0.19 + 0.13 * np.sin(2 * np.pi * 185 * t)) * np.exp(-24 * t)
    t = np.arange(round(0.08 * rate)) / rate
    noise = sosfilt(butter(2, 6500, "highpass", fs=rate, output="sos"), rng.normal(0, 1, len(t)))
    hat = noise * 0.075 * np.exp(-70 * t)
    out = np.zeros(frames, dtype=np.float32)
    for bar in range(8):
        start = bar * 4 * beat
        for position in kick_positions(bar):
            place(out, kick, start + round(position * beat))
        for position in (1, 3):
            place(out, snare, start + position * beat + round(0.007 * rate))
        for eighth in range(8):
            late = round(0.012 * rate) if eighth % 2 else 0
            place(out, hat, start + round(eighth * beat / 2) + late, 0.65 if eighth % 2 else 1)
    return np.column_stack((out, out))


def bass(rate: int, beat: int, frames: int) -> np.ndarray:
    out = np.zeros(frames, dtype=np.float32)
    for bar, selected in enumerate(ORDER):
        for position in kick_positions(bar):
            # Leave the reverse pickup clear in the last half beat.
            if bar == 7 and position >= 3.5:
                continue
            midi = ROOTS[selected][0 if position < 1.6 else 1]
            seconds = (1.25 if position == 0 else 0.55) * beat / rate
            t = np.arange(round(seconds * rate)) / rate
            frequency = 440 * 2 ** ((midi - 69) / 12)
            phase = 2 * np.pi * np.cumsum(frequency * (1 + 0.08 * np.exp(-t / 0.025))) / rate
            envelope = np.minimum(t / 0.008, 1) * np.exp(-3.5 * t)
            envelope[-round(0.025 * rate) :] *= np.linspace(1, 0, round(0.025 * rate))
            note = 0.4 * np.tanh(1.8 * np.sin(phase)) / np.tanh(1.8) * envelope
            at = bar * 4 * beat + round(position * beat) + round(0.015 * rate)
            place(out, note, at, 1 if position == 0 else 0.7)
    out = sosfilt(butter(2, [25, 180], "bandpass", fs=rate, output="sos"), out)
    return np.column_stack((out, out)).astype(np.float32)
