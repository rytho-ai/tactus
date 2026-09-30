"""Optional sound-generating building blocks: phase, oscillators, noise, envelopes,
resonators, plucked strings and grains. Building blocks, not instruments or presets.

Every function returns a new float64 array and never mutates its inputs. Generators
return mono `(frames,)`; place, pan and mix them with ordinary NumPy or `tactus.dsp`.
`grains` with per-grain `pan` is the one stereo `(frames, 2)` result. Phase is measured
in cycles throughout (never radians). Controls are a scalar or one value per frame.
Randomness appears only in `noise`, whose seed is required. Timbre-shaping choices
(waveform, width, decay, brightness, curve, window) are explicit arguments.

Algorithms are implemented from published methods; no Csound or SuperCollider source
was read or copied. Csound serves as a behavioral oracle in tests; SC and Csound names
below identify comparable units:
PolyBLEP/PolyBLAMP band-limiting (Välimäki et al.; cf. Csound vco2, SC Saw/Pulse/LFTri),
Kellet's pink-noise filter, transeg-style exponential segments (Csound transeg),
two-pole modal resonators with T60 decay (Csound mode, SC Ringz/Klank),
Karplus-Strong with a first-order allpass tuning stage (Jaffe-Smith; Csound pluck,
SC Pluck), and windowed-grain overlap-add (Csound partikkel, SC GrainBuf).

Reads: numpy · scipy.signal.lfilter · dsp validation · timing.frame_of ·
_synth_kernels.karplus_strong/overlap_grains
"""

from __future__ import annotations

import math

import numpy as np
from scipy.signal import lfilter

from ._synth_kernels import karplus_strong, overlap_grains
from .dsp import _audio, _control, _finite_result, _rate, _scalar
from .timing import frame_of

__all__ = [
    "envelope",
    "grains",
    "noise",
    "phase",
    "pluck",
    "pulse",
    "resonators",
    "saw",
    "sine",
    "triangle",
]

_T60 = math.log(1000.0)


def _frames(frames):
    if (
        isinstance(frames, (bool, np.bool_))
        or not isinstance(frames, (int, np.integer))
        or frames < 0
    ):
        raise ValueError("frames must be a nonnegative integer")
    return int(frames)


def _frequency(freq_hz, sample_rate, frames):
    freq = _control(freq_hz, frames, "freq_hz")
    if np.any(np.abs(freq) >= sample_rate / 2):
        raise ValueError("freq_hz must be below Nyquist in magnitude")
    return freq


def phase(
    freq_hz: float | np.ndarray,
    sample_rate: int,
    *,
    frames: int,
    start: float = 0.0,
) -> np.ndarray:
    """Cumulative phase in cycles: frame i holds start + sum(freq[:i]) / sample_rate.

    Frequency may be scalar or per frame and may be negative. The result is not wrapped,
    so glides and pitch envelopes stay continuous; take `% 1.0` for a 0..1 ramp.
    Scalar frequency is computed as start + i*freq/sample_rate without accumulation.
    """
    _rate(sample_rate)
    frames = _frames(frames)
    freq = _frequency(freq_hz, sample_rate, frames)
    start = _scalar(start, "start")
    if freq.ndim == 0:
        return start + np.arange(frames) * (float(freq) / sample_rate)
    out = np.empty(frames)
    if frames:
        out[0] = 0.0
        np.cumsum(freq[:-1] / sample_rate, out=out[1:])
    return start + out


def _total_phase(freq_hz, sample_rate, frames, start, phase_mod, *, band_limited=True):
    base = phase(freq_hz, sample_rate, frames=frames, start=start)
    mod = _control(phase_mod, frames, "phase_mod")
    total = base + mod
    if not band_limited:
        return total, None
    increment = np.empty(frames)
    if frames > 1:
        increment[1:] = np.diff(total)
        increment[0] = increment[1]
    elif frames:
        freq = _frequency(freq_hz, sample_rate, frames)
        increment[0] = float(freq if freq.ndim == 0 else freq[0]) / sample_rate
    step = np.abs(increment)
    if np.any(step >= 0.5):
        frame = int(np.argmax(step))
        raise ValueError(
            f"instantaneous frequency reaches {step[frame] * sample_rate:.0f} Hz at frame {frame}, "
            f"at or above Nyquist ({sample_rate / 2:.0f} Hz); band-limited oscillators need "
            "freq_hz plus the phase_mod deviation below Nyquist. A sinusoidal phase_mod of "
            "depth D cycles at f Hz deviates by 2*pi*D*f Hz; reduce D or f, or use sine, "
            "which accepts any phase_mod"
        )
    return total, step


def _blep(t, dt):
    """PolyBLEP residual for a unit downward step at phase 0 (t in [0,1), dt=|increment|)."""
    r = np.zeros_like(t)
    safe = dt > 0
    after = safe & (t < dt)
    x = t[after] / dt[after]
    r[after] = x + x - x * x - 1.0
    before = safe & (t > 1.0 - dt)
    x = (t[before] - 1.0) / dt[before]
    r[before] = x * x + x + x + 1.0
    return r


def _blamp(t, dt):
    r = np.zeros_like(t)
    safe = dt > 0
    after = safe & (t < dt)
    x = t[after] / dt[after] - 1.0
    r[after] = -x * x * x / 3.0
    before = safe & (t > 1.0 - dt)
    x = (t[before] - 1.0) / dt[before] + 1.0
    r[before] = x * x * x / 3.0
    return r


def sine(
    freq_hz: float | np.ndarray,
    sample_rate: int,
    *,
    frames: int,
    phase: float = 0.0,
    phase_mod: float | np.ndarray = 0.0,
) -> np.ndarray:
    """sin(2π·(phase(t) + phase_mod)): a sine in -1..1 for FM/PM carriers and modulators.

    phase_mod is in cycles per frame: `phase_mod = D * sine(f_m, ...)` deviates the
    frequency by 2π·D·f_m Hz. A classic FM index β (radians) is D = β / (2π); β = 2 is
    D ≈ 0.32. Any depth is accepted: sidebands beyond Nyquist fold back (alias) as in
    other FM implementations; only freq_hz itself must stay below Nyquist.
    """
    total, _ = _total_phase(
        freq_hz, sample_rate, _frames(frames), phase, phase_mod, band_limited=False
    )
    return _finite_result(np.sin(2 * np.pi * total))


def saw(
    freq_hz: float | np.ndarray,
    sample_rate: int,
    *,
    frames: int,
    phase: float = 0.0,
    phase_mod: float | np.ndarray = 0.0,
) -> np.ndarray:
    """Rising sawtooth, -1 at each cycle start to +1, band-limited with PolyBLEP.

    The correction uses the per-frame phase increment, so glides, negative frequency
    and phase_mod keep it aligned. PolyBLEP greatly reduces aliasing near the jump;
    it does not remove it, and it slightly darkens upper harmonics compared with an
    ideal band-limited saw (at 48 kHz about -1 dB at 9 kHz and -2 dB at 12 kHz).
    The instantaneous frequency must stay below Nyquist.
    """
    total, step = _total_phase(freq_hz, sample_rate, _frames(frames), phase, phase_mod)
    t = total % 1.0
    return _finite_result(2.0 * t - 1.0 - _blep(t, step))


def pulse(
    freq_hz: float | np.ndarray,
    sample_rate: int,
    *,
    frames: int,
    width: float | np.ndarray = 0.5,
    phase: float = 0.0,
    phase_mod: float | np.ndarray = 0.0,
) -> np.ndarray:
    """Pulse +1 for the first `width` of each cycle and -1 for the rest (width=0.5 is square).

    Built from two PolyBLEP saws, so width may vary per frame (0 < width < 1). The
    average value is 2*width - 1; no DC is removed.
    """
    frames = _frames(frames)
    total, step = _total_phase(freq_hz, sample_rate, frames, phase, phase_mod)
    w = _control(width, frames, "width")
    if np.any(w <= 0) or np.any(w >= 1):
        raise ValueError("width must be strictly between 0 and 1")
    t = total % 1.0
    shifted = (total - w) % 1.0
    first = 2.0 * t - 1.0 - _blep(t, step)
    second = 2.0 * shifted - 1.0 - _blep(shifted, step)
    return _finite_result(-(first - second - (2.0 * w - 1.0)))


def triangle(
    freq_hz: float | np.ndarray,
    sample_rate: int,
    *,
    frames: int,
    phase: float = 0.0,
    phase_mod: float | np.ndarray = 0.0,
) -> np.ndarray:
    """Triangle, +1 at each cycle start and -1 at mid-cycle, band-limited with PolyBLAMP."""
    total, step = _total_phase(freq_hz, sample_rate, _frames(frames), phase, phase_mod)
    t = total % 1.0
    naive = 4.0 * np.abs(t - 0.5) - 1.0
    correction = 4.0 * step * (_blamp(t, step) - _blamp((t + 0.5) % 1.0, step))
    return _finite_result(naive - correction)


def noise(frames: int, *, seed: int, color: str = "white") -> np.ndarray:
    """Seeded noise: identical seed and arguments give identical samples.

    white: uniform in [-1, 1) from NumPy's PCG64 generator. NumPy does not promise the
    same Generator stream across versions, so samples are reproducible within a locked
    environment; a NumPy upgrade may change them. pink: that white noise through
    Paul Kellet's refined filter (about -3 dB/octave from roughly 10 Hz at 44.1-48 kHz),
    scaled by 0.11; peaks are not bounded. Use different seeds for independent layers.
    """
    frames = _frames(frames)
    if (
        isinstance(seed, (bool, np.bool_))
        or not isinstance(seed, (int, np.integer))
        or seed < 0
    ):
        raise ValueError("seed must be a nonnegative integer")
    white = np.random.Generator(np.random.PCG64(int(seed))).uniform(-1.0, 1.0, frames)
    if color == "white":
        return white
    if color != "pink":
        raise ValueError("color must be 'white' or 'pink'")
    poles = (
        (0.99886, 0.0555179),
        (0.99332, 0.0750759),
        (0.96900, 0.1538520),
        (0.86650, 0.3104856),
        (0.55000, 0.5329522),
        (-0.7616, -0.0168980),
    )
    out = white * 0.5362
    for pole, weight in poles:
        out = out + lfilter([weight], [1.0, -pole], white)
    delayed = np.zeros(frames)
    delayed[1:] = white[:-1] * 0.115926
    return (out + delayed) * 0.11


def envelope(
    start: float,
    segments,
    sample_rate: int,
    *,
    frames: int | None = None,
) -> np.ndarray:
    """Piecewise envelope from `start` through (seconds, target, curve) segments.

    Segment boundaries are absolute: boundary k = frame_of(sum of seconds so far).
    Each segment moves from the previous value to `target`, reaching it on the
    boundary frame. curve 0 is linear; otherwise value = a + (b-a)(1-e^(c·x))/(1-e^c),
    as in Csound transeg: positive c starts slowly, negative c starts quickly. It is
    defined at and across zero. A segment rounding to zero frames jumps to its target.
    Without `frames` the result has last boundary + 1 frames (final target included);
    with it, the result is cut or held at the final target to that length.
    """
    _rate(sample_rate)
    level = _scalar(start, "start")
    points = [(0, level)]
    elapsed = 0.0
    curves = []
    for segment in segments:
        if len(segment) != 3:
            raise ValueError("each segment must be (seconds, target, curve)")
        seconds = _scalar(segment[0], "seconds")
        if seconds < 0:
            raise ValueError("segment seconds must be nonnegative")
        elapsed += seconds
        points.append((frame_of(elapsed, sample_rate), _scalar(segment[1], "target")))
        curves.append(_scalar(segment[2], "curve"))
    total = points[-1][0] + 1
    out = np.empty(total)
    out[0] = level
    for (a_frame, a), (b_frame, b), c in zip(points, points[1:], curves):
        n = b_frame - a_frame
        if n <= 0:
            out[b_frame] = b
            continue
        x = np.arange(1, n + 1) / n
        if c == 0:
            shape = x
        else:
            with np.errstate(over="ignore", invalid="ignore"):
                shape = np.expm1(c * x) / np.expm1(c)
            if not np.isfinite(shape).all():
                raise ValueError("curve magnitude is too large for a finite segment")
        out[a_frame + 1 : b_frame + 1] = a + (b - a) * shape
    if frames is None:
        return out
    frames = _frames(frames)
    if frames <= total:
        return out[:frames].copy()
    return np.concatenate((out, np.full(frames - total, out[-1])))


def resonators(
    excitation: np.ndarray,
    sample_rate: int,
    *,
    freqs_hz,
    decays_s,
    gains=None,
) -> np.ndarray:
    """A bank of parallel two-pole resonators (modes) driven by `excitation`.

    A unit impulse makes each mode ring as gain·r^n·sin(2π·f·(n+1)/sample_rate), with r
    chosen so the mode falls 60 dB in its decay time. freqs/decays/gains are equal-length
    sequences (gains default to 1); 0 < freq < Nyquist, decay > 0. Excitation may be mono
    or multichannel; each channel is filtered independently and the layout is kept.
    The output has the excitation's length; append zeros to hear a longer ring.
    """
    x = _audio(excitation)
    _rate(sample_rate)
    freqs = np.atleast_1d(np.asarray(freqs_hz, dtype=np.float64))
    decays = np.atleast_1d(np.asarray(decays_s, dtype=np.float64))
    amps = np.ones_like(freqs) if gains is None else np.atleast_1d(np.asarray(gains, dtype=np.float64))
    if freqs.ndim != 1 or not (len(freqs) == len(decays) == len(amps)) or not len(freqs):
        raise ValueError("freqs_hz, decays_s and gains must be equal-length nonempty sequences")
    if not (np.isfinite(freqs).all() and np.isfinite(decays).all() and np.isfinite(amps).all()):
        raise ValueError("freqs_hz, decays_s and gains must be finite")
    if np.any(freqs <= 0) or np.any(freqs >= sample_rate / 2):
        raise ValueError("freqs_hz must be between zero and Nyquist")
    if np.any(decays <= 0):
        raise ValueError("decays_s must be positive")
    out = np.zeros_like(x)
    for f, decay, amp in zip(freqs, decays, amps):
        theta = 2 * np.pi * f / sample_rate
        r = math.exp(-_T60 / (decay * sample_rate))
        out += lfilter([amp * math.sin(theta)], [1.0, -2 * r * math.cos(theta), r * r], x, axis=0)
    return _finite_result(out)


def pluck(
    freq_hz: float,
    sample_rate: int,
    *,
    excitation: np.ndarray,
    frames: int,
    decay_s: float,
    brightness: float = 0.5,
) -> np.ndarray:
    """Karplus-Strong string: `excitation` (mono, e.g. a noise burst) feeds a tuned loop.

    The loop averages neighbouring samples with weight s = 0.5·(1-brightness)
    (brightness 1 = no damping filter) and a first-order allpass sets the fractional
    delay, so the fundamental lands on freq_hz. Loop gain makes the fundamental decay
    60 dB in decay_s; higher partials decay faster when brightness < 1. Excitation
    longer than `frames` is cut; shorter is zero-padded. Frequency is fixed per call.
    The loop passes DC, so an excitation with an offset leaves a slowly decaying offset;
    remove it from the excitation or high-pass the result.
    """
    _rate(sample_rate)
    frames = _frames(frames)
    freq = _scalar(freq_hz, "freq_hz")
    decay = _scalar(decay_s, "decay_s")
    bright = _scalar(brightness, "brightness")
    if not 20.0 <= freq < sample_rate / 4:
        raise ValueError("freq_hz must be at least 20 Hz and below a quarter of the sample rate")
    if decay <= 0:
        raise ValueError("decay_s must be positive")
    if not 0.0 <= bright <= 1.0:
        raise ValueError("brightness must be between 0 and 1")
    x = _audio(excitation)
    if x.ndim != 1:
        raise ValueError("excitation must be mono (frames,)")
    drive = np.zeros(frames)
    drive[: min(frames, len(x))] = x[:frames]
    s = 0.5 * (1.0 - bright)
    theta = 2 * np.pi * freq / sample_rate
    loop_delay = sample_rate / freq - s
    integer = math.floor(loop_delay - 0.5)
    fraction = loop_delay - integer
    allpass = (1.0 - fraction) / (1.0 + fraction)
    filter_gain = math.sqrt((1 - s) ** 2 + s * s + 2 * s * (1 - s) * math.cos(theta))
    gain = 10 ** (-3.0 / (decay * freq)) / filter_gain
    if gain >= 1.0:
        raise ValueError("decay_s is too long for this brightness; the loop would not decay")
    return _finite_result(karplus_strong(drive, integer, s, allpass, gain))


def grains(
    source: np.ndarray,
    sample_rate: int,
    *,
    onsets_s,
    positions_s,
    durations_s,
    frames: int,
    rate=1.0,
    gain=1.0,
    pan=None,
    window: str = "hann",
) -> np.ndarray:
    """Overlap-add an explicit list of windowed grains read from mono `source`.

    Each grain starts at frame_of(onset), lasts frame_of(duration) frames (at least 1)
    and reads the source from `position` seconds, advancing `rate` source frames per
    output frame (negative plays backwards) with linear interpolation; reads outside
    the source are silent. rate/gain/pan are scalars or one value per grain. The caller
    decides density and randomness (e.g. with `noise` or a seeded NumPy generator).
    window is "hann" (sin², sampled at frame centres) or "triangle". Grains past `frames` are
    cut. Without `pan` the result is mono; with per-grain pan (-1..1, equal power) it
    is stereo (frames, 2).
    """
    src = _audio(source)
    if src.ndim != 1:
        raise ValueError("source must be mono (frames,)")
    _rate(sample_rate)
    frames = _frames(frames)
    onsets = np.atleast_1d(np.asarray(onsets_s, dtype=np.float64))
    count = len(onsets)
    columns = {}
    for name, value in (
        ("positions_s", positions_s),
        ("durations_s", durations_s),
        ("rate", rate),
        ("gain", gain),
    ):
        arr = np.asarray(value, dtype=np.float64)
        arr = np.full(count, float(arr)) if arr.ndim == 0 else arr
        if arr.shape != (count,) or not np.isfinite(arr).all():
            raise ValueError(f"{name} must be finite: a scalar or one value per grain")
        columns[name] = arr
    if onsets.ndim != 1 or not np.isfinite(onsets).all() or np.any(onsets < 0):
        raise ValueError("onsets_s must be finite nonnegative seconds")
    if np.any(columns["durations_s"] <= 0):
        raise ValueError("durations_s must be positive")
    if window not in ("hann", "triangle"):
        raise ValueError("window must be 'hann' or 'triangle'")
    pans = None
    if pan is not None:
        pans = np.asarray(pan, dtype=np.float64)
        pans = np.full(count, float(pans)) if pans.ndim == 0 else pans
        if pans.shape != (count,) or not np.isfinite(pans).all() or np.any(np.abs(pans) > 1):
            raise ValueError("pan must be between -1 and 1: a scalar or one value per grain")
    begins = np.floor(onsets * sample_rate + 0.5).astype(np.int64)
    lengths = np.maximum(1, np.floor(columns["durations_s"] * sample_rate + 0.5)).astype(np.int64)
    angle = (pans + 1) * (np.pi / 4) if pans is not None else np.zeros(count)
    out = overlap_grains(
        np.concatenate((src, [0.0])),
        begins,
        lengths,
        np.ascontiguousarray(columns["positions_s"] * sample_rate),
        np.ascontiguousarray(columns["rate"]),
        np.ascontiguousarray(columns["gain"]),
        np.cos(angle),
        np.sin(angle),
        window == "hann",
        frames,
        pans is not None,
    )
    out = out if pans is not None else out[:, 0]
    return _finite_result(out)
