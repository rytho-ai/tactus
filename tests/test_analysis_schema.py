"""Data declarations checked against actual windows, arrays and serialized artifacts."""

import inspect
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus.analysis import CATEGORIES, image, level, rhythm, schema, spectral
from tactus.cli import main
from tactus.inputs.pool import hash_file

BUILTINS = [fn for module in CATEGORIES.values() for fn in module.ANALYSES]


def same(actual, expected):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key in expected:
            same(actual[key], expected[key])
    elif isinstance(expected, (list, tuple)):
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected, strict=True):
            same(a, b)
    else:
        np.testing.assert_array_equal(actual, expected)


@pytest.mark.parametrize("fn", BUILTINS, ids=lambda fn: fn.__name__)
@pytest.mark.parametrize("silent", [False, True])
def test_every_builtin_is_additive_finite_and_classifies_all_existing_fields(fn, silent):
    rate = 22050
    audio = np.zeros(rate) if silent else 0.1 * np.sin(2 * np.pi * 1000 * np.arange(rate) / rate)
    before = audio.copy()
    result = fn(audio, rate)
    expected = inspect.unwrap(fn)(audio, rate)
    schema = result["schema"]
    same({k: v for k, v in result.items() if k != "schema"}, expected)
    np.testing.assert_array_equal(audio, before)
    assert json.loads(json.dumps(schema, allow_nan=False)) == schema
    assert schema["version"] == (2 if fn.__name__ == "beats" else 1)  # beats points to beats_s with slice/end
    assert schema["input"] == {
        "sample_rate": rate,
        "frames": len(audio),
        "time_origin": "input_start",
    }
    fields = schema["fields"]
    classified = [
        *fields,
        *schema["coordinate_keys"],
        *schema["parameter_keys"],
        *schema["auxiliary_keys"],
    ]
    assert len(classified) == len(set(classified))
    assert set(classified) == set(expected)
    assert all(d["shape"] in {"series", "grid", "events", "summary"} for d in fields.values())
    for key, d in fields.items():
        if d["shape"] == "grid":
            assert d["dimensions"] == ["y", "x"]
            x = result[d["x"]["key"]]
            y = result[d["y"]["key"]] if "key" in d["y"] else d["y"]["values"]
            assert np.shape(result[key]) == (len(y), len(x))
        elif d["shape"] == "series" and d.get("layout") not in {"records", "rows"}:
            x = result[d["x"]["key"]] if "key" in d["x"] else d["x"]["values"]
            assert len(x) == len(result[key])


@pytest.mark.parametrize(
    "name,key",
    [
        ("rms_curve", "rms_dbfs"),
        ("peak_curve", "sample_peak_dbfs"),
        ("crest_factor_curve", "crest_factor_db"),
        ("momentary_loudness", "loudness_lufs"),
        ("short_term_loudness", "loudness_lufs"),
    ],
)
def test_end_times_use_actual_rounded_windows(name, key):
    rate = 8001
    kwargs = {"hop_s": 0.01006}
    if name.endswith("_curve"):
        kwargs["window_s"] = 0.02006
    audio = np.ones(rate * 4) * 0.2
    result = getattr(level, name)(audio, rate, **kwargs)
    x = result["schema"]["fields"][key]["x"]
    window, hop = result["window_samples"], result["hop_samples"]
    assert x["at"] == "end" and x["origin"] == "input_start"
    assert x["width"] == window / rate and x["hop"] == hop / rate
    assert x["padding"] == "none" and x["end_exclusive"]
    np.testing.assert_array_equal(
        result["times_s"], (window + np.arange(len(result[key])) * hop) / rate
    )
    short = getattr(level, name)(audio[: window - 1], rate, **kwargs)
    assert short[key] == [] and short["times_s"] == []
    assert short["schema"]["fields"][key]["x"] == x
    # The first value actually measures frames [0, window), not a centered window.
    if name == "rms_curve":
        signal = np.arange(window + hop, dtype=float) / window
        measured = level.rms_curve(signal, rate, **kwargs)
        expected = 20 * np.log10(np.sqrt(np.mean(signal[:window] ** 2)))
        assert measured[key][0] == pytest.approx(expected)
        assert x["width"] != kwargs["window_s"]


@pytest.mark.parametrize(
    "name,key",
    [
        ("stft", "level_db"),
        ("mel", "power"),
        ("chroma", "chroma"),
        ("mfcc", "coefficients"),
        ("bandwidth", "bandwidth_hz"),
        ("rolloff", "rolloff_hz"),
        ("flatness", "flatness"),
    ],
)
def test_centered_data_uses_custom_fft_and_hop(name, key):
    result = getattr(spectral, name)(np.zeros(1001), 22050, n_fft=1024, hop=127)
    d = result["schema"]["fields"][key]
    assert d["x"]["at"] == "centre"
    assert d["x"]["width"] == 1024 / 22050
    assert d["x"]["hop"] == 127 / 22050
    assert d["x"]["padding"] == "zero"
    np.testing.assert_allclose(result["times_s"], np.arange(len(result["times_s"])) * 127 / 22050)
    assert len(result["times_s"]) == (9 if name == "stft" else 8)
    if name == "stft":
        assert result["times_s"][-1] > 1001 / 22050


def test_centroid_width_matches_scipy_short_window():
    with pytest.warns(UserWarning, match="nperseg"):
        result = spectral.centroid(np.ones(1500), 8000, hop_s=0.1)
    axis = result["schema"]["fields"]["centroid_hz"]["x"]
    assert axis["width"] == 1500 / 8000
    assert axis["hop"] == (1500 - (2048 - 800)) / 8000
    np.testing.assert_allclose(np.diff(result["times_s"]), axis["hop"])


@pytest.mark.parametrize("name", ["cqt", "vqt"])
def test_q_windows_are_per_frequency_and_not_a_single_guessed_width(name):
    result = getattr(spectral, name)(np.zeros(211), 22050, fmin=220, n_bins=6, hop=71)
    d = result["schema"]["fields"]["magnitude"]
    assert d["x"]["at"] == "centre" and d["x"]["width_axis"] == "y"
    assert d["x"]["width"] == {"key": "window_samples", "factor": 1 / 22050}
    widths = result["window_samples"] / 22050
    assert len(set(widths)) > 1
    with pytest.raises(ValueError, match="no interval ends"):
        schema.ends(result, "magnitude")  # widths are per frequency row, not per time
    assert d["y"]["spacing"] == "logarithmic"
    np.testing.assert_allclose(np.diff(np.log2(result["freqs_hz"])), 1 / 12)


def test_nonuniform_categorical_and_normalized_axes():
    mel = spectral.mel(np.zeros(100), 22050)
    d = mel["schema"]["fields"]["power"]
    assert d["y"]["unit"] == "Hz" and d["y"]["spacing"] == "nonuniform"
    assert not np.allclose(np.diff(mel["freqs_hz"]), np.diff(mel["freqs_hz"])[0])
    chroma = spectral.chroma(np.zeros(100), 22050)
    d = chroma["schema"]["fields"]["chroma"]
    assert d["y"]["quantity"] == "pitch_class" and d["y"]["spacing"] == "categorical"
    assert d["value"]["normalization"] == "per_frame_max" and d["value"]["silence"] == 0
    assert chroma[d["y"]["key"]] == [
        "C",
        "C#",
        "D",
        "D#",
        "E",
        "F",
        "F#",
        "G",
        "G#",
        "A",
        "A#",
        "B",
    ]
    tempo = rhythm.tempogram(np.zeros(100), 8000, hop_s=0.011, window_s=0.457)
    d = tempo["schema"]["fields"]["tempogram"]
    assert d["x"]["width"] == tempo["window_frames"] * tempo["hop_samples"] / 8000
    assert d["x"]["width"] != 0.457
    assert d["x"]["at"] == "centre" and d["y"]["spacing"] == "nonuniform"
    np.testing.assert_allclose(tempo["bpms"], 60 * 8000 / (tempo["hop_samples"] * tempo["lags"]))


@pytest.mark.parametrize(
    "filterbank,unit", [("mel", "dB difference"), ("log", "log10(1 + magnitude) difference")]
)
def test_onset_strength_declares_compensated_points_not_false_window_centers(filterbank, unit):
    rate = 22050
    audio = np.zeros(rate)
    audio[5000] = 1
    result = rhythm.onset_strength(audio, rate, hop_s=0.007, lag=3, filterbank=filterbank)
    d = result["schema"]["fields"]["strength"]
    assert d["x"]["at"] == "point" and "width" not in d["x"]
    assert d["x"]["alignment"]["delay_frames"] == 1024 // (2 * result["hop_samples"])
    assert d["x"]["alignment"]["difference_lag_frames"] == 3
    assert d["y"]["unit"] == unit
    np.testing.assert_array_equal(
        result["times_s"], np.arange(len(result["strength"])) * result["hop_samples"] / rate
    )


def test_beats_intervals_use_each_actual_pair(monkeypatch):
    monkeypatch.setattr(
        rhythm.pyqmdsp,
        "beats",
        lambda *args: {
            "beats_s": np.array([0.12, 0.65, 1.24, 1.8]),
            "bpm": 103.0,
            "tempo_curve": 60 / np.diff([0.12, 0.65, 1.24, 1.8]),
        },
    )
    r = rhythm.beats(np.zeros(2000), 1000)
    d = r["schema"]["fields"]
    assert d["beats_s"]["x"]["at"] == "point"
    assert d["tempo_curve"]["x"]["at"] == "start"
    starts = schema.coordinates(r, "tempo_curve")
    np.testing.assert_array_equal(starts, r["beats_s"][:-1])
    np.testing.assert_array_equal(schema.ends(r, "tempo_curve"), r["beats_s"][1:])
    np.testing.assert_allclose(r["tempo_curve"], 60 / (schema.ends(r, "tempo_curve") - starts))
    assert "values" not in d["tempo_curve"]["x"] and r["schema"]["version"] == 2


def test_clipping_event_selectors_recover_true_sample_span():
    audio = np.zeros((100, 2))
    audio[17:23, 1] = 0.9
    r = level.clipping(audio, 1000)
    d = r["schema"]["fields"]["first_positions"]
    event = r["first_positions"][0]
    x = d["x"]
    assert event[x["column"]] * x["factor"] == 0.017
    assert event[x["width"]["column"]] * x["width"]["factor"] == 0.006
    assert event[d["attributes"]["channel"]["column"]] == 1


def test_record_series_selectors_and_units():
    t = np.arange(22050) / 22050
    audio = 0.2 * np.sin(2 * np.pi * 1000 * t)
    for name, key in [("peaks", "peaks"), ("band_levels", "bands")]:
        result = getattr(spectral, name)(audio, 22050)
        d = result["schema"]["fields"][key]
        assert d["layout"] == "records"
        assert d["x"]["unit"] == "Hz" and d["y"]["unit"] == "dB re full-scale sine"
        for row in result[key]:
            assert isinstance(row[d["x"]["key"]], float)
            assert isinstance(row[d["y"]["key"]], float)


@pytest.mark.parametrize(
    "category,name,key",
    [
        ("spectral", "stft", "level_db"),
        ("spectral", "spectrum", "level_db"),
        ("spectral", "centroid", "centroid_hz"),
        ("level", "rms_curve", "rms_dbfs"),
    ],
)
def test_cli_encodings_match_declarations_and_implementation_source(
    tmp_path, capsys, category, name, key
):
    wav = tmp_path / "silent.wav"
    sf.write(wav, np.zeros(4096), 22050, subtype="DOUBLE")
    assert main(["analyze", category, name, str(wav), "--out", str(tmp_path / "out")]) == 0
    report = json.loads(capsys.readouterr().out)
    r = report["result"]
    desc = r["schema"]["fields"][key]
    value = desc["value"] if desc["shape"] == "grid" else desc["y"]
    encoding = value["special_values"][0]
    if name == "stft":
        with np.load(r[key]["file"]) as arrays:
            assert np.isneginf(arrays[r[key]["key"]]).all()
        assert encoding["npz"] == "-inf"
    else:
        assert set(r[key]) == {None}
        assert encoding["json"] == "null"
    source = report["provenance"]["callable"]["source"]
    assert Path(source["path"]).name == f"{category}.py"
    assert source["sha256"] == hash_file(Path(source["path"]))
    direct = getattr(CATEGORIES[category], name)(np.zeros(4096), 22050)
    assert r["schema"] == direct["schema"]


def test_schema_is_fresh_and_images_are_unchanged():
    audio = np.zeros(200)
    result = spectral.stft(audio, 22050)
    assert image(result) == image(inspect.unwrap(spectral.stft)(audio, 22050))
    result["schema"]["fields"]["level_db"]["x"]["unit"] = "broken"
    assert spectral.stft(audio, 22050)["schema"]["fields"]["level_db"]["x"]["unit"] == "s"
    r = rhythm.onset_strength(audio, np.int64(22050), n_fft=np.int64(1024), lag=np.int64(2))
    json.dumps(r["schema"], allow_nan=False)


def _clicks(seconds, rate=22050, bpm=120):
    audio = 0.01 * np.sin(2 * np.pi * 330 * np.arange(int(seconds * rate)) / rate)
    for start in np.arange(0, seconds, 60 / bpm):
        i = int(start * rate)
        audio[i : i + 200] += np.hanning(400)[200:] * 0.8
    return audio


@pytest.mark.parametrize("fn", BUILTINS, ids=lambda fn: fn.__name__)
def test_no_builtin_schema_grows_with_the_input(fn):
    """A declaration points to result data; it never copies arrays that scale with the input."""
    rate = 22050
    short, long = (json.dumps(fn(_clicks(s), rate)["schema"]) for s in (6, 24))
    assert len(long) - len(short) < 64, (len(short), len(long))  # digits of frames/durations only
