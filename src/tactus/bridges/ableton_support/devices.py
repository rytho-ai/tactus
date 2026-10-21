"""Inspect metadata once, batch guarded edits, and settle one chosen device load.

The caller chooses device paths, tracks and every parameter value. Native target,
layout and observed-value checks remain fresh. No automatic retry or rendering.
Reads: native state.devices via ableton.execute, monotonic clock.
"""

import math
import time

from .. import ableton


def inspect(*, bridge_path, track_id, device_id, parameters=None, metadata=True, timeout=10):
    """Read fresh chosen values and optional reusable metadata without changing selection."""
    return ableton.execute('result = state.devices.inspect(**args)', bridge_path=bridge_path,
                           args={'track_id': track_id, 'device_id': device_id,
                                 'parameters': parameters, 'metadata': metadata}, timeout=timeout)


def configure_many(edits, *, bridge_path, timeout=10):
    """Preflight all snapshots, write once, return compact fresh readback in one Undo.

    Each edit is {snapshot: inspect result, values: {parameter name/ID: native value}}.
    Native errors can leave partial edits; inspect and use native Undo deliberately.
    No automatic rollback, retry, recording or rendering.
    """
    return ableton.execute('result = state.devices.configure(args)', bridge_path=bridge_path,
                           args=edits, timeout=timeout, undo='Configure inspected devices')


def configure(snapshot, values, *, bridge_path, timeout=10):
    """Configure one inspected device through the same whole-batch preflight."""
    return configure_many([{'snapshot': snapshot, 'values': values}],
                          bridge_path=bridge_path, timeout=timeout)[0]


def browse(*, bridge_path, root='audio_effects', path=None, search='', recursive=False,
           include_presets=False, refresh=False, timeout=10):
    """Search reusable browser metadata; loading resolves the fresh native item.

    Entries may be instruments/templates or duplicate names. This lists the native
    browser index, not a guarantee of plugin authorization or tested sound.
    """
    return ableton.execute('result = state.devices.browse(**args)', bridge_path=bridge_path,
                           args={'root': root, 'path': path, 'search': search,
                                 'recursive': recursive, 'include_presets': include_presets,
                                 'refresh': refresh}, timeout=timeout)


def append(browser_path, *, bridge_path, track_id, expected_chain, timeout=10,
           parameters=None, metadata=False, uri=None):
    """Load once, wait/configure/readback without intermediate agent decisions.

    Defaults retain the original {id, name, class} result. Optional parameters are
    explicit native values; metadata=True also returns the new device's snapshot.
    uri disambiguates a same-name final browser item. Polls read only until the
    exact chain settles, then preflight/configure once and return its readback.
    Loading and parameter configuration use separate Undo steps: never hold an
    Undo group across waiting ticks and interleaved human actions. An error may
    leave the new device/partial settings; inspect before retrying.
    """
    if (not isinstance(browser_path, list) or len(browser_path) < 2
            or any(not isinstance(part, str) or not part for part in browser_path)):
        raise ValueError('Supply a browser root and exact child path')
    if not isinstance(track_id, str) or not track_id:
        raise ValueError('Supply an inspected runtime track_id')
    if (not isinstance(expected_chain, list)
            or any(not isinstance(item, str) or not item for item in expected_chain)
            or len(set(expected_chain)) != len(expected_chain)):
        raise ValueError('Supply the ordered inspected device IDs as expected_chain')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    if parameters is not None and (not isinstance(parameters, dict) or not parameters):
        raise ValueError('parameters must be a nonempty mapping or None')
    if parameters is not None:
        for key, value in parameters.items():
            if (not isinstance(key, str) or not key or type(value) not in (int, float)
                    or not math.isfinite(value)):
                raise ValueError('parameters must map names/IDs to finite native numbers')
    if uri is not None and (not isinstance(uri, str) or not uri):
        raise ValueError('uri must be a nonempty inspected browser URI or None')
    ableton.execute('''
state.devices.begin_append(args['path'], args['track'], args['chain'], args['uri'])
''', bridge_path=bridge_path,
        args={'track': track_id, 'chain': expected_chain, 'path': browser_path, 'uri': uri},
        timeout=timeout, undo='Append inspected browser device')
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Device load completion unknown; inspect the chain before retrying')
        result = ableton.execute('result = state.devices.finish_append(**args)',
            bridge_path=bridge_path,
            args={'track_id': track_id, 'expected_chain': expected_chain,
                  'parameters': parameters, 'metadata': metadata},
            timeout=remaining, undo='Configure appended device' if parameters else None)
        if not result['pending']:
            return result['device']
        time.sleep(min(.05, max(0, deadline-time.monotonic())))
