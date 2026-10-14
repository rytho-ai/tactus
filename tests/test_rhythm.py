"""Native beat tracking integration: numerical parity, known signals and CLI contracts."""

from __future__ import annotations

import json

import numpy as np
import pyqmdsp
import pytest
import soundfile as sf

from tactus.analysis import rhythm
from tactus.cli import main


def clicks(rate, times):
    audio = np.zeros(int((times[-1] + 0.5) * rate))
    t = np.arange(int(0.02 * rate)) / rate
    hit = np.sin(2 * np.pi * 1000 * t) * np.exp(-t * 250)
    for time in times:
        start = round(time * rate)
        audio[start : start + len(hit)] += hit
    return audio


@pytest.mark.parametrize("rate", [22050, 44100, 48000])
@pytest.mark.parametrize("stereo", [False, True])
def test_matches_package_exactly_without_mutating_input(rate, stereo):
    audio = clicks(rate, np.arange(32) * 0.5)
    if stereo:
        # Unequal channels exercise the engine's mean downmix rather than a sum.
        audio = np.column_stack([audio, audio * 0.31])
    before = audio.copy()
    expected = pyqmdsp.beats(audio, rate)
    actual = rhythm.beats(audio, rate)
    assert len(actual["beats_s"]) > 20
    np.testing.assert_array_equal(actual["beats_s"], expected["beats_s"])
    np.testing.assert_array_equal(actual["tempo_curve"], expected["tempo_curve"])
    assert actual["bpm"] == expected["bpm"]
    np.testing.assert_array_equal(audio, before)
    assert json.loads(json.dumps(actual, allow_nan=False)) == actual


@pytest.mark.parametrize("bpm", [90, 120, 150])
def test_tracks_known_clicks(bpm):
    truth = np.arange(40) * (60 / bpm)
    result = rhythm.beats(clicks(44100, truth), 44100)
    assert result["bpm"] == pytest.approx(bpm, abs=3)
    assert len(result["beats_s"]) > len(truth) / 2
    distances = np.min(np.abs(np.array(result["beats_s"])[:, None] - truth), axis=1)
    assert np.mean(distances <= 0.07) > 0.9


def test_tracks_tempo_change():
    early = np.arange(24) * 0.6
    switch = 24 * 0.6
    late = switch + np.arange(24) * (60 / 130)
    result = rhythm.beats(clicks(48000, np.concatenate([early, late])), 48000)
    times = np.array(result["beats_s"][:-1])
    curve = np.array(result["tempo_curve"])
    assert np.median(curve[times < switch - 1]) == pytest.approx(100, abs=3)
    assert np.median(curve[times > switch + 3]) == pytest.approx(130, abs=3)


@pytest.mark.parametrize("audio", [np.zeros(48000 * 12), clicks(48000, [0, 0.5, 1])])
def test_no_estimate_is_json_null(audio):
    result = rhythm.beats(audio, 48000)
    assert {key: value for key, value in result.items() if key != "schema"} == {
        "beats_s": [],
        "bpm": None,
        "tempo_curve": [],
    }


@pytest.mark.parametrize(
    "audio,rate,match",
    [
        (np.empty(0), 48000, "empty"),
        (np.array([np.nan]), 48000, "finite"),
        (np.array([np.inf]), 48000, "finite"),
        (np.zeros((2, 2, 2)), 48000, "1-D or 2-D"),
        (np.zeros(100), 0, "positive"),
        (np.zeros(100), -1, "positive"),
    ],
)
def test_invalid_input_raises(audio, rate, match):
    with pytest.raises(ValueError, match=match):
        rhythm.beats(audio, rate)


def test_cli_on_saved_stereo_audio(tmp_path, capsys):
    audio = clicks(44100, np.arange(32) * 0.5)
    wav = tmp_path / "loop.wav"
    sf.write(wav, np.column_stack([audio, audio * 0.31]), 44100, subtype="PCM_24")
    assert main(["analyze", "rhythm", "beats", str(wav)]) == 0
    report = json.loads(capsys.readouterr().out)
    decoded, rate = sf.read(wav, dtype="float64")
    from tactus.inputs.pool import hash_file

    assert report.pop("input_sha256") == hash_file(wav)
    provenance = report.pop("provenance")
    assert provenance["callable"]["callable"] == "tactus.analysis.rhythm:beats"
    assert report == {
        "analysis": "rhythm.beats",
        "revision": 1,
        "params": {},
        "path": str(wav),
        "sample_rate": rate,
        "result": rhythm.beats(decoded, rate),
    }


def test_cli_analyzes_every_run_output(tmp_path, capsys):
    source = tmp_path / "song.py"
    source.write_text("""import numpy as np

def render():
    rate = 44100
    audio = np.zeros(rate * 16)
    t = np.arange(882) / rate
    hit = np.sin(2 * np.pi * 1000 * t) * np.exp(-250 * t)
    for start in range(0, len(audio) - len(hit), rate // 2):
        audio[start:start + len(hit)] += hit
    return {"sample_rate": rate, "outputs": {"loop": audio, "silence": audio * 0}}
""")
    out = tmp_path / "run"
    assert main(["run", str(source), "--out", str(out)]) == 0
    capsys.readouterr()
    assert main(["analyze", "rhythm", "beats", str(out)]) == 0
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["output"] for r in reports] == ["loop", "silence"]
    for report in reports:
        audio, rate = sf.read(report["path"], dtype="float64")
        assert report["result"] == rhythm.beats(audio, rate)
    assert len(reports[0]["result"]["beats_s"]) > 20
    assert reports[1]["result"]["bpm"] is None


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (["analyze", "--help"], "rhythm"),
        (["analyze", "rhythm", "--help"], "beats"),
        (["analyze", "rhythm", "beats", "--help"], "7.45"),
    ],
)
def test_generated_help(arguments, expected, capsys):
    with pytest.raises(SystemExit) as exc:
        main(arguments)
    assert exc.value.code == 0
    assert expected in capsys.readouterr().out
