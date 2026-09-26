"""JSON command adapters for functional productions, work scaffolding and diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

from .excerpt import excerpt, parse_outputs, parse_range
from .init import init
from .inputs import pool, tree
from .run import RunError, parse_params, run


class _RunParser(argparse.ArgumentParser):
    """Keep run argument failures in the same JSON envelope as execution failures."""

    def error(self, message: str) -> None:
        raise RunError("invalid_request", "request", message)


def main(argv: Sequence[str] | None = None) -> int:
    """Execute a command; functional runs reserve stdout for one JSON result."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    package_version = version("tactus")
    parser_type = (
        _RunParser
        if arguments[:1] in (["run"], ["material"], ["excerpt"], ["init"])
        else argparse.ArgumentParser
    )
    parser = parser_type(
        prog="tactus",
        description="Experimental code-first music production framework.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report the installed environment")
    run_command = commands.add_parser("run", help="Execute a Python render() production")
    run_command.add_argument("source", type=Path, help="Python file defining render(*, ...)")
    run_command.add_argument("--out", required=True, type=Path, help="New run directory")
    run_command.add_argument("--params", default="{}", help="JSON object of parameter overrides")
    run_command.add_argument(
        "--reuse",
        action="store_true",
        help="Reuse unchanged @stage results from prior runs on unchanged source",
    )
    excerpt_command = commands.add_parser(
        "excerpt", help="Slice an existing run's outputs into a new run directory"
    )
    excerpt_command.add_argument("run_dir", type=Path, help="Directory of a completed run")
    excerpt_command.add_argument("--out", required=True, type=Path, help="New run directory")
    excerpt_command.add_argument(
        "--range",
        required=True,
        help="START:END in seconds to publish; END may be empty for each output's end",
    )
    excerpt_command.add_argument("--outputs", help="Comma-separated output names to publish")
    init_command = commands.add_parser(
        "init", help="Scaffold a work as its own uv project depending on a pinned Tactus"
    )
    init_command.add_argument(
        "directory", type=Path, help="New work directory (must not exist or be empty)"
    )
    init_source = init_command.add_mutually_exclusive_group()
    init_source.add_argument(
        "--tactus-path", type=Path, help="Pin an editable local Tactus checkout"
    )
    init_source.add_argument("--tactus", help="Pin an explicit Tactus source as URL@REV")
    material_command = commands.add_parser("material", help="Manage the shared input material pool")
    material_subcommands = material_command.add_subparsers(dest="material_command", required=True)
    add_command = material_subcommands.add_parser(
        "add", help="Import files into the pool, printing their sha256 refs"
    )
    add_command.add_argument("paths", nargs="+", type=Path, help="Files or folders to import")
    try:
        args = parser.parse_args(arguments)
        if args.command == "run":
            result = run(
                args.source, out=args.out, params=parse_params(args.params), reuse=args.reuse
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "excerpt":
            result = excerpt(
                args.run_dir,
                out=args.out,
                range=parse_range(args.range),
                outputs=parse_outputs(args.outputs) if args.outputs is not None else None,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "init":
            result = init(args.directory, tactus_path=args.tactus_path, tactus=args.tactus)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.command == "material" and args.material_command == "add":
            for path in args.paths:
                if not path.is_file() and not path.is_dir():
                    raise RunError(
                        "invalid_request",
                        "request",
                        f"material path is not a file or directory: {path}",
                    )
            materials: dict[str, str] = {}
            try:
                for path in args.paths:
                    materials[str(path)] = (
                        tree.add(path) if path.is_dir() else f"sha256:{pool.put(path)}"
                    )
            except ValueError as exc:
                raise RunError("invalid_request", "request", str(exc)) from exc
            print(json.dumps({"status": "ok", "materials": materials}, sort_keys=True))
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
