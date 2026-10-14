"""join: continuity at declared positions: seams, loop wraps, crossfades and onset phase.

One aspect of sound: what happens where the work says audio is joined. The caller declares
positions in seconds on this input's clock (`at_s`), a loop wrap (`wrap`: the last frame runs
into frame 0; `wrap_range_s`: a loop embedded in a longer file) and, optionally, ordinary
positions of the same music to compare against (`reference_s`, e.g. bar lines). Positions
resolve to frames with `tactus.timing.frame_of`; a join at frame j is the boundary between
samples j-1 and j. A wrap is measured on the virtual concatenation of the loop's tail and
head, which is what a player looping it plays. Nothing is estimated: no tempo, bars or
downbeats, and no map is read; bars-to-seconds stays with the work.

Every analysis reports numbers only; none says whether a join is acceptable. A single
reference ratio misleads (one drum attack dominates "the largest step inside"), so `seams`
reports the step, the prediction error and a high-frequency burst at each position next to
whole-input and caller-supplied references, and leaves the comparison to the work.

Channel policy: steps and prediction residuals take the maximum over channels (a click in one
channel is a click); levels average channel powers like `level.rms`; onsets use
`rhythm.onsets` (channels averaged). No positions gives empty results.
Definitions and the evidence behind them are maintained in docs/analysis.md.

Reads: numpy · scipy.linalg · scipy.signal · timing · schema · rhythm · _level
"""

from __future__ import annotations

import inspect
import math
from functools import wraps
from typing import Any

import numpy as np
from scipy.linalg import solve_toeplitz
from scipy.signal import butter, lfilter, sosfiltfilt

from ..timing import frame_of
from . import _level as _windows
from . import rhythm, schema
from ._revision import revision as _revision

_SCHEMA_DOC = (
    "\n\n    schema (object): versioned data fields, axes, units, timestamp positions and "
    "special-value encodings; coordinates are relative to this input. "
    "See docs/analysis.md#data-schema.\n"
)


def _declared(declare):
    """Attach a public `schema.attach` declaration after the computation succeeds."""

    def decorate(fn):
        signature = inspect.signature(fn)

        @wraps(fn)
        def described(*args, **kwargs) -> dict[str, Any]:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            result = fn(*args, **kwargs)
            rate = int(bound.arguments["sample_rate"])
            fields, coordinates, parameters = declare(result, rate)
            return schema.attach(
                result,
                sample_rate=rate,
                frames=len(bound.arguments["audio"]),
                fields=fields,
                coordinate_keys=coordinates,
                parameter_keys=parameters,
            )

        described.__doc__ = (fn.__doc__ or "").rstrip() + _SCHEMA_DOC
        return described

    return decorate


# -- positions ---------------------------------------------------------------------------


def _frames(audio, sample_rate) -> np.ndarray:
    x = _windows.audio_frames(audio, sample_rate)
    if len(x) < 2:
        raise ValueError("audio must have at least two frames")
    return x


def _seconds_list(values, name) -> list[float]:
    if values is None:
        return []
    if not isinstance(values, (list, tuple, np.ndarray)):
        raise TypeError(f"{name} must be a list of seconds")
    out = []
    for value in values:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
            raise TypeError(f"{name} must contain numbers of seconds, got {value!r}")
        if not math.isfinite(value):
            raise ValueError(f"{name} must contain finite seconds, got {value!r}")
        out.append(float(value))
    return out


def _resolve(seconds, rate, frames, name) -> int:
    frame = frame_of(seconds, rate)
    if not 1 <= frame <= frames - 1:
        raise ValueError(
            f"{name} {seconds} s resolves to frame {frame}, outside [1, {frames - 1}] "
            f"for an input of {frames} frames"
        )
    return frame


def _positions(x, rate, at_s, wrap, wrap_range_s, *, kind="join", name="at_s"):
    """[(kind, frame, to_frame, before_end, after_start, loop_frames)] in declared order."""
    frames = len(x)
    out = [
        (kind, f, None, f, f, None)
        for f in (_resolve(s, rate, frames, name) for s in _seconds_list(at_s, name))
    ]
    if not isinstance(wrap, (bool, np.bool_)):
        raise TypeError("wrap must be true or false")
    if wrap:
        out.append(("wrap", frames, 0, frames, 0, frames))
    if wrap_range_s is not None:
        pair = _seconds_list(wrap_range_s, "wrap_range_s")
        if len(pair) != 2:
            raise ValueError("wrap_range_s must be [start, end] in seconds")
        start, end = (frame_of(s, rate) for s in pair)
        if not (0 <= start and end <= frames and end - start >= 2):
            raise ValueError(
                f"wrap_range_s {pair} resolves to frames [{start}, {end}), which must lie in "
                f"[0, {frames}] and span at least two frames"
            )
        out.append(("wrap", end, start, end, start, end - start))
    return out


def _context(x, position, n):
    """Samples before and after one position: at most n each side, half a loop for wraps."""
    _, _, _, before_end, after_start, loop = position
    if loop is None:
        return x[max(0, before_end - n) : before_end], x[after_start : after_start + n]
    m = min(n, loop // 2)
    return x[before_end - m : before_end], x[after_start : after_start + m]


def _record_base(position, rate):
    kind, frame, to_frame, *_ = position
    return {
        "kind": kind,
        "time_s": frame / rate,
        "frame": frame,
        "to_s": None if to_frame is None else to_frame / rate,
    }


def _db_power(power):
    return 10 * math.log10(power) if power > 0 else None


def _rms_dbfs(block):
    return _db_power(float(np.mean(np.square(block)))) if block.size else None


# -- seams ---------------------------------------------------------------------------------


def _lpc(fit, order):
    """Autocorrelation-method predictor of `fit` (Hann-windowed); None for silence."""
    w = fit * np.hanning(len(fit) + 2)[1:-1]
    r = np.array([np.dot(w[: len(w) - k], w[k:]) for k in range(order + 1)])
    if r[0] <= 0:
        return None
    r[0] *= 1 + 1e-9  # diagonal loading keeps nearly periodic material solvable
    return solve_toeplitz(r[:order], r[1:])


_PREDICTED = 1  # samples predicted past the boundary
_FLOOR = 1e-6  # FS (-120 dBFS): residual RMS floor, so a near-silent fit region stays finite


def _residual_ratio(pre, post, order, fit_n):
    """Prediction error of the first sample past the boundary / RMS error over the fit region,
    as dB. Only the boundary sample: later samples would measure how new the following
    material is (any onset over a quiet bed), not whether the boundary breaks."""
    fit = pre[-fit_n:]
    if len(fit) <= 2 * order or len(post) < 1:
        return None
    a = _lpc(fit, order)
    if a is None:  # digital silence: it predicts silence, so any sample past it is the error
        return 20 * math.log10(max(float(np.max(np.abs(post[:_PREDICTED]))), _FLOOR) / _FLOOR)
    inverse = np.concatenate(([1.0], -a))
    inside = lfilter(inverse, 1, fit)[order:]
    sigma = max(math.sqrt(float(np.mean(np.square(inside)))), _FLOOR)
    across = np.concatenate((fit[-order:], post[:_PREDICTED]))
    error = float(np.max(np.abs(lfilter(inverse, 1, across)[order:])))
    return 20 * math.log10(max(error, _FLOOR) / sigma)


def _seam(pre, post, *, window_n, click_n, order, fit_n, sos):
    """Measures at one boundary between `pre` and `post` (frames, channels)."""
    step = float(np.max(np.abs(post[0] - pre[-1])))
    slope = None
    if len(pre) >= 2 and len(post) >= 2:
        slope = float(np.max(np.abs((post[1] - post[0]) - (pre[-1] - pre[-2]))))
    residuals = []
    for ch in range(pre.shape[1]):
        for before, after in ((pre[:, ch], post[:, ch]), (post[::-1, ch], pre[::-1, ch])):
            value = _residual_ratio(before, after, order, fit_n)
            if value is not None:
                residuals.append(value)
    w = min(window_n, len(pre), len(post))
    before, after = pre[len(pre) - w :], post[:w]
    level_before, level_after = _rms_dbfs(before), _rms_dbfs(after)
    change = None
    if level_before is not None and level_after is not None:
        change = level_after - level_before
    peak = float(np.max(np.abs(np.concatenate((before, after)))))
    hf = None
    c = min(click_n, len(pre), len(post))
    local = np.concatenate((pre, post))
    if len(local) > 30:
        filtered = sosfiltfilt(sos, local, axis=0)
        hf = float(np.mean(np.square(filtered[len(pre) - c : len(pre) + c])))
    return {
        "window_samples": w,
        "step": step,
        "slope_step": slope,
        "residual_db": max(residuals) if residuals else None,
        "hf_energy": hf,
        "level_before_dbfs": level_before,
        "level_after_dbfs": level_after,
        "level_change_db": change,
        "peak_dbfs": 20 * math.log10(peak) if peak > 0 else None,
    }


def _summary(records, key, stat):
    values = [r[key] for r in records if r[key] is not None]
    if not values:
        return None
    if stat == "max_abs":
        return float(max(abs(v) for v in values))
    return float(np.median(values) if stat == "median" else max(values))


def _seams_schema(result, rate):
    db = "dB"
    time = schema.axis("time_s", "time", "s", "nonuniform", origin="input_start", at="point")
    attributes = {
        "kind": {"unit": "category", "categories": ["join", "wrap", "reference"]},
        "frame": schema.value("boundary_frame", "frame", boundary="between frame-1 and frame"),
        "to_s": schema.value(
            "wrap_target_time", "s", sentinel="null", meaning="not_a_wrap", origin="input_start"
        ),
        "window_samples": schema.value("level_window", "sample"),
        "step": schema.value("sample_step", "FS", channels="max"),
        "slope_step": schema.value(
            "slope_change", "FS/sample", sentinel="null", meaning="insufficient_context",
            channels="max",
        ),
        "residual_db": schema.value(
            "prediction_error", "dB re fit-region residual RMS", sentinel="null",
            meaning="insufficient_context", channels="max",
        ),
        "hf_burst_db": schema.value(
            "high_frequency_burst", "dB re baseline high-passed power", sentinel="null",
            meaning="zero_energy_or_no_baseline",
        ),
        "level_before_dbfs": schema.value("rms", "dBFS", sentinel="null", meaning="zero_energy"),
        "level_after_dbfs": schema.value("rms", "dBFS", sentinel="null", meaning="zero_energy"),
        "level_change_db": schema.value(
            "rms_change", db, sentinel="null", meaning="zero_energy_on_either_side"
        ),
        "peak_dbfs": schema.value(
            "sample_peak", "dBFS", sentinel="null", meaning="digital_silence"
        ),
    }
    fields = {
        key: schema.events(dict(time), layout="records", attributes=attributes)
        for key in ("joins", "references")
    }
    fields["typical_step_p999"] = schema.summary("sample_step_99.9th_percentile", "FS")
    fields["typical_step_max"] = schema.summary("sample_step_maximum", "FS")
    for key, quantity, unit in (
        ("reference_step_median", "sample_step", "FS"),
        ("reference_step_max", "sample_step", "FS"),
        ("reference_residual_db_median", "prediction_error", "dB re fit-region residual RMS"),
        ("reference_residual_db_max", "prediction_error", "dB re fit-region residual RMS"),
        ("reference_hf_burst_db_max", "high_frequency_burst", "dB re baseline"),
        ("reference_level_change_db_max_abs", "rms_change", db),
    ):
        fields[key] = schema.summary(
            quantity, unit, sentinel="null", meaning="no_reference_values"
        )
    parameters = [
        "window_samples", "click_window_samples", "lpc_order", "lpc_fit_samples", "hf_baseline"
    ]
    return fields, [], parameters


@_revision(2)  # 2: sound entering from digital silence is measured, not null
@_declared(_seams_schema)
def seams(
    audio: np.ndarray,
    sample_rate: int,
    *,
    at_s: list[float] | None = None,
    wrap: bool = False,
    wrap_range_s: list[float] | None = None,
    reference_s: list[float] | None = None,
    window_s: float = 0.5,
    click_window_s: float = 0.001,
    lpc_order: int = 16,
    lpc_fit_s: float = 0.01,
    hf_hz: float = 8000.0,
) -> dict[str, Any]:
    """Discontinuity, level and peak at declared joins and loop wraps, beside references.

    Positions: `at_s` (seconds on this input's clock, each in frames [1, frames-1] after
    `timing.frame_of`), `wrap` (last frame -> frame 0 of this input, which must be one cycle),
    `wrap_range_s` ([start, end] of a loop inside a longer input; end may equal the input
    length). `reference_s` are ordinary positions of the same music (e.g. bar lines) measured
    the same way. Wrap context is clipped to half the loop. Records keep the declared order:
    at_s, then wrap, then wrap_range_s. Positions out of range raise ValueError.

    Measures at a boundary between samples j-1 and j (maximum over channels):
    step = |x[j] - x[j-1]|; slope_step = |(x[j+1]-x[j]) - (x[j-1]-x[j-2])|;
    residual_db = an order-`lpc_order` autocorrelation-method linear predictor (Hann-windowed,
    fitted on the `lpc_fit_s` before the boundary) predicts the first sample after it; |error|
    relative to the RMS error inside the fit region, in dB; the same backwards from the other
    side, the larger reported (residual RMS floored at -120 dBFS, so sound entering from silence,
    digital or near, reads very high rather than infinite; silence after silence reads 0). It responds to amplitude and slope breaks
    that a step alone misses, and to impulses. One sample's error varies by 10-20 dB between
    ordinary positions of real music: compare with references, not with zero. Only the
    boundary sample is predicted; later samples would measure how new the following material
    is (any onset over a quiet bed is unpredictable), not whether the boundary breaks.
    hf_burst_db = power above `hf_hz` (4th-order Butterworth high-pass, zero-phase) in
    +/-click_window_s around the boundary relative to the median of the same measure at
    `reference_s`, or, with no references, over windows every 50 ms of the input.
    Levels use `window_s` each side (shortened equally near the input's or loop's edges; pass
    one bar when a downbeat makes short windows unfair); they average channel powers.

    Returns:
        joins (records): one per declared position with kind ("join" | "wrap"), time_s (s,
            resolved frame / rate; a wrap sits at its end frame), frame (frames), to_s (s,
            wrap target or null), window_samples (samples, level window used), step (FS),
            slope_step (FS/sample, null without two samples each side), residual_db (dB, null
            for a too short fit region), hf_burst_db (dB, null when either energy is
            zero), level_before_dbfs / level_after_dbfs (dBFS, null for zero energy),
            level_change_db (dB, after minus before), peak_dbfs (dBFS over both windows).
        references (records): the same fields at reference_s, kind "reference".
        typical_step_p999 (FS): 99.9th percentile of |x[j]-x[j-1]| over the whole input.
        typical_step_max (FS): its maximum; usually one transient, shown because the works'
            old "wrap step <= max step inside" checks used it.
        reference_step_median (FS), reference_step_max (FS): over references, null without.
        reference_residual_db_median (dB), reference_residual_db_max (dB): same.
        reference_hf_burst_db_max (dB): largest reference hf_burst_db.
        reference_level_change_db_max_abs (dB): largest |level_change_db| at references.
        window_samples (samples): round(window_s * rate) before edge clipping.
        click_window_samples (samples): round(click_window_s * rate).
        lpc_order (count): predictor order.
        lpc_fit_samples (samples): round(lpc_fit_s * rate).
        hf_baseline (label): "references", "grid_50ms" or null when nothing was measured.
    """
    x = _frames(audio, sample_rate)
    rate = int(sample_rate)
    for name, value in (("window_s", window_s), ("click_window_s", click_window_s),
                        ("lpc_fit_s", lpc_fit_s)):
        if isinstance(value, (bool, np.bool_)) or not np.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if isinstance(lpc_order, (bool, np.bool_)) or int(lpc_order) != lpc_order or lpc_order < 1:
        raise ValueError("lpc_order must be a positive integer")
    order = int(lpc_order)
    if not 0 < hf_hz < rate / 2:
        raise ValueError(f"hf_hz must lie between 0 and Nyquist ({rate / 2} Hz)")
    window_n = max(1, round(window_s * rate))
    click_n = max(1, round(click_window_s * rate))
    fit_n = max(1, round(lpc_fit_s * rate))
    sos = butter(4, hf_hz, btype="highpass", fs=rate, output="sos")
    context_n = max(window_n, fit_n, 3 * click_n)
    options = {
        "window_n": window_n, "click_n": click_n, "order": order, "fit_n": fit_n, "sos": sos
    }

    def measure(positions):
        records = []
        for position in positions:
            pre, post = _context(x, position, context_n)
            records.append({**_record_base(position, rate), **_seam(pre, post, **options)})
        return records

    joins = measure(_positions(x, rate, at_s, wrap, wrap_range_s))
    references = measure(
        _positions(x, rate, reference_s, False, None, kind="reference", name="reference_s")
    )
    baseline, baseline_name = None, None
    if references:
        energies = [r["hf_energy"] for r in references if r["hf_energy"] is not None]
        baseline, baseline_name = (float(np.median(energies)) if energies else None), "references"
    elif joins:
        filtered = sosfiltfilt(sos, x, axis=0) if len(x) > 30 else None
        centres = np.arange(click_n, len(x) - click_n + 1, max(1, round(0.05 * rate)))
        if filtered is not None and len(centres):
            power = np.mean(np.square(filtered), axis=1)
            cumulative = np.concatenate(([0.0], np.cumsum(power)))
            energies = (cumulative[centres + click_n] - cumulative[centres - click_n]) / (
                2 * click_n
            )
            baseline = float(np.median(energies))
        baseline_name = "grid_50ms"
    for record in (*joins, *references):
        energy = record.pop("hf_energy")
        record["hf_burst_db"] = (
            10 * math.log10(energy / baseline) if energy and baseline else None
        )
    steps = np.max(np.abs(np.diff(x, axis=0)), axis=1)
    return {
        "joins": joins,
        "references": references,
        "typical_step_p999": float(np.percentile(steps, 99.9)),
        "typical_step_max": float(np.max(steps)),
        "reference_step_median": _summary(references, "step", "median"),
        "reference_step_max": _summary(references, "step", "max"),
        "reference_residual_db_median": _summary(references, "residual_db", "median"),
        "reference_residual_db_max": _summary(references, "residual_db", "max"),
        "reference_hf_burst_db_max": _summary(references, "hf_burst_db", "max"),
        "reference_level_change_db_max_abs": _summary(references, "level_change_db", "max_abs"),
        "window_samples": window_n,
        "click_window_samples": click_n,
        "lpc_order": order,
        "lpc_fit_samples": fit_n,
        "hf_baseline": baseline_name,
    }


# -- fades ---------------------------------------------------------------------------------


def _fades_schema(result, rate):
    window = result["window_samples"] / rate
    fields = {
        "positions": schema.events(
            schema.axis("time_s", "time", "s", "nonuniform", origin="input_start", at="point"),
            layout="records",
            attributes={
                "kind": {"unit": "category", "categories": ["join", "wrap"]},
                "frame": schema.value("boundary_frame", "frame"),
                "to_s": schema.value(
                    "wrap_target_time", "s", sentinel="null", meaning="not_a_wrap",
                    origin="input_start",
                ),
                "span_samples": schema.value("contour_span_each_side", "sample"),
                "before_dbfs": schema.value(
                    "rms", "dBFS", sentinel="null", meaning="zero_energy", region="outer_quarter"
                ),
                "after_dbfs": schema.value(
                    "rms", "dBFS", sentinel="null", meaning="zero_energy", region="outer_quarter"
                ),
                "dip_db": schema.value(
                    "contour_dip", "dB re quieter side", sentinel="null", meaning="zero_energy"
                ),
                "bump_db": schema.value(
                    "contour_bump", "dB re louder side", sentinel="null", meaning="zero_energy"
                ),
            },
        ),
        "curve": schema.series(
            schema.axis(
                "offset_s", "time", "s", "nonuniform", origin="position", at="end",
                width=window, hop=result["hop_samples"] / rate, padding="none",
                end_exclusive=True,
            ),
            {"key": "rms_dbfs", **schema.value("rms", "dBFS", sentinel="null",
                                               meaning="zero_energy")},
            layout="records",
            attributes={"position": {"unit": "index", "index_base": 0}},
        ),
    }
    return fields, [], ["window_samples", "hop_samples"]


@_revision(1)
@_declared(_fades_schema)
def fades(
    audio: np.ndarray,
    sample_rate: int,
    *,
    at_s: list[float] | None = None,
    wrap: bool = False,
    wrap_range_s: list[float] | None = None,
    span_s: float = 0.1,
    hop_s: float = 0.005,
    window_s: float = 0.01,
) -> dict[str, Any]:
    """RMS contour through each declared join or wrap: shows a dip or bump at a crossfade.

    Positions as in `seams` (at_s, wrap, wrap_range_s; resolved with `timing.frame_of`).
    Around each boundary, complete rectangular windows of round(window_s*rate) samples end at
    the boundary plus multiples of round(hop_s*rate), all within +/-span_s (clipped to half a
    loop for wraps); levels average channel powers (as `level.rms_curve`). before_dbfs and
    after_dbfs are the power-mean levels of the outer quarter of windows on each side.
    dip_db = curve minimum minus the quieter side; bump_db = curve maximum minus the louder
    side, so a plain level step reads near 0 for both. An equal-gain crossfade of uncorrelated
    material dips about 3 dB; equal-power stays near 0. The analysis does not know the
    material's correlation and does not verify a crossfade law. Short windows on noise read a
    few tenths of a dB low at the minimum; widen window_s for steadier contours.

    Returns:
        positions (records): kind ("join" | "wrap"), time_s (s), frame (frames), to_s (s or
            null), span_samples (samples used each side), before_dbfs (dBFS), after_dbfs
            (dBFS), dip_db (dB), bump_db (dB); null where a side has zero energy.
        curve (records): position (index into positions), offset_s (s, window end relative to
            the boundary), rms_dbfs (dBFS, null for zero energy).
        window_samples (samples): resolved window.
        hop_samples (samples): resolved hop.
    """
    x = _frames(audio, sample_rate)
    rate = int(sample_rate)
    if isinstance(span_s, (bool, np.bool_)) or not np.isfinite(span_s) or span_s <= 0:
        raise ValueError("span_s must be finite and positive")
    _, window_n, hop_n = _windows.window_grid(2 * round(span_s * rate), rate, window_s, hop_s)
    span_n = max(1, round(span_s * rate))
    positions, curve = [], []
    for index, position in enumerate(_positions(x, rate, at_s, wrap, wrap_range_s)):
        pre, post = _context(x, position, span_n)
        local = np.concatenate((pre, post))
        power = np.concatenate(([0.0], np.cumsum(np.mean(np.square(local), axis=1))))
        boundary = len(pre)
        low = -((boundary - window_n) // hop_n) if boundary >= window_n else 1
        high = (len(local) - boundary) // hop_n
        ks = np.arange(low, high + 1)
        ends = boundary + ks * hop_n
        ks, ends = ks[ends >= window_n], ends[ends >= window_n]
        powers = (power[ends] - power[ends - window_n]) / window_n
        levels = [_db_power(float(p)) for p in powers]
        for k, value in zip(ks, levels, strict=True):
            curve.append({"position": index, "offset_s": int(k) * hop_n / rate, "rms_dbfs": value})
        quarter = max(1, len(powers) // 4)
        before = _db_power(float(np.mean(powers[:quarter]))) if len(powers) else None
        after = _db_power(float(np.mean(powers[-quarter:]))) if len(powers) else None
        finite = [v for v in levels if v is not None]
        dip = bump = None
        if before is not None and after is not None and finite:
            dip = min(finite) - min(before, after)
            bump = max(finite) - max(before, after)
        positions.append(
            {
                **_record_base(position, rate),
                "span_samples": min(len(pre), len(post)),
                "before_dbfs": before,
                "after_dbfs": after,
                "dip_db": dip,
                "bump_db": bump,
            }
        )
    return {
        "positions": positions,
        "curve": curve,
        "window_samples": window_n,
        "hop_samples": hop_n,
    }


# -- onset phase ---------------------------------------------------------------------------


def _grid(beat_s, bpm, origin_s, subdivision):
    """A function t -> (nearest grid time, grid index, local spacing)."""
    if isinstance(subdivision, (bool, np.bool_)) or int(subdivision) != subdivision or (
        subdivision < 1
    ):
        raise ValueError("subdivision must be a positive integer")
    k = int(subdivision)
    beats = _seconds_list(beat_s, "beat_s")
    if beats and bpm is not None:
        raise ValueError("give either beat_s or bpm (with origin_s), not both")
    if beats:
        if len(beats) < 2 or np.any(np.diff(beats) <= 0):
            raise ValueError("beat_s needs at least two increasing beat times")
        b = np.asarray(beats)
        points = np.concatenate(
            [b[i] + (b[i + 1] - b[i]) * np.arange(k) / k for i in range(len(b) - 1)] + [b[-1:]]
        )

        def nearest(t):
            i = int(np.argmin(np.abs(points - t)))
            if t >= points[i]:
                spacing = points[min(i + 1, len(points) - 1)] - points[min(i, len(points) - 2)]
            else:
                spacing = points[max(i, 1)] - points[max(i - 1, 0)]
            return float(points[i]), i, float(spacing)

        return nearest
    if bpm is None:
        raise ValueError("onset_phase needs a grid: beat_s, or bpm with origin_s")
    if isinstance(bpm, (bool, np.bool_)) or not np.isfinite(bpm) or bpm <= 0:
        raise ValueError("bpm must be finite and positive")
    if not np.isfinite(origin_s):
        raise ValueError("origin_s must be finite")
    spacing = 60.0 / float(bpm) / k

    def nearest(t):
        n = math.floor((t - origin_s) / spacing + 0.5)
        return float(origin_s + n * spacing), n, spacing

    return nearest


def _ranges(ranges_s):
    if ranges_s is None:
        return []
    if not isinstance(ranges_s, (list, tuple)):
        raise TypeError("ranges_s must be a list of [start, end] pairs in seconds")
    out = []
    for item in ranges_s:
        pair = _seconds_list(item, "ranges_s")
        if len(pair) != 2 or not 0 <= pair[0] < pair[1]:
            raise ValueError(f"ranges_s entry {item!r} must be [start, end] with 0 <= start < end")
        out.append(pair)
    return out


def _onset_phase_schema(result, rate):
    hop = result["resolution_ms"] / 1000
    fields = {
        "onsets": schema.events(
            schema.axis(
                "time_s", "time", "s", "nonuniform", origin="input_start", at="point", hop=hop
            ),
            layout="records",
            empty="no_estimates",
            attributes={
                "range": {"unit": "index", "index_base": 0},
                "nearest_grid_s": schema.value("grid_time", "s", origin="input_start"),
                "grid_index": {"unit": "index", "index_base": 0, "of": "declared grid points"},
                "offset_ms": schema.value("onset_offset_from_grid", "ms"),
                "offset_subdivisions": schema.value(
                    "onset_offset_from_grid", "subdivision", range=[-0.5, 0.5]
                ),
            },
        ),
        "ranges": schema.events(
            schema.axis(
                "start_s", "time", "s", "nonuniform", origin="input_start", at="start",
                end_key="end_s", end_exclusive=True,
            ),
            layout="records",
            attributes={
                "count": schema.value("onsets", "count"),
                "median_offset_ms": schema.value(
                    "onset_offset_from_grid", "ms", sentinel="null", meaning="no_onsets"
                ),
                "median_abs_offset_ms": schema.value(
                    "absolute_onset_offset_from_grid", "ms", sentinel="null", meaning="no_onsets"
                ),
            },
        ),
    }
    return fields, [], ["resolution_ms"]


@_revision(1)
@_declared(_onset_phase_schema)
def onset_phase(
    audio: np.ndarray,
    sample_rate: int,
    *,
    ranges_s: list[list[float]] | None = None,
    beat_s: list[float] | None = None,
    bpm: float | None = None,
    origin_s: float = 0.0,
    subdivision: int = 1,
    hop_s: float = 0.005,
    filterbank: str = "mel",
    delta: float = 0.07,
) -> dict[str, Any]:
    """Onset candidates in declared ranges, as offsets from a declared beat grid.

    The grid is given, never estimated: `beat_s` (frozen beat times, at least two; points
    between consecutive beats are interpolated for subdivision > 1) or `bpm` plus `origin_s`
    (a regular grid through origin_s). `subdivision` 2 = eighths, 4 = sixteenths: offsets are
    to the nearest point of that grid, so eighth-note material reads near 0 with subdivision 2
    and near half a beat with 1. `ranges_s` are [start, end) pairs, e.g. four beats after each
    join; pass one range for a whole song. Onsets come from `rhythm.onsets` (SuperFlux,
    forwarded hop_s, filterbank, delta) over the whole input, so they are candidates on its
    compensated envelope grid, not sample-accurate attacks: a click at a known time reads up
    to one hop late or early. That frontend offset is reported as resolution_ms, not removed.
    The fold adds no bias of its own. No ranges gives empty results; ranges without a grid
    raise ValueError.

    Returns:
        onsets (records): range (index), time_s (s), nearest_grid_s (s), grid_index (index of
            the grid point: position in the subdivided beat_s list, or the integer n of
            origin_s + n*spacing), offset_ms (ms, onset minus grid), offset_subdivisions
            (subdivision, the same offset in grid spacings).
        ranges (records): start_s (s), end_s (s), count (onsets), median_offset_ms (ms) and
            median_abs_offset_ms (ms), null when the range has no onsets.
        resolution_ms (ms): the onset hop, round(hop_s * rate) / rate.
    """
    x = _frames(audio, sample_rate)
    rate = int(sample_rate)
    ranges = _ranges(ranges_s)
    hop_n = round(hop_s * rate) if np.isfinite(hop_s) else 0
    if hop_n < 1:
        raise ValueError("hop_s must round to at least one sample")
    onsets, records = [], []
    if ranges:
        nearest = _grid(beat_s, bpm, origin_s, subdivision)
        found = rhythm.onsets(x, rate, hop_s=hop_s, filterbank=filterbank, delta=delta)
        times = found["onsets_s"]
        hop_n = found["hop_samples"]
        for index, (start, end) in enumerate(ranges):
            offsets = []
            for t in (t for t in times if start <= t < end):
                g, n, spacing = nearest(t)
                offset = t - g
                offsets.append(offset * 1000)
                onsets.append(
                    {
                        "range": index,
                        "time_s": t,
                        "nearest_grid_s": g,
                        "grid_index": n,
                        "offset_ms": offset * 1000,
                        "offset_subdivisions": offset / spacing,
                    }
                )
            records.append(
                {
                    "start_s": start,
                    "end_s": end,
                    "count": len(offsets),
                    "median_offset_ms": float(np.median(offsets)) if offsets else None,
                    "median_abs_offset_ms": (
                        float(np.median(np.abs(offsets))) if offsets else None
                    ),
                }
            )
    elif beat_s or bpm is not None:
        _grid(beat_s, bpm, origin_s, subdivision)  # report a malformed grid even without ranges
    return {"onsets": onsets, "ranges": records, "resolution_ms": hop_n / rate * 1000}


ANALYSES = (seams, fades, onset_phase)
