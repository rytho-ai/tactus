"""diff.compare: level alignment, where outputs differ, new outputs, causes and the layer."""

import pytest

from tactus import RunError, diff, run

SONG = """import numpy as np
def render(*, level: float = 0.5, busy: bool = False, noise: bool = False):
    sr = 48000
    t = np.arange(sr * 4) / sr
    hits = (t % 0.5 < 0.1) | (busy & (t >= 1.0) & (t < 2.0) & (t % 0.25 < 0.1))
    kick = 0.6 * np.sin(2 * np.pi * 60 * t) * hits
    keys = 0.3 * np.sin(2 * np.pi * 440 * t)
    stems = {"kick": level * kick, "keys": level * keys}
    if noise:
        stems["noise"] = level * 0.01 * np.random.default_rng(1).standard_normal(len(t))
    return {"sample_rate": sr, "outputs": {**stems, "mix": sum(stems.values())}}
"""


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    root = tmp_path / "work"
    root.mkdir()
    (root / "song.py").write_text(SONG)

    def render(name, **params):
        run(root / "song.py", out=root / "runs" / name, params=params, checkpoint=False)
        return root / "runs" / name

    return root, render


def test_identical_and_level_only_runs_have_no_differences(work):
    _, render = work
    a, same, quiet = render("a"), render("same"), render("quiet", level=0.25)
    result = diff.compare(a, same)
    assert result["gain_db"] == 0.0 and {o["kind"] for o in result["outputs"].values()} == {"same"}
    result = diff.compare(a, quiet)
    assert result["gain_db"] == pytest.approx(-6.02, abs=0.01)
    assert {o["kind"] for o in result["outputs"].values()} == {"same"}
    assert "the render parameters differ" in result["causes"]


def test_an_edit_is_located_in_its_output_and_time(work):
    _, render = work
    result = diff.compare(render("a"), render("b", busy=True, level=0.4), bpm=120)
    assert result["window_s"] == 0.25 and result["gain_db"] == pytest.approx(-1.94, abs=0.02)
    outputs = result["outputs"]
    assert outputs["keys"] == {"kind": "same", "ranges": []}
    assert outputs["kick"]["kind"] == "changed" and outputs["mix"]["kind"] == "changed"
    ranges = outputs["kick"]["ranges"]
    assert (
        ranges[0]["start_s"] >= 1.0
        and ranges[-1]["end_s"] <= 2.0
        and all(r["major"] for r in ranges)
    )
    assert all(r["res_db"] > -40 and r["rel_db"] > -20 for r in ranges)


def test_new_and_missing_outputs_are_named(work):
    _, render = work
    a, b = render("a"), render("b", noise=True)
    forward, back = diff.compare(a, b), diff.compare(b, a)
    assert (
        forward["outputs"]["noise"]["kind"] == "new"
        and back["outputs"]["noise"]["kind"] == "missing"
    )
    span = forward["outputs"]["noise"]["ranges"]
    assert span[0]["start_s"] == 0.0 and span[-1]["end_s"] == 4.0
    assert (
        forward["outputs"]["kick"]["kind"] == "same"
        and forward["outputs"]["mix"]["kind"] == "changed"
    )


def test_a_missing_run_is_an_error(work):
    root, render = work
    with pytest.raises(RunError):
        diff.compare(render("a"), root / "missing")
