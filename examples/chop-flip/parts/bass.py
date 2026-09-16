"""Custom NumPy 808, inspired by the n808 production role in Music Agent OS."""

import numpy as np

BASS_DRIVE = 2.4


def synth_808(
    *, sample_rate: int, midi: int, duration_seconds: float, drive: float
) -> np.ndarray:
    t = np.arange(round(duration_seconds * sample_rate), dtype=np.float32) / sample_rate
    frequency = 440.0 * 2 ** ((midi - 69) / 12)
    # A short pitch drop and a restrained tanh drive are source-owned sound design.
    instantaneous = frequency * (1 + 0.095 * np.exp(-t / 0.025))
    phase = 2 * np.pi * np.cumsum(instantaneous) / sample_rate
    envelope = np.minimum(1.0, t / 0.008) * np.exp(-2.5 * t)
    return (0.42 * np.tanh(np.sin(phase) * drive) / np.tanh(drive) * envelope).astype(
        np.float32
    )


def add_bass(project, *, gain_db: float = -4.5) -> None:
    track = project.track("bass", gain_db=gain_db)
    roots = [36, 36, 33, 31, 36, 39, 31, 36]
    for bar, midi in enumerate(roots):
        audio = project.compute(
            f"808-{bar}",
            synth_808,
            params={"midi": midi, "duration_seconds": 0.85, "drive": BASS_DRIVE},
        )
        track.place(f"bass-{bar}", audio, at_beats=bar * 4 + 0.03, gain_db=-3)
