"""Excitation plus resonance: struck metal from a modal bank and a plucked-string line.

The mode ratios, decays, excitation bursts and string brightness are this example's
choices. Replace the ratios with measured or invented ones; any excitation works.
"""

import numpy as np

from tactus import dsp, synth

SR = 48000
BAR_RATIOS = [1.0, 2.756, 5.404, 8.933, 13.34]  # free-bar modes, stretched slightly below
PLUCKS = [(0.0, 45), (0.25, 52), (0.5, 57), (0.75, 59), (1.0, 60), (1.5, 57), (2.0, 55), (2.5, 52)]


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def metal_hit(fundamental, *, seed, stretch, decay_s, seconds=1.5):
    frames = round(seconds * SR)
    burst = synth.noise(frames, seed=seed) * synth.envelope(1.0, [(0.004, 0.0, -6)], SR, frames=frames)
    ratios = np.array(BAR_RATIOS) ** stretch
    freqs = fundamental * ratios
    keep = freqs < SR * 0.45
    return synth.resonators(
        burst,
        SR,
        freqs_hz=freqs[keep],
        decays_s=decay_s / np.sqrt(ratios[keep]),
        gains=1.0 / ratios[keep],
    )


def string_note(freq, *, seed, brightness, decay_s, seconds=1.2):
    burst = synth.noise(round(SR / freq), seed=seed)
    burst = dsp.svf(burst - burst.mean(), SR, mode="lowpass", cutoff_hz=2000 + 6000 * brightness)
    return synth.pluck(freq, SR, excitation=burst, frames=round(seconds * SR), decay_s=decay_s, brightness=brightness)


def render(*, stretch=0.97, metal_decay_s=1.2, brightness=0.55, string_decay_s=1.6):
    total = round(4.0 * SR)
    metal = np.zeros(total)
    for i, (beat, midi) in enumerate([(0.5, 62), (1.5, 65), (2.5, 62), (3.25, 69)]):
        hit = metal_hit(hz(midi), seed=100 + i, stretch=stretch, decay_s=metal_decay_s)
        start = round(beat * SR)
        end = min(total, start + len(hit))
        metal[start:end] += hit[: end - start]
    strings = np.zeros(total)
    for i, (beat, midi) in enumerate(PLUCKS):
        note = string_note(hz(midi), seed=200 + i, brightness=brightness, decay_s=string_decay_s)
        start = round(beat * SR)
        end = min(total, start + len(note))
        strings[start:end] += note[: end - start]
    metal_out = dsp.pan(metal * 0.12, 0.35)
    string_out = dsp.pan(strings * 0.3, -0.3)
    return {
        "sample_rate": SR,
        "outputs": {"metal": metal_out, "strings": string_out, "mix": metal_out + string_out},
    }
