"""Machine-readable analysis output without dropping saved result metadata."""

import json

import numpy as np
import pytest
import soundfile as sf

from tactus.cli import main
from tactus.run import run


@pytest.fixture
def audio_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths = [tmp_path / "one.wav", tmp_path / "two.wav"]
    for path in paths:
        sf.write(path, np.full(800, 0.25), 8000, subtype="FLOAT")
    return paths


def test_json_is_one_array_for_multiple_files(audio_files, capsys):
    assert main(["analyze", "level", "sample_peak", *map(str, audio_files), "--json"]) == 0
    reports = json.loads(capsys.readouterr().out)
    assert [r["path"] for r in reports] == list(map(str, audio_files))
    assert all("schema" in r["result"] for r in reports)


def test_json_shape_stays_an_array_for_one_file(audio_files, capsys):
    assert main(["analyze", "level", "sample_peak", str(audio_files[0]), "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_default_jsonl_is_preserved(audio_files, capsys):
    assert main(["analyze", "level", "sample_peak", *map(str, audio_files)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["analysis"] == "level.sample_peak" for line in lines)


def test_brief_omits_schema_but_saved_result_keeps_it(audio_files, tmp_path, capsys):
    out = tmp_path / "measurements"
    assert main([
        "analyze", "level", "sample_peak", str(audio_files[0]),
        "--brief", "--json", "--out", str(out),
    ]) == 0
    [brief] = json.loads(capsys.readouterr().out)
    saved = json.loads(next(out.glob("*/result.json")).read_text())
    assert "schema" not in brief["result"]
    assert "schema" in saved["result"]
    assert brief["result"] == {k: v for k, v in saved["result"].items() if k != "schema"}
    assert set(brief) == {"path", "analysis", "result"}


def test_multi_output_run_can_be_parsed_once(audio_files, tmp_path, capsys):
    source = tmp_path / "song.py"
    source.write_text(
        "import numpy as np\ndef render():\n"
        "    return {'sample_rate': 8000, 'outputs': "
        "{'mix': np.full(800, .25), 'stem': np.full(800, .1)}}\n"
    )
    run(source, out=tmp_path / "render")
    assert main([
        "analyze", "level", "sample_peak", str(tmp_path / "render"), "--json", "--brief",
    ]) == 0
    reports = json.loads(capsys.readouterr().out)
    assert [r["output"] for r in reports] == ["mix", "stem"]
    assert all("schema" not in r["result"] for r in reports)


def test_json_error_is_one_error_document(audio_files, capsys):
    assert main([
        "analyze", "level", "sample_peak", str(audio_files[0]), "missing.wav", "--json",
    ]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error"
    assert "path does not exist" in report["error"]["message"]
