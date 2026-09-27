"""spectral: frequency-domain measurements — spectrum, band levels, centroid, peaks and STFT.

Every function here *reports* a measurement; none returns a pass/fail verdict — Tactus reports,
not blocks (see `docs/design.md`'s "驗證與觀察"). Each analysis takes `audio` in Tactus's
`(frames,)` or `(frames, channels)` float layout and `sample_rate` (matching `render`'s own
`sample_rate`); multi-channel input is summed to mono before analysis, because these are
single-number/curve measurements over the mixed signal, not a per-channel or stereo-field
report. `ANALYSES` lists the public analyses; each carries a `revision` int, bumped only when a
result's meaning changes.

Ported from the frequency-analysis probe's validated `tfreq.py` prototype (see
`docs/blueprints/thoughts/2026-09-27-frequency-analysis-probes.md`), without its `fundamental`/
`f0_over_time` pitch estimators: validation found `fundamental` within ±50 cents on only 47.5%
of unseen material (two SFZ bass patches carry a sub-octave layer louder than the fundamental
and defeat every method tried, not just this one), so there is no `pitch` category yet.
`spectrum`, `band_levels`, `centroid`, `peaks` and `stft` are computations of stated
definitions, not estimators, so they carry no equivalent overfitting risk.

dB reference throughout this module: 0 dB = the power of a full-scale (amplitude 1.0) sine
wave, i.e. mean-square 0.5.

Reads: numpy · scipy.signal
"""

from __future__ import annotations

import math
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import find_peaks, welch
from scipy.signal import stft as _scipy_stft

from ._revision import revision as _revision

_FS_SINE_MEAN_SQUARE = 0.5

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
    noverlap = n_fft - hop
    freqs, times_s, zxx = _scipy_stft(
        x, fs=rate, window="hann", nperseg=n_fft, noverlap=noverlap, boundary="zeros"
    )
    # scipy's stft normalizes so a full-scale sine's peak bin magnitude is 0.5 (half the
    # window-summed amplitude, matching a one-sided spectrum convention); power = |X|^2, and
    # dividing by _FS_SINE_MEAN_SQUARE (0.5) puts a full-scale sine at ~0 dB, matching `spectrum`.
    power = np.abs(zxx) ** 2
    level_db = _power_to_db(power * 2.0)
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


@_revision(1)
def stft(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 2048,
    hop: int = 512,
    out: str | None = None,
) -> dict[str, Any]:
    """Short-time Fourier transform magnitude, in dB, over time.

    Hann window of length `n_fft`, hop `hop` samples (overlap = `n_fft - hop`). Frame centre
    times run from near `t=0` (scipy's `boundary="zeros"` padding centres the first frame).
    `level_db` is power in dB relative to a full-scale sine (see module docstring), computed
    from the STFT magnitude as `|X|^2` scaled so a full-scale sine bin reads ~0 dB.

    The full `times_s`/`freqs_hz`/`level_db` arrays are large, so they are only returned when
    `out` names a directory to write them to (as `.npz`, arrays `times_s`, `freqs_hz`,
    `level_db`); the CLI passes its own `--out DIR` here. Without `out`, only a summary is
    returned, and `note` says so.

    Returns:
        file (path): `.npz` path holding `times_s`, `freqs_hz`, `level_db`; absent without
            `out`.
        shape (frames, bins): `level_db`'s shape, `(len(freqs_hz), len(times_s))`.
        duration_s (s): the analysed signal's duration.
        note (text): present, and explains how to get the full arrays, only when `out` was not
            given.
    """
    times_s, freqs, level_db = _stft(audio, sample_rate, n_fft, hop)
    shape = [len(freqs), len(times_s)]
    duration_s = len(_to_mono(audio)) / sample_rate if sample_rate else 0.0
    if out is None:
        return {
            "shape": shape,
            "duration_s": duration_s,
            "note": "pass --out DIR (CLI) or out=PATH (library) to write the full "
            "times_s/freqs_hz/level_db arrays as .npz",
        }
    out_path = Path(out)
    np.savez(out_path, times_s=times_s, freqs_hz=freqs, level_db=level_db)
    return {"file": str(out_path), "shape": shape, "duration_s": duration_s}


ANALYSES = (spectrum, band_levels, centroid, peaks, stft)
