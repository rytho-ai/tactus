"""Compare the reusable offline effects and combine them in an ordinary render.

The source is synthesized here so this example needs no external assets. Each effect
processes the same source independently; the mix is a deliberate example arrangement.
Reads: NumPy, tactus.dsp. Outputs: dry, ducked, echo, filtered, driven and mix WAVs.
"""

import numpy as np

from tactus import dsp


def render(*, drive_db=12.0, delay_seconds=0.16):
    sr = 48000
    t = np.arange(4 * sr) / sr
    notes = np.array([220.0, 261.6256, 329.6276, 293.6648])
    frequency = notes[(t // 0.5).astype(int) % len(notes)]
    phase = np.cumsum(frequency) / sr
    tone = sum(np.sin(2 * np.pi * k * phase) / k for k in range(1, 8))
    pulse = np.exp(-(t % 0.5) / 0.2)
    dry = dsp.pan(dsp.fade(0.16 * tone * (0.3 + 0.7 * pulse), sr, in_s=0.01, out_s=0.08))
    detector = np.exp(-(t % 0.5) / 0.05) * np.sin(2 * np.pi * 65 * t)

    ducked, gain = dsp.duck(dry, detector, sr, return_gain=True)
    # The curve can be applied unchanged to any same-length program signal.
    assert np.allclose(ducked, dry * gain[:, None])
    echo = dsp.delay(
        dry,
        sr,
        delay_seconds=delay_seconds + 0.03 * np.sin(2 * np.pi * 0.5 * t),
        feedback=0.35,
        tail_seconds=0.75,
    )
    filtered = dsp.lowpass(dry, sr, cutoff_hz=np.geomspace(250, 7000, len(dry)))
    driven = dsp.saturate(dry, sr, drive_db=drive_db, mix=np.linspace(0.15, 0.65, len(dry)))
    mix = echo * 0.25
    mix[: len(dry)] += 0.45 * ducked + 0.2 * filtered + 0.2 * driven
    return {
        "sample_rate": sr,
        "outputs": {
            "dry": dry,
            "ducked": ducked,
            "echo": echo,
            "filtered": filtered,
            "driven": driven,
            "mix": mix,
        },
    }
