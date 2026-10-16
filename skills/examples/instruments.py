"""Acoustic piano and bowed string through synth; no external instruments or assets."""

import numpy as np

from tactus import dsp, synth


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
    string = synth.bowed_string(
        293.664767917,
        rate,
        frames=frames,
        hold_s=1.5,
        seed=17,
        velocity=0.65,
        body_size=1.0,
        vibrato_hz=5.0,
        vibrato_cents=10.0,
        events=[
            {"kind": "slur", "time_s": 1.4, "freq_hz": 349.228231433, "hold_s": 1.5},
            {"kind": "slur", "time_s": 2.8, "freq_hz": 329.627556913, "hold_s": 1.4},
        ],
    )
    # Explicit gain and placement; source models do not normalize or add effects.
    keys = keys * 2.5
    strings = dsp.pan(string, -0.2) * 0.2
    mix = (keys + strings) * 0.7
    mix[-600:] *= np.linspace(1, 0, 600)[:, None]
    return {"sample_rate": rate, "outputs": {"piano": keys, "bowed": strings, "mix": mix}}
