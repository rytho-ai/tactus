"""Cached Numba kernels for sequential synthesis loops.

Callers own validation and finite-output checks. Kernels use float64 arrays without
fastmath and keep the recurrence order documented by synth.py.
"""

from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True)
def karplus_strong(
    drive: np.ndarray, delay: int, smoothing: float, allpass: float, gain: float
) -> np.ndarray:
    """y[n] = drive[n] + gain·A(avg[n]); avg[n] = (1-s)·y[n-D] + s·y[n-D-1]; A is allpass."""
    frames = drive.shape[0]
    out = np.empty(frames, dtype=np.float64)
    previous_avg = 0.0
    previous_ap = 0.0
    for n in range(frames):
        newer = out[n - delay] if n >= delay else 0.0
        older = out[n - delay - 1] if n >= delay + 1 else 0.0
        avg = (1.0 - smoothing) * newer + smoothing * older
        ap = allpass * avg + previous_avg - allpass * previous_ap
        previous_avg = avg
        previous_ap = ap
        out[n] = drive[n] + gain * ap
    return out
