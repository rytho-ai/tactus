"""level: whole-signal and time-varying loudness, peaks, RMS, crest factor and clipping.

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
this category.

New curves use complete windows and window-end timestamps. LUFS sums channel powers;
RMS averages powers; peaks take the maximum across channels. No mono downmix is applied.
The native curve/LRA algorithms use NumPy/SciPy; integrated loudness preserves
the legacy pyloudnorm numerical definition. See experiments/level-curves for definitions and bounded verification.

Reads: numpy · scipy.signal · _level
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.signal import resample_poly

from . import _level as _windows
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
    return _windows.integrated_loudness(audio, sample_rate)


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
    """Integrated (gated) loudness, ITU-R BS.1770 with the legacy RBJ K-weighting definition.

    This is NOT the same number as `rms`: it K-weights (de-emphasizes deep bass, shelves up
    high frequencies) and excludes quiet blocks (absolute -70 LUFS gate, then a relative -10 LU
    gate) that a plain whole-file RMS would still average in — long quiet stretches make
    ungated RMS read quieter than the gated loudness a listener/meter reports, and the
    K-weight filter can push the two apart even with no silence at all (e.g. a bass-heavy
    signal reads louder in RMS than in LUFS).

    Returns:
        integrated_lufs (LUFS): gated integrated loudness. `null` for digital silence or
            audio too short to gate (at least one 400ms gating block is needed).
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


@_revision(1)
def momentary_loudness(
    audio: np.ndarray, sample_rate: int, *, hop_s: float = 0.01
) -> dict[str, Any]:
    """Momentary loudness curve: ungated 400 ms rectangular K-weighted windows.

    NumPy/SciPy implementation of the EBU Tech 3341 definition, using De Man biquads.
    Filters run continuously from zero state across the supplied audio, not reset per window.
    Sum weighted channel powers, without mono downmix: order L, R, C, Ls, Rs (no LFE),
    weights 1, 1, 1, 1.41, 1.41. Accepts 1..5 channels and integer sample_rate >= 8000.
    New curves use the De Man coefficient design; existing integrated loudness retains
    the legacy RBJ design, so small filter-response differences are expected.
    Only complete windows are measured, starting at frame 0, with no padding; discard
    partial tails. Window/hop sizes use round(seconds*sample_rate), with 1 <= hop <= window.
    Default 10 ms hop resolves short level changes. Larger hops can miss brief maxima.
    Empty/nonfinite/malformed audio and invalid parameters raise ValueError.

    Returns:
        times_s (seconds): window END positions, aligned with loudness_lufs.
        loudness_lufs (LUFS): ungated values; null for zero-energy windows. Audio shorter
            than 400 ms yields empty times/values. Quiet finite values are not gated out.
        window_samples (samples): effective rectangular window size.
        hop_samples (samples): effective hop after rounding.
    """
    return _windows.loudness_curve(audio, sample_rate, 0.4, hop_s)


@_revision(1)
def short_term_loudness(
    audio: np.ndarray, sample_rate: int, *, hop_s: float = 0.1
) -> dict[str, Any]:
    """Short-term loudness curve: ungated 3 s rectangular K-weighted windows.

    Same continuous filters, weighted channel powers, validation and complete-window
    policy as momentary_loudness; L, R, C, Ls, Rs order, no LFE, sample_rate >= 8000.
    A 100 ms default hop samples the 3 s curve at 10 Hz. No gain change or resampling.
    Empty/nonfinite/malformed input and invalid parameters raise ValueError.

    Returns:
        times_s (seconds): window END positions from 3 s, not centers or onset times.
        loudness_lufs (LUFS): ungated values; null for zero energy. Audio shorter than
            3 s yields empty times/values. No padding; partial trailing windows discarded.
        window_samples (samples): round(3*sample_rate).
        hop_samples (samples): round(hop_s*sample_rate), between 1 and window_samples.
    """
    return _windows.loudness_curve(audio, sample_rate, 3.0, hop_s)


@_revision(1)
def loudness_range(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    """Loudness range (LRA): gated spread of short-term loudness, in LU.

    EBU Tech 3342 algorithm: native continuous K-weighting as in momentary_loudness,
    3 s windows with a floor(0.1*sample_rate) hop (at least 10 Hz); append 1.5 s of silence
    for file-based evaluation. This padding is specific to LRA, not the curve APIs.
    Keep levels >= -70 LUFS, then >= their energy-mean loudness minus 20 LU. Take the
    95th minus 10th percentile, choosing nearest sorted indices (ties upward).
    Channel order L, R, C, Ls, Rs, no LFE, sample_rate >= 8000. Original audio shorter
    than 3 s, silence or all levels below the absolute gate yields null LRA/percentiles.
    Values for audio under 60 s are provisional. This measures loudness variation, not
    crest factor, transient punch or mix quality. Invalid/empty/nonfinite input raises ValueError.

    Returns:
        lra_lu (LU): high_lufs - low_lufs, or null when unavailable.
        low_lufs (LUFS): gated 10th percentile level, or null.
        high_lufs (LUFS): gated 95th percentile level, or null.
        relative_gate_lufs (LUFS): computed relative gate before combining with -70 LUFS.
        gated_blocks (count): number of short-term values surviving both gates.
        duration_s (seconds): original audio duration, excluding appended silence.
        provisional (bool): true when original duration is under 60 s or LRA is unavailable.
    """
    x = _windows.audio_frames(audio, sample_rate, loudness=True)
    duration = len(x) / sample_rate
    values = np.empty(0)
    if duration >= 3:
        padded = np.pad(x, ((0, round(1.5 * sample_rate)), (0, 0)))
        starts, window, _ = _windows.window_grid(
            len(padded), sample_rate, 3.0, (sample_rate // 10) / sample_rate
        )
        power = _windows.sample_power(padded, sample_rate, weighted=True)
        values = _windows.decibels(_windows.window_mean(power, starts, window), offset=-0.691)
    result = _windows.range_statistics(values)
    return {
        **result,
        "duration_s": duration,
        "provisional": duration < 60 or result["lra_lu"] is None,
    }


@_revision(1)
def rms_curve(
    audio: np.ndarray, sample_rate: int, *, window_s: float = 0.05, hop_s: float = 0.01
) -> dict[str, Any]:
    """RMS curve over rectangular windows, unweighted and ungated.

    Average squared samples across time AND channels, with no mono downmix. 0 dBFS means
    RMS amplitude 1; a full-scale sine reads about -3.0103 dBFS. Use (frames,) or
    (frames, channels) real finite audio and a positive integer sample_rate. No resampling,
    normalization or padding. Window/hop seconds round to samples; 1 <= hop <= window.
    Windows start at sample 0; incomplete trailing windows are discarded.
    Invalid/empty/nonfinite inputs raise ValueError.

    Returns:
        times_s (seconds): window END positions.
        rms_dbfs (dBFS): one value per window; null for zero energy. Audio shorter than
            a window yields empty times/values. No silence gate or arbitrary dB floor.
        window_samples (samples): effective window size after rounding.
        hop_samples (samples): effective hop size after rounding.
    """
    x = _windows.audio_frames(audio, sample_rate)
    starts, window, hop = _windows.window_grid(len(x), sample_rate, window_s, hop_s)
    values = _windows.decibels(_windows.amplitude_windows(x, starts, window, hop, peak=False))
    return _windows.curve_result(values, "rms_dbfs", starts, window, hop, sample_rate)


@_revision(1)
def peak_curve(
    audio: np.ndarray, sample_rate: int, *, window_s: float = 0.05, hop_s: float = 0.01
) -> dict[str, Any]:
    """Sample-peak curve: maximum absolute sample across each window and all channels.

    Same validated input, rounded window/hop and complete-window policy as rms_curve.
    Sample peaks do not include intersample peaks; use true_peak for the whole-file
    oversampled measurement. No downmix, resampling, padding or normalization.

    Returns:
        times_s (seconds): window END positions.
        sample_peak_dbfs (dBFS): 20*log10(peak amplitude), null for zero-energy windows.
            Audio shorter than a window yields empty times/values; partial tails discarded.
        window_samples (samples): effective window size after rounding.
        hop_samples (samples): effective hop size after rounding.
    """
    x = _windows.audio_frames(audio, sample_rate)
    starts, window, hop = _windows.window_grid(len(x), sample_rate, window_s, hop_s)
    peaks = _windows.amplitude_windows(x, starts, window, hop, peak=True)
    with np.errstate(divide="ignore"):
        values = 20 * np.log10(peaks)
    return _windows.curve_result(values, "sample_peak_dbfs", starts, window, hop, sample_rate)


@_revision(1)
def crest_factor(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    """Whole-input sample crest factor: 20*log10(sample peak / RMS), in dB.

    Peak is the maximum absolute sample across all channels; RMS averages squared
    samples across time AND channels. No downmix or DC removal. A sine is about
    3.01 dB and constant-magnitude audio is 0 dB. Silence returns null. This is not
    true-peak minus integrated loudness (PLR), LRA, or a perceptual punch score.
    Finite nonempty (frames,) or (frames, channels); positive integer sample_rate.

    Returns:
        crest_factor_db (dB): sample-peak to RMS ratio, or null for silence.
    """
    x = _windows.audio_frames(audio, sample_rate)
    peak = np.max(np.abs(x))
    if peak == 0:
        return {"crest_factor_db": None}
    # Scaling cancels in the ratio and avoids squaring overflow/underflow.
    mean_power = np.mean(np.square(x / peak))
    return {"crest_factor_db": float(-10 * np.log10(mean_power))}


@_revision(1)
def crest_factor_curve(
    audio: np.ndarray, sample_rate: int, *, window_s: float = 0.05, hop_s: float = 0.01
) -> dict[str, Any]:
    """Sample-peak/RMS crest factor in complete rectangular windows, in dB.

    Same channel convention as crest_factor, with no downmix or DC removal. Window/hop
    sizes round to samples, with 1 <= hop <= window; discard partial tails. Timestamps
    mark window ends, as in rms_curve/peak_curve. Short input returns an empty curve;
    zero-energy windows return null. No whole-file prefix-sum subtraction. Invalid
    inputs/parameters or unrepresentable squared power raise ValueError.
    Values depend on window size and are not loudness range or a punch/quality verdict.

    Returns:
        times_s (seconds): window END times.
        crest_factor_db (dB): sample-peak/RMS ratio per window; null for silence.
        window_samples (samples): rounded window size.
        hop_samples (samples): rounded hop size.
    """
    x = _windows.audio_frames(audio, sample_rate)
    starts, window, hop = _windows.window_grid(len(x), sample_rate, window_s, hop_s)
    power = _windows.amplitude_windows(x, starts, window, hop, peak=False)
    peaks = _windows.amplitude_windows(x, starts, window, hop, peak=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        values = 20 * np.log10(peaks) - 10 * np.log10(power)
    # Very small finite samples can underflow when squared; recompute just those
    # windows relative to their own peak so quiet tails remain meaningful.
    for i in np.flatnonzero((power == 0) & (peaks > 0)):
        scaled = x[starts[i] : starts[i] + window] / peaks[i]
        values[i] = -10 * np.log10(np.mean(np.square(scaled)))
    values = np.maximum(values, 0)
    return _windows.curve_result(values, "crest_factor_db", starts, window, hop, sample_rate)


ANALYSES = (
    loudness,
    true_peak,
    sample_peak,
    rms,
    clipping,
    momentary_loudness,
    short_term_loudness,
    loudness_range,
    rms_curve,
    peak_curve,
    crest_factor,
    crest_factor_curve,
)
