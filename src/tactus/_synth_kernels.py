"""Cached Numba kernels for synthesis loops: the Karplus-Strong recurrence and grain overlap-add.

Callers own validation and finite-output checks. Kernels use float64 arrays without
fastmath and keep the operation order documented by synth.py.
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


@njit(cache=True)
def overlap_grains(
    padded: np.ndarray,
    begins: np.ndarray,
    lengths: np.ndarray,
    starts: np.ndarray,
    rates: np.ndarray,
    gains: np.ndarray,
    left: np.ndarray,
    right: np.ndarray,
    hann: bool,
    frames: int,
    stereo: bool,
) -> np.ndarray:
    """Overlap-add windowed grains read with linear interpolation; zero outside the source.

    padded is the source plus one trailing zero. Grain i starts at begins[i], lasts
    lengths[i] frames and reads from starts[i] + k·rates[i]. Stereo multiplies each grain
    by its left/right equal-power gains; mono ignores them. The window is recomputed
    only when the grain length changes.
    """
    size = padded.shape[0] - 1
    out = np.zeros((frames, 2 if stereo else 1), dtype=np.float64)
    window = np.empty(0, dtype=np.float64)
    for i in range(begins.shape[0]):
        begin = begins[i]
        if begin >= frames:
            continue
        length = lengths[i]
        if window.shape[0] != length:
            window = np.empty(length, dtype=np.float64)
            for k in range(length):
                x = (k + 0.5) / length
                if hann:
                    w = np.sin(np.pi * x)
                    window[k] = w * w
                else:
                    window[k] = 1.0 - abs(2.0 * x - 1.0)
        stop = min(frames, begin + length)
        for k in range(stop - begin):
            read = starts[i] + k * rates[i]
            whole = np.floor(read)
            index = int(whole)
            if 0 <= index < size:
                frac = read - whole
                sample = (1 - frac) * padded[index] + frac * padded[min(index + 1, size)]
            else:
                sample = 0.0
            grain = sample * window[k] * gains[i]
            if stereo:
                out[begin + k, 0] += grain * left[i]
                out[begin + k, 1] += grain * right[i]
            else:
                out[begin + k, 0] += grain
    return out
