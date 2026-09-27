"""tactus.analysis measurements on synthetic cases with known answers, plus the cross-category
consistency contract every analysis must satisfy."""

from __future__ import annotations

import inspect
import math
import re

import numpy as np
import pyloudnorm as pyln
import pytest

from tactus import analysis
from tactus.analysis import level, spectral

SR = 48000


def sine(freq, sr, seconds, amp=1.0, phase=0.0):
    t = np.arange(int(sr * seconds)) / sr
    return (amp * np.sin(2 * np.pi * freq * t + phase)).astype(np.float64)


def stereo(mono, scale_r=1.0):
    return np.stack([mono, mono * scale_r], axis=1)


# -- level.sample_peak --------------------------------------------------------------------------


def test_sample_peak_known_amplitude():
    x = stereo(sine(1000, SR, 1.0, amp=0.5))
    assert level.sample_peak(x, SR)["sample_peak_dbfs"] == pytest.approx(
        20 * math.log10(0.5), abs=0.02
    )


def test_sample_peak_silence_is_neg_inf():
    x = np.zeros((1000, 2))
    assert level.sample_peak(x, SR)["sample_peak_dbfs"] == -math.inf


def test_sample_peak_accepts_mono_1d_shape():
    x = sine(1000, SR, 1.0, amp=0.25)
    assert level.sample_peak(x, SR)["sample_peak_dbfs"] == pytest.approx(
        20 * math.log10(0.25), abs=0.02
    )


# -- level.true_peak: fs/4 sine, 45-degree phase overshoots sample peak by ~3 dB ------------------


def test_true_peak_fs4_overshoot():
    n = 4000
    tt = np.arange(n)
    tone = np.cos(np.pi / 2 * tt + np.pi / 4)  # samples all at +-cos(45deg) = +-0.7071
    x = stereo(tone)
    sp = level.sample_peak(x, SR)["sample_peak_dbfs"]
    tp = level.true_peak(x, SR)["true_peak_dbtp"]
    assert sp == pytest.approx(20 * math.log10(2**-0.5), abs=0.05)
    assert tp > sp + 2.5  # true peak overshoots the sample peak by ~3 dB


def test_true_peak_never_below_sample_peak():
    x = stereo(sine(300, SR, 0.5, amp=0.4))
    assert (
        level.true_peak(x, SR)["true_peak_dbtp"]
        >= level.sample_peak(x, SR)["sample_peak_dbfs"] - 0.01
    )


# -- level.loudness -------------------------------------------------------------------------


def test_loudness_matches_pyloudnorm_directly():
    x = stereo(sine(1000, SR, 3.0, amp=0.2), scale_r=0.95)
    meter = pyln.Meter(SR)
    want = meter.integrated_loudness(x)
    got = level.loudness(x, SR)["integrated_lufs"]
    assert got == pytest.approx(want, abs=1e-9)


def test_loudness_differs_from_rms_with_deep_bass():
    # K-weighting de-emphasizes deep bass: a 40 Hz tone reads quieter in LUFS than in RMS.
    x = stereo(sine(40, SR, 3.0, amp=0.5))
    lufs = level.loudness(x, SR)["integrated_lufs"]
    rms = level.rms(x, SR)["rms_dbfs"]
    assert lufs < rms - 1.0


def test_loudness_is_none_for_digital_silence():
    x = np.zeros((SR * 2, 2))
    assert level.loudness(x, SR)["integrated_lufs"] is None


def test_loudness_is_none_when_audio_too_short_to_gate():
    x = stereo(sine(1000, SR, 0.01, amp=0.3))  # far under a 400ms gating block
    assert level.loudness(x, SR)["integrated_lufs"] is None


# -- level.rms ---------------------------------------------------------------------------------


def test_rms_of_full_scale_sine():
    x = stereo(sine(1000, SR, 1.0, amp=1.0))
    assert level.rms(x, SR)["rms_dbfs"] == pytest.approx(-3.0103, abs=0.01)


# -- level.clipping -----------------------------------------------------------------------------


def test_clipping_counts_exact_run():
    x = np.zeros((1000, 1))
    x[100:106, 0] = 0.9  # a run of exactly 6 identical samples above 0.5
    res = level.clipping(x, SR, min_length=4, above=0.5)
    assert res["count"] == 1
    assert res["longest"] == 6
    assert res["first_positions"][0] == (0, 100, 6)


def test_clipping_at_min_length_is_counted():
    x = np.zeros((1000, 1))
    x[100:104, 0] = 0.9  # exactly 4 samples, at min_length=4
    res = level.clipping(x, SR, min_length=4, above=0.5)
    assert res["count"] == 1
    assert res["longest"] == 4


def test_clipping_below_min_length_not_counted():
    x = np.zeros((1000, 1))
    x[100:103, 0] = 0.9  # only 3 samples, under min_length=4
    res = level.clipping(x, SR, min_length=4, above=0.5)
    assert res["count"] == 0


def test_clipping_below_threshold_not_counted():
    x = np.zeros((1000, 1))
    x[100:110, 0] = 0.4  # identical run, but below `above`
    res = level.clipping(x, SR, min_length=4, above=0.5)
    assert res["count"] == 0


# -- spectral.spectrum ----------------------------------------------------------------------------


def test_spectrum_bin_centred_full_scale_sine_reads_near_zero_db():
    x = sine(1000, SR, 1.0, amp=1.0)
    result = spectral.spectrum(x, SR, resolution_hz=1.0)
    freqs = np.array(result["freqs_hz"])
    level_db = np.array(result["level_db"])
    peak_db = level_db[np.argmin(np.abs(freqs - 1000))]
    assert peak_db == pytest.approx(0.0, abs=1.0)


def test_spectrum_nfft_zero_pad_does_not_change_bin_count_when_omitted():
    x = sine(220.0, SR, 0.5)
    r1 = spectral.spectrum(x, SR, resolution_hz=5.0)
    r2 = spectral.spectrum(x, SR, resolution_hz=5.0, nfft=None)
    assert r1["freqs_hz"] == r2["freqs_hz"]
    assert r1["level_db"] == r2["level_db"]


def test_spectrum_nfft_finer_grid():
    x = sine(220.0, SR, 0.05)  # short segment -> coarse native grid
    coarse = spectral.spectrum(x, SR, resolution_hz=1.0)
    fine = spectral.spectrum(x, SR, resolution_hz=1.0, nfft=1 << 17)
    assert (fine["freqs_hz"][1] - fine["freqs_hz"][0]) < (
        coarse["freqs_hz"][1] - coarse["freqs_hz"][0]
    )


# -- spectral.band_levels -------------------------------------------------------------------------


def test_band_levels_puts_a_tone_mostly_in_its_own_band():
    x = sine(1000, SR, 2.0, amp=1.0)  # falls in the default 500-2000 Hz "mid" band
    result = spectral.band_levels(x, SR)
    bands = {(b["low_hz"], b["high_hz"]): b for b in result["bands"]}
    mid = bands[(500.0, 2000.0)]
    assert mid["share_db"] > -1.0  # nearly all the signal's power


def test_band_levels_custom_bands_and_shares_sum_near_total():
    x = sine(1000, SR, 2.0, amp=1.0)
    bands = ((0.0, 500.0), (500.0, 2000.0), (2000.0, 24000.0))
    result = spectral.band_levels(x, SR, bands=bands)
    shares_linear = [10 ** (b["share_db"] / 10.0) for b in result["bands"]]
    assert sum(shares_linear) == pytest.approx(1.0, abs=0.05)


# -- spectral.centroid ----------------------------------------------------------------------------


def test_centroid_of_a_pure_tone_matches_its_frequency():
    x = sine(1000, SR, 1.0, amp=1.0)
    result = spectral.centroid(x, SR)
    centroid_hz = np.array(result["centroid_hz"])
    voiced = centroid_hz[~np.isnan(centroid_hz)]
    assert np.mean(np.abs(voiced - 1000.0)) < 20.0


def test_centroid_first_crossing_on_a_linear_sweep():
    dur = 2.0
    f_start, f_end = 200.0, 2000.0
    t = np.arange(int(SR * dur)) / SR
    inst_f = f_start + (f_end - f_start) * t / dur
    phase = 2 * np.pi * np.cumsum(inst_f) / SR
    x = np.sin(phase)
    threshold = 1000.0
    result = spectral.centroid(x, SR, threshold_hz=threshold)
    expected_t = dur * (threshold - f_start) / (f_end - f_start)
    assert result["first_crossing_s"] == pytest.approx(expected_t, abs=0.15)


def test_centroid_first_crossing_is_none_without_threshold():
    x = sine(1000, SR, 1.0)
    assert spectral.centroid(x, SR)["first_crossing_s"] is None


# -- spectral.peaks -------------------------------------------------------------------------------


def test_peaks_finds_a_non_bin_centred_tone():
    x = sine(1000.37, SR, 2.0, amp=1.0)
    result = spectral.peaks(x, SR, n=1, resolution_hz=1.0)
    assert len(result["peaks"]) == 1
    assert result["peaks"][0]["freq_hz"] == pytest.approx(1000.37, abs=0.5)


def test_peaks_ranks_a_strong_second_harmonic_bass_note_above_the_weaker_fundamental():
    f0 = 55.0
    t = np.arange(int(SR * 2.0)) / SR
    x = 0.3 * np.sin(2 * np.pi * f0 * t) + 0.9 * np.sin(2 * np.pi * 2 * f0 * t)
    result = spectral.peaks(x, SR, n=2, min_hz=20.0)
    assert result["peaks"][0]["freq_hz"] == pytest.approx(2 * f0, abs=1.0)


# -- spectral.stft --------------------------------------------------------------------------------


def test_stft_without_out_returns_a_summary_only():
    x = sine(1000, SR, 1.0)
    result = spectral.stft(x, SR)
    assert "file" not in result
    assert "note" in result
    assert result["shape"][0] > 0 and result["shape"][1] > 0


def test_stft_with_out_writes_npz_and_returns_its_path(tmp_path):
    x = sine(1000, SR, 1.0)
    out_path = tmp_path / "result.npz"
    result = spectral.stft(x, SR, out=str(out_path))
    assert result["file"] == str(out_path)
    assert out_path.is_file()
    with np.load(out_path) as data:
        assert set(data.files) == {"times_s", "freqs_hz", "level_db"}
        assert data["level_db"].shape == tuple(result["shape"])


# -- cross-category consistency contract -----------------------------------------------------


def _synthetic_audio():
    return sine(440.0, SR, 1.0, amp=0.5)


@pytest.mark.parametrize("category_name", list(analysis.CATEGORIES))
def test_every_analysis_has_a_revision_and_typed_defaulted_params(category_name):
    module = analysis.CATEGORIES[category_name]
    assert module.ANALYSES, f"{category_name} declares no ANALYSES"
    for fn in module.ANALYSES:
        assert isinstance(fn.revision, int), f"{fn.__name__} has no int revision"
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        assert [p.name for p in params[:2]] == ["audio", "sample_rate"]
        for param in params[2:]:
            assert param.default is not inspect.Parameter.empty, (
                f"{fn.__name__}'s {param.name} has no default"
            )
            assert param.annotation is not inspect.Parameter.empty, (
                f"{fn.__name__}'s {param.name} has no type hint"
            )


@pytest.mark.parametrize("category_name", list(analysis.CATEGORIES))
def test_every_analysis_docstring_names_a_unit_for_each_result_field(category_name):
    module = analysis.CATEGORIES[category_name]
    audio = _synthetic_audio()
    for fn in module.ANALYSES:
        sig = inspect.signature(fn)
        kwargs = {}
        if "out" in sig.parameters:
            kwargs["out"] = None
        result = fn(audio, SR, **kwargs)
        doc = fn.__doc__ or ""
        for field in result:
            assert re.search(rf"{re.escape(field)}\s*\(", doc), (
                f"{module.__name__}.{fn.__name__}'s docstring never states a unit for "
                f"result field {field!r}"
            )
