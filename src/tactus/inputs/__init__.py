"""Resolve production inputs (pinned files, external executables) with a run-scoped record.

`material` takes a `"sha256:<hex>"` reference and returns a verified path into the shared
pool (`inputs.pool`); `tool` takes a name or path and returns a verified, resolved
executable path, hashing whatever it finds. Both append to a process-local record that
`run.py` reads after render returns, so a receipt can attribute every input a work
actually resolved, in the order it resolved them, without either function needing to
know it is running inside a receipted run. Calling `material` or `tool` outside a run
(a REPL, a script, a test) works the same way; the record is simply never read.

Reads: tactus/inputs/pool.py
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from . import pool

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


def _reset_record() -> None:
    """Clear the run-scoped record; called by run.py before each render."""
    _materials.clear()
    _tools.clear()


def _record_snapshot() -> dict[str, Any]:
    """Return the resolutions recorded so far, in first-resolution order."""
    return {"materials": list(_materials.values()), "tools": list(_tools.values())}


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
    """Resolve a `"sha256:<hex>"` reference to a verified path in the shared pool."""
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
    _materials[ref] = {"ref": ref}
    return path


def tool(name_or_path: str) -> Path:
    """Resolve an executable by name (via PATH) or path, hashing the resolved file."""
    if not isinstance(name_or_path, str) or not name_or_path:
        raise ToolError("missing", str(name_or_path), "tool name or path must be a nonempty string")
    is_path = os.sep in name_or_path or (os.altsep is not None and os.altsep in name_or_path)
    if is_path:
        candidate = Path(name_or_path)
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
    _tools[name_or_path] = {"name": name_or_path, "path": str(resolved), "sha256": digest}
    return resolved


__all__ = ["MaterialError", "ToolError", "material", "tool"]
