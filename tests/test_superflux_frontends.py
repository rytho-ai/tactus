"""Independent dense/reference checks for selectable SuperFlux frontends."""

import json

import numpy as np
import pytest
import soundfile as sf
from scipy.ndimage import maximum_filter1d

from tactus.analysis import _features, _onset, rhythm
from tactus.cli import main


def dense_log(
    audio,
    rate,
    n_fft=1024,
    hop_s=0.005,
    bands_per_octave=24,
    fmin=27.5,
    fmax=None,
    lag=2,
    max_size=3,
):
    """Dense independent FFT/filter/difference oracle, with explicit Tactus framing."""
    upper = min(16000, rate / 2) if fmax is None else fmax
    hop = max(1, round(hop_s * rate))
    x = audio.mean(axis=1) if audio.ndim == 2 else audio
    # Enumerate A440 log-grid points analytically, including bracketing edges.
    low = min(0, int(np.floor(bands_per_octave * np.log2(fmin / 440))))
    high = max(0, int(np.ceil(bands_per_octave * np.log2(upper / 440))))
    hz = 440 * 2.0 ** (np.arange(low, high + 1) / bands_per_octave)
    edges = np.unique(np.rint(hz * n_fft / rate).astype(int))
    edges = edges[edges < n_fft // 2]
    bins = np.arange(n_fft // 2 + 1)
    rows = []
    for left, center, right in zip(edges, edges[1:], edges[2:], strict=False):
        if fmin <= center * rate / n_fft <= upper:
            rows.append(
                np.maximum(
                    0,
                    np.minimum((bins - left) / (center - left), (right - bins) / (right - center)),
                )
            )
    frames = np.lib.stride_tricks.sliding_window_view(np.pad(x, (n_fft // 2, n_fft // 2)), n_fft)[
        ::hop
    ]
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(n_fft) / n_fft)
    magnitude = abs(np.fft.rfft(frames * window, axis=1))
    compressed = np.log10(1 + np.array(rows) @ magnitude.T)
    if len(frames) <= lag:
        return np.zeros(len(frames))
    ref = maximum_filter1d(compressed, max_size, axis=0)
    raw = np.maximum(0, compressed[:, lag:] - ref[:, :-lag]).mean(axis=0)
    return np.pad(raw, (lag + n_fft // (2 * hop), 0))[: len(frames)]


def test_log_filter_known_triangles():
    weights = _features.log_frequency_weights(16000, 16, 1, 1000, 6000)
    expected = np.zeros((3, 9))
    expected[0, 1] = 1
    expected[1, 2:4] = [1, 0.5]
    expected[2, 3:7] = [0.5, 1, 2 / 3, 1 / 3]
    np.testing.assert_allclose(weights, expected, atol=1e-15)


@pytest.fixture(
    params=[
        (rate, n_fft, bands, lag, width)
        for rate in [8000, 22050, 44100, 48000]
        for n_fft, bands, lag, width in [(1024, 24, 2, 3), (2048, 12, 1, 1), (126, 36, 3, 5)]
    ]
)
def log_case(request):
    rate, n_fft, bands, lag, width = request.param
    audio = np.random.default_rng(914).normal(size=(rate * 2, 2))[::2] * 0.05
    kw = {"n_fft": n_fft, "bands_per_octave": bands, "lag": lag, "max_size": width, "hop_s": 0.001}
    return rate, audio, kw


def test_log_frontend_matches_independent_dense_reference(log_case):
    rate, audio, kw = log_case
    before = audio.copy()
    expected = dense_log(audio, rate, **kw)
    actual = rhythm.onset_strength(audio, rate, filterbank="log", **kw)
    np.testing.assert_allclose(actual["strength"], expected, atol=1e-12, rtol=1e-10)
    hop = actual["hop_samples"]
    np.testing.assert_array_equal(actual["times_s"], np.arange(len(expected)) * hop / rate)
    np.testing.assert_array_equal(audio, before)


@pytest.mark.reference
def test_log_peak_picker_matches_librosa(log_case, librosa):
    rate, audio, kw = log_case
    expected = dense_log(audio, rate, **kw)
    hop = max(1, round(kw["hop_s"] * rate))
    for backtrack in [False, True]:
        frames = librosa.onset.onset_detect(
            onset_envelope=expected,
            sr=rate,
            hop_length=hop,
            delta=0.07,
            wait=int(0.03 * rate // hop),
        )
        if backtrack and len(frames):
            normalized = expected - expected.min()
            normalized /= normalized.max() + np.finfo(float).tiny
            frames = librosa.onset.onset_backtrack(frames, normalized)
        times = np.unique(frames[frames * hop < len(audio)]) * hop / rate
        got = rhythm.onsets(audio, rate, filterbank="log", backtrack=backtrack, **kw)
        np.testing.assert_array_equal(got["onsets_s"], times)


@pytest.mark.parametrize("filterbank", ["mel", "log"])
@pytest.mark.parametrize("length", [1, 17, 8000])
def test_empty_events_and_cancellation(filterbank, length):
    x = np.zeros(length)
    assert rhythm.onsets(x, 8000, filterbank=filterbank, backtrack=True)["onsets_s"] == []
    assert not np.any(rhythm.onset_strength(x, 8000, filterbank=filterbank)["strength"])
    x = np.random.default_rng(15).normal(size=length)
    assert rhythm.onsets(np.column_stack([x, -x]), 8000, filterbank=filterbank)["onsets_s"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"filterbank": "unknown"},
        {"bands_per_octave": 0},
        {"bands_per_octave": True},
        {"filterbank": "log", "fmin": 0},
        {"filterbank": "log", "fmin": -1},
        {"filterbank": "log", "fmin": 999, "fmax": 1000, "n_fft": 4},
        {"filterbank": "log", "n_fft": 5},
        {"filterbank": "log", "fmax": float("nan")},
        {"filterbank": "log", "n_mels": 0},
        {"filterbank": "log", "hop_s": 1},
    ],
)
def test_invalid_configuration(params):
    for fn in [rhythm.onsets, rhythm.onset_strength]:
        with pytest.raises((ValueError, TypeError)):
            fn(np.zeros(1000), 8000, **params)


def test_maximum_filter_suppresses_a_moving_spectral_peak():
    # A sustained partial moves one band: no new attack. New energy remains detectable.
    spectrum = np.zeros((7, 8))
    spectrum[2, :4] = 1
    spectrum[3, 4:] = 1
    ordinary = _onset.strength(spectrum, 4, 2, 1, 1, compressed=True)
    suppressed = _onset.strength(spectrum, 4, 2, 1, 3, compressed=True)
    assert ordinary.max() > 0
    assert not suppressed.any()
    spectrum[3, 6:] = 2
    assert _onset.strength(spectrum, 4, 2, 1, 3, compressed=True).max() > 0


@pytest.mark.parametrize("name", ["onsets", "onset_strength"])
@pytest.mark.parametrize("filterbank", ["mel", "log"])
def test_cli_records_frontend_and_matches_python(name, filterbank, tmp_path, capsys):
    wav = tmp_path / "source.wav"
    x = np.zeros(16000)
    x[[2000, 9000]] = 1
    sf.write(wav, x, 8000, subtype="DOUBLE")
    assert (
        main(
            [
                "analyze",
                "rhythm",
                name,
                str(wav),
                "--filterbank",
                filterbank,
                "--bands-per-octave",
                "12",
                "--out",
                str(tmp_path / "measurements"),
            ]
        )
        == 0
    )
    record = json.loads(capsys.readouterr().out)
    assert record["params"]["filterbank"] == filterbank
    assert record["params"]["bands_per_octave"] == 12
    assert record["result"] == getattr(rhythm, name)(
        x, 8000, filterbank=filterbank, bands_per_octave=12
    )
    saved = json.loads(next((tmp_path / "measurements").rglob("result.json")).read_text())
    assert saved == record


def test_mel_default_is_explicit_mel_and_log_ignores_mel_count():
    x = np.random.default_rng(3).normal(size=12000)
    assert rhythm.onsets(x, 8000) == rhythm.onsets(x, 8000, filterbank="mel")
    assert rhythm.onsets(x, 8000, filterbank="log") == rhythm.onsets(
        x, 8000, filterbank="log", n_mels=8
    )


@pytest.mark.parametrize("filterbank", [pytest.param("mel", marks=pytest.mark.reference), "log"])
def test_projection_chunk_boundary_and_quiet_tail(filterbank, request):
    rate = 44100
    x = np.random.default_rng(22).normal(size=220 * 1024 + 17)[::-1]
    x[220 * 1024 - 100 :] *= 1e-20
    if filterbank == "log":
        expected = dense_log(x, rate)
    else:
        librosa = request.getfixturevalue("librosa")
        mel = librosa.feature.melspectrogram(
            y=x,
            sr=rate,
            n_fft=1024,
            hop_length=220,
            n_mels=138,
            fmin=27.5,
            fmax=16000,
        )
        expected = librosa.onset.onset_strength(
            S=librosa.power_to_db(mel, ref=np.max),
            sr=rate,
            n_fft=1024,
            hop_length=220,
            lag=2,
            max_size=3,
        )
    actual = rhythm.onset_strength(x, rate, filterbank=filterbank)["strength"]
    np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=1e-10)


@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("width", [1, 3])
def test_strength_scratch_reuse_does_not_modify_input(compressed, width):
    x = np.random.default_rng(23).random((12, 80))[:, ::2]
    before = x.copy()
    _onset.strength(x, 16, 4, 2, width, compressed=compressed)
    np.testing.assert_array_equal(x, before)
