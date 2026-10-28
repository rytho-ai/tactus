"""Bounded internal overlap keeps the public whole-clip waveshaper definition."""
import numpy as np
import pytest
from scipy.signal import resample_poly

from tactus import dsp


@pytest.mark.parametrize('oversample', [2, 4, 8, 16])
@pytest.mark.parametrize('curve', ['tanh', 'clip', 'fold'])
@pytest.mark.parametrize('channels', [None, 2])
def test_internal_overlap_matches_whole_clip(monkeypatch, oversample, curve, channels):
    monkeypatch.setattr(dsp, '_SATURATION_BLOCK', 257)
    x = np.random.default_rng(13).normal(0, .3, (1027,) if channels is None else (1027, channels))
    # Probe the joins as well as global clip edges and time-varying controls.
    x[256:259] = 3
    x[[0, -1]] = -2
    original = x.copy()
    drive = np.linspace(2., 18., len(x))
    mix = np.linspace(0., 1., len(x))
    frames = x[:, None] if x.ndim == 1 else x
    up = resample_poly(frames, oversample, 1, axis=0, window=('kaiser', 8.6))
    gain = np.interp(np.arange(len(up)) / oversample, np.arange(len(x)), 10 ** (drive / 20))[:, None]
    wet = resample_poly(dsp._CURVES[curve](up * gain), 1, oversample, axis=0,
                        window=('kaiser', 8.6))[:len(x)]
    reference = (1-mix[:, None]) * frames + mix[:, None] * wet
    actual = dsp.saturate(x, 48000, drive_db=drive, mix=mix, oversample=oversample, curve=curve)
    np.testing.assert_allclose(actual, reference[:, 0] if x.ndim == 1 else reference, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(x, original)
