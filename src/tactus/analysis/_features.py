"""Owned NumPy/SciPy spectral frontend shared by features and onset analysis.

Owns validation, centered Hann framing, Slaney Mel/log-power and fixed-tuning chroma.
Sparse band projection bounds FFT temporaries, with native workers for large inputs;
log-frequency magnitude bands adapt
CPJKU/SuperFlux's A440-aligned triangles (see LICENSE.SuperFlux).
Filter formulas adapted from librosa (ISC); see LICENSE.librosa. Retains established
float32 filter coefficients, float64 power and channel conventions without importing it.
"""

from __future__ import annotations

import warnings

import numpy as np
from scipy.fft import rfft
from scipy.signal import get_window
from scipy.sparse import csr_matrix

from ._acceleration import fft_workers


def positive_int(name: str, value: int) -> None:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def mono(audio: np.ndarray, sample_rate: int, *, average: bool) -> np.ndarray:
    positive_int("sample_rate", sample_rate)
    raw = np.asarray(audio)
    if raw.ndim not in (1, 2) or raw.size == 0:
        raise ValueError("audio must be nonempty, 1-D or 2-D (frames[, channels])")
    if raw.dtype.kind not in "fiu" or not np.isfinite(raw).all():
        raise ValueError("audio must contain finite real samples")
    x = np.asarray(raw, dtype=np.float64)
    if x.ndim == 2:
        x = np.mean(x, axis=1) if average else np.sum(x, axis=1)
    if not np.isfinite(x).all():
        raise ValueError("audio downmix must contain finite samples")
    return x


def _validate_frames(n_fft: int, hop: int):
    positive_int("n_fft", n_fft)
    positive_int("hop", hop)
    if n_fft < 4 or n_fft % 2:
        raise ValueError("n_fft must be even and at least 4")
    if hop > n_fft:
        raise ValueError("hop must not exceed n_fft")


def _frames(x: np.ndarray, n_fft: int, hop: int):
    _validate_frames(n_fft, hop)
    padded = np.pad(x, (n_fft // 2, n_fft // 2))
    frames = np.lib.stride_tricks.sliding_window_view(padded, n_fft)[::hop]
    window = get_window("hann", n_fft, fftbins=True)
    return frames, window


def power_spectrum(x: np.ndarray, n_fft: int, hop: int) -> np.ndarray:
    frames, window = _frames(x, n_fft, hop)
    power = np.empty((n_fft // 2 + 1, len(frames)), order="F")
    chunk = max(1, (1 << 20) // n_fft)
    for first in range(0, len(frames), chunk):
        transformed = rfft(frames[first : first + chunk] * window, axis=1)
        power[:, first : first + chunk] = (np.abs(transformed) ** 2).T
    if not np.isfinite(power).all():
        raise ValueError("audio magnitude is too large for finite spectral power")
    return power


def _project_bands(x, n_fft, hop, weights, *, power):
    """Project bounded FFT chunks using only nonzero triangular coefficients."""
    _validate_frames(n_fft, hop)
    count = 1 + len(x) // hop
    window = get_window("hann", n_fft, fftbins=True)
    # Promote AFTER filter construction, preserving the Mel float32 rounding steps.
    sparse = csr_matrix(weights.astype(np.float64))
    result = np.empty((weights.shape[0], count), order="F")
    chunk = max(1, (1 << 20) // n_fft)
    for first in range(0, count, chunk):
        stop = min(count, first + chunk)
        left = first * hop - n_fft // 2
        right = (stop - 1) * hop + n_fft // 2
        segment = x[max(0, left) : min(len(x), right)]
        # Only boundary chunks need padding; don't duplicate the whole input.
        if left < 0 or right > len(x):
            segment = np.pad(segment, (max(0, -left), max(0, right - len(x))))
        frames = np.lib.stride_tricks.sliding_window_view(segment, n_fft)[::hop]
        magnitudes = np.abs(rfft(frames * window, axis=1, workers=fft_workers(count * n_fft)))
        if power:
            np.square(magnitudes, out=magnitudes)
        # Check all bins, including those outside the selected frequency range.
        if not np.isfinite(magnitudes).all():
            raise ValueError("audio magnitude is too large for finite spectral values")
        result[:, first : first + chunk] = sparse @ magnitudes.T
    if not np.isfinite(result).all():
        raise ValueError("audio magnitude is too large for finite band values")
    return result


def frequency_range(sample_rate: int, fmin: float, fmax: float | None) -> float:
    upper = sample_rate / 2 if fmax is None else fmax
    if not np.isfinite([fmin, upper]).all() or not 0 <= fmin < upper <= sample_rate / 2:
        raise ValueError("frequencies must satisfy 0 <= fmin < fmax <= sample_rate / 2")
    return float(upper)


def mel_power(
    x: np.ndarray,
    sample_rate: int,
    n_fft: int,
    hop: int,
    n_mels: int,
    fmin: float,
    fmax: float | None,
) -> tuple[np.ndarray, np.ndarray]:
    positive_int("n_mels", n_mels)
    upper = frequency_range(sample_rate, fmin, fmax)
    # Validate framing before constructing frequency axes or allocating filters.
    _validate_frames(n_fft, hop)
    edges = mel_frequencies(n_mels + 2, fmin, upper)
    frequencies = np.fft.rfftfreq(n_fft, 1 / sample_rate)
    ramps = edges[:, None] - frequencies
    widths = np.diff(edges)
    # Retain the two float32 rounding steps of the established filter definition.
    weights = np.maximum(
        0, np.minimum(-ramps[:-2] / widths[:-1, None], ramps[2:] / widths[1:, None])
    ).astype(np.float32)
    weights *= (2 / (edges[2:] - edges[:-2]))[:, None]
    if not np.all((edges[:-2] == 0) | (weights.max(axis=1) > 0)):
        warnings.warn(
            "Empty filters detected in mel frequency basis; increase n_fft or reduce n_mels.",
            UserWarning,
            stacklevel=2,
        )
    return _project_bands(x, n_fft, hop, weights, power=True), edges[1:-1]


def log_frequency_weights(sample_rate, n_fft, bands_per_octave, fmin, fmax):
    """Unit-height log triangles, matching the original SuperFlux Filter construction.

    Round A440-aligned edges to bins, merge duplicates, exclude Nyquist. Resolution
    determines the actual band count; this is not a CQT or Slaney normalization.
    """
    positive_int("n_fft", n_fft)
    positive_int("bands_per_octave", bands_per_octave)
    if n_fft < 4 or n_fft % 2:
        raise ValueError("n_fft must be even and at least 4")
    frequency_range(sample_rate, fmin, fmax)
    if fmin <= 0:
        raise ValueError("log filterbank requires fmin > 0")
    factor = 2.0 ** (1.0 / bands_per_octave)
    if factor == 1:
        raise ValueError("bands_per_octave is too large to resolve")
    frequency = 440.0
    frequencies = [frequency]
    while frequency <= fmax:
        frequency *= factor
        frequencies.append(frequency)
    frequency = 440.0
    while frequency >= fmin:
        frequency /= factor
        frequencies.append(frequency)
    edges = np.unique(np.round(np.sort(frequencies) / (sample_rate / n_fft)).astype(int))
    # The original frequency generator includes A440 even for narrower ranges.
    # Retain only triangles whose center lies inside the requested range.
    edges = edges[edges < n_fft // 2]
    centers = edges[1:-1] * sample_rate / n_fft
    selected = (centers >= fmin) & (centers <= fmax)
    if not selected.any():
        raise ValueError("log filterbank has no resolvable bands; widen range or increase n_fft")
    weights = np.zeros((len(edges) - 2, n_fft // 2 + 1))
    for i, (start, mid, stop) in enumerate(zip(edges, edges[1:], edges[2:], strict=False)):
        weights[i, start:mid] = np.linspace(0, 1, mid - start, endpoint=False)
        weights[i, mid:stop] = np.linspace(1, 0, stop - mid, endpoint=False)
    return weights[selected]


def log_magnitude(x, sample_rate, n_fft, hop, bands_per_octave, fmin, fmax):
    weights = log_frequency_weights(sample_rate, n_fft, bands_per_octave, fmin, fmax)
    magnitude = _project_bands(x, n_fft, hop, weights, power=False)
    return np.log10(1 + magnitude)


def mel_frequencies(count, lower, upper):
    frequencies = np.array([lower, upper], dtype=float)
    mels = frequencies / (200 / 3)
    mask = frequencies >= 1000
    step = np.log(6.4) / 27
    transition = 1000 / (200 / 3)
    mels[mask] = transition + np.log(frequencies[mask] / 1000) / step
    grid = np.linspace(mels[0], mels[1], count)
    hz = (200 / 3) * grid
    mask = grid >= transition
    hz[mask] = 1000 * np.exp(step * (grid[mask] - transition))
    return hz


def log_power(power, *, relative=False):
    result = np.maximum(1e-10, power)
    np.log10(result, out=result)
    result *= 10
    if relative:
        result -= 10 * np.log10(max(1e-10, np.max(power)))
    np.maximum(result, result.max() - 80, out=result)
    return result


def chroma_power(power, sample_rate, n_fft, tuning):
    # Adapted from librosa.filters.chroma, retaining its octave weighting and DC rule.
    frequencies = np.linspace(0, sample_rate, n_fft, endpoint=False)[1:]
    reference = 440 * 2 ** (tuning / 12)
    bins = 12 * np.log2(frequencies / (reference / 16))
    bins = np.r_[bins[0] - 18, bins]
    widths = np.r_[np.maximum(np.diff(bins), 1), 1]
    distances = (bins[None, :] - np.arange(12)[:, None] + 126) % 12 - 6
    weights = np.exp(-0.5 * (2 * distances / widths) ** 2)
    norms = np.sqrt(np.sum(weights**2, axis=0, keepdims=True))
    weights /= np.where(norms < np.finfo(float).tiny, 1, norms)
    weights *= np.exp(-0.5 * ((bins / 12 - 5) / 2) ** 2)
    weights = np.ascontiguousarray(
        np.roll(weights, -3, axis=0)[:, : n_fft // 2 + 1], dtype=np.float32
    )
    result = np.einsum("mf,ft->mt", weights, power, optimize=True)
    norms = np.max(np.abs(result), axis=0, keepdims=True)
    return result / np.where(norms < np.finfo(float).tiny, 1, norms)


def times(frame_count: int, sample_rate: int, hop: int) -> np.ndarray:
    return np.arange(frame_count, dtype=np.float64) * hop / sample_rate


def power_distribution(audio, sample_rate, n_fft, hop):
    """Frame-relative power and valid-frame mask for dimensionless descriptors.

    Scaling by frame peak before summing prevents total-power overflow and removes
    gain dependence without applying a silence gate. Zero-power frames remain marked.
    """
    x = mono(audio, sample_rate, average=False)
    power = power_spectrum(x, n_fft, hop)
    maxima = power.max(axis=0)
    valid = maxima > 0
    relative = np.divide(power, maxima, out=np.zeros_like(power), where=valid)
    return relative, valid
