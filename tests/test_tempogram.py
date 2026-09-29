"""Independent lag correlations, tempo axes, audio pipeline and optional oracle."""

import numpy as np
import pytest

from tactus.analysis import rhythm
from tactus.analysis._tempogram import autocorrelation


def direct(envelope, window, lags):
    result = np.zeros((len(lags), len(envelope)))
    weights = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(window) / window)
    for j in range(len(envelope)):
        indices = j + np.arange(window) - window // 2
        valid = (indices >= 0) & (indices < len(envelope))
        frame = np.zeros(window)
        frame[valid] = envelope[indices[valid]]
        frame *= weights
        energy = np.dot(frame, frame)
        if energy:
            for k, lag in enumerate(lags):
                result[k, j] = np.dot(frame[:-lag], frame[lag:]) / energy
    return result


@pytest.mark.parametrize("window", [4, 5, 64, 401])
@pytest.mark.parametrize("length", [1, 73, 1500])
def test_fft_matches_direct_linear_correlation(window, length):
    env = np.random.default_rng(123).uniform(size=length)
    lags = np.arange(window - 1, 0, -1)
    np.testing.assert_allclose(
        autocorrelation(env, window, lags), direct(env, window, lags), atol=1e-14
    )


@pytest.mark.parametrize("bpm", [60, 120, 180])
def test_known_click_tempo(bpm):
    rate = 12000
    audio = np.zeros(rate * 12)
    audio[(np.arange(0.5, 11.5, 60 / bpm) * rate).astype(int)] = 1
    result = rhythm.tempogram(audio, rate, bpm_min=40, bpm_max=240)
    strongest = np.argmax(result["tempogram"][:, 400:800].mean(axis=1))
    assert result["bpms"][strongest] == pytest.approx(bpm, abs=3)
    np.testing.assert_allclose(result["bpms"], 60 * rate / (result["hop_samples"] * result["lags"]))
    assert np.all(np.diff(result["bpms"]) > 0)
    assert result["tempogram"].shape[1] == len(result["times_s"])


@pytest.mark.parametrize("length", [1, 120, 2401])
def test_silence_and_short_input(length):
    result = rhythm.tempogram(np.zeros(length), 12000)
    assert not result["tempogram"].any()
    assert result["tempogram"].shape[1] == 1 + length // 120


@pytest.mark.parametrize(
    "params",
    [
        {"hop_s": 0},
        {"hop_s": 1},
        {"window_s": 0.01},
        {"window_s": 10000},
        {"window_s": float("nan")},
        {"bpm_min": 0},
        {"bpm_max": 20},
        {"bpm_max": float("inf")},
        {"bpm_min": 10000, "bpm_max": 11000},
    ],
)
def test_bad_parameters(params):
    with pytest.raises(ValueError):
        rhythm.tempogram(np.zeros(10), 22050, **params)


@pytest.mark.reference
def test_librosa_same_envelope_with_explicit_zero_padding(librosa):
    rate = 22050
    x = np.random.default_rng(15).normal(size=rate)
    result = rhythm.tempogram(x, rate)
    onset = rhythm.onset_strength(x, rate, hop_s=0.01)["strength"]
    window = result["window_frames"]
    # center=False over explicitly zero-padded input avoids upstream ramp padding.
    expected = librosa.feature.tempogram(
        onset_envelope=np.pad(onset, (window // 2, window // 2)),
        sr=rate,
        hop_length=result["hop_samples"],
        win_length=window,
        center=False,
    )[:, : len(onset)]
    np.testing.assert_allclose(result["tempogram"], expected[result["lags"]], atol=2e-14)
