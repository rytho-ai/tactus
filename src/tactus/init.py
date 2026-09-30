"""Scaffold a work as its own uv project pinned to a Tactus source.

Before this module, a work borrowed Tactus's own environment (`uv run --project <tactus>`):
it could not add a package of its own, its receipt's `dependency_lock` was always null, and
its environment moved whenever the Tactus checkout moved. `init` fixes this by writing the
work a `pyproject.toml` that depends on `tactus` through `[tool.uv.sources]`, pinned to a
resolved Git source, plus a `.gitignore`, then running `uv lock` so the work has its own
`uv.lock`, and a Git repository rooted at the work even inside another checkout.
Git availability and initialization failures are reported explicitly. `_tactus_source`
resolves that pin: by default the *running* Tactus's own PEP 610
origin (reusing `_source.direct_url`, the same parsing `run.py` uses for receipt attribution),
falling back to an explicit `--tactus-path`/`--tactus` override. An editable checkout is only
usable as a source when it is clean and its `HEAD` is already pushed (`revision.py`); a dirty
or unpushed checkout fails with a message telling the caller to push or use `--tactus-path`.
`requires-python` always comes from the *running* Tactus's own metadata, regardless of which
source is pinned, since that is the interpreter constraint `init` itself was verified against
(Pedalboard's cp313 crash — see `docs/design.md`).

Reads: _source.direct_url/RunError · revision.describe/remote_origin/commit_on_remote/ensure_repository
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from importlib.metadata import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

from . import revision
from ._contracts import RunError
from ._source import direct_url as _direct_url

_GITIGNORE = "runs/\nanalyses/\nexports/\n.tactus/\n.venv/\n__pycache__/\n"


def _project_name(directory: Path) -> str:
    name = re.sub(r"[^a-z0-9._-]+", "-", directory.name.lower()).strip("-.")
    return name or "work"


def _requires_python() -> str:
    value = metadata("tactus").get("Requires-Python")
    if not value:
        raise RunError(
            "init_failed", "request", "the installed tactus has no Requires-Python metadata"
        )
    return str(value)


def _path_source(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_dir():
        raise RunError("invalid_request", "request", f"--tactus-path is not a directory: {path}")
    return {"path": str(resolved), "editable": True}


def _explicit_source(spec: str) -> dict[str, Any]:
    if "@" not in spec:
        raise RunError("invalid_request", "request", f"--tactus must be URL@REV: {spec!r}")
    url, rev = spec.rsplit("@", 1)
    if not url or not rev:
        raise RunError("invalid_request", "request", f"--tactus must be URL@REV: {spec!r}")
    return {"git": url, "rev": rev}


def _running_tactus_source() -> dict[str, Any]:
    """The running Tactus's own origin, as a `[tool.uv.sources]` entry.

    A Git install pins that same URL and commit. An editable (directory) install pins the
    checkout's `origin` remote at `HEAD`, but only when the checkout is clean and `HEAD` is
    reachable from a remote-tracking branch — otherwise a caller elsewhere could not fetch it.
    """
    info = _direct_url("tactus")
    if info is None:
        raise RunError(
            "init_failed",
            "request",
            "the installed tactus has no recorded install source (not Git or a local "
            "checkout); pass --tactus-path or --tactus",
        )
    vcs_info = info.get("vcs_info")
    if vcs_info:
        return {"git": info.get("url", ""), "rev": vcs_info.get("commit_id")}
    dir_info = info.get("dir_info")
    if dir_info:
        parsed = urlparse(info.get("url", ""))
        if parsed.scheme != "file":
            raise RunError(
                "init_failed", "request", f"unsupported tactus install source: {info.get('url')!r}"
            )
        directory = Path(url2pathname(parsed.path))
        git = revision.describe(directory)
        if git is None:
            raise RunError(
                "init_failed",
                "request",
                "the editable tactus checkout is not a Git repository; pass --tactus-path "
                "or --tactus",
            )
        if git["dirty"]:
            raise RunError(
                "init_failed",
                "request",
                "the editable tactus checkout has uncommitted changes; commit and push it, "
                "or pass --tactus-path",
            )
        origin = revision.remote_origin(directory)
        if origin is None:
            raise RunError(
                "init_failed",
                "request",
                "the editable tactus checkout has no 'origin' remote; push it, or pass "
                "--tactus-path",
            )
        if not revision.commit_on_remote(directory, git["commit"]):
            raise RunError(
                "init_failed",
                "request",
                f"commit {git['commit']} is not pushed to origin; push it, or pass --tactus-path",
            )
        return {"git": origin, "rev": git["commit"]}
    raise RunError(
        "init_failed",
        "request",
        "unsupported tactus install source (neither Git nor a directory checkout); pass "
        "--tactus-path or --tactus",
    )


def _pyproject_toml(name: str, requires_python: str, source: dict[str, Any]) -> str:
    fields = ", ".join(f"{key} = {json.dumps(value)}" for key, value in source.items())
    return (
        "[project]\n"
        f'name = "{name}"\n'
        'version = "0.1.0"\n'
        f'requires-python = "{requires_python}"\n'
        'dependencies = ["tactus"]\n'
        "\n"
        "[tool.uv.sources]\n"
        f"tactus = {{ {fields} }}\n"
    )


def init(
    directory: str | Path,
    *,
    tactus_path: str | Path | None = None,
    tactus: str | None = None,
) -> dict[str, Any]:
    """Scaffold `directory` as a uv project depending on a pinned Tactus, then `uv lock` it.

    `directory` must not exist or must be empty. `tactus_path` pins an editable local
    checkout; `tactus` pins an explicit `URL@REV`; passing both is a request error. With
    neither, the source is the running Tactus's own origin (see `_running_tactus_source`).
    Does not write `song.py`; the work's content belongs to whoever writes it next. Runs
    `git init` creates a repository rooted at `directory`, even inside another checkout.
    The author commits the first source before rendering; initialization alone creates no HEAD.
    """
    if tactus_path is not None and tactus is not None:
        raise RunError(
            "invalid_request", "request", "--tactus-path and --tactus are mutually exclusive"
        )
    try:
        directory = Path(directory).resolve()
    except OSError as exc:
        raise RunError("invalid_request", "request", str(exc)) from exc
    if directory.exists() and any(directory.iterdir()):
        raise RunError("invalid_request", "request", f"directory is not empty: {directory}")
    uv = shutil.which("uv")
    if uv is None:
        raise RunError("init_failed", "request", "uv is not installed or not on PATH")
    if shutil.which("git") is None:
        raise RunError("init_failed", "request", "Git is not installed or not on PATH; install Git before tactus init")

    if tactus_path is not None:
        source = _path_source(Path(tactus_path))
    elif tactus is not None:
        source = _explicit_source(tactus)
    else:
        source = _running_tactus_source()
    requires_python = _requires_python()

    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pyproject.toml").write_text(
        _pyproject_toml(_project_name(directory), requires_python, source), encoding="utf-8"
    )
    (directory / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")

    try:
        subprocess.run([uv, "lock"], cwd=directory, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise RunError("init_failed", "lock", f"uv lock failed: {exc.stderr}") from exc

    try:
        git_created = revision.ensure_repository(directory)
    except OSError as exc:
        raise RunError("init_failed", "git", str(exc)) from exc
    return {
        "status": "ok",
        "work": str(directory),
        "tactus": source,
        "python": requires_python,
        "git_init": git_created,
    }
