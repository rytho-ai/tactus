"""Long-phrase chops with a short turnaround, adapted from Music Agent OS."""

from __future__ import annotations

import numpy as np


def source_phrase(*, sample_rate: int, bpm: float) -> np.ndarray:
    """A redistributable synthetic four-bar source in place of the private crate."""
    seconds_per_bar = 240 / bpm
    length = round(4 * seconds_per_bar * sample_rate)
    audio = np.zeros((length, 2), dtype=np.float32)
    chords = ((261.63, 329.63, 392.0), (220.0, 261.63, 329.63),
              (174.61, 220.0, 261.63), (196.0, 246.94, 293.66))
    for bar, notes in enumerate(chords):
        start = round(bar * seconds_per_bar * sample_rate)
        end = round((bar + 1) * seconds_per_bar * sample_rate)
        t = np.arange(end - start, dtype=np.float32) / sample_rate
        envelope = np.minimum(1.0, t / 0.025) * np.exp(-0.55 * t)
        chord = sum(np.sin(2 * np.pi * frequency * t) for frequency in notes) / 3
        audio[start:end, 0] = 0.16 * chord * envelope
        audio[start:end, 1] = 0.14 * chord * envelope
    return audio


def _fit(audio: np.ndarray, frames: int) -> np.ndarray:
    """Simple resampling for this equal-tempo fixture; not RubberBand's pitch-preserving warp."""
    x = np.linspace(0, len(audio) - 1, frames)
    old = np.arange(len(audio))
    return np.column_stack([np.interp(x, old, audio[:, channel]) for channel in range(2)])


def chop_rearrange(source: np.ndarray, *, sample_rate: int, bpm: float) -> np.ndarray:
    bar_frames = round(240 / bpm * sample_rate)
    output = np.zeros((bar_frames * 8, 2), dtype=np.float32)
    order = [0, 1, 2, 3, 2, 3, 0]
    for bar, source_bar in enumerate(order):
        part = source[source_bar * bar_frames : (source_bar + 1) * bar_frames]
        output[bar * bar_frames : (bar + 1) * bar_frames] = _fit(part, bar_frames)

    # Preserve the phrase until the final bar; use only the turnaround for smaller grains.
    final = output[7 * bar_frames :]
    half = bar_frames // 2
    final[:half] = _fit(source[3 * bar_frames : 3 * bar_frames + half], half)
    grain = source[3 * bar_frames + half : 3 * bar_frames + half + bar_frames // 8]
    for index in range(4):
        start = half + index * (bar_frames - half) // 4
        end = half + (index + 1) * (bar_frames - half) // 4
        final[start:end] = _fit(grain[::-1] if index == 3 else grain, end - start)
    return output


def add_chops(project, *, gain_db: float = -4.5) -> None:
    source = project.compute(
        "source-phrase", source_phrase, params={"bpm": project.bpm}
    )
    chops = project.compute(
        "chops", chop_rearrange, inputs={"source": source}, params={"bpm": project.bpm}
    )
    project.track("sample", gain_db=gain_db).place(
        "sample-form", chops, at_beats=0, duration_beats=project.total_beats
    )
