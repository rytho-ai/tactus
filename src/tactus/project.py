"""Discover one work's pyproject and its explicit Tactus command registrations.

The nearest pyproject is a boundary, including an unrelated Python project. Launcher
and command registry share this lookup; paths supplied by users keep their cwd meaning.
A work without its own uv.lock may be locked by an enclosing uv workspace that lists it.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Project:
    root: Path
    data: dict

    @property
    def settings(self) -> dict:
        settings = self.data.get("tool", {}).get("tactus", {})
        if not isinstance(settings, dict):
            raise TypeError("[tool.tactus] must be a table")
        return settings

    @property
    def is_work(self) -> bool:
        project = self.data.get("project", {})
        dependencies = project.get("dependencies", [])
        return (
            project.get("name") == "tactus"
            or bool(self.settings)
            or any(
                re.split(r"[\s\[<>=!~;@]", dep, maxsplit=1)[0].lower() == "tactus"
                for dep in dependencies
            )
        )


def discover(start: Path | None = None) -> Project | None:
    current = (start or Path.cwd()).resolve()
    for root in (current, *current.parents):
        file = root / "pyproject.toml"
        if file.is_file():
            with file.open("rb") as stream:
                project = Project(root, tomllib.load(stream))
            return project if project.is_work else None
    return None


def environment_root(root: Path) -> Path:
    """The uv project whose `uv.lock` and default `.venv` serve the work at `root`.

    That is the work itself when it holds a `uv.lock`; otherwise the nearest enclosing
    uv workspace (`[tool.uv.workspace]`) that lists it as a member, as uv resolves it;
    otherwise the work itself. Membership follows uv's `members`/`exclude` globs.
    """
    root = root.resolve()
    if (root / "uv.lock").is_file():
        return root
    for parent in root.parents:
        file = parent / "pyproject.toml"
        if not file.is_file():
            continue
        with file.open("rb") as stream:
            workspace = tomllib.load(stream).get("tool", {}).get("uv", {}).get("workspace")
        if not isinstance(workspace, dict):
            continue
        member = _listed(parent, workspace.get("members", []), root)
        excluded = _listed(parent, workspace.get("exclude", []), root)
        return parent if member and not excluded else root
    return root


def _listed(base: Path, patterns: object, root: Path) -> bool:
    """Whether a workspace glob list (relative to `base`) names the directory `root`."""
    if not isinstance(patterns, list):
        return False
    return any(
        path.resolve() == root
        for pattern in patterns
        if isinstance(pattern, str)
        for path in base.glob(pattern)
    )


def selected_project(explicit: Path | None = None, *, recognize_uv: bool = True) -> Project | None:
    """Explicit selection, delegated work, uv's current .venv owner, then cwd.

    uv --project changes the environment without changing cwd. Only recognize a
    running uv context with matching interpreter/activation, not activation alone.
    Custom or shared environments require explicit selection.
    """
    if explicit is not None:
        return discover(explicit)
    delegated = os.environ.get("TACTUS_PROJECT_ROOT")
    if delegated:
        root = Path(delegated)
        if not root.is_dir():
            raise ValueError(f"selected work directory does not exist: {root}")
        project = discover(root)
        if project is None:
            raise ValueError(f"no Tactus work found at selected directory: {root}")
        return project
    depth = os.environ.get("UV_RUN_RECURSION_DEPTH", "")
    active = os.environ.get("VIRTUAL_ENV")
    prefix = Path(sys.prefix)
    if (
        recognize_uv
        and depth.isdigit()
        and int(depth) > 0
        and active
        and Path(active).resolve() == prefix.resolve()
        and prefix.name == ".venv"
        and sys.prefix != sys.base_prefix
    ):
        project = discover(prefix.parent)
        if project is not None and project.root == prefix.parent.resolve():
            return project
    return discover()
