"""Optional owned audio processing, using NumPy/SciPy/Numba and explicit filter state.

Arrays use (frames,) or (frames, channels), with finite real samples and retained
headroom. Functions allocate float64 outputs without mutating audio or caller state.
Gain/pan accept scalar or per-frame controls; fade applies to a complete clip. Biquad
returns (audio, state) for explicit block continuation. No hidden chain or shared state.
Duck/delay/lowpass/saturate process complete clips, resetting on each call; they accept
external detectors or per-frame controls without imposing a composition/processor model.
Delay returns only the delayed signal, with explicitly requested tail duration. Saturate
owns its oversampling/alignment and tanh/clip/fold transfer, not a loudness-normalization policy.
Crossover returns LR4 low/high branches. Crossfade delay keeps two fractional heads
fixed during retiming, with explicit transition length and latest-request behavior.
Varispeed and RMS fitting retain their original float32 contracts; fx re-exports them.
Svf generalizes the automated lowpass recurrence to four modes with per-frame cutoff/Q.
Spectral wraps a caller transform in phase-vocoder analysis/overlap-add resynthesis.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from scipy.signal import butter, lfilter, resample_poly, sosfilt

from ._biquad import coefficients
from ._dsp_kernels import (
    crossfade_fractional_delay,
    duck_envelope,
    fractional_delay,
    variable_svf,
)

__all__ = [
    "biquad",
    "crossfade_delay",
    "crossover",
    "delay",
    "duck",
    "fade",
    "fit_rms",
    "gain",
    "lowpass",
    "pan",
    "saturate",
    "spectral",
    "svf",
    "varispeed",
]


_FIT_RMS_WINDOW_MS = 5.0


def _audio(audio):
    x = np.asarray(audio)
    if x.ndim not in (1, 2) or (x.ndim == 2 and x.shape[1] < 1):
        raise ValueError("audio must have shape (frames,) or (frames, channels)")
    if x.dtype.kind not in "fiu" or not np.isfinite(x).all():
        raise ValueError("audio must contain finite real samples")
    return np.asarray(x, dtype=np.float64)


def _rate(sample_rate):
    if (
        isinstance(sample_rate, (bool, np.bool_))
        or not isinstance(sample_rate, (int, np.integer))
        or sample_rate <= 0
    ):
        raise ValueError("sample_rate must be a positive integer")


def _control(value, frames, name):
    raw = np.asarray(value)
    if raw.dtype.kind not in "fiu" or not np.isfinite(raw).all():
        raise ValueError(f"{name} must contain finite real values")
    if raw.ndim > 1 or (raw.ndim == 1 and len(raw) != frames):
        raise ValueError(f"{name} must be a scalar or one value per frame")
    return np.asarray(raw, dtype=np.float64)


def _finite_result(result):
    if not np.isfinite(result).all():
        raise ValueError("processing produced nonfinite samples; reduce input or gain")
    return result


def _scalar(value, name):
    raw = _control(value, 0, name)
    if raw.ndim:
        raise ValueError(f"{name} must be a finite real scalar")
    return float(raw)


def gain(audio: np.ndarray, db: float | np.ndarray) -> np.ndarray:
    """Multiply by 10**(db/20); scalar or one dB value per frame, shared across channels.

    Preserves shape and headroom; never normalizes or clips. Empty input is supported.
    """
    x = _audio(audio)
    control = _control(db, len(x), "db")
    with np.errstate(over="ignore", invalid="ignore"):
        factor = 10 ** (control / 20)
        if x.ndim == 2 and factor.ndim:
            factor = factor[:, None]
        return _finite_result(x * factor)


def fade(
    audio: np.ndarray, sample_rate: int, *, in_s: float = 0.0, out_s: float = 0.0
) -> np.ndarray:
    """Apply linear amplitude fades to a complete clip, retaining its length and layout.

    Durations round to samples and must fit the clip. A fade of N>=2 samples includes
    both endpoints (0..1 in, 1..0 out); a one-sample fade sets that endpoint to zero.
    Overlapping fades multiply. Zero durations are a copy. For block processing use
    an authored per-frame gain curve instead of restarting fade on each block.
    """
    x = _audio(audio)
    _rate(sample_rate)
    counts = []
    for name, seconds in (("in_s", in_s), ("out_s", out_s)):
        value = _control(seconds, len(x), name)
        if value.ndim or value < 0 or value > len(x) / sample_rate:
            raise ValueError(f"{name} must be a nonnegative scalar duration fitting the clip")
        counts.append(round(float(value) * sample_rate))
    envelope = np.ones(len(x))
    for n, incoming in zip(counts, (True, False)):
        if n:
            ramp = np.linspace(0, 1, n) if n > 1 else np.zeros(1)
            if incoming:
                envelope[:n] *= ramp
            else:
                envelope[-n:] *= ramp[::-1]
    return x * (envelope[:, None] if x.ndim == 2 else envelope)


def pan(audio: np.ndarray, position: float | np.ndarray = 0.0) -> np.ndarray:
    """Pan mono to stereo with equal-power gains: -1 left, 0 center, +1 right.

    Center attenuates each output by about 3.01 dB. Position may vary per frame.
    Accepts (frames,) or (frames, 1); stereo balancing is a different operation.
    """
    x = _audio(audio)
    if x.ndim == 2:
        if x.shape[1] != 1:
            raise ValueError("pan expects mono audio; it does not downmix stereo")
        x = x[:, 0]
    control = _control(position, len(x), "position")
    if np.any(np.abs(control) > 1):
        raise ValueError("position must be between -1 and 1")
    angle = (control + 1) * (np.pi / 4)
    return np.column_stack((x * np.cos(angle), x * np.sin(angle)))


def biquad(
    audio: np.ndarray,
    sample_rate: int,
    *,
    kind: str,
    frequency_hz: float,
    q: float = 1 / np.sqrt(2),
    gain_db: float = 0.0,
    state: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Process one RBJ biquad and return (audio, next_state).

    kind: lowpass, highpass, peak, low_shelf or high_shelf. Frequency is strictly
    between zero and Nyquist; q>0. gain_db applies to peak/shelves (must be zero for
    pass filters). Shelves use the Q-based Cookbook form, not a shelf-slope control.
    See https://www.w3.org/TR/audio-eq-cookbook/ .

    State is float64 (2, channels), including (2, 1) for mono, in direct-form-II
    transposed order. None starts at zero. Pass the returned state to the next block
    with the same channel layout and filter parameters. Audio and state are not mutated.
    Empty blocks preserve state. For a tail, explicitly process zeros. Parameter changes
    at block boundaries are allowed but are not smoothed and can produce transients.
    """
    x = _audio(audio)
    _rate(sample_rate)
    for name, value in (("frequency_hz", frequency_hz), ("q", q), ("gain_db", gain_db)):
        v = _control(value, len(x), name)
        if v.ndim:
            raise ValueError(f"{name} must be a scalar")
    if not 0 < frequency_hz < sample_rate / 2 or q <= 0:
        raise ValueError("frequency_hz must be between 0 and Nyquist, and q must be positive")
    if kind in ("lowpass", "highpass") and gain_db != 0:
        raise ValueError("gain_db applies only to peak and shelf filters")
    with np.errstate(over="ignore", invalid="ignore"):
        sos = coefficients(sample_rate, kind, frequency_hz, q, gain_db)
    if not np.isfinite(sos).all() or np.any(np.abs(np.roots(sos[3:])) >= 1):
        raise ValueError("parameters do not produce a stable finite filter")
    mono = x.ndim == 1
    frames = x[:, None] if mono else x
    shape = (2, frames.shape[1])
    if state is None:
        initial = np.zeros(shape)
    else:
        raw = np.asarray(state)
        if raw.shape != shape or raw.dtype.kind not in "fiu" or not np.isfinite(raw).all():
            raise ValueError(f"state must contain finite real values with shape {shape}")
        initial = np.array(raw, dtype=np.float64, copy=True)
    if not len(x):
        return x.copy(), initial
    result, final = lfilter(sos[:3], sos[3:], frames, axis=0, zi=initial)
    _finite_result(result)
    _finite_result(final)
    return (result[:, 0] if mono else result), final


def duck(
    audio: np.ndarray,
    detector: np.ndarray,
    sample_rate: int,
    *,
    threshold_db: float = -18.0,
    ratio: float = 4.0,
    attack_ms: float = 5.0,
    release_ms: float = 100.0,
    return_gain: bool = False,
) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """Duck a complete clip using an external peak detector and one linked gain.

    Detector has the same frame count, with any positive number of channels; its
    maximum absolute channel value feeds a linear-amplitude attack/release envelope.
    Time constants in ms reach 63.2% of a step after one time constant; zero is
    immediate. The envelope starts at zero on EVERY call. Above threshold, each
    ratio dB of detector excess becomes 1 dB; below threshold the gain is unity.
    ratio>=1, times>=0. No lookahead, separate gain smoothing or makeup gain.

    return_gain=True also returns the linear (frames,) gain applied to every program
    channel, so another signal can use exactly the same curve. No input is mutated.
    """
    x = _audio(audio)
    side = _audio(detector)
    _rate(sample_rate)
    if len(side) != len(x):
        raise ValueError("detector must have the same frame count as audio")
    threshold = _scalar(threshold_db, "threshold_db")
    ratio = _scalar(ratio, "ratio")
    attack = _scalar(attack_ms, "attack_ms")
    release = _scalar(release_ms, "release_ms")
    if ratio < 1 or attack < 0 or release < 0:
        raise ValueError("ratio must be >=1 and attack_ms/release_ms must be >=0")
    if not isinstance(return_gain, (bool, np.bool_)):
        raise TypeError("return_gain must be a bool")
    peaks = np.abs(side)
    if side.ndim == 2:
        peaks = np.max(peaks, axis=1)
    # expm1 retains the update weight for long time constants.
    attack_weight = -math.expm1(-1000.0 / sample_rate / attack) if attack else 1.0
    release_weight = -math.expm1(-1000.0 / sample_rate / release) if release else 1.0
    envelope = duck_envelope(np.ascontiguousarray(peaks), attack_weight, release_weight)
    levels_db = np.full(len(x), -np.inf)
    np.log10(envelope, out=levels_db, where=envelope > 0)
    with np.errstate(over="ignore", under="ignore"):
        excess = np.maximum(20 * levels_db - threshold, 0)
        gains = 10 ** (-excess * (1 - 1 / ratio) / 20)
    result = _finite_result(x * (gains[:, None] if x.ndim == 2 else gains))
    return (result, gains) if return_gain else result


def delay(
    audio: np.ndarray,
    sample_rate: int,
    *,
    delay_seconds: float | np.ndarray = 0.15,
    feedback: float = 0.35,
    tail_seconds: float = 0.0,
) -> np.ndarray:
    """Return a whole clip's WET-ONLY fractional feedback delay, including its tail.

    At frame n, linearly interpolate history at n-delay, then store input+feedback*read.
    Missing prehistory/input is zero. Channels have independent histories. Delays
    are scalar or one seconds value per INPUT frame, at least one sample; modulation
    moves the read head directly (pitch motion is intentional), without smoothing.
    -1 < feedback < 1. Each call resets history; this is not a streaming function.

    Output has len(audio)+round(tail_seconds*sample_rate) frames. Tail defaults to 0;
    explicitly request what you want to retain. A control array holds its last value
    during the tail. Empty input produces only a zero tail. Add dry audio yourself.
    """
    x = _audio(audio)
    _rate(sample_rate)
    control = _control(delay_seconds, len(x), "delay_seconds")
    feedback = _scalar(feedback, "feedback")
    tail = _scalar(tail_seconds, "tail_seconds")
    if not -1 < feedback < 1 or tail < 0:
        raise ValueError("feedback must be between -1 and 1, and tail_seconds must be >=0")
    with np.errstate(over="ignore"):
        delays = control * sample_rate
        tail_frames = tail * sample_rate
    if not np.isfinite(delays).all() or np.any(delays < 1):
        raise ValueError("delay_seconds must give finite delays of at least one sample")
    if not math.isfinite(tail_frames):
        raise ValueError("tail_seconds gives a nonfinite frame count")
    total = len(x) + round(tail_frames)
    mono = x.ndim == 1
    frames = x[:, None] if mono else x
    if not len(x):
        result = np.zeros((total, frames.shape[1]))
        return result[:, 0] if mono else result
    # Delays beyond the entire output cannot read any history. Cap allocation there.
    capacity = math.ceil(min(float(np.max(delays)), total)) + 1
    delay_values = np.asarray([float(delays)]) if delays.ndim == 0 else delays
    result = fractional_delay(
        np.ascontiguousarray(frames),
        np.ascontiguousarray(delay_values),
        feedback,
        total,
        capacity,
    )
    _finite_result(result)
    return result[:, 0] if mono else result


def crossfade_delay(
    audio: np.ndarray,
    sample_rate: int,
    *,
    delay_seconds: float | np.ndarray = 0.15,
    feedback: float = 0.35,
    tail_seconds: float = 0.0,
    crossfade_seconds: float = 0.05,
) -> np.ndarray:
    """Return a wet-only delay whose delay changes use fixed-head crossfades.

    This is the same whole-clip, reset-on-call effect shape as delay(), but delay
    changes do not move one read head continuously. When the requested delay changes,
    old and new fractional read distances are frozen and linearly crossfaded over
    round(crossfade_seconds*sample_rate) samples, at least one. Intermediate requests
    during that fade are skipped; the latest request can start a new fade on the next
    sample after completion if the control at that sample still differs. This avoids
    pitch glide but can create cancellation.

    Delay may be scalar or one value per input frame, at least one sample. Feedback is
    strictly between -1 and 1. Tail length matches delay():
    len(audio)+round(tail_seconds*sample_rate).
    """
    x = _audio(audio)
    _rate(sample_rate)
    control = _control(delay_seconds, len(x), "delay_seconds")
    feedback = _scalar(feedback, "feedback")
    tail = _scalar(tail_seconds, "tail_seconds")
    crossfade = _scalar(crossfade_seconds, "crossfade_seconds")
    if not -1 < feedback < 1 or tail < 0:
        raise ValueError("feedback must be between -1 and 1, and tail_seconds must be >=0")
    if crossfade <= 0:
        raise ValueError("crossfade_seconds must be > 0")
    with np.errstate(over="ignore"):
        delays = control * sample_rate
        tail_frames = tail * sample_rate
        fade_frames = crossfade * sample_rate
    if not np.isfinite(delays).all() or np.any(delays < 1):
        raise ValueError("delay_seconds must give finite delays of at least one sample")
    if not math.isfinite(tail_frames):
        raise ValueError("tail_seconds gives a nonfinite frame count")
    if not math.isfinite(fade_frames):
        raise ValueError("crossfade_seconds gives a nonfinite frame count")
    crossfade_samples = round(fade_frames)
    if crossfade_samples < 1:
        raise ValueError("crossfade_seconds must round to at least one sample")
    if crossfade_samples > np.iinfo(np.int64).max:
        raise ValueError("crossfade_seconds gives an unsupported frame count")
    total = len(x) + round(tail_frames)
    mono = x.ndim == 1
    frames = x[:, None] if mono else x
    if not len(x):
        result = np.zeros((total, frames.shape[1]))
        return result[:, 0] if mono else result
    capacity = math.ceil(min(float(np.max(delays)), total)) + 1
    delay_values = np.asarray([float(delays)]) if delays.ndim == 0 else delays
    result = crossfade_fractional_delay(
        np.ascontiguousarray(frames),
        np.ascontiguousarray(delay_values),
        feedback,
        total,
        capacity,
        crossfade_samples,
    )
    _finite_result(result)
    return result[:, 0] if mono else result


def crossover(
    audio: np.ndarray,
    sample_rate: int,
    *,
    cutoff_hz: float = 1000.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Split audio into two Linkwitz-Riley 4th-order low/high bands.

    The split uses two cascaded 2nd-order Butterworth SOS filters per branch. Both
    branches reset on every call and preserve the input shape/layout. The summed
    bands have flat magnitude for a fixed cutoff, with phase change; it is not dry
    sample identity. cutoff_hz is a finite scalar strictly between zero and Nyquist.
    """
    x = _audio(audio)
    _rate(sample_rate)
    cutoff = _scalar(cutoff_hz, "cutoff_hz")
    if not 0 < cutoff < sample_rate / 2:
        raise ValueError("cutoff_hz must be between zero and Nyquist")
    mono = x.ndim == 1
    frames = x[:, None] if mono else x
    if not len(x):
        return x.copy(), x.copy()
    low_sos = butter(2, cutoff, btype="lowpass", fs=sample_rate, output="sos")
    high_sos = butter(2, cutoff, btype="highpass", fs=sample_rate, output="sos")
    low = sosfilt(low_sos, sosfilt(low_sos, frames, axis=0), axis=0)
    high = sosfilt(high_sos, sosfilt(high_sos, frames, axis=0), axis=0)
    _finite_result(low)
    _finite_result(high)
    if mono:
        return low[:, 0], high[:, 0]
    return low, high


def lowpass(
    audio: np.ndarray,
    sample_rate: int,
    *,
    cutoff_hz: float | np.ndarray = 1000.0,
    q: float = 1 / np.sqrt(2),
) -> np.ndarray:
    """Whole-clip two-pole lowpass with scalar or per-frame cutoff in Hz.

    Unity DC gain; Q=1/sqrt(2) gives -3.01 dB at cutoff. Each channel starts from
    silence on each call. Scalar cutoff uses the existing biquad; automated cutoff
    uses a topology-preserving state-variable recurrence with continuous memory.
    0 < cutoff < Nyquist, q>0. Controls are applied directly without smoothing;
    arbitrary parameter jumps are not promised to be click-free. For explicit
    fixed-parameter block continuation, use biquad instead.
    """
    x = _audio(audio)
    _rate(sample_rate)
    cutoff = _control(cutoff_hz, len(x), "cutoff_hz")
    q = _scalar(q, "q")
    if q <= 0 or not math.isfinite(1 / q):
        raise ValueError("q must be positive with a finite reciprocal")
    if np.any(cutoff <= 0) or np.any(cutoff >= sample_rate / 2):
        raise ValueError("cutoff_hz must be between zero and Nyquist")
    if cutoff.ndim == 0:
        return biquad(x, sample_rate, kind="lowpass", frequency_hz=float(cutoff), q=q)[0]
    zeros = np.zeros(len(x))
    return _svf(x, sample_rate, cutoff, np.full(len(x), 1 / q), zeros, zeros, np.ones(len(x)))


def _svf(x, sample_rate, cutoff, k, m0, m1, m2):
    mono = x.ndim == 1
    frames = x[:, None] if mono else x
    cutoff = np.broadcast_to(cutoff, (len(x),))
    g = np.tan(np.pi * cutoff / sample_rate)
    a1 = 1 / (1 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    with np.errstate(over="ignore", invalid="ignore"):
        result = variable_svf(
            np.ascontiguousarray(frames),
            *(np.ascontiguousarray(v, dtype=np.float64) for v in (a1, a2, a3, m0, m1, m2)),
        )
    _finite_result(result)
    return result[:, 0] if mono else result


_SVF_MODES = ("lowpass", "highpass", "bandpass", "notch")
_BUTTERWORTH_Q = 2**-0.5


def svf(
    audio: np.ndarray,
    sample_rate: int,
    *,
    mode: str,
    cutoff_hz: float | np.ndarray,
    q: float | np.ndarray = _BUTTERWORTH_Q,
) -> np.ndarray:
    """Whole-clip state-variable filter with scalar or per-frame cutoff and Q.

    mode is lowpass, highpass, bandpass or notch. Lowpass/highpass have unity gain in
    their passband; bandpass is normalized to 0 dB at the cutoff (peak) frequency, so
    raising Q narrows it; notch removes the cutoff frequency. Higher Q makes low/high
    pass resonate (about 20·log10(Q) dB at cutoff). Topology-preserving (Simper) SVF,
    the same recurrence as automated `lowpass`: each channel starts from silence; controls
    are applied directly without smoothing. 0 < cutoff < Nyquist, q > 0.
    """
    x = _audio(audio)
    _rate(sample_rate)
    if mode not in _SVF_MODES:
        raise ValueError(f"mode must be one of {', '.join(_SVF_MODES)}")
    cutoff = _control(cutoff_hz, len(x), "cutoff_hz")
    qs = _control(q, len(x), "q")
    if np.any(cutoff <= 0) or np.any(cutoff >= sample_rate / 2):
        raise ValueError("cutoff_hz must be between zero and Nyquist")
    if np.any(qs <= 0) or not np.isfinite(1 / qs).all():
        raise ValueError("q must be positive with a finite reciprocal")
    k = np.broadcast_to(1 / qs, (len(x),)).astype(np.float64)
    one = np.ones(len(x))
    zero = np.zeros(len(x))
    weights = {
        "lowpass": (zero, zero, one),
        "highpass": (one, -k, -one),
        "bandpass": (zero, k, zero),
        "notch": (one, -k, zero),
    }[mode]
    return _svf(x, sample_rate, cutoff, k, *weights)


def _fold(x):
    return 1.0 - 4.0 * np.abs(np.mod((x + 1.0) / 4.0, 1.0) - 0.5)


_CURVES = {"tanh": np.tanh, "clip": lambda x: np.clip(x, -1.0, 1.0), "fold": _fold}


def saturate(
    audio: np.ndarray,
    sample_rate: int,
    *,
    drive_db: float | np.ndarray = 12.0,
    mix: float | np.ndarray = 0.5,
    oversample: int = 8,
    curve: str = "tanh",
) -> np.ndarray:
    """Whole-clip waveshaping drive with aligned, linear dry/wet and optional oversampling.

    Wet transfer: curve(audio * 10**(drive_db/20)), without makeup/normalization.
    curve "tanh" (default) is smooth saturation; "clip" limits hard to ±1; "fold"
    reflects the signal back at ±1 as often as needed (triangle wavefolder, like
    SuperCollider's fold2), so more drive adds more folds rather than more clipping.
    Clip and fold have sharp corners and a wider spectrum than tanh; oversampling
    matters most for them.
    drive_db/mix may be scalar or one value per frame, shared across channels.
    0<=mix<=1; mix=0 is exact bypass, including input headroom. Output length/layout
    are unchanged. oversample is 1/2/4/8/16; 1 explicitly disables antialiasing.

    Default 8x SciPy polyphase resampling uses a Kaiser(8.6) window and compensates
    FIR alignment. Linear gain is interpolated at the higher sample rate; mix is
    applied at the original rate. Padding is zero at clip edges. Process complete
    clips: independent chunk calls are NOT equivalent because of those edges.
    Oversampling reduces aliasing, not a guarantee of its elimination or sound quality.
    """
    x = _audio(audio)
    _rate(sample_rate)
    drive = _control(drive_db, len(x), "drive_db")
    blend = _control(mix, len(x), "mix")
    if np.any(blend < 0) or np.any(blend > 1):
        raise ValueError("mix must be between 0 and 1")
    if (
        isinstance(oversample, (bool, np.bool_))
        or not isinstance(oversample, (int, np.integer))
        or oversample not in (1, 2, 4, 8, 16)
    ):
        raise ValueError("oversample must be one of 1, 2, 4, 8, 16")
    if curve not in _CURVES:
        raise ValueError(f"curve must be one of {', '.join(_CURVES)}")
    shape = _CURVES[curve]
    with np.errstate(over="ignore", under="ignore"):
        factor = 10 ** (drive / 20)
    if not np.isfinite(factor).all():
        raise ValueError("drive_db produces a nonfinite gain")
    if not len(x) or np.all(blend == 0):
        return x.copy()
    mono = x.ndim == 1
    frames = x[:, None] if mono else x
    up = resample_poly(frames, oversample, 1, axis=0, window=("kaiser", 8.6))
    high_gain = factor
    if factor.ndim:
        high_gain = np.interp(np.arange(len(up)) / oversample, np.arange(len(x)), factor)
        high_gain = high_gain[:, None]
    with np.errstate(over="ignore", invalid="ignore"):
        wet = resample_poly(shape(up * high_gain), 1, oversample, axis=0, window=("kaiser", 8.6))[
            : len(x)
        ]
        blend = blend[:, None] if blend.ndim else blend
        result = _finite_result((1 - blend) * frames + blend * wet)
    return result[:, 0] if mono else result


def spectral(
    audio: np.ndarray,
    sample_rate: int,
    transform,
    *,
    n_fft: int = 2048,
    hop: int = 512,
) -> np.ndarray:
    """Phase-vocoder analysis/resynthesis around a caller-supplied per-frame transform.

    Each Hann-windowed frame is analyzed into magnitude and instantaneous frequency (Hz)
    per bin. `transform(magnitude, frequency_hz, frame_index)` returns new
    (magnitude, frequency_hz) arrays of the same shape: (bins,) for mono audio or
    (bins, channels). Output phase accumulates 2π·frequency·hop/sample_rate per frame
    from the first frame's analysis phase, then frames are overlap-added with
    window-power normalization. The identity transform reconstructs the input to
    numerical precision; freezing, shifting or smearing are choices of the transform.
    Output keeps the input length and layout. n_fft is an even integer >= 16;
    1 <= hop <= n_fft // 2. Magnitudes must be finite and nonnegative.
    """
    x = _audio(audio)
    _rate(sample_rate)
    if (
        isinstance(n_fft, (bool, np.bool_))
        or not isinstance(n_fft, (int, np.integer))
        or n_fft < 16
        or n_fft % 2
    ):
        raise ValueError("n_fft must be an even integer of at least 16")
    if (
        isinstance(hop, (bool, np.bool_))
        or not isinstance(hop, (int, np.integer))
        or not 1 <= hop <= n_fft // 2
    ):
        raise ValueError("hop must be an integer between 1 and n_fft // 2")
    if not callable(transform):
        raise TypeError("transform must be callable")
    mono = x.ndim == 1
    frames = x[:, None] if mono else x
    length, channels = frames.shape
    count = -(-(length + n_fft) // hop) + 1
    padded = np.zeros((count * hop + n_fft, channels))
    padded[n_fft : n_fft + length] = frames
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n_fft) / n_fft)
    bins = n_fft // 2 + 1
    advance = 2 * np.pi * np.arange(bins)[:, None] * hop / n_fft
    to_hz = sample_rate / (2 * np.pi * hop)
    output = np.zeros_like(padded)
    norm = np.zeros(len(padded))
    previous = None
    phase = None
    for m in range(count):
        start = m * hop
        spectrum = np.fft.rfft(padded[start : start + n_fft] * window[:, None], axis=0)
        magnitude = np.abs(spectrum)
        angle = np.angle(spectrum)
        if previous is None:
            deviation = np.zeros_like(angle)
        else:
            deviation = np.mod(angle - previous - advance + np.pi, 2 * np.pi) - np.pi
        previous = angle
        frequency = (advance + deviation) * to_hz
        result = transform(
            magnitude[:, 0] if mono else magnitude, frequency[:, 0] if mono else frequency, m
        )
        if not isinstance(result, tuple) or len(result) != 2:
            raise ValueError("transform must return (magnitude, frequency_hz)")
        new_mag, new_freq = (np.asarray(v, dtype=np.float64) for v in result)
        if mono:
            new_mag, new_freq = new_mag[:, None], new_freq[:, None]
        if new_mag.shape != magnitude.shape or new_freq.shape != magnitude.shape:
            raise ValueError("transform results must keep the analysis shape")
        if not (np.isfinite(new_mag).all() and np.isfinite(new_freq).all()) or np.any(new_mag < 0):
            raise ValueError("transform must return finite, nonnegative magnitudes and finite Hz")
        phase = angle if phase is None else phase + new_freq / to_hz
        frame = np.fft.irfft(new_mag * np.exp(1j * phase), n_fft, axis=0)
        output[start : start + n_fft] += frame * window[:, None]
        norm[start : start + n_fft] += window**2
    result = output[n_fft : n_fft + length] / norm[n_fft : n_fft + length, None]
    _finite_result(result)
    return result[:, 0] if mono else result


def varispeed(audio: np.ndarray, sample_rate: int, speed: np.ndarray) -> np.ndarray:
    """Play `audio` back at a per-output-frame `speed`, so pitch follows speed.

    `speed[i]` is the playback rate at output frame `i`: 1.0 is normal, 0.5 is half
    speed an octave down, 0.0 holds the current position. The read position advances
    by the cumulative speed and is linearly interpolated; once it passes the end of
    `audio`, output is silence. Output has `len(speed)` frames in `audio`'s layout
    (`(frames,)` or `(frames, channels)`), float32. The curve's shape is the work's
    choice; this only resamples. Speeds above 1.0 are not band-limited and can alias.
    """
    raw = np.asarray(audio)
    if type(sample_rate) is not int or sample_rate <= 0:
        raise ValueError("sample_rate must be a positive int")
    if raw.ndim not in (1, 2) or not len(raw) or not np.isfinite(raw).all():
        raise ValueError("audio must be finite, nonempty (frames,) or (frames, channels)")
    rates = np.asarray(speed, dtype=np.float64)
    if rates.ndim != 1 or not len(rates) or not np.isfinite(rates).all() or (rates < 0).any():
        raise ValueError("speed must be a nonempty 1-D array of finite values >= 0")

    source = raw.astype(np.float32, copy=False)
    frames = source.shape[0]
    position = np.concatenate([[0.0], np.cumsum(rates[:-1])])
    inside = position <= frames - 1
    grid = np.arange(frames, dtype=np.float64)
    if source.ndim == 1:
        out = np.interp(position, grid, source).astype(np.float32)
        out[~inside] = 0.0
        return out
    out = np.stack(
        [np.interp(position, grid, source[:, ch]) for ch in range(source.shape[1])], axis=1
    ).astype(np.float32)
    out[~inside] = 0.0
    return out


def _rms_dbfs(x: np.ndarray) -> float:
    mean_square = float(np.mean(np.square(x, dtype=np.float64))) if x.size else 0.0
    return 10.0 * math.log10(mean_square) if mean_square > 0 else -math.inf


def _limiter_gain(x: np.ndarray, ceiling_lin: float, sample_rate: int) -> np.ndarray:
    """A per-sample gain envelope that never exceeds what that sample needs to reach the
    ceiling, smoothed so it changes gradually instead of snapping on and off. `needed` is the
    instantaneous `min(1, ceiling / peak-across-channels)`; a centered running minimum over a
    window of about 2W looks ahead and behind so the dip starts before an oncoming peak and
    holds through it, then a box average over W (W ~ 5 ms) smooths the transitions."""
    peak = np.max(np.abs(x), axis=-1) if x.ndim == 2 else np.abs(x)
    needed = np.minimum(1.0, ceiling_lin / np.maximum(peak, 1e-9))
    w = max(1, round(_FIT_RMS_WINDOW_MS / 1000.0 * sample_rate))
    ducked = minimum_filter1d(needed, size=2 * w + 1, mode="nearest")
    return uniform_filter1d(ducked, size=w, mode="nearest")


def _apply_gain(x: np.ndarray, gain: np.ndarray) -> np.ndarray:
    return x * gain[:, None] if x.ndim == 2 else x * gain


def fit_rms(
    audio: np.ndarray, sample_rate: int, target_dbfs: float, ceiling_dbfs: float = -1.0
) -> np.ndarray:
    """Return audio whose whole-signal RMS (all channels flattened together) is within 0.05 dB
    of `target_dbfs`, with every sample at or below `ceiling_dbfs`, measured on this
    function's returned array (matching how a checker would measure the delivered file).

    Limiting is a NumPy look-ahead gain envelope (`_limiter_gain`), not
    `pedalboard.Limiter`: a hard-clipping limiter can leave hundreds of samples flat at the
    ceiling on peaky material, which this avoids by ducking gain smoothly ahead of a peak
    rather than clipping into it. A trailing `np.clip` is a safety guard for the rare case the
    smoothing itself lets a sample edge a hair over the ceiling; it should never trigger
    meaningfully.

    Applying the envelope changes the RMS relative to a plain gain, so this bisects the
    pre-gain (up to 30 steps) between a bound quiet enough to barely limit and one loud enough
    to limit heavily -- the achieved RMS rises monotonically with pre-gain over that range --
    stopping early once within 0.05 dB of the target. If still more than 0.5 dB away after 30
    steps, raises `ValueError` naming the achieved RMS: heavy targets on peaky material mean
    heavy limiting, which can make the target unreachable at that ceiling (a target RMS can
    never exceed the ceiling itself). Silence (all-zero input) passes through unchanged.
    """
    x = np.asarray(audio, dtype=np.float32)
    if x.size == 0 or not np.any(x):
        return x
    ceiling_lin = 10.0 ** (ceiling_dbfs / 20.0)

    def measure(pre_gain_db: float) -> tuple[np.ndarray, float]:
        pre = x * (10.0 ** (pre_gain_db / 20.0))
        gain = _limiter_gain(pre, ceiling_lin, sample_rate)
        limited = _apply_gain(pre, gain)
        return limited, _rms_dbfs(limited)

    naive_db = target_dbfs - _rms_dbfs(x)
    lo, hi = naive_db - 60.0, naive_db + 60.0
    y, cur_db = measure(hi)
    for _ in range(30):
        mid = (lo + hi) / 2.0
        y, cur_db = measure(mid)
        if abs(cur_db - target_dbfs) <= 0.05:
            break
        if cur_db < target_dbfs:
            lo = mid
        else:
            hi = mid

    if abs(cur_db - target_dbfs) > 0.5:
        raise ValueError(
            f"fit_rms could not reach {target_dbfs} dBFS within 0.5 dB in 30 iterations "
            f"(achieved {cur_db:.2f} dBFS); the ceiling of {ceiling_dbfs} dBFS may be too "
            "tight for this material's crest factor."
        )

    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > ceiling_lin:
        y = np.clip(y, -ceiling_lin, ceiling_lin)
    return y.astype(np.float32)
