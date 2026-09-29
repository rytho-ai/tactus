"""Compare whole-clip LR4 band processing and two ways of retiming an echo.

Reads: NumPy and tactus.dsp; no external assets. A deterministic synthesized source
feeds separate comparisons. Outputs preserve the actual processing gain.
"""

import numpy as np

from tactus import dsp


def make_source(sample_rate):
    t = np.arange(8 * sample_rate) / sample_rate
    notes = np.array([110.0, 130.8128, 164.8138, 146.8324])
    frequency = notes[(t // 0.5).astype(int) % len(notes)]
    phase = np.cumsum(frequency) / sample_rate
    tone = sum(np.sin(2 * np.pi * k * phase) / k for k in range(1, 9))
    beat = t % 0.5
    kick = np.sin(2 * np.pi * (48 * beat + 2 * (1 - np.exp(-beat / 0.025))))
    kick *= np.exp(-beat / 0.065)
    rng = np.random.default_rng(20260929)
    hats = rng.normal(size=len(t)) * np.exp(-(t % 0.25) / 0.01)
    mono = 0.09 * tone * (0.3 + 0.7 * np.exp(-beat / 0.15)) + 0.12 * kick + 0.02 * hats
    return dsp.pan(dsp.fade(mono, sample_rate, in_s=0.01, out_s=0.08))


def split_and_drive(dry, sample_rate, cutoff_hz, drive_db):
    low, high = dsp.crossover(dry, sample_rate, cutoff_hz=cutoff_hz)
    recombined = low + high
    high_drive = low + dsp.saturate(high, sample_rate, drive_db=drive_db, mix=0.4)
    full_drive = dsp.saturate(recombined, sample_rate, drive_db=drive_db, mix=0.4)
    return {"recombined": recombined, "high_drive": high_drive, "full_drive": full_drive}


def delay_controls(frames, sample_rate, crossfade_seconds):
    targets = np.array([0.125, 0.25, 0.375, 0.125])
    step = targets[np.minimum(np.arange(frames) // (2 * sample_rate), 3)]
    moving = step.copy()
    transition = max(1, round(crossfade_seconds * sample_rate))
    for index in range(1, len(targets)):
        start = index * 2 * sample_rate
        count = min(transition, frames - start, 2 * sample_rate)
        moving[start : start + count] = np.linspace(targets[index - 1], targets[index], count)
    return step, moving


def compare_echoes(dry, sample_rate, crossfade_seconds):
    step, moving = delay_controls(len(dry), sample_rate, crossfade_seconds)
    crossfade = dsp.crossfade_delay(
        dry,
        sample_rate,
        delay_seconds=step,
        feedback=0,
        tail_seconds=0.5,
        crossfade_seconds=crossfade_seconds,
    )
    glide = dsp.delay(dry, sample_rate, delay_seconds=moving, feedback=0, tail_seconds=0.5)
    padded_dry = np.pad(dry, ((0, len(crossfade) - len(dry)), (0, 0)))
    return {
        "crossfade_echo": 0.65 * padded_dry + 0.35 * crossfade,
        "gliding_echo": 0.65 * padded_dry + 0.35 * glide,
    }


def render(*, cutoff_hz=1000.0, crossfade_seconds=0.05, drive_db=12.0):
    sample_rate = 48000
    dry = make_source(sample_rate)
    bands = split_and_drive(dry, sample_rate, cutoff_hz, drive_db)
    echoes = compare_echoes(dry, sample_rate, crossfade_seconds)
    return {"sample_rate": sample_rate, "outputs": {"dry": dry, **bands, **echoes}}
