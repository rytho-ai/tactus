"""CLI for shared selected-MIDI guards; the work authors replacement notes."""

import argparse
import json
from pathlib import Path

from tactus.bridges.reaper_support.selection import inspect_selection, replace_notes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-path", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    read = commands.add_parser("inspect", help="Read current item/time selection to JSON")
    read.add_argument("--out", required=True, type=Path)
    apply = commands.add_parser("apply", help="Apply authored notes against a saved snapshot")
    apply.add_argument("snapshot", type=Path)
    apply.add_argument("notes", type=Path, help="JSON list of replacement notes")
    args = parser.parse_args()
    if args.command == "inspect":
        if args.out.exists():
            parser.error(f"Output already exists: {args.out}")
        result = inspect_selection(resource_path=args.resource_path)
        args.out.write_text(json.dumps(result, indent=2) + "\n")
    else:
        result = replace_notes(json.loads(args.snapshot.read_text()),
                               json.loads(args.notes.read_text()), resource_path=args.resource_path)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
