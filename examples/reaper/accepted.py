"""Continue accepted REAPER state in Tactus, or replay its chosen audio offline.

Pin a native project/media with project.py capture + tactus material add. Render
that project_ref with REAPER, then pin the selected mix and put its audio_ref in
source to continue with REAPER stopped. gain is an explicit Tactus revision.
"""

import numpy as np
import soundfile as sf

from tactus import material
from tactus.bridges.reaper_support.project import render_project


def render(*, project_ref=None, audio_ref=None, resource_path=None, reaper_bundle=None,
           seconds=8, sample_rate=24000, gain=1.0):
    if audio_ref:
        audio, rate = sf.read(material(audio_ref), always_2d=True)
        if rate != sample_rate or audio.shape != (round(seconds * sample_rate), 2):
            raise ValueError('Pinned audio does not match the requested range/rate')
    else:
        if not project_ref or not resource_path or not reaper_bundle:
            raise ValueError('Pass project_ref/resource_path/reaper_bundle, or audio_ref')
        audio = render_project(project_ref, resource_path=resource_path,
                               reaper_bundle=reaper_bundle, seconds=seconds,
                               sample_rate=sample_rate)
    if not np.isfinite(gain):
        raise ValueError('gain must be finite')
    return {'sample_rate': sample_rate, 'outputs': {'mix': audio * gain}}
