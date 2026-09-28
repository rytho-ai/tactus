"""Render OB-Xf in one fresh process with explicit controls; no stage cache."""

import argparse
import ctypes
from pathlib import Path

import numpy as np
import pedalboard

from tactus import fx


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--plugin", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--zero-slop", action="store_true")
    p.add_argument("--c-seed", type=int)
    a = p.parse_args()
    if a.c_seed is not None:
        ctypes.CDLL(None).srand(ctypes.c_uint(a.c_seed))
    synth = pedalboard.load_plugin(str(a.plugin.resolve()))
    for name, value, unit in [
        ("amp_env_attack_ms", 1800, "ms"),
        ("amp_env_release_ms", 2600, "ms"),
        ("amp_env_sustain", 100, "%"),
        ("filter_cutoff_hz", 4000, "Hz"),
        ("filter_resonance", 8, "%"),
        ("osc_2_volume", -7, "dB"),
        ("osc_2_detune_cents", 6, "cents"),
        ("volume", 70, "%"),
        ("polyphony_voices", 16, "Voices"),
    ]:
        fx.set_param(synth, name, value, unit=unit)
    if a.zero_slop:
        for name in ["envelope_slop", "filter_slop", "glide_slop", "level_slop"]:
            fx.set_param(synth, name, 0, unit="%")
    notes = [57, 60, 64, 67]
    messages = [(bytes([0x90, n, 38]), i * 0.15) for i, n in enumerate(notes)]
    messages += [(bytes([0x80, n, 0]), 2.0) for n in notes]
    audio = fx.render_instrument(synth, messages, duration=5, sample_rate=44100)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    np.save(a.out, audio, allow_pickle=False)


if __name__ == "__main__":
    main()
