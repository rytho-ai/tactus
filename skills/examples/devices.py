"""Three devices in one small work: a sampler melody, a chopped break on pads, a step-sequenced kit.

The "recordings" are synthesized here so the example needs no material; in a real work
they would be audio loaded with `tactus.load_audio`. Every pattern, slice order, root,
loop and level below is this example's choice. Import the devices as shown, or copy
`tactus/devices/sampler.py` (or pads, steps) into a work and change it.
"""

import numpy as np

from tactus import dsp, synth
from tactus.devices import pads, sampler, steps

SR = 48000
BPM = 96
BAR_S = 4 * 60 / BPM
FRAMES = round(4 * BAR_S * SR)


def recorded_note():
    """Stand-in for a sampled instrument note: a plucked string at A3 (MIDI 57)."""
    burst = synth.noise(round(SR / 220), seed=7)
    return synth.pluck(220.0, SR, excitation=burst - burst.mean(), frames=2 * SR, decay_s=4.0, brightness=0.7)


def recorded_break():
    """Stand-in for a one-bar drum loop at this tempo: kick, snare and hats on eighths."""
    out = np.zeros(round(BAR_S * SR))
    t = np.arange(round(0.25 * SR)) / SR
    kick = np.sin(2 * np.pi * (45 * t + 60 * 0.03 * (1 - np.exp(-t / 0.03)))) * np.exp(-t / 0.09)
    snare = synth.noise(len(t), seed=3) * np.exp(-t / 0.05) + 0.5 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.04)
    hat = dsp.svf(synth.noise(len(t), seed=5), SR, mode="highpass", cutoff_hz=7000) * np.exp(-t / 0.02)
    for eighth, sound, level in [(0, kick, 1.0), (2, snare, 0.7), (3, kick, 0.8), (5, kick, 0.9), (6, snare, 0.7)]:
        start = round(eighth * BAR_S / 8 * SR)
        out[start : start + len(sound)] += sound * level
    for eighth in range(8):
        start = round(eighth * BAR_S / 8 * SR)
        out[start : start + len(hat)] += hat * 0.25
    return out


def render(*, swing=0.56, chop_order="0 0 3 2 4 6 3 7"):
    order = [int(i) for i in chop_order.split()]
    # Sampler: one recorded note played as a melody, sustained by a loop.
    note = recorded_note()
    melody_notes = steps.notes("x..x ..x. x... x.x.", [57, 60, 64, 62, 57, 69], bpm=BPM, repeats=4, gate=2.5)
    melody = sampler.play(note, SR, melody_notes, frames=FRAMES, root=57, loop=(0.3, 0.3 + 44 / 220), release_s=0.25)

    # Pads: cut a break into eighths, then trigger the slices in a new order.
    parts = pads.slices(recorded_break(), SR, count=8)
    kit = {f"s{i}": part for i, part in enumerate(parts)}
    chop_hits = [
        (bar * BAR_S + i * BAR_S / 8, f"s{index}", 0.9)
        for bar in range(4)
        for i, index in enumerate(order if bar % 2 == 0 else order[::-1])
    ]
    chopped = pads.play(chop_hits, kit, SR, frames=FRAMES, choke="break")

    # Steps: a swung hat line on two pads that choke each other.
    t = np.arange(round(0.4 * SR)) / SR
    tick = dsp.svf(synth.noise(len(t), seed=11), SR, mode="highpass", cutoff_hz=8000)
    hats = {"closed": tick * np.exp(-t / 0.015), "open": tick * np.exp(-t / 0.15)}
    hat_hits = steps.hits("x.xx x.x. x.xx x...", "closed", bpm=BPM, repeats=4, swing=swing)
    hat_hits += steps.hits(".... .... .... ..X.", "open", bpm=BPM, repeats=4, swing=swing)
    hat_line = pads.play(hat_hits, hats, SR, frames=FRAMES, choke={"closed": "hat", "open": "hat"})

    outputs = {
        "melody": dsp.pan(melody * 0.5, -0.2),
        "break": dsp.pan(chopped * 0.6, 0.0),
        "hats": dsp.pan(hat_line * 0.25, 0.3),
    }
    outputs["mix"] = sum(outputs.values())
    return {"sample_rate": SR, "outputs": outputs}
