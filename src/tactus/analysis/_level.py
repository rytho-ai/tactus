"""NumPy/SciPy implementation of complete-window level curves.

Owns validation, local window reductions, continuous K-weighting and integrated LUFS
for level.py. Integrated LUFS retains its legacy RBJ filter and gating grid.
The De Man biquad coefficients are adapted from pyloudnorm's MIT-licensed IIRfilter;
see LICENSE.pyloudnorm. No pyloudnorm or pymixtool imports are required here.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import lfilter, sosfilt

from tactus._biquad import coefficients


def audio_frames(audio: np.ndarray, sample_rate: int, *, loudness: bool = False) -> np.ndarray:
    if (
        isinstance(sample_rate, (bool, np.bool_))
        or not isinstance(sample_rate, (int, np.integer))
        or sample_rate < 1
    ):
        raise ValueError("sample_rate must be a positive integer")
    x = np.asarray(audio)
    if x.ndim not in (1, 2) or x.size == 0:
        raise ValueError("audio must be nonempty (frames,) or (frames, channels)")
    if x.dtype.kind not in "fiu" or not np.isfinite(x).all():
        raise ValueError("audio must contain finite real samples")
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if loudness and (sample_rate < 8000 or x.shape[1] > 5):
        raise ValueError("loudness requires sample_rate >= 8000 and 1 to 5 channels (no LFE)")
    return x


def window_grid(length: int, sample_rate: int, window_s: float, hop_s: float):
    for name, value in (("window_s", window_s), ("hop_s", hop_s)):
        if isinstance(value, (bool, np.bool_)) or not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    sizes = np.asarray([window_s, hop_s]) * sample_rate
    if not np.isfinite(sizes).all() or np.max(sizes) > np.iinfo(np.int64).max:
        raise ValueError("window/hop sizes exceed the supported sample range")
    window, hop = (round(v) for v in sizes)
    if not 1 <= hop <= window:
        raise ValueError("rounded sizes must satisfy 1 <= hop_samples <= window_samples")
    starts = np.arange(0, max(0, length - window + 1), hop, dtype=np.int64)
    return starts, window, hop


def k_weighting(sample_rate: int) -> np.ndarray:
    """Two SOS rows: shelf then RLB high-pass, matching BS.1770's 48 kHz coefficients."""
    k = np.tan(np.pi * 1681.974450955533 / sample_rate)
    q = 0.7071752369554196
    vh = 10 ** (3.999843853973347 / 20)
    vb = vh**0.4996667741545416
    denominator = 1 + k / q + k * k
    shelf = [
        (vh + vb * k / q + k * k) / denominator,
        2 * (k * k - vh) / denominator,
        (vh - vb * k / q + k * k) / denominator,
        1,
        2 * (k * k - 1) / denominator,
        (1 - k / q + k * k) / denominator,
    ]
    k = np.tan(np.pi * 38.13547087602444 / sample_rate)
    q = 0.5003270373238773
    denominator = 1 + k / q + k * k
    high_pass = [1, -2, 1, 1, 2 * (k * k - 1) / denominator, (1 - k / q + k * k) / denominator]
    return np.asarray([shelf, high_pass])


def sample_power(audio: np.ndarray, sample_rate: int, *, weighted: bool) -> np.ndarray:
    x = sosfilt(k_weighting(sample_rate), audio, axis=0) if weighted else audio
    with np.errstate(over="ignore", invalid="ignore"):
        if weighted:
            weights = np.asarray([1, 1, 1, 1.41, 1.41])[: x.shape[1]]
            power = np.square(x) @ weights
        else:
            power = np.mean(np.square(x), axis=1)
    if not np.isfinite(power).all():
        raise ValueError("audio magnitude is too large for finite power")
    return power


def window_mean(power: np.ndarray, starts: np.ndarray, window: int) -> np.ndarray:
    # Local hop-bin or direct reductions preserve quiet windows after loud passages.
    # Whole-file prefix-sum subtraction can erase their energy through cancellation.
    with np.errstate(over="ignore"):
        if len(starts) > 1 and starts[0] == 0:
            hop = int(starts[1] - starts[0])
        else:
            hop = 0
        if hop > 0 and window % hop == 0 and np.all(np.diff(starts) == hop):
            blocks = power[: (len(power) // hop) * hop].reshape(-1, hop).mean(axis=1)
            values = np.lib.stride_tricks.sliding_window_view(blocks, window // hop).mean(axis=1)
            values = values[: len(starts)]
        else:
            values = np.asarray([np.mean(power[start : start + window]) for start in starts])
    if not np.isfinite(values).all():
        raise ValueError("audio magnitude is too large for finite window power")
    return values


def decibels(power: np.ndarray, *, offset: float = 0.0) -> np.ndarray:
    with np.errstate(divide="ignore"):
        return offset + 10 * np.log10(power)


def curve_result(values: np.ndarray, field: str, starts, window, hop, sample_rate):
    return {
        "times_s": ((starts + window) / sample_rate).tolist(),
        field: [float(v) if np.isfinite(v) else None for v in values],
        "window_samples": window,
        "hop_samples": hop,
    }


def loudness_curve(audio, sample_rate, window_s, hop_s):
    x = audio_frames(audio, sample_rate, loudness=True)
    starts, window, hop = window_grid(len(x), sample_rate, window_s, hop_s)
    power = sample_power(x, sample_rate, weighted=True)
    values = decibels(window_mean(power, starts, window), offset=-0.691)
    return curve_result(values, "loudness_lufs", starts, window, hop, sample_rate)


def range_statistics(values: np.ndarray) -> dict:
    eligible = values[values >= -70]
    result = {
        "lra_lu": None,
        "low_lufs": None,
        "high_lufs": None,
        "relative_gate_lufs": None,
        "gated_blocks": 0,
    }
    if not len(eligible):
        return result
    # Mean in the energy domain, stabilized around the largest dB value.
    largest = np.max(eligible)
    relative_gate = largest + 10 * np.log10(np.mean(10 ** ((eligible - largest) / 10))) - 20
    gated = np.sort(eligible[eligible >= relative_gate])
    indices = np.floor((len(gated) - 1) * np.asarray([0.10, 0.95]) + 0.5).astype(int)
    low, high = gated[indices]
    return {
        "lra_lu": float(high - low),
        "low_lufs": float(low),
        "high_lufs": float(high),
        "relative_gate_lufs": float(relative_gate),
        "gated_blocks": len(gated),
    }


def amplitude_windows(x, starts, window, hop, *, peak):
    """Reduce aligned hop bins once; keep direct windows for arbitrary sample grids."""
    with np.errstate(over="ignore", invalid="ignore"):
        transformed = np.abs(x) if peak else np.square(x)
        if not np.isfinite(transformed).all():
            raise ValueError("audio magnitude is too large for finite power")
        if len(starts) and window % hop == 0:
            bins = transformed[: (len(x) // hop) * hop].reshape(-1, hop, x.shape[1])
            bins = bins.max(axis=(1, 2)) if peak else bins.mean(axis=(1, 2))
            frames = np.lib.stride_tricks.sliding_window_view(bins, window // hop)
            values = frames.max(axis=1) if peak else frames.mean(axis=1)
        elif peak:
            maxima = transformed.max(axis=1)
            values = np.asarray([maxima[i : i + window].max() for i in starts])
        else:
            power = transformed.mean(axis=1)
            if not np.isfinite(power).all():
                raise ValueError("audio magnitude is too large for finite power")
            values = window_mean(power, starts, window)
    if not np.isfinite(values).all():
        raise ValueError("audio magnitude is too large for finite window power")
    return values


def integrated_loudness(audio, sample_rate):
    """Legacy pyloudnorm default definition, including rounded partial-tail blocks.

    RBJ filters differ from the De Man design used by the curve APIs. Preserve the
    historical integration grid and denominator rather than silently changing revision 1.
    Adapted from pyloudnorm Meter; see LICENSE.pyloudnorm.
    """
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2 or not 1 <= x.shape[1] <= 5 or len(x) < 0.4 * sample_rate:
        return None
    if sample_rate <= 0 or not np.isfinite(x).all():
        return None
    for kind, frequency, q, gain in [
        ("high_shelf", 1500.0, 1 / np.sqrt(2), 4.0),
        ("highpass", 38.0, 0.5, 0.0),
    ]:
        sos = coefficients(sample_rate, kind, frequency, q, gain)
        x = lfilter(sos[:3], sos[3:], x, axis=0)
    count = int(np.round((len(x) / sample_rate - 0.4) / (0.4 * 0.25))) + 1
    powers = np.empty((count, x.shape[1]))
    with np.errstate(over="ignore", invalid="ignore"):
        # Channel-contiguous reductions avoid a Python-sized reduction per sample.
        squared = np.ascontiguousarray(np.square(x).T)
        for j in range(count):
            start = int(0.4 * (j * 0.25) * sample_rate)
            end = int(0.4 * (j * 0.25 + 1) * sample_rate)
            powers[j] = squared[:, start:end].sum(axis=1) / (0.4 * sample_rate)
        weights = np.asarray([1, 1, 1, 1.41, 1.41])[: x.shape[1]]
        loudness = decibels(powers @ weights, offset=-0.691)
        eligible = loudness >= -70
        if not eligible.any():
            return None
        relative = decibels(powers[eligible].mean(axis=0) @ weights, offset=-0.691) - 10
        keep = (loudness > -70) & (loudness > relative)
        if not keep.any():
            return None
        value = decibels(powers[keep].mean(axis=0) @ weights, offset=-0.691)
    return float(value) if np.isfinite(value) else None
