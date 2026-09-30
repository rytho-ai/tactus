"""Deterministic demo material; shared only to compare transformations on one phrase."""

import numpy as np


def phrase(sample_rate=24000):
    t = np.arange(6 * sample_rate) / sample_rate
    segment = np.minimum((t / 0.75).astype(int), 7)
    notes = np.array([220, 261.6256, 329.6276, 293.6648, 220, 391.9954, 329.6276, 261.6256])
    phase = np.cumsum(notes[segment]) / sample_rate
    amplitudes = np.array([0.2, 0.6, 0.3, 1.0, 0.25, 0.8, 0.4, 0.65])
    local = t % 0.75
    envelope = (1 - np.exp(-local * 250)) * np.exp(-local * 4)
    tone = sum(np.sin(2 * np.pi * k * phase) / k for k in range(1, 9))
    x = 0.18 * tone * envelope * amplitudes[segment]
    fade = min(240, len(x) // 2)
    x[-fade:] *= np.linspace(1, 0, fade)
    return x.astype(np.float32), sample_rate
