"""Exercise `tactus.inputs.tree`: manifest digest, import, and verified materialization."""

from __future__ import annotations

import os

import pytest

from tactus.inputs import pool, tree


@pytest.fixture(autouse=True)
def scratch_pool(tmp_path, monkeypatch):
    """Point every test at a private pool so nothing touches the real machine pool."""
    root = tmp_path / "pool"
    monkeypatch.setenv("TACTUS_POOL", str(root))
    return root


def make_instrument(root):
    """A small nested "instrument": a program that `#include`s a sibling by relative path."""
    (root / "samples").mkdir(parents=True)
    (root / "samples" / "note.wav").write_bytes(b"fake sample bytes")
    (root / "programs").mkdir()
    (root / "programs" / "piano.sfz").write_text(
        '<region> sample=../samples/note.wav\n#include "shared.sfzi"\n'
    )
    (root / "programs" / "shared.sfzi").write_text("<control> default_path=../samples/\n")
    return root


def test_digest_of_tree_is_the_same_regardless_of_walk_order_or_location(tmp_path):
    a = make_instrument(tmp_path / "a")
    b = make_instrument(tmp_path / "elsewhere" / "b")
    digest_a, entries_a = tree.digest_of_tree(a)
    digest_b, entries_b = tree.digest_of_tree(b)
    assert digest_a == digest_b
    assert entries_a == entries_b
    assert entries_a == sorted(entries_a)


def test_a_changed_file_changes_the_digest(tmp_path):
    root = make_instrument(tmp_path / "instrument")
    before, _ = tree.digest_of_tree(root)
    (root / "samples" / "note.wav").write_bytes(b"different bytes now")
    after, _ = tree.digest_of_tree(root)
    assert before != after


def test_a_renamed_file_changes_the_digest(tmp_path):
    root = make_instrument(tmp_path / "instrument")
    before, _ = tree.digest_of_tree(root)
    (root / "samples" / "note.wav").rename(root / "samples" / "renamed.wav")
    (root / "programs" / "piano.sfz").write_text(
        '<region> sample=../samples/renamed.wav\n#include "shared.sfzi"\n'
    )
    after, _ = tree.digest_of_tree(root)
    assert before != after


def test_an_extra_file_changes_the_digest(tmp_path):
    root = make_instrument(tmp_path / "instrument")
    before, _ = tree.digest_of_tree(root)
    (root / "samples" / "extra.wav").write_bytes(b"an extra file")
    after, _ = tree.digest_of_tree(root)
    assert before != after


def test_a_symlink_is_rejected(tmp_path):
    root = make_instrument(tmp_path / "instrument")
    target = tmp_path / "outside.wav"
    target.write_bytes(b"outside bytes")
    (root / "samples" / "linked.wav").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        tree.digest_of_tree(root)


def test_a_symlinked_directory_is_rejected(tmp_path):
    root = make_instrument(tmp_path / "instrument")
    other = tmp_path / "other-dir"
    other.mkdir()
    (root / "linked-dir").symlink_to(other, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        tree.digest_of_tree(root)


@pytest.mark.skipif(os.name != "posix", reason="special files are POSIX-specific")
def test_a_special_file_is_rejected(tmp_path):
    root = make_instrument(tmp_path / "instrument")
    fifo = root / "samples" / "a.fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="non-regular"):
        tree.digest_of_tree(root)


def test_empty_folder_is_rejected(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    with pytest.raises(ValueError, match="no regular files"):
        tree.digest_of_tree(root)


def test_add_stores_every_file_and_the_manifest_as_pool_blobs(tmp_path, scratch_pool):
    root = make_instrument(tmp_path / "instrument")
    digest, entries = tree.digest_of_tree(root)
    ref = tree.add(root)
    assert ref == f"tree:sha256:{digest}"
    manifest_path = pool.path_for(digest)
    assert manifest_path is not None
    assert tree.parse_manifest(manifest_path.read_bytes()) == entries
    for _relative, file_digest in entries:
        assert pool.path_for(file_digest) is not None


def test_add_is_idempotent(tmp_path):
    root = make_instrument(tmp_path / "instrument")
    first = tree.add(root)
    second = tree.add(root)
    assert first == second


def test_resolve_rebuilds_the_exact_tree_and_relative_reads_work(tmp_path):
    root = make_instrument(tmp_path / "instrument")
    digest, _ = tree.digest_of_tree(root)
    tree.add(root)
    materialized = tree.resolve(digest)
    assert materialized.is_dir()
    assert (materialized / "samples" / "note.wav").read_bytes() == b"fake sample bytes"
    program = (materialized / "programs" / "piano.sfz").read_text()
    assert "../samples/note.wav" in program
    included = materialized / "programs" / "shared.sfzi"
    assert included.is_file()


def test_resolve_reuses_an_existing_correct_materialized_folder(tmp_path):
    root = make_instrument(tmp_path / "instrument")
    digest, _ = tree.digest_of_tree(root)
    tree.add(root)
    first = tree.resolve(digest)
    marker = first / "programs" / "piano.sfz"
    before = marker.stat().st_ino
    second = tree.resolve(digest)
    assert second == first
    assert marker.stat().st_ino == before


def test_resolve_missing_manifest_raises_tree_error_missing(scratch_pool):
    with pytest.raises(tree.TreeError) as failure:
        tree.resolve("0" * 64)
    assert failure.value.reason == "missing"


def test_resolve_corrupt_manifest_blob_raises_tree_error_corrupt(tmp_path, scratch_pool):
    root = make_instrument(tmp_path / "instrument")
    digest, _ = tree.digest_of_tree(root)
    tree.add(root)
    manifest_entry = scratch_pool / digest[:2] / digest
    manifest_entry.write_bytes(b"tampered manifest bytes")
    with pytest.raises(tree.TreeError) as failure:
        tree.resolve(digest)
    assert failure.value.reason == "corrupt"


def test_resolve_missing_file_blob_raises_tree_error_missing(tmp_path, scratch_pool):
    root = make_instrument(tmp_path / "instrument")
    digest, entries = tree.digest_of_tree(root)
    tree.add(root)
    _relative, file_digest = entries[0]
    (scratch_pool / file_digest[:2] / file_digest).unlink()
    with pytest.raises(tree.TreeError) as failure:
        tree.resolve(digest)
    assert failure.value.reason == "missing"


def test_a_tampered_materialized_folder_is_detected(tmp_path):
    # Materialization hardlinks each pool blob into place, so overwriting a materialized
    # file's bytes in-place also tampers the shared pool blob (same inode): resolve then
    # reports corruption on the underlying blob, rather than silently rebuilding from it.
    # Truncate-and-rewrite avoids this and exercises the "detected and rebuilt" path
    # instead: the materialized directory itself is replaced, while its pool blob (still
    # linked at the original inode from `add`) is untouched.
    root = make_instrument(tmp_path / "instrument")
    digest, _ = tree.digest_of_tree(root)
    tree.add(root)
    materialized = tree.resolve(digest)
    tampered = materialized / "samples" / "note.wav"
    tampered.unlink()
    tampered.write_bytes(b"tampered materialized bytes")
    rebuilt = tree.resolve(digest)
    assert rebuilt == materialized
    assert (rebuilt / "samples" / "note.wav").read_bytes() == b"fake sample bytes"


def test_tampering_a_materialized_file_in_place_corrupts_the_shared_pool_blob(tmp_path):
    # The hardlink strategy's other face: in-place tampering (no unlink first) mutates the
    # pool blob too, so resolve correctly reports corruption rather than masking it.
    root = make_instrument(tmp_path / "instrument")
    digest, _ = tree.digest_of_tree(root)
    tree.add(root)
    materialized = tree.resolve(digest)
    (materialized / "samples" / "note.wav").write_bytes(b"tampered materialized bytes")
    with pytest.raises(tree.TreeError) as failure:
        tree.resolve(digest)
    assert failure.value.reason == "corrupt"


def test_a_materialized_folder_with_an_extra_file_is_rebuilt_without_it(tmp_path):
    root = make_instrument(tmp_path / "instrument")
    digest, _ = tree.digest_of_tree(root)
    tree.add(root)
    materialized = tree.resolve(digest)
    (materialized / "samples" / "extra-not-in-manifest.wav").write_bytes(b"stray bytes")
    rebuilt = tree.resolve(digest)
    assert not (rebuilt / "samples" / "extra-not-in-manifest.wav").exists()


def test_digest_from_ref_rejects_bad_shapes():
    for bad in (
        "sha256:" + "0" * 64,
        "tree:" + "0" * 64,
        "tree:sha256:" + "Z" * 64,
        "tree:sha256:",
    ):
        with pytest.raises(ValueError):
            tree.digest_from_ref(bad)


def test_digest_from_ref_accepts_a_well_formed_ref():
    digest = "0" * 64
    assert tree.digest_from_ref(f"tree:sha256:{digest}") == digest


def test_materialization_uses_hardlinks_when_available(tmp_path):
    root = make_instrument(tmp_path / "instrument")
    digest, entries = tree.digest_of_tree(root)
    tree.add(root)
    materialized = tree.resolve(digest)
    _relative, file_digest = entries[0]
    blob = pool.path_for(file_digest)
    materialized_file = materialized / entries[0][0]
    if os.name == "posix":
        assert materialized_file.stat().st_ino == blob.stat().st_ino


def test_version_control_directories_do_not_change_the_digest(tmp_path):
    root = tmp_path / "instrument"
    (root / "samples").mkdir(parents=True)
    (root / "program.sfz").write_text("<region> sample=samples/a.wav\n", encoding="utf-8")
    (root / "samples" / "a.wav").write_bytes(b"RIFF-a")
    before, _ = tree.digest_of_tree(root)
    (root / ".git" / "objects").mkdir(parents=True)
    (root / ".git" / "objects" / "pack").write_bytes(b"history")
    after, entries = tree.digest_of_tree(root)
    assert after == before
    assert all(not path.startswith(".git") for path, _ in entries)


@pytest.mark.skipif(os.name == 'nt', reason='Windows filenames cannot contain carriage returns')
def test_native_macos_project_icon_roundtrips_through_folder_material(tmp_path, scratch_pool):
    source = tmp_path / 'native-project'
    source.mkdir()
    (source / 'Icon\r').write_bytes(b'')
    (source / 'session.als').write_bytes(b'native set')
    ref = tree.add(source)
    resolved = tree.resolve(tree.digest_from_ref(ref))
    assert (resolved / 'Icon\r').read_bytes() == b''
    assert (resolved / 'session.als').read_bytes() == b'native set'
