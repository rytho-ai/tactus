"""Append an explicitly chosen browser device once and verify its settled native chain.

The caller chooses the device path, track and expected full chain. No routing,
instrument choice or parameter settings are implied; native failures are not rollback.
Reads: native exact targets/browser paths via ableton.execute/read, monotonic clock.
"""

import math
import time

from .. import ableton


def append(browser_path, *, bridge_path, track_id, expected_chain, timeout=10):
    """Append after the last device; return the settled new device's ID/name/class.

    browser_path starts with an app.browser root attribute followed by exact child
    names, e.g. ['instruments', 'Operator']. expected_chain is the ordered runtime-ID
    list read before the request. Reject hotswap, ambiguous paths and changed chains
    before loading. Loading happens once; only fresh readback is polled. Unsupported
    native insertion/replacement is reported as a changed chain, never hidden/retried.
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
    ableton.execute('''
t=state.track(args['track'])
assert [str(d._live_ptr) for d in t.devices]==args['chain'], 'Device chain changed; inspect again'
assert app.browser.hotswap_target is None, 'Exit browser hotswap before appending'
node=getattr(app.browser,args['path'][0])
for name in args['path'][1:]:
    matches=[c for c in node.children if c.name==name]
    assert len(matches)==1, 'Missing/ambiguous browser path: '+name
    node=matches[0]
assert node.is_loadable, 'Choose a loadable browser device'
song.view.selected_track=t
if t.devices:song.view.select_device(t.devices[-1])
app.browser.load_item(node)
''', bridge_path=bridge_path,
        args={'track': track_id, 'chain': expected_chain, 'path': browser_path},
        timeout=timeout, undo='Append inspected browser device')
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Device load completion unknown; inspect the chain before retrying')
        row = ableton.read(bridge_path=bridge_path, scope='track', track_id=track_id,
                           timeout=remaining)
        chain = [d['id'] for d in row['devices']]
        if chain == expected_chain:
            time.sleep(min(.05, max(0, deadline-time.monotonic())))
            continue
        if len(chain) == len(expected_chain) + 1 and chain[:-1] == expected_chain:
            return row['devices'][-1]
        raise ableton.BridgeError('Device chain changed during load; inspect before further edits')
