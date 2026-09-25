"""Exercise excerpt selection/slicing of an existing run: identity with the source run's
frames, stateful correctness, request/validate-phase rejections, tampered-source detection,
and the manifest fields an excerpt adds — including that it is exact even when the source
work's own render is nondeterministic, which is the whole reason excerpt exists instead of
`run --range` re-rendering.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import RunError, excerpt, run

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
# excerpt must, because it never re-renders anything — it slices what was published.
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

# Uses np.random without a fixed seed: two renders of this source produce different audio.
# This is the exact failure mode `run --range` had (a nondeterministic instrument re-rendered
# a different performance for the slice) and the reason excerpt slices published outputs
# instead: an excerpt of one run's outputs is exact to that run, never to a fresh render.
NONDETERMINISTIC_SOURCE = """\
import numpy as np

def render():
    rate = 2000
    n = rate * 2
    noise = np.random.default_rng().uniform(-0.3, 0.3, n)
    return {"sample_rate": rate, "outputs": {"mix": noise}}
"""


def test_excerpt_slice_is_identical_to_the_same_frames_of_the_source_run_mono_and_stereo(
    tmp_path,
):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    full = run(entry, out=tmp_path / "full")
    cut = excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.5, 1.0])
    start_frame, end_frame = round(0.5 * RATE), round(1.0 * RATE)
    for name in ("mono", "stereo"):
        full_audio = read_int32(full["outputs"][name])
        cut_audio = read_int32(cut["outputs"][name])
        np.testing.assert_array_equal(cut_audio, full_audio[start_frame:end_frame])


def test_stateful_tail_and_loop_phase_survive_slicing(tmp_path):
    entry = source(tmp_path, STATEFUL_SOURCE)
    full = run(entry, out=tmp_path / "full")
    cut = excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.6, 1.1])
    start_frame, end_frame = round(0.6 * RATE), round(1.1 * RATE)
    full_audio = read_int32(full["outputs"]["mix"])
    cut_audio = read_int32(cut["outputs"]["mix"])
    np.testing.assert_array_equal(cut_audio, full_audio[start_frame:end_frame])


def test_clamped_output_and_omitted_output_in_one_excerpt(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    full = run(entry, out=tmp_path / "full")
    # "early" (500 frames) ends before start_frame (800): omitted.
    # "short" (2000 frames) has an end (3000) beyond its length: clamped to 2000.
    result = excerpt(
        tmp_path / "full", out=tmp_path / "cut", range=[0.4, 1.5], outputs=["short", "early"]
    )
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["range"]["omitted"] == ["early"]
    assert set(manifest["outputs"]) == {"short"}
    assert manifest["outputs"]["short"]["source_frames"] == RATE
    assert manifest["outputs"]["short"]["frames"] == RATE - 800

    start_frame = round(0.4 * RATE)
    full_short = read_int32(full["outputs"]["short"])
    cut_short = read_int32(result["outputs"]["short"])
    np.testing.assert_array_equal(cut_short, full_short[start_frame:])


def test_open_ended_range_reaches_each_outputs_own_end(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    full = run(entry, out=tmp_path / "full")
    result = excerpt(tmp_path / "full", out=tmp_path / "cut", range=[1.5, None])
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["range"]["end_seconds"] is None
    assert manifest["range"]["end_frame"] is None
    start_frame = round(1.5 * RATE)
    for name in ("mono", "stereo"):
        full_audio = read_int32(full["outputs"][name])
        cut_audio = read_int32(result["outputs"][name])
        np.testing.assert_array_equal(cut_audio, full_audio[start_frame:])
    # "short" (2000 frames) and "early" (500 frames) both end before 1.5s (3000 frames).
    assert set(manifest["range"]["omitted"]) == {"short", "early"}


def test_excerpt_of_a_nondeterministic_render_is_exact_to_its_own_run_not_a_fresh_one(tmp_path):
    entry = source(tmp_path, NONDETERMINISTIC_SOURCE)
    run_a = run(entry, out=tmp_path / "a")
    run_b = run(entry, out=tmp_path / "b")
    a_audio = read_int32(run_a["outputs"]["mix"])
    b_audio = read_int32(run_b["outputs"]["mix"])
    assert not np.array_equal(a_audio, b_audio)  # the two renders really do differ

    cut = excerpt(tmp_path / "a", out=tmp_path / "cut", range=[0.5, 1.0])
    start_frame, end_frame = round(0.5 * RATE), round(1.0 * RATE)
    cut_audio = read_int32(cut["outputs"]["mix"])
    np.testing.assert_array_equal(cut_audio, a_audio[start_frame:end_frame])


def test_tampered_source_output_fails_source_corrupt_and_leaves_no_out_dir(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    full = run(entry, out=tmp_path / "full")
    audio_path = Path(full["outputs"]["mono"])
    audio_path.write_bytes(audio_path.read_bytes() + b"\x00")
    with pytest.raises(RunError) as failure:
        excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.0, 0.5])
    assert failure.value.code == "source_corrupt"
    assert not (tmp_path / "cut").exists()


def test_missing_run_directory_fails_invalid_request_request(tmp_path):
    with pytest.raises(RunError) as failure:
        excerpt(tmp_path / "nonexistent", out=tmp_path / "cut", range=[0.0, 0.5])
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "request")
    assert not (tmp_path / "cut").exists()


def test_run_directory_without_manifest_fails_invalid_request_request(tmp_path):
    run_dir = tmp_path / "not-a-run"
    run_dir.mkdir()
    with pytest.raises(RunError) as failure:
        excerpt(run_dir, out=tmp_path / "cut", range=[0.0, 0.5])
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "request")
    assert not (tmp_path / "cut").exists()


def test_existing_out_directory_fails_invalid_request_request(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    run(entry, out=tmp_path / "full")
    (tmp_path / "cut").mkdir()
    with pytest.raises(RunError) as failure:
        excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.0, 0.5])
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "request")


def test_all_requested_outputs_empty_in_range_fails_invalid_request_validate(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    run(entry, out=tmp_path / "full")
    with pytest.raises(RunError) as failure:
        excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.4, 1.5], outputs=["early"])
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "validate")
    assert not (tmp_path / "cut").exists()


def test_unknown_output_name_fails_invalid_request_validate(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    run(entry, out=tmp_path / "full")
    with pytest.raises(RunError) as failure:
        excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.0, 0.5], outputs=["nonexistent"])
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "validate")
    assert not (tmp_path / "cut").exists()


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
    run(entry, out=tmp_path / "full")
    with pytest.raises(RunError) as failure:
        excerpt(tmp_path / "full", out=tmp_path / "cut", range=range_)
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "request")
    assert not (tmp_path / "cut").exists()


@pytest.mark.parametrize("outputs", [[], [123], [""], "mono"])
def test_invalid_outputs_rejected_at_request_phase(tmp_path, outputs):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    run(entry, out=tmp_path / "full")
    with pytest.raises(RunError) as failure:
        excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.0, 0.5], outputs=outputs)
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "request")
    assert not (tmp_path / "cut").exists()


def test_manifest_source_fields_point_at_the_run_and_its_manifest_hash(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    full = run(entry, out=tmp_path / "full")
    result = excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.5, 1.0])
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["kind"] == "tactus.excerpt"
    assert manifest["source"]["run"] == str((tmp_path / "full").resolve())
    source_manifest_bytes = Path(full["manifest"]).read_bytes()
    assert (
        manifest["source"]["manifest_sha256"] == hashlib.sha256(source_manifest_bytes).hexdigest()
    )
    assert "receipt" not in result


def test_outputs_without_narrowing_publishes_every_source_output(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    run(entry, out=tmp_path / "full")
    result = excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.0, 0.1])
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert set(manifest["outputs"]) == {"mono", "stereo", "short", "early"}


def test_excerpt_outputs_report_zero_clipped_samples_and_a_peak(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    run(entry, out=tmp_path / "full")
    result = excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.5, 1.0])
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert manifest["format_version"] == 2
    for ref in manifest["outputs"].values():
        assert ref["clipped_samples"] == 0
        assert ref["peak_dbfs"] is None or ref["peak_dbfs"] <= 0


def test_excerpt_accepts_a_v1_source_manifest_without_level_keys(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    full = run(entry, out=tmp_path / "full")
    manifest_path = Path(full["manifest"])
    manifest = json.loads(manifest_path.read_text())
    manifest["format_version"] = 1
    for ref in manifest["outputs"].values():
        del ref["peak_dbfs"]
        del ref["clipped_samples"]
    manifest_path.write_text(json.dumps(manifest))
    result = excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.5, 1.0])
    assert set(result["outputs"]) == {"mono", "stereo", "short"}


def test_excerpt_rejects_an_unsupported_source_manifest_format_version(tmp_path):
    entry = source(tmp_path, MULTI_OUTPUT_SOURCE)
    full = run(entry, out=tmp_path / "full")
    manifest_path = Path(full["manifest"])
    manifest = json.loads(manifest_path.read_text())
    manifest["format_version"] = 3
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(RunError) as failure:
        excerpt(tmp_path / "full", out=tmp_path / "cut", range=[0.0, 0.5])
    assert failure.value.code == "source_corrupt"
    assert not (tmp_path / "cut").exists()
