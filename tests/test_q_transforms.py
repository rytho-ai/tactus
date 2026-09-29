"""Direct mathematical Q-filter oracles, signal behavior and optional length reference."""

import numpy as np
import pytest

from tactus.analysis import spectral


def direct(audio, rate, *, hop, fmin, n_bins, bins_per_octave=12, filter_scale=1, gamma=0):
    """Literal sample sums, independent of the production convolution/alignment."""
    alpha = (2 ** (2 / bins_per_octave) - 1) / (2 ** (2 / bins_per_octave) + 1)
    out = []
    for k in range(n_bins):
        f = fmin * 2 ** (k / bins_per_octave)
        size = int(np.ceil(filter_scale * rate / (alpha * f + gamma)))
        offsets = np.arange(size) - size // 2
        weights = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(size) / size)
        kernel = 2 * weights / weights.sum() * np.exp(-2j * np.pi * f * offsets / rate)
        values = []
        for center in range(0, len(audio) + 1, hop):
            indices = center + offsets
            keep = (indices >= 0) & (indices < len(audio))
            values.append(abs(np.dot(audio[indices[keep]], kernel[keep])))
        out.append(values)
    return np.array(out)


@pytest.mark.parametrize("rate", [8000, 22050, 48000])
@pytest.mark.parametrize("gamma", [0, 13.7, 90])
@pytest.mark.parametrize("length,hop", [(1, 64), (128, 64), (503, 71)])
def test_every_frame_matches_direct_sum_including_boundaries(rate, gamma, length, hop):
    x = np.random.default_rng(72).normal(size=length * 2)[::2]
    before = x.copy()
    params = {"hop": hop, "fmin": 220, "n_bins": 6, "gamma": gamma}
    actual = spectral.vqt(x, rate, **params)
    np.testing.assert_allclose(actual["magnitude"], direct(x, rate, **params), atol=2e-14)
    np.testing.assert_array_equal(actual["times_s"], np.arange(length // hop + 1) * hop / rate)
    np.testing.assert_array_equal(x, before)


def test_tones_scaling_octaves_and_gamma():
    rate = 22050
    time = np.arange(rate * 2) / rate
    x = 0.3 * np.sin(2 * np.pi * 220 * time)
    kwargs = {"fmin": 110, "n_bins": 36, "hop": 256}
    cqt = spectral.cqt(x, rate, **kwargs)
    vqt = spectral.vqt(x, rate, gamma=0, **kwargs)
    np.testing.assert_array_equal(cqt["magnitude"], vqt["magnitude"])
    means = cqt["magnitude"][:, 20:-20].mean(axis=1)
    assert np.argmax(means) == 12
    assert means[12] == pytest.approx(0.3, abs=1e-5)
    doubled = spectral.cqt(np.column_stack([x, x]), rate, **kwargs)
    np.testing.assert_allclose(doubled["magnitude"], 2 * cqt["magnitude"], atol=1e-14)
    cancelled = spectral.cqt(np.column_stack([x, -x]), rate, **kwargs)
    assert not cancelled["magnitude"].any()
    variable = spectral.vqt(x, rate, **kwargs)
    assert np.all(variable["window_samples"] < cqt["window_samples"])
    assert variable["gamma_hz"] > 0


@pytest.mark.parametrize("fn", [spectral.cqt, spectral.vqt])
@pytest.mark.parametrize(
    "kwargs",
    [
        {"hop": 0},
        {"hop": True},
        {"n_bins": 0},
        {"n_bins": 4097},
        {"bins_per_octave": 0},
        {"fmin": -1},
        {"fmin": 1e-12},
        {"fmin": float("nan")},
        {"fmin": 20000},
        {"filter_scale": 0},
        {"filter_scale": float("inf")},
        {"filter_scale": 1e-6},
    ],
)
def test_bad_parameters(fn, kwargs):
    # Tiny fmin in VQT can remain valid because positive gamma bounds window length.
    if fn is spectral.vqt:
        kwargs = {"gamma": 0, **kwargs}
    with pytest.raises(ValueError):
        fn(np.zeros(40), 22050, **kwargs)


@pytest.mark.parametrize("gamma", [-1, float("nan"), float("inf")])
def test_bad_gamma(gamma):
    with pytest.raises(ValueError):
        spectral.vqt(np.zeros(4), 22050, gamma=gamma)


@pytest.mark.parametrize("fn", [spectral.cqt, spectral.vqt])
@pytest.mark.parametrize(
    "audio,rate",
    [
        (np.array([]), 22050),
        (np.array([np.nan]), 22050),
        (np.array([1j]), 22050),
        (np.zeros((3, 0)), 22050),
        (np.zeros(10), 0),
    ],
)
def test_bad_input(fn, audio, rate):
    with pytest.raises(ValueError):
        fn(audio, rate)


@pytest.mark.reference
@pytest.mark.parametrize("gamma", [0, 13.7])
def test_lengths_match_reference_convention(librosa, gamma):
    actual = spectral.vqt(np.zeros(3), 22050, gamma=gamma)
    lengths, _ = librosa.filters.wavelet_lengths(freqs=actual["freqs_hz"], sr=22050, gamma=gamma)
    np.testing.assert_array_equal(actual["window_samples"], np.ceil(lengths))


def test_q_analysis_never_imports_numba_or_reference_packages(monkeypatch):
    import builtins

    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"numba", "librosa", "pyloudnorm"}:
            raise AssertionError(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    # A huge hop still needs only frame zero; no proportional padding allocation.
    for fn in (spectral.cqt, spectral.vqt):
        result = fn(np.array([0.2, 0.4]), 22050, hop=10**9)
        assert result["magnitude"].shape == (84, 1)
