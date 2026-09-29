"""RBJ biquad coefficients shared by owned DSP and legacy integrated loudness.

Q-based forms of the Audio EQ Cookbook equations:
https://www.w3.org/TR/audio-eq-cookbook/ . Parameter validation belongs to callers.
"""

import numpy as np


def coefficients(sample_rate, kind, frequency_hz, q, gain_db):
    a = np.power(10.0, gain_db / 40.0)
    w = 2 * np.pi * (frequency_hz / sample_rate)
    c = np.cos(w)
    alpha = np.sin(w) / (2 * q)
    if kind in ("lowpass", "highpass"):
        sign = 1 if kind == "lowpass" else -1
        b = [(1 - sign * c) / 2, sign * (1 - sign * c), (1 - sign * c) / 2]
        denominator = [1 + alpha, -2 * c, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * a, -2 * c, 1 - alpha * a]
        denominator = [1 + alpha / a, -2 * c, 1 - alpha / a]
    elif kind in ("low_shelf", "high_shelf"):
        sign = 1 if kind == "high_shelf" else -1
        v = 2 * np.sqrt(a) * alpha
        b = [
            a * ((a + 1) + sign * (a - 1) * c + v),
            -2 * sign * a * ((a - 1) + sign * (a + 1) * c),
            a * ((a + 1) + sign * (a - 1) * c - v),
        ]
        denominator = [
            (a + 1) - sign * (a - 1) * c + v,
            2 * sign * ((a - 1) - sign * (a + 1) * c),
            (a + 1) - sign * (a - 1) * c - v,
        ]
    else:
        raise ValueError("kind must be lowpass, highpass, peak, low_shelf or high_shelf")
    return np.asarray([*b, *denominator]) / denominator[0]
