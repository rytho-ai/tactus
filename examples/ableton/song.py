"""Borrow an already loaded Max host/tap, then pin its audio for host-free replay.

Copy into a Tactus work. Supply the generated device.json objects and the exact
owned track ID. This example intentionally uses a continuous oscillator: its first
four captured seconds define the excerpt, with no claim of transport/sample sync.
"""

import math
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from tactus import load_render, material, tool
from tactus.bridges import ableton
from tactus.bridges.ableton_support import audio, max

SECONDS = 4


def live_voice(bridge_path, live_binary, track_id, host, tap, frequency):
    tool(live_binary)
    ableton.execute('''
t = next(t for t in song.tracks if str(t._live_ptr) == args['track'])
assert not song.is_playing, 'Stop transport for this fixture recipe'
assert not t.mute and t.current_monitoring_state == 0, 'Fixture must process audio'
assert t.output_routing_type.display_name == 'Sends Only', 'Use an inaudible fixture'
assert [d.name for d in t.devices] == args['devices'], 'Fixture devices changed'
assert all(d.is_active for d in t.devices), 'Activate fixture devices'
''', bridge_path=bridge_path, args={'track': track_id,
         'devices': [host['name'], Path(tap['amxd_path']).stem]})
    buses = host['audio_buses']
    patch = {
        'objects': [{'id': 'tone', 'object': 'cycle~', 'args': [frequency]},
                    {'id': 'gain', 'text': '*~ 0.05'},
                    {'id': 'left', 'object': 'send~', 'args': [buses['output_left']]},
                    {'id': 'right', 'object': 'send~', 'args': [buses['output_right']]}],
        'connections': [{'from': 'tone', 'to': 'gain'},
                        {'from': 'gain', 'to': 'left'}, {'from': 'gain', 'to': 'right'}],
    }
    reply = max.command(host, {'command': 'update', 'patch': patch})
    if reply.get('connection_errors'):
        raise ValueError(f'Max graph did not connect: {reply}')
    # Live's real-time audio clock owns the take. The accepted WAV owns replay.
    captured, rate = audio.capture(tap, lambda: time.sleep(SECONDS + .2))
    frames = round(SECONDS * rate)
    if captured.shape[1] != 2 or len(captured) < frames:
        raise ValueError('Unexpected Live excerpt length/layout')
    voice = captured[:frames].copy()
    if not np.any(voice):
        raise ValueError('This oscillator work expects audible audio; inspect routing/DSP')
    return voice, rate


def render(*, bridge_path=None, live_binary=None, track_id=None, host=None, tap=None,
           voice_ref=None, frequency=220):
    if not isinstance(frequency, (int, float)) or not math.isfinite(frequency) or frequency <= 0:
        raise ValueError('frequency must be finite and positive')
    if voice_ref:
        if voice_ref.startswith('tree:sha256:'):
            saved = load_render(voice_ref, outputs=['voice'])
            voice, rate = saved.outputs['voice'], saved.sample_rate
        else:
            voice, rate = sf.read(material(voice_ref), always_2d=True)
        if voice.shape != (SECONDS * rate, 2):
            raise ValueError('Pinned voice must be four seconds, stereo')
    else:
        if not all((bridge_path, live_binary, track_id, host, tap)):
            raise ValueError('Supply bridge_path/live_binary/track_id/host/tap, or voice_ref')
        voice, rate = live_voice(bridge_path, live_binary, track_id, host, tap, frequency)
    t = np.arange(len(voice)) / rate
    pulse = (1 - np.exp(-(t % .5) / .008)) * np.exp(-(t % .5) / .14)
    lead = voice * pulse[:, None]
    bass = .07 * np.sin(2 * np.pi * 55 * t) * np.exp(-(t % .5) / .18)
    bass = np.column_stack((bass, bass))
    return {'sample_rate': rate, 'outputs': {'voice': voice, 'lead': lead, 'bass': bass,
                                            'mix': lead + bass}}
