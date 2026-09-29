"""Environment diagnostics and functional CLI execution, failure and cancellation checks."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tactus.cli import main


def test_material_add_imports_files_and_prints_refs(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    a = tmp_path / "a.wav"
    a.write_bytes(b"a bytes")
    b = tmp_path / "b.wav"
    b.write_bytes(b"b bytes")
    assert main(["material", "add", str(a), str(b)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ok"
    import hashlib

    assert report["materials"] == {
        str(a): f"sha256:{hashlib.sha256(a.read_bytes()).hexdigest()}",
        str(b): f"sha256:{hashlib.sha256(b.read_bytes()).hexdigest()}",
    }


def test_material_add_imports_a_folder_and_prints_a_tree_ref(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    folder = tmp_path / "instrument"
    (folder / "samples").mkdir(parents=True)
    (folder / "samples" / "note.wav").write_bytes(b"fake sample bytes")
    (folder / "piano.sfz").write_text("<region> sample=samples/note.wav\n")
    assert main(["material", "add", str(folder)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ok"
    ref = report["materials"][str(folder)]
    assert ref.startswith("tree:sha256:")

    from tactus.inputs import material

    resolved = material(ref)
    assert (resolved / "piano.sfz").read_text() == "<region> sample=samples/note.wav\n"


def test_material_add_mixes_files_and_folders_in_one_call(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    a = tmp_path / "a.wav"
    a.write_bytes(b"a bytes")
    folder = tmp_path / "instrument"
    (folder / "samples").mkdir(parents=True)
    (folder / "samples" / "note.wav").write_bytes(b"fake sample bytes")
    assert main(["material", "add", str(a), str(folder)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["materials"][str(a)].startswith("sha256:")
    assert report["materials"][str(folder)].startswith("tree:sha256:")


def test_material_add_missing_path_is_a_structured_error_with_nothing_reported(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    present = tmp_path / "present.wav"
    present.write_bytes(b"present bytes")
    missing = tmp_path / "missing.wav"
    assert main(["material", "add", str(present), str(missing)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["code"] == "invalid_request"
    assert not (tmp_path / "pool").exists()  # nothing partially imported


def test_doctor_reports_environment(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["doctor"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["package"] == "tactus"
    assert report["version"] == "0.1.0"
    assert report["status"] == "ok"
    assert report["python"]


def test_version_uses_distribution_metadata(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main(["--version"])
    assert result.value.code == 0
    assert capsys.readouterr().out.strip() == "tactus 0.1.0"


def test_functional_cli_keeps_python_and_native_logs_off_stdout(tmp_path):
    entry = tmp_path / "song.py"
    entry.write_text("""import os
import numpy as np
print("loading author source")
os.write(1, b"native load log\\n")
def render(*, gain=0.2):
    print("rendering")
    os.write(1, b"native render log\\n")
    return {"sample_rate": 8000, "outputs": {"clip": np.full(8, gain)}}
""")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tactus.cli",
            "run",
            str(entry),
            "--out",
            str(tmp_path / "out"),
            "--params",
            '{"gain": 0.1}',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    report = json.loads(result.stdout)
    assert report["status"] == "ok"
    assert Path(report["outputs"]["clip"]).is_file()
    for message in ("loading author source", "native load log", "rendering", "native render log"):
        assert message in result.stderr
        assert message not in result.stdout


@pytest.mark.parametrize(
    "params",
    [
        "{",
        "[]",
        '{"gain": NaN}',
        '{"gain": Infinity}',
        '{"gain": 1e999}',
        '{"gain": 0.1, "gain": 0.2}',
        '{"options": {"a": 1, "a": 2}}',
    ],
)
def test_functional_cli_invalid_json_is_a_structured_request_error(tmp_path, capsys, params):
    assert main(["run", "missing.py", "--out", str(tmp_path / "out"), "--params", params]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["code"] == "invalid_request"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "arguments", [["run"], ["run", "song.py"], ["run", "song.py", "--out", "x", "--unknown"]]
)
def test_functional_cli_argument_errors_are_json(capsys, arguments):
    assert main(arguments) == 2
    assert json.loads(capsys.readouterr().out)["error"]["phase"] == "request"


def test_functional_cli_excerpt_selects_and_slices_from_an_existing_run(tmp_path, capsys):
    entry = tmp_path / "song.py"
    entry.write_text("""import numpy as np
def render():
    return {"sample_rate": 1000, "outputs": {"a": np.linspace(0, 0.5, 1000), "b": np.zeros(1000)}}
""")
    assert main(["run", str(entry), "--out", str(tmp_path / "full")]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "excerpt",
                str(tmp_path / "full"),
                "--out",
                str(tmp_path / "cut"),
                "--range",
                "0.1:0.2",
                "--outputs",
                "a",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    manifest = json.loads(Path(report["manifest"]).read_text())
    assert set(manifest["outputs"]) == {"a"}
    assert manifest["range"] == {
        "start_seconds": 0.1,
        "end_seconds": 0.2,
        "start_frame": 100,
        "end_frame": 200,
        "omitted": [],
    }


def test_functional_cli_excerpt_with_open_end(tmp_path, capsys):
    entry = tmp_path / "song.py"
    entry.write_text("""import numpy as np
def render():
    return {"sample_rate": 1000, "outputs": {"a": np.zeros(1000)}}
""")
    assert main(["run", str(entry), "--out", str(tmp_path / "full")]) == 0
    capsys.readouterr()
    assert (
        main(["excerpt", str(tmp_path / "full"), "--out", str(tmp_path / "cut"), "--range", "0.9:"])
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    manifest = json.loads(Path(report["manifest"]).read_text())
    assert manifest["range"]["end_seconds"] is None
    assert manifest["range"]["end_frame"] is None
    assert manifest["outputs"]["a"]["frames"] == 100


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--range", "bad"),
        ("--range", "1:2:3"),
        ("--range", ":5"),
        ("--range", "one:2"),
        ("--outputs", ""),
        ("--outputs", "a,,b"),
    ],
)
def test_functional_cli_excerpt_bad_range_or_outputs_syntax_is_a_structured_request_error(
    tmp_path, capsys, flag, value
):
    entry = tmp_path / "song.py"
    entry.write_text("""import numpy as np
def render():
    return {"sample_rate": 1000, "outputs": {"a": np.zeros(1000)}}
""")
    assert main(["run", str(entry), "--out", str(tmp_path / "full")]) == 0
    capsys.readouterr()
    arguments = ["excerpt", str(tmp_path / "full"), "--out", str(tmp_path / "cut")]
    if flag == "--range":
        arguments += [flag, value]
    else:
        arguments += ["--range", "0:0.5", flag, value]
    assert main(arguments) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["code"] == "invalid_request"
    assert report["error"]["phase"] == "request"
    assert not (tmp_path / "cut").exists()


def test_functional_cli_excerpt_missing_range_is_an_argument_error(tmp_path, capsys):
    entry = tmp_path / "song.py"
    entry.write_text("""import numpy as np
def render():
    return {"sample_rate": 1000, "outputs": {"a": np.zeros(1000)}}
""")
    assert main(["run", str(entry), "--out", str(tmp_path / "full")]) == 0
    capsys.readouterr()
    assert main(["excerpt", str(tmp_path / "full"), "--out", str(tmp_path / "cut")]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["phase"] == "request"


def test_functional_cli_execution_error_reports_phase_and_exit_code(tmp_path, capsys):
    entry = tmp_path / "song.py"
    entry.write_text("def render(): raise RuntimeError('broken instrument')\n")
    assert main(["run", str(entry), "--out", str(tmp_path / "out")]) == 1
    captured = capsys.readouterr()
    error = json.loads(captured.out)["error"]
    assert error["phase"] == "execute"
    assert error["code"] == "execution_failed"
    assert "broken instrument" in captured.err


@pytest.mark.skipif(os.name != "posix", reason="POSIX CLI cancellation")
def test_functional_cli_cancellation_reaps_worker_and_removes_output(tmp_path):
    entry = tmp_path / "song.py"
    ready = tmp_path / "ready"
    entry.write_text("""import os
import time
from pathlib import Path
def render():
    Path("ready").write_text(str(os.getpid()))
    time.sleep(60)
""")
    out = tmp_path / "out"
    process = subprocess.Popen(
        [sys.executable, "-m", "tactus.cli", "run", str(entry), "--out", str(out)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "worker did not reach render"
        worker_pid = int(ready.read_text())
        process.send_signal(signal.SIGINT)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 130, stderr
        assert json.loads(stdout)["error"]["code"] == "cancelled"
        assert not out.exists()
        with pytest.raises(ProcessLookupError):
            os.kill(worker_pid, 0)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def test_analyze_measures_a_wav_file(tmp_path, capsys):
    import numpy as np
    import soundfile as sf

    wav = tmp_path / "tone.wav"
    t = np.arange(48000) / 48000
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    sf.write(wav, np.stack([tone, tone], axis=1), 48000, subtype="PCM_24")

    assert main(["analyze", "level", "sample_peak", str(wav)]) == 0
    report = json.loads(capsys.readouterr().out.strip())
    assert report["path"] == str(wav)
    assert report["sample_rate"] == 48000
    assert report["analysis"] == "level.sample_peak"
    assert report["revision"] == 1
    assert report["params"] == {}
    assert report["result"]["sample_peak_dbfs"] < 0
    assert "output" not in report


def test_analyze_measures_every_output_in_a_run_directory(tmp_path, capsys):
    entry = tmp_path / "song.py"
    entry.write_text("""import numpy as np
def render():
    t = np.arange(48000) / 48000
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    return {"sample_rate": 48000, "outputs": {"mix": tone, "silence": np.zeros(48000)}}
""")
    assert main(["run", str(entry), "--out", str(tmp_path / "out")]) == 0
    capsys.readouterr()

    assert main(["analyze", "level", "rms", str(tmp_path / "out")]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    names = {report["output"] for report in lines}
    assert names == {"mix", "silence"}
    for report in lines:
        assert report["sample_rate"] == 48000
        assert report["path"].endswith(".wav")
        assert report["analysis"] == "level.rms"


def test_analyze_missing_path_is_a_structured_error(tmp_path, capsys):
    assert main(["analyze", "level", "rms", str(tmp_path / "missing.wav")]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["code"] == "invalid_request"


def test_analyze_directory_without_manifest_is_a_structured_error(tmp_path, capsys):
    empty = tmp_path / "not_a_run"
    empty.mkdir()
    assert main(["analyze", "level", "rms", str(empty)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["code"] == "invalid_request"


def test_analyze_path_without_category_or_name_is_a_structured_request_error(tmp_path, capsys):
    assert main(["analyze", str(tmp_path / "tone.wav")]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["code"] == "invalid_request"
    assert report["error"]["phase"] == "request"


def test_analyze_unknown_category_is_a_structured_request_error(capsys, tmp_path):
    assert main(["analyze", "nope", "rms", str(tmp_path / "tone.wav")]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["code"] == "invalid_request"


def test_analyze_unknown_analysis_is_a_structured_request_error(capsys, tmp_path):
    assert main(["analyze", "level", "nope", str(tmp_path / "tone.wav")]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["code"] == "invalid_request"


def test_analyze_unknown_flag_is_a_structured_request_error(tmp_path, capsys):
    assert main(["analyze", "level", "rms", str(tmp_path / "tone.wav"), "--nope", "1"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["code"] == "invalid_request"


def test_analyze_help_renders_at_all_three_levels(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["analyze", "--help"])
    assert exc.value.code == 0
    top = capsys.readouterr().out
    assert "level" in top and "spectral" in top

    with pytest.raises(SystemExit) as exc:
        main(["analyze", "level", "--help"])
    assert exc.value.code == 0
    category = capsys.readouterr().out
    assert "loudness" in category and "clipping" in category

    with pytest.raises(SystemExit) as exc:
        main(["analyze", "level", "loudness", "--help"])
    assert exc.value.code == 0
    detail = capsys.readouterr().out
    assert "integrated_lufs" in detail and "LUFS" in detail


def test_analyze_spectral_passes_a_custom_flag_through_to_params(tmp_path, capsys):
    import numpy as np
    import soundfile as sf

    wav = tmp_path / "tone.wav"
    t = np.arange(48000) / 48000
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    sf.write(wav, np.stack([tone, tone], axis=1), 48000, subtype="PCM_24")

    assert main(["analyze", "spectral", "peaks", str(wav), "--n", "2"]) == 0
    report = json.loads(capsys.readouterr().out.strip())
    assert report["params"]["n"] == 2
    assert len(report["result"]["peaks"]) <= 2


def test_analyze_stft_requires_out_and_saves_numeric_attachments(tmp_path, capsys):
    import numpy as np
    import soundfile as sf

    wav = tmp_path / "tone.wav"
    t = np.arange(48000) / 48000
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32)
    sf.write(wav, np.stack([tone, tone], axis=1), 48000, subtype="PCM_24")

    assert main(["analyze", "spectral", "stft", str(wav)]) != 0
    assert "pass --out DIR" in capsys.readouterr().out

    out_dir = tmp_path / "out"
    assert main(["analyze", "spectral", "stft", str(wav), "--out", str(out_dir)]) == 0
    written = json.loads(capsys.readouterr().out.strip())
    assert written["revision"] == 2
    ref = written["result"]["level_db"]
    with np.load(ref["file"]) as arrays:
        assert arrays[ref["key"]].shape == tuple(written["result"]["shape"])
    assert "visualization" not in written
