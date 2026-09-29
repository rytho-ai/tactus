"""Independent signal/window checks for native level curves, plus the generated CLI."""

from __future__ import annotations

import builtins
import json

import numpy as np
import pytest
import soundfile as sf

from tactus.analysis import _level, level
from tactus.cli import main

CURVES = (
    (level.momentary_loudness, "loudness_lufs", 0.4),
    (level.short_term_loudness, "loudness_lufs", 3.0),
    (level.rms_curve, "rms_dbfs", 0.05),
    (level.peak_curve, "sample_peak_dbfs", 0.05),
)
FUNCTIONS = [f for f, _, _ in CURVES] + [level.loudness_range]


def tone(rate, seconds, db=-23):
    t = np.arange(round(rate * seconds)) / rate
    mono = 10 ** (db / 20) * np.sin(2 * np.pi * 1000 * t)
    return np.column_stack((mono, mono))


def test_k_weighting_matches_itu_48k_coefficients():
    expected = np.array(
        [
            [
                1.53512485958697,
                -2.69169618940638,
                1.19839281085285,
                1,
                -1.69065929318241,
                0.73248077421585,
            ],
            [1, -2, 1, 1, -1.99004745483398, 0.99007225036621],
        ]
    )
    np.testing.assert_allclose(_level.k_weighting(48000), expected, atol=2e-13, rtol=0)


@pytest.mark.parametrize("rate", [22050, 44100, 48000, 96000])
def test_loudness_matches_independent_meter_block_powers(rate, loudness_reference):
    # End exactly on both grids: the library otherwise includes a partial final window.
    x = np.random.default_rng(3).normal(0, 0.03, (rate * 6, 2))
    original = x.copy()
    # Library implementation uses a separate lfilter per stage/channel, and its own grid.
    for fn, window in [(level.momentary_loudness, 0.4), (level.short_term_loudness, 3)]:
        expected = loudness_reference(f"curve-{rate}-{window}", x, rate)["blockwise_lufs"]
        got = fn(x, rate, hop_s=window / 2)
        np.testing.assert_allclose(got["loudness_lufs"], expected, atol=2e-8)
    np.testing.assert_array_equal(x, original)


@pytest.mark.parametrize("rate", [44100, 48000, 96000])
def test_calibrated_tone_and_stereo_polarity(rate):
    x = tone(rate, 4)
    opposite = x * [1, -1]
    for fn in [level.momentary_loudness, level.short_term_loudness]:
        values = np.array(fn(x, rate)["loudness_lufs"])
        np.testing.assert_allclose(values, -23, atol=0.1)
        np.testing.assert_allclose(fn(opposite, rate)["loudness_lufs"], values, atol=1e-12)
        mono = np.array(fn(x[:, 0], rate)["loudness_lufs"])
        np.testing.assert_allclose(values - mono, 10 * np.log10(2), atol=1e-10)


def test_loudness_channel_weights():
    rate = 8000
    mono = tone(rate, 4)[:, 0]
    expected = level.short_term_loudness(mono, rate)["loudness_lufs"][-1]
    for ch, weight in enumerate([1, 1, 1, 1.41, 1.41]):
        x = np.zeros((len(mono), 5))
        x[:, ch] = mono
        value = level.short_term_loudness(x, rate)["loudness_lufs"][-1]
        assert value == pytest.approx(expected + 10 * np.log10(weight), abs=1e-10)


@pytest.mark.parametrize("fn,field,window_s", CURVES)
def test_silence_short_inputs_and_window_end_grid(fn, field, window_s):
    rate = 8000
    window = round(window_s * rate)
    assert fn(np.zeros(window - 1), rate)[field] == []
    exact = fn(np.zeros(window), rate)
    assert exact[field] == [None]
    assert exact["times_s"] == [window_s]
    result = fn(np.zeros(window + 2 * 800 + 7), rate, hop_s=0.01)
    assert result["times_s"] == pytest.approx((window + np.arange(21) * 80) / rate)
    assert result[field] == [None] * 21
    assert result["window_samples"] == window
    assert result["hop_samples"] == 80


def test_rms_and_peak_exact_windows_channels_and_tail():
    x = np.array([[1.0, -1.0], [0, 0], [0.5, 0], [0, -0.25], [9, 9]])
    original = x.copy()
    rms = level.rms_curve(x, 10, window_s=0.2, hop_s=0.2)
    peaks = level.peak_curve(x, 10, window_s=0.2, hop_s=0.2)
    assert rms["times_s"] == [0.2, 0.4]  # fifth sample is not a complete window
    np.testing.assert_allclose(rms["rms_dbfs"], 10 * np.log10([0.5, (0.25 + 0.0625) / 4]))
    np.testing.assert_allclose(peaks["sample_peak_dbfs"], 20 * np.log10([1, 0.5]))
    np.testing.assert_array_equal(x, original)


def test_quiet_windows_after_loud_audio_keep_energy():
    # A whole-file cumulative sum would erase the quiet window through cancellation.
    x = np.r_[np.ones(1000), np.full(1000, 1e-10), np.zeros(1000)]
    result = level.rms_curve(x, 1000, window_s=1, hop_s=1)
    assert result["rms_dbfs"] == pytest.approx([0, -200, None])


def test_k_filter_is_not_reset_at_each_window_and_quiet_values_are_ungated():
    rate = 8000
    x = tone(rate, 2, -90)
    curve = level.momentary_loudness(x, rate, hop_s=0.2)
    assert all(v < -70 for v in curve["loudness_lufs"])
    from scipy.signal import sosfilt

    weighted = sosfilt(_level.k_weighting(rate), x, axis=0)
    expected = -0.691 + 10 * np.log10(np.mean(np.sum(weighted[1600:4800] ** 2, axis=1)))
    assert curve["loudness_lufs"][1] == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize(
    "levels,expected",
    [([-20, -30], 10), ([-20, -15], 5), ([-40, -20], 20), ([-50, -35, -20, -35, -50], 15)],
)
def test_ebu_3342_synthetic_plateaus(levels, expected):
    rate = 8000
    x = np.concatenate([tone(rate, 20, db) for db in levels])
    result = level.loudness_range(x, rate)
    assert result["lra_lu"] == pytest.approx(expected, abs=1)
    assert result["duration_s"] == len(levels) * 20
    assert result["provisional"] == (len(levels) * 20 < 60)
    assert result["gated_blocks"] > 0
    assert result["lra_lu"] == result["high_lufs"] - result["low_lufs"]


def test_range_gate_uses_energy_mean_and_absolute_gate():
    # Ten -60 LUFS blocks would move a dB arithmetic-mean gate too low; the energy gate
    # excludes them. Adding sub-absolute-gate blocks must not change the result.
    values = np.array([-20.0, -30.0] + [-60.0] * 10)
    expected_gate = 10 * np.log10(np.mean(10 ** (values / 10))) - 20
    got = _level.range_statistics(values)
    assert got["relative_gate_lufs"] == pytest.approx(expected_gate)
    assert got["gated_blocks"] == 2
    assert got["lra_lu"] == 10
    assert _level.range_statistics(np.r_[values, [-80.0] * 100]) == got


@pytest.mark.parametrize(
    "audio", [np.zeros(8000 * 10), np.zeros(1), tone(8000, 2), tone(8000, 4, -100)]
)
def test_unavailable_lra_is_null_without_warnings(audio):
    result = level.loudness_range(audio, 8000)
    assert result["lra_lu"] is None
    assert result["gated_blocks"] == 0
    assert result["provisional"] is True


def test_new_functions_do_not_import_pyloudnorm(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.startswith(("pyloudnorm", "pymixtool")):
            raise AssertionError(f"unexpected import: {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    for fn in FUNCTIONS:
        fn(tone(8000, 4), 8000)


@pytest.mark.parametrize("fn", FUNCTIONS)
@pytest.mark.parametrize(
    "audio,rate",
    [
        ([], 8000),
        (np.zeros((2, 0)), 8000),
        (np.zeros((2, 2, 2)), 8000),
        ([np.nan], 8000),
        ([np.inf], 8000),
        ([1j], 8000),
        ([1], 0),
        ([1], True),
        ([1], 8000.0),
    ],
)
def test_invalid_audio_and_rate(fn, audio, rate):
    with pytest.raises(ValueError):
        fn(audio, rate)


@pytest.mark.parametrize(
    "fn", [level.momentary_loudness, level.short_term_loudness, level.loudness_range]
)
def test_loudness_rejects_unsupported_rate_and_layout(fn):
    with pytest.raises(ValueError, match="8000"):
        fn(np.ones(100), 1000)
    with pytest.raises(ValueError, match="channels"):
        fn(np.ones((100, 6)), 48000)


@pytest.mark.parametrize("fn,field,window_s", CURVES)
@pytest.mark.parametrize("hop", [0, -1, float("nan"), float("inf"), 1e-20, 100, True])
def test_invalid_hop(fn, field, window_s, hop):
    with pytest.raises(ValueError):
        fn(np.ones(800), 8000, hop_s=hop)


@pytest.mark.parametrize("fn", FUNCTIONS)
def test_cli_help_and_saved_json(tmp_path, capsys, fn):
    with pytest.raises(SystemExit) as error:
        main(["analyze", "level", fn.__name__, "--help"])
    assert error.value.code == 0
    assert fn.__doc__.splitlines()[0] in " ".join(capsys.readouterr().out.split())
    path = tmp_path / "tone.wav"
    x = tone(8000, 4)
    sf.write(path, x, 8000, subtype="DOUBLE")
    out = tmp_path / "measurements"
    assert main(["analyze", "level", fn.__name__, str(path), "--out", str(out)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["analysis"] == "level." + fn.__name__
    assert report["revision"] == 1
    assert report["result"] == fn(x, 8000)
    assert report["input_sha256"] and report["provenance"]
    assert json.loads(next(out.glob("*/result.json")).read_text()) == report


def test_cli_silence_and_bad_window(tmp_path, capsys):
    path = tmp_path / "silence.wav"
    sf.write(path, np.zeros(8000), 8000)
    assert main(["analyze", "level", "rms_curve", str(path)]) == 0
    assert set(json.loads(capsys.readouterr().out)["result"]["rms_dbfs"]) == {None}
    assert main(["analyze", "level", "rms_curve", str(path), "--window-s", "-1"]) != 0
    assert "window_s" in json.loads(capsys.readouterr().out)["error"]["message"]
