"""Work-authored master-tap performance; shared lifecycle APIs are re-exported.

The work chooses master placement, monitoring, playback length and trim. Internal
capture/rebuild/export own copied files, recovery and native-content verification.
"""

import math
import tempfile
import time
from pathlib import Path

from tactus import tool
from tactus.bridges import ableton
from tactus.bridges.ableton_support.project import (
    capture,
    export_project,
    inspect,
    native,
    rebuild,
)

__all__ = ['capture', 'export_project', 'inspect', 'rebuild', 'render_project']


def render_project(ref, *, bridge_path, live_binary, tap, tap_browser_path,
                   seconds=8, replace_active_set=False):
    """Capture a rebuilt set through an authored master tap (real-time, pre-fader).

    The raw capture window starts before requesting transport start. Its leading
    silence/latency is retained; alignment/trimming is an explicit work decision.
    A writable scratch and recovery set remain available while Live uses them.
    """
    import sys

    from tactus.bridges.ableton_support import audio, devices, transport

    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('seconds must be finite and positive')
    if replace_active_set is not True:
        raise ValueError('Use a dedicated Live workspace and replace_active_set=True')
    tool(live_binary)
    tool(tap['amxd_path'])
    tool(str(Path(tap['amxd_path']).with_name('agent_audio_tap.js')))
    scratch = Path(tempfile.mkdtemp(prefix='tactus-live-project-'))
    try:
        rebuild(ref, bridge_path=bridge_path, out=scratch / 'session', replace_active_set=True)
        master_id = ableton.read(bridge_path=bridge_path)['master_track']['id']
        chain = ableton.read(bridge_path=bridge_path, scope='track', track_id=master_id)['devices']
        devices.append(['user_library', *tap_browser_path], bridge_path=bridge_path,
                       track_id=master_id, expected_chain=[d['id'] for d in chain])
        # Monitoring is this work's decision; the tap records before this fader.
        native('song.master_track.mixer_device.volume.value=0;song.current_song_time=0', bridge_path)
        def perform():
            with transport.playing(bridge_path=bridge_path, mode='arrangement', start_beat=0):
                time.sleep(seconds + .3)

        captured, rate = audio.capture(tap, perform, timeout=10)
        frames = round(seconds * rate)
        if captured.shape[1] != 2 or len(captured) < frames:
            raise ValueError('Unexpected Live capture; inspect scratch')
        print(f'Active native scratch/recovery retained: {scratch}', file=sys.stderr)
        return captured[:frames].copy(), rate
    except Exception as exc:
        exc.add_note(f'Live scratch/recovery retained: {scratch}; inspect before retrying')
        raise
