"""Read-only Git revision record for a run's receipt.

`record` shells out to `git` with list arguments only (never GitPython), scoped to the
entry directory, and never writes to the repository. Any absence — no `git` binary, no
repository, a git failure, or a timeout — yields `None` rather than raising, so a run
never fails because of Git. When the entry directory is dirty, the diff against `HEAD`
is saved alongside the run as `source.patch` so `commit` + `patch` can restore the
exact executed source.

Reads: nothing else in tactus; invoked by run.py at inventory time.
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

    `out` is the run's output directory; when dirty, `out/source.patch` receives
    `git diff HEAD --binary -- entry_dir`. Returns None outside a repository, without
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
    untracked = sorted(
        (root / line).relative_to(entry_dir).as_posix()
        for line in untracked_proc.stdout.splitlines()
        if line.endswith(".py")
    )

    result: dict[str, Any] = {"commit": commit, "dirty": dirty, "untracked": untracked}
    if dirty:
        diff = _git(["diff", "HEAD", "--binary", "--", str(entry_dir)], entry_dir)
        if diff is None or diff.returncode != 0:
            return None
        (out / "source.patch").write_text(diff.stdout, encoding="utf-8")
        result["patch"] = "source.patch"
    return result
