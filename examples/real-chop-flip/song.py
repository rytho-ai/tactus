"""Eight-bar real-source chop-flip study through the functional render entry.

The sample, rhythms, processing and mix are this work's choices. Tactus only
executes and exports. A bass-gain override creates an unaccepted audition candidate.
"""

import numpy as np
from chops import sample_part
from materials import source_bars
from rhythm import bass, drums

BPM = 90
MASTER_GAIN = 1.5


def render(*, bass_gain_db=-5.0):
    bars, rate, _ = source_bars()
    beat = round(rate * 60 / BPM)
    frames = 8 * 4 * beat + rate  # One second for the authored delay/filter tails.
    sample = sample_part(bars, rate, beat, frames) * 10 ** (-7.0 / 20)
    percussion = drums(rate, beat, frames) * 10 ** (-7.0 / 20)
    low = bass(rate, beat, frames) * 10 ** (bass_gain_db / 20)
    # Fixed headroom preserves the relationship across parameter candidates.
    outputs = {
        "sample": sample * MASTER_GAIN,
        "drums": percussion * MASTER_GAIN,
        "bass": low * MASTER_GAIN,
    }
    outputs["mix"] = outputs["sample"] + outputs["drums"] + outputs["bass"]
    for name, audio in outputs.items():
        audio[-round(0.08 * rate) :] *= np.linspace(1, 0, round(0.08 * rate))[:, None]
        outputs[name] = audio.astype(np.float32)
    return {"sample_rate": rate, "outputs": outputs}
