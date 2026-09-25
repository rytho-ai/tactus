"""Exercise the pool store and the material()/tool() resolvers with a scratch TACTUS_POOL."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

import pytest

from tactus.inputs import MaterialError, ToolError, material, pool, tool


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
