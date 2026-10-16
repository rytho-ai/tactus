"""Edit notes inside the live time selection of one selected MIDI item.

Copy with selection.lua into a work. inspect_selection returns project-quarter-note
coordinates; replace_notes accepts authored notes and preserves other MIDI events.
The native snapshot is valid only in the running bridge and is consumed on apply.
"""

import argparse
import json
import math
import uuid
from pathlib import Path

from tactus import tool
from tactus.bridges import reaper


def _execute(resource_path, args):
    lua = tool(str(Path(__file__).with_name("selection.lua")))
    return reaper.execute(lua.read_text(), resource_path=resource_path, args=args)


def inspect_selection(*, resource_path):
    """Read one selected MIDI item and fully contained notes in the time selection."""
    return _execute(resource_path, {"mode": "read", "token": uuid.uuid4().hex})


def replace_notes(snapshot, notes, *, resource_path):
    """Replace the inspected notes in one Undo; re-read after a stale/error response.

    Notes use start_qn/end_qn (absolute project quarter notes), pitch 0..127,
    velocity 1..127; channel defaults to 0, selected/muted to False. [] removes
    the editable notes. This does not change the time selection or instrument.
    """
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("token"), str):
        raise TypeError("Use the snapshot returned by inspect_selection")
    if not isinstance(notes, list):
        raise TypeError("notes must be a list")
    bounds = snapshot.get("range_qn")
    if not isinstance(bounds, list) or len(bounds) != 2:
        raise ValueError("Snapshot is missing range_qn")
    clean = []
    required = {"start_qn", "end_qn", "pitch", "velocity"}
    allowed = required | {"channel", "selected", "muted"}
    for note in notes:
        if not isinstance(note, dict) or not required <= note.keys() <= allowed:
            raise ValueError("Each note needs start_qn, end_qn, pitch, velocity")
        n = {"channel": 0, "selected": False, "muted": False, **note}
        for key in ("start_qn", "end_qn"):
            value = n[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{key} must be finite")
        if not bounds[0] <= n["start_qn"] < n["end_qn"] <= bounds[1]:
            raise ValueError("Notes must fit inside the inspected range_qn")
        for key, low, high in (("pitch", 0, 127), ("velocity", 1, 127), ("channel", 0, 15)):
            if type(n[key]) is not int or not low <= n[key] <= high:
                raise ValueError(f"{key} must be an integer in {low}..{high}")
        if type(n["selected"]) is not bool or type(n["muted"]) is not bool:
            raise ValueError("selected and muted must be booleans")
        clean.append(n)
    return _execute(resource_path, {"mode": "apply", "token": snapshot["token"], "notes": clean})


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
