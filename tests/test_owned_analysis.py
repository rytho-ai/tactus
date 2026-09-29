"""Compatibility and numerical edge checks for owned analysis implementations."""

import builtins

import numpy as np
import pytest

from tactus.analysis import _features, _level, _onset, level, rhythm, spectral


@pytest.mark.parametrize("window,hop", [(5, 1), (15, 3), (17, 3), (4, 4), (1, 1), (90, 7)])
@pytest.mark.parametrize("channels", [1, 2, 5])
def test_window_reductions_match_direct_for_strides_and_quiet_tails(window, hop, channels):
    rng = np.random.default_rng(44)
    x = rng.normal(size=(400, channels))[::2]
    x[100:] *= 1e-100
    before = x.copy()
    starts = np.arange(0, max(0, len(x) - window + 1), hop)
    for peak in [False, True]:
        expected = np.array(
            [
                np.abs(x[i : i + window]).max() if peak else np.square(x[i : i + window]).mean()
                for i in starts
            ]
        )
        got = _level.amplitude_windows(x, starts, window, hop, peak=peak)
        np.testing.assert_allclose(got, expected, rtol=2e-15, atol=0)
    power = np.square(x).mean(axis=1)
    expected = np.array([power[i : i + window].mean() for i in starts])
    np.testing.assert_allclose(
        _level.window_mean(power, starts, window), expected, rtol=2e-15, atol=0
    )
    np.testing.assert_array_equal(x, before)


def test_overflow_in_discarded_tail_is_rejected():
    x = np.zeros((101, 2))
    x[-1] = 1e200
    with pytest.raises(ValueError, match="finite"):
        level.rms_curve(x, 1000, window_s=0.05, hop_s=0.01)


@pytest.mark.parametrize("rate", [8000, 22051, 44100, 48000])
@pytest.mark.parametrize("channels", [1, 2, 5])
def test_integrated_lufs_matches_legacy_gate_and_partial_tail(rate, channels, loudness_reference):
    rng = np.random.default_rng(84)
    x = rng.normal(size=(round(rate * 2.357), channels)) * 0.08
    x[: rate // 2] *= 1e-5
    x[rate : rate + rate // 2] *= 0.04
    before = x.copy()
    expected = loudness_reference(f"integrated-{rate}-{channels}", x, rate)["integrated_lufs"]
    assert level.loudness(x, rate)["integrated_lufs"] == pytest.approx(expected, abs=1e-8)
    np.testing.assert_array_equal(x, before)


@pytest.mark.parametrize("rate", [8000, 44100])
@pytest.mark.parametrize("seconds", [0.399, 0.4, 0.449, 0.45, 0.451, 1.05])
def test_integrated_short_threshold_and_silence(rate, seconds, loudness_reference):
    x = np.zeros(round(rate * seconds))
    ref = loudness_reference(f"silence-{rate}-{seconds}", x, rate)
    assert ref["integrated_lufs"] is None
    assert ref.get("error") == ("ValueError" if seconds < 0.4 else None)
    assert level.loudness(x, rate)["integrated_lufs"] is None


@pytest.mark.parametrize("n_fft,hop", [(4, 1), (126, 37), (1024, 1024), (2048, 117)])
@pytest.mark.parametrize("length", [1, 159, 4113])
@pytest.mark.reference
def test_owned_frontend_short_nonpoweroftwo_and_fullhop(n_fft, hop, length, librosa):
    x = np.random.default_rng(88).normal(size=length)
    padded = np.pad(x, (0, max(0, n_fft - len(x))))
    ref = np.abs(librosa.stft(padded, n_fft=n_fft, hop_length=hop))[:, : 1 + len(x) // hop] ** 2
    np.testing.assert_allclose(_features.power_spectrum(x, n_fft, hop), ref, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("hop", [1, 127, 1024, 2048])
@pytest.mark.parametrize("delta", [0, 0.07, 0.5])
@pytest.mark.reference
def test_peak_picker_matches_reference_at_edges_plateaus_and_zero_wait(hop, delta, librosa):
    rng = np.random.default_rng(18)
    for x in [
        np.zeros(1),
        np.ones(8),
        np.array([1.0, 0.0, 0.0, 1.0]),
        np.array([0.0, 1.0, 1.0, 0.0, 0.0, 1.0, 0.0]),
        rng.random(111),
    ]:
        for backtrack in [False, True]:
            ref = librosa.onset.onset_detect(
                onset_envelope=x, sr=8000, hop_length=hop, wait=0, delta=delta, backtrack=False
            )
            if backtrack and len(ref):
                normalized = x - x.min()
                normalized /= normalized.max() + np.finfo(float).tiny
                ref = librosa.onset.onset_backtrack(ref, normalized)
            # librosa 1.0 raises for empty events with backtrack=True. An empty
            # candidate list has nothing to backtrack and should remain empty.
            got = _onset.pick(x, 8000, hop, delta, 0, backtrack)
            np.testing.assert_array_equal(got, ref)


def test_owned_analysis_and_dsp_need_no_reference_imports(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"librosa", "pyloudnorm", "pymixtool"}:
            raise AssertionError(f"reference package imported: {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    from tactus import dsp

    x = np.zeros(32000)
    for module in (level, spectral, rhythm):
        for fn in module.ANALYSES:
            if fn is not rhythm.beats:
                # Seven default Q octaves extend past an 8 kHz input's Nyquist.
                kwargs = {"n_bins": 72} if fn in (spectral.cqt, spectral.vqt) else {}
                fn(x, 8000, **kwargs)
    dsp.biquad(x, 8000, kind="lowpass", frequency_hz=1000)
    dsp.gain(x, -3)
    dsp.fade(x, 8000, in_s=0.1)
    dsp.pan(x)


def test_no_detected_events_with_backtracking_returns_empty():
    x = np.zeros(8000)
    x[4000] = 1
    assert rhythm.onsets(x, 8000, delta=2, backtrack=True)["onsets_s"] == []


@pytest.mark.parametrize("bounds", [(0, 1000), (1000, 8000), (27.5, 16000)])
@pytest.mark.reference
def test_mel_centers_match_reference_at_linear_log_transition(bounds, librosa):
    np.testing.assert_array_equal(
        _features.mel_frequencies(66, *bounds),
        librosa.mel_frequencies(66, fmin=bounds[0], fmax=bounds[1]),
    )
