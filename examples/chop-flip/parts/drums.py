"""A small reusable drum bed; the framework does not own its pattern."""

from __future__ import annotations

import numpy as np


def kick(*, sample_rate: int) -> np.ndarray:
    t = np.arange(round(0.3 * sample_rate), dtype=np.float32) / sample_rate
    phase = 2 * np.pi * (52 * t + 46 * 0.025 * (1 - np.exp(-t / 0.025)))
    return (0.55 * np.sin(phase) * np.exp(-19 * t)).astype(np.float32)


def hat(*, sample_rate: int, seed: int) -> np.ndarray:
    t = np.arange(round(0.09 * sample_rate), dtype=np.float32) / sample_rate
    noise = np.random.default_rng(seed).normal(0, 1, len(t)).astype(np.float32)
    return 0.085 * noise * np.exp(-55 * t)


def add_drums(project, *, gain_db: float = -4.0) -> None:
    kick_audio = project.compute("kick-sound", kick)
    hat_audio = project.compute("hat-sound", hat, params={"seed": 710})
    track = project.track("drums", gain_db=gain_db)
    for bar in range(project.bars):
        for beat in (0, 2):
            track.place(f"kick-{bar}-{beat}", kick_audio, at_beats=bar * 4 + beat)
        for beat in (1, 3):
            track.place(
                f"hat-{bar}-{beat}", hat_audio, at_beats=bar * 4 + beat, gain_db=-4
            )
