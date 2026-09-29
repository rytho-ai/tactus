"""Owned Mel/log-frequency SuperFlux envelope and greedy onset selection.

Retains the established librosa framing compensation, boundary windows and backtracking.
Adapted from librosa (ISC); see LICENSE.librosa. NumPy/SciPy only, no learned model.
"""

import numpy as np
from scipy.ndimage import maximum_filter1d

from ._features import log_power


def strength(power, n_fft, hop, lag, max_size, *, compressed=False):
    if power.shape[1] <= lag:
        return np.zeros(power.shape[1])
    spectrum = power if compressed else log_power(power, relative=True)
    reference = maximum_filter1d(spectrum, max_size, axis=0) if max_size > 1 else spectrum
    # The filtered reference is owned here: reuse it instead of allocating another
    # bands-by-time matrix. With filtering disabled, protect the caller's spectrum.
    positive = reference[:, :-lag] if max_size > 1 else np.empty_like(spectrum[:, lag:])
    np.subtract(spectrum[:, lag:], reference[:, :-lag], out=positive)
    np.maximum(positive, 0, out=positive)
    envelope = positive.mean(axis=0)
    return np.pad(envelope, (lag + n_fft // (2 * hop), 0))[: power.shape[1]]


def pick(envelope, sample_rate, hop, delta, min_interval_s, backtrack):
    values = envelope - envelope.min()
    values /= values.max() + np.finfo(values.dtype).tiny
    if not values.any() or not np.isfinite(values).all():
        return np.empty(0, dtype=np.int64)
    pre_max = int(0.03 * sample_rate // hop)
    pre_avg = int(0.10 * sample_rate // hop)
    post_avg = pre_avg + 1
    wait = int(min_interval_s * sample_rate // hop)
    # Only evaluate means for local maxima. Direct local sums avoid global prefix-sum
    # cancellation and preserve the reference's boundary truncation and greedy ordering.
    maxima = maximum_filter1d(values, pre_max + 1, origin=pre_max // 2, mode="nearest")
    events = []
    next_frame = 0
    for frame in np.flatnonzero(values == maxima):
        if frame < next_frame:
            continue
        mean = values[max(0, frame - pre_avg) : min(len(values), frame + post_avg)].mean()
        if values[frame] >= mean + delta:
            events.append(frame)
            next_frame = frame + wait + 1
    events = np.asarray(events, dtype=np.int64)
    if backtrack and len(events):
        minima = np.r_[
            0, 1 + np.flatnonzero((values[1:-1] <= values[:-2]) & (values[1:-1] < values[2:]))
        ]
        events = minima[np.searchsorted(minima, events, side="right") - 1]
    return events
