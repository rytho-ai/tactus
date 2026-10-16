"""Waveguide voice and explicit performance events, with optional violin body.

render_bow returns float64 mono, unnormalized. Events are seconds relative to one
continuous bow; slur preserves the bow, while separate render calls retrigger it.
No ensembles, DAWG session expressions or sympathetic string bank are implicit.
"""

import math
from functools import lru_cache

import numpy as np
from scipy.signal import lfilter

from .bow_core import BowCore, compiled_core
from .bow_math import halfband_taps, unit

SPEC_KEYS = (
    "decay",
    "track",
    "damp",
    "pos",
    "pressure",
    "speed",
    "attack",
    "release",
    "tremhz",
    "unused",
    "sord",
)
DEFAULT_SPEC = {
    "decay": 0.6,
    "track": 0.5,
    "damp": 0.5,
    "pos": 0.12,
    "pressure": 0.5,
    "speed": 0.6,
    "attack": 0.08,
    "release": 0.15,
    "tremhz": 0.0,
    "sord": 0.0,
}


@lru_cache(maxsize=1)
def accelerated_class():
    return compiled_core()


def points(values, width):
    raw = np.asarray(values)
    if raw.dtype.kind not in "fiu" or (raw.size and (raw.ndim != 2 or raw.shape[1] != width)):
        raise ValueError(f"Curve points must be real rows with {width} columns")
    array = np.array(raw, dtype=np.float64).reshape(-1, width)
    if not np.isfinite(array).all() or (
        len(array) and (array[0, 0] < 0 or np.any(np.diff(array[:, 0]) <= 0))
    ):
        raise ValueError("Curve points must be finite, nonnegative and strictly chronological")
    return array


def make_voice(recipe, rate, *, compiled=True):
    spec = {**DEFAULT_SPEC, **recipe.get("spec", {})}
    if set(spec) != set(DEFAULT_SPEC):
        raise ValueError("Unknown bow parameter")
    for key, value in spec.items():
        if not math.isfinite(value):
            raise ValueError("Nonfinite bow parameter")
        if key in ("decay", "attack", "release") and not 0 < value <= 12:
            raise ValueError("Positive bow time <=12 seconds required")
        if key in ("track", "damp", "pressure", "speed", "sord") and not 0 <= value <= 1:
            raise ValueError("Bow controls must be in [0, 1]")
    if not 0.01 <= spec["pos"] <= 0.5 or not 0 <= spec["tremhz"] <= 40:
        raise ValueError("Invalid bow position or tremolo rate")
    hz, velocity, hold = recipe["hz"], recipe.get("velocity", 0.8), recipe.get("hold", 1.0)
    seconds = recipe.get("seconds", 3.0)
    if (
        not isinstance(rate, int)
        or rate < 8000
        or not all(math.isfinite(x) for x in (hz, velocity, hold, seconds))
    ):
        raise ValueError("Finite note and integer sample rate >=8000 required")
    if not 20 <= hz < 0.4 * rate or not 0 <= velocity <= 1 or not (hold >= 0 and seconds >= 0):
        raise ValueError("Unsupported note frequency, velocity or duration")
    seed = recipe.get("seed", 1)
    if not isinstance(seed, int) or not 0 <= seed <= 0xFFFFFFFF:
        raise ValueError("Seed must be uint32")
    control = points(recipe.get("controls", []), 5)
    if len(control) and (np.any(control[:, 1:] < 0) or np.any(control[:, 1:] > 1)):
        raise ValueError("Controls must be in [0, 1]")
    cents = points(recipe.get("cents", []), 2)
    if len(cents) and np.any(abs(cents[:, 1]) > 100):
        raise ValueError("Pitch curve limited to +/-100 cents")
    vib_hz, vib_depth = recipe.get("vibrato_hz", 0.0), recipe.get("vibrato_cents", 0.0)
    if (
        not math.isfinite(vib_hz)
        or not math.isfinite(vib_depth)
        or not 0 <= vib_hz <= 20
        or not 0 <= vib_depth <= 100
    ):
        raise ValueError("Invalid vibrato")
    packed = np.array([spec.get(k, 0.0) for k in SPEC_KEYS])
    taps, offsets = halfband_taps()
    cls = accelerated_class() if compiled else BowCore
    return cls(
        packed,
        hz,
        velocity,
        hold,
        rate,
        seconds,
        spec["tremhz"] * (1 + 0.08 * (unit(seed, 0, 7) - 0.5)),
        unit(seed, 0, 8),
        taps,
        offsets,
        control,
        cents,
        vib_hz,
        vib_depth,
    )


def violin_body(audio, size, rate):
    if not math.isfinite(size) or size < 0.05:
        raise ValueError("Body size must be finite and >=.05")
    modes = [
        (275, 14, 1.0),
        (460, 18, 0.9),
        (540, 18, 1.1),
        (700, 12, 0.5),
        (1100, 8, 0.4),
        (2500, 3, 0.9),
        (3400, 4, 0.4),
    ]
    out = 0.3 * audio
    for hz, q, gain in modes:
        hz /= size
        if hz >= 0.45 * rate:
            continue
        w = 2 * math.pi * hz / rate
        alpha = math.sin(w) / (2 * q)
        a0 = 1 + alpha
        b0, a1, a2 = alpha / a0, -2 * math.cos(w) / a0, (1 - alpha) / a0
        # Equivalent transposed-DFII bandpass; accumulate modes in source order.
        out += gain * lfilter([b0, 0, -b0], [1, a1, a2], audio)
    return lfilter([1, -1], [1, -math.exp(-2 * math.pi * 10 / rate)], out)


def render_bow(recipe, rate=44100, *, compiled=True):
    voice = make_voice(recipe, rate, compiled=compiled)
    total = math.floor(recipe.get("seconds", 3.0) * rate + 0.5)
    out = np.zeros(total)
    events = recipe.get("events", [])
    previous = -1
    prepared = []
    for event in events:
        time = event["time"]
        if (
            not math.isfinite(time)
            or not 0 <= time <= recipe.get("seconds", 3.0)
            or time < previous
        ):
            raise ValueError("Events must be finite, in-range and chronological")
        at = math.floor(time * rate + 0.5)
        if event["kind"] not in ("slur", "release"):
            raise ValueError("Unknown bow event")
        if event["kind"] == "slur":
            hz, hold = event["hz"], event["hold"]
            if (
                not math.isfinite(hz)
                or not 20 <= hz < 0.4 * rate
                or not math.isfinite(hold)
                or hold < 0
            ):
                raise ValueError("Invalid slur")
            curve = points(event.get("cents", []), 2)
            if len(curve) and np.any(abs(curve[:, 1]) > 100):
                raise ValueError("Slur pitch curve limited to +/-100 cents")
        else:
            curve = np.empty((0, 2))
        prepared.append((at, event, curve))
        previous = time
    cursor = index = 0
    while cursor < total:
        while index < len(prepared) and prepared[index][0] <= cursor:
            at, event, curve = prepared[index]
            if event["kind"] == "slur":
                if not voice.can_slur_to(event["hz"]):
                    raise ValueError("Slur crosses two-octave or oversampling boundary")
                voice.slur_to(event["hz"], at, event["hold"], curve)
            else:
                voice.release_at(at)
            index += 1
        end = min(total, cursor + 128)
        if index < len(prepared):
            end = min(end, prepared[index][0])
        out[cursor:end] = voice.process(end - cursor)
        cursor = end
    if recipe.get("body_size") is not None:
        out = violin_body(out, recipe["body_size"], rate)
    return out


def render_bowed_string(
    freq_hz,
    rate,
    *,
    frames,
    hold_s,
    seed,
    velocity,
    parameters,
    body_size,
    controls,
    pitch_curve,
    vibrato_hz,
    vibrato_cents,
    events,
):
    """Normalize the public seconds/Hz contract into the verified voice recipe."""
    from ..dsp import _scalar

    if isinstance(seed, (bool, np.bool_)) or not isinstance(seed, (int, np.integer)):
        raise TypeError("bowed_string seed must be uint32")
    params = {} if parameters is None else dict(parameters)
    params = {key: _scalar(value, f"bow parameter {key}") for key, value in params.items()}
    recipe = {
        "hz": _scalar(freq_hz, "freq_hz"),
        "seconds": frames / rate,
        "hold": _scalar(hold_s, "hold_s"),
        "seed": int(seed),
        "velocity": _scalar(velocity, "velocity"),
        "spec": params,
        "controls": controls,
        "cents": pitch_curve,
        "vibrato_hz": _scalar(vibrato_hz, "vibrato_hz"),
        "vibrato_cents": _scalar(vibrato_cents, "vibrato_cents"),
    }
    if body_size is not None:
        recipe["body_size"] = _scalar(body_size, "body_size")
        if recipe["body_size"] < 0.05:
            raise ValueError("body_size must be >=0.05")
    normalized = []
    for event in events:
        kind = event.get("kind")
        allowed = (
            {"kind", "time_s"}
            if kind == "release"
            else {"kind", "time_s", "freq_hz", "hold_s", "pitch_curve"}
        )
        required = allowed - {"pitch_curve"}
        if (
            kind not in ("release", "slur")
            or not required <= event.keys()
            or event.keys() - allowed
        ):
            raise ValueError(
                "events need kind/time_s and slurs also freq_hz/hold_s, optional pitch_curve"
            )
        item = {"kind": kind, "time": _scalar(event["time_s"], "event time_s")}
        if kind == "slur":
            item.update(
                hz=_scalar(event["freq_hz"], "slur freq_hz"),
                hold=_scalar(event["hold_s"], "slur hold_s"),
                cents=event.get("pitch_curve", []),
            )
        normalized.append(item)
    recipe["events"] = normalized
    return render_bow(recipe, rate)
