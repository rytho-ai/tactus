"""Project-local named analysis/export discovery and global environment dispatch."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import launcher
from tactus.cli import main
from tactus.project import discover


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TACTUS_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("UV_RUN_RECURSION_DEPTH", raising=False)
    (tmp_path / "pyproject.toml").write_text("""[project]
name = "example-work"
version = "0.1.0"
dependencies = ["tactus"]
[tool.tactus.analysis]
"stereo.width" = "local_analysis:width"
"stereo.broken" = "not_installed:anything"
[tool.tactus.export]
"my-delivery" = "local_delivery:bundle"
""")
    (tmp_path / "local_analysis.py").write_text('''from __future__ import annotations
import numpy as np
print("analysis loaded")
def width(audio, sample_rate, *, scale: float, invert: bool = False, out=None):
    """Width example with 100% custom parameters."""
    values = np.mean(audio, axis=0) * scale
    return {"rate": sample_rate, "values": -values if invert else values}
''')
    (tmp_path / "local_delivery.py").write_text('''import soundfile as sf
def bundle(outputs, sample_rate, *, out, title: str = "demo"):
    """Deliver a named floating-point mix."""
    sf.write(out / (title + ".wav"), outputs["mix"], sample_rate, subtype="FLOAT")
    return {"title": title}
''')
    sf.write(tmp_path / "audio.wav", np.full((64, 2), 0.25), 8000, subtype="FLOAT")
    return tmp_path


def test_help_is_lazy_and_selected_help_uses_annotations(work, capsys):
    for args in (["analyze", "--help"], ["analyze", "stereo", "--help"], ["export", "--help"]):
        with pytest.raises(SystemExit) as exc:
            main(args)
        assert exc.value.code == 0
        output = capsys.readouterr()
        assert "analysis loaded" not in output.out + output.err
    with pytest.raises(SystemExit):
        main(["analyze", "stereo", "width", "--help"])
    text = capsys.readouterr()
    assert "--scale" in text.out and "--no-invert" in text.out
    assert "100%" in text.out and "analysis loaded" in text.err
    assert main(["analyze", "stereo", "broken", "audio.wav"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"
    assert main(["analyze", "level", "rms", "audio.wav"]) == 0


def test_custom_analysis_scalar_array_provenance_and_required_flags(work, capsys):
    assert main(["analyze", "stereo", "width", "audio.wav"]) == 2
    capsys.readouterr()
    assert (
        main(
            [
                "analyze",
                "stereo",
                "width",
                "audio.wav",
                "--scale",
                "2",
                "--invert",
                "--out",
                "results",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["params"] == {"scale": 2.0, "invert": True}
    assert report["provenance"]["project"] == str(work)
    assert report["provenance"]["inventory"]["source_files"]["local_analysis.py"]
    assert report["input_sha256"]
    array = report["result"]["values"]
    with np.load(array["file"]) as stored:
        np.testing.assert_array_equal(stored[array["key"]], [-0.5, -0.5])
    assert list((work / "results").rglob("result.json"))
    assert "analysis loaded" not in captured.out
    # A repeated output request cannot overwrite or remove the earlier delivery.
    assert (
        main(
            [
                "analyze",
                "stereo",
                "width",
                "audio.wav",
                "--scale",
                "2",
                "--invert",
                "--out",
                "results",
            ]
        )
        != 0
    )
    assert Path(array["file"]).exists()


def test_project_export_registered_and_receipted(work, capsys):
    (work / "song.py").write_text("""import numpy as np
def render():
    return {"sample_rate": 8000, "outputs": {"mix": np.full((64, 2), 1.25)}}
""")
    assert main(["run", "song.py", "--out", "runs/a"]) == 0
    capsys.readouterr()
    assert main(["export", "my-delivery", "runs/a", "--out", "delivery", "--title", "chosen"]) == 0
    report = json.loads(capsys.readouterr().out)
    audio, _ = sf.read(report["files"]["chosen.wav"])
    np.testing.assert_array_equal(audio, 1.25)
    manifest = json.loads(Path(report["manifest"]).read_text())
    assert manifest["params"] == {"title": "chosen"}
    assert manifest["source"]["kind"] == "original-render"
    assert manifest["exporter"]["callable"] == "local_delivery:bundle"
    assert manifest["provenance"]["inventory"]["source_files"]["local_delivery.py"]


def test_builtin_name_collision_and_bad_signature(work, capsys):
    path = work / "pyproject.toml"
    path.write_text(path.read_text().replace('"stereo.width"', '"level.rms"'))
    assert main(["analyze", "--help"]) == 2
    assert "conflicts" in capsys.readouterr().out
    path.write_text(path.read_text().replace('"level.rms"', '"stereo.width"'))
    (work / "local_analysis.py").write_text("def width(audio, sample_rate, **kwargs): return {}")
    assert main(["analyze", "stereo", "width", "audio.wav"]) == 2
    assert "keyword-only" in capsys.readouterr().out
    (work / "local_analysis.py").write_text(
        "def width(audio, sample_rate, *, value: 'Undefined' = 1): return {}"
    )
    assert main(["analyze", "stereo", "width", "audio.wav"]) == 2
    assert "parameter annotations" in capsys.readouterr().out


def test_discovery_stops_at_nearest_unrelated_project(work):
    nested = work / "sub"
    nested.mkdir()
    assert discover(nested).root == work
    (nested / "pyproject.toml").write_text('[project]\nname="unrelated"\n')
    assert discover(nested) is None


def test_launcher_uses_locked_project_interpreter_without_recursion(work, monkeypatch):
    (work / "uv.lock").write_text("version = 1")
    monkeypatch.setattr(sys, "argv", ["tactus", "analyze", "stereo", "width", "audio.wav"])
    calls = []

    class Completed:
        returncode = 7

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.main() == 7
    command, kwargs = calls[0]
    assert command[1:5] == ["run", "--project", str(work), "--locked"]
    assert ["python", "-m", "tactus.cli"] == command[6:9]
    assert kwargs["env"]["TACTUS_PROJECT_ROOT"] == str(work)
    assert "cwd" not in kwargs


def test_launcher_missing_lock_never_falls_back(work, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["tactus", "analyze", "level", "rms", "audio.wav"])
    assert launcher.main() == 2
    assert "uv.lock" in json.loads(capsys.readouterr().out)["error"]["message"]


def test_analysis_attachments_require_out_and_clean_failed_output(work, capsys):
    assert main(["analyze", "stereo", "width", "audio.wav", "--scale", "1"]) == 1
    assert "--out" in json.loads(capsys.readouterr().out)["error"]["message"]
    (work / "local_analysis.py").write_text("""from pathlib import Path

def width(audio, sample_rate, *, out=None):
    Path(out).write_text("partial")
    raise RuntimeError("cannot measure")
""")
    assert main(["analyze", "stereo", "width", "audio.wav", "--out", "results"]) == 1
    assert not list((work / "results").iterdir())


def test_analysis_rejects_input_changed_while_decoding(work, monkeypatch, capsys):
    from tactus import analyze

    read = analyze.sf.read

    def changing_read(path, **kwargs):
        result = read(path, **kwargs)
        sf.write(path, np.zeros((64, 2)), 8000, subtype="FLOAT")
        return result

    monkeypatch.setattr(analyze.sf, "read", changing_read)
    assert main(["analyze", "level", "rms", "audio.wav"]) == 1
    assert "input changed" in json.loads(capsys.readouterr().out)["error"]["message"]


def test_project_source_changes_are_detected(work, capsys):
    (work / "local_analysis.py").write_text("""from pathlib import Path

def width(audio, sample_rate):
    Path(__file__).write_text("# changed while measuring")
    return {"value": 1}
""")
    assert main(["analyze", "stereo", "width", "audio.wav"]) == 1
    assert "source or project configuration changed" in capsys.readouterr().out


@pytest.mark.parametrize("parameter", ["callable_command", "param_names", "help"])
def test_dispatch_parameter_names_are_reserved(work, capsys, parameter):
    (work / "local_analysis.py").write_text(
        f"def width(audio, sample_rate, *, {parameter}: str = 'bad'): return {{}}"
    )
    assert main(["analyze", "stereo", "width", "audio.wav"]) == 2
    assert "conflicts" in capsys.readouterr().out
