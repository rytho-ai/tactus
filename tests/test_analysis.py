"""tactus.analysis measurements on synthetic cases with known answers."""

from __future__ import annotations

import math

import numpy as np
import pyloudnorm as pyln
import pytest

from tactus import analysis

SR = 48000


def sine(freq, sr, seconds, amp=1.0, phase=0.0):
    t = np.arange(int(sr * seconds)) / sr
    return (amp * np.sin(2 * np.pi * freq * t + phase)).astype(np.float64)


def stereo(mono, scale_r=1.0):
    return np.stack([mono, mono * scale_r], axis=1)


# -- sample_peak_dbfs --------------------------------------------------------------------------


def test_sample_peak_known_amplitude():
    x = stereo(sine(1000, SR, 1.0, amp=0.5))
    assert analysis.sample_peak_dbfs(x) == pytest.approx(20 * math.log10(0.5), abs=0.02)


def test_sample_peak_silence_is_neg_inf():
    x = np.zeros((1000, 2))
    assert analysis.sample_peak_dbfs(x) == -math.inf


def test_sample_peak_accepts_mono_1d_shape():
    x = sine(1000, SR, 1.0, amp=0.25)
    assert analysis.sample_peak_dbfs(x) == pytest.approx(20 * math.log10(0.25), abs=0.02)


# -- true_peak_dbtp: fs/4 sine, 45-degree phase overshoots sample peak by ~3 dB -----------------


def test_true_peak_fs4_overshoot():
    n = 4000
    tt = np.arange(n)
    tone = np.cos(np.pi / 2 * tt + np.pi / 4)  # samples all at +-cos(45deg) = +-0.7071
    x = stereo(tone)
    sp = analysis.sample_peak_dbfs(x)
    tp = analysis.true_peak_dbtp(x, SR)
    assert sp == pytest.approx(20 * math.log10(2**-0.5), abs=0.05)
    assert tp > sp + 2.5  # true peak overshoots the sample peak by ~3 dB


def test_true_peak_never_below_sample_peak():
    x = stereo(sine(300, SR, 0.5, amp=0.4))
    assert analysis.true_peak_dbtp(x, SR) >= analysis.sample_peak_dbfs(x) - 0.01


# -- integrated_lufs ------------------------------------------------------------------------


def test_lufs_matches_pyloudnorm_directly():
    x = stereo(sine(1000, SR, 3.0, amp=0.2), scale_r=0.95)
    meter = pyln.Meter(SR)
    want = meter.integrated_loudness(x)
    got = analysis.integrated_lufs(x, SR)
    assert got == pytest.approx(want, abs=1e-9)


def test_lufs_differs_from_rms_with_deep_bass():
    # K-weighting de-emphasizes deep bass: a 40 Hz tone reads quieter in LUFS than in RMS.
    x = stereo(sine(40, SR, 3.0, amp=0.5))
    lufs = analysis.integrated_lufs(x, SR)
    rms = analysis.rms_dbfs(x)
    assert lufs < rms - 1.0


def test_lufs_is_none_for_digital_silence():
    x = np.zeros((SR * 2, 2))
    assert analysis.integrated_lufs(x, SR) is None


def test_lufs_is_none_when_audio_too_short_to_gate():
    x = stereo(sine(1000, SR, 0.01, amp=0.3))  # far under a 400ms gating block
    assert analysis.integrated_lufs(x, SR) is None


# -- rms_dbfs ---------------------------------------------------------------------------------


def test_rms_of_full_scale_sine():
    x = stereo(sine(1000, SR, 1.0, amp=1.0))
    assert analysis.rms_dbfs(x) == pytest.approx(-3.0103, abs=0.01)


# -- flat_runs --------------------------------------------------------------------------------


def test_flat_runs_counts_exact_run():
    x = np.zeros((1000, 1))
    x[100:106, 0] = 0.9  # a run of exactly 6 identical samples above 0.5
    res = analysis.flat_runs(x, min_length=4, above=0.5)
    assert res["count"] == 1
    assert res["longest"] == 6
    assert res["first_positions"][0] == (0, 100, 6)


def test_flat_runs_at_min_length_is_counted():
    x = np.zeros((1000, 1))
    x[100:104, 0] = 0.9  # exactly 4 samples, at min_length=4
    res = analysis.flat_runs(x, min_length=4, above=0.5)
    assert res["count"] == 1
    assert res["longest"] == 4


def test_flat_runs_below_min_length_not_counted():
    x = np.zeros((1000, 1))
    x[100:103, 0] = 0.9  # only 3 samples, under min_length=4
    res = analysis.flat_runs(x, min_length=4, above=0.5)
    assert res["count"] == 0


def test_flat_runs_below_threshold_not_counted():
    x = np.zeros((1000, 1))
    x[100:110, 0] = 0.4  # identical run, but below `above`
    res = analysis.flat_runs(x, min_length=4, above=0.5)
    assert res["count"] == 0


# -- analyze() ------------------------------------------------------------------------------------


def test_analyze_returns_every_measurement_for_stereo():
    x = stereo(sine(1000, SR, 1.0, amp=0.5))
    result = analysis.analyze(x, SR)
    assert set(result) == {
        "sample_peak_dbfs",
        "true_peak_dbtp",
        "integrated_lufs",
        "rms_dbfs",
        "flat_runs",
    }


def test_analyze_accepts_mono_1d_shape():
    x = sine(1000, SR, 1.0, amp=0.5)
    result = analysis.analyze(x, SR)
    assert math.isfinite(result["rms_dbfs"])
