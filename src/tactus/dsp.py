"""Optional owned audio processing, using NumPy/SciPy/Numba and explicit filter state.

Arrays use (frames,) or (frames, channels), with finite real samples and retained
headroom. Functions allocate float64 outputs without mutating audio or caller state.
Gain/pan accept scalar or per-frame controls; fade applies to a complete clip. Biquad
returns (audio, state) for explicit block continuation. No hidden chain or shared state.
Duck/delay/lowpass/saturate process complete clips, resetting on each call; they accept
external detectors or per-frame controls without imposing a composition/processor model.
Delay returns only the delayed signal, with explicitly requested tail duration. Saturate
owns its oversampling/alignment and tanh transfer, not a loudness-normalization policy.
Crossover returns LR4 low/high branches. Crossfade delay keeps two fractional heads
fixed during retiming, with explicit transition length and latest-request behavior.
Existing fx.varispeed/fit_rms are also available here, with their original contracts.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import butter, lfilter, resample_poly, sosfilt

from ._biquad import coefficients
from ._dsp_kernels import (
    crossfade_fractional_delay,
    duck_envelope,
    fractional_delay,
    variable_lowpass_svf,
)
from .fx import fit_rms, varispeed

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
    "varispeed",
]


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
    mono = x.ndim == 1
    frames = x[:, None] if mono else x
    g = np.tan(np.pi * cutoff / sample_rate)
    k = 1 / q
    a1 = 1 / (1 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    with np.errstate(over="ignore", invalid="ignore"):
        result = variable_lowpass_svf(
            np.ascontiguousarray(frames),
            np.ascontiguousarray(a1),
            np.ascontiguousarray(a2),
            np.ascontiguousarray(a3),
        )
    _finite_result(result)
    return result[:, 0] if mono else result


def saturate(
    audio: np.ndarray,
    sample_rate: int,
    *,
    drive_db: float | np.ndarray = 12.0,
    mix: float | np.ndarray = 0.5,
    oversample: int = 8,
) -> np.ndarray:
    """Whole-clip tanh drive with aligned, linear dry/wet and optional oversampling.

    Wet transfer: tanh(audio * 10**(drive_db/20)), without makeup/normalization.
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
        wet = resample_poly(np.tanh(up * high_gain), 1, oversample, axis=0, window=("kaiser", 8.6))[
            : len(x)
        ]
        blend = blend[:, None] if blend.ndim else blend
        result = _finite_result((1 - blend) * frames + blend * wet)
    return result[:, 0] if mono else result
