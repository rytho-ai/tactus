"""A work-owned analysis, usable from Python or `tactus analyze stereo width`."""

import numpy as np


def width(audio, sample_rate, *, window_ms: float = 100.0, curve: bool = False):
    """Measure side/mid RMS ratio; optionally attach the per-window ratio curve.

    Stereo only. Mid = (L + R)/2, side = (L - R)/2. Ratios are linear,
    not percentages. Zero-mid windows are NaN in the curve and excluded from the mean.
    A partial final window is included. This measures energy, not perceived width.
    """
    if audio.ndim != 2 or audio.shape[1] != 2:
        raise ValueError("width requires stereo audio")
    frames = round(window_ms * sample_rate / 1000)
    if frames < 1:
        raise ValueError("window_ms must span at least one frame")
    mid = (audio[:, 0] + audio[:, 1]) / 2
    side = (audio[:, 0] - audio[:, 1]) / 2
    ratios = []
    for start in range(0, len(audio), frames):
        m = np.sqrt(np.mean(mid[start : start + frames] ** 2))
        s = np.sqrt(np.mean(side[start : start + frames] ** 2))
        ratios.append(float(s / m) if m else np.nan)
    finite = [r for r in ratios if np.isfinite(r)]
    result = {"mean_ratio": float(np.mean(finite)) if finite else None, "windows": len(ratios)}
    if curve:
        result["ratios"] = np.asarray(ratios)
    return result
