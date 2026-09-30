"""Authored loop-body boundaries and explicit channel/master outputs.

Synthetic source includes a marked tail. phrase() selects only complete windows inside
the declared body; it owns a copy. These are work-local patterns, not a Tactus slicing API.
"""

import numpy as np

from tactus import dsp, timing


def phrase(
    source: np.ndarray, *, body_end: int, starts: tuple[int, ...], frames: int, index: int
) -> np.ndarray:
    """Select a full window from authored frame starts; body_end is exclusive."""
    if not 0 < body_end <= len(source) or frames <= 0 or not starts:
        raise ValueError("declare a valid body, positive phrase length and source starts")
    if any(start < 0 or start + frames > body_end for start in starts):
        raise ValueError("every source phrase must fit completely inside the loop body")
    start = starts[index % len(starts)]
    return source[start : start + frames].copy()


def render(*, master_gain_db: float = -3.0) -> dict:
    sample_rate = 8000
    # Frame positions are authored once, independently of the file's tail duration.
    beat_frames = tuple(timing.frame_of(beat * 60 / 120, sample_rate) for beat in range(9))
    body_end = beat_frames[-1]
    t = np.arange(body_end) / sample_rate
    body = 0.12 * np.sin(2 * np.pi * 220 * t)
    tail = np.full(1900, 0.75)  # Deliberately unrelated to the beat grid.
    source = np.concatenate((body, tail))
    windows = (beat_frames[0], beat_frames[2], beat_frames[4], beat_frames[6])
    phrase_frames = beat_frames[2]
    loop = np.concatenate(
        [phrase(source, body_end=body_end, starts=windows, frames=phrase_frames, index=i)
         for i in range(8)]
    )
    left = dsp.fade(loop, sample_rate, in_s=0.01, out_s=0.05)
    channel_a = np.column_stack((left, 0.7 * left))
    channel_b = dsp.gain(np.column_stack((0.7 * left, left)), -6.0)
    pre_master = channel_a + channel_b
    mix = dsp.gain(pre_master, master_gain_db)
    return {
        "sample_rate": sample_rate,
        "outputs": {
            "channel_a_post": channel_a,
            "channel_b_post": channel_b,
            "pre_master": pre_master,
            "mix": mix,
        },
    }
