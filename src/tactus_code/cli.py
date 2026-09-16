"""The minimal executable entry point for the Tactus Code experiment."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from importlib.metadata import version
from pathlib import Path

from .build import build
from .graph import read_graph, semantic_diff
from .render import render


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
    build_command = commands.add_parser("build", help="Compile a Python music project")
    build_command.add_argument("source", type=Path, help="Entry point defining TRANSPORT and build")
    build_command.add_argument("--out", type=Path, help="Generated build directory")
    inspect_command = commands.add_parser("inspect", help="Summarize a compiled arrangement")
    inspect_command.add_argument("graph", type=Path)
    render_command = commands.add_parser("render", help="Render from compiled state only")
    render_command.add_argument("graph", type=Path)
    render_command.add_argument("--out", required=True, type=Path)
    render_command.add_argument("--mute", action="append", default=[])
    render_command.add_argument("--solo", action="append", default=[])
    diff_command = commands.add_parser("diff", help="Compare two compiled arrangements")
    diff_command.add_argument("before", type=Path)
    diff_command.add_argument("after", type=Path)
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

    if args.command == "build":
        output = args.out or args.source.resolve().parent / ".tactus-code" / "build"
        print(json.dumps({key: str(path) for key, path in build(args.source, output).items()}))
        return 0
    if args.command == "inspect":
        graph = read_graph(args.graph)
        print(
            json.dumps(
                {
                    "transport": graph["transport"],
                    "tracks": [
                        {"name": track["name"], "events": len(track["events"])}
                        for track in graph["tracks"]
                    ],
                    "computations": len(graph["computations"]),
                    "outputs": graph["outputs"],
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "render":
        files = render(
            args.graph, args.out, mute=frozenset(args.mute), solo=frozenset(args.solo)
        )
        print(json.dumps({key: str(path) for key, path in files.items()}, sort_keys=True))
        return 0
    if args.command == "diff":
        print(json.dumps(semantic_diff(read_graph(args.before), read_graph(args.after)), sort_keys=True))
        return 0

    parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
