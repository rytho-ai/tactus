"""level: whole-signal amplitude — loudness, peaks, RMS and clipping.

Every function here *reports* a measurement; none returns a pass/fail verdict — Tactus
reports, not blocks (see `docs/design.md`'s "驗證與觀察"). Works and Agents apply their own
thresholds. Each analysis takes `audio` in Tactus's `(frames,)` or `(frames, channels)` float
layout and `sample_rate` (matching `render`'s own `sample_rate`), and returns a JSON-ready
dict. `ANALYSES` lists the public analyses; each carries a `revision` int, bumped only when a
result's meaning changes.

Ported from the audio-analysis probe's `tanalysis.py` prototype (see
`docs/blueprints/plans/2026-09-27-audio-analysis-measurements.md`), keeping its flat-run
definition. Stereo-field and dropout measurements (`dc_offset`, `correlation_windows`,
`silent_runs`) were cut from that prototype port; onsets and beat tracking are not part of
this package yet.

Reads: numpy · scipy.signal · pyloudnorm
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pyloudnorm as pyln
from scipy.signal import resample_poly

from ._revision import revision as _revision


def _as_2d(audio: np.ndarray) -> np.ndarray:
    """Tactus `(frames,)` or `(frames, channels)` as `(frames, channels)`, channels >= 1."""
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if x.ndim != 2:
        raise ValueError(f"audio must be 1-D or 2-D (frames[, channels]), got shape {x.shape}")
    return x


def _sample_peak_dbfs(audio: np.ndarray) -> float:
    x = np.asarray(audio, dtype=np.float64)
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    return 20 * math.log10(peak) if peak > 0 else -math.inf


def _true_peak_dbtp(audio: np.ndarray, sample_rate: int, factor: int) -> float:
    x = np.asarray(audio, dtype=np.float64)
    up = resample_poly(x, factor, 1, axis=0)
    peak = float(np.max(np.abs(up))) if up.size else 0.0
    return 20 * math.log10(peak) if peak > 0 else -math.inf


def _integrated_lufs(audio: np.ndarray, sample_rate: int) -> float | None:
    x = np.asarray(audio, dtype=np.float64)
    meter = pyln.Meter(sample_rate)
    try:
        value = meter.integrated_loudness(x)
    except ValueError:
        return None
    return float(value) if math.isfinite(value) else None


def _rms_dbfs(audio: np.ndarray) -> float:
    x = np.asarray(audio, dtype=np.float64)
    r = math.sqrt(float(np.mean(np.square(x)))) if x.size else 0.0
    return 20 * math.log10(r) if r > 0 else -math.inf


def _flat_runs(audio: np.ndarray, min_length: int, above: float) -> dict[str, Any]:
    x = _as_2d(audio)
    count = 0
    longest = 0
    first: list[tuple[int, int, int]] = []
    for ch in range(x.shape[1]):
        v = np.abs(x[:, ch])
        # A run continues while the sample stays above `above` and equals the previous one.
        same = np.zeros(len(v), dtype=bool)
        same[1:] = (v[1:] > above) & (v[:-1] > above) & (np.abs(v[1:] - v[:-1]) < 1e-9)
        starts = np.flatnonzero((v > above) & ~same)
        if starts.size == 0:
            continue
        # Run ends: the next start of any run (above or not) bounds each run.
        breaks = np.flatnonzero(~same)
        ends = np.append(breaks[1:], len(v))
        lengths = ends[np.searchsorted(breaks, starts)] - starts
        keep = lengths >= min_length
        count += int(np.count_nonzero(keep))
        if np.any(keep):
            longest = max(longest, int(lengths[keep].max()))
        first.extend((ch, int(s), int(n)) for s, n in zip(starts[keep], lengths[keep]))
    first.sort(key=lambda item: (item[1], item[0]))
    return {"count": count, "longest": longest, "first_positions": first[:10]}


@_revision(1)
def loudness(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    """Integrated (gated) loudness, ITU-R BS.1770 via pyloudnorm.

    This is NOT the same number as `rms`: it K-weights (de-emphasizes deep bass, shelves up
    high frequencies) and excludes quiet blocks (absolute -70 LUFS gate, then a relative -10 LU
    gate) that a plain whole-file RMS would still average in — long quiet stretches make
    ungated RMS read quieter than the gated loudness a listener/meter reports, and the
    K-weight filter can push the two apart even with no silence at all (e.g. a bass-heavy
    signal reads louder in RMS than in LUFS).

    Returns:
        integrated_lufs (LUFS): gated integrated loudness. `null` for digital silence or
            audio too short to gate (pyloudnorm needs at least one 400ms gating block).
    """
    return {"integrated_lufs": _integrated_lufs(audio, sample_rate)}


@_revision(1)
def true_peak(audio: np.ndarray, sample_rate: int, *, factor: int = 4) -> dict[str, Any]:
    """BS.1770-4 true peak: `factor`x-oversample (polyphase FIR, `scipy.signal.resample_poly`)
    and take the peak absolute value of the oversampled signal.

    Catches inter-sample peaks a sample-domain peak reading misses (a full-scale-looking
    waveform can still ring higher between samples).

    Returns:
        true_peak_dbtp (dBTP): peak absolute value of the oversampled signal, `-inf` for
            digital silence.
    """
    return {"true_peak_dbtp": _true_peak_dbtp(audio, sample_rate, factor)}


@_revision(1)
def sample_peak(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    """Peak absolute sample value across every channel.

    Returns:
        sample_peak_dbfs (dBFS): peak absolute sample value, `-inf` for digital silence.
    """
    return {"sample_peak_dbfs": _sample_peak_dbfs(audio)}


@_revision(1)
def rms(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    """Plain whole-signal RMS (all samples, all channels, unweighted, ungated).

    See `loudness` for why this is not a loudness measurement.

    Returns:
        rms_dbfs (dBFS): root-mean-square level, `-inf` for digital silence.
    """
    return {"rms_dbfs": _rms_dbfs(audio)}


@_revision(1)
def clipping(
    audio: np.ndarray, sample_rate: int, *, min_length: int = 4, above: float = 0.5
) -> dict[str, Any]:
    """Runs of consecutive samples in one channel that are exactly identical in absolute value
    and above `above` (a `np.clip`-style flat top).

    Returns:
        count (runs): number of runs with length >= `min_length`.
        longest (samples): length of the longest such run, 0 if none.
        first_positions (list of [channel, start_frame, length]): up to the first 10 such
            runs, in frame order.
    """
    return _flat_runs(audio, min_length, above)


ANALYSES = (loudness, true_peak, sample_peak, rms, clipping)
