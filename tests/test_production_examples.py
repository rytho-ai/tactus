"""Protect loop-tail exclusion and the documented channel/master handoff patterns."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import run

EXAMPLES = Path(__file__).parents[1] / "skills" / "examples"


def test_phrases_wrap_between_valid_starts_without_tail_or_source_mutation():
    phrase = runpy.run_path(str(EXAMPLES / "boundaries.py"))["phrase"]
    # The source body is an authored grid; the trailing five frames are not loopable.
    body = np.arange(24, dtype=np.float64)
    source = np.concatenate((body, np.full(5, 999.0)))
    original = source.copy()
    for index in range(17):
        cut = phrase(source, body_end=24, starts=(0, 8, 16), frames=8, index=index)
        np.testing.assert_array_equal(cut, body[(index % 3) * 8 : (index % 3 + 1) * 8])
        assert len(cut) == 8
        cut[:] = 0  # A phrase owns its data, even when the processor changes it in place.
    np.testing.assert_array_equal(source, original)
    with pytest.raises(ValueError, match="fit completely"):
        phrase(source, body_end=24, starts=(0, 20), frames=8, index=0)


def test_stem_example_sums_before_master_and_keeps_master_separate(tmp_path):
    render = runpy.run_path(str(EXAMPLES / "boundaries.py"))["render"]
    outputs = render(master_gain_db=-6.0)["outputs"]
    np.testing.assert_array_equal(
        outputs["pre_master"], outputs["channel_a_post"] + outputs["channel_b_post"]
    )
    np.testing.assert_allclose(outputs["mix"], outputs["pre_master"] * 10 ** (-6 / 20))
    result = run(EXAMPLES / "boundaries.py", out=tmp_path / "printed")
    assert set(result["outputs"]) == {
        "channel_a_post", "channel_b_post", "pre_master", "mix"
    }
    for path in result["outputs"].values():
        audio, rate = sf.read(path, always_2d=True)
        assert rate == 8000
        assert audio.shape == (64000, 2)
        assert np.isfinite(audio).all() and np.max(np.abs(audio)) < 1


def test_minimal_entry_runs_without_materials(tmp_path):
    result = run(EXAMPLES / "minimal.py", out=tmp_path / "minimal")
    audio, rate = sf.read(result["outputs"]["mix"])
    assert rate == 48000 and audio.shape == (48000,)
    assert np.isfinite(audio).all() and np.max(np.abs(audio)) <= 0.2 + 2**-23


@pytest.mark.parametrize(
    ("name", "outputs"),
    [
        ("voices.py", {"lead", "bell", "mix"}),
        ("physical.py", {"metal", "strings", "mix"}),
        ("textures.py", {"grain_pad", "riser", "mix"}),
    ],
)
def test_synth_instrument_examples_run_deterministically(tmp_path, name, outputs):
    first = run(EXAMPLES / name, out=tmp_path / "a")
    second = run(EXAMPLES / name, out=tmp_path / "b")
    assert set(first["outputs"]) == outputs
    for output, path in first["outputs"].items():
        audio, rate = sf.read(path, always_2d=True)
        again, _ = sf.read(second["outputs"][output], always_2d=True)
        assert rate == 48000 and audio.shape[1] == 2
        assert np.isfinite(audio).all() and 0.01 < np.max(np.abs(audio)) < 1
        np.testing.assert_array_equal(audio, again)


def test_devices_example_runs_deterministically(tmp_path):
    first = run(EXAMPLES / "devices.py", out=tmp_path / "a")
    second = run(EXAMPLES / "devices.py", out=tmp_path / "b")
    assert set(first["outputs"]) == {"melody", "break", "hats", "mix"}
    for name, path in first["outputs"].items():
        audio, rate = sf.read(path, always_2d=True)
        again, _ = sf.read(second["outputs"][name], always_2d=True)
        assert rate == 48000 and audio.shape == (480000, 2)
        assert np.isfinite(audio).all() and 0.01 < np.max(np.abs(audio)) < 1
        np.testing.assert_array_equal(audio, again)


def test_route_example_takes_a_performance_and_gives_out_its_map(tmp_path):
    import json

    from tactus import RunError
    from tactus.analysis import join

    walk = tmp_path / "walk.json"
    walk.write_text('{"steps": [{"room": "hall", "bars": 2}, {"room": "stair", "bars": 3}]}')
    result = run(EXAMPLES / "route.py", out=tmp_path / "walk", param_files={"route": walk})
    time_map = json.loads(Path(result["map"]).read_text())
    rate = 48000
    bar = round(rate * 60 / 96 * 4)
    assert time_map["outputs"]["walk"]["grid"]["bars"] == [i * bar for i in range(5)]
    assert [s["label"] for s in time_map["outputs"]["walk"]["lanes"]["route"]["items"]] == [
        "hall", "stair"]
    assert set(time_map["segments"]) == {"hall", "stair", "roof"}
    for name in ("hall", "stair", "roof"):
        loop, _ = sf.read(result["outputs"][name])
        assert len(loop) == 2 * bar == time_map["segments"][name]["end"]
        # each room loops cleanly: its wrap steps no more than its own bar line
        (wrap,) = join.seams(loop, rate, wrap=True)["joins"]
        assert wrap["step"] < 0.01
    bad = tmp_path / "bad.json"
    bad.write_text('{"steps": [{"room": "cellar", "bars": 1}]}')
    with pytest.raises(RunError) as failure:
        run(EXAMPLES / "route.py", out=tmp_path / "bad", param_files={"route": bad})
    assert failure.value.code == "invalid_parameters" and "room must be one of" in str(
        failure.value)


def test_builtin_instrument_example_runs_without_external_assets(tmp_path):
    result = run(EXAMPLES / "instruments.py", out=tmp_path / "instruments")
    assert set(result["outputs"]) == {"piano", "mix"}
    for path in result["outputs"].values():
        audio, rate = sf.read(path, always_2d=True)
        assert rate == 24000 and audio.shape == (144000, 2)
        assert np.isfinite(audio).all() and 0 < np.max(abs(audio)) < 1
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert receipt["tools"] == [] and receipt["materials"] == []
