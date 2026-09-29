"""Owned DSP signal properties, explicit state, and production integration."""

import json

import numpy as np
import pytest
from scipy.signal import butter, freqz, lfilter

from tactus import dsp
from tactus._biquad import coefficients
from tactus.cli import main


def test_gain_controls_channels_without_clipping_or_mutation():
    x = np.array([[1.0, -1.0], [0.25, -0.5]])
    saved = x.copy()
    got = dsp.gain(x, np.array([20.0, 0.0]))
    np.testing.assert_allclose(got, [[10, -10], [0.25, -0.5]])
    np.testing.assert_array_equal(x, saved)
    assert got.dtype == np.float64
    assert not np.shares_memory(got, x)
    np.testing.assert_array_equal(dsp.gain(x[:0], 0), x[:0])


def test_fade_endpoints_overlap_and_one_sample():
    x = np.ones((5, 2))
    expected = np.array([0, 0.5, 1, 0.5, 0])
    np.testing.assert_allclose(
        dsp.fade(x, 10, in_s=0.3, out_s=0.3), np.column_stack([expected, expected])
    )
    np.testing.assert_array_equal(dsp.fade(np.ones(3), 10, in_s=0.1, out_s=0.1), [0, 1, 0])
    np.testing.assert_allclose(
        dsp.fade(np.ones(5), 10, in_s=0.5, out_s=0.5), np.linspace(0, 1, 5) * np.linspace(1, 0, 5)
    )
    np.testing.assert_array_equal(x, 1)
    assert dsp.fade(np.array([]), 10).shape == (0,)


def test_pan_energy_and_endpoints():
    x = np.ones(101)
    result = dsp.pan(x, np.linspace(-1, 1, 101))
    np.testing.assert_allclose(np.sum(result**2, axis=1), x**2)
    np.testing.assert_allclose(result[0], [1, 0], atol=1e-15)
    np.testing.assert_allclose(result[-1], [0, 1], atol=1e-15)
    np.testing.assert_allclose(result[50], [1 / np.sqrt(2)] * 2)
    assert dsp.pan(np.empty(0)).shape == (0, 2)
    with pytest.raises(ValueError, match="mono"):
        dsp.pan(np.ones((3, 2)))


@pytest.mark.parametrize("kind", ["lowpass", "highpass"])
def test_pass_filters_match_independent_butterworth_design(kind):
    rate = 48000
    impulse = np.r_[1.0, np.zeros(4095)]
    result, _ = dsp.biquad(impulse, rate, kind=kind, frequency_hz=1300)
    b, a = butter(2, 1300, fs=rate, btype="low" if kind == "lowpass" else "high")
    np.testing.assert_allclose(result, lfilter(b, a, impulse), atol=1e-14)


@pytest.mark.parametrize("kind", ["peak", "low_shelf", "high_shelf"])
@pytest.mark.parametrize("db", [-12, 0, 9])
def test_eq_gain_at_center_and_endpoints(kind, db):
    c = coefficients(48000, kind, 1000, 0.707, db)
    _, h = freqz(c[:3], c[3:], worN=[0, 2 * np.pi * 1000 / 48000, np.pi])
    measured = 20 * np.log10(abs(h))
    target = {"peak": [0, db, 0], "low_shelf": [db, db / 2, 0], "high_shelf": [0, db / 2, db]}[kind]
    np.testing.assert_allclose(measured, target, atol=1e-10)


@pytest.mark.parametrize("kind", ["lowpass", "highpass", "peak", "low_shelf", "high_shelf"])
@pytest.mark.parametrize("channels", [1, 2, 5])
def test_explicit_state_matches_whole_audio_and_does_not_mutate(kind, channels):
    x = np.random.default_rng(123).normal(size=(1093, channels))
    if channels == 1:
        x = x[:, 0]
    before = x.copy()
    kw = {"kind": kind, "frequency_hz": 1700, "gain_db": 6 if "pass" not in kind else 0}
    whole, final = dsp.biquad(x, 44100, **kw)
    state = None
    outputs = []
    for first, end in [(0, 1), (1, 7), (7, 7), (7, 301), (301, len(x))]:
        prior = None if state is None else state.copy()
        result, next_state = dsp.biquad(x[first:end], 44100, state=state, **kw)
        if prior is not None:
            np.testing.assert_array_equal(state, prior)
        state = next_state
        outputs.append(result)
    np.testing.assert_array_equal(np.concatenate(outputs), whole)
    np.testing.assert_array_equal(state, final)
    np.testing.assert_array_equal(x, before)
    np.testing.assert_array_equal(dsp.biquad(x, 44100, **kw)[0], whole)


def test_biquad_channel_isolation_and_tail():
    x = np.zeros((100, 2))
    x[0, 0] = 1
    y, state = dsp.biquad(x, 48000, kind="lowpass", frequency_hz=300)
    assert not y[:, 1].any()
    tail, _ = dsp.biquad(np.zeros((100, 2)), 48000, kind="lowpass", frequency_hz=300, state=state)
    assert np.any(tail[:, 0]) and not tail[:, 1].any()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frequency_hz": 0},
        {"frequency_hz": 24000},
        {"q": 0},
        {"gain_db": np.nan},
        {"kind": "unknown"},
        {"gain_db": 2},
        {"state": np.zeros((2, 2))},
        {"state": np.full((2, 1), np.nan)},
    ],
)
def test_biquad_rejects_invalid_parameters(kwargs):
    params = {"kind": "lowpass", "frequency_hz": 1000}
    params.update(kwargs)
    with pytest.raises(ValueError):
        dsp.biquad(np.ones(100), 48000, **params)


@pytest.mark.parametrize(
    "audio", [np.array([np.nan]), np.array([1j]), np.zeros((2, 0)), np.zeros((2, 2, 2))]
)
def test_invalid_audio(audio):
    for fn in [
        lambda: dsp.gain(audio, 0),
        lambda: dsp.fade(audio, 48000),
        lambda: dsp.pan(audio),
        lambda: dsp.biquad(audio, 48000, kind="lowpass", frequency_hz=1000),
    ]:
        with pytest.raises(ValueError):
            fn()


def test_bad_controls():
    x = np.ones(10)
    for fn in [
        lambda: dsp.gain(x, [0, 1]),
        lambda: dsp.gain(x, np.nan),
        lambda: dsp.pan(x, 2),
        lambda: dsp.fade(x, 10, in_s=2),
        lambda: dsp.fade(x, 10, out_s=-1),
        lambda: dsp.fade(x, False),
        lambda: dsp.biquad(x, 0, kind="peak", frequency_hz=1),
        lambda: dsp.gain(x, 10000),
    ]:
        with pytest.raises(ValueError):
            fn()


def test_dsp_in_real_run(tmp_path, capsys):
    song = tmp_path / "song.py"
    song.write_text("""import numpy as np
from tactus import dsp
def render():
    sr=48000
    x=np.sin(2*np.pi*440*np.arange(sr)/sr)
    x=dsp.fade(dsp.gain(x,-12),sr,in_s=.01,out_s=.1)
    x=dsp.pan(x,np.linspace(-1,1,sr))
    x,_=dsp.biquad(x,sr,kind="lowpass",frequency_hz=3000)
    return {"sample_rate":sr,"outputs":{"mix":x}}
""")
    out = tmp_path / "run"
    assert main(["run", str(song), "--out", str(out)]) == 0
    reports = capsys.readouterr().out
    assert "mix" in reports
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["sample_rate"] == 48000
