"""Minimal render entry: keyword controls in, named audio arrays out."""

import numpy as np

from tactus import dsp


def render(*, gain: float = 0.2) -> dict:
    sample_rate = 48_000
    t = np.arange(sample_rate) / sample_rate
    audio = dsp.fade(gain * np.sin(2 * np.pi * 220 * t), sample_rate, in_s=0.01, out_s=0.05)
    return {"sample_rate": sample_rate, "outputs": {"mix": audio}}
