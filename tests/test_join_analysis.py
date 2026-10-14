"""join analyses on synthetic signals with known answers: loops, clicks, steps, fades, onsets."""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import timemap
from tactus.analysis import join, rhythm, schema
from tactus.cli import main

SR = 48000


def sine(freq, seconds, amp=0.5, rate=SR):
    return amp * np.sin(2 * np.pi * freq * np.arange(round(seconds * rate)) / rate)


def noise(seconds, rms, seed):
    return rms * np.random.default_rng(seed).standard_normal(round(seconds * SR))


# -- seams ---------------------------------------------------------------------------------


def test_clean_loop_wrap_reads_like_any_other_position():
    loop = sine(440.0, 1.0)  # exactly 440 periods: the wrap continues the waveform
    result = join.seams(loop, SR, wrap=True, reference_s=[0.25, 0.5, 0.75])
    (wrap,) = result["joins"]
    assert wrap["kind"] == "wrap" and wrap["frame"] == SR and wrap["to_s"] == 0.0
    one_sample = 0.5 * math.sin(2 * math.pi * 440 / SR)
    assert wrap["step"] == pytest.approx(one_sample, rel=1e-6)
    assert wrap["step"] == pytest.approx(result["reference_step_median"], rel=1e-6)
    assert wrap["residual_db"] < 10
    assert wrap["residual_db"] == pytest.approx(result["reference_residual_db_median"], abs=0.5)
    assert abs(wrap["hf_burst_db"]) < 0.5
    assert wrap["level_change_db"] == pytest.approx(0, abs=1e-9)
    schema.validate(result)


def test_clicked_loop_wrap_step_is_the_analytic_jump():
    freq = 441.3
    loop = sine(freq, 1.0)
    clean = join.seams(sine(440.0, 1.0), SR, wrap=True)["joins"][0]
    (wrap,) = join.seams(loop, SR, wrap=True)["joins"]
    expected = abs(0.0 - 0.5 * math.sin(2 * math.pi * freq * (SR - 1) / SR))
    assert wrap["step"] == pytest.approx(expected, rel=1e-9)
    assert wrap["residual_db"] > clean["residual_db"] + 40
    assert wrap["hf_burst_db"] > 20


def test_phase_flip_at_a_zero_crossing_has_no_step_but_breaks_slope_and_prediction():
    tone = sine(500.0, 1.0)  # 96 samples per period: frame 24000 is a zero crossing
    flipped = tone.copy()
    flipped[24000:] *= -1
    result = join.seams(flipped, SR, at_s=[0.5], reference_s=[0.25, 0.75])
    (seam,) = result["joins"]
    assert seam["step"] == pytest.approx(result["reference_step_median"], rel=1e-3)
    assert seam["slope_step"] > 100 * result["references"][0]["slope_step"]
    assert seam["residual_db"] > result["reference_residual_db_max"] + 40


def test_click_and_downbeat_with_equal_album_ratio_are_told_apart():
    # The album check divided max |dx| within +/-5 ms by the tape's p99.9. A kick with a
    # 2 ms attack and an impulse of the same max |dx| give the same ratio.
    t = np.arange(SR) / SR
    kick = 0.5 * np.exp(-20 * t) * np.sin(2 * np.pi * 60 * t) * np.minimum(1, t / 0.002)
    height = float(np.max(np.abs(np.diff(kick[:240]))))
    bed = noise(2.0, 0.0005, 0)
    clicked, kicked = bed.copy(), bed.copy()
    clicked[SR] += height
    kicked[SR:] += kick
    window = slice(SR - 240, SR + 240)
    assert np.max(np.abs(np.diff(clicked[window]))) == pytest.approx(
        np.max(np.abs(np.diff(kicked[window]))), rel=0.2
    )
    refs = [0.5, 0.7, 1.3, 1.5]
    click = join.seams(clicked, SR, at_s=[1.0], reference_s=refs)["joins"][0]
    downbeat = join.seams(kicked, SR, at_s=[1.0], reference_s=refs)["joins"][0]
    assert click["residual_db"] > downbeat["residual_db"] + 10
    assert click["hf_burst_db"] > downbeat["hf_burst_db"] + 3
    assert click["slope_step"] > 5 * downbeat["slope_step"]
    assert downbeat["level_change_db"] > 20  # the downbeat is a level change, not a break


def test_dc_step_reports_the_offset_and_a_level_change():
    bed = sine(220.0, 1.0, amp=0.05)
    stepped = bed.copy()
    stepped[SR // 2 :] += 0.1
    (seam,) = join.seams(stepped, SR, at_s=[0.5])["joins"]
    assert seam["step"] == pytest.approx(0.1, abs=0.01)
    assert seam["residual_db"] > 30
    assert seam["level_change_db"] > 5


def test_level_change_and_digital_silence():
    blocks = np.concatenate((noise(1.0, 0.1, 1), noise(1.0, 0.1 * 10 ** (-6 / 20), 2)))
    (seam,) = join.seams(blocks, SR, at_s=[1.0])["joins"]
    assert seam["level_before_dbfs"] == pytest.approx(-20, abs=0.1)
    assert seam["level_change_db"] == pytest.approx(-6, abs=0.1)
    silent_tail = np.concatenate((noise(1.0, 0.1, 1), np.zeros(SR)))
    result = join.seams(silent_tail, SR, at_s=[1.0])
    (seam,) = result["joins"]
    assert seam["level_after_dbfs"] is None and seam["level_change_db"] is None
    assert seam["level_before_dbfs"] == pytest.approx(-20, abs=0.1)
    json.dumps(result, allow_nan=False)
    silence = join.seams(np.zeros(SR), SR, at_s=[0.5], wrap=True)
    assert all(
        seam[key] is None
        for seam in silence["joins"]
        for key in ("hf_burst_db", "level_before_dbfs", "peak_dbfs")
    )
    assert {seam["residual_db"] for seam in silence["joins"]} == {0.0}   # silence after silence
    json.dumps(silence, allow_nan=False)


def test_a_hit_out_of_digital_silence_reads_as_unpredictable():
    # dig's *_stab stems: a loop ending in exact zeros wraps to a hit on its downbeat. Silence
    # predicts silence, so the hit is the error, as loud as it is (here 0.1 FS -> 100 dB).
    hit = np.concatenate((np.zeros(SR), 0.1 * np.exp(-np.arange(SR) / 2000.0)))
    (seam,) = join.seams(hit, SR, at_s=[1.0])["joins"]
    assert seam["step"] == pytest.approx(0.1)
    assert seam["residual_db"] == pytest.approx(100, abs=0.01)


def test_references_show_what_one_max_step_ratio_hides():
    # The One Tape cruise shape: smooth tail near -0.07, smooth head near +0.15, one drum
    # transient inside that is larger than the wrap step.
    t = np.arange(4 * SR) / SR
    loop = 0.15 - 0.22 * t / 4 + 0.03 * np.sin(2 * np.pi * 55 * t)
    hit = round(1.3 * SR)
    loop[hit : hit + 400] += 0.33 * np.exp(-np.arange(400) / 60) * np.sign(
        np.random.default_rng(3).standard_normal(400)
    )
    bars = [0.5 * k for k in range(1, 8)]
    result = join.seams(loop, SR, wrap=True, reference_s=bars)
    (wrap,) = result["joins"]
    assert wrap["step"] == pytest.approx(0.22, abs=0.01)
    assert wrap["step"] > 20 * result["reference_step_median"]
    assert result["typical_step_max"] > wrap["step"]  # the old check passed this wrap


def test_wrap_range_inside_a_longer_file_and_short_loops():
    tone = sine(440.0, 3.0)
    result = join.seams(tone, SR, wrap_range_s=[1.0, 2.0])
    (wrap,) = result["joins"]
    assert (wrap["frame"], wrap["to_s"]) == (2 * SR, 1.0)
    assert wrap["residual_db"] < 10
    whole = join.seams(tone, SR, wrap_range_s=[0.0, 3.0])["joins"][0]
    assert whole["frame"] == 3 * SR
    short = join.seams(sine(441.3, 0.01), SR, wrap=True)["joins"][0]
    assert short["window_samples"] == 240  # half the 480-frame loop


@pytest.mark.parametrize(
    "kwargs",
    [
        {"at_s": [0.0]},
        {"at_s": [1.0]},
        {"at_s": [-0.5]},
        {"reference_s": [2.0]},
        {"wrap_range_s": [0.5, 1.5]},
        {"wrap_range_s": [0.5]},
        {"hf_hz": 30000.0},
        {"lpc_order": 0},
    ],
)
def test_invalid_positions_and_parameters_raise(kwargs):
    with pytest.raises(ValueError):
        join.seams(sine(440, 1.0), SR, **kwargs)


def test_stereo_click_in_one_channel_is_reported():
    left = sine(440.0, 1.0)
    right = left.copy()
    right[SR // 2] += 0.3
    stereo = np.stack([left, right], axis=1)
    (seam,) = join.seams(stereo, SR, at_s=[0.5])["joins"]
    mono = join.seams(left, SR, at_s=[0.5])["joins"][0]
    assert seam["step"] > 0.25 > mono["step"]
    assert seam["residual_db"] > mono["residual_db"] + 20


def test_positions_resolve_with_frame_of_and_keep_declared_order():
    tone = sine(440.0, 1.0)
    result = join.seams(tone, SR, at_s=[0.75, 0.25 + 0.5 / SR], wrap=True)
    assert [j["frame"] for j in result["joins"]] == [36000, 12001, SR]
    assert [j["kind"] for j in result["joins"]] == ["join", "join", "wrap"]


# -- fades ---------------------------------------------------------------------------------


def _crossfade(shape):
    a, b = noise(2.0, 0.1, 4), noise(2.0, 0.1, 5)
    i = np.arange(len(a))
    g = np.clip((i - (SR - 2400)) / 4800, 0, 1)
    gains = {
        "equal_gain": (1 - g, g),
        "equal_power": (np.cos(g * np.pi / 2), np.sin(g * np.pi / 2)),
        "cut": ((i < SR) * 1.0, (i >= SR) * 1.0),
    }[shape]
    return a * gains[0] + b * gains[1]


@pytest.mark.parametrize(
    "shape,dip", [("equal_gain", -3.0), ("equal_power", 0.0), ("cut", 0.0)]
)
def test_crossfade_contour(shape, dip):
    result = join.fades(_crossfade(shape), SR, at_s=[1.0], span_s=0.3, window_s=0.02)
    (position,) = result["positions"]
    assert position["dip_db"] == pytest.approx(dip, abs=0.6)
    assert position["bump_db"] < 0.6
    assert position["before_dbfs"] == pytest.approx(-20, abs=0.3)
    schema.validate(result)
    offsets = [p["offset_s"] for p in result["curve"]]
    assert 0.0 in offsets and min(offsets) >= -0.28 - 1e-9 and max(offsets) <= 0.3 + 1e-9
    assert {p["position"] for p in result["curve"]} == {0}


def test_fade_level_step_is_not_a_dip_and_wrap_contour():
    step = np.concatenate((noise(1.0, 0.1, 6), noise(1.0, 0.05, 7)))
    (position,) = join.fades(step, SR, at_s=[1.0], span_s=0.3, window_s=0.02)["positions"]
    assert position["after_dbfs"] - position["before_dbfs"] == pytest.approx(-6, abs=0.5)
    assert position["dip_db"] > -0.8 and position["bump_db"] < 0.8
    loop = join.fades(sine(440.0, 1.0), SR, wrap=True)["positions"][0]
    assert loop["kind"] == "wrap" and abs(loop["dip_db"]) < 0.3


# -- onset phase ---------------------------------------------------------------------------


def clicks(times, seconds):
    x = np.zeros(round(seconds * SR))
    burst = np.random.default_rng(1).standard_normal(200) * np.exp(-np.arange(200) / 30) * 0.5
    for t in times:
        i = round(t * SR)
        x[i : i + 200] += burst
    return x


BPM = 88
BEAT = 60 / BPM


def _frontend_offset_ms(times, seconds):
    found = np.asarray(rhythm.onsets(clicks(times, seconds), SR)["onsets_s"])
    assert len(found) == len(times)
    return float(np.median(found - np.asarray(times)) * 1000)


@pytest.mark.parametrize("shift_ms", [10.0, 25.0])
def test_late_onsets_read_their_shift_plus_the_frontend_offset(shift_ms):
    grid = 0.5 + BEAT * np.arange(16)
    played = grid + shift_ms / 1000
    frontend = _frontend_offset_ms(list(played), 13.0)
    result = join.onset_phase(
        clicks(played, 13.0), SR, ranges_s=[[0.4, 12.0]], bpm=BPM, origin_s=0.5
    )
    (rng,) = result["ranges"]
    assert rng["count"] == 16
    hop_ms = result["resolution_ms"]
    assert hop_ms == pytest.approx(5.0)
    assert rng["median_offset_ms"] == pytest.approx(shift_ms + frontend, abs=1e-6)
    assert abs(rng["median_offset_ms"] - shift_ms) <= hop_ms
    by_beats = join.onset_phase(
        clicks(played, 13.0), SR, ranges_s=[[0.4, 12.0]], beat_s=list(grid)
    )["ranges"][0]
    assert by_beats["median_offset_ms"] == pytest.approx(rng["median_offset_ms"], abs=1e-9)
    schema.validate(result)


def test_eighth_note_material_against_the_declared_subdivision():
    offbeats = list(0.5 + BEAT * (np.arange(12) + 0.5))
    audio = clicks(offbeats, 10.0)
    eighths = join.onset_phase(audio, SR, ranges_s=[[0.4, 9.5]], bpm=BPM, origin_s=0.5,
                               subdivision=2)
    quarters = join.onset_phase(audio, SR, ranges_s=[[0.4, 9.5]], bpm=BPM, origin_s=0.5)
    assert eighths["ranges"][0]["median_abs_offset_ms"] < eighths["resolution_ms"]
    assert quarters["ranges"][0]["median_abs_offset_ms"] == pytest.approx(
        BEAT / 2 * 1000, abs=quarters["resolution_ms"]
    )
    assert all(abs(abs(o["offset_subdivisions"]) - 0.5) < 0.02 for o in quarters["onsets"])


def test_empty_range_and_grid_errors():
    audio = clicks([1.0], 3.0)
    result = join.onset_phase(audio, SR, ranges_s=[[1.5, 2.5], [0.9, 1.2]], bpm=120)
    empty, one = result["ranges"]
    assert empty == {
        "start_s": 1.5, "end_s": 2.5, "count": 0, "median_offset_ms": None,
        "median_abs_offset_ms": None,
    }
    assert one["count"] == 1 and result["onsets"][0]["range"] == 1
    schema.validate(result)
    json.dumps(result, allow_nan=False)
    for kwargs in (
        {"ranges_s": [[0.0, 1.0]]},
        {"ranges_s": [[1.0, 0.5]], "bpm": 120},
        {"ranges_s": [[0.0, 1.0]], "bpm": 120, "beat_s": [0.0, 0.5]},
        {"ranges_s": [[0.0, 1.0]], "beat_s": [0.5]},
        {"bpm": -1.0},
    ):
        with pytest.raises(ValueError):
            join.onset_phase(audio, SR, **kwargs)


# -- a run's map turned into positions (the recipe in docs/analysis.md) ---------------------


def seam_arguments(time_map, rate, segment):
    """seams keyword arguments for one map segment: joins, bar lines and the loop wrap."""
    m = timemap.to_seconds(time_map, rate)
    seg = m["segments"][segment]
    start, end = seg["start"], seg["end"]
    grid = m.get("outputs", {}).get(seg["output"], {}).get("grid", {})
    inner = [b for b in grid.get("bars", []) if start < b < end]
    at = set()
    for exit_point in seg["joins"]:
        points = inner if exit_point["at"] == "bars" else [start + t for t in exit_point["at"]]
        at.update(p for p in points if start < p < end)
    arguments = {"at_s": sorted(at), "reference_s": inner}
    if seg["loop"]:
        arguments["wrap_range_s"] = [start, end]
    return seg["output"], arguments


def switches(time_map, outputs, segment):
    """Every exit from `segment` into another segment, joined as a hard switch: yields
    (target, audio, frame). Change the joining to your player's rule (crossfades, overlaps)."""
    segments = time_map["segments"]
    seg = segments[segment]
    grid = time_map.get("outputs", {}).get(seg["output"], {}).get("grid", {})
    x = outputs[seg["output"]]
    for exit_point in seg["joins"]:
        if exit_point["at"] == "bars":
            points = [*grid.get("bars", []), grid.get("end", seg["end"])]
        else:
            points = [seg["start"] + f for f in exit_point["at"]]
        to = exit_point["to"]
        if isinstance(to, dict):
            to = [n for n, s in segments.items() if set(to["tags"]) & set(s["tags"])]
        for target in to or []:  # null: the player decides; list those targets yourself
            t = segments[target]
            for p in sorted({p for p in points if seg["start"] < p <= seg["end"]}):
                enter = t["start"] + (p - seg["start"] if exit_point["keep_phase"] else 0)
                after = outputs[t["output"]][enter : t["tail_end"]].copy()
                if p == seg["end"]:  # leaving at the body's end: its tail rings over the next
                    tail = x[seg["end"] : seg["tail_end"]][: len(after)]
                    after[: len(tail)] += tail
                yield target, np.concatenate([x[seg["start"] : p], after]), p - seg["start"]


WORK = """import numpy as np

def render():
    rate = 48000
    t = np.arange(4 * rate) / rate
    loop = 0.5 * np.sin(2 * np.pi * 441.3 * t)
    tape = np.concatenate([0.5 * np.sin(2 * np.pi * 440 * t), loop])
    stop = np.concatenate([0.5 * np.sin(2 * np.pi * 220 * t[:rate - 4800]), np.full(4800, 0.25)])
    bars = [0, rate, 2 * rate, 3 * rate]
    return {"sample_rate": rate,
            "outputs": {"loop": loop, "tape": tape, "stop": stop},
            "map": {"outputs": {"loop": {"grid": {"bars": bars, "end": 4 * rate}}},
                    "segments": {
                        "loop": {"output": "loop", "start": 0, "end": 4 * rate, "loop": True,
                                 "joins": [{"at": "bars", "to": ["verse"]}]},
                        "verse": {"output": "tape", "start": 4 * rate, "end": 8 * rate,
                                  "joins": [{"at": [rate // 2]}]},
                        "stop": {"output": "stop", "start": 0, "end": rate,
                                 "joins": [{"at": [rate], "to": ["loop"]}]}}}}
"""


def test_map_recipe_measures_a_runs_wraps_and_joins(tmp_path, capsys):
    source = tmp_path / "song.py"
    source.write_text(WORK)
    run = tmp_path / "run"
    assert main(["run", str(source), "--out", str(run)]) == 0
    capsys.readouterr()
    manifest = json.loads((run / "manifest.json").read_text())
    time_map = json.loads((run / "map.json").read_text())
    rate = manifest["sample_rate"]
    measured = {}
    for name in time_map["segments"]:
        output, arguments = seam_arguments(time_map, rate, name)
        audio, _ = sf.read(run / manifest["outputs"][output]["file"])
        measured[name] = (arguments, join.seams(audio, rate, **arguments))
    loop_args, loop = measured["loop"]
    assert loop_args == {
        "at_s": [1.0, 2.0, 3.0], "reference_s": [1.0, 2.0, 3.0], "wrap_range_s": [0.0, 4.0]
    }
    wrap = loop["joins"][-1]
    assert wrap["kind"] == "wrap" and wrap["frame"] == 4 * rate
    assert wrap["step"] > 10 * loop["reference_step_median"]
    verse_args, verse = measured["verse"]
    assert verse_args == {"at_s": [4.5], "reference_s": []}
    assert [j["frame"] for j in verse["joins"]] == [round(4.5 * rate)]
    # Switches into another segment are measured on the two clips joined. A turntable stop
    # holding 0.25 FS (dig's falls) into a loop starting at 0 is a 0.25 step.
    outputs = {n: sf.read(run / e["file"])[0] for n, e in manifest["outputs"].items()}
    found = {}
    for name in time_map["segments"]:
        for target, audio, frame in switches(time_map, outputs, name):
            (seam,) = join.seams(audio, rate, at_s=[frame / rate])["joins"]
            found.setdefault((name, target), []).append(round(seam["step"], 3))
    assert found[("stop", "loop")] == [0.25]
    assert len(found[("loop", "verse")]) == 4   # three inner bar lines and the loop's end
    # The same positions through the CLI, on the run directory (every output measured).
    assert main(["analyze", "join", "seams", str(run), "--wrap", "--brief"]) == 0
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [r["output"] for r in reports] == ["loop", "stop", "tape"]
    assert all(r["result"]["joins"][0]["kind"] == "wrap" for r in reports)
    assert main(
        ["analyze", "join", "seams", str(run), "--at-s", "[0.25, 0.5]", "--brief"]
    ) == 0
    reports = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [j["frame"] for j in reports[0]["result"]["joins"]] == [rate // 4, rate // 2]


def test_cli_rejects_positions_without_a_traceback(tmp_path, capsys):
    path = tmp_path / "tone.wav"
    sf.write(path, sine(440.0, 1.0), SR, subtype="FLOAT")
    code = main(["analyze", "join", "seams", str(path), "--at-s", "[5.0]"])
    assert code != 0
    captured = capsys.readouterr()
    error = json.loads(captured.out)["error"]
    assert error["code"] == "analysis_failed" and "at_s 5.0 s" in error["message"]
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("document", ["docs/analysis.md", "skills/measure/SKILL.md"])
def test_documented_map_recipe_is_the_tested_one(document):
    text = (Path(__file__).resolve().parents[1] / document).read_text(encoding="utf-8")
    assert inspect.getsource(seam_arguments) in text
    assert inspect.getsource(switches) in text
