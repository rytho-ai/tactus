"""Discover isolated native DAW queues while accepting an installed legacy bridge."""

import json
import time
from pathlib import Path


def available(base: Path, *, protocol: int = 1) -> list[dict]:
    """Return fresh bridge endpoints; isolated queues take precedence over legacy."""
    roots = sorted((base / "instances").glob("*/heartbeat.json"))
    roots.append(base / "heartbeat.json")
    found = []
    for heartbeat_path in roots:
        try:
            data = json.loads(heartbeat_path.read_text(encoding="utf-8"))
            age = time.time() - data["time"]
            if data["protocol"] != protocol or not -2 <= age <= 10:
                continue
            instance = data.get("instance")
            if heartbeat_path.parent != base:
                if instance != heartbeat_path.parent.name:
                    continue
            elif not isinstance(instance, str) or not instance:
                instance = "legacy"
            found.append({"connection_id": instance, "root": heartbeat_path.parent,
                          "heartbeat": data})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    # New bridges may leave an old top-level heartbeat behind. Never offer it
    # alongside isolated processes: that would invent a duplicate endpoint.
    if any(row["connection_id"] != "legacy" and row["root"] != base for row in found):
        found = [row for row in found if row["root"] != base]
    return found


def select(base: Path, connection_id: str | None) -> dict:
    endpoints = available(base)
    if connection_id is not None:
        matches = [row for row in endpoints if row["connection_id"] == connection_id]
        if len(matches) != 1:
            raise ValueError(f"Bridge connection {connection_id!r} is unavailable or stale")
        return matches[0]
    if len(endpoints) != 1:
        raise ValueError("No bridge connection is ready (missing or stale heartbeat)" if not endpoints else
                         "Multiple bridge connections are ready; specify connection_id")
    return endpoints[0]
