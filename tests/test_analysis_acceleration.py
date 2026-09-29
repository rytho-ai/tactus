"""Numerical parity and resource policy for the automatic analysis backends."""

import numba
import numpy as np
import pytest
from scipy.fft import get_workers, set_workers
from scipy.signal import stft as scipy_stft

from tactus.analysis import _acceleration, _analysis_kernels, _features, _qtransform, spectral


@pytest.mark.parametrize("gamma", [0, None, 90])
@pytest.mark.parametrize("length,hop", [(1, 64), (128, 64), (503, 71), (8192, 32)])
def test_compiled_q_matches_native_and_preserves_input(monkeypatch, gamma, length, hop):
    x = np.random.default_rng(72).normal(size=(length * 2, 2))[::2]
    before = x.copy()
    params = {"hop": hop, "fmin": 220, "n_bins": 6, "gamma": gamma}
    monkeypatch.setattr(_qtransform, "_JIT_MIN_WORK", float("inf"))
    expected = spectral.vqt(x, 22050, **params)
    monkeypatch.setattr(_qtransform, "_JIT_MIN_WORK", 0)
    actual = spectral.vqt(x, 22050, **params)
    np.testing.assert_allclose(actual["magnitude"], expected["magnitude"], rtol=1e-12, atol=2e-14)
    for key in expected.keys() - {"magnitude"}:
        np.testing.assert_array_equal(actual[key], expected[key])
    np.testing.assert_array_equal(x, before)


def test_q_thread_mask_restored_after_success_and_failure(monkeypatch):
    previous = numba.get_num_threads()
    monkeypatch.setattr(_qtransform, "_JIT_MIN_WORK", 0)
    try:
        numba.set_num_threads(min(2, previous))
        expected = numba.get_num_threads()
        spectral.cqt(np.ones(100), 8000, fmin=220, n_bins=6, hop=16)
        assert numba.get_num_threads() == expected

        def fail(*args):
            assert numba.get_num_threads() == expected
            raise RuntimeError("kernel failed")

        monkeypatch.setattr(_analysis_kernels, "correlations", fail)
        with pytest.raises(RuntimeError, match="kernel failed"):
            spectral.cqt(np.ones(100), 8000, fmin=220, n_bins=6, hop=16)
        assert numba.get_num_threads() == expected
    finally:
        numba.set_num_threads(previous)


def test_q_memory_limit_falls_back_to_native(monkeypatch):
    monkeypatch.setattr(_qtransform, "_JIT_MIN_WORK", 0)
    monkeypatch.setattr(_qtransform, "_JIT_MAX_BYTES", 1)

    def forbidden(*args):
        raise AssertionError("packed allocation should have been avoided")

    monkeypatch.setattr(_qtransform, "_compiled_magnitude", forbidden)
    assert spectral.cqt(np.zeros(128), 8000, fmin=220, n_bins=6)["magnitude"].shape == (6, 1)
    assert not spectral.cqt(np.zeros(128), 8000, fmin=220, n_bins=6, hop=16)["magnitude"].any()


@pytest.mark.parametrize("n_fft,hop", [(2048, 512), (511, 127), (513, 513), (2, 1)])
def test_parallel_stft_matches_original_scipy_exactly(n_fft, hop):
    x = np.random.default_rng(93).normal(size=600000)
    freqs, times, values = scipy_stft(
        x, fs=44100, window="hann", nperseg=n_fft, noverlap=n_fft - hop, boundary="zeros"
    )
    with np.errstate(divide="ignore"):
        expected = 10 * np.log10((np.abs(values) ** 2 * 2) / 0.5)
    actual = spectral.stft(x, 44100, n_fft=n_fft, hop=hop)
    np.testing.assert_array_equal(actual["level_db"], expected)
    np.testing.assert_array_equal(actual["times_s"], times)
    np.testing.assert_array_equal(actual["freqs_hz"], freqs)


def test_parallel_mel_matches_serial_exactly(monkeypatch):
    x = np.random.default_rng(94).normal(size=600000)
    parallel = spectral.mel(x, 44100)
    monkeypatch.setattr(_features, "fft_workers", lambda work: 1)
    serial = spectral.mel(x, 44100)
    for key in serial:
        np.testing.assert_array_equal(parallel[key], serial[key])


def test_fft_worker_context_is_restored_and_nondefault_is_honored():
    original = get_workers()
    with set_workers(2):
        assert _acceleration.fft_workers(10**9) == 2
        spectral.stft(np.zeros(600000), 44100)
        spectral.mel(np.zeros(600000), 44100)
        assert get_workers() == 2
    assert get_workers() == original
    with set_workers(1):
        assert _acceleration.fft_workers(1) == 1
