"""Owned Q-filter bank: geometric centers, variable Hann windows, decimated FIR.

NumPy designs the filters; SciPy upfirdn computes only requested output samples,
without a full-rate complex convolution or a frequency-by-frame-by-window tensor.
Bandwidth convention follows librosa wavelet_lengths (see LICENSE.librosa); this
is a direct filter-bank definition, not its recursive resampling approximation.
"""

import numpy as np
from scipy.signal import get_window, upfirdn

from . import _features


def design(sample_rate, fmin, n_bins, bins_per_octave, filter_scale, gamma):
    _features.positive_int("n_bins", n_bins)
    _features.positive_int("bins_per_octave", bins_per_octave)
    for name, value in (("fmin", fmin), ("filter_scale", filter_scale)):
        if not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    # tanh avoids overflow at low bins_per_octave.
    alpha = np.tanh(np.log(2) / bins_per_octave)
    gamma = 24.7 * alpha / 0.108 if gamma is None else gamma
    if not np.isfinite(gamma) or gamma < 0:
        raise ValueError("gamma must be finite and nonnegative")
    if n_bins > 4096:
        raise ValueError("n_bins must not exceed 4096")
    with np.errstate(over="ignore"):
        frequencies = fmin * np.exp2(np.arange(n_bins) / bins_per_octave)
    bandwidth = (alpha * frequencies + gamma) / filter_scale
    # Hann equivalent-noise half-bandwidth guard; not a brick-wall filter.
    if np.any(~np.isfinite(frequencies)) or np.any(
        frequencies + 0.75 * bandwidth >= sample_rate / 2
    ):
        raise ValueError(
            "highest filter bandwidth must remain below Nyquist; reduce n_bins/fmin/gamma"
        )
    lengths = sample_rate / bandwidth
    if not np.isfinite(lengths).all() or np.any(lengths > 2**20):
        raise ValueError("Q windows must not exceed 1048576 samples; raise fmin/gamma")
    if np.any(lengths < 4):
        raise ValueError("Q windows must contain at least 4 samples; increase filter_scale")
    return frequencies, np.ceil(lengths).astype(int), float(gamma)


def transform(audio, sample_rate, hop, fmin, n_bins, bins_per_octave, filter_scale, gamma):
    x = _features.mono(audio, sample_rate, average=False)
    _features.positive_int("hop", hop)
    frequencies, lengths, gamma = design(
        sample_rate, fmin, n_bins, bins_per_octave, filter_scale, gamma
    )
    count = 1 + len(x) // hop
    magnitude = np.empty((n_bins, count))
    for row, (frequency, length) in enumerate(zip(frequencies, lengths, strict=True)):
        offsets = np.arange(length) - length // 2
        window = get_window("hann", int(length), fftbins=True)
        kernel = window * np.exp(-2j * np.pi * frequency * offsets / sample_rate)
        kernel *= 2 / window.sum()
        # Align the decimated full convolution to centered frame timestamps.
        offset = length - 1 - length // 2
        prefix = int(-offset % hop)
        first = (offset + prefix) // hop
        if count == 1:
            usable = min(len(x), length - length // 2)
            magnitude[row, 0] = abs(np.dot(x[:usable], kernel[length // 2 : length // 2 + usable]))
            continue
        signal = np.pad(x, (prefix, hop))
        # Two real FIRs avoid promoting every input sample to complex. Both compute
        # the same correlation; only the floating-point summation path differs.
        real = upfirdn(kernel.real[::-1], signal, down=hop)[first : first + count]
        imag = upfirdn(kernel.imag[::-1], signal, down=hop)[first : first + count]
        magnitude[row] = np.hypot(real, imag)
    if not np.isfinite(magnitude).all():
        raise ValueError("audio magnitude is too large for finite Q-transform values")
    return {
        "times_s": _features.times(count, sample_rate, hop),
        "freqs_hz": frequencies,
        "magnitude": magnitude,
        "window_samples": lengths,
        "hop_samples": int(hop),
        "gamma_hz": gamma,
    }
