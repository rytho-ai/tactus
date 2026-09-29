"""Global console entry: delegate to the work's locked environment, never back to self.

uv invokes `python -m tactus.cli` rather than the console script, so even older pinned
Tactus versions cannot recurse. Init belongs to the launcher installation. No work
means local/global execution; failed project resolution never falls back to global.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .project import discover


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
        project = discover(explicit)
        if explicit is not None and project is None:
            raise ValueError(f"no Tactus work found at {explicit}")
        if project is not None and args[:1] != ["init"]:
            if not (project.root / "uv.lock").is_file():
                raise ValueError(f"work has no uv.lock: {project.root}; run uv lock first")
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
            return subprocess.run(command, env=env, check=False).returncode
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
