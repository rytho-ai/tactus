"""Exercise range/outputs selection: identity with a full render, stateful correctness,
request/validate-phase rejections, and the manifest/receipt fields a range run adds.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import RunError, run

RATE = 2000


def source(tmp_path: Path, text: str) -> Path:
    root = tmp_path / "authoring"
    root.mkdir(exist_ok=True)
    path = root / "song.py"
    path.write_text(text, encoding="utf-8")
    return path


def read_int32(path: str) -> np.ndarray:
    audio, rate = sf.read(path, dtype="int32", always_2d=True)
    assert rate == RATE
    return audio


MULTI_OUTPUT_SOURCE = """\
import numpy as np

RATE = 2000

def render():
    n = RATE * 2
    t = np.arange(n) / RATE
    mono = 0.5 * np.sin(2 * np.pi * 3 * t)
    stereo = np.stack([mono, -mono], axis=1)
    short = mono[: RATE]
    early = mono[: RATE // 4]
    return {
        "sample_rate": RATE,
        "outputs": {"mono": mono, "stereo": stereo, "short": short, "early": early},
    }
"""

# A feedback delay with a long ringing tail, plus a loop whose phase depends on the
# absolute sample index rather than resetting at any window start. A self-windowed
# render of this source would not match the same span of the full render; a correct
# post-render slice must, because it never re-renders anything.
STATEFUL_SOURCE = """\
import numpy as np

def render():
    rate = 2000
    n = int(rate * 1.5)
    t = np.arange(n)
    loop = 0.2 * np.sin(2 * np.pi * 7 * t / rate)
    impulse = np.zeros(n)
    impulse[::400] = 1.0
    delay = 30
    feedback = 0.85
    tail = np.zeros(n)
    for i in range(n):
        prior = tail[i - delay] if i >= delay else 0.0
        tail[i] = impulse[i] + feedback * prior
    mix = np.clip(0.3 * loop + 0.3 * np.tanh(tail), -1, 1)
    return {"sample_rate": rate, "outputs": {"mix": mix}}
"""


def test_range_slice_is_identical_to_the_same_frames_of_a_full_run_mono_and_stereo(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    full = run(entry, out=tmp_path / "full")
    ranged = run(entry, out=tmp_path / "ranged", range=[0.5, 1.0])
    start_frame, end_frame = round(0.5 * RATE), round(1.0 * RATE)
    for name in ("mono", "stereo"):
        full_audio = read_int32(full["outputs"][name])
        range_audio = read_int32(ranged["outputs"][name])
        np.testing.assert_array_equal(range_audio, full_audio[start_frame:end_frame])


def test_stateful_tail_and_loop_phase_survive_slicing(tmp_path):
    entry = source(tmp_path, STATEFUL_SOURCE)
    full = run(entry, out=tmp_path / "full")
    ranged = run(entry, out=tmp_path / "ranged", range=[0.6, 1.1])
    start_frame, end_frame = round(0.6 * RATE), round(1.1 * RATE)
    full_audio = read_int32(full["outputs"]["mix"])
    range_audio = read_int32(ranged["outputs"]["mix"])
    np.testing.assert_array_equal(range_audio, full_audio[start_frame:end_frame])


def test_clamped_output_and_omitted_output_in_one_run(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    full = run(entry, out=tmp_path / "full")
    # "early" (500 frames) ends before start_frame (800): omitted.
    # "short" (2000 frames) has an end (3000) beyond its length: clamped to 2000.
    result = run(entry, out=tmp_path / "ranged", range=[0.4, 1.5], outputs=["short", "early"])
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["range"]["omitted"] == ["early"]
    assert set(manifest["outputs"]) == {"short"}
    assert manifest["outputs"]["short"]["source_frames"] == RATE
    assert manifest["outputs"]["short"]["frames"] == RATE - 800

    start_frame = round(0.4 * RATE)
    full_short = read_int32(full["outputs"]["short"])
    range_short = read_int32(result["outputs"]["short"])
    np.testing.assert_array_equal(range_short, full_short[start_frame:])


def test_all_requested_outputs_empty_in_range_fails_invalid_request_validate(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out", range=[0.4, 1.5], outputs=["early"])
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "validate")
    assert not (tmp_path / "out").exists()


def test_unknown_output_name_fails_invalid_request_validate(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out", outputs=["nonexistent"])
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "validate")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "range_",
    [
        [-1, 1],  # negative start
        [1, 0.5],  # reversed
        [1, 1],  # zero-length
        [float("nan"), 1],
        [0, float("nan")],
        [float("inf"), 2],
        [0, float("inf")],
        [0],  # wrong shape
        [0, 1, 2],  # wrong shape
        "0:1",  # not a list
        [None, 1],
        [0, "1"],
    ],
)
def test_invalid_range_rejected_at_request_phase(tmp_path, range_):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out", range=range_)
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "request")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("outputs", [[], [123], [""], "mono"])
def test_invalid_outputs_rejected_at_request_phase(tmp_path, outputs):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "out", outputs=outputs)
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "request")
    assert not (tmp_path / "out").exists()


def test_open_ended_range_reaches_each_outputs_own_end(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    full = run(entry, out=tmp_path / "full")
    result = run(entry, out=tmp_path / "ranged", range=[1.5, None])
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["range"]["end_seconds"] is None
    assert manifest["range"]["end_frame"] is None
    start_frame = round(1.5 * RATE)
    for name in ("mono", "stereo"):
        full_audio = read_int32(full["outputs"][name])
        range_audio = read_int32(result["outputs"][name])
        np.testing.assert_array_equal(range_audio, full_audio[start_frame:])
    # "short" (2000 frames) and "early" (500 frames) both end before 1.5s (3000 frames).
    assert set(manifest["range"]["omitted"]) == {"short", "early"}


def test_manifest_and_receipt_fields_without_range_or_outputs_are_unchanged(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    result = run(entry, out=tmp_path / "out")
    manifest = json.loads(Path(result["manifest"]).read_text())
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert "range" not in manifest
    assert all("source_frames" not in ref for ref in manifest["outputs"].values())
    assert receipt["range"] is None
    assert receipt["outputs"] is None


def test_receipt_records_range_and_outputs(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    result = run(entry, out=tmp_path / "out", range=[0.5, 1.0], outputs=["mono", "stereo"])
    receipt = json.loads(Path(result["receipt"]).read_text())
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert receipt["outputs"] == ["mono", "stereo"]
    assert receipt["range"] == manifest["range"]
    assert receipt["range"] == {
        "start_seconds": 0.5,
        "end_seconds": 1.0,
        "start_frame": round(0.5 * RATE),
        "end_frame": round(1.0 * RATE),
        "omitted": [],
    }


def test_outputs_without_range_publishes_only_those_names(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    result = run(entry, out=tmp_path / "out", outputs=["mono"])
    manifest = json.loads(Path(result["manifest"]).read_text())
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert set(manifest["outputs"]) == {"mono"}
    assert "source_frames" not in manifest["outputs"]["mono"]
    assert "range" not in manifest
    assert receipt["outputs"] == ["mono"]
    assert receipt["range"] is None
