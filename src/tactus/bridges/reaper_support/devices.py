"""Inspect native FX descriptions once and batch guarded normalized parameter edits.

Track/FX GUIDs and zero-based parameter indices stay native REAPER concepts. Values
remain caller-chosen; descriptors are cached inside the running bridge Action, while
every write resolves the live target, layout and observed values afresh.
Reads: packaged devices.lua; inputs.tool; reaper.execute.
"""

from pathlib import Path

from tactus import tool
from tactus.bridges import reaper


def _execute(resource_path, mode, *, undo=None, timeout=10, **args):
    lua = tool(str(Path(__file__).with_suffix('.lua')))
    return reaper.execute(lua.read_text(), resource_path=resource_path,
                          args={'mode': mode, **args}, undo=undo, timeout=timeout)


def inspect(*, resource_path, track_guid, fx_guid, parameters=None,
            metadata=True, refresh=False, timeout=10):
    """Read fresh values at selected zero-based indices; omit parameters for all.

    Values use REAPER's normalized 0..1 scale, not plugin-specific physical units.
    Metadata supplies native labels. Cached descriptions never authorize writes.
    The ordinary track FX chain, including Master FX, is supported; use native Lua
    for other chain/container encodings. No selection, audio or project save occurs.
    """
    return _execute(resource_path, 'inspect', timeout=timeout, track_guid=track_guid,
                    fx_guid=fx_guid, parameters=parameters, metadata=metadata, refresh=refresh)


def configure_many(edits, *, resource_path, timeout=10):
    """Preflight every snapshot before any write; return compact actual values.

    Each edit is {snapshot: inspect result, values: {index string: normalized value}}.
    Native setters can fail after partial changes; there is no automatic rollback,
    retry or render. One native Undo groups the requested parameter writes.
    """
    return _execute(resource_path, 'configure', edits=edits, timeout=timeout,
                    undo='Configure inspected FX')


def configure(snapshot, values, *, resource_path, timeout=10):
    """Configure one inspected FX through the same whole-batch preflight."""
    return configure_many([{'snapshot': snapshot, 'values': values}],
                          resource_path=resource_path, timeout=timeout)[0]


def stats(*, resource_path, timeout=10):
    """Inspect this running Action's descriptor-cache counts without reading audio."""
    return _execute(resource_path, 'stats', timeout=timeout)
