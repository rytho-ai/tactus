"""rhythm: beat/tempo estimates and owned SuperFlux-style onset observations.

Input uses Tactus's (frames,) or (frames, channels) layout. pyqmdsp averages channels
to mono and analyzes at the supplied sample rate. pyqmdsp owns beat framing, algorithm
defaults and time conversion. Onsets offer Mel and log-frequency SuperFlux frontends,
with shared explicit framing/selection and no learned models. Both paths return JSON-ready values.

These are estimates, not a bar grid or downbeat detector. Analyze outside render and
freeze accepted results as material or source constants before using them for cuts.
ANALYSES supplies the functions for the generated CLI; revision marks result semantics.

Reads: numpy · pyqmdsp · _features · _onset · _revision
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pyqmdsp

from . import _features, _onset
from ._revision import revision as _revision
from ._schema import describe as _describe


@_revision(1)
@_describe
def beats(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    """Estimate beat times using qm-dsp's DetectionFunction and TempoTrackV2.

    Channels are averaged to mono, without resampling or normalization. Short material
    (roughly 7.45 seconds or less of active audio) and silence return empty arrays and
    null BPM: the tracker needs more than 640 detection-function frames after trimming.
    Empty/nonfinite audio and invalid dimensions or sample rates raise ValueError.
    Beat estimates carry no confidence, meter or downbeat position.

    Returns:
        beats_s (seconds): estimated beat times relative to the audio start, earliest first.
        bpm (BPM): median instantaneous tempo, null if fewer than two beats were found.
        tempo_curve (BPM): 60 / (beats_s[i+1] - beats_s[i]) for each consecutive beat pair;
            one value shorter than beats_s, or empty if fewer than two beats were found.
    """
    result = pyqmdsp.beats(audio, sample_rate)
    return {
        "beats_s": result["beats_s"].tolist(),
        "bpm": result["bpm"] if len(result["beats_s"]) >= 2 else None,
        "tempo_curve": result["tempo_curve"].tolist(),
    }


def _onset_envelope(
    audio,
    sample_rate,
    n_fft,
    hop_s,
    n_mels,
    fmin,
    fmax,
    lag,
    max_size,
    filterbank,
    bands_per_octave,
):
    if filterbank not in ("mel", "log"):
        raise ValueError("filterbank must be 'mel' or 'log'")
    _features.positive_int("n_mels", n_mels)
    _features.positive_int("bands_per_octave", bands_per_octave)
    x = _features.mono(audio, sample_rate, average=True)
    if not np.isfinite(hop_s) or hop_s <= 0:
        raise ValueError("hop_s must be finite and positive")
    hop = max(1, round(hop_s * sample_rate))
    _features.positive_int("lag", lag)
    _features.positive_int("max_size", max_size)
    upper = min(16000.0, sample_rate / 2) if fmax is None else fmax
    if filterbank == "mel":
        spectrum, _ = _features.mel_power(x, sample_rate, n_fft, hop, n_mels, fmin, upper)
    else:
        spectrum = _features.log_magnitude(
            x, sample_rate, n_fft, hop, bands_per_octave, fmin, upper
        )
    envelope = _onset.strength(spectrum, n_fft, hop, lag, max_size, compressed=filterbank == "log")
    return x, envelope, hop, float(upper)


@_revision(1)
@_describe
def onset_strength(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 1024,
    hop_s: float = 0.005,
    n_mels: int = 138,
    filterbank: str = "mel",
    bands_per_octave: int = 24,
    fmin: float = 27.5,
    fmax: float | None = None,
    lag: int = 2,
    max_size: int = 3,
) -> dict[str, Any]:
    """Owned SuperFlux onset strength with filterbank="mel" or "log", no learned weights.

    Channels are averaged to mono without resampling/normalization. Centered, zero-padded
    Hann frames (even n_fft >= 4), hop=max(1, round(hop_s*sample_rate)) <= n_fft.
    filterbank="mel" (default): Slaney-area-normalized Mel power becomes dB
    (ref=max, amin=1e-10, top_db=80), using n_mels; bands_per_octave is inactive.
    filterbank="log": A440-aligned log-frequency triangles, rounded unique FFT bins,
    unit-height, excluding Nyquist; log10(1 + filtered magnitude). bands_per_octave
    sets requested density (default 24); n_mels is inactive. Both density parameters
    must be positive integers. Log requires fmin > 0 and a resolvable triangle;
    only centers inside [fmin, fmax] survive. It is not a CQT.
    Positive differences from a frequency-maximum-filtered reference lag frames earlier
    are averaged over bands. max_size=1 disables vibrato suppression. fmax=None resolves
    to min(16000, Nyquist); fmin/fmax are Hz. The frontend compensates lag and centered framing
    on the envelope's hop grid. Both variants use Tactus framing and peak picking,
    not the original SuperFlux application's complete conventions. They can detect
    different events; neither is guaranteed more accurate. Low FFT resolution can
    leave some Mel filters empty (a warning is emitted).
    Silence and signals with too few frames for lag produce zero strength. Invalid,
    empty or nonfinite input raises ValueError. Strength is not a probability.

    Returns:
        times_s (seconds): envelope timestamps j*hop_samples/sample_rate; endpoint
            included if on the grid. Timing is frame-based, not sample-accurate.
        strength (mean positive compressed-band difference): nonnegative curve;
            Mel uses dB, log uses log10(1+magnitude). These units are not comparable.
        hop_samples (samples): actual integer frame step after rounding hop_s.
        fmax_hz (Hz): resolved upper filterbank bound.
    """
    _, envelope, hop, upper = _onset_envelope(
        audio,
        sample_rate,
        n_fft,
        hop_s,
        n_mels,
        fmin,
        fmax,
        lag,
        max_size,
        filterbank,
        bands_per_octave,
    )
    return {
        "times_s": _features.times(len(envelope), sample_rate, hop).tolist(),
        "strength": envelope.tolist(),
        "hop_samples": hop,
        "fmax_hz": upper,
    }


@_revision(1)
@_describe
def onsets(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = 1024,
    hop_s: float = 0.005,
    n_mels: int = 138,
    filterbank: str = "mel",
    bands_per_octave: int = 24,
    fmin: float = 27.5,
    fmax: float | None = None,
    lag: int = 2,
    max_size: int = 3,
    delta: float = 0.07,
    min_interval_s: float = 0.03,
    backtrack: bool = False,
) -> dict[str, Any]:
    """Candidate onset times from Mel or log-frequency SuperFlux and peak picking.

    Uses onset_strength's averaged mono, centered Hann framing and compression:
    filterbank="mel" uses n_mels (power/dB); "log" uses bands_per_octave
    (log-frequency magnitude/log10(1+x)). The other density parameter is inactive.
    Log requires fmin > 0 and a resolvable triangle. Mel remains the default. Peak picking normalizes the strength curve to 0..1.
    delta is a nonnegative threshold above the local mean (lower detects more events).
    Peaks use the preceding 30 ms maximum and +/-100 ms mean, rounded to hop frames.
    min_interval_s >= 0 sets wait=floor(min_interval_s*sample_rate/hop_samples): selected
    peaks must be more than wait frames apart. Default settings can merge fast flams/rolls.
    backtrack=True moves markers to preceding minima of the strength curve, then removes
    duplicate markers; this can reduce their spacing. It changes marker meaning and does
    not guarantee precise slice boundaries. Leading attacks, soft onsets and ghost notes
    can be missed. No 2 ms accuracy, beat grid or transient-boundary guarantee is made.
    Silence/too-short signals return no events. Invalid/empty/nonfinite inputs raise
    ValueError. Accepted markers can be frozen as material or source constants.

    Returns:
        onsets_s (seconds): sorted unique candidate times in [0, audio duration), on the
            hop grid, optionally backtracked; no confidence/probability is attached.
        hop_samples (samples): actual integer frame step after rounding hop_s.
        fmax_hz (Hz): resolved upper filterbank bound, min(16000, Nyquist) when fmax=None.
    """
    if not np.isfinite(delta) or delta < 0:
        raise ValueError("delta must be finite and nonnegative")
    if not np.isfinite(min_interval_s) or min_interval_s < 0:
        raise ValueError("min_interval_s must be finite and nonnegative")
    if not isinstance(backtrack, (bool, np.bool_)):
        raise TypeError("backtrack must be a boolean")
    x, envelope, hop, upper = _onset_envelope(
        audio,
        sample_rate,
        n_fft,
        hop_s,
        n_mels,
        fmin,
        fmax,
        lag,
        max_size,
        filterbank,
        bands_per_octave,
    )
    frames = _onset.pick(envelope, sample_rate, hop, delta, min_interval_s, backtrack)
    frames = np.unique(frames[frames * hop < len(x)])
    return {
        "onsets_s": (frames * hop / sample_rate).tolist(),
        "hop_samples": hop,
        "fmax_hz": upper,
    }


@_revision(1)
@_describe
def tempogram(
    audio: np.ndarray,
    sample_rate: int,
    *,
    hop_s: float = 0.01,
    window_s: float = 4.0,
    bpm_min: float = 30.0,
    bpm_max: float = 300.0,
) -> dict[str, Any]:
    """Autocorrelation tempogram from the owned Mel SuperFlux onset envelope.

    Uses onset_strength defaults except hop_s (default 10 ms); channels are averaged.
    Hop is rounded to samples, no more than 1024. Local periodic Hann window length
    round(window_s*sample_rate/hop_samples), at least 4 and at most 65536 frames.
    Windows center on each onset frame, zero-padded at both ends. Linear (not circular)
    autocorrelation is divided by each window's zero-lag energy; silence remains zero.
    Keep positive integer lags whose BPM=60*sample_rate/(hop_samples*lag) is within
    [bpm_min, bpm_max], ascending in BPM. Rows are NOT uniformly spaced in BPM.
    No interpolation, prior, tempo selection or beat positions; half/double-time
    alternatives can coexist. Short inputs are padded and can lack useful context.
    Finite 0 < bpm_min < bpm_max required; reject ranges with no available lag.

    Returns:
        tempogram (relative periodicity): NumPy (tempo_rows, time_frames) relative periodicity, 0..1.
        times_s (seconds): NumPy onset-grid timestamps, seconds.
        bpms (BPM): NumPy ascending BPM centers for each row.
        lags (onset frames): NumPy integer onset-frame lags corresponding to bpms.
        hop_samples (samples): actual integer onset hop in samples.
        window_frames (onset frames): actual integer autocorrelation window length.
    """
    from ._tempogram import autocorrelation

    _features.positive_int("sample_rate", sample_rate)
    if not np.isfinite(hop_s) or hop_s <= 0:
        raise ValueError("hop_s must be finite and positive")
    hop = max(1, round(hop_s * sample_rate))
    if hop > 1024:
        raise ValueError("hop_s must resolve to no more than 1024 samples")
    if not np.isfinite(window_s) or window_s <= 0:
        raise ValueError("window_s must be finite and positive")
    length = window_s * sample_rate / hop
    if not 4 <= length <= 65536:
        raise ValueError("window_s must resolve to 4..65536 onset frames")
    window = round(length)
    if not (np.isfinite(bpm_min) and np.isfinite(bpm_max) and 0 < bpm_min < bpm_max):
        raise ValueError("require finite 0 < bpm_min < bpm_max")
    lags = np.arange(window - 1, 0, -1)
    bpms = 60 * sample_rate / (hop * lags)
    keep = (bpms >= bpm_min) & (bpms <= bpm_max)
    if not keep.any():
        raise ValueError("BPM range contains no available lag; change range/window_s")
    envelope = onset_strength(audio, sample_rate, hop_s=hop_s)
    lags, bpms = lags[keep], bpms[keep]
    return {
        "tempogram": autocorrelation(np.asarray(envelope["strength"]), window, lags),
        "times_s": np.asarray(envelope["times_s"]),
        "bpms": bpms,
        "lags": lags,
        "hop_samples": hop,
        "window_frames": window,
    }


ANALYSES = (beats, onset_strength, onsets, tempogram)
