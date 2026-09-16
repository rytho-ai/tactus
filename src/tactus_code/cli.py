"""The minimal executable entry point for the Tactus Code experiment."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.metadata import version


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bootstrap CLI without claiming unimplemented production features."""
    package_version = version("tactus-code")
    parser = argparse.ArgumentParser(
        prog="tactus-code",
        description="Experimental code-first music production framework.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {package_version}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report the installed bootstrap environment")
    args = parser.parse_args(argv)

    if args.command == "doctor":
        print(
            json.dumps(
                {
                    "package": "tactus-code",
                    "version": package_version,
                    "python": sys.version.split()[0],
                    "status": "bootstrap",
                },
                sort_keys=True,
            )
        )
        return 0

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
