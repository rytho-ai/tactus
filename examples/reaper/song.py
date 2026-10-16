"""A REAPER lead plus NumPy bass/drums; Lua owns native DAW instructions.

Pass resource_path and reaper_bundle to generate a phrase. Use lead_ref to replay
accepted audio independently of REAPER. The eight-second outputs share zero origin.
"""

import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from tactus import material, tool
from tactus.bridges import reaper

RATE, FRAMES = 24000, 192000


def daw_lead(resource_path, reaper_bundle, transpose):
    tool(reaper_bundle)
    lua = tool(str(Path(__file__).with_name("instrument.lua")))
    notes = [
        (
            (i % 4) * 0.5 + 0.25 + (4 if i >= 4 else 0),
            pitch + (transpose if i >= 4 else 0),
            0.3125,
            90,
        )
        for i, pitch in enumerate([62, 65, 69, 67, 62, 65, 72, 69])
    ]
    with tempfile.TemporaryDirectory(prefix="tactus-reaper-") as directory:
        reaper.execute(
            lua.read_text(),
            resource_path=resource_path,
            args={"notes": notes, "rate": RATE, "seconds": FRAMES / RATE, "out": directory},
            timeout=60,
        )
        audio, rate = sf.read(Path(directory) / "lead.wav", always_2d=True)
    if rate != RATE or audio.shape != (FRAMES, 2) or not np.isfinite(audio).all():
        raise ValueError("REAPER returned unexpected audio")
    return audio


def render(*, resource_path=None, reaper_bundle=None, lead_ref=None, transpose=0):
    if lead_ref:
        lead, rate = sf.read(material(lead_ref), always_2d=True)
        if rate != RATE or lead.shape != (FRAMES, 2):
            raise ValueError("Pinned lead must be 8 seconds, stereo, 24 kHz")
    else:
        if not resource_path or not reaper_bundle:
            raise ValueError("Pass resource_path and reaper_bundle, or a pinned lead_ref")
        lead = daw_lead(resource_path, reaper_bundle, transpose)
    time = np.arange(FRAMES) / RATE
    bass = 0.1 * np.sin(2 * np.pi * 73.41619198 * time)
    bass *= (1 - np.exp(-(time % 0.5) / 0.008)) * np.exp(-(time % 0.5) / 0.12)
    drums = np.random.default_rng(42).uniform(-1, 1, FRAMES)
    drums *= 0.025 * np.exp(-(time % 0.25) / 0.012)
    bass, drums = np.column_stack([bass, bass]), np.column_stack([drums, drums])
    return {
        "sample_rate": RATE,
        "outputs": {"lead": lead, "bass": bass, "drums": drums, "mix": lead + bass + drums},
        "map": {
            "outputs": {
                "mix": {
                    "lanes": {
                        "sections": {
                            "kind": "points",
                            "items": [{"at": 0, "label": "A"}, {"at": 96000, "label": "B"}],
                        }
                    }
                }
            }
        },
    }
