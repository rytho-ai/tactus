"""Own start/stop completion around an explicitly authored Live performance.

The caller chooses Arrangement/Session, start beat, clip, quantization and duration.
Native writes happen once; only state readback is polled. No routing/gain changes.
Reads: native Live transport/clip identity via shared bridge and cleanup ownership.
"""

import math
import time
from contextlib import contextmanager

from .. import ableton
from ._lifecycle import cleanup


def _wait(bridge_path, playing, timeout):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Transport completion unknown; inspect Live before retrying')
        if ableton.read(bridge_path=bridge_path, timeout=remaining)['is_playing'] is playing:
            return
        time.sleep(min(.02, max(0, deadline-time.monotonic())))


@contextmanager
def playing(*, bridge_path, mode, start_beat, track_id=None, clip_id=None,
            launch_quantization=None, timeout=5):
    """Start stopped Live, yield for caller timing, then stop and verify completion.

    mode is 'arrangement' or 'session'. Session requires exact track/clip IDs and a
    native quantization name such as 'q_no_q' or 'q_bar'. Quantization is set on the
    clip; Live11 Clip.fire takes no keyword arguments. This is real-time transport,
    with no sample-accurate onset promise. Use an owned/stopped performance workspace.
    """
    if mode not in ('arrangement', 'session'):
        raise ValueError('Choose arrangement or session explicitly')
    for value in (start_beat, timeout):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('start_beat and timeout must be finite')
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    if mode == 'session':
        if any(not isinstance(v, str) or not v for v in (track_id, clip_id, launch_quantization)):
            raise ValueError('Session requires track_id, clip_id and launch_quantization')
    elif any(v is not None for v in (track_id, clip_id, launch_quantization)):
        raise ValueError('Clip/launch choices apply to session playback')
    if ableton.read(bridge_path=bridge_path, timeout=timeout)['is_playing']:
        raise RuntimeError('Transport is already playing; inspect before starting another performance')

    def stop():
        ableton.execute('song.stop_playing()', bridge_path=bridge_path, timeout=timeout)
        _wait(bridge_path, False, timeout)

    with cleanup(stop, 'Transport stop completion unknown; inspect Live'):
        ableton.execute('''
assert not song.is_playing, 'Transport changed; inspect again'
if args['mode']=='session':
    t=state.track(args['track'])
    matches=[s.clip for s in t.clip_slots if s.has_clip and str(s.clip._live_ptr)==args['clip']]
    assert len(matches)==1, 'Session clip changed; inspect again'
    c=matches[0]
    q=getattr(Live.Song.Quantization,args['quantization'])
    c.launch_quantization=q
song.current_song_time=args['start']
if args['mode']=='arrangement':song.back_to_arranger=False
song.start_playing()
if args['mode']=='session':c.fire()
''', bridge_path=bridge_path, timeout=timeout,
            args={'mode': mode, 'track': track_id, 'clip': clip_id,
                  'quantization': launch_quantization, 'start': start_beat})
        _wait(bridge_path, True, timeout)
        yield
