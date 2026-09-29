"""Bounded FFT linear autocorrelation of a nonnegative onset envelope.

Zero padding, periodic Hann windows and zero-lag normalization are explicit.
Positive integer lags are retained and reversed into ascending BPM order.
"""

import numpy as np
from scipy.fft import irfft, next_fast_len, rfft
from scipy.signal import get_window


def autocorrelation(envelope, window, lags):
    padded = np.pad(envelope, (window // 2, window // 2))
    frames = np.lib.stride_tricks.sliding_window_view(padded, window)[: len(envelope)]
    weights = get_window("hann", window, fftbins=True)
    n_fft = next_fast_len(2 * window - 1)
    result = np.empty((len(lags), len(envelope)))
    chunk = max(1, (1 << 19) // n_fft)
    for first in range(0, len(envelope), chunk):
        spectrum = rfft(frames[first : first + chunk] * weights, n=n_fft, axis=1)
        corr = irfft(np.abs(spectrum) ** 2, n=n_fft, axis=1)
        energy = corr[:, :1]
        normalized = np.divide(
            corr[:, lags], energy, out=np.zeros((len(corr), len(lags))), where=energy > 0
        )
        result[:, first : first + chunk] = np.clip(normalized, 0, 1).T
    return result
