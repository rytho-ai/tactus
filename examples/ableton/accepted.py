"""Continue a pinned native Live Set or replay its saved original arrays offline.

Capture/project rebuild uses an explicit dedicated Live workspace; real-time timing
and plugin regeneration are not sample-exact. Pin the resulting run for exact replay.
"""

import math

from project import render_project

from tactus import load_render


def render(*, project_ref=None, audio_ref=None, bridge_path=None, live_binary=None,
           tap=None, tap_browser_path=None, seconds=8, gain=1., replace_active_set=False):
    if type(gain) not in (int, float) or not math.isfinite(gain):
        raise ValueError('gain must be finite')
    if audio_ref:
        saved = load_render(audio_ref, outputs=['mix'])
        audio, rate = saved.outputs['mix'], saved.sample_rate
    else:
        if not all((project_ref, bridge_path, live_binary, tap, tap_browser_path)):
            raise ValueError('Supply a native project/workspace/tap, or audio_ref')
        audio, rate = render_project(project_ref, bridge_path=bridge_path,
                                    live_binary=live_binary, tap=tap,
                                    tap_browser_path=tap_browser_path, seconds=seconds,
                                    replace_active_set=replace_active_set)
    return {'sample_rate': rate, 'outputs': {'mix': audio * gain}}
