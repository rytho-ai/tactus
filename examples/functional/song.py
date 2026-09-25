"""A modular free-time production with an authored nonlinear stereo mix."""

import numpy as np
from parts import RATE, bass, texture


def render(*, bass_gain=0.8):
    low = bass() * bass_gain
    pad = texture()
    mix = 0.7 * np.tanh(1.4 * (low[:, None] + pad))
    return {
        "sample_rate": RATE,
        "outputs": {"mix": mix, "stem-bass": low, "stem-texture": pad},
    }
