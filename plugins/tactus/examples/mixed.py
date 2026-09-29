"""A short render can combine native plugins, builtin DSP and local array math.

The chorus receives channels-first audio explicitly. Its state belongs to this render;
one second of zeros makes its tail audible. The mid/side gesture uses output time.
"""

import numpy as np
from pedalboard import Chorus
from phrase import phrase

from tactus import dsp


def render(*, motion_hz=0.3):
    mono, rate = phrase()
    dry = np.pad(dsp.pan(mono), ((0, rate), (0, 0)))
    low, high = dsp.crossover(dry, rate, cutoff_hz=800)
    chorus = Chorus(rate_hz=0.8, depth=0.5, centre_delay_ms=9, feedback=0.1, mix=0.6)
    colored = chorus(np.ascontiguousarray(high.T, dtype=np.float32), rate, reset=True).T
    mid = colored.mean(axis=1)
    side = (colored[:, 0] - colored[:, 1]) / 2
    t = np.arange(len(dry)) / rate
    # Add a slow asymmetric gesture even when the chorus starts from mono.
    side = side * (0.8 + 0.5 * np.sin(2 * np.pi * motion_hz * t))
    side += 0.2 * mid * np.sin(2 * np.pi * motion_hz * t)
    mix = low + np.column_stack([mid + side, mid - side])
    return {"sample_rate": rate, "outputs": {"dry": dry, "mix": mix}}
