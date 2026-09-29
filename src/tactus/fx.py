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
gives every future work the same tested implementation. `varispeed` plays audio back at a
per-frame speed so pitch moves with speed (tape stop, spin-down), which pytimestretch's
pitch-preserving engines cannot do; two probe Agents hand-wrote it for a tape stop.
`describe` lists a plugin's parameters (name, current value, units, range or valid
values) instead of assuming a scale: a full-song dogfood had an Agent set OB-Xf's
`amp_env_sustain` to 1.0 believing a 0-1 scale when it's 0-100%, and `set_param` accepted
it silently because 1.0 was in range. A survey of installed plugins found unit metadata
isn't general (OB-Xf reports units on most params, Dexed and the Cardinal/DrumCraker
plugins mostly don't), but name/range/valid-values/current-value are always there, so
discovery generalizes where units don't. `format_table` renders `describe`'s rows as
fixed-width text for a quick `print`. `fit_rms` brings audio to a target whole-signal RMS
without letting any sample cross a ceiling, using a smooth look-ahead gain envelope rather than
a hard-clipping limiter (`pedalboard.Limiter` left probe mixes with thousands of samples flat
at the ceiling).

Reads: pedalboard · scipy.ndimage
"""

from __future__ import annotations

import difflib
import inspect
import math
from collections.abc import Iterable
from typing import Any

import numpy as np
from scipy.ndimage import minimum_filter1d, uniform_filter1d

__all__ = [
    "describe",
    "fit_rms",
    "format_table",
    "process_automated",
    "render_instrument",
    "set_param",
    "varispeed",
]

_FIT_RMS_WINDOW_MS = 5.0

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


def _units_note(param_units: str | None) -> str:
    return f"; units={param_units!r}" if param_units else ""


def _choose_discrete(
    param: Any, valid_values: list[Any], name: str, value: Any, unit: str | None
) -> Any:
    param_units = getattr(param, "units", None)
    unit_note = _units_note(param_units)

    if isinstance(value, str):
        for candidate in valid_values:
            if candidate == value or str(candidate) == value:
                return candidate
        raise ValueError(
            f"{value!r} is not a valid value for parameter {name!r}; "
            f"valid values include {valid_values[:10]!r}{unit_note}"
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
                            f"{label_family!r}{unit_note}"
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
        f"{valid_values[:10]!r}{unit_note}"
    )


def _set_vst_value(plugin: Any, param: Any, name: str, value: Any, unit: str | None) -> Any:
    valid_values = list(getattr(param, "valid_values", None) or [])
    if valid_values:
        chosen = _choose_discrete(param, valid_values, name, value, unit)
        setattr(plugin, name, chosen)
        return chosen

    lo, hi = getattr(param, "min_value", None), getattr(param, "max_value", None)
    param_units = getattr(param, "units", None)
    unit_note = _units_note(param_units)
    range_note = f"; range [{lo}, {hi}]" if lo is not None and hi is not None else ""

    if unit is not None:
        raise ValueError(
            f"unit must be None for continuous parameter {name!r} (no discrete valid_values); "
            f"got {unit!r}{range_note}{unit_note}"
        )
    if lo is not None and hi is not None and not (lo <= value <= hi):
        raise ValueError(
            f"{value!r} is outside valid range [{lo}, {hi}] for parameter {name!r}{unit_note}"
        )
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


def _valid_values_kind(valid_values: list[Any]) -> str:
    if valid_values and all(isinstance(v, bool) for v in valid_values):
        return "boolean"
    if any(isinstance(v, str) for v in valid_values):
        return "labels"
    return "range"


def _describe_vst_param(plugin: Any, name: str, param: Any) -> dict[str, Any]:
    valid_values = list(getattr(param, "valid_values", None) or [])
    return {
        "name": name,
        "value": getattr(plugin, name, None),
        "units": str(getattr(param, "units", None) or ""),
        "min": getattr(param, "min_value", None),
        "max": getattr(param, "max_value", None),
        "valid_values": valid_values[:12],
        "valid_values_count": len(valid_values),
        "kind": _valid_values_kind(valid_values),
    }


def _describe_builtin(plugin: Any) -> list[dict[str, Any]]:
    rows = []
    for name, prop in inspect.getmembers(type(plugin), lambda member: isinstance(member, property)):
        if name.startswith("_") or prop.fset is None:
            continue
        value = getattr(plugin, name, None)
        if isinstance(value, bool):
            kind = "boolean"
        elif isinstance(value, (int, float)):
            kind = "range"
        elif isinstance(value, str):
            kind = "labels"
        else:
            continue  # not a bare float/int/bool/str attribute (e.g. an enum)
        rows.append(
            {
                "name": name,
                "value": value,
                "units": "",
                "min": None,
                "max": None,
                "valid_values": [],
                "valid_values_count": 0,
                "kind": kind,
            }
        )
    return rows


def describe(plugin: Any, contains: str | None = None) -> list[dict[str, Any]]:
    """List `plugin`'s parameters: name, current value, units, range, and valid values.

    One dict per parameter, sorted by name, with keys `name`, `value` (current value),
    `units` (`""` when the plugin doesn't report one), `min`, `max` (`None` when
    unknown), `valid_values` (up to 12 entries; see `valid_values_count` for the full
    count), and `kind` (`"labels"` for string-valued discrete parameters, `"boolean"`
    for two-valued True/False parameters, `"range"` otherwise). `contains` filters
    parameter names case-insensitively (substring match).

    VST3 plugins (anything with a `.parameters` dict) report this directly per
    parameter. Built-in Pedalboard plugins (e.g. `pedalboard.Reverb`) have no
    `.parameters`; for those, this inspects the class's settable float/int/bool/str
    properties and reports their current values, with `min`/`max`/`valid_values`
    left unknown (Pedalboard doesn't expose them for built-ins).

    Use this before guessing a parameter's scale: unit metadata isn't consistent across
    plugins (some report `%`, `ms`, or discrete labels; many report nothing), but name,
    current value, and range or valid values are always available, and are enough to
    tell a 0-100 percent knob from a 0-1 fraction.
    """
    params = getattr(plugin, "parameters", None)
    if params is not None:
        rows = [_describe_vst_param(plugin, name, param) for name, param in params.items()]
    else:
        rows = _describe_builtin(plugin)

    if contains:
        needle = contains.lower()
        rows = [row for row in rows if needle in row["name"].lower()]

    return sorted(rows, key=lambda row: row["name"])


_TABLE_COLUMNS = ("name", "value", "units", "min", "max", "kind", "valid_values")


def _table_cell(row: dict[str, Any], column: str) -> str:
    if column == "valid_values":
        shown = row.get("valid_values") or []
        count = row.get("valid_values_count", len(shown))
        text = ", ".join(str(v) for v in shown)
        if count > len(shown):
            text += f", ... (+{count - len(shown)} more)"
        return text
    value = row.get(column)
    return "" if value is None else str(value)


def format_table(rows: list[dict[str, Any]]) -> str:
    """Render `describe()`'s rows as a fixed-width text table, e.g. for `print`.

    Columns are name/value/units/min/max/kind/valid_values; `valid_values` shows the
    truncated sample with a "+N more" suffix when `valid_values_count` exceeds it.
    """
    widths = {column: len(column) for column in _TABLE_COLUMNS}
    cells = [{column: _table_cell(row, column) for column in _TABLE_COLUMNS} for row in rows]
    for row_cells in cells:
        for column in _TABLE_COLUMNS:
            widths[column] = max(widths[column], len(row_cells[column]))

    def format_line(row_cells: dict[str, str]) -> str:
        return "  ".join(row_cells[column].ljust(widths[column]) for column in _TABLE_COLUMNS)

    header = {column: column for column in _TABLE_COLUMNS}
    separator = {column: "-" * widths[column] for column in _TABLE_COLUMNS}
    lines = [format_line(header), format_line(separator)]
    lines.extend(format_line(row_cells) for row_cells in cells)
    return "\n".join(lines)


def _latencies(chain: Any) -> tuple[int, ...]:
    """Reported latency of external plugins, omitting native effects without it."""
    plugins = list(chain) if isinstance(chain, Iterable) else [chain]
    return tuple(
        int(plugin.reported_latency_samples or 0)
        for plugin in plugins
        if hasattr(plugin, "reported_latency_samples")
    )


def _settle_latency(chain, sample_rate, block_frames, source):
    """Negotiate external-plugin latency on silence before starting the stream."""
    previous = _latencies(chain)
    if previous:
        shape = (max(3, block_frames), *source.shape[1:])
        silence = np.zeros(shape, dtype=np.float32)
        # External plugins can publish their initial latency only after processing.
        # Require two processing calls at minimum, and never loop without a bound.
        for attempt in range(5):
            chain(silence, sample_rate, reset=True)
            current = _latencies(chain)
            if attempt >= 1 and current == previous:
                break
            previous = current
        else:
            raise ValueError("effect latency did not stabilize during initialization")
    chain.reset()
    return _latencies(chain)


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
    same layout and `tail_seconds` of silence appended. External-plugin latency is
    settled on silence first, then Pedalboard compensates a continuous stream and
    buffered output is flushed at the end. Requires a callable Pedalboard plugin or
    chain with reset(). Keep lookahead/oversampling and other latency-changing
    settings fixed during this call; changing reported latency raises ValueError.
    """
    raw = np.asarray(audio)
    _validate_process_args(sample_rate, block_seconds, tail_seconds, raw)

    source = raw.astype(np.float32, copy=False)
    tail_frames = round(tail_seconds * sample_rate)
    padded = _pad_frames(source, tail_frames)
    target_frames = len(padded)
    if not target_frames:
        return padded.copy()

    block_frames = max(1, round(block_seconds * sample_rate))
    bounds = _block_bounds(target_frames, block_frames)
    update(0.0)
    latencies = _settle_latency(chain, sample_rate, block_frames, source)

    chunks = []
    for i, (start, end) in enumerate(bounds):
        if i:
            update(start / sample_rate)
        # reset=True means a complete call to Pedalboard, including end flushing.
        # Reset explicitly once, then stream every block with reset=False.
        chunks.append(chain(padded[start:end], sample_rate, reset=False))
        if _latencies(chain) != latencies:
            raise ValueError("effect latency changed during automation; keep latency fixed")

    received = sum(len(chunk) for chunk in chunks)
    if received < target_frames:
        # Pedalboard already removes initial delay. Feed silence to retrieve the
        # buffered end; shifting again would discard the start of the actual audio.
        count = max(3, target_frames - received, sum(latencies))
        silence = np.zeros((count, *source.shape[1:]), dtype=np.float32)
        chunks.append(chain(silence, sample_rate, reset=False))
        if _latencies(chain) != latencies:
            raise ValueError("effect latency changed while flushing")
    output = np.concatenate(chunks, axis=0)
    if len(output) < target_frames:
        raise ValueError("effect chain did not return the requested audio after flushing")
    return output[:target_frames].astype(np.float32, copy=False)


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
    buffer_size: int = 64,
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
    back).

    `buffer_size` is the block Pedalboard renders in. VST3 carries pitch bend and CC as
    parameter changes that most plugins read once per block, so they take effect at the
    start of the block that contains them: at Pedalboard's default of 8192 frames a bend
    landed up to 170 ms early (note on/off are unaffected). The default of 64 keeps that
    error near 1 ms at little cost (an 8 s Dexed phrase: 0.24 s vs 0.21 s).

    Pedalboard returns instrument audio as `(channels, frames)`; this transposes
    to Tactus's `(frames, channels)` before returning, at exactly `round(duration *
    sample_rate)` frames (padded with silence or truncated if the plugin returns a
    different length).
    """
    _validate_render_instrument_args(duration, sample_rate, num_channels, warmup_seconds)
    if buffer_size < 1:
        raise ValueError(f"buffer_size must be >= 1, got {buffer_size!r}")

    if warmup_seconds > 0:
        plugin(
            [],
            duration=warmup_seconds,
            sample_rate=sample_rate,
            num_channels=num_channels,
            buffer_size=buffer_size,
        )

    raw = plugin(
        list(messages),
        duration=duration,
        sample_rate=sample_rate,
        num_channels=num_channels,
        buffer_size=buffer_size,
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
