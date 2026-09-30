"""Source and environment identities shared by rendering, commands and work creation.

Owns Python-file/lock inventories, imported distribution versions and PEP 610 origins.
Reads Git metadata through revision; does not import the runner or execute user code.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from importlib.metadata import PackageNotFoundError, distribution, packages_distributions, version
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlparse
from urllib.request import url2pathname

from . import revision


class FileIdentity(TypedDict):
    path: str
    sha256: str


class SourceInventory(TypedDict):
    source_files: dict[str, str]
    dependency_lock: FileIdentity | None


def _find_lock(start: Path) -> Path | None:
    """Walk upward from `start` for the nearest `uv.lock`, stopping at the filesystem root."""
    current = start
    while True:
        candidate = current / "uv.lock"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def inventory(root: Path, output: Path | None) -> SourceInventory:
    excluded = {".tactus", ".tactus-code", ".venv", "__pycache__", ".git"}
    files = {}
    for directory, children, names in os.walk(root):
        children[:] = [
            name
            for name in children
            if name not in excluded and (Path(directory) / name).resolve() != output
        ]
        for name in sorted(names):
            if name.endswith(".py"):
                path = Path(directory) / name
                files[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    lock = _find_lock(root)
    return {
        "source_files": files,
        "dependency_lock": {
            "path": str(lock),
            "sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        }
        if lock is not None
        else None,
    }


def python_packages() -> dict[str, str]:
    """Map imported top-level modules to installed distribution versions, minus stdlib."""
    mapping = packages_distributions()
    stdlib = sys.stdlib_module_names
    result: dict[str, str] = {}
    for name in list(sys.modules):
        top = name.split(".", 1)[0]
        if top in stdlib:
            continue
        for dist_name in mapping.get(top, ()):
            if dist_name in result:
                continue
            try:
                result[dist_name] = version(dist_name)
            except PackageNotFoundError:  # pragma: no cover - defensive; metadata inconsistent
                pass
    return dict(sorted(result.items()))


def environment() -> dict[str, Any]:
    """The running interpreter's prefix and, when it owns a project, that project's lock."""
    prefix = Path(sys.prefix)
    candidate = prefix.parent / "uv.lock"
    lock = (
        {"path": str(candidate), "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest()}
        if candidate.is_file()
        else None
    )
    return {"prefix": str(prefix), "lock": lock}


def direct_url(name: str) -> dict[str, Any] | None:
    """Parsed PEP 610 `direct_url.json` for an installed distribution, or None without one.

    Shared by `package_sources` (receipt attribution) and `init.py` (resolving the
    running Tactus's own origin to pin a new work) so the parsing lives in one place.
    """
    try:
        raw = distribution(name).read_text("direct_url.json")
    except PackageNotFoundError:  # pragma: no cover - defensive; metadata inconsistent
        return None
    if raw is None:
        return None
    return json.loads(raw)


def package_sources(names: list[str]) -> dict[str, Any]:
    """PEP 610 origin of each named distribution not installed from an index.

    Reads each distribution's `direct_url.json`; a distribution with none (an index
    install) is omitted, since the lock already pins it.
    """
    result: dict[str, Any] = {}
    for name in names:
        data = direct_url(name)
        if data is None:
            continue
        url = data.get("url", "")
        vcs_info = data.get("vcs_info")
        dir_info = data.get("dir_info")
        archive_info = data.get("archive_info")
        if vcs_info:
            result[name] = {
                "url": url,
                "vcs": vcs_info.get("vcs"),
                "commit": vcs_info.get("commit_id"),
            }
        elif dir_info:
            entry: dict[str, Any] = {"url": url, "editable": bool(dir_info.get("editable", False))}
            parsed = urlparse(url)
            if parsed.scheme == "file":
                git = revision.describe(Path(url2pathname(parsed.path)))
                if git is not None:
                    entry["git"] = git
            result[name] = entry
        elif archive_info and archive_info.get("hash"):
            result[name] = {"url": url, "hash": archive_info["hash"]}
    return dict(sorted(result.items()))
