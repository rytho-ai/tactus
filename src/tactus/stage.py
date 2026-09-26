"""`@stage`: opt-in reuse of an unchanged stage's result across parameter candidates.

Owns the reuse key end to end: a stage's qualified name and source file, the run-level
source/dependency/runtime identity `run.py` computes once before `render` and hands in
via `_begin_run`, and a canonical hash of the call's own arguments. One encoder
(`_canon`) builds a type-tagged, JSON-stable form of both the key's parts and a stored
result, so the same "what counts as the same value" rule governs a cache hit and a
cache write; anything it cannot tag (a random `Generator`, a plugin object, a callable,
an object-dtype array, a non-finite float, a non-string dict key) raises, and the call
falls back to running normally with that reason recorded. Outside a `--reuse` run
(`_context is None`), `@stage` is a plain call — no key, no I/O, no timing.

A hit replays the original call's recorded materials/tools (`inputs._replay`) after
re-verifying every recorded tool (`inputs._tool_matches`); a miss (or nested stage call)
records and stores its own capture frame (`inputs._begin_capture`/`_end_capture`), so a
reused outer stage's replayed frame already covers calls its never-re-executed inner
stages would have made. Storage is `$TACTUS_POOL/stages/<key>/`: `entry.json` (the
result's tagged structure, plus the captured materials/tools) beside `arr-<n>.npy` files
(`np.save`/`np.load(allow_pickle=False)`, never pickle), written to a temp directory and
renamed into place, following `inputs/tree.py`'s pattern.

Reads: tactus/inputs/__init__.py (_begin_capture/_end_capture/_replay/_tool_matches) ·
tactus/inputs/pool.py (default_pool_dir)
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import math
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from .inputs import _begin_capture, _end_capture, _replay, _tool_matches
from .inputs.pool import default_pool_dir


class _NotKeyable(Exception):
    """An argument, or a run-level key part, `_canon` cannot tag; message becomes `reason`."""


class _NotStorable(Exception):
    """A stage's return value `_canon` cannot tag; the call still runs, just uncached."""


def _canon(value: Any) -> Any:
    """A JSON-stable, type-tagged form of `value`; the same rule for hashing and storage.

    Every branch checks `type(value) is ...` exactly (never `isinstance`, except for the
    `Path`/`np.ndarray` cases, which have no meaningful subclasses here), so a NumPy scalar
    (a `float` subclass on most platforms) or a `bool`/`int` mismatch is never mistaken for
    the plain type. Anything unrecognised — a `Generator`, a plugin object, a callable, an
    object-dtype array — raises `_NotKeyable`/`_NotStorable` depending on the caller.
    """
    if value is None:
        return ["null"]
    kind = type(value)
    if kind is bool:
        return ["bool", value]
    if kind is int:
        return ["int", value]
    if kind is float:
        if not math.isfinite(value):
            raise _NotKeyable(f"non-finite float: {value!r}")
        return ["float", value]
    if kind is str:
        return ["str", value]
    if kind is bytes:
        return ["bytes", value.hex()]
    if isinstance(value, Path):
        return ["path", str(value)]
    if kind is list:
        return ["list", [_canon(item) for item in value]]
    if kind is tuple:
        return ["tuple", [_canon(item) for item in value]]
    if kind is dict:
        if not all(type(key) is str for key in value):
            raise _NotKeyable("dict keys must be str")
        return ["dict", sorted((key, _canon(item)) for key, item in value.items())]
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise _NotKeyable("ndarray dtype must not be object")
        contiguous = np.ascontiguousarray(value)
        return [
            "ndarray",
            contiguous.dtype.str,
            list(contiguous.shape),
            hashlib.sha256(contiguous.tobytes()).hexdigest(),
        ]
    raise _NotKeyable(f"unsupported type: {type(value).__name__}")


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class _RunParts:
    """The run-level key parts `run.py` computes once, before `render`."""

    __slots__ = (
        "_lock_identity",
        "_lock_identity_set",
        "calls",
        "dependency_lock",
        "python_version",
        "reuse",
        "source_files",
        "tactus_version",
    )

    def __init__(
        self,
        *,
        reuse: bool,
        source_files: dict[str, str],
        dependency_lock: dict[str, str] | None,
        python_version: str,
        tactus_version: str,
    ) -> None:
        self.reuse = reuse
        self.source_files = source_files
        self.dependency_lock = dependency_lock
        self.python_version = python_version
        self.tactus_version = tactus_version
        self._lock_identity: Any = None
        self._lock_identity_set = False
        self.calls: list[dict[str, Any]] = []

    def lock_identity(self) -> Any:
        """The lock's hash, or a sorted `(distribution, version)` fallback with no lock."""
        if not self._lock_identity_set:
            if self.dependency_lock is not None:
                self._lock_identity = self.dependency_lock["sha256"]
            else:
                from importlib.metadata import distributions

                self._lock_identity = sorted(
                    (str(dist.metadata["Name"]), str(dist.version))
                    for dist in distributions()
                    if dist.metadata.get("Name")
                )
            self._lock_identity_set = True
        return self._lock_identity


_context: _RunParts | None = None


def _begin_run(
    *,
    reuse: bool,
    source_files: dict[str, str],
    dependency_lock: dict[str, str] | None,
    python_version: str,
    tactus_version: str,
) -> None:
    """Set this run's key parts; called once by run.py before `render`, reuse or not."""
    global _context
    _context = _RunParts(
        reuse=reuse,
        source_files=source_files,
        dependency_lock=dependency_lock,
        python_version=python_version,
        tactus_version=tactus_version,
    )


def _end_run() -> list[dict[str, Any]]:
    """Return this run's `stages` receipt entries, in call order; clears the context."""
    global _context
    calls = _context.calls if _context is not None else []
    _context = None
    return calls


def _stage_dir(key: str) -> Path:
    return default_pool_dir() / "stages" / key


def _load_entry(directory: Path) -> dict[str, Any] | None:
    entry_path = directory / "entry.json"
    if not entry_path.is_file():
        return None
    try:
        return json.loads(entry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _decode(node: Any, directory: Path) -> Any:
    tag, *rest = node
    if tag == "null":
        return None
    if tag in ("bool", "int", "float", "str"):
        return rest[0]
    if tag == "bytes":
        return bytes.fromhex(rest[0])
    if tag == "path":
        return Path(rest[0])
    if tag == "list":
        return [_decode(item, directory) for item in rest[0]]
    if tag == "tuple":
        return tuple(_decode(item, directory) for item in rest[0])
    if tag == "dict":
        return {key: _decode(item, directory) for key, item in rest[0]}
    if tag == "array":
        return np.load(directory / f"arr-{rest[0]}.npy", allow_pickle=False)
    raise ValueError(f"unknown stored result tag: {tag!r}")


def _encode_for_storage(value: Any, arrays: list[np.ndarray]) -> Any:
    """Like `_canon`, but ndarrays are collected for `np.save` instead of hashed in place."""
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise _NotStorable("ndarray dtype must not be object")
        arrays.append(np.ascontiguousarray(value))
        return ["array", len(arrays) - 1]
    if value is None or type(value) in (bool, int, str, bytes) or isinstance(value, Path):
        try:
            return _canon(value)
        except _NotKeyable as exc:
            raise _NotStorable(str(exc)) from exc
    kind = type(value)
    if kind is float:
        if not math.isfinite(value):
            raise _NotStorable(f"non-finite float: {value!r}")
        return ["float", value]
    if kind is list:
        return ["list", [_encode_for_storage(item, arrays) for item in value]]
    if kind is tuple:
        return ["tuple", [_encode_for_storage(item, arrays) for item in value]]
    if kind is dict:
        if not all(type(key) is str for key in value):
            raise _NotStorable("dict keys must be str")
        return ["dict", [[key, _encode_for_storage(item, arrays)] for key, item in value.items()]]
    raise _NotStorable(f"unsupported type: {type(value).__name__}")


def _store(
    directory: Path, structure: Any, arrays: list[np.ndarray], record: dict[str, Any]
) -> None:
    """Write a stage hit's arrays and sidecar atomically; a same-key entry is left as-is."""
    if directory.is_dir():
        return
    directory.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f"{directory.name}.building-", dir=directory.parent))
    try:
        for index, array in enumerate(arrays):
            np.save(staging / f"arr-{index}.npy", array, allow_pickle=False)
        (staging / "entry.json").write_text(
            json.dumps({"result": structure, **record}, sort_keys=True), encoding="utf-8"
        )
        if not directory.is_dir():
            staging.rename(directory)
            staging = None
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def _stage_key(func: Callable[..., Any], arguments: dict[str, Any]) -> str:
    assert _context is not None
    payload = _canon(
        {
            "qualname": func.__qualname__,
            "file": func.__code__.co_filename,
            "python": _context.python_version,
            "tactus": _context.tactus_version,
            "source_files": _context.source_files,
            "dependency_lock": _context.lock_identity(),
            "arguments": arguments,
        }
    )
    return _digest(payload)


def stage[F: Callable[..., Any]](func: F) -> F:
    """Mark a module-level function as a reuse boundary; a plain call outside `--reuse`."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        context = _context
        if context is None or not context.reuse:
            return func(*args, **kwargs)

        name = func.__qualname__
        try:
            bound = inspect.signature(func).bind(*args, **kwargs)
        except TypeError:
            return func(*args, **kwargs)  # let the mismatch raise from the real call
        bound.apply_defaults()

        reason: str | None
        key: str | None
        try:
            key = _stage_key(func, dict(bound.arguments))
            reason = None
        except _NotKeyable as exc:
            key = None
            reason = str(exc)

        if key is not None:
            directory = _stage_dir(key)
            entry = _load_entry(directory)
            if entry is not None and all(_tool_matches(t) for t in entry.get("tools", ())):
                started = time.perf_counter()
                result = _decode(entry["result"], directory)
                _replay({"materials": entry.get("materials", ()), "tools": entry.get("tools", ())})
                context.calls.append(
                    {
                        "name": name,
                        "key": key,
                        "reused": True,
                        "seconds": round(time.perf_counter() - started, 3),
                        "reason": None,
                    }
                )
                return result

        frame = _begin_capture()
        started = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        finally:
            captured = _end_capture(frame)
        elapsed = round(time.perf_counter() - started, 3)

        if key is not None:
            try:
                arrays: list[np.ndarray] = []
                structure = _encode_for_storage(result, arrays)
                _store(_stage_dir(key), structure, arrays, captured)
            except _NotStorable as exc:
                reason = str(exc)

        context.calls.append(
            {"name": name, "key": key, "reused": False, "seconds": elapsed, "reason": reason}
        )
        return result

    return wrapper  # type: ignore[return-value]


__all__ = ["stage"]
