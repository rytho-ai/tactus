"""Read-only Git revision record for a run's receipt.

`record` shells out to `git` with list arguments only (never GitPython), scoped to the
entry directory, and never writes to the repository. Any absence — no `git` binary, no
repository, a git failure, or a timeout — yields `None` rather than raising, so a run
never fails because of Git. When the entry directory has tracked changes or untracked
`.py` files, one `source.patch` saved alongside the run holds the diff against `HEAD`
plus each untracked file as a new-file diff, so `git apply` of `patch` on `commit`
restores the exact executed source. `describe` is the same read-only Git reading for any
other directory a receipt attributes (an editable install's directory, for
`package_sources`): just `{commit, dirty}`, no patch. `remote_origin` and
`commit_on_remote` support `init.py`'s decision of whether an editable checkout's `HEAD`
can be pinned as a Git source for a new work (it must be clean and pushed).

Reads: nothing else in tactus; invoked by run.py at inventory time and init.py at scaffold time.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

_TIMEOUT = 10
_ENV = {"GIT_OPTIONAL_LOCKS": "0"}


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            env={**os.environ, **_ENV},
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def record(entry_dir: Path, out: Path) -> dict[str, Any] | None:
    """Record HEAD, dirtiness and untracked .py files for `entry_dir`, or None.

    `out` is the run's output directory; when dirty or with untracked `.py` files,
    `out/source.patch` receives `git diff HEAD --binary -- entry_dir` followed by a
    `/dev/null` diff for each untracked file. Returns None outside a repository, without
    a `git` binary, or on any git failure (including a repository with no commits,
    where `HEAD` does not resolve).
    """
    toplevel = _git(["rev-parse", "--show-toplevel"], entry_dir)
    if toplevel is None or toplevel.returncode != 0:
        return None
    head = _git(["rev-parse", "HEAD"], entry_dir)
    if head is None or head.returncode != 0:
        return None
    commit = head.stdout.strip()

    status = _git(["status", "--porcelain", "--", str(entry_dir)], entry_dir)
    if status is None or status.returncode != 0:
        return None
    # Untracked entries (`??`) are reported separately as `untracked`; dirty tracks
    # only tracked-file changes under the entry directory.
    dirty = any(line and not line.startswith("??") for line in status.stdout.splitlines())

    untracked_proc = _git(
        ["ls-files", "--others", "--exclude-standard", "--full-name", "--", str(entry_dir)],
        entry_dir,
    )
    if untracked_proc is None or untracked_proc.returncode != 0:
        return None
    root = Path(toplevel.stdout.strip())
    untracked_paths = sorted(
        line for line in untracked_proc.stdout.splitlines() if line.endswith(".py")
    )
    untracked = [(root / line).relative_to(entry_dir).as_posix() for line in untracked_paths]

    result: dict[str, Any] = {"commit": commit, "dirty": dirty, "untracked": untracked}
    if dirty or untracked_paths:
        diff = _git(["diff", "HEAD", "--binary", "--", str(entry_dir)], entry_dir)
        if diff is None or diff.returncode != 0:
            return None
        parts = [diff.stdout]
        for path in untracked_paths:
            # `--no-index` exits 1 when the files differ, which is always the case here.
            added = _git(["diff", "--no-index", "--binary", "--", "/dev/null", path], root)
            if added is None or added.returncode != 1:
                return None
            parts.append(added.stdout)
        (out / "source.patch").write_text("".join(parts), encoding="utf-8")
        result["patch"] = "source.patch"
    return result


def describe(directory: Path) -> dict[str, Any] | None:
    """Read-only `{commit, dirty}` for `directory`'s Git checkout, or None outside one.

    Unlike `record`, this attributes an arbitrary directory (not necessarily the run's
    entry directory) and never writes a patch file.
    """
    head = _git(["rev-parse", "HEAD"], directory)
    if head is None or head.returncode != 0:
        return None
    status = _git(["status", "--porcelain"], directory)
    if status is None or status.returncode != 0:
        return None
    dirty = any(line and not line.startswith("??") for line in status.stdout.splitlines())
    return {"commit": head.stdout.strip(), "dirty": dirty}


def remote_origin(directory: Path) -> str | None:
    """The `origin` remote's URL for `directory`'s checkout, or None without one."""
    result = _git(["remote", "get-url", "origin"], directory)
    if result is None or result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def commit_on_remote(directory: Path, commit: str) -> bool:
    """Whether `commit` is reachable from some remote-tracking branch, without fetching."""
    result = _git(["branch", "-r", "--contains", commit], directory)
    return result is not None and result.returncode == 0 and bool(result.stdout.strip())


def ensure_repository(directory: Path) -> bool:
    """`git init` `directory` unless it is already inside a work tree; True when it created one."""
    inside = _git(["rev-parse", "--is-inside-work-tree"], directory)
    if inside is not None and inside.returncode == 0 and inside.stdout.strip() == "true":
        return False
    created = _git(["init", "-q"], directory)
    return created is not None and created.returncode == 0
