"""Original render preservation, legacy export and publication failure recovery."""

import json
import shutil
import zipfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import RunError, run
from tactus.cli import main
from tactus.commands import Command
from tactus.export import deliver, wav
from tactus.render_store import read, read_published
from tactus.takes import save_take


@pytest.fixture
def rendered(tmp_path):
    source = tmp_path / "work" / "song.py"
    source.parent.mkdir()
    source.write_text("""import numpy as np
def render():
    raw = np.array([0.123456789123, 1.25, -1.5], dtype=np.float64)
    return {"sample_rate": 48000, "outputs": {"mix": raw, "bass": raw * 0.5}, "takes": {"raw": raw}}
""")
    output = tmp_path / "run"
    run(source, out=output)
    return source, output


def test_double_precision_and_default_wav_parity(rendered, tmp_path):
    source, output = rendered
    source.unlink()  # Export cannot depend on the generator existing.
    rate, arrays, _ = read(output)
    assert rate == 48000 and arrays["mix"].dtype == np.float64
    result = deliver(
        output,
        out=tmp_path / "double",
        command=Command("wav", "export", wav),
        params={"subtype": "DOUBLE"},
    )
    audio, _ = sf.read(result["files"]["mix.wav"])
    np.testing.assert_array_equal(audio, arrays["mix"])
    result = deliver(
        output,
        out=tmp_path / "pcm",
        command=Command("wav", "export", wav),
        params={"subtype": "PCM_24"},
    )
    original = json.loads((output / "manifest.json").read_text())
    for item in original["outputs"].values():
        assert (output / item["file"]).read_bytes() == Path(
            result["files"][item["file"]]
        ).read_bytes()


def test_published_reader_keeps_pcm_distinct_from_original_and_legacy_adapter(rendered):
    from tactus.excerpt import read_published as legacy_read

    _, output = rendered
    original = read(output)
    published = read_published(output)
    assert original.outputs["mix"].max() == 1.25
    assert published.outputs["mix"].max() < 1.0
    assert published.outputs["mix"].dtype == np.float32
    assert published.manifest_bytes == (output / "manifest.json").read_bytes()
    payload, rate, arrays, files = legacy_read(output)
    assert payload == published.manifest_bytes and rate == published.sample_rate
    for name, reference in published.references.items():
        assert files[name] == reference.file
        np.testing.assert_array_equal(arrays[name], published.outputs[name])


def test_published_reader_reports_missing_manifest_as_source_corrupt(tmp_path):
    with pytest.raises(RunError) as caught:
        read_published(tmp_path)
    assert caught.value.code == "source_corrupt"


def test_cli_stems_and_flac(rendered, tmp_path, capsys):
    _, output = rendered
    assert main(["export", "stems", str(output), "--out", str(tmp_path / "stems")]) == 0
    capsys.readouterr()
    with zipfile.ZipFile(tmp_path / "stems/stems.zip") as archive:
        assert archive.namelist() == ["bass.wav"]
    assert main(["export", "flac", str(output), "--out", str(tmp_path / "flac")]) == 0
    assert sf.info(tmp_path / "flac/mix.flac").subtype == "PCM_24"


def test_legacy_pcm_fallback_is_explicit(rendered, tmp_path):
    _, output = rendered
    (output / "render.json").unlink()
    shutil.rmtree(output / "render")
    _, arrays, origin = read(output)
    assert origin["kind"] == "published-pcm"
    assert arrays["mix"].max() < 1.0
    result = deliver(
        output,
        out=tmp_path / "float",
        command=Command("wav", "export", wav),
        params={"subtype": "FLOAT"},
    )
    assert json.loads(Path(result["manifest"]).read_text())["source"]["kind"] == "published-pcm"


@pytest.mark.parametrize("file", ["render/mix.npy", "receipt.json"])
def test_corruption_fails_without_pcm_fallback(rendered, tmp_path, file):
    _, output = rendered
    with (output / file).open("ab") as stream:
        stream.write(b"corrupt")
    with pytest.raises(RunError, match="hash mismatch"):
        deliver(output, out=tmp_path / "bad", command=Command("wav", "export", wav), params={})
    assert not (tmp_path / "bad").exists()


def test_failed_custom_export_keeps_source_and_existing_destination(rendered, tmp_path):
    _, output = rendered

    def broken(outputs, sample_rate, *, out):
        (out / "partial.txt").write_text("partial")
        raise RuntimeError("broken encoder")

    with pytest.raises(RunError, match="broken encoder"):
        deliver(
            output, out=tmp_path / "broken", command=Command("broken", "export", broken), params={}
        )
    assert not (tmp_path / "broken").exists()
    assert read(output)[1]
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "keep").write_text("keep")
    with pytest.raises(RunError, match="already exists"):
        deliver(output, out=existing, command=Command("wav", "export", wav), params={})
    assert (existing / "keep").read_text() == "keep"


def test_run_delivery_failure_retains_completed_render_and_takes(tmp_path, monkeypatch):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    source = tmp_path / "song.py"
    source.write_text("""import numpy as np
from tactus.store import OutputStore
from pathlib import Path
def fail(*args): raise OSError("encoder failed")
OutputStore.add = fail

def render():
    Path("calls").write_text("one generation")
    x = np.random.default_rng().uniform(-0.5, 0.5, 10)
    return {"sample_rate": 8000, "outputs": {"mix": x}, "takes": {"part": x}}
""")
    output = tmp_path / "failed-run"
    with pytest.raises(RunError, match="completed render retained"):
        run(source, out=output)
    assert not (output / "manifest.json").exists()
    original = read(output)[1]["mix"]
    assert save_take(output, "part")["ref"]
    source.unlink()
    result = deliver(
        output,
        out=tmp_path / "retry",
        command=Command("wav", "export", wav),
        params={"subtype": "DOUBLE"},
    )
    np.testing.assert_array_equal(sf.read(result["files"]["mix.wav"])[0], original)
    assert (tmp_path / "calls").read_text() == "one generation"


@pytest.mark.parametrize("dtype", [np.float16, np.uint8])
@pytest.mark.parametrize("subtype", ["FLOAT", "DOUBLE"])
def test_floating_export_casts_every_supported_numeric_dtype(tmp_path, dtype, subtype):
    # render accepts real integer/float arrays beyond SoundFile's native input types.
    audio = np.array([0, 1, 2], dtype=dtype)
    wav({"mix": audio}, 8000, out=tmp_path, subtype=subtype)
    decoded, _ = sf.read(tmp_path / "mix.wav")
    np.testing.assert_array_equal(decoded, audio.astype(np.float64))


@pytest.mark.parametrize("stereo", [False, True])
def test_flac_and_stems_preserve_default_pcm24_rounding(tmp_path, stereo):
    from tactus.export import flac, stems
    from tactus.store import OutputStore

    # Exercise both sides of PCM24 rounding thresholds, plus clipping and exact values.
    fractions = np.array([-1.7, -0.51, -0.49, 0.49, 0.51, 1.7]) / 2**23
    audio = np.concatenate((fractions, [-1.5, -1, 0, 1, 1.5])).astype(np.float32)
    if stereo:
        audio = np.column_stack((audio, -audio))
    reference, levels = OutputStore(tmp_path / "wav", 48000).add("part", audio)
    expected, _ = sf.read(tmp_path / "wav" / reference.file, dtype="int32")
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    result = flac({"part": audio}, 48000, out=delivery)
    decoded, _ = sf.read(delivery / "part.flac", dtype="int32")
    np.testing.assert_array_equal(decoded, expected)
    assert result["clipped_samples"]["part"] == levels["clipped_samples"]
    stems({"part": audio}, 48000, out=delivery)
    with zipfile.ZipFile(delivery / "stems.zip") as archive:
        assert archive.read("part.wav") == (tmp_path / "wav" / reference.file).read_bytes()
