"""Author a finite echo sculpture using wet-only delay as an interface reference.

Each tap is a separate colored copy, not feedback. SciPy handles the filter in native
code; there is no per-sample Python loop to JIT. All state is local to a call.
"""

import numpy as np
from phrase import phrase
from scipy.signal import butter, sosfilt

from tactus import dsp


def colored_taps(audio, sample_rate, *, spacing_s=0.23, repeats=5):
    """Mono in, stereo wet-only out, preserving the last finite repeat in full."""
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim != 1 or not np.isfinite(x).all():
        raise ValueError("expected finite mono audio")
    if not np.isfinite(spacing_s) or spacing_s <= 0 or sample_rate <= 0:
        raise ValueError("positive rate and spacing required")
    if not isinstance(repeats, int) or repeats < 1:
        raise ValueError("repeats must be a positive integer")
    spacing = max(1, round(spacing_s * sample_rate))
    wet = np.zeros((len(x) + repeats * spacing, 2))
    for repeat in range(1, repeats + 1):
        cutoff = min(3600 / repeat, sample_rate * 0.4)
        colored = sosfilt(butter(2, cutoff, fs=sample_rate, output="sos"), x)
        position = (-1 if repeat % 2 else 1) * 0.7
        tap = dsp.pan(colored, position) * 0.64**repeat
        start = repeat * spacing
        wet[start : start + len(tap)] += tap
    return wet


def render(*, spacing_s=0.23):
    mono, rate = phrase()
    wet = colored_taps(mono, rate, spacing_s=spacing_s)
    dry = np.pad(dsp.pan(mono), ((0, len(wet) - len(mono)), (0, 0)))
    return {"sample_rate": rate, "outputs": {"dry": dry, "wet": wet, "mix": dry + wet}}
