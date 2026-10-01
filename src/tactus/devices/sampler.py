"""Sampler: play one recording as a pitched instrument (in the manner of Simpler).

Self-contained: copy this file into a work and change it freely. Samples are mono
`(frames,)` or `(frames, channels)` arrays at the work's sample rate. Repitching
resamples with linear interpolation, so higher notes are shorter and brighter and
very high transpositions alias; nothing here time-stretches.

Reads: numpy · tactus.timing.frame_of
"""

from __future__ import annotations

import numpy as np

from tactus.timing import frame_of

__all__ = ["note", "play"]


def _read(sample, positions):
    """Linear interpolation of `sample` at fractional frame `positions`; silence outside."""
    index = np.arange(len(sample))
    if sample.ndim == 1:
        return np.interp(positions, index, sample, left=0.0, right=0.0)
    return np.stack(
        [np.interp(positions, index, sample[:, c], left=0.0, right=0.0) for c in range(sample.shape[1])],
        axis=1,
    )


def note(
    sample,
    sample_rate,
    pitch,
    duration_s,
    velocity=1.0,
    *,
    root=60.0,
    start_s=0.0,
    loop=None,
    xfade_s=0.02,
    attack_s=0.005,
    release_s=0.08,
):
    """One note: `sample` transposed from `root` to `pitch` (MIDI numbers, fractions allowed).

    `root` is the pitch the recording actually sounds at; measure it when unsure (a
    sample named "C" may sit tens of cents away). `start_s` skips into the source, e.g.
    past an unpitched onset. Without `loop` the note ends when the source does.
    `loop=(start_s, end_s)` in source seconds sustains by repeating that region; each
    wrap crossfades over `xfade_s` into the material just before the loop start, so
    choose a region that begins at least `xfade_s` into the source and covers whole
    periods of a steady tone. The result lasts `duration_s + release_s`: linear attack,
    full level until `duration_s`, linear release. `velocity` scales amplitude linearly.
    """
    sample = np.asarray(sample, dtype=np.float64)
    if sample.ndim not in (1, 2) or not len(sample):
        raise ValueError("sample must be a nonempty (frames,) or (frames, channels) array")
    if duration_s <= 0 or attack_s < 0 or release_s < 0 or start_s < 0:
        raise ValueError("duration_s must be positive; attack_s, release_s and start_s nonnegative")
    rate = 2.0 ** ((pitch - root) / 12.0)
    frames = frame_of(duration_s + release_s, sample_rate)
    positions = start_s * sample_rate + np.arange(frames) * rate
    if loop is None:
        out = _read(sample, positions)
    else:
        a, b = (float(t) * sample_rate for t in loop)
        if not 0 <= a < b <= len(sample):
            raise ValueError("loop must satisfy 0 <= start_s < end_s <= sample length")
        span = b - a
        fade = min(xfade_s * sample_rate, a, span)
        looped = np.where(positions < b, positions, a + np.mod(positions - a, span))
        out = _read(sample, looped)
        if fade > 0:
            weight = np.clip((looped - (b - fade)) / fade, 0.0, 1.0)
            before = _read(sample, looped - span)
            if sample.ndim == 2:
                weight = weight[:, None]
            out = (1.0 - weight) * out + weight * before
    time = np.arange(frames) / sample_rate
    envelope = np.ones(frames)
    if attack_s > 0:
        envelope = np.minimum(envelope, time / attack_s)
    if release_s > 0:
        envelope = np.minimum(envelope, np.clip((duration_s + release_s - time) / release_s, 0.0, 1.0))
    else:
        envelope = envelope * (time < duration_s)
    if sample.ndim == 2:
        envelope = envelope[:, None]
    return out * envelope * velocity


def play(sample, sample_rate, notes, *, frames, **settings):
    """Render a whole part: `notes` are `(start_s, pitch, duration_s, velocity)` tuples.

    Each note is made by `note(..., **settings)` and added at `frame_of(start_s)`; notes
    overlap freely and anything past `frames` is cut. Returns `(frames,)` for a mono
    sample or `(frames, channels)` otherwise.
    """
    sample = np.asarray(sample, dtype=np.float64)
    out = np.zeros((frames,) + sample.shape[1:])
    for start_s, pitch, duration_s, velocity in notes:
        begin = frame_of(start_s, sample_rate)
        if begin >= frames or begin < 0:
            continue
        sound = note(sample, sample_rate, pitch, duration_s, velocity, **settings)
        end = min(frames, begin + len(sound))
        out[begin:end] += sound[: end - begin]
    return out
