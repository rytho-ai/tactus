"""Long-phrase chop arrangement, inspired by Music Agent OS lab/chop_flip.py.

Musical selection, filter, delay and tail are ordinary project-owned Python.
Rubber Band performs pitch-preserving stretch; no Tactus temporal API is needed here.
"""

import numpy as np
import pyrubberband as rubberband
from scipy.signal import butter, sosfilt

ORDER = (0, 1, 2, 3, 2, 3, 0, 3)


def warp(audio: np.ndarray, rate: int, frames: int) -> np.ndarray:
    stretched = rubberband.time_stretch(audio, rate, len(audio) / frames)
    if len(stretched) != frames:
        raise ValueError(f"stretch returned {len(stretched)} frames; expected {frames}")
    stretched = np.asarray(stretched, dtype=np.float32).copy()
    fade = min(round(0.004 * rate), frames // 2)
    stretched[:fade] *= np.linspace(0, 1, fade)[:, None]
    stretched[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return stretched


def sample_part(bars: list[np.ndarray], rate: int, beat: int, frames: int) -> np.ndarray:
    bar_frames = 4 * beat
    whole = [warp(audio, rate, bar_frames) for audio in bars]
    out = np.zeros((frames, 2), dtype=np.float32)
    for bar, selected in enumerate(ORDER[:7]):
        at = bar * bar_frames
        out[at : at + bar_frames] += whole[selected]
    # Last bar: half a phrase, two repetitions, then a reversed pickup.
    half = bars[3][: len(bars[3]) // 2]
    last = 7 * bar_frames
    out[last : last + 2 * beat] += warp(half, rate, 2 * beat)
    grain = bars[3][: len(bars[3]) // 4]
    for offset, gain in [(2.0, 0.8), (2.5, 0.7), (3.0, 0.7)]:
        at = last + round(offset * beat)
        out[at : at + beat // 2] += warp(grain, rate, beat // 2) * gain
    reverse = bars[0][: len(bars[0]) // 2][::-1].copy()
    at = last + round(3.5 * beat)
    out[at : at + beat // 2] += warp(reverse, rate, beat // 2) * 0.6

    # Make room for the separately authored bass; keep stereo placement intact.
    out = sosfilt(butter(2, 150, "highpass", fs=rate, output="sos"), out, axis=0)
    out = sosfilt(butter(2, 9000, "lowpass", fs=rate, output="sos"), out, axis=0)
    delayed = out.copy()
    for repeats, gain in [(1, 0.10), (2, 0.035)]:
        delay = round(beat * 0.75 * repeats)
        delayed[delay:] += out[:-delay, ::-1] * gain
    return delayed.astype(np.float32)
