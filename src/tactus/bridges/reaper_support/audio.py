"""Render authored native Lua in a private tab and return verified decoded audio.

Owns scratch lifetime, native render completion and WAV validation. Caller chooses
the entire native setup, duration, rate and channels; no gain, trimming or silence
test is applied. Reads: packaged render.lua; inputs.tool; SoundFile/NumPy.
"""

import math
import shutil
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from tactus import tool
from tactus.bridges import reaper


def render(code, *, resource_path, reaper_bundle, seconds, sample_rate, channels,
           args=None, timeout=120):
    """Execute setup Lua once in a fresh project, render [0, seconds), restore tab.

    Setup sees ordinary ``args`` and ``reaper.*``. It may open a writable project
    copy, or create tracks/FX/MIDI. It must stay in its owned tab. Returns a
    frames-first array decoded from native PCM24, including a column for mono. Timeout is not cancellation:
    scratch/private tab remain on failure; inspect before retrying. Full offline
    rendering occupies REAPER's main thread. No automatic rollback or retry.
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError('code must be nonempty Lua source')
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('seconds must be finite and positive')
    if type(sample_rate) is not int or sample_rate <= 0:
        raise ValueError('sample_rate must be a positive integer')
    if type(channels) is not int or channels not in (1, 2):
        raise ValueError('channels must be 1 or 2')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive')
    reaper._literal(args)  # Reject unsupported data before allocating scratch/contacting DAW.
    tool(reaper_bundle)
    lua = tool(str(Path(__file__).with_name('render.lua')))
    scratch = Path(tempfile.mkdtemp(prefix='tactus-reaper-render-'))
    try:
        reaper.execute(lua.read_text(), resource_path=resource_path, timeout=timeout,
                       args={'setup': code, 'data': args, 'seconds': seconds,
                             'rate': sample_rate, 'channels': channels, 'out': str(scratch)})
        audio, rate = sf.read(scratch / 'audio.wav', always_2d=True)
        if (rate != sample_rate or audio.shape != (round(seconds * sample_rate), channels)
                or not np.isfinite(audio).all()):
            raise ValueError('REAPER returned unexpected render audio; inspect scratch')
    except BaseException as exc:
        exc.add_note(f'REAPER scratch retained at {scratch}; inspect host/reply before cleanup')
        raise
    shutil.rmtree(scratch)
    return audio
