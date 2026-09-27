"""Exercise the pool store and the material()/tool()/load_audio() resolvers with a scratch
TACTUS_POOL."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import run
from tactus.inputs import MaterialError, ToolError, load_audio, material, pool, tool


@pytest.fixture(autouse=True)
def scratch_pool(tmp_path, monkeypatch):
    """Point every test at a private pool so nothing touches the real machine pool."""
    root = tmp_path / "pool"
    monkeypatch.setenv("TACTUS_POOL", str(root))
    return root


def digest_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_put_is_idempotent_and_uses_two_char_fanout(tmp_path, scratch_pool):
    source = tmp_path / "sample.bin"
    source.write_bytes(b"some pinned bytes")
    digest = pool.put(source)
    entry = scratch_pool / digest[:2] / digest
    assert entry.is_file()
    assert entry.read_bytes() == source.read_bytes()

    mtime_before = entry.stat().st_mtime_ns
    again = pool.put(source)
    assert again == digest
    assert entry.stat().st_mtime_ns == mtime_before  # not rewritten


def test_material_resolves_after_file_moved_or_renamed(tmp_path):
    source = tmp_path / "original.wav"
    source.write_bytes(b"identical bytes regardless of filename")
    digest = pool.put(source)
    moved = tmp_path / "renamed.wav"
    source.rename(moved)  # original path no longer exists; bytes already in the pool
    resolved = material(f"sha256:{digest}")
    assert resolved.is_file()
    assert digest_of(resolved) == digest


def test_corrupt_entry_is_reported_distinctly(tmp_path, scratch_pool):
    source = tmp_path / "clean.bin"
    source.write_bytes(b"clean bytes")
    digest = pool.put(source)
    entry = scratch_pool / digest[:2] / digest
    entry.write_bytes(b"tampered bytes")
    with pytest.raises(MaterialError) as failure:
        material(f"sha256:{digest}")
    assert failure.value.reason == "corrupt"
    assert failure.value.ref == f"sha256:{digest}"


def test_missing_material_names_ref_pool_and_fix(scratch_pool):
    digest = "0" * 64
    with pytest.raises(MaterialError) as failure:
        material(f"sha256:{digest}")
    assert failure.value.reason == "missing"
    message = str(failure.value)
    assert digest in message
    assert str(scratch_pool) in message
    assert "tactus material add" in message


@pytest.mark.parametrize(
    "ref",
    [
        "0" * 64,  # no prefix
        "sha256:" + "A" * 64,  # uppercase
        "sha256:" + "0" * 10,  # too short
        "sha256:../../etc/passwd" + "0" * 40,
        "sha256:",
        "md5:" + "0" * 32,
    ],
)
def test_invalid_refs_are_rejected_before_any_path_is_built(ref, scratch_pool):
    with pytest.raises(MaterialError) as failure:
        material(ref)
    assert failure.value.reason == "invalid_ref"
    assert not scratch_pool.exists()  # no pool directory was even created/touched


def test_tool_records_sha256_for_an_existing_executable_path(tmp_path):
    script = tmp_path / "fake-tool.sh"
    script.write_text("#!/bin/sh\necho hi\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    resolved = tool(str(script))
    assert resolved == script.resolve()
    assert digest_of(resolved) == hashlib.sha256(script.read_bytes()).hexdigest()


def test_tool_raises_for_absent_name():
    with pytest.raises(ToolError) as failure:
        tool("definitely-not-a-real-executable-name")
    assert failure.value.reason == "missing"


def test_tool_raises_for_absent_path(tmp_path):
    with pytest.raises(ToolError):
        tool(str(tmp_path / "nope"))


def test_tool_resolves_via_path_lookup():
    # `sh` is a safe, near-universal POSIX executable to resolve by name.
    if os.name != "posix":
        pytest.skip("PATH lookup exercised on POSIX only")
    resolved = tool("sh")
    assert resolved.is_file()


def test_tool_records_kind_file_for_a_resolved_file(tmp_path):
    script = tmp_path / "fake-tool.sh"
    script.write_text("#!/bin/sh\necho hi\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    tool(str(script))
    from tactus.inputs import _tools

    assert _tools[str(script)]["kind"] == "file"


def test_tool_on_a_folder_hashes_the_tree_and_returns_the_folder(tmp_path):
    bundle = tmp_path / "Some.vst3"
    (bundle / "Contents").mkdir(parents=True)
    (bundle / "Contents" / "plugin.so").write_bytes(b"fake plugin bytes")
    resolved = tool(str(bundle))
    assert resolved == bundle.resolve()

    from tactus.inputs import _tools
    from tactus.inputs.tree import digest_of_tree

    expected_digest, _ = digest_of_tree(bundle)
    entry = _tools[str(bundle)]
    assert entry["kind"] == "tree"
    assert entry["sha256"] == expected_digest
    assert entry["path"] == str(bundle.resolve())


def test_tool_on_a_folder_digest_is_stable_across_calls(tmp_path):
    bundle = tmp_path / "Some.vst3"
    (bundle / "Contents").mkdir(parents=True)
    (bundle / "Contents" / "plugin.so").write_bytes(b"fake plugin bytes")
    from tactus.inputs import _tools

    tool(str(bundle))
    first = _tools[str(bundle)]["sha256"]
    tool(str(bundle))
    second = _tools[str(bundle)]["sha256"]
    assert first == second


def test_material_resolves_a_tree_ref_to_a_materialized_folder(tmp_path):
    from tactus.inputs import tree

    root = tmp_path / "instrument"
    (root / "samples").mkdir(parents=True)
    (root / "samples" / "note.wav").write_bytes(b"fake sample bytes")
    (root / "piano.sfz").write_text("<region> sample=samples/note.wav\n")
    ref = tree.add(root)
    resolved = material(ref)
    assert (resolved / "piano.sfz").read_text() == "<region> sample=samples/note.wav\n"
    assert (resolved / "samples" / "note.wav").read_bytes() == b"fake sample bytes"


def test_material_missing_tree_ref_gives_missing_reason(scratch_pool):
    with pytest.raises(MaterialError) as failure:
        material(f"tree:sha256:{'0' * 64}")
    assert failure.value.reason == "missing"


def test_material_rejects_a_malformed_tree_ref(scratch_pool):
    with pytest.raises(MaterialError) as failure:
        material("tree:sha256:not-hex")
    assert failure.value.reason == "invalid_ref"


# ---------------------------------------------------------------------------
# load_audio
# ---------------------------------------------------------------------------


def test_load_audio_mono_to_stereo_duplicates(tmp_path, scratch_pool):
    x = np.array([[0.5], [-0.5], [0.25]], dtype=np.float32)
    source = tmp_path / "m.wav"
    sf.write(source, x, 48000, subtype="PCM_16")
    ref = f"sha256:{pool.put(source)}"
    y = load_audio(ref, 48000, channels=2)
    assert y.shape == (3, 2)
    assert np.allclose(y[:, 0], y[:, 1], atol=1e-3)


def test_load_audio_stereo_to_mono_is_mean(tmp_path, scratch_pool):
    x = np.array([[1.0, 0.0], [0.5, -0.5]], dtype=np.float32)
    source = tmp_path / "s.wav"
    sf.write(source, x, 48000, subtype="PCM_16")
    ref = f"sha256:{pool.put(source)}"
    y = load_audio(ref, 48000, channels=1)
    assert y.shape == (2, 1)
    assert abs(y[0, 0] - 0.5) < 1e-3
    assert abs(y[1, 0] - 0.0) < 1e-3


def test_load_audio_bad_channel_combo_raises(tmp_path, scratch_pool):
    x = np.zeros((10, 2), dtype=np.float32)
    source = tmp_path / "s2.wav"
    sf.write(source, x, 48000, subtype="PCM_16")
    ref = f"sha256:{pool.put(source)}"
    with pytest.raises(ValueError):
        load_audio(ref, 48000, channels=3)


def test_load_audio_exact_resample_preserves_pitch_and_length(tmp_path, scratch_pool):
    sr0 = 44100
    n = int(sr0 * 0.1)
    t = np.arange(n) / sr0
    tone = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    source = tmp_path / "tone.wav"
    sf.write(source, tone[:, None], sr0, subtype="PCM_16")
    ref = f"sha256:{pool.put(source)}"
    y = load_audio(ref, 48000, channels=1)
    expected_n = round(n * 48000 / sr0)
    assert abs(y.shape[0] - expected_n) <= 1
    z = y[:, 0]
    crossings = np.sum(np.diff(np.sign(z[np.abs(z) > 1e-6])) != 0)
    expected_crossings = 2 * 440 * (y.shape[0] / 48000)
    assert abs(crossings - expected_crossings) / expected_crossings < 0.15


def test_load_audio_trim_db_drops_leading_silence(tmp_path, scratch_pool):
    silence = np.zeros(100, dtype=np.float32)
    body = np.ones(50, dtype=np.float32)
    x = np.concatenate([silence, body])[:, None]
    source = tmp_path / "trim.wav"
    sf.write(source, x, 48000, subtype="FLOAT")
    ref = f"sha256:{pool.put(source)}"
    y = load_audio(ref, 48000, channels=1, trim_db=-40.0)
    assert y.shape[0] == 50
    assert abs(y[0, 0] - 1.0) < 1e-3


def test_load_audio_no_trim_when_trim_db_none(tmp_path, scratch_pool):
    x = np.concatenate([np.zeros(20, dtype=np.float32), np.ones(5, dtype=np.float32)])[:, None]
    source = tmp_path / "notrim.wav"
    sf.write(source, x, 48000, subtype="FLOAT")
    ref = f"sha256:{pool.put(source)}"
    y = load_audio(ref, 48000, channels=1)
    assert y.shape[0] == 25


def test_load_audio_accepts_a_path_material_already_returned(tmp_path, scratch_pool):
    x = np.ones((10, 2), dtype=np.float32) * 0.5
    source = tmp_path / "s.wav"
    sf.write(source, x, 48000, subtype="PCM_16")
    ref = f"sha256:{pool.put(source)}"
    path = material(ref)
    y = load_audio(path, 48000, channels=2)
    assert y.shape == (10, 2)
    assert np.allclose(y, 0.5, atol=1e-3)


def test_load_audio_ref_is_recorded_in_a_run_receipt(tmp_path, scratch_pool):
    sample = tmp_path / "kick.wav"
    sf.write(sample, np.ones((10, 2), dtype=np.float32) * 0.5, 48000, subtype="PCM_16")
    digest = pool.put(sample)

    entry = tmp_path / "work" / "song.py"
    entry.parent.mkdir()
    entry.write_text(
        f"""\
from tactus import load_audio

KICK = "sha256:{digest}"


def render(*, gain: float = 1.0):
    kick = load_audio(KICK, 48000, channels=2) * gain
    return {{"sample_rate": 48000, "outputs": {{"kick": kick}}}}
""",
        encoding="utf-8",
    )
    result = run(entry, out=tmp_path / "out")
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert {"ref": f"sha256:{digest}"} in receipt["materials"]
