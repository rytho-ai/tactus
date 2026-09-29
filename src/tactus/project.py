"""Discover one work's pyproject and its explicit Tactus command registrations.

The nearest pyproject is a boundary, including an unrelated Python project. Launcher
and command registry share this lookup; paths supplied by users keep their cwd meaning.
"""

from __future__ import annotations

import re
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
