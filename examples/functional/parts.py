"""Ordinary musical functions for a short free-time study; all choices are authored here."""

import numpy as np

RATE = 24_000


def pluck(hz: float, seconds: float) -> np.ndarray:
    t = np.arange(round(seconds * RATE)) / RATE
    envelope = (1 - np.exp(-80 * t)) * np.exp(-3 * t)
    return (
        0.3 * envelope * (np.sin(2 * np.pi * hz * t) + 0.2 * np.sin(4 * np.pi * hz * t))
    ).astype(np.float32)


def bass() -> np.ndarray:
    audio = np.zeros(3 * RATE, dtype=np.float32)
    for start, hz in [(0.0, 110), (0.85, 146.83), (1.9, 130.81)]:
        note = pluck(hz, 1.0)
        at = round(start * RATE)
        audio[at : at + len(note)] += note
    return audio


def texture() -> np.ndarray:
    t = np.arange(3 * RATE) / RATE
    envelope = np.sin(np.pi * t / 3) ** 2
    left = 0.08 * envelope * np.sin(2 * np.pi * 329.63 * t)
    right = 0.08 * envelope * np.sin(2 * np.pi * 392 * t)
    return np.column_stack((left, right)).astype(np.float32)
