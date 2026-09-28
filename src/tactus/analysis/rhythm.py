"""rhythm: estimated beat times and tempo via pyqmdsp's direct qm-dsp binding.

Input uses Tactus's (frames,) or (frames, channels) layout. pyqmdsp averages channels
to mono and analyzes at the supplied sample rate. This module only converts results
to JSON-ready values; pyqmdsp owns framing, algorithm defaults and time conversion.
No Vamp host or separate native build is needed.

These are estimates, not a bar grid or downbeat detector. Analyze outside render and
freeze accepted results as material or source constants before using them for cuts.
ANALYSES supplies the functions for the generated CLI; revision marks result semantics.

Reads: numpy (annotations) · pyqmdsp · _revision
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pyqmdsp

from ._revision import revision as _revision


@_revision(1)
def beats(audio: np.ndarray, sample_rate: int) -> dict[str, Any]:
    """Estimate beat times using qm-dsp's DetectionFunction and TempoTrackV2.

    Channels are averaged to mono, without resampling or normalization. Short material
    (roughly 7.45 seconds or less of active audio) and silence return empty arrays and
    null BPM: the tracker needs more than 640 detection-function frames after trimming.
    Empty/nonfinite audio and invalid dimensions or sample rates raise ValueError.
    Beat estimates carry no confidence, meter or downbeat position.

    Returns:
        beats_s (seconds): estimated beat times relative to the audio start, earliest first.
        bpm (BPM): median instantaneous tempo, null if fewer than two beats were found.
        tempo_curve (BPM): 60 / (beats_s[i+1] - beats_s[i]) for each consecutive beat pair;
            one value shorter than beats_s, or empty if fewer than two beats were found.
    """
    result = pyqmdsp.beats(audio, sample_rate)
    return {
        "beats_s": result["beats_s"].tolist(),
        "bpm": result["bpm"] if len(result["beats_s"]) >= 2 else None,
        "tempo_curve": result["tempo_curve"].tolist(),
    }


ANALYSES = (beats,)
