"""Texture from existing audio: a granular pad and a spectral-freeze riser.

Grain timing, positions, rates and pans come from a seeded generator this example owns;
the freeze frame and upward drift are choices of its `dsp.spectral` transform. The
source is synthesized here so the example needs no material; any mono audio works.
"""

import numpy as np

from tactus import dsp, synth

SR = 48000
CHORD = [50, 57, 62, 65, 69]


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def source_chord(seconds):
    frames = round(seconds * SR)
    tone = sum(synth.triangle(hz(m), SR, frames=frames, phase=0.17 * i) for i, m in enumerate(CHORD))
    breath = synth.noise(frames, seed=5, color="pink") * 0.3
    return dsp.svf(tone / len(CHORD) + breath, SR, mode="lowpass", cutoff_hz=3000, q=1.2)


def grain_pad(source, seconds, *, density, spread_s, seed):
    rng = np.random.Generator(np.random.PCG64(seed))
    count = int(density * seconds)
    onsets = np.sort(rng.uniform(0, seconds - 0.2, count))
    centre = np.linspace(0.5, len(source) / SR - 1.0, count)
    return synth.grains(
        source,
        SR,
        onsets_s=onsets,
        positions_s=np.clip(centre + rng.normal(0, spread_s, count), 0, None),
        durations_s=rng.uniform(0.08, 0.2, count),
        rate=2 ** (rng.choice([0, 0, 12, -12, 7], count) / 12),
        gain=rng.uniform(0.2, 0.5, count),
        pan=rng.uniform(-0.8, 0.8, count),
        frames=round(seconds * SR),
    )


def frozen_riser(source, *, freeze_frame, drift_octaves):
    held = {}
    frames = -(-(len(source) + 2048) // 512) + 1

    def freeze(magnitude, frequency, index):
        if index <= freeze_frame:
            held["mag"], held["freq"] = magnitude, frequency
            return magnitude, frequency
        rise = 2 ** (drift_octaves * (index - freeze_frame) / max(1, frames - freeze_frame))
        return held["mag"], np.minimum(held["freq"] * rise, SR / 2)

    frozen = dsp.spectral(source, SR, freeze, n_fft=2048, hop=512)
    swell = synth.envelope(0.0, [(len(source) / SR, 1.0, 3)], SR, frames=len(source))
    cutoff = synth.envelope(300.0, [(len(source) / SR, 12000.0, 2)], SR, frames=len(source))
    return dsp.svf(frozen, SR, mode="lowpass", cutoff_hz=cutoff, q=1.5) * swell


def render(*, density=40.0, spread_s=0.3, freeze_frame=40, drift_octaves=1.0, seed=17):
    seconds = 6.0
    source = source_chord(seconds)
    pad = grain_pad(source, seconds, density=density, spread_s=spread_s, seed=seed) * 0.35
    riser = dsp.pan(frozen_riser(source, freeze_frame=freeze_frame, drift_octaves=drift_octaves))
    return {"sample_rate": SR, "outputs": {"grain_pad": pad, "riser": riser, "mix": pad + riser}}
