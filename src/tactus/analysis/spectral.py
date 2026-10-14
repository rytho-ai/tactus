"""spectral: frequency measurements, distribution descriptors and spectral feature arrays.

Every function here *reports* a measurement; none returns a pass/fail verdict — Tactus reports,
not blocks (see `docs/design.md`'s "驗證與觀察"). Each analysis takes `audio` in Tactus's
`(frames,)` or `(frames, channels)` float layout and `sample_rate` (matching `render`'s own
`sample_rate`); multi-channel input is summed to mono before analysis, because these are
single-number/curve measurements over the mixed signal, not a per-channel or stereo-field
report. `ANALYSES` lists the public analyses; each carries a `revision` int, bumped only when a
result's meaning changes.

Measurement definitions and feature-array contracts are maintained in
docs/analysis.md. Pitch estimation is outside this category; current limits
and the decision to omit a pitch category are recorded in docs/design.md. `tuning`
reports only a whole-signal offset from A440, the input `chroma` needs.

dB reference for the original five measurements: 0 dB = the power of a full-scale
(amplitude 1.0) sine wave, i.e. mean-square 0.5. The owned feature functions `mel`,
`chroma` and `mfcc` have their own units, documented individually, and return NumPy
arrays for Python; STFT also returns its matrix directly. The CLI saves matrix arrays
as attachments with `--out DIR`; analysis.image adds an optional SVG view.

Large STFT inputs use bounded SciPy chunks; STFT/Mel share a native FFT worker policy.

Reads: numpy · scipy.signal/fft · _features · _acceleration
"""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Any

import numpy as np
from scipy.fft import dct, set_workers
from scipy.signal import find_peaks, welch
from scipy.signal import stft as _scipy_stft

from . import _features
from ._acceleration import fft_workers
from ._revision import revision as _revision
from ._schema import describe as _describe

_FS_SINE_MEAN_SQUARE = 0.5
_STFT_CHUNK_WORK = 1 << 20

# Default `band_levels` bands (Hz): a coarse, commonly-used split from sub-bass through air.
_DEFAULT_BANDS: tuple[tuple[float, float], ...] = (
    (20.0, 60.0),  # sub-bass
    (60.0, 250.0),  # bass
    (250.0, 500.0),  # low-mid
    (500.0, 2000.0),  # mid
    (2000.0, 4000.0),  # high-mid
    (4000.0, 6000.0),  # presence
    (6000.0, 20000.0),  # brilliance/air
)


def _to_mono(audio: np.ndarray) -> np.ndarray:
    """Tactus `(frames,)` or `(frames, channels)` summed to mono `(frames,)` float64.

    Channels are summed (not averaged): the mix Tactus would play on a mono bus is what
    listeners/measurements care about here; for a stereo file this matches summing L+R the way
    a mono downmix or a mono meter would. Callers who need a single channel should slice
    `audio[:, ch]` before calling.
    """
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim == 1:
        return x
    if x.ndim == 2:
        return np.sum(x, axis=1)
    raise ValueError(f"audio must be 1-D or 2-D (frames[, channels]), got shape {x.shape}")


def _power_to_db(power: np.ndarray) -> np.ndarray:
    """Power (mean-square units) to dB relative to a full-scale sine. `-inf` where power is
    exactly 0 (silence); a tiny floor is NOT applied so callers can see true silence, but this
    means `-inf` may appear in returned arrays (re-encoded to `null` at the CLI boundary)."""
    power = np.asarray(power, dtype=np.float64)
    with np.errstate(divide="ignore"):
        db = 10.0 * np.log10(power / _FS_SINE_MEAN_SQUARE)
    return db


def _welch_nperseg(rate: int, resolution_hz: float) -> int:
    """Segment length (samples) whose Hann-windowed frequency resolution is <= `resolution_hz`.
    Welch/FFT frequency resolution is `rate / n`, so `n = rate / resolution_hz`, rounded up to
    the next power of 2 for FFT efficiency (this makes the achieved resolution somewhat finer
    than requested, never coarser)."""
    n = max(8, math.ceil(rate / resolution_hz))
    return 1 << (n - 1).bit_length()


def _spectrum(
    audio: np.ndarray, rate: int, resolution_hz: float, nfft: int | None
) -> tuple[np.ndarray, np.ndarray]:
    x = _to_mono(audio)
    nperseg = min(_welch_nperseg(rate, resolution_hz), len(x)) if len(x) else 1
    nperseg = max(nperseg, 1)
    noverlap = nperseg // 2
    n_fft_use = max(nperseg, nfft) if nfft else nperseg
    freqs, power = welch(
        x,
        fs=rate,
        window="hann",
        nperseg=nperseg,
        noverlap=noverlap,
        nfft=n_fft_use,
        scaling="spectrum",
    )
    return freqs, _power_to_db(power)


def _stft(
    audio: np.ndarray, rate: int, n_fft: int, hop: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = _to_mono(audio)
    if len(x) >= n_fft and (1 + len(x) // hop) * n_fft >= _STFT_CHUNK_WORK:
        return _chunked_stft(x, rate, n_fft, hop)
    noverlap = n_fft - hop
    with set_workers(fft_workers((1 + len(x) // hop) * n_fft)):
        freqs, times_s, zxx = _scipy_stft(
            x, fs=rate, window="hann", nperseg=n_fft, noverlap=noverlap, boundary="zeros"
        )
    # scipy's stft normalizes so a full-scale sine's peak bin magnitude is 0.5 (half the
    # window-summed amplitude, matching a one-sided spectrum convention); power = |X|^2, and
    # dividing by _FS_SINE_MEAN_SQUARE (0.5) puts a full-scale sine at ~0 dB, matching `spectrum`.
    power = np.abs(zxx) ** 2
    level_db = _power_to_db(power * 2.0)
    return times_s, freqs, level_db


def _chunked_stft(x, rate, n_fft, hop):
    """Bound SciPy FFT temporaries while retaining its exact scaling and time grid."""
    half = n_fft // 2
    extended = len(x) + 2 * half
    tail = (-(extended - n_fft) % hop) % n_fft
    count = 1 + (extended + tail - n_fft) // hop
    level_db = np.empty((n_fft // 2 + 1, count), order="F")
    chunk = max(1, (1 << 20) // n_fft)
    with set_workers(fft_workers(count * n_fft)):
        for first in range(0, count, chunk):
            stop = min(count, first + chunk)
            left = first * hop - half
            right = (stop - 1) * hop - half + n_fft
            segment = x[max(0, left) : min(len(x), right)]
            if left < 0 or right > len(x):
                segment = np.pad(segment, (max(0, -left), max(0, right - len(x))))
            freqs, _, zxx = _scipy_stft(
                segment,
                fs=rate,
                window="hann",
                nperseg=n_fft,
                noverlap=n_fft - hop,
                boundary=None,
                padded=False,
            )
            level_db[:, first:stop] = _power_to_db(np.abs(zxx) ** 2 * 2.0)
    # Preserve SciPy's order of floating-point operations (also for odd FFT sizes).
    times_s = np.arange(n_fft / 2, extended + tail - n_fft / 2 + 1, hop) / rate
    times_s -= (n_fft / 2) / rate
    return times_s, freqs, level_db


def _when_crosses(times: np.ndarray, values: np.ndarray, threshold: float) -> float | None:
    t = np.asarray(times, dtype=np.float64)
    v = np.asarray(values, dtype=np.float64)
    valid = ~np.isnan(v)
    if np.count_nonzero(valid) < 2:
        return None
    idx = np.flatnonzero(valid)
    for a, b in pairwise(idx):
        v0, v1 = v[a], v[b]
        if (v0 - threshold) == 0.0:
            return float(t[a])
        if (v0 - threshold) * (v1 - threshold) < 0.0:
            frac = (threshold - v0) / (v1 - v0)
            return float(t[a] + frac * (t[b] - t[a]))
    if v[idx[-1]] == threshold:
        return float(t[idx[-1]])
    return None


@_revision(1)
@_describe
def spectrum(
    audio: np.ndarray,
    sample_rate: int,
    *,
    resolution_hz: float = 1.0,
    nfft: int | None = None,
) -> dict[str, Any]:
    """Averaged power spectrum via Welch's method (Hann window, half-segment overlap).

    `resolution_hz` sets the segment length: `nperseg` is chosen so the FFT bin spacing
    (`sample_rate / nperseg`) is at or finer than `resolution_hz`, rounded up to the next power
    of 2. A finer (smaller) `resolution_hz` needs a longer segment, which needs more signal to
    average over — for a short signal, few or one segment (no averaging, more variance).

    `nfft`, if given and larger than the resolved segment length, zero-pads each Welch segment
    before the FFT. This makes the returned `freqs_hz` grid finer (sinc-interpolated bins)
    without needing a longer segment, i.e. it buys frequency precision independently of how
    much signal is available; it does not add real frequency resolving power (two genuinely
    close tones still blur together at the `resolution_hz`-implied resolution).

    Returns:
        freqs_hz (Hz): frequency of each bin, 0 to `sample_rate / 2` inclusive.
        level_db (dB): averaged power per bin relative to a full-scale sine (0 dB reference,
            see module docstring). Welch already scales for the window's power loss, so a
            full-scale sine at a bin-centred frequency reads ~0 dB.
    """
    freqs, level_db = _spectrum(audio, sample_rate, resolution_hz, nfft)
    return {"freqs_hz": freqs.tolist(), "level_db": level_db.tolist()}


@_revision(1)
@_describe
def band_levels(
    audio: np.ndarray,
    sample_rate: int,
    *,
    bands: tuple[tuple[float, float], ...] = _DEFAULT_BANDS,
) -> dict[str, Any]:
    """Power in each `(low_hz, high_hz)` band of `bands`, from the whole-file power spectrum
    (`spectrum(audio, sample_rate, resolution_hz=1.0)`, 1 Hz bins).

    A bin at frequency `f` belongs to a band when `low_hz <= f < high_hz` (low inclusive, high
    exclusive), except the last band's `high_hz`, which is inclusive too (so a band ending
    exactly at Nyquist doesn't silently drop that bin). Default bands (Hz), sub-bass through
    air: 20-60, 60-250, 250-500, 500-2000, 2000-4000, 4000-6000, 6000-20000. Empty bands (no
    bins fall in range) report `level_db = -inf`, `share_db = -inf`.

    Returns:
        bands (list of {low_hz, high_hz, level_db, share_db}):
            low_hz / high_hz (Hz): the band's edges, echoing `bands`.
            level_db (dB): that band's summed power, relative to a full-scale sine.
            share_db (dB): `10*log10(band_power / total_power)`, the band's power as a
                fraction of the whole spectrum's total power (<= 0 dB; 0 dB only if the band
                holds 100% of the signal's power).
    """
    freqs, level_db = _spectrum(audio, sample_rate, 1.0, None)
    power = _FS_SINE_MEAN_SQUARE * (10.0 ** (level_db / 10.0))
    total_power = float(np.sum(power))
    out = []
    n_bands = len(bands)
    for i, (low, high) in enumerate(bands):
        mask = (freqs >= low) & (freqs <= high if i == n_bands - 1 else freqs < high)
        band_power = float(np.sum(power[mask]))
        band_db = (
            10.0 * math.log10(band_power / _FS_SINE_MEAN_SQUARE) if band_power > 0 else -math.inf
        )
        share_db = (
            10.0 * math.log10(band_power / total_power)
            if band_power > 0 and total_power > 0
            else -math.inf
        )
        out.append(
            {
                "low_hz": float(low),
                "high_hz": float(high),
                "level_db": band_db,
                "share_db": share_db,
            }
        )
    return {"bands": out}


@_revision(1)
@_describe
def centroid(
    audio: np.ndarray,
    sample_rate: int,
    *,
    hop_s: float = 0.01,
    threshold_hz: float | None = None,
) -> dict[str, Any]:
    """Spectral centroid (power-weighted mean frequency) per STFT frame, over time.

    Uses an STFT with a hop of `round(hop_s * sample_rate)` samples and `n_fft = 2048` (fixed;
    time resolution is set by `hop_s`, frequency resolution by `n_fft` stays constant). A frame
    with zero power (silence) reports `nan` (there is no meaningful weighted mean of an empty
    distribution) — carried as `null` at the CLI boundary.

    If `threshold_hz` is given, `first_crossing_s` is the first time the centroid crosses it
    (linearly interpolated between the two surrounding frames, rising or falling, whichever
    happens first); `null` if it never crosses, or `threshold_hz` is not given.

    Returns:
        times_s (s): centre time of each STFT frame.
        centroid_hz (Hz): power-weighted mean frequency of each frame.
        first_crossing_s (s): first time `centroid_hz` crosses `threshold_hz`; `null` if
            `threshold_hz` is not given or never crossed.
    """
    hop = max(1, round(hop_s * sample_rate))
    n_fft = 2048
    times_s, freqs, level_db = _stft(audio, sample_rate, n_fft, hop)
    power = _FS_SINE_MEAN_SQUARE * (10.0 ** (level_db / 10.0))  # (freqs, times)
    total = np.sum(power, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        centroid_hz = np.where(total > 0, np.sum(power * freqs[:, None], axis=0) / total, np.nan)
    first_crossing_s = (
        _when_crosses(times_s, centroid_hz, threshold_hz) if threshold_hz is not None else None
    )
    return {
        "times_s": times_s.tolist(),
        "centroid_hz": centroid_hz.tolist(),
        "first_crossing_s": first_crossing_s,
    }


@_revision(1)
@_describe
def peaks(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n: int = 5,
    min_hz: float = 20.0,
    resolution_hz: float = 1.0,
) -> dict[str, Any]:
    """Top `n` spectral peaks by level, above `min_hz`, from the whole-file power spectrum.

    Finds local maxima in `spectrum(audio, sample_rate, resolution_hz)`'s `level_db`, then
    refines each peak's frequency with parabolic interpolation on the log-magnitude (fit a
    parabola through the peak bin and its two neighbours; the vertex offset gives a sub-bin
    correction). Accurate to a small fraction of a bin for well-separated, non-noisy tones —
    for a tone held exactly at a bin frequency the correction is 0; error grows if the true
    peak sits near a null between two close peaks, or if noise perturbs the neighbour bins.
    Fewer than `n` peaks are returned if the spectrum doesn't have that many local maxima above
    `min_hz`.

    Returns:
        peaks (list of {freq_hz, level_db}): up to `n` peaks, loudest first.
            freq_hz (Hz): sub-bin-refined peak frequency.
            level_db (dB): peak level relative to a full-scale sine.
    """
    freqs, level_db = _spectrum(audio, sample_rate, resolution_hz, None)
    valid = freqs >= min_hz
    f = freqs[valid]
    lv = level_db[valid]
    if len(lv) < 3:
        return {"peaks": []}
    peak_idx, _ = find_peaks(lv)
    if len(peak_idx) == 0:
        return {"peaks": []}
    order = peak_idx[np.argsort(lv[peak_idx])[::-1]][:n]
    out = []
    bin_hz = f[1] - f[0] if len(f) > 1 else 1.0
    for i in order:
        if i == 0 or i == len(lv) - 1:
            freq_hz = float(f[i])
            level = float(lv[i])
        else:
            y0, y1, y2 = lv[i - 1], lv[i], lv[i + 1]
            denom = y0 - 2 * y1 + y2
            delta = 0.5 * (y0 - y2) / denom if denom != 0 else 0.0
            delta = float(np.clip(delta, -0.5, 0.5))
            freq_hz = float(f[i] + delta * bin_hz)
            level = float(y1 - 0.25 * (y0 - y2) * delta)
        out.append({"freq_hz": freq_hz, "level_db": level})
    out.sort(key=lambda d: d["level_db"], reverse=True)
    return {"peaks": out[:n]}


@_revision(2)
@_describe
def stft(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 2048,
    hop: int = 512,
) -> dict[str, Any]:
    """Short-time Fourier transform magnitude, in dB, over time.

    Hann window of length `n_fft`, hop `hop` samples (overlap = `n_fft - hop`). Frame centre
    times run from near `t=0` (scipy's `boundary="zeros"` padding centres the first frame).
    `level_db` is power in dB relative to a full-scale sine (see module docstring), computed
    from the STFT magnitude as `|X|^2` scaled so a full-scale sine bin reads ~0 dB.

    Returns NumPy arrays directly; use analysis.image(result) for an SVG view. The CLI
    requires --out DIR for arrays and accepts --image to save both views. Silence remains
    -inf in the numeric matrix. Channels are summed; short inputs are zero-padded to keep
    the requested FFT size. Frames include the final padded hop, possibly past duration_s.
    Requires nonempty finite audio, positive integer sample_rate, n_fft >= 2 and
    1 <= hop <= n_fft. Revision 2 replaces the summary/file-only return and out parameter.

    Returns:
        times_s (seconds): frame-center times as a NumPy array.
        freqs_hz (Hz): linearly spaced FFT-bin centers as a NumPy array.
        level_db (dB re full-scale sine): matrix shaped (frequency_bins, time_frames).
        shape (bins, frames): `level_db`'s shape, `(len(freqs_hz), len(times_s))`.
        duration_s (s): the analysed signal's duration.
    """
    x = _features.mono(audio, sample_rate, average=False)
    _features.positive_int("n_fft", n_fft)
    _features.positive_int("hop", hop)
    if n_fft < 2 or hop > n_fft:
        raise ValueError("require n_fft >= 2 and hop <= n_fft")
    duration_s = len(x) / sample_rate
    frames = 1 + math.ceil(len(x) / hop)
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    times_s, freqs, level_db = _stft(x, sample_rate, n_fft, hop)
    level_db = level_db[:, :frames]
    return {
        "times_s": times_s[:frames],
        "freqs_hz": freqs,
        "level_db": level_db,
        "shape": list(level_db.shape),
        "duration_s": duration_s,
    }


@_revision(1)
@_describe
def mel(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 2048,
    hop: int = 512,
    n_mels: int = 128,
    fmin: float = 0.0,
    fmax: float | None = None,
) -> dict[str, Any]:
    """Mel power spectrogram as a NumPy matrix (CLI: use --out DIR).

    Channels are summed to mono without resampling or gain normalization. Uses librosa's
    Slaney Mel scale and area-normalized triangular filters on squared, unnormalized FFT
    magnitudes; values are features, not calibrated dBFS or whole-file mean-square power.
    Centered Hann frames, even n_fft >= 4, 1 <= hop <= n_fft, constant zero padding.
    fmin/fmax are Hz; fmax=None means Nyquist. Empty/nonfinite audio and invalid parameters
    raise ValueError. Short audio is zero-padded; silence produces zero power.

    Returns:
        times_s (seconds): frame centers, j*hop/sample_rate, including the endpoint if it
            falls on the hop grid. These are NumPy arrays, not JSON lists.
        freqs_hz (Hz): theoretical center of each triangular Mel filter, ascending.
        power (squared FFT magnitude per Hz): matrix shaped (n_mels, len(times_s));
            filter weights use Slaney area normalization. CLI requires --out for arrays.
    """
    x = _features.mono(audio, sample_rate, average=False)
    power, frequencies = _features.mel_power(x, sample_rate, n_fft, hop, n_mels, fmin, fmax)
    return {
        "times_s": _features.times(power.shape[1], sample_rate, hop),
        "freqs_hz": frequencies,
        "power": power,
    }


@_revision(1)
@_describe
def chroma(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 4096,
    hop: int = 512,
    tuning: float = 0.0,
) -> dict[str, Any]:
    """Twelve pitch-class energy features over time (CLI: use --out DIR).

    Uses the established chroma_stft definition on power spectra, summed mono channels, centered zero-padded
    Hann frames (even n_fft >= 4, 1 <= hop <= n_fft). No resampling or input normalization.
    tuning is a finite semitone offset from A440 (0 fixes equal temperament); it is not
    estimated here: `spectral.tuning` measures it and returns `offset_semitones`.
    Filters use librosa's octave weighting (ctroct=5, octwidth=2) and C-first ordering;
    each frame is divided by its largest bin. Silent frames remain zero. Short signals
    are zero-padded. Invalid/empty/nonfinite input raises ValueError.
    These are normalized pitch-class features, not chord, key or fundamental estimates.

    Returns:
        times_s (seconds): NumPy frame centers j*hop/sample_rate; endpoint included if
            on the grid, as in mel.
        pitch_classes (names): row labels C, C#, D, D#, E, F, F#, G, G#, A, A#, B.
        chroma (relative energy, 0..1): NumPy matrix (12, len(times_s)), max-normalized
            per frame. CLI requires --out for arrays.
    """
    if not np.isfinite(tuning):
        raise ValueError("tuning must be finite")
    x = _features.mono(audio, sample_rate, average=False)
    power = _features.power_spectrum(x, n_fft, hop)
    values = _features.chroma_power(power, sample_rate, n_fft, tuning)
    return {
        "times_s": _features.times(values.shape[1], sample_rate, hop),
        "pitch_classes": ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"],
        "chroma": values,
    }


@_revision(1)
@_describe
def tuning(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 8192,
    hop: int = 2048,
    fmin: float = 150.0,
    fmax: float = 4000.0,
    threshold_db: float = -40.0,
) -> dict[str, Any]:
    """How far the material sits from A440 equal temperament, as one offset in cents.

    Spectral peaks (local maxima of each centered Hann frame's power, refined by parabolic
    interpolation of log power, within `threshold_db` of the frame's strongest bin and between
    `fmin` and `fmax`) are reduced to their distance from the nearest equal-tempered semitone.
    The magnitude-weighted circular mean of those distances is the offset; frames more than
    60 dB below the loudest frame are ignored. Channels are summed; no resampling.
    This is one number for the whole signal: it is not a pitch, key or chord estimate, and it
    assumes the material keeps one reference throughout. Upper partials do not fall on the
    semitone grid (the 5th is 14 cents flat, the 7th 31), so expect a few cents of bias and a
    concentration below 1 on real instruments. Invalid/empty/nonfinite input raises ValueError.

    Returns:
        offset_cents (cents, -50..50): positive when the material is sharp of A440. `null`
            when no peak qualifies (silence).
        offset_semitones (semitones): the same value divided by 100, the unit `chroma`'s
            `tuning` takes. `null` with offset_cents.
        concentration (0..1): length of the weighted mean vector. About 0.01 for noise,
            0.15-0.25 for full-band recordings, above 0.8 for clean harmonic tones; a low
            value means the offset says little.
        peaks (count): spectral peaks used.
    """
    if not (np.isfinite(threshold_db) and threshold_db < 0):
        raise ValueError("threshold_db must be a finite negative number")
    x = _features.mono(audio, sample_rate, average=False)
    upper = _features.frequency_range(sample_rate, fmin, fmax)
    power = _features.power_spectrum(x, n_fft, hop)
    empty = {"offset_cents": None, "offset_semitones": None, "concentration": 0.0, "peaks": 0}
    loudest = float(power.max()) if power.size else 0.0
    if loudest <= 0.0:
        return empty
    log_power = 10.0 * np.log10(np.maximum(power, loudest * 1e-20))
    left, mid, right = log_power[:-2], log_power[1:-1], log_power[2:]
    bins = np.arange(1, power.shape[0] - 1, dtype=np.float64)[:, None]
    frame_peak = log_power.max(axis=0, keepdims=True)
    hz = bins * sample_rate / n_fft
    chosen = (
        (mid > left)
        & (mid >= right)
        & (mid >= frame_peak + threshold_db)
        & (frame_peak >= 10.0 * math.log10(loudest) - 60.0)
        & (hz >= fmin)
        & (hz <= upper)
    )
    if not chosen.any():
        return empty
    a, b, c = left[chosen], mid[chosen], right[chosen]
    curvature = a - 2.0 * b + c
    shift = np.where(curvature < 0, 0.5 * (a - c) / np.where(curvature < 0, curvature, -1.0), 0.0)
    frequency = (np.broadcast_to(bins, mid.shape)[chosen] + shift) * sample_rate / n_fft
    cents = 1200.0 * np.log2(frequency / 440.0)
    weights = 10.0 ** (b / 20.0)
    vector = np.sum(weights * np.exp(2j * np.pi * cents / 100.0)) / np.sum(weights)
    offset = float(np.angle(vector) / (2.0 * np.pi) * 100.0)
    return {
        "offset_cents": offset,
        "offset_semitones": offset / 100.0,
        "concentration": float(np.abs(vector)),
        "peaks": int(chosen.sum()),
    }


@_revision(1)
@_describe
def mfcc(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 2048,
    hop: int = 512,
    n_mels: int = 128,
    n_mfcc: int = 20,
    fmin: float = 0.0,
    fmax: float | None = None,
) -> dict[str, Any]:
    """Mel-frequency cepstral coefficients as a NumPy matrix (CLI: use --out DIR).

    Same summed-mono, centered Hann, zero-padded Mel power definition as mel; fmax=None
    means Nyquist. Convert power to dB (ref=1, amin=1e-10, top_db=80),
    then orthonormal DCT-II along Mel bands, retaining coefficients 0..n_mfcc-1 without
    liftering or coefficient normalization. Require 1 <= n_mfcc <= n_mels.
    Coefficients describe the spectral envelope; no similarity/classification is inferred.
    Silence is finite: coefficient 0 is -100*sqrt(n_mels), the others approximately zero.
    Empty/nonfinite audio and invalid parameters raise ValueError; short audio is padded.

    Returns:
        times_s (seconds): NumPy frame centers j*hop/sample_rate; endpoint included if
            on the grid, as in mel.
        coefficients (orthonormal DCT of log-Mel power): NumPy matrix
            (n_mfcc, len(times_s)), starting with coefficient 0; not dBFS.
            CLI requires --out for arrays.
    """
    _features.positive_int("n_mfcc", n_mfcc)
    _features.positive_int("n_mels", n_mels)
    if n_mfcc > n_mels:
        raise ValueError("n_mfcc must not exceed n_mels")
    x = _features.mono(audio, sample_rate, average=False)
    power, _ = _features.mel_power(x, sample_rate, n_fft, hop, n_mels, fmin, fmax)
    values = dct(_features.log_power(power), type=2, norm="ortho", axis=0)[:n_mfcc]
    return {
        "times_s": _features.times(values.shape[1], sample_rate, hop),
        "coefficients": values,
    }


@_revision(1)
@_describe
def cqt(
    audio: np.ndarray,
    sample_rate: int,
    *,
    hop: int = 512,
    fmin: float = 32.70319566257483,
    n_bins: int = 84,
    bins_per_octave: int = 12,
    filter_scale: float = 1.0,
) -> dict[str, Any]:
    """Constant-Q magnitude: frequency-dependent Hann windows on a logarithmic grid.

    Sum channels; no resampling, tuning estimation or input normalization. Centers
    fmin*2**(k/bins_per_octave), default C1 and seven octaves at 12 bins/octave.
    alpha=tanh(log(2)/bins_per_octave); window length ceil(filter_scale*sample_rate /
    (alpha*frequency)). Periodic Hann, offsets arange(length)-length//2, zero-padded
    edges; each complex sinusoidal filter has L1 norm 2. A resolved bin-centered
    real sinusoid therefore reads approximately its peak amplitude. These are
    features, not calibrated dBFS or librosa's length-scaled coefficients.
    Windows must be 4..1048576 samples; at most 4096 bins. Center plus 0.75 times
    nominal bandwidth must stay below Nyquist (Hann guard, not a brick-wall cutoff).
    Invalid/nonfinite/empty input raises ValueError. Silence returns zero magnitude.
    Low frequencies smear events across longer windows; no inverse/phase is returned.

    Returns:
        magnitude (amplitude feature): NumPy (n_bins, frames) nonnegative filter magnitudes.
        times_s (seconds): NumPy frame centers j*hop/sample_rate, through duration if on grid.
        freqs_hz (Hz): NumPy ascending geometric filter centers, in Hz.
        window_samples (samples): NumPy integer window length for each frequency.
        hop_samples (samples): requested positive integer hop, in samples.
        gamma_hz (Hz): 0.0; CQT equals vqt with gamma=0 for otherwise identical parameters.
    """
    from ._qtransform import transform

    return transform(audio, sample_rate, hop, fmin, n_bins, bins_per_octave, filter_scale, 0.0)


@_revision(1)
@_describe
def vqt(
    audio: np.ndarray,
    sample_rate: int,
    *,
    hop: int = 512,
    fmin: float = 32.70319566257483,
    n_bins: int = 84,
    bins_per_octave: int = 12,
    filter_scale: float = 1.0,
    gamma: float | None = None,
) -> dict[str, Any]:
    """Variable-Q magnitude with an explicit bandwidth offset gamma, in Hz.

    Same grid, summed channels, centered zero padding, Hann filters and magnitude
    units as cqt. Length=ceil(filter_scale*sample_rate/(alpha*frequency+gamma)),
    alpha=tanh(log(2)/bins_per_octave). gamma=None resolves to 24.7*alpha/0.108 (ERB
    convention); gamma=0 is exactly cqt. Larger gamma shortens low-frequency windows,
    improving time localization while reducing frequency selectivity. Require finite
    gamma >= 0 and cqt's window/band limits. This direct filter-bank transform does
    not reproduce librosa's recursive resampling/sparse approximation coefficientwise.

    Returns:
        magnitude (amplitude feature): NumPy (n_bins, frames), as in cqt.
        times_s (seconds): NumPy centered frame timestamps.
        freqs_hz (Hz): NumPy geometric filter centers.
        window_samples (samples): NumPy integer window length per frequency.
        hop_samples (samples): positive integer frame step.
        gamma_hz (Hz): resolved nonnegative bandwidth offset.
    """
    from ._qtransform import transform

    return transform(audio, sample_rate, hop, fmin, n_bins, bins_per_octave, filter_scale, gamma)


def _descriptor_result(values, field, valid, sample_rate, n_fft, hop):
    return {
        "times_s": _features.times(len(values), sample_rate, hop).tolist(),
        field: [float(v) if keep else None for v, keep in zip(values, valid)],
        "n_fft": int(n_fft),
        "hop_samples": int(hop),
    }


@_revision(1)
@_describe
def bandwidth(
    audio: np.ndarray, sample_rate: int, *, n_fft: int = 2048, hop: int = 512
) -> dict[str, Any]:
    """Power-weighted spectral standard deviation per frame, in Hz.

    Describes spread around the power-weighted centroid, not a filter's -3 dB width.
    Sum channels; centered periodic Hann frames with zero padding, even n_fft >= 4,
    1 <= hop <= n_fft. Frame centers j*hop/sample_rate stop at the original duration,
    matching mel/mfcc (legacy centroid has its own terminal-frame policy). Include DC
    and Nyquist. No resampling or DC removal. Zero-power frames return null, including
    opposite-phase channel cancellation. Values describe distribution, not mix quality.

    Returns:
        times_s (seconds): frame centers.
        bandwidth_hz (Hz): power-weighted standard deviation; null for zero power.
        n_fft (samples): transform size.
        hop_samples (samples): frame step.
    """
    power, valid = _features.power_distribution(audio, sample_rate, n_fft, hop)
    total = power.sum(axis=0)
    weights = np.divide(power, total, out=np.zeros_like(power), where=valid)
    frequencies = np.fft.rfftfreq(n_fft, 1 / sample_rate)[:, None]
    center = np.sum(weights * frequencies, axis=0)
    values = np.sqrt(np.sum(weights * (frequencies - center) ** 2, axis=0))
    return _descriptor_result(values, "bandwidth_hz", valid, sample_rate, n_fft, hop)


@_revision(1)
@_describe
def rolloff(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 2048,
    hop: int = 512,
    roll_percent: float = 0.85,
) -> dict[str, Any]:
    """Frequency below which a chosen fraction of frame spectral power accumulates.

    Uses bandwidth's summed channels, centered Hann framing and time grid. Include DC
    and Nyquist. roll_percent must be finite and strictly between 0 and 1. Select the
    first FFT bin whose cumulative power reaches the fraction; no interpolation.
    Zero-power frames return null. This is an energy percentile, not highest audible
    frequency or an automatic low-pass cutoff. Finite nonempty real audio only.

    Returns:
        times_s (seconds): frame centers.
        rolloff_hz (Hz): first bin reaching the power fraction; null for zero power.
        roll_percent (fraction): requested cumulative power fraction.
        n_fft (samples): transform size.
        hop_samples (samples): frame step.
    """
    if (
        isinstance(roll_percent, (bool, np.bool_))
        or not np.isfinite(roll_percent)
        or not 0 < roll_percent < 1
    ):
        raise ValueError("roll_percent must be finite and strictly between 0 and 1")
    power, valid = _features.power_distribution(audio, sample_rate, n_fft, hop)
    cumulative = np.cumsum(power, axis=0)
    indices = np.argmax(cumulative >= roll_percent * cumulative[-1], axis=0)
    values = np.fft.rfftfreq(n_fft, 1 / sample_rate)[indices]
    return {
        **_descriptor_result(values, "rolloff_hz", valid, sample_rate, n_fft, hop),
        "roll_percent": float(roll_percent),
    }


@_revision(1)
@_describe
def flatness(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 2048,
    hop: int = 512,
    floor_ratio: float = 1e-12,
) -> dict[str, Any]:
    """Geometric/arithmetic mean of frame power: spectral evenness on a 0..1 scale.

    Uses bandwidth's summed channels, centered Hann framing and time grid; DC and
    Nyquist included. Divide power by each frame's maximum, then floor bins at
    floor_ratio (finite, strictly between 0 and 1) before both means. This relative
    floor keeps the descriptor gain-invariant within floating-point range. Uniform
    spectra approach 1, concentrated spectra approach 0; not an instrument/noise label.
    Zero-power frames return null rather than a misleading flatness of 1.

    Returns:
        times_s (seconds): frame centers.
        flatness (ratio, 0..1): power flatness; null for zero-power frames.
        floor_ratio (fraction): minimum power relative to the frame peak.
        n_fft (samples): transform size.
        hop_samples (samples): frame step.
    """
    if (
        isinstance(floor_ratio, (bool, np.bool_))
        or not np.isfinite(floor_ratio)
        or not 0 < floor_ratio < 1
    ):
        raise ValueError("floor_ratio must be finite and strictly between 0 and 1")
    power, valid = _features.power_distribution(audio, sample_rate, n_fft, hop)
    bounded = np.maximum(power, floor_ratio)
    values = np.clip(np.exp(np.mean(np.log(bounded), axis=0)) / bounded.mean(axis=0), 0, 1)
    return {
        **_descriptor_result(values, "flatness", valid, sample_rate, n_fft, hop),
        "floor_ratio": float(floor_ratio),
    }


ANALYSES = (
    spectrum,
    band_levels,
    centroid,
    peaks,
    stft,
    mel,
    chroma,
    tuning,
    mfcc,
    cqt,
    vqt,
    bandwidth,
    rolloff,
    flatness,
)
