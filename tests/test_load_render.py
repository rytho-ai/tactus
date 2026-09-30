"""Saved render reuse: exact selected payloads, integrity scope and input attribution."""

import json
import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pytest

from tactus import LoadedRender, MaterialError, inputs, load_render, material, render_store, run
from tactus.inputs import pool, tree


@pytest.fixture(autouse=True)
def private_pool(tmp_path, monkeypatch):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    inputs._reset_record()


@pytest.fixture
def checkpoint(tmp_path):
    root = tmp_path / "original"
    root.mkdir()
    (root / "receipt.json").write_text('{"historical": "generator no longer installed"}')
    arrays = {
        "bass": np.array([0.123456789123, 1.25, -1.5], dtype=np.float64),
        "drums": np.arange(12, dtype=np.float32).reshape(6, 2) / 20,
    }
    render_store.publish(root, 48000, arrays)
    return root, arrays


def blob(ref, relative):
    entries = dict(tree.parse_manifest(pool.path_for(tree.digest_from_ref(ref)).read_bytes()))
    digest = entries[relative]
    return pool.default_pool_dir() / digest[:2] / digest


def test_exact_originals_readonly_rate_and_identity_survive_source_removal(checkpoint):
    root, arrays = checkpoint
    digest = pool.hash_file(root / "render.json")
    ref = tree.add(root)
    shutil.rmtree(root)
    saved = load_render(ref)
    assert isinstance(saved, LoadedRender)
    assert saved.sample_rate == 48000
    assert dict(saved.origin) == {"ref": ref, "kind": "original-render", "sha256": digest}
    assert set(saved.outputs) == set(arrays)
    for name, original in arrays.items():
        np.testing.assert_array_equal(saved.outputs[name], original)
        assert saved.outputs[name].dtype == original.dtype
        with pytest.raises(ValueError, match="read-only"):
            saved.outputs[name][0] = 0
    editable = saved.outputs["bass"].copy()
    editable[0] = 0
    assert saved.outputs["bass"][0] != 0
    with pytest.raises(TypeError):
        saved.outputs["new"] = editable
    with pytest.raises(TypeError):
        saved.origin["ref"] = "different"
    with pytest.raises(FrozenInstanceError):
        saved.sample_rate = 1
    assert not (pool.default_pool_dir() / "trees").exists()


def test_selection_reads_only_dependency_blobs(checkpoint, monkeypatch):
    root, _ = checkpoint
    (root / "unrelated.wav").write_bytes(b"unused audition PCM")
    ref = tree.add(root)
    hashed, loaded = [], []
    hash_file, np_load = pool.hash_file, np.load

    def track_hash(path):
        hashed.append(path)
        return hash_file(path)

    def track_load(path, **kwargs):
        loaded.append(path)
        return np_load(path, **kwargs)

    expected = {pool.path_for(tree.digest_from_ref(ref))} | {
        blob(ref, relative) for relative in ["render.json", "receipt.json", "render/bass.npy"]
    }
    expected_array = blob(ref, "render/bass.npy")
    monkeypatch.setattr(pool, "hash_file", track_hash)
    monkeypatch.setattr(np, "load", track_load)
    saved = load_render(ref, outputs=("bass",))
    assert list(saved.outputs) == ["bass"]
    assert len(hashed) == 4 and set(hashed) == expected
    assert loaded == [expected_array]


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_unrequested_damage_is_ignored_but_selected_damage_rejected(checkpoint, damage):
    root, _ = checkpoint
    ref = tree.add(root)
    target = blob(ref, "render/drums.npy")
    if damage == "missing":
        target.unlink()
    else:
        target.write_bytes(b"tampered")
    assert list(load_render(ref, outputs=["bass"]).outputs) == ["bass"]
    for call in [lambda: load_render(ref), lambda: material(ref)]:
        with pytest.raises(MaterialError) as failure:
            call()
        assert failure.value.reason == damage


@pytest.mark.parametrize("outputs", [[], "bass", ["bass", "bass"], [1], ["unknown"]])
def test_invalid_selection(checkpoint, outputs):
    root, _ = checkpoint
    with pytest.raises(ValueError, match="outputs"):
        load_render(tree.add(root), outputs=outputs)


def test_requested_order(checkpoint):
    root, _ = checkpoint
    assert list(load_render(tree.add(root), outputs=["drums", "bass"]).outputs) == ["drums", "bass"]


@pytest.mark.parametrize("relative", ["render.json", "receipt.json", "render/bass.npy"])
def test_selected_metadata_or_audio_tamper_rejected(checkpoint, relative):
    root, _ = checkpoint
    ref = tree.add(root)
    blob(ref, relative).write_bytes(b"corrupt")
    with pytest.raises(MaterialError) as failure:
        load_render(ref, outputs=["bass"])
    assert failure.value.reason == "corrupt"


@pytest.mark.parametrize(
    "field,value",
    [
        ("shape", [4]),
        ("shape", [True]),
        ("dtype", "<f4"),
        ("sha256", "0" * 64),
        ("file", "../outside.npy"),
    ],
)
def test_checkpoint_metadata_mismatch_rejected(checkpoint, field, value):
    root, _ = checkpoint
    path = root / "render.json"
    manifest = json.loads(path.read_text())
    manifest["outputs"]["bass"][field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(MaterialError) as failure:
        load_render(tree.add(root), outputs=["bass"])
    assert failure.value.reason == "corrupt"


@pytest.mark.parametrize("mutation", ["nonfinite", "receipt", "rate", "duplicate-json"])
def test_invalid_checkpoint_rejected(checkpoint, mutation):
    root, _ = checkpoint
    path = root / "render.json"
    manifest = json.loads(path.read_text())
    if mutation == "nonfinite":
        np.save(root / "render/bass.npy", np.array([np.nan, 0, 1]))
        manifest["outputs"]["bass"]["sha256"] = pool.hash_file(root / "render/bass.npy")
    elif mutation == "receipt":
        manifest["receipt_sha256"] = "0" * 64
    elif mutation == "rate":
        manifest["sample_rate"] = True
    payload = json.dumps(manifest)
    if mutation == "duplicate-json":
        payload = payload[:-1] + ', "sample_rate": 48000}'
    path.write_text(payload)
    with pytest.raises(MaterialError) as failure:
        load_render(tree.add(root), outputs=["bass"])
    assert failure.value.reason == "corrupt"


@pytest.mark.parametrize(
    "entry", ["../escape", "/absolute", "render//bass.npy", "render\\bass.npy"]
)
def test_unsafe_tree_index_rejected(tmp_path, entry):
    path = tmp_path / "index"
    path.write_bytes(tree.manifest_bytes([(entry, "0" * 64)]))
    with pytest.raises(MaterialError) as failure:
        load_render(tree.PREFIX + pool.put(path))
    assert failure.value.reason == "corrupt"


def test_duplicate_and_tampered_index_rejected(checkpoint, tmp_path):
    root, _ = checkpoint
    ref = tree.add(root)
    index = pool.path_for(tree.digest_from_ref(ref))
    duplicate = tmp_path / "duplicate-index"
    duplicate.write_bytes(index.read_bytes() + index.read_bytes())
    with pytest.raises(MaterialError) as failure:
        load_render(tree.PREFIX + pool.put(duplicate))
    assert failure.value.reason == "corrupt"
    index.write_bytes(b"corrupt")
    with pytest.raises(MaterialError) as failure:
        load_render(ref)
    assert failure.value.reason == "corrupt"


def test_original_checkpoint_required_and_ref_errors(checkpoint):
    root, _ = checkpoint
    (root / "render.json").unlink()
    (root / "manifest.json").write_text('{"kind": "tactus.functional-run"}')
    with pytest.raises(MaterialError) as failure:
        load_render(tree.add(root))
    assert failure.value.reason == "missing"
    with pytest.raises(MaterialError) as failure:
        load_render("sha256:" + "0" * 64)
    assert failure.value.reason == "invalid_ref"
    with pytest.raises(MaterialError) as failure:
        load_render(tree.PREFIX + "0" * 64)
    assert failure.value.reason == "missing"


def test_receipt_and_stage_capture_one_tree_ref(checkpoint, tmp_path):
    root, arrays = checkpoint
    ref = tree.add(root)
    source = tmp_path / "work/song.py"
    source.parent.mkdir()
    source.write_text(f"""from tactus import load_render, stage
@stage
def stems():
    saved = load_render({ref!r}, outputs=["bass"])
    return dict(saved.outputs)
def render(*, gain=1.0):
    return {{"sample_rate": 48000, "outputs": {{"mix": stems()["bass"] * gain}}}}
""")
    for attempt in range(2):
        output = tmp_path / f"reuse-{attempt}"
        result = run(source, out=output, reuse=True)
        receipt = json.loads(Path(result["receipt"]).read_text())
        assert receipt["materials"] == [{"ref": ref}]
        assert receipt["stages"][0]["reused"] == bool(attempt)
        np.testing.assert_array_equal(render_store.read(output).outputs["mix"], arrays["bass"])
