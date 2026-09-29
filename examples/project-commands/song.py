"""Two synthetic tones for exercising project commands; no external audio needed."""

import numpy as np


def render(*, side_gain: float = 0.1):
    rate = 48_000
    t = np.arange(rate) / rate
    mid = 0.2 * np.sin(2 * np.pi * 220 * t)
    side = side_gain * np.sin(2 * np.pi * 330 * t)
    return {
        "sample_rate": rate,
        "outputs": {"mix": np.column_stack([mid + side, mid - side]), "mid": mid, "side": side},
    }
