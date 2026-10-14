"""A performance as an input: JSON parameter files and the work's own fail-fast check."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import tactus
from tactus import InvalidParameters, RunError, run
from tactus.cli import main

WORK = """import numpy as np
import tactus

def render(*, tape=None, gain=0.5):
    if tape is not None and not tape.get("tracks"):
        raise tactus.InvalidParameters("a tape holds 1 to 12 tracks")
    n = 8 * (len(tape["tracks"]) if tape else 1)
    return {"sample_rate": 8000, "outputs": {"mix": np.full(n, gain)}}
"""


@pytest.fixture
def work(tmp_path):
    entry = tmp_path / "work" / "song.py"
    entry.parent.mkdir()
    entry.write_text(WORK)
    tape = tmp_path / "tapes" / "demo.json"
    tape.parent.mkdir()
    tape.write_bytes(b'{"tracks": [{"station": "block"}, {"station": "crates"}]}\n')
    return entry, tape


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def test_param_file_binds_and_travels_with_the_run(work, tmp_path):
    entry, tape = work
    result = run(entry, out=tmp_path / "run", param_files={"tape": tape}, params={"gain": 0.25})
    receipt = load(result["receipt"])
    assert receipt["parameters"]["tape"] == {"tracks": [{"station": "block"}, {"station": "crates"}]}
    assert receipt["parameters"]["gain"] == 0.25
    payload = tape.read_bytes()
    assert receipt["parameter_files"] == {
        "tape": {
            "path": str(tape),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "copy": "parameters/tape.json",
        }
    }
    copy = tmp_path / "run" / "parameters" / "tape.json"
    assert copy.read_bytes() == payload
    assert load(result["manifest"])["outputs"]["mix"]["frames"] == 16
    # The copy renders the same performance again.
    again = run(entry, out=tmp_path / "again", param_files={"tape": copy}, params={"gain": 0.25})
    assert load(again["manifest"])["outputs"] == load(result["manifest"])["outputs"]


def test_runs_without_files_have_no_record(work, tmp_path):
    entry, _ = work
    result = run(entry, out=tmp_path / "run")
    assert "parameter_files" not in load(result["receipt"])
    assert not (tmp_path / "run" / "parameters").exists()


@pytest.mark.parametrize(
    "files,params,message",
    [
        ({"tape": "missing.json"}, {}, "parameter file tape=missing.json"),
        ({"tape": "BAD"}, {}, "parameter file tape="),
        ({"tape": "DUP"}, {}, "duplicate parameter key: tracks"),
        ({"tape": "NAN"}, {}, "finite JSON"),
        ({"tape": "OK"}, {"tape": {}}, "given both inline and as a file"),
        ({"not a name": "OK"}, {}, "must be a parameter name"),
    ],
)
def test_bad_param_files_are_request_errors(work, tmp_path, files, params, message):
    entry, tape = work
    contents = {"BAD": "{tracks", "DUP": '{"tracks": [], "tracks": []}', "NAN": "[NaN]"}
    resolved = {}
    for name, path in files.items():
        if path in contents:
            target = tmp_path / f"{path}.json"
            target.write_text(contents[path])
            path = target
        resolved[name] = tape if path == "OK" else path
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "run", param_files=resolved, params=params)
    assert (failure.value.code, failure.value.phase) == ("invalid_request", "request")
    assert message in str(failure.value)
    assert not (tmp_path / "run").exists()


def test_invalid_parameters_from_render_fail_fast(work, tmp_path):
    entry, _ = work
    empty = tmp_path / "empty.json"
    empty.write_text('{"tracks": []}')
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "run", param_files={"tape": empty})
    assert (failure.value.code, failure.value.phase) == ("invalid_parameters", "bind")
    assert "a tape holds 1 to 12 tracks" in str(failure.value)
    assert failure.value.exit_code == 2
    assert not (tmp_path / "run").exists()
    assert tactus.InvalidParameters is InvalidParameters and issubclass(InvalidParameters,
                                                                        ValueError)


def test_cli_param_file(work, tmp_path, capsys):
    entry, tape = work
    out = tmp_path / "run"
    code = main(["run", str(entry), "--out", str(out), "--param-file", f"tape={tape}",
                 "--params", '{"gain": 0.1}'])
    result = json.loads(capsys.readouterr().out)
    assert code == 0, result
    assert load(result["receipt"])["parameter_files"]["tape"]["copy"] == "parameters/tape.json"
    empty = tmp_path / "empty.json"
    empty.write_text('{"tracks": []}')
    assert main(["run", str(entry), "--out", str(tmp_path / "bad"), "--param-file",
                 f"tape={empty}"]) == 2
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "invalid_parameters"
    for arguments, message in (
        (["--param-file", "tape"], "needs NAME=FILE"),
        (["--param-file", f"tape={tape}", "--param-file", f"tape={tape}"], "given twice"),
        (["--param-file", f"tape={tape}", "--params", '{"tape": 1}'], "both inline"),
    ):
        assert main(["run", str(entry), "--out", str(tmp_path / "x"), *arguments]) == 2
        error = json.loads(capsys.readouterr().out)["error"]
        assert error["code"] == "invalid_request" and message in error["message"]


def test_a_rejected_performance_prints_no_traceback(work, tmp_path, capsys):
    entry, _ = work
    empty = tmp_path / "empty.json"
    empty.write_text('{"tracks": []}')
    with pytest.raises(RunError):
        run(entry, out=tmp_path / "run", param_files={"tape": empty})
    assert "Traceback" not in capsys.readouterr().err
    entry.write_text(WORK.replace("raise tactus.InvalidParameters", "raise RuntimeError"))
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "crash", param_files={"tape": empty})
    assert failure.value.code == "execution_failed"
    assert "Traceback" in capsys.readouterr().err   # a crash still shows where it broke
