"""Guarded edits to one selected inline MIDI take and its explicit time range.

Owns one-use native inspections, note validation, scope checks and Undo. Musical
note values remain authored. Reads: packaged selection.lua; reaper.execute.
"""

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
