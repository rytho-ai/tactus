"""Selected performances survive rerolls, source changes, cache deletion and transfer."""

import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pytest

from tactus import MaterialError, RunError, excerpt, load_take, material, run
from tactus.cli import main
from tactus.inputs import pool, tree
from tactus.takes import export_take, save_take


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    source = tmp_path / "work" / "song.py"
    source.parent.mkdir()
    source.write_text("""import numpy as np
from tactus import tool

def render(*, offset=0.0):
    tool("/bin/true")
    raw = np.array([[1.25, -1.5], [0.123456789123, 1e-12]], dtype=np.float64) + offset
    return {"sample_rate": 8000, "outputs": {"mix": raw * 0.25}, "takes": {"pad": raw}}
""")
    out = tmp_path / "run"
    result = run(source, out=out)
    return source, out, result


def test_select_transfer_and_replay_without_generator(candidate, tmp_path, monkeypatch):
    source, out, result = candidate
    raw = np.load(out / "takes/pad/audio.npy")
    selected = save_take(out, "pad")["ref"]
    assert result["takes"]["pad"] == selected
    assert save_take(out, "pad")["ref"] == selected
    assert json.loads((out / "manifest.json").read_text())["format_version"] == 3
    np.testing.assert_array_equal(load_take(selected, sample_rate=8000), raw)
    assert load_take(selected, sample_rate=8000).dtype == raw.dtype
    cut = excerpt(out, out=tmp_path / "excerpt", range=[0, 0.000125])
    assert "mix" in cut["outputs"]

    # Two revisions remain selectable; the source snapshot is from generation time.
    second = run(source, out=tmp_path / "second", params={"offset": 0.1})
    alternative = save_take(tmp_path / "second", "pad")["ref"]
    assert alternative != selected
    assert second["takes"]["pad"] == alternative
    source.write_text("raise RuntimeError('generator unavailable')")
    exported = tmp_path / "exported"
    export_take(selected, out=exported)
    with zipfile.ZipFile(exported / "source.zip") as archive:
        assert b"def render" in archive.read("source/song.py")
    assert json.loads((exported / "receipt.json").read_text())["tools"]
    old = load_take(selected, sample_rate=8000)
    assert not np.array_equal(old, load_take(alternative, sample_rate=8000))
    np.testing.assert_array_equal(load_take(selected, sample_rate=8000), raw)

    shutil.rmtree(source.parent)
    shutil.rmtree(out)
    shutil.rmtree(tmp_path / "pool")
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "new-pool"))
    assert tree.add(exported) == selected
    playback = tmp_path / "playback.py"
    playback.write_text(f"""from tactus import load_take

def render(*, gain=0.25):
    return {{"sample_rate": 8000, "outputs": {{"mix": load_take({selected!r}, sample_rate=8000) * gain}}}}
""")
    replay = run(playback, out=tmp_path / "replay")
    receipt = json.loads(Path(replay["receipt"]).read_text())
    assert receipt["tools"] == []
    assert receipt["materials"] == [{"ref": selected}]
    assert not receipt["reuse"] and receipt["stages"] == []
    np.testing.assert_array_equal(load_take(selected, sample_rate=8000), raw)


@pytest.mark.parametrize("dtype,shape", [("float32", (3,)), ("float64", (3, 1)), ("int16", (3, 2))])
def test_exact_dtype_shape_and_headroom(tmp_path, monkeypatch, dtype, shape):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    source = tmp_path / "song.py"
    source.write_text(f"""import numpy as np

def render():
    x = np.arange({np.prod(shape)}, dtype={dtype!r}).reshape({shape!r})
    return {{"sample_rate": 48000, "outputs": {{"mix": x}}, "takes": {{"raw": x}}}}
""")
    run(source, out=tmp_path / "run")
    ref = save_take(tmp_path / "run", "raw")["ref"]
    audio = load_take(ref, sample_rate=48000)
    np.testing.assert_array_equal(audio, np.arange(np.prod(shape), dtype=dtype).reshape(shape))
    assert audio.dtype == dtype
    assert audio.shape == shape


def test_corruption_missing_and_rate_never_regenerate(candidate, tmp_path):
    _, out, _ = candidate
    ref = save_take(out, "pad")["ref"]
    with pytest.raises(MaterialError, match="sample rate"):
        load_take(ref, sample_rate=44100)
    with pytest.raises(MaterialError, match="tree ref"):
        load_take("sha256:" + "a" * 64, sample_rate=8000)
    root = material(ref)
    digest = pool.hash_file(root / "audio.npy")
    blob = pool.path_for(digest)
    blob.write_bytes(b"corrupt")
    with pytest.raises(MaterialError, match="corrupt"):
        load_take(ref, sample_rate=8000)
    blob.unlink()
    with pytest.raises(MaterialError, match="not in the pool"):
        load_take(ref, sample_rate=8000)


@pytest.mark.parametrize("filename", ["audio.npy", "receipt.json", "source.zip", "take.json"])
def test_corrupt_candidate_refused(candidate, filename):
    _, out, _ = candidate
    with (out / "takes/pad" / filename).open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(RunError, match="does not match"):
        save_take(out, "pad")


@pytest.mark.parametrize(
    "expression",
    ["{}", "{'a': np.array([np.nan])}", "{'../escape': np.zeros(2)}", "{'a': np.ones((3, 3))}"],
)
def test_invalid_take_cleans_run(tmp_path, expression):
    source = tmp_path / "song.py"
    source.write_text(f"""import numpy as np

def render():
    return {{"sample_rate": 8000, "outputs": {{"mix": np.zeros(2)}}, "takes": {expression}}}
""")
    with pytest.raises(RunError) as exc:
        run(source, out=tmp_path / "out")
    assert exc.value.code == "invalid_output"
    assert not (tmp_path / "out").exists()


def test_cli_save_export_import_and_errors(candidate, tmp_path, monkeypatch, capsys):
    _, out, _ = candidate
    assert main(["take", "save", str(out), "pad"]) == 0
    ref = json.loads(capsys.readouterr().out)["ref"]
    destination = tmp_path / "bundle"
    assert main(["take", "export", ref, "--out", str(destination)]) == 0
    capsys.readouterr()
    assert main(["take", "export", ref, "--out", str(destination)]) != 0
    assert destination.is_dir()
    capsys.readouterr()
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "other-pool"))
    assert main(["material", "add", str(destination)]) == 0
    assert list(json.loads(capsys.readouterr().out)["materials"].values()) == [ref]
    assert main(["take", "save", str(out), "missing"]) != 0
    assert json.loads(capsys.readouterr().out)["status"] == "error"


def test_random_candidates_and_cached_playback(candidate, tmp_path):
    source, _, _ = candidate
    source.write_text("""import numpy as np

def render():
    x = np.random.default_rng().uniform(-0.5, 0.5, (32, 2)).astype(np.float32)
    return {"sample_rate": 8000, "outputs": {"mix": x}, "takes": {"pad": x}}
""")
    refs = []
    for index in range(2):
        destination = tmp_path / f"random-{index}"
        run(source, out=destination)
        refs.append(save_take(destination, "pad")["ref"])
    first = load_take(refs[0], sample_rate=8000)
    assert not np.array_equal(first, load_take(refs[1], sample_rate=8000))
    source.write_text(f"""from tactus import load_take, stage

@stage
def part(ref):
    return load_take(ref, sample_rate=8000)

def render(*, ref={refs[0]!r}, gain=1.0):
    return {{"sample_rate": 8000, "outputs": {{"mix": part(ref) * gain}}}}
""")
    manifests = []
    for index, ref in enumerate([refs[0], refs[1], refs[0]]):
        result = run(source, out=tmp_path / f"play-{index}", params={"ref": ref}, reuse=True)
        manifests.append(json.loads(Path(result["manifest"]).read_text()))
        receipt = json.loads(Path(result["receipt"]).read_text())
        assert receipt["materials"] == [{"ref": ref}]
        assert receipt["tools"] == []
    assert receipt["stages"][0]["reused"]
    assert manifests[0] == manifests[2] != manifests[1]


def test_malformed_imported_take_fails(candidate, tmp_path):
    _, out, _ = candidate
    bundle = tmp_path / "bad-bundle"
    shutil.copytree(out / "takes/pad", bundle)
    (bundle / "audio.npy").write_bytes(b"")
    metadata = json.loads((bundle / "take.json").read_text())
    metadata["audio_sha256"] = pool.hash_file(bundle / "audio.npy")
    (bundle / "take.json").write_text(json.dumps(metadata))
    ref = tree.add(bundle)
    with pytest.raises(MaterialError, match="invalid take"):
        load_take(ref, sample_rate=8000)
    with pytest.raises(RunError, match="cannot export"):
        export_take(ref, out=tmp_path / "not-published")
    assert not (tmp_path / "not-published").exists()
