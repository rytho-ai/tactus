"""A render's time map: bar lines, lanes and segments of named outputs, as integer frames.

`render` may return `"map"` beside its audio. The map is data the work's own code derives
(never a second authored file): per output an optional `grid` (bar-start frames, 1-based bar
numbers as in `tactus.timing.Clock`) and `lanes` (author-named spans or points), and
`segments` (regions a player can loop, enter or leave, with their exit points). Tactus checks
structure and references only; it gives no lane name a meaning and does not judge whether a
join sounds right. `run` applies `validate` and saves the result as `map.json`.

    from tactus import timemap
    checked = timemap.validate(time_map, {"mix": audio})   # the same check `run` applies
    timemap.to_seconds(checked, 48000)                     # every position as seconds
    timemap.from_seconds(map_in_seconds, 48000)            # the inverse, for timing given in seconds

Shape (every key optional unless noted; positions are frames of that output):

    {"outputs": {NAME: {"grid": {"bars": [...], "first_bar": 1, "end": F,
                                 "beats_per_bar": 4 | [...], "beats": [...]},
                        "lanes": {LANE: {"kind": "spans" | "points",
                                         "items": [{"start": F, "end": F, ...} | {"at": F, ...}]}}}},
     "segments": {NAME: {"output": NAME (required), "start": F, "end": F (required),
                         "tail_end": F, "loop": false, "tags": [...], "label": str,
                         "joins": [{"at": "bars" | [relative frames], "to": null | [names] |
                                    {"tags": [...]}, "keep_phase": false, "label": str}]}},
     "clock_hint": any JSON (informational, never re-resolved)}

Reads: numpy · store · timing (frame_of)
"""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from .store import NAME_PATTERN
from .timing import frame_of

__all__ = ["from_seconds", "to_seconds", "validate"]

_TOP = {"outputs", "segments", "clock_hint"}
_OUTPUT = {"grid", "lanes"}
_GRID = {"first_bar", "bars", "end", "beats_per_bar", "beats"}
_LANE = {"kind", "items"}
_SEGMENT = {"output", "start", "end", "tail_end", "loop", "tags", "joins", "label"}
_JOIN = {"at", "to", "keep_phase", "label"}


def _fail(path: str, message: str) -> None:
    raise ValueError(f"map.{path}: {message}" if path else f"map: {message}")


def _plain(value: Any, path: str) -> Any:
    """JSON values with field paths in errors; NumPy scalars become Python numbers."""
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _fail(path, "numbers must be finite")
        return value
    if type(value) is list:
        return [_plain(item, f"{path}[{i}]") for i, item in enumerate(value)]
    if type(value) is dict:
        for key in value:
            if not isinstance(key, str):
                _fail(path, f"object keys must be strings, got {key!r}")
        return {key: _plain(item, f"{path}.{key}" if path else key) for key, item in value.items()}
    _fail(path, f"must be JSON (list, dict, str, finite number, bool or null), got "
          f"{type(value).__name__}")


def _keys(value: Any, path: str, allowed: set[str], required: set[str] = frozenset()) -> dict:
    if not isinstance(value, dict):
        _fail(path, f"must be an object, got {type(value).__name__}")
    missing = required - value.keys()
    unexpected = value.keys() - allowed
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing fields: {', '.join(sorted(missing))}")
        if unexpected:
            details.append(f"unexpected fields: {', '.join(sorted(map(repr, unexpected)))}")
        _fail(path, f"{'; '.join(details)} (allowed: {', '.join(sorted(allowed))})")
    return value


def _frame(value: Any, path: str, low: int, high: int | None) -> int:
    if type(value) is not int:
        _fail(path, f"must be an integer frame, got {value!r}")
    if value < low or (high is not None and value > high):
        bound = "" if high is None else f", {high}"
        _fail(path, f"frame {value} lies outside [{low}{bound}]")
    return value


def _frames(value: Any, path: str, high: int, *, nonempty: bool) -> list[int]:
    if not isinstance(value, list) or (nonempty and not value):
        _fail(path, "must be a nonempty list of integer frames" if nonempty else "must be a list")
    previous = None
    for i, item in enumerate(value):
        _frame(item, f"{path}[{i}]", 0, high)
        if previous is not None and item < previous:
            _fail(f"{path}[{i}]", f"frames must not decrease ({item} after {previous})")
        previous = item
    return value


def _name(value: Any, path: str) -> str:
    if not isinstance(value, str) or not NAME_PATTERN.match(value):
        _fail(path, f"name {value!r} must match [A-Za-z0-9][A-Za-z0-9._-]*")
    return value


def _grid(grid: Any, path: str, length: int) -> dict:
    _keys(grid, path, _GRID, {"bars"})
    first = grid.get("first_bar", 1)
    if type(first) is not int:
        _fail(f"{path}.first_bar", f"must be an integer bar number, got {first!r}")
    bars = _frames(grid["bars"], f"{path}.bars", length, nonempty=True)
    result = {"first_bar": first, "bars": bars}
    if "end" in grid:
        # A master usually stops before its last bar line ends: end may exceed the output.
        result["end"] = _frame(grid["end"], f"{path}.end", bars[-1], None)
    if "beats_per_bar" in grid:
        meter = grid["beats_per_bar"]
        values = meter if isinstance(meter, list) else [meter]
        if isinstance(meter, list) and len(meter) != len(bars):
            _fail(f"{path}.beats_per_bar", f"has {len(meter)} entries for {len(bars)} bars")
        for i, beats in enumerate(values):
            if type(beats) not in (int, float) or beats <= 0:
                where = f"{path}.beats_per_bar" + (f"[{i}]" if isinstance(meter, list) else "")
                _fail(where, f"must be a positive number of quarter beats, got {beats!r}")
        result["beats_per_bar"] = meter
    if "beats" in grid:
        result["beats"] = _frames(grid["beats"], f"{path}.beats", length, nonempty=False)
    return result


def _lane(lane: Any, path: str, length: int) -> dict:
    _keys(lane, path, _LANE, {"kind", "items"})
    kind, items = lane["kind"], lane["items"]
    if kind not in ("spans", "points"):
        _fail(f"{path}.kind", f"must be 'spans' or 'points', got {kind!r}")
    if not isinstance(items, list):
        _fail(f"{path}.items", "must be a list of objects")
    previous = None
    for i, item in enumerate(items):
        where = f"{path}.items[{i}]"
        if not isinstance(item, dict):
            _fail(where, "must be an object")
        if kind == "spans":
            for field in ("start", "end"):
                if field not in item:
                    _fail(where, f"a span needs start and end (missing {field})")
            start = _frame(item["start"], f"{where}.start", 0, length)
            _frame(item["end"], f"{where}.end", start, length)
            position = start
        else:
            if "at" not in item:
                _fail(where, "a point needs at")
            position = _frame(item["at"], f"{where}.at", 0, length)
        if previous is not None and position < previous:
            _fail(where, f"items must be sorted by position ({position} after {previous})")
        previous = position
    return {"kind": kind, "items": items}


def _segment(segment: Any, path: str, lengths: dict[str, int]) -> dict:
    _keys(segment, path, _SEGMENT, {"output", "start", "end"})
    output = segment["output"]
    if output not in lengths:
        _fail(f"{path}.output", f"names no returned output: {output!r}")
    length = lengths[output]
    start = _frame(segment["start"], f"{path}.start", 0, length)
    end = _frame(segment["end"], f"{path}.end", start, length)
    tail_end = _frame(segment.get("tail_end", end), f"{path}.tail_end", end, length)
    loop = segment.get("loop", False)
    if type(loop) is not bool:
        _fail(f"{path}.loop", f"must be true or false, got {loop!r}")
    tags = segment.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(tag, str) or not tag for tag in tags):
        _fail(f"{path}.tags", "must be a list of nonempty strings")
    joins = segment.get("joins", [])
    if not isinstance(joins, list):
        _fail(f"{path}.joins", "must be a list")
    checked = []
    for i, join in enumerate(joins):
        where = f"{path}.joins[{i}]"
        _keys(join, where, _JOIN, {"at"})
        at = join["at"]
        if at != "bars":
            if not isinstance(at, list):
                _fail(f"{where}.at", "must be 'bars' or a list of frames relative to start")
            _frames(at, f"{where}.at", end - start, nonempty=True)
        keep_phase = join.get("keep_phase", False)
        if type(keep_phase) is not bool:
            _fail(f"{where}.keep_phase", f"must be true or false, got {keep_phase!r}")
        if "label" in join and not isinstance(join["label"], str):
            _fail(f"{where}.label", "must be a string")
        checked.append({**join, "at": at, "to": join.get("to"), "keep_phase": keep_phase})
    result = {
        **segment,
        "output": output,
        "start": start,
        "end": end,
        "tail_end": tail_end,
        "loop": loop,
        "tags": tags,
        "joins": checked,
    }
    if "label" in segment and not isinstance(segment["label"], str):
        _fail(f"{path}.label", "must be a string")
    return result


def validate(time_map: Any, outputs: dict[str, Any]) -> dict[str, Any]:
    """Check a map against the outputs it describes and return its canonical copy.

    `outputs` maps names to audio arrays or frame counts. Checks: referenced outputs exist;
    positions are integer frames within `[0, len(output)]` (`grid.end` may exceed it);
    bar, beat and lane positions do not decrease; `beats_per_bar` is a positive number or
    one per bar; `start <= end <= tail_end` for segments; join points lie in the body;
    `"bars"` joins need that output's grid; named join targets and tags exist. Unknown keys
    are rejected with their field path. Defaults are filled (`first_bar` 1, `tail_end` =
    `end`, `loop` false, `tags`/`joins` empty, `to` null, `keep_phase` false); everything
    else is kept as given. Raises ValueError naming the field, e.g.
    `map.outputs.tape.grid.bars[3]: frames must not decrease (100 after 200)`.
    """
    lengths = {
        name: (value if type(value) is int else len(value)) for name, value in outputs.items()
    }
    time_map = _plain(time_map, "")
    _keys(time_map, "", _TOP)
    result: dict[str, Any] = {}
    described = time_map.get("outputs", {})
    if not isinstance(described, dict):
        _fail("outputs", "must be an object of output names")
    checked_outputs = {}
    for name, entry in described.items():
        path = f"outputs.{name}"
        if name not in lengths:
            _fail(path, f"names no returned output (returned: {', '.join(sorted(lengths))})")
        _keys(entry, path, _OUTPUT)
        checked: dict[str, Any] = {}
        if "grid" in entry:
            checked["grid"] = _grid(entry["grid"], f"{path}.grid", lengths[name])
        if "lanes" in entry:
            lanes = entry["lanes"]
            if not isinstance(lanes, dict):
                _fail(f"{path}.lanes", "must be an object of lane names")
            checked["lanes"] = {
                _name(lane, f"{path}.lanes.{lane}"): _lane(value, f"{path}.lanes.{lane}",
                                                          lengths[name])
                for lane, value in lanes.items()
            }
        checked_outputs[name] = checked
    if "outputs" in time_map:
        result["outputs"] = checked_outputs
    segments = time_map.get("segments", {})
    if not isinstance(segments, dict):
        _fail("segments", "must be an object of segment names")
    checked_segments = {
        _name(name, f"segments.{name}"): _segment(value, f"segments.{name}", lengths)
        for name, value in segments.items()
    }
    tags = {tag for segment in checked_segments.values() for tag in segment["tags"]}
    for name, segment in checked_segments.items():
        for i, join in enumerate(segment["joins"]):
            where = f"segments.{name}.joins[{i}]"
            if join["at"] == "bars" and "grid" not in checked_outputs.get(segment["output"], {}):
                _fail(f"{where}.at", f"'bars' needs a grid for output {segment['output']!r}")
            target = join["to"]
            if target is None:
                continue
            if isinstance(target, list):
                for j, other in enumerate(target):
                    if other not in checked_segments:
                        _fail(f"{where}.to[{j}]", f"names no segment: {other!r}")
            elif isinstance(target, dict):
                _keys(target, f"{where}.to", {"tags"}, {"tags"})
                if not isinstance(target["tags"], list) or not target["tags"]:
                    _fail(f"{where}.to.tags", "must be a nonempty list of tags")
                for j, tag in enumerate(target["tags"]):
                    if tag not in tags:
                        _fail(f"{where}.to.tags[{j}]", f"no segment carries tag {tag!r}")
            else:
                _fail(f"{where}.to", "must be null, a list of segment names or {\"tags\": [...]}")
    if "segments" in time_map:
        result["segments"] = checked_segments
    if "clock_hint" in time_map:
        result["clock_hint"] = time_map["clock_hint"]
    return result


def _positions(time_map: dict[str, Any], convert) -> dict[str, Any]:
    """A deep copy of the map with every position field passed through `convert`.

    The one list of position fields shared by `to_seconds` and `from_seconds`: grid
    `bars`/`end`/`beats`, lane item `start`/`end`/`at`, segment `start`/`end`/`tail_end` and
    list-valued join `at`. Every other field is copied unchanged.
    """
    result = json.loads(json.dumps(time_map))
    for entry in result.get("outputs", {}).values():
        grid = entry.get("grid")
        if grid:
            grid["bars"] = [convert(f) for f in grid["bars"]]
            if "end" in grid:
                grid["end"] = convert(grid["end"])
            if "beats" in grid:
                grid["beats"] = [convert(f) for f in grid["beats"]]
        for lane in entry.get("lanes", {}).values():
            for item in lane["items"]:
                for key in ("start", "end", "at"):
                    if key in item:
                        item[key] = convert(item[key])
    for segment in result.get("segments", {}).values():
        for key in ("start", "end", "tail_end"):
            if key in segment:
                segment[key] = convert(segment[key])
        for join in segment.get("joins", []):
            if isinstance(join.get("at"), list):
                join["at"] = [convert(f) for f in join["at"]]
    return result


def to_seconds(time_map: dict[str, Any], sample_rate: int) -> dict[str, Any]:
    """The same map with every position field divided by `sample_rate` (floats, seconds).

    Converted: grid `bars`/`end`/`beats`, lane item `start`/`end`/`at`, segment
    `start`/`end`/`tail_end` and list-valued join `at` (still relative to the segment
    start). Every other field is copied unchanged.
    """
    return _positions(time_map, lambda frame: frame / sample_rate)


def from_seconds(time_map: dict[str, Any], sample_rate: int) -> dict[str, Any]:
    """The inverse of `to_seconds`: a map written in seconds, with every position as frames.

    For timing that arrives in seconds (subtitles, labels, onsets, cues). The same fields
    `to_seconds` converts become `timing.frame_of(seconds, sample_rate)`, Tactus's one
    rounding rule; every other field (`text`, `status`, `label`, `clock_hint`, ...) is copied
    unchanged. It does not sort, clamp or validate: `run` validates what `render` returns,
    and a work's tests call `validate`, so an out-of-order or out-of-range input is reported
    with its field path instead of being hidden.

        lines = [{"start": 14.74, "end": 16.9, "text": "...", "status": "draft"}]
        timemap.from_seconds({"outputs": {"mix": {"lanes": {"lyrics":
            {"kind": "spans", "items": lines}}}}}, 44100)
    """
    return _positions(time_map, lambda seconds: frame_of(seconds, sample_rate))
