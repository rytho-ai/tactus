"""JSON command adapters for functional productions and environment diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

from .run import RunError, parse_params, run


class _RunParser(argparse.ArgumentParser):
    """Keep run argument failures in the same JSON envelope as execution failures."""

    def error(self, message: str) -> None:
        raise RunError("invalid_request", "request", message)


def main(argv: Sequence[str] | None = None) -> int:
    """Execute a command; functional runs reserve stdout for one JSON result."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    package_version = version("tactus")
    parser_type = _RunParser if arguments[:1] == ["run"] else argparse.ArgumentParser
    parser = parser_type(
        prog="tactus",
        description="Experimental code-first music production framework.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {package_version}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report the installed environment")
    run_command = commands.add_parser("run", help="Execute a Python render() production")
    run_command.add_argument("source", type=Path, help="Python file defining render(*, ...)")
    run_command.add_argument("--out", required=True, type=Path, help="New run directory")
    run_command.add_argument("--params", default="{}", help="JSON object of parameter overrides")
    try:
        args = parser.parse_args(arguments)
        if args.command == "run":
            result = run(args.source, out=args.out, params=parse_params(args.params))
            print(json.dumps(result, sort_keys=True))
            return 0
    except RunError as exc:
        print(json.dumps(exc.to_dict(), sort_keys=True))
        return exc.exit_code

    if args.command == "doctor":
        print(
            json.dumps(
                {
                    "package": "tactus",
                    "version": package_version,
                    "python": sys.version.split()[0],
                    "status": "ok",
                },
                sort_keys=True,
            )
        )
        return 0

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
