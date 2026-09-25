"""Pedalboard parameter, automation, and instrument-rendering helpers shared across works.

`set_param` picks the nearest valid value for a VST3 discrete/string-labelled parameter
(parsing each label into a canonical unit so a request like "10 ms" doesn't silently
match a "9.97 s" label) or sets a built-in Pedalboard attribute directly, and returns
the value actually set so authors can keep it in source or a log. When a parameter's
unit (e.g. "semitones", "voices") isn't one of the known time/frequency/cents/dB/percent
families, it falls back to matching labels by their raw unit text instead of raising.
`process_automated` runs an effects chain block-by-block, calling an author-supplied
`update(t)` before each block so parameter automation reads as a curve function rather
than a hand-rolled loop, while handling the reset flag, tail padding, and plugin latency
alignment once instead of once per `render()`. `render_instrument` renders a VST
instrument plugin (MIDI in, audio out) to Tactus's `(frames, channels)` layout, running a
silent warm-up render first because a plugin's very first render after parameter changes
can carry an audible transient. Four probe-round agents each hand-wrote these pieces
independently (one got the unit wrong and produced a 10-second attack instead of 10ms;
two shipped instrument renders with an audible pop before the first note); this module
gives every future work the same tested implementation.

Reads: pedalboard
"""

from __future__ import annotations

import difflib
import math
from collections.abc import Iterable
from typing import Any

import numpy as np

__all__ = ["process_automated", "render_instrument", "set_param"]

# Canonical unit per family: ms (time), Hz (frequency), cents, dB, % (percent).
_TIME_TO_MS = {"ms": 1.0, "s": 1000.0}
_FREQ_TO_HZ = {"hz": 1.0, "khz": 1000.0}
_UNIT_ALIASES = {
    "ms": ("ms", "millisecond", "milliseconds"),
    "s": ("s", "sec", "secs", "second", "seconds"),
    "hz": ("hz",),
    "khz": ("khz",),
    "cents": ("cents", "cent"),
    "db": ("db",),
    "%": ("%", "percent"),
}
_TOKEN_FAMILY = {
    "ms": "time",
    "s": "time",
    "hz": "freq",
    "khz": "freq",
    "cents": "cents",
    "db": "db",
    "%": "percent",
}

_LOG_SPACE_FAMILIES = {"time", "freq"}


def _normalize_unit(unit: str) -> tuple[str, str] | tuple[None, None]:
    """Map a unit spelling (any case) to (canonical token, family), or (None, None)."""
    low = unit.strip().lower()
    for token, spellings in _UNIT_ALIASES.items():
        if low in spellings:
            return token, _TOKEN_FAMILY[token]
    return None, None


def _to_canonical(amount: float, token: str) -> float:
    if token in _TIME_TO_MS:
        return amount * _TIME_TO_MS[token]
    if token in _FREQ_TO_HZ:
        return amount * _FREQ_TO_HZ[token]
    return amount  # cents / dB / % are already their own canonical unit


def _split_label_text(label: str) -> tuple[float, str] | None:
    """Split '10.16 ms' -> (10.16, 'ms'); a bare number returns unit=''."""
    text = label.strip()
    idx = len(text)
    while idx > 0 and (text[idx - 1].isalpha() or text[idx - 1] == "%"):
        idx -= 1
    number_part, unit_part = text[:idx].strip(), text[idx:].strip()
    try:
        return float(number_part), unit_part
    except ValueError:
        return None


def _parse_label(label: Any, param_units: str | None) -> tuple[float, str] | None:
    """Parse one valid_values entry into (canonical_value, family); None if unparseable."""
    if isinstance(label, bool):
        return None
    if isinstance(label, (int, float)):
        if not param_units:
            return None
        token, family = _normalize_unit(param_units)
        if token is None:
            return None
        return _to_canonical(float(label), token), family
    if isinstance(label, str):
        split = _split_label_text(label)
        if split is None:
            return None
        amount, unit_text = split
        if unit_text:
            token, family = _normalize_unit(unit_text)
            if token is None:
                return None
            return _to_canonical(amount, token), family
        if param_units:
            token, family = _normalize_unit(param_units)
            if token is not None:
                return _to_canonical(amount, token), family
        return None  # bare number, no unit anywhere to anchor a family
    return None


def _closest_names(name: str, candidates: Iterable[str]) -> list[str]:
    return difflib.get_close_matches(name, list(candidates), n=5, cutoff=0.0)


def _distance(a: float, b: float, family: str) -> float:
    if family in _LOG_SPACE_FAMILIES and a > 0 and b > 0:
        return abs(math.log(a) - math.log(b))
    return abs(a - b)


def _raw_token(text: str) -> str:
    """Lowercase/trim a unit spelling and tolerate a simple trailing-s plural."""
    low = text.strip().lower()
    if len(low) > 1 and low.endswith("s") and not low.endswith("ss"):
        return low[:-1]
    return low


def _raw_split_label(label: Any, param_units: str | None) -> tuple[float, str] | None:
    """Parse one valid_values entry into (amount, raw unit token) without requiring the
    unit to belong to a known family; None if unparseable or unanchored."""
    if isinstance(label, bool):
        return None
    if isinstance(label, (int, float)):
        if not param_units:
            return None
        return float(label), _raw_token(param_units)
    if isinstance(label, str):
        split = _split_label_text(label)
        if split is None:
            return None
        amount, unit_text = split
        if unit_text:
            return amount, _raw_token(unit_text)
        if param_units:
            return amount, _raw_token(param_units)
        return None
    return None


def _nearest_by_raw_unit(
    valid_values: list[Any], param_units: str | None, unit: str, value: Any
) -> Any | None:
    """Nearest-match among labels whose raw unit token equals `unit`'s, comparing the
    numeric amounts linearly. Returns None (never raises) when nothing matches."""
    requested_token = _raw_token(unit)
    requested_amount = float(value)
    best_candidate, best_distance = None, None
    for candidate in valid_values:
        parsed = _raw_split_label(candidate, param_units)
        if parsed is None or parsed[1] != requested_token:
            continue
        d = abs(parsed[0] - requested_amount)
        if best_distance is None or d < best_distance:
            best_candidate, best_distance = candidate, d
    return best_candidate


def _choose_discrete(
    param: Any, valid_values: list[Any], name: str, value: Any, unit: str | None
) -> Any:
    param_units = getattr(param, "units", None)

    if isinstance(value, str):
        for candidate in valid_values:
            if candidate == value or str(candidate) == value:
                return candidate
        raise ValueError(
            f"{value!r} is not a valid value for parameter {name!r}; "
            f"valid values include {valid_values[:10]!r}"
        )

    parsed = [(candidate, _parse_label(candidate, param_units)) for candidate in valid_values]
    parseable = [(candidate, p) for candidate, p in parsed if p is not None]
    known_family_ok = bool(parseable) and len(parseable) == len(valid_values)

    if known_family_ok:
        families = {family for _, (_, family) in parseable}
        if len(families) == 1:
            label_family = next(iter(families))
            requested: float | None = None
            if unit is None:
                requested = float(value)
            else:
                token, family = _normalize_unit(unit)
                if token is not None:
                    if family != label_family:
                        raise ValueError(
                            f"unit family mismatch for parameter {name!r}: requested unit "
                            f"{unit!r} is {family!r}, but valid values are in "
                            f"{label_family!r}"
                        )
                    requested = _to_canonical(float(value), token)
            if requested is not None:
                best_candidate, best_distance = None, None
                for candidate, (canonical, _family) in parseable:
                    d = _distance(canonical, requested, label_family)
                    if best_distance is None or d < best_distance:
                        best_candidate, best_distance = candidate, d
                return best_candidate
            # else: unit given but not a recognized family -> try raw-unit match below

    if unit is not None:
        raw_match = _nearest_by_raw_unit(valid_values, param_units, unit, value)
        if raw_match is not None:
            return raw_match

    for candidate in valid_values:
        if candidate == value:
            return candidate
    raise ValueError(
        f"could not match {value!r}"
        + (f" (unit {unit!r})" if unit is not None else "")
        + f" to a valid value for parameter {name!r}; some valid values: "
        f"{valid_values[:10]!r}"
    )


def _set_vst_value(plugin: Any, param: Any, name: str, value: Any, unit: str | None) -> Any:
    valid_values = list(getattr(param, "valid_values", None) or [])
    if valid_values:
        chosen = _choose_discrete(param, valid_values, name, value, unit)
        setattr(plugin, name, chosen)
        return chosen

    if unit is not None:
        raise ValueError(
            f"unit must be None for continuous parameter {name!r} (no discrete valid_values); "
            f"got {unit!r}"
        )
    lo, hi = getattr(param, "min_value", None), getattr(param, "max_value", None)
    if lo is not None and hi is not None and not (lo <= value <= hi):
        raise ValueError(f"{value!r} is outside valid range [{lo}, {hi}] for parameter {name!r}")
    setattr(plugin, name, value)
    return value


def set_param(plugin: Any, name: str, value: Any, unit: str | None = None) -> Any:
    """Set a Pedalboard plugin parameter and return the value actually set.

    VST3 discrete/string-labelled parameters are matched to the nearest valid value in a
    canonical unit derived from `value`+`unit`; continuous VST3 parameters and built-in
    Pedalboard attributes are set (and range- or existence-checked) directly.

    `unit` normally has to be one of the known families (ms/s, Hz/kHz, cents, dB, %),
    matched against the labels' parsed values in log space for time/frequency and linear
    space otherwise. When `unit` doesn't belong to a known family, or a label's own unit
    text doesn't (e.g. "semitones", "voices"), this falls back to matching labels whose
    raw unit token equals `unit`'s (case-insensitive, trimmed, tolerant of a simple
    trailing-s plural like "semitone"/"semitones"), comparing the numeric amounts
    linearly. Raises ValueError, listing some valid values, if nothing matches either way.
    """
    params = getattr(plugin, "parameters", None)
    if params is not None:
        if name not in params:
            close = _closest_names(name, params.keys())
            raise KeyError(f"unknown parameter {name!r}; closest matches: {close}")
        return _set_vst_value(plugin, params[name], name, value, unit)

    if not hasattr(plugin, name):
        candidates = [
            attr
            for attr in dir(plugin)
            if not attr.startswith("_") and not callable(getattr(plugin, attr, None))
        ]
        close = _closest_names(name, candidates)
        raise KeyError(f"unknown parameter {name!r}; closest matches: {close}")
    if unit is not None:
        raise ValueError(f"unit must be None for built-in parameter {name!r}; got {unit!r}")
    setattr(plugin, name, value)
    return value


def _total_latency(chain: Any) -> int:
    """Sum `reported_latency_samples` over every plugin in `chain` (0 for built-ins)."""
    if isinstance(chain, Iterable):
        plugins = list(chain)
    else:
        plugins = [chain]
    return sum(int(getattr(plugin, "reported_latency_samples", 0) or 0) for plugin in plugins)


def _pad_frames(audio: np.ndarray, n_frames: int) -> np.ndarray:
    if n_frames <= 0:
        return audio
    pad_shape = (n_frames,) if audio.ndim == 1 else (n_frames, audio.shape[1])
    return np.concatenate([audio, np.zeros(pad_shape, dtype=audio.dtype)], axis=0)


def _block_bounds(total_frames: int, block_frames: int) -> list[tuple[int, int]]:
    """Split [0, total_frames) into blocks of block_frames, merging a <3-frame remainder."""
    if total_frames <= 0:
        return []
    bounds = [
        (start, min(start + block_frames, total_frames))
        for start in range(0, total_frames, block_frames)
    ]
    if len(bounds) > 1:
        last_start, last_end = bounds[-1]
        if last_end - last_start < 3:
            prev_start, _prev_end = bounds[-2]
            bounds[-2] = (prev_start, last_end)
            bounds.pop()
    return bounds


def _validate_process_args(
    sample_rate: int, block_seconds: float, tail_seconds: float, audio: np.ndarray
) -> None:
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError(f"sample_rate must be a positive int, got {sample_rate!r}")
    if block_seconds <= 0:
        raise ValueError(f"block_seconds must be > 0, got {block_seconds!r}")
    if tail_seconds < 0:
        raise ValueError(f"tail_seconds must be >= 0, got {tail_seconds!r}")
    if audio.ndim not in (1, 2):
        raise ValueError(f"audio must be 1-D or 2-D (frames[, channels]), got shape {audio.shape}")
    if not np.all(np.isfinite(audio)):
        raise ValueError("audio must be finite (no NaN/Inf)")


def process_automated(
    chain: Any,
    audio: np.ndarray,
    sample_rate: int,
    update: Any,
    *,
    block_seconds: float = 0.02,
    tail_seconds: float = 0.0,
) -> np.ndarray:
    """Run `chain` over `audio` in blocks, calling `update(t)` before each block.

    `chain` is a `pedalboard.Pedalboard` or a single plugin; `audio` is Tactus layout
    `(frames, channels)` or `(frames,)`. The author mutates plugin parameters inside
    `update` (typically via `set_param`) to automate a curve over time. Output is the
    same layout, `tail_seconds` of silence appended, and plugin-reported latency shifted
    out so the result aligns with the input.
    """
    raw = np.asarray(audio)
    _validate_process_args(sample_rate, block_seconds, tail_seconds, raw)

    source = raw.astype(np.float32, copy=False)
    frames_in = source.shape[0]
    tail_frames = round(tail_seconds * sample_rate)
    latency = _total_latency(chain)

    padded = _pad_frames(source, tail_frames)
    padded = _pad_frames(padded, latency)

    block_frames = max(1, round(block_seconds * sample_rate))
    bounds = _block_bounds(padded.shape[0], block_frames)

    chunks = []
    for i, (start, end) in enumerate(bounds):
        update(start / sample_rate)
        chunks.append(chain(padded[start:end], sample_rate, reset=(i == 0)))

    if chunks:
        output = np.concatenate(chunks, axis=0)
    else:
        output = padded[:0].astype(np.float32, copy=False)

    if latency > 0:
        output = output[latency:]

    target_frames = frames_in + tail_frames
    output = output[:target_frames]
    return output.astype(np.float32, copy=False)


def _validate_render_instrument_args(
    duration: float, sample_rate: int, num_channels: int, warmup_seconds: float
) -> None:
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError(f"sample_rate must be a positive int, got {sample_rate!r}")
    if duration <= 0:
        raise ValueError(f"duration must be > 0, got {duration!r}")
    if warmup_seconds < 0:
        raise ValueError(f"warmup_seconds must be >= 0, got {warmup_seconds!r}")
    if num_channels not in (1, 2):
        raise ValueError(f"num_channels must be 1 or 2, got {num_channels!r}")


def render_instrument(
    plugin: Any,
    messages: Iterable[Any],
    *,
    duration: float,
    sample_rate: int,
    num_channels: int = 2,
    warmup_seconds: float = 1.0,
) -> np.ndarray:
    """Render a VST instrument plugin (MIDI in, audio out) to Tactus's `(frames,
    channels)` layout.

    `messages` are mido messages or `(bytes, seconds)` tuples, per Pedalboard's
    `VST3Plugin.__call__`; each message's time is absolute seconds from the start of
    this render (0 = first sample). Before rendering `messages`, this runs a silent
    warm-up render of `warmup_seconds` on the same plugin instance (skipped when
    `warmup_seconds` is 0): a plugin's first render after `set_param` calls can carry an
    audible start transient even when no notes play in that render, so the warm-up
    absorbs it. The performance render then runs with `reset=False` so it continues from
    the warmed-up state instead of resetting the plugin (which brings the transient
    back). Pedalboard returns instrument audio as `(channels, frames)`; this transposes
    to Tactus's `(frames, channels)` before returning, at exactly `round(duration *
    sample_rate)` frames (padded with silence or truncated if the plugin returns a
    different length).
    """
    _validate_render_instrument_args(duration, sample_rate, num_channels, warmup_seconds)

    if warmup_seconds > 0:
        plugin([], duration=warmup_seconds, sample_rate=sample_rate, num_channels=num_channels)

    raw = plugin(
        list(messages),
        duration=duration,
        sample_rate=sample_rate,
        num_channels=num_channels,
        reset=False,
    )
    audio = np.asarray(raw)
    if audio.ndim != 2:
        raise ValueError(
            f"expected 2-D (channels, frames) instrument output, got shape {audio.shape}"
        )
    audio = audio.T  # (channels, frames) -> Tactus (frames, channels)

    target_frames = round(duration * sample_rate)
    if audio.shape[0] < target_frames:
        pad = target_frames - audio.shape[0]
        audio = np.concatenate([audio, np.zeros((pad, audio.shape[1]), dtype=audio.dtype)], axis=0)
    else:
        audio = audio[:target_frames]

    return audio.astype(np.float32, copy=False)
