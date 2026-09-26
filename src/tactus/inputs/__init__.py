"""Resolve production inputs (pinned files, external executables) with a run-scoped record.

`material` takes a `"sha256:<hex>"` file reference or a `"tree:sha256:<hex>"` folder
reference (see `inputs.tree`) and returns a verified path into the shared pool
(`inputs.pool`); `tool` takes a name, a file path, or a folder path (a plugin bundle)
and returns a verified, resolved path, hashing whatever it finds — a single file's
bytes, or a folder's whole tree via `inputs.tree`. Both append to a process-local
record that `run.py` reads after render returns, so a receipt can attribute every
input a work actually resolved, in the order it resolved them, without either function
needing to know it is running inside a receipted run. Calling `material` or `tool`
outside a run (a REPL, a script, a test) works the same way; the record is simply never
read.

`_begin_capture`/`_end_capture` additionally let `stage.py` recover exactly what a
single call resolved, without knowing this module's dedupe encoding: a captured frame
mirrors every resolution into the run-wide record and into its own first-resolution-order
frame, so nested stage calls are captured by every enclosing frame too. `_replay` feeds a
stored stage hit's recorded entries back through the same dedupe path, and `_tool_matches`
re-hashes a recorded tool the way `tool()` did, for a stage's re-verification on lookup.
`stage.py` owns none of this encoding; it only calls these functions.

Reads: tactus/inputs/pool.py · tactus/inputs/tree.py
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from . import pool, tree

_REF_PREFIX = "sha256:"


class MaterialError(Exception):
    """A `material()` resolution failure: invalid reference, missing, or corrupt entry."""

    def __init__(self, reason: str, ref: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.ref = ref


class ToolError(Exception):
    """A `tool()` resolution failure: the named or pathed executable was not found."""

    def __init__(self, reason: str, name: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.name = name


# Process-local, resolution-ordered records. Keys dedupe repeat resolutions while a
# dict's insertion order preserves first-resolution order.
_materials: dict[str, dict[str, str]] = {}
_tools: dict[str, dict[str, str]] = {}

# Active `stage()` capture frames, outermost first. Each frame is its own
# (materials, tools) pair of dicts, populated alongside `_materials`/`_tools` so a
# frame records only what happened while it was open, in the same first-resolution
# order and with the same per-key dedupe. A frame open while a nested stage call opens
# another still receives that nested call's resolutions, which is what lets replaying a
# reused outer stage's frame also cover its (never re-executed) inner stage calls.
_capture_stack: list[tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]] = []


def _reset_record() -> None:
    """Clear the run-scoped record; called by run.py before each render."""
    _materials.clear()
    _tools.clear()
    _capture_stack.clear()


def _record_snapshot() -> dict[str, Any]:
    """Return the resolutions recorded so far, in first-resolution order."""
    return {"materials": list(_materials.values()), "tools": list(_tools.values())}


def _record_material(ref: str, entry: dict[str, str]) -> None:
    _materials[ref] = entry
    for frame_materials, _frame_tools in _capture_stack:
        frame_materials.setdefault(ref, entry)


def _record_tool(name: str, entry: dict[str, str]) -> None:
    _tools[name] = entry
    for _frame_materials, frame_tools in _capture_stack:
        frame_tools.setdefault(name, entry)


def _begin_capture() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Open a capture frame for one `stage()` call; must be closed with `_end_capture`."""
    frame = ({}, {})
    _capture_stack.append(frame)
    return frame


def _end_capture(
    frame: tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]],
) -> dict[str, Any]:
    """Close `frame` (must be the innermost open frame) and return what it captured."""
    assert _capture_stack and _capture_stack[-1] is frame, "capture frames must nest"
    _capture_stack.pop()
    frame_materials, frame_tools = frame
    return {"materials": list(frame_materials.values()), "tools": list(frame_tools.values())}


def _replay(record: dict[str, Any]) -> None:
    """Feed a stored stage hit's recorded materials/tools back through the normal record."""
    for entry in record.get("materials", ()):
        _record_material(entry["ref"], entry)
    for entry in record.get("tools", ()):
        _record_tool(entry["name"], entry)


def _tool_matches(entry: dict[str, str]) -> bool:
    """Whether a recorded tool entry still hashes the same, re-verified the way `tool()` did."""
    path = Path(entry["path"])
    try:
        if entry.get("kind") == "tree":
            if not path.is_dir():
                return False
            digest, _entries = tree.digest_of_tree(path)
        else:
            if not path.is_file():
                return False
            digest = pool.hash_file(path)
    except (OSError, ValueError):
        return False
    return digest == entry["sha256"]


def _digest_from_ref(ref: str) -> str:
    if not isinstance(ref, str) or not ref.startswith(_REF_PREFIX):
        raise MaterialError(
            "invalid_ref", ref, f"material ref must be 'sha256:<64 lowercase hex>': {ref!r}"
        )
    digest = ref[len(_REF_PREFIX) :]
    if not pool.DIGEST_RE.match(digest):
        raise MaterialError(
            "invalid_ref", ref, f"material ref must be 'sha256:<64 lowercase hex>': {ref!r}"
        )
    return digest


def material(ref: str) -> Path:
    """Resolve a `"sha256:<hex>"` file ref or a `"tree:sha256:<hex>"` folder ref.

    Returns a verified path in the shared pool — a file for the former, a materialized
    folder for the latter.
    """
    if isinstance(ref, str) and ref.startswith(tree.PREFIX):
        return _material_tree(ref)
    return _material_file(ref)


def _material_file(ref: str) -> Path:
    digest = _digest_from_ref(ref)
    try:
        path = pool.path_for(digest)
    except ValueError as exc:
        raise MaterialError("corrupt", ref, str(exc)) from exc
    if path is None:
        raise MaterialError(
            "missing",
            ref,
            f"material {ref} is not in the pool ({pool.default_pool_dir()}); "
            f"import it first with: tactus material add <file>",
        )
    _record_material(ref, {"ref": ref})
    return path


def _material_tree(ref: str) -> Path:
    try:
        digest = tree.digest_from_ref(ref)
    except ValueError as exc:
        raise MaterialError("invalid_ref", ref, str(exc)) from exc
    try:
        path = tree.resolve(digest)
    except tree.TreeError as exc:
        raise MaterialError(exc.reason, ref, str(exc)) from exc
    _record_material(ref, {"ref": ref})
    return path


def tool(name_or_path: str) -> Path:
    """Resolve an executable by name (via PATH), a file path, or a folder (bundle) path.

    Hashes whatever it finds: a single file's bytes, or a folder's whole tree via
    `inputs.tree`. Records `kind: "file"` or `kind: "tree"` accordingly, and returns the
    resolved path unchanged — a folder tool returns the folder, so
    `pedalboard.load_plugin(tool(".../Name.vst3"))` is one step.
    """
    if not isinstance(name_or_path, str) or not name_or_path:
        raise ToolError("missing", str(name_or_path), "tool name or path must be a nonempty string")
    is_path = os.sep in name_or_path or (os.altsep is not None and os.altsep in name_or_path)
    if is_path:
        candidate = Path(name_or_path)
        if candidate.is_dir() and not candidate.is_symlink():
            resolved = candidate.resolve()
            try:
                digest, _entries = tree.digest_of_tree(resolved)
            except ValueError as exc:
                raise ToolError("missing", name_or_path, str(exc)) from exc
            _record_tool(
                name_or_path,
                {"name": name_or_path, "path": str(resolved), "sha256": digest, "kind": "tree"},
            )
            return resolved
        if not candidate.is_file():
            raise ToolError("missing", name_or_path, f"tool not found: {name_or_path}")
        resolved = candidate.resolve()
    else:
        found = shutil.which(name_or_path)
        if found is None:
            raise ToolError("missing", name_or_path, f"tool not found on PATH: {name_or_path}")
        resolved = Path(found).resolve()
        if not resolved.is_file():
            raise ToolError("missing", name_or_path, f"tool not found: {name_or_path}")
    digest = pool.hash_file(resolved)
    _record_tool(
        name_or_path,
        {"name": name_or_path, "path": str(resolved), "sha256": digest, "kind": "file"},
    )
    return resolved


__all__ = ["MaterialError", "ToolError", "material", "tool"]
