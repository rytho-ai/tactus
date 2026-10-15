"""Public declarations work with independent measurements and reject structural mistakes."""

import copy
import json
import os
import subprocess
import sys

import numpy as np
import pytest
import soundfile as sf

from tactus.analysis import level, rhythm, schema, spectral


def waveform():
    rate = 8000
    times = np.arange(rate) / rate
    samples = np.sin(2 * np.pi * 1000 * times)
    samples[2000:6000] = 0
    raw = {"sample_clock": times, "left": samples, "gain": 1.0}
    fields = {
        "left": schema.series(
            schema.axis("sample_clock", "time", "s", "linear", origin="input_start", at="point"),
            schema.value("sample_amplitude", "FS"),
        )
    }
    result = schema.attach(
        raw,
        sample_rate=rate,
        frames=len(samples),
        fields=fields,
        coordinate_keys=["sample_clock"],
        parameter_keys=["gain"],
    )
    return raw, fields, result


def test_custom_waveform_preserves_arrays_and_resolves_true_gap_samples():
    raw, fields, result = waveform()
    assert "schema" not in raw
    assert result["left"] is raw["left"]
    assert result["sample_clock"] is raw["sample_clock"]
    x = schema.coordinates(result, "left")
    np.testing.assert_array_equal(x, raw["sample_clock"])
    selected = (x >= 0.25) & (x < 0.75)
    assert np.count_nonzero(selected) == 4000
    assert not result["left"][selected].any()
    x[:] = -1
    assert raw["sample_clock"][0] == 0
    fields["left"]["x"]["unit"] = "changed"
    assert result["schema"]["fields"]["left"]["x"]["unit"] == "s"


@pytest.mark.parametrize("dimensions", [("y", "x"), ("x", "y")])
def test_grid_does_not_require_time_or_builtin_field_names(dimensions):
    matrix = np.arange(6).reshape(2, 3)
    data = matrix if dimensions == ("y", "x") else matrix.T
    r = schema.attach(
        {"bins": [200, 320, 500], "channels": ["left", "right"], "energy": data},
        sample_rate=8000,
        frames=8000,
        fields={
            "energy": schema.grid(
                schema.axis("bins", "frequency", "Hz", "nonuniform"),
                schema.axis("channels", "channel", "name", "categorical"),
                schema.value("power", "FS^2"),
                dimensions=dimensions,
            )
        },
        coordinate_keys=["bins", "channels"],
    )
    schema.validate(r)
    np.testing.assert_array_equal(schema.coordinates(r, "energy"), [200, 320, 500])
    np.testing.assert_array_equal(schema.coordinates(r, "energy", "y"), ["left", "right"])
    assert r["energy"] is data
    r["energy"] = data.T
    with pytest.raises(ValueError, match="coordinate length"):
        schema.validate(r)


def test_record_events_keep_labels_and_scale_frame_intervals():
    r = schema.attach(
        {
            "regions": [
                {"a": 100, "b": 300, "label": "phrase"},
                {"a": 600, "b": 600, "label": "cue"},
            ]
        },
        sample_rate=1000,
        frames=1000,
        fields={
            "regions": schema.events(
                schema.axis(
                    "a",
                    "time",
                    "s",
                    "nonuniform",
                    end_key="b",
                    factor=0.001,
                    origin="input_start",
                    at="start",
                ),
                layout="records",
                attributes={"label": {"unit": "text"}},
            )
        },
    )
    np.testing.assert_allclose(schema.coordinates(r, "regions"), [0.1, 0.6])
    r["regions"][0]["b"] = 50
    with pytest.raises(ValueError, match="ends must not precede"):
        schema.validate(r)


def test_record_frequency_series_and_row_spans():
    records = schema.attach(
        {
            "resonances": [
                {"frequency": 320.0, "height": -6.0},
                {"frequency": 900.0, "height": -12.0},
            ]
        },
        sample_rate=8000,
        frames=8000,
        fields={
            "resonances": schema.series(
                schema.axis("frequency", "frequency", "Hz", "nonuniform"),
                {"key": "height", **schema.value("level", "dB")},
                layout="records",
            )
        },
    )
    np.testing.assert_array_equal(schema.coordinates(records, "resonances"), [320, 900])
    rows = schema.attach(
        {"intervals": [(10, 20), (30, 0)]},
        sample_rate=1000,
        frames=100,
        fields={
            "intervals": schema.events(
                schema.axis(
                    quantity="time",
                    unit="s",
                    column=0,
                    factor=0.001,
                    at="start",
                    width={"column": 1, "factor": 0.001},
                ),
                layout="rows",
            )
        },
    )
    np.testing.assert_array_equal(schema.coordinates(rows, "intervals"), [0.01, 0.03])
    rows["intervals"] = [(10, -20)]
    with pytest.raises(ValueError, match="width.*nonnegative"):
        schema.validate(rows)


def test_inline_irregular_widths_and_per_row_grid_support():
    r = schema.attach(
        {"local_tempo": [120, 100]},
        sample_rate=1000,
        frames=2000,
        fields={
            "local_tempo": schema.series(
                schema.axis(
                    values=[0.2, 0.7], quantity="time", unit="s", at="start", width=[0.5, 0.6]
                ),
                schema.value("tempo", "BPM"),
            )
        },
    )
    np.testing.assert_array_equal(schema.coordinates(r, "local_tempo"), [0.2, 0.7])
    r["schema"]["fields"]["local_tempo"]["x"]["width"] = [0.5]
    with pytest.raises(ValueError, match="width count"):
        schema.validate(r)
    q = spectral.cqt(np.zeros(100), 8000, fmin=200, n_bins=3)
    schema.validate(q)
    q["schema"]["fields"]["magnitude"]["x"]["width_axis"] = "x"
    with pytest.raises(ValueError, match="width count"):
        schema.validate(q)


def test_unknown_semantics_stay_unknown_and_summary_has_no_coordinates():
    r = schema.attach(
        {"trend": [2.0, 3.0], "score": None},
        sample_rate=1000,
        frames=100,
        fields={
            "trend": {"shape": "series"},
            "score": schema.summary("score", "1", sentinel="null", meaning="unavailable"),
        },
    )
    assert r["schema"]["fields"]["trend"] == {"shape": "series"}
    for field in ("trend", "score"):
        with pytest.raises(ValueError, match="undeclared"):
            schema.coordinates(r, field)
    assert json.loads(json.dumps(r, allow_nan=False)) == r
    with pytest.raises(ValueError, match="explicit declaration"):
        schema.coordinates({"old": [1, 2]}, "old")


@pytest.mark.parametrize(
    "edit,match",
    [
        (lambda r: r["schema"].update(version=3), "version"),
        (lambda r: r["schema"].update(version=True), "version"),
        (lambda r: r["schema"].update(parameter_keys=["gain", "left"]), "overlap"),
        (lambda r: r.update(extra=0), "every result key"),
        (lambda r: r["schema"].update(extra=float("nan")), "finite JSON"),
        (lambda r: r["schema"]["input"].update(sample_rate=0), "sample_rate"),
        (lambda r: r["schema"]["fields"]["left"].update(shape="blob"), "shape"),
        (lambda r: r["schema"]["fields"]["left"]["x"].update(key="absent"), "selector cannot"),
        (lambda r: r["schema"]["fields"]["left"]["x"].update(values=[1]), "exactly one"),
        (lambda r: r["schema"]["fields"]["left"]["x"].update(at="end"), "require width"),
        (lambda r: r["schema"]["fields"]["left"]["x"].update(at="guess"), "at"),
        (lambda r: r["schema"]["fields"]["left"]["x"].update(hop=-1), "hop"),
        (lambda r: r["schema"]["fields"]["left"]["x"].update(width=-1), "width"),
        (lambda r: r.update(sample_clock=[float("inf")] * 8000), "finite"),
    ],
)
def test_validation_reports_malformed_declarations_without_mutation(edit, match):
    _, _, r = waveform()
    edit(r)
    metadata = copy.deepcopy(r["schema"])
    with pytest.raises(ValueError, match=match):
        schema.validate(r)
    assert repr(r["schema"]) == repr(metadata)


def test_coordinates_never_loads_attachment_paths(tmp_path):
    _, _, r = waveform()
    r["sample_clock"] = {
        "file": str(tmp_path / "missing.npz"),
        "key": "x",
        "dtype": "<f8",
        "shape": [8000],
    }
    with pytest.raises(ValueError, match="load NPZ"):
        schema.coordinates(r, "left")
    with pytest.raises(ValueError, match="load NPZ"):
        schema.validate(r)
    assert not list(tmp_path.iterdir())


def test_redeclaring_a_builtin_keeps_the_source_schema_independent():
    original = level.rms_curve(np.ones(1000), 8000)
    fields = copy.deepcopy(original["schema"]["fields"])
    fields["rms_dbfs"]["y"]["unit"] = "custom unit"
    changed = schema.attach(
        original,
        sample_rate=np.int64(8000),
        frames=np.int64(1000),
        fields=fields,
        coordinate_keys=["times_s"],
        parameter_keys=["hop_samples", "window_samples"],
    )
    assert original["schema"]["fields"]["rms_dbfs"]["y"]["unit"] == "dBFS"
    assert changed["rms_dbfs"] is original["rms_dbfs"]
    assert changed["schema"]["fields"]["rms_dbfs"]["y"]["unit"] == "custom unit"
    empty = rhythm.beats(np.zeros(100), 8000)
    assert schema.coordinates(empty, "beats_s").size == 0


def test_custom_cli_uses_public_schema_and_serializes_arrays(tmp_path):
    (tmp_path / "pyproject.toml").write_text("""[project]
name = "schema-work"
version = "0.0.0"
dependencies = ["tactus"]
[tool.tactus.analysis]
"custom.waveform" = "observations:waveform"
""")
    (tmp_path / "observations.py").write_text("""import numpy as np
from tactus.analysis import schema

def waveform(audio, sample_rate):
    return schema.attach(
        {"clock": np.arange(len(audio)) / sample_rate, "signal": audio},
        sample_rate=sample_rate, frames=len(audio), coordinate_keys=["clock"],
        fields={"signal": schema.series(
            schema.axis("clock", "time", "s", "linear", origin="input_start", at="point"),
            schema.value("amplitude", "FS"),
        )},
    )
""")
    sf.write(tmp_path / "input.wav", np.arange(64) / 64, 8000, subtype="FLOAT")
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "tactus.cli",
            "analyze",
            "custom",
            "waveform",
            "input.wav",
            "--out",
            "results",
        ],
        cwd=tmp_path,
        env={**os.environ, "TACTUS_PROJECT_ROOT": str(tmp_path)},
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(process.stdout)
    assert report["analysis"] == "custom.waveform"
    assert report["result"]["schema"]["fields"]["signal"]["x"]["at"] == "point"
    result = report["result"]
    for key in ("clock", "signal"):
        ref = result[key]
        with np.load(tmp_path / ref["file"]) as arrays:
            result[key] = arrays[ref["key"]]
    schema.validate(result)
    np.testing.assert_array_equal(schema.coordinates(result, "signal"), np.arange(64) / 8000)


def intervals_result(x_axis, **raw):
    data = {"onsets": np.array([0.0, 0.5, 1.25, 2.0]), "level": np.array([1.0, 2.0, 3.0]), **raw}
    return schema.attach(
        data, sample_rate=1000, frames=3000, coordinate_keys=[k for k in data if k != "level"],
        fields={"level": schema.series(x_axis, schema.value("level", "1"))},
    )


def test_slice_and_end_point_to_existing_data_with_version_2():
    x = schema.axis("onsets", "time", "s", "nonuniform", origin="input_start", at="start",
                    slice=[0, -1], end={"key": "onsets", "slice": [1, None]})
    r = intervals_result(x)
    assert r["schema"]["version"] == 2
    np.testing.assert_array_equal(schema.coordinates(r, "level"), [0.0, 0.5, 1.25])
    np.testing.assert_array_equal(schema.ends(r, "level"), [0.5, 1.25, 2.0])


def test_version_1_is_kept_without_slice_or_end_and_rejects_them():
    x = schema.axis("starts", "time", "s", "nonuniform", origin="input_start", at="start", width=0.25)
    r = intervals_result(x, starts=np.array([0.0, 1.0, 2.0]))
    assert r["schema"]["version"] == 1
    np.testing.assert_array_equal(schema.ends(r, "level"), [0.25, 1.25, 2.25])
    r["schema"]["fields"]["level"]["x"]["slice"] = [0, 3]
    with pytest.raises(ValueError, match="need version 2"):
        schema.validate(r)


@pytest.mark.parametrize(
    "change,match",
    [
        ({"slice": [0]}, "slice"),
        ({"slice": [0.5, None]}, "slice"),
        ({"slice": [1, None], "end": {"key": "onsets", "slice": [0, -1]}}, "must not precede"),
        ({"slice": [0, -1], "end": {"key": "onsets"}}, "match coordinates"),
        ({"slice": [0, -1], "end": {"key": "onsets", "slice": [1, None]}, "end_key": "onsets"}, "not both"),
    ],
)
def test_slice_and_end_are_checked(change, match):
    x = {**schema.axis("onsets", "time", "s", "nonuniform", origin="input_start", at="start",
                       width=0.1), **change}
    if "end" in change or "end_key" in change:
        x.pop("width")
    with pytest.raises(ValueError, match=match):
        intervals_result(x)


def test_ends_of_centre_end_and_point_axes():
    for at, expected in (("centre", [0.05, 0.55, 1.3]), ("end", [0.0, 0.5, 1.25])):
        x = schema.axis("onsets", "time", "s", "nonuniform", origin="input_start", at=at,
                        width=0.1, slice=[0, -1])
        np.testing.assert_allclose(schema.ends(intervals_result(x), "level"), expected)
    x = schema.axis("onsets", "time", "s", "nonuniform", origin="input_start", at="point", slice=[1, None])
    with pytest.raises(ValueError, match="no interval ends"):
        schema.ends(intervals_result(x), "level")
