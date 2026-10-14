"""Global console entry: delegate to the work's locked environment, never back to self.

uv invokes `python -m tactus.cli` rather than the console script, so even older pinned
Tactus versions cannot recurse. Init belongs to the launcher installation. No work
means local/global execution; failed project resolution never falls back to global.
A work inside a uv workspace uses the workspace's `uv.lock` (see project.environment_root).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from .project import environment_root, selected_project


def _delegate(command: list[str], env: dict[str, str]) -> int:
    """Run the work's command and wait for it, even through Ctrl-C.

    A terminal's Ctrl-C reaches the whole process group, so the child handles it itself
    (a `tactus serve` shuts down and prints its summary); the launcher keeps waiting
    instead of abandoning it. SIGTERM, which a program sends to the launcher alone, is
    forwarded.
    """
    process = subprocess.Popen(command, env=env)
    previous = signal.signal(signal.SIGTERM, lambda signum, _frame: process.send_signal(signum))
    try:
        while True:
            try:
                return process.wait()
            except KeyboardInterrupt:
                continue
    finally:
        signal.signal(signal.SIGTERM, previous)


def main() -> int:
    args = sys.argv[1:]
    try:
        explicit = None
        if args[:1] == ["--project"]:
            if len(args) < 2:
                raise ValueError("--project requires a directory")
            explicit = Path(args[1])
            if not explicit.is_dir():
                raise ValueError(f"project directory does not exist: {explicit}")
            args = args[2:]
        project = selected_project(explicit)
        if explicit is not None and project is None:
            raise ValueError(f"no Tactus work found at {explicit}")
        if project is not None and args[:1] != ["init"]:
            owner = environment_root(project.root)
            if not (owner / "uv.lock").is_file():
                if owner == project.root:
                    raise ValueError(f"work has no uv.lock: {project.root}; run uv lock first")
                raise ValueError(
                    f"uv workspace {owner} (containing work {project.root}) has no uv.lock; "
                    "run uv lock there first"
                )
            uv = shutil.which("uv")
            if uv is None:
                raise ValueError("uv is required to use the work's environment")
            env = dict(os.environ)
            # An activated unrelated environment must not override the selected work.
            env.pop("VIRTUAL_ENV", None)
            env.pop("UV_PROJECT_ENVIRONMENT", None)
            env["TACTUS_PROJECT_ROOT"] = str(project.root)
            command = [
                uv,
                "run",
                "--project",
                str(project.root),
                "--locked",
                "--",
                "python",
                "-m",
                "tactus.cli",
                *args,
            ]
            return _delegate(command, env)
        from .cli import main as cli_main

        return cli_main(args)
    except (ValueError, TypeError, OSError) as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": {
                        "code": "project_unavailable",
                        "phase": "request",
                        "message": str(exc),
                    },
                }
            )
        )
        return 2
    except KeyboardInterrupt:
        return 130
