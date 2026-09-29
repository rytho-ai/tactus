"""Frozen source observations control time and then timbre in destination coordinates.

Reads pinned source/report via decisions.py, written by prepare.py. No estimator runs
in render. The inverse marker map carries a source envelope through a nonuniform warp.
"""

import json

import numpy as np
import pytimestretch as pts
import soundfile as sf
from decisions import DECISION, SOURCE

from tactus import dsp, material


def output_envelope(report, output_frames):
    markers = np.asarray(report["markers"], dtype=np.int64)
    source_frames = np.interp(np.arange(output_frames), markers[:, 1], markers[:, 0])
    curve = report["curve"]
    amplitude = [0 if x is None else 10 ** (x / 20) for x in curve["rms_dbfs"]]
    return np.interp(source_frames / report["sample_rate"], curve["times_s"], amplitude)


def render(*, brightness=1.0):
    if not np.isfinite(brightness) or not 0 <= brightness <= 2:
        raise ValueError("brightness must be between 0 and 2")
    audio, rate = sf.read(material(SOURCE), dtype="float32")
    report = json.loads(material(DECISION).read_text())
    if (report["source_ref"], report["sample_rate"], report["source_frames"]) != (
        SOURCE,
        rate,
        len(audio),
    ):
        raise ValueError("decision belongs to another source")
    markers = np.asarray(report["markers"], dtype=np.int64)
    warped = pts.time_warp(audio, rate, markers=markers, backend="rubberband", quality="high")
    envelope = output_envelope(report, len(warped))
    normalized = envelope / max(float(envelope.max()), 1e-12)
    cutoff = 450 + 2800 * brightness * normalized
    shaped = dsp.lowpass(warped, rate, cutoff_hz=cutoff)
    return {"sample_rate": rate, "outputs": {"source": audio, "warped": warped, "mix": shaped}}
