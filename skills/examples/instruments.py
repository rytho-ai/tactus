"""Acoustic piano through synth; no external instruments or assets."""

import numpy as np

from tactus import synth


def render(*, piano_family="felt"):
    rate, seconds = 24000, 6
    frames = rate * seconds
    notes = [
        (0, 50, 0.5, 0.65),
        (0.5, 57, 0.5, 0.5),
        (1, 62, 0.5, 0.75),
        (1.5, 65, 0.5, 0.55),
        (2, 48, 0.5, 0.65),
        (2.5, 55, 0.5, 0.5),
        (3, 60, 0.5, 0.75),
        (3.5, 64, 0.5, 0.55),
    ]
    keys = synth.piano(
        notes,
        rate,
        frames=frames,
        seed="keys-a",
        family=piano_family,
        pedal=[(0, "down"), (1.9, "up"), (2, "down"), (4.5, "up")],
    )
    # Explicit gain; the source model does not normalize or add effects.
    keys = keys * 2.5
    mix = keys * 0.7
    mix[-600:] *= np.linspace(1, 0, 600)[:, None]
    return {"sample_rate": rate, "outputs": {"piano": keys, "mix": mix}}
