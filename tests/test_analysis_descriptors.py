"""Dynamics/spectral descriptors: analytical signals, reference definitions and CLI."""

import json

import numpy as np
import pytest
import soundfile as sf

from tactus.analysis import level, spectral
from tactus.cli import main

SPECTRAL = [
    (spectral.bandwidth, "bandwidth_hz"),
    (spectral.rolloff, "rolloff_hz"),
    (spectral.flatness, "flatness"),
]
FUNCTIONS = [level.crest_factor, level.crest_factor_curve, *(fn for fn, _ in SPECTRAL)]


def tone(rate=48000, frequency=1000):
    return np.sin(2 * np.pi * frequency * np.arange(rate) / rate)


def test_crest_known_sine_square_impulse_and_channel_definition():
    assert level.crest_factor(tone(), 48000)["crest_factor_db"] == pytest.approx(10 * np.log10(2))
    assert level.crest_factor(np.ones(100), 48000)["crest_factor_db"] == 0
    assert level.crest_factor(np.r_[1.0, np.zeros(99)], 48000)["crest_factor_db"] == pytest.approx(
        20
    )
    mono = tone()
    stereo = np.column_stack([mono, -mono])
    assert level.crest_factor(stereo, 48000)["crest_factor_db"] == pytest.approx(
        level.crest_factor(mono, 48000)["crest_factor_db"], abs=1e-12
    )
    assert level.crest_factor(np.column_stack([mono, mono * 0]), 48000)[
        "crest_factor_db"
    ] == pytest.approx(10 * np.log10(4))


@pytest.mark.parametrize("window,hop", [(50, 10), (43, 13), (1, 1), (50, 50)])
def test_crest_curve_direct_window_reference_and_strided_input(window, hop):
    x = np.random.default_rng(33).normal(size=(450, 2))[::2]
    before = x.copy()
    got = level.crest_factor_curve(x, 1000, window_s=window / 1000, hop_s=hop / 1000)
    starts = range(0, len(x) - window + 1, hop)
    expected = [
        20 * np.log10(np.abs(x[i : i + window]).max() / np.sqrt(np.mean(x[i : i + window] ** 2)))
        for i in starts
    ]
    np.testing.assert_allclose(got["crest_factor_db"], expected, atol=1e-12)
    np.testing.assert_array_equal(got["times_s"], [(i + window) / 1000 for i in starts])
    np.testing.assert_array_equal(x, before)


@pytest.mark.parametrize("scale", [1e-200, 1e-10, 1, 1e100])
def test_crest_extreme_gain_and_quiet_tail(scale):
    x = np.tile([0.0, 1.0, 0.0, -1.0], 25) * scale
    assert level.crest_factor(x, 1000)["crest_factor_db"] == pytest.approx(10 * np.log10(2))
    signal = np.r_[np.ones(100), x]
    got = level.crest_factor_curve(signal, 1000, window_s=0.1, hop_s=0.1)
    np.testing.assert_allclose(got["crest_factor_db"], [0, 10 * np.log10(2)], atol=1e-10)


@pytest.mark.parametrize("rate", [8000, 22050, 48000])
@pytest.mark.reference
def test_spectral_definitions_match_librosa_with_explicit_power_and_floor(rate, librosa):
    x = np.random.default_rng(412).normal(size=(rate // 2, 2)) * 0.2
    before = x.copy()
    size = 512
    hop = 121
    power = abs(librosa.stft(x.sum(axis=1), n_fft=size, hop_length=hop)) ** 2
    power /= power.max(axis=0)
    expected = {
        "bandwidth_hz": librosa.feature.spectral_bandwidth(S=power, sr=rate, n_fft=size, p=2)[0],
        "rolloff_hz": librosa.feature.spectral_rolloff(
            S=power, sr=rate, n_fft=size, roll_percent=0.85
        )[0],
        "flatness": librosa.feature.spectral_flatness(S=power, power=1, amin=1e-12)[0],
    }
    for fn, field in SPECTRAL:
        got = fn(x, rate, n_fft=size, hop=hop)
        np.testing.assert_allclose(got[field], expected[field], atol=1e-9, rtol=1e-12)
        np.testing.assert_array_equal(got["times_s"], np.arange(power.shape[1]) * hop / rate)
    np.testing.assert_array_equal(x, before)


def test_equal_tones_have_known_power_spread_and_rolloff():
    # Hann power contributes variance of one third of a bin squared to each tone.
    x = tone(frequency=1000) + tone(frequency=3000)
    got = spectral.bandwidth(x, 48000, n_fft=4800, hop=1200)
    np.testing.assert_allclose(got["bandwidth_hz"][2:-2], np.sqrt(1000**2 + 10**2 / 3), atol=1e-8)
    got = spectral.rolloff(x, 48000, n_fft=4800, hop=1200, roll_percent=0.85)
    np.testing.assert_array_equal(got["rolloff_hz"][2:-2], 3000)


def test_flatness_distinguishes_spectrum_shapes_without_labeling_audio():
    tonal = np.mean(spectral.flatness(tone(), 48000)["flatness"][2:-2])
    noise = np.mean(
        spectral.flatness(np.random.default_rng(7).normal(size=48000), 48000)["flatness"][2:-2]
    )
    assert tonal < 1e-6
    assert 0.3 < noise < 0.8
    impulse = np.zeros(1024)
    impulse[256] = 1
    assert spectral.flatness(impulse, 48000, n_fft=512, hop=128)["flatness"][2] == 1


@pytest.mark.parametrize("fn,field", SPECTRAL)
def test_gain_invariance_and_channel_cancellation(fn, field):
    x = np.random.default_rng(2).normal(size=8000)
    ref = fn(x, 8000)[field]
    np.testing.assert_allclose(fn(x * 1e-9, 8000)[field], ref, rtol=1e-12, atol=1e-9)
    cancelled = fn(np.column_stack([x, -x]), 8000)
    assert all(v is None for v in cancelled[field])


@pytest.mark.parametrize("length", [1, 17, 512, 2049])
def test_silence_short_inputs_and_curve_grids(length):
    x = np.zeros((length, 2))
    assert level.crest_factor(x, 8000)["crest_factor_db"] is None
    curve = level.crest_factor_curve(x, 8000)
    assert len(curve["times_s"]) == max(0, 1 + (length - 400) // 80)
    assert all(v is None for v in curve["crest_factor_db"])
    for fn, field in SPECTRAL:
        got = fn(x, 8000)
        assert len(got[field]) == 1 + length // 512
        assert all(v is None for v in got[field])
        assert got["times_s"][-1] <= length / 8000


@pytest.mark.parametrize("fn", FUNCTIONS)
@pytest.mark.parametrize(
    "audio,rate",
    [
        (np.array([]), 8000),
        (np.ones(1), False),
        (np.ones(1), 0),
        (np.ones(1), 8000.5),
        (np.array([np.nan]), 8000),
        (np.array([1j]), 8000),
        (np.zeros((2, 0)), 8000),
    ],
)
def test_invalid_inputs(fn, audio, rate):
    with pytest.raises(ValueError):
        fn(audio, rate)


@pytest.mark.parametrize(
    "fn,params",
    [
        (spectral.bandwidth, {"n_fft": 3}),
        (spectral.flatness, {"hop": 4096}),
        (spectral.rolloff, {"roll_percent": 0}),
        (spectral.rolloff, {"roll_percent": 1}),
        (spectral.rolloff, {"roll_percent": True}),
        (spectral.flatness, {"floor_ratio": 0}),
        (spectral.flatness, {"floor_ratio": np.nan}),
        (spectral.flatness, {"floor_ratio": True}),
        (level.crest_factor_curve, {"hop_s": 0}),
        (level.crest_factor_curve, {"window_s": -1}),
    ],
)
def test_invalid_parameters(fn, params):
    with pytest.raises(ValueError):
        fn(np.ones(8000), 8000, **params)


@pytest.mark.parametrize("fn", FUNCTIONS)
def test_generated_cli_help_records_and_silence_nulls(fn, tmp_path, capsys):
    category = "level" if fn in [level.crest_factor, level.crest_factor_curve] else "spectral"
    args = ["analyze", category, fn.__name__]
    with pytest.raises(SystemExit) as error:
        main([*args, "--help"])
    assert error.value.code == 0
    assert "Returns:" in capsys.readouterr().out
    path = tmp_path / "silent.wav"
    sf.write(path, np.zeros(3000), 8000, subtype="DOUBLE")
    out = tmp_path / "analysis"
    assert main([*args, str(path), "--out", str(out)]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["result"] == fn(np.zeros(3000), 8000)
    assert record["revision"] == 1
    assert json.loads(next(out.glob("*/result.json")).read_text()) == record
    assert "NaN" not in json.dumps(record)
