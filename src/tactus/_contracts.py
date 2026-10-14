"""Shared execution boundaries: errors, finite JSON and publishable audio mappings.

Runner, storage, analysis and export use the same validation and atomic JSON writer.
This module does not execute works or discover their source/environment.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .store import validate_name


class RunError(Exception):
    """A failed run with a stable code and the phase in which it failed."""

    def __init__(self, code: str, phase: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.phase = phase

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "error",
            "error": {
                "code": self.code,
                "phase": self.phase,
                "message": str(self),
            },
        }

    @property
    def exit_code(self) -> int:
        if self.code == "cancelled":
            return 130
        return 2 if self.phase in {"request", "load", "bind"} else 1


def json_copy(value: Any) -> Any:
    """Validate JSON values without silently coercing tuples or nonstring keys."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [json_copy(item) for item in value]
    if type(value) is dict and all(isinstance(key, str) for key in value):
        return {key: json_copy(item) for key, item in value.items()}
    raise ValueError("parameters must contain finite JSON values and string object keys")


class InvalidParameters(ValueError):
    """Raised by a work's `render` when its parameters are invalid (e.g. a malformed
    performance), before the expensive part; `run` reports it as `invalid_parameters`."""


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate parameter key: {key}")
        result[key] = value
    return result


def strict_json(raw: str | bytes) -> Any:
    """Finite JSON with unique object keys (the parameter boundary), or ValueError."""
    return json_copy(json.loads(raw, object_pairs_hook=_pairs))


def parse_params(raw: str) -> dict[str, Any]:
    """Parse CLI overrides, rejecting duplicate keys and nonstandard JSON numbers."""
    try:
        params = strict_json(raw)
        if not isinstance(params, dict):
            raise TypeError("--params must be a JSON object")
        return params
    except (ValueError, TypeError, RecursionError) as exc:
        raise RunError("invalid_request", "request", str(exc)) from exc


def write_json(path: Path, value: dict[str, Any], *, compact: bool = False) -> None:
    """Write JSON atomically; `compact` drops indentation and spaces (files a page downloads)."""
    temporary = path.with_suffix(".json.tmp")
    layout = {"separators": (",", ":")} if compact else {"indent": 2}
    temporary.write_text(
        json.dumps(value, sort_keys=True, allow_nan=False, **layout) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def validate_audio_mapping(outputs: Any) -> None:
    if not isinstance(outputs, dict) or not outputs:
        raise ValueError("audio mapping must be a nonempty dictionary")
    for name, audio in outputs.items():
        if not isinstance(name, str) or not name:
            raise ValueError("output labels must be nonempty strings")
        validate_name(name)
        if not isinstance(audio, np.ndarray) or audio.dtype.kind not in "iuf":
            raise ValueError(f"output {name!r} must be a real numeric NumPy array")
        if (
            audio.ndim not in (1, 2)
            or not len(audio)
            or (audio.ndim == 2 and audio.shape[1] not in (1, 2))
        ):
            raise ValueError(f"output {name!r} must contain nonempty mono or stereo frames")
        if not np.isfinite(audio).all():
            raise ValueError(f"output {name!r} contains NaN or infinity")
