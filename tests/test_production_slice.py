"""Real CLI round trips for the first modular music project."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus_code.graph import read_graph, semantic_diff

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "chop-flip"


def _run(*arguments: object) -> dict:
    result = subprocess.run(
        [sys.executable, "-m", "tactus_code.cli", *(str(value) for value in arguments)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _copy_example(target: Path) -> Path:
    shutil.copytree(
        EXAMPLE,
        target,
        ignore=shutil.ignore_patterns(".tactus-code", "__pycache__"),
    )
    return target


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_compiled_graph_replays_without_authoring_project(tmp_path: Path) -> None:
    project = _copy_example(tmp_path / "authoring")
    first = _run("build", project / "song.py", "--out", tmp_path / "build-a")
    second = _run("build", project / "song.py", "--out", tmp_path / "build-b")
    assert _hash(Path(first["graph"])) == _hash(Path(second["graph"]))
    assert _hash(Path(first["receipt"])) == _hash(Path(second["receipt"]))

    before = _run("render", first["graph"], "--out", tmp_path / "render-before")
    shutil.copytree(tmp_path / "build-a", tmp_path / "isolated")
    project.rename(tmp_path / "authoring.quarantined")
    after = _run(
        "render", tmp_path / "isolated" / "arrangement.json", "--out", tmp_path / "render-after"
    )
    for name in ("mix", "stem:sample", "stem:drums", "stem:bass"):
        assert _hash(Path(before[name])) == _hash(Path(after[name]))

    graph = read_graph(tmp_path / "isolated" / "arrangement.json")
    assert [track["name"] for track in graph["tracks"]] == ["sample", "drums", "bass"]
    assert len(graph["computations"]) == 12
    receipt = json.loads((tmp_path / "isolated" / "receipt.json").read_text())
    assert receipt["reproducibility"] == "compiled replay only; source rebuild not guaranteed"
    assert "parts/bass.py" in receipt["source_files"]

    muted = _run(
        "render",
        tmp_path / "isolated" / "arrangement.json",
        "--out",
        tmp_path / "render-muted",
        "--mute",
        "bass",
    )
    original, rate = sf.read(before["mix"], always_2d=True)
    no_bass, muted_rate = sf.read(muted["mix"], always_2d=True)
    assert rate == muted_rate == 48000
    assert not np.array_equal(original, no_bass)
    assert len(original) == round(8 * 4 * 60 / 90 * rate)

    material = next((tmp_path / "isolated" / "materials" / "audio").glob("*.wav"))
    payload = material.read_bytes()
    material.write_bytes(payload[:-1] + bytes([payload[-1] ^ 1]))
    with pytest.raises(subprocess.CalledProcessError) as failure:
        _run("render", tmp_path / "isolated" / "arrangement.json", "--out", tmp_path / "tampered")
    assert "audio material hash mismatch" in failure.value.stderr


def test_bass_revision_changes_only_bass_part(tmp_path: Path) -> None:
    project = _copy_example(tmp_path / "authoring")
    before = _run("build", project / "song.py", "--out", tmp_path / "before")
    before_audio = _run("render", before["graph"], "--out", tmp_path / "before-audio")

    bass_file = project / "parts" / "bass.py"
    original = bass_file.read_text(encoding="utf-8")
    assert "BASS_DRIVE = 2.4" in original
    bass_file.write_text(original.replace("BASS_DRIVE = 2.4", "BASS_DRIVE = 3.2"), encoding="utf-8")
    after = _run("build", project / "song.py", "--out", tmp_path / "after")
    after_audio = _run("render", after["graph"], "--out", tmp_path / "after-audio")

    diff = semantic_diff(read_graph(Path(before["graph"])), read_graph(Path(after["graph"])))
    assert diff["tracks"].keys() == {"bass"}
    assert diff["tracks"]["bass"]["events"] == [f"bass-{bar}" for bar in range(8)]
    assert _run("diff", before["graph"], after["graph"]) == diff
    assert _hash(Path(before_audio["stem:drums"])) == _hash(Path(after_audio["stem:drums"]))
    assert _hash(Path(before_audio["stem:sample"])) == _hash(Path(after_audio["stem:sample"]))
    assert _hash(Path(before_audio["stem:bass"])) != _hash(Path(after_audio["stem:bass"]))
    assert _hash(Path(before_audio["mix"])) != _hash(Path(after_audio["mix"]))


def test_hidden_randomness_is_never_claimed_source_reproducible(tmp_path: Path) -> None:
    project = tmp_path / "random-song"
    project.mkdir()
    (project / "song.py").write_text(
        """import numpy as np

TRANSPORT = {"bpm": 120, "bars": 1, "sample_rate": 48000}

def noise(*, sample_rate):
    return np.random.default_rng().normal(0, 0.01, sample_rate).astype('float32')

def build(project):
    sound = project.compute('unseeded', noise)
    project.track('noise').place('noise-1', sound, at_beats=0)
""",
        encoding="utf-8",
    )
    first = _run("build", project / "song.py", "--out", tmp_path / "random-a")
    second = _run("build", project / "song.py", "--out", tmp_path / "random-b")
    graph_a = read_graph(Path(first["graph"]))
    graph_b = read_graph(Path(second["graph"]))
    assert graph_a["computations"][0]["output"] != graph_b["computations"][0]["output"]
    for output in (first, second):
        receipt = json.loads(Path(output["receipt"]).read_text())
        assert receipt["reproducibility"] == "compiled replay only; source rebuild not guaranteed"
        assert read_graph(Path(output["graph"]))["computations"][0]["reproducibility"].startswith(
            "materialized"
        )
