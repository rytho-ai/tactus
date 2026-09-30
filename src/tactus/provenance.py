"""Bounded attribution shared by analysis and export executions.

Records local Python/config/lock and callable identity before execution, verifies those
identities afterwards, then records actual imported distributions and declared inputs.
It does not sandbox Python or trace undeclared I/O/network/randomness.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from . import _source
from .commands import Command, CommandIdentity, identity
from .inputs import _record_snapshot, _reset_record
from .inputs.pool import hash_file


class AttributionStart(TypedDict):
    callable: CommandIdentity
    project: str | None
    inventory: _source.SourceInventory | None
    pyproject_sha256: str | None


class Attribution(AttributionStart):
    environment: dict[str, Any]
    python_packages: dict[str, str]
    package_sources: dict[str, dict[str, Any]]
    inputs: dict[str, Any]


def _snapshot(command: Command, out: Path | None) -> AttributionStart:
    root = command.project.root if command.project else None
    return {
        "callable": identity(command),
        "project": str(root) if root else None,
        "inventory": _source.inventory(root, out) if root else None,
        "pyproject_sha256": hash_file(root / "pyproject.toml") if root else None,
    }


def begin(command: Command, out: Path | None) -> AttributionStart:
    _reset_record()
    return _snapshot(command, out)


def finish(command: Command, out: Path | None, before: AttributionStart) -> Attribution:
    if _snapshot(command, out) != before:
        raise ValueError("analysis/export source or project configuration changed during execution")
    packages = _source.python_packages()
    return {
        **before,
        "environment": _source.environment(),
        "python_packages": packages,
        "package_sources": _source.package_sources(sorted({*packages, "tactus"})),
        "inputs": _record_snapshot(),
    }
