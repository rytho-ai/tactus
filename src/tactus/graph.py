"""The compiled arrangement's small, versioned wire contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_graph(path: Path) -> dict[str, Any]:
    graph = json.loads(path.read_text(encoding="utf-8"))
    if graph.get("format_version") != 1:
        raise ValueError("unsupported arrangement format version")
    if not isinstance(graph.get("transport"), dict) or not isinstance(graph.get("tracks"), list):
        raise TypeError("invalid arrangement transport or tracks")
    return graph


def semantic_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Report ownership-level changes, not a text diff of generated JSON."""
    old = {track["name"]: track for track in before["tracks"]}
    new = {track["name"]: track for track in after["tracks"]}
    changes: dict[str, Any] = {}
    for name in sorted(old.keys() | new.keys()):
        if name not in old:
            changes[name] = {"change": "added"}
        elif name not in new:
            changes[name] = {"change": "removed"}
        elif old[name] != new[name]:
            old_events = {event["id"]: event for event in old[name]["events"]}
            new_events = {event["id"]: event for event in new[name]["events"]}
            changes[name] = {
                "gain_db": [old[name]["gain_db"], new[name]["gain_db"]]
                if old[name]["gain_db"] != new[name]["gain_db"]
                else None,
                "events": [
                    event_id
                    for event_id in sorted(old_events.keys() | new_events.keys())
                    if old_events.get(event_id) != new_events.get(event_id)
                ],
            }
    return {"transport_changed": before["transport"] != after["transport"], "tracks": changes}
