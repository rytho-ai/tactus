"""Execute native Python in Live through the packaged TactusBridge Remote Script.

Transport, completion, errors, fresh reads and guarded selected-note edits belong here.
Work-authored code owns musical values and Max/VST operations. Live state is external input.
Reads: standalone Remote Script's local JSON queue; shared finite JSON; inputs.tool.
"""

from __future__ import annotations

import math
import sys
import time
import uuid
from pathlib import Path

from .._contracts import json_copy, strict_json, write_json
from ..inputs import ToolError, tool
from .TactusBridge.bridge import PROTOCOL
from .TactusBridge.selection import validate_notes

__all__ = ["BridgeError", "BridgeTimeout", "execute", "inspect_selection", "read", "script",
           "update_notes"]


class BridgeError(RuntimeError):
    """Live is unavailable, the transport failed, or native Python raised an error."""


class BridgeTimeout(TimeoutError):
    """Completion is unknown; inspect native state/late reply before retrying."""


def script() -> Path:
    """Packaged Remote Script directory; copy it to User Library/Remote Scripts."""
    return Path(__file__).with_name("TactusBridge")


def read(*, bridge_path: str | Path, scope: str = 'summary', track_id: str | None = None,
         device_id: str | None = None, timeout: float = 30):
    """Read fresh summary/track/notes/device/project state using the native owner.

    IDs are runtime-only; omitted targets use Live's current selection. Project and
    notes retain the lifecycle/guarded-edit data shapes. Summary/device include
    observed change counters; these are incomplete hints, not stale-edit guards.
    """
    return execute('result = state.read(**args)', bridge_path=bridge_path,
                   args={'scope': scope, 'track_id': track_id, 'device_id': device_id},
                   timeout=timeout)


def inspect_selection(*, bridge_path: str | Path):
    """Inspect selected MIDI with a one-use snapshot; coordinates are clip-local beats."""
    return execute('result = state.selection.inspect()', bridge_path=bridge_path)


def update_notes(snapshot, notes, *, bridge_path: str | Path):
    """Apply full selected-note rows after fresh exact-content checks; never choose values.

    Supply one full row per selected ID. Native token consumption, Undo and partial
    failure semantics stay explicit; after a native call inspect again before editing.
    """
    validate_notes(snapshot, notes)
    return execute('result = state.selection.update(args["token"], args["notes"])',
                   bridge_path=bridge_path, args={'token': snapshot['token'], 'notes': notes},
                   undo='Edit selected MIDI notes')


def execute(code: str, *, bridge_path: str | Path, args=None,
            timeout: float = 30, undo: str | None = None):
    """Run Python on Live's main thread; return the finite JSON value of `result`.

    `bridge_path` is the installed TactusBridge directory. Code receives native
    Live/song/app/state, explicit args, and result=None. Prints go to Python stderr.
    `undo` requests a native Undo group; Live owns the displayed Undo description.
    Errors/timeouts never imply rollback/cancellation and are never retried.
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError("code must be nonempty native Python")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite positive number of seconds")
    if undo is not None and (not isinstance(undo, str) or not undo):
        raise ValueError("undo must be a nonempty label or None")
    bindings = json_copy(args)
    root = Path(bridge_path).expanduser().resolve() / "tactus-bridge"
    try:
        heartbeat = strict_json((root / "heartbeat.json").read_text(encoding="utf-8"))
        if heartbeat["protocol"] != PROTOCOL:
            raise ValueError("incompatible protocol")
        instance = heartbeat["instance"]
        if not isinstance(instance, str) or not instance:
            raise ValueError("missing instance")
        if not -2 <= time.time() - heartbeat["time"] <= 10:
            raise ValueError("stale heartbeat (Live may be busy)")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BridgeError(
            f"Ableton bridge unavailable at {root}: {exc}. "
            f"Copy {script()} into User Library/Remote Scripts and select TactusBridge "
            "in Live's MIDI preferences."
        ) from exc
    try:
        for name in ("__init__.py", "bridge.py", "state.py", "selection.py", "devices.py"):
            tool(str(root.parent / name))
    except (ToolError, OSError) as exc:
        raise BridgeError(f"Cannot read installed Ableton Remote Script sources: {exc}") from exc
    request_id = uuid.uuid4().hex
    request = root / "requests" / f"{request_id}.json"
    response = root / "responses" / f"{request_id}.json"
    try:
        write_json(request, {
            "protocol": PROTOCOL, "id": request_id, "instance": instance,
            "expires": time.time() + timeout, "code": code, "args": bindings, "undo": undo,
        }, compact=True)
    except OSError as exc:
        raise BridgeError(f"Cannot submit Ableton request {request_id}: {exc}") from exc
    deadline = time.monotonic() + timeout
    while True:
        try:
            raw = response.read_text(encoding="utf-8")
        except FileNotFoundError:
            if time.monotonic() >= deadline:
                request.unlink(missing_ok=True)
                raise BridgeTimeout(
                    f"Ableton request {request_id} timed out; execution may have started. "
                    f"Inspect DAW state before retrying; a late reply may appear at {response}"
                ) from None
            time.sleep(min(.02, max(0, deadline - time.monotonic())))
            continue
        except OSError as exc:
            raise BridgeError(
                f"Cannot read Ableton reply {request_id}; completion unknown: {exc}. "
                f"Inspect DAW state and {response} before retrying."
            ) from exc
        try:
            reply = strict_json(raw)
            if (reply["id"] != request_id or reply["instance"] != instance
                    or type(reply["ok"]) is not bool):
                raise ValueError("reply identity/status mismatch")
            if reply["ok"] and "result" not in reply:
                raise ValueError("missing result")
            if not isinstance(reply.get("output", ""), str):
                raise TypeError("invalid diagnostic output")
        except (ValueError, KeyError, TypeError) as exc:
            raise BridgeError(f"Invalid Ableton reply for {request_id}: {response}") from exc
        response.unlink()
        if reply.get("output"):
            print(reply["output"], file=sys.stderr, end="")
        if not reply["ok"]:
            raise BridgeError(reply.get("error", "Native Ableton request failed"))
        return reply["result"]
