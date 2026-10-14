"""Delivery exporters that read the run's map: web bundles, subtitles and per-frame curves."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tactus import RunError, run
from tactus.analysis import level
from tactus.cli import main
from tactus.commands import Command, add_flags
from tactus.export import BUILTINS, deliver, flag_view

WORK = """import numpy as np
from tactus.timing import Clock

RATE = 8000

def render():
    clock = Clock(sample_rate=RATE, tempo=120)
    t = np.arange(clock.frame(5)) / RATE
    mix = 0.25 * np.sin(2 * np.pi * 220 * t)
    stems = {"mix": np.stack([mix, -mix], axis=1), "bass": 0.5 * mix}
    lyrics = [{"start": 0, "end": 12345, "text": "first line", "status": "checked"},
              {"start": 12345, "end": 20000, "text": "  "},
              {"start": 20000, "end": 32000, "text": "second line", "status": "guess"}]
    return {"sample_rate": RATE, "outputs": stems,
            "map": {"outputs": {"mix": {"grid": clock.grid(1, 4), "lanes": {
                "lyrics": {"kind": "spans", "items": lyrics},
                "sections": {"kind": "spans", "items": [
                    {"start": 0, "end": 16000, "label": "intro"},
                    {"start": 16000, "end": 32000, "label": "verse"}]},
                "kick": {"kind": "points", "items": [{"at": f} for f in clock.grid(1, 4)["bars"]]},
            }}}}}
"""


@pytest.fixture
def rendered(tmp_path):
    entry = tmp_path / "work" / "song.py"
    entry.parent.mkdir()
    entry.write_text(WORK)
    run(entry, out=tmp_path / "run")
    return tmp_path / "run"


def export(run_dir: Path, out: Path, name: str, **params) -> dict:
    result = deliver(run_dir, out=out, command=Command(name, "export", BUILTINS[name]),
                     params=params)
    return json.loads(Path(result["manifest"]).read_text())


def test_runtime_keywords_reach_only_exporters_that_declare_them(rendered, tmp_path):
    seen = {}

    def legacy(outputs, sample_rate, *, out, gain: float = 1.0):
        (out / "x.txt").write_text(str(gain))
        return {"gain": gain}

    def aware(outputs, sample_rate, *, out, time_map=None, run_identity=None):
        seen.update(time_map=time_map, run_identity=run_identity)
        (out / "x.txt").write_text("ok")
        return {}

    deliver(rendered, out=tmp_path / "a", command=Command("legacy", "export", legacy),
            params={"gain": 0.5})
    record = deliver(rendered, out=tmp_path / "b", command=Command("aware", "export", aware),
                     params={})
    saved = json.loads((rendered / "map.json").read_text())
    assert seen["time_map"] == saved
    identity = seen["run_identity"]
    assert identity["run"] == str(rendered) and identity["origin"]["kind"] == "original-render"
    assert identity["manifest_sha256"] and identity["receipt_sha256"] and identity["map_sha256"]
    source = json.loads(Path(record["manifest"]).read_text())["source"]
    assert source["map"] == {"sha256": identity["map_sha256"]}
    for fn in (legacy, aware, *BUILTINS.values()):
        parser = argparse.ArgumentParser()
        names = add_flags(parser, flag_view(fn), {"out"})
        assert "time_map" not in names and "run_identity" not in names
    assert flag_view(legacy) is legacy


def test_tampered_map_fails_export(rendered, tmp_path):
    (rendered / "map.json").write_text("{}\n")
    with pytest.raises(RunError) as failure:
        export(rendered, tmp_path / "web", "web", codec="wav")
    assert failure.value.code == "source_corrupt"
    assert not (tmp_path / "web").exists()


def test_web_wav_reproduces_the_published_pcm(rendered, tmp_path):
    record = export(rendered, tmp_path / "web", "web", codec="wav", peaks=100)
    bundle = json.loads((tmp_path / "web" / "bundle.json").read_text())
    manifest = json.loads((rendered / "manifest.json").read_text())
    receipt_sha = record["source"]["sha256"]
    assert receipt_sha
    for name, item in manifest["outputs"].items():
        entry = bundle["outputs"][name]
        assert entry["file"] == f"audio/{item['file'].replace('.wav', '')}.wav"
        assert (tmp_path / "web" / entry["file"]).read_bytes() == (rendered / item["file"]).read_bytes()
        assert entry["source_sha256"] == item["sha256"] and entry["frames"] == item["frames"]
        assert entry["decoded"] == {"frames": item["frames"], "offset_frames": 0,
                                    "decoder": "soundfile"}
        assert entry["seconds"] == item["frames"] / 8000
        assert len(entry["peaks"]["values"]) == 100 and entry["peaks"]["buckets"] == 100
        assert entry["peak_dbfs"] == item["peak_dbfs"]
    assert bundle["source"]["manifest_sha256"] and bundle["source"]["map_sha256"]
    assert bundle["map"]["outputs"]["mix"]["grid"]["bars"] == [0, 16000, 32000, 48000]
    assert bundle["map_seconds"]["outputs"]["mix"]["grid"]["bars"] == [0.0, 2.0, 4.0, 6.0]
    assert bundle["map_seconds"]["outputs"]["mix"]["lanes"]["lyrics"]["items"][0]["end"] == 12345 / 8000
    assert bundle["outputs"]["mix"]["integrated_lufs"] == pytest.approx(
        level.loudness(np.load(rendered / "render" / "mix.npy"), 8000)["integrated_lufs"]
    )


def test_web_flac_is_lossless_and_codecs_are_explicit(rendered, tmp_path):
    export(rendered, tmp_path / "flac", "web", codec="flac", names=["bass"])
    bundle = json.loads((tmp_path / "flac" / "bundle.json").read_text())
    assert list(bundle["outputs"]) == ["bass"]
    manifest = json.loads((rendered / "manifest.json").read_text())
    flac, _ = sf.read(tmp_path / "flac" / bundle["outputs"]["bass"]["file"], dtype="int32")
    wav, _ = sf.read(rendered / manifest["outputs"]["bass"]["file"], dtype="int32")
    np.testing.assert_array_equal(flac, wav)
    for params, message in (({"codec": "mp3"}, "codec must be one of"),
                            ({"codec": "aac"}, "explicit --bitrate"),
                            ({"codec": "wav", "bitrate": "192k"}, "omit --bitrate")):
        with pytest.raises(RunError) as failure:
            export(rendered, tmp_path / "bad", "web", **params)
        assert message in str(failure.value)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
@pytest.mark.parametrize("codec,suffix", [("aac", ".m4a"), ("opus", ".opus")])
def test_web_lossy_reports_decoded_length_and_records_ffmpeg(rendered, tmp_path, codec, suffix):
    record = export(rendered, tmp_path / codec, "web", codec=codec, bitrate="96k")
    bundle = json.loads((tmp_path / codec / "bundle.json").read_text())
    entry = bundle["outputs"]["mix"]
    assert entry["file"].endswith(suffix) and entry["bitrate"] == "96k"
    assert isinstance(entry["decoded"]["frames"], int) and entry["decoded"]["frames"] > 0
    assert isinstance(entry["decoded"]["offset_frames"], int)
    assert entry["decoded"]["decoder"].startswith("ffmpeg")
    assert [tool["name"] for tool in record["provenance"]["inputs"]["tools"]] == ["ffmpeg"]
    mismatch = record["result"]["decoded_mismatch"]
    assert isinstance(mismatch, list)
    assert not list((tmp_path / codec).rglob("*.wav"))


def test_srt_from_a_spans_lane(rendered, tmp_path):
    record = export(rendered, tmp_path / "subs", "srt", output="mix", lane="lyrics")
    assert record["result"] == {"lines": 2, "skipped": 1, "unsure": 1}
    text = (tmp_path / "subs" / "lyrics.srt").read_text()
    # 12345 frames at 8 kHz = 1543.125 ms -> 1543.
    assert text == (
        "1\n00:00:00,000 --> 00:00:01,543\nfirst line\n\n"
        "2\n00:00:02,500 --> 00:00:04,000\nsecond line\n"
    )
    for params, message in (({"output": "mix", "lane": "kick"}, "holds points, not spans"),
                            ({"output": "bass", "lane": "lyrics"}, "no lane 'lyrics'"),
                            ({"output": "drums", "lane": "lyrics"}, "no output 'drums'")):
        with pytest.raises(RunError) as failure:
            export(rendered, tmp_path / "bad", "srt", **params)
        assert message in str(failure.value)


def test_srt_rounds_half_milliseconds_later():
    from tactus._delivery import _milliseconds

    assert _milliseconds(1, 2000) == 1  # 0.5 ms
    assert _milliseconds(3, 2000) == 2  # 1.5 ms
    assert _milliseconds(1, 3000) == 0  # 0.333 ms
    assert _milliseconds(2, 3000) == 1  # 0.667 ms


def test_curves_join_levels_events_and_the_grid(rendered, tmp_path):
    export(rendered, tmp_path / "curves", "curves", fps=10.0, measures=["rms", "peak"],
           events=["kick"])
    curves = json.loads((tmp_path / "curves" / "curves.json").read_text())
    assert curves["frames"] == 80 and curves["frame_time"] == "start"
    assert set(curves["measures"]) == {"mix.rms_dbfs", "mix.peak_dbfs", "bass.rms_dbfs",
                                       "bass.peak_dbfs"}
    rms = curves["measures"]["mix.rms_dbfs"]
    assert rms["analysis"] == "level.rms_curve" and rms["window_s"] == 0.1
    assert rms["values"][20] == pytest.approx(20 * np.log10(0.25 / np.sqrt(2)), abs=0.05)
    assert curves["events"]["mix.kick"]["hits"][::10] == [1, 0, 1, 0, 1, 0, 1, 0]
    assert sum(curves["events"]["mix.kick"]["hits"]) == 4
    grid = curves["grid"]
    assert grid["output"] == "mix" and grid["bar"][:41:10] == [1, 1, 2, 2, 3]
    assert grid["bar_phase"][5] == 0.25 and grid["beat_phase"][5] == 0.0
    assert grid["beat_phase"][1] == pytest.approx(0.2)
    assert curves["spans"]["sections"]["index"][19:21] == [0, 1]
    assert curves["spans"]["sections"]["labels"] == ["intro", "verse"]
    assert curves["source"]["map_sha256"]


def test_curves_sample_frame_times_without_drift(tmp_path):
    """32 kHz at 30 fps: a frame is 1066.67 samples, so index arithmetic would drift."""
    rate, fps, frames = 32000, 30, 6000
    length = frames * rate // fps
    seconds = np.arange(length) // rate  # a louder level every whole second
    audio = (0.001 * (1 + seconds % 2 * 30) * np.sign(np.sin(np.arange(length)))).astype(
        np.float64)
    from tactus.export import curves

    out = tmp_path / "c"
    out.mkdir()
    curves({"mix": audio}, rate, out=out, fps=fps)
    values = json.loads((out / "curves.json").read_text())["measures"]["mix.rms_dbfs"]
    assert len(values["values"]) == frames
    direct = level.rms_curve(audio, rate, window_s=1 / fps, hop_s=values["hop_s"])
    window, hop = direct["window_samples"], direct["hop_samples"]
    # Only the first frame (t = 0, before the first window's centre) is half a window away.
    assert values["max_offset_s"] == pytest.approx(window / 2 / rate)
    for i in range(1, frames):
        t = i * rate / fps
        k = min(max(round((t - window / 2) / hop), 0), len(direct["rms_dbfs"]) - 1)
        assert abs(k * hop + window / 2 - t) <= hop / 2 + 1
    for i in (0, 1, 2999, 5998, 5999):
        k = min(max(round((i * rate / fps - window / 2) / hop), 0), len(direct["rms_dbfs"]) - 1)
        assert values["values"][i] == direct["rms_dbfs"][k]
    # Level steps at whole seconds land on frames 30 * s at the end as at the start.
    loud = np.array([v > -40 for v in values["values"]])
    changes = np.flatnonzero(np.diff(loud.astype(int))) + 1
    assert all(abs(c - 30 * round(c / 30)) <= 1 for c in changes)
    assert changes[-1] in (5970, 5971)


def test_export_web_from_a_run_without_checkpoint_and_cli(tmp_path, capsys):
    entry = tmp_path / "work" / "song.py"
    entry.parent.mkdir()
    entry.write_text(WORK)
    run(entry, out=tmp_path / "run", checkpoint=False)
    assert main(["export", "web", str(tmp_path / "run"), "--codec", "wav", "--out",
                 str(tmp_path / "web")]) == 0
    result = json.loads(capsys.readouterr().out)
    record = json.loads(Path(result["manifest"]).read_text())
    assert record["source"]["kind"] == "published-pcm" and record["source"]["map"]["sha256"]
    assert main(["export", "curves", str(tmp_path / "run"), "--fps", "25", "--events",
                 '["kick"]', "--out", str(tmp_path / "curves")]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert main(["export", "srt", str(tmp_path / "run"), "--output", "mix", "--lane", "lyrics",
                 "--out", str(tmp_path / "srt")]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert main(["export", "srt", str(tmp_path / "run"), "--output", "mix", "--lane", "lyrics",
                 "--time-map", "{}", "--out", str(tmp_path / "srt2")]) == 2


def test_web_and_curves_on_a_run_without_a_map(tmp_path):
    entry = tmp_path / "plain" / "song.py"
    entry.parent.mkdir()
    entry.write_text("import numpy as np\ndef render():\n"
                     "    return {'sample_rate': 8000, 'outputs': {'mix': np.full(16000, 0.1)}}\n")
    run(entry, out=tmp_path / "run")
    record = export(tmp_path / "run", tmp_path / "web", "web", codec="wav")
    bundle = json.loads((tmp_path / "web" / "bundle.json").read_text())
    assert bundle["map"] is None and bundle["map_seconds"] is None
    assert bundle["source"]["map_sha256"] is None and record["source"]["map"] is None
    export(tmp_path / "run", tmp_path / "curves", "curves", fps=10.0)
    curves = json.loads((tmp_path / "curves" / "curves.json").read_text())
    assert curves["frames"] == 20 and "grid" not in curves and "events" not in curves
    with pytest.raises(RunError) as failure:
        export(tmp_path / "run", tmp_path / "srt", "srt", output="mix", lane="lyrics")
    assert "has no map" in str(failure.value)


NOISE = """import numpy as np

def render():
    noise = np.random.default_rng(7).standard_normal(100_003) * 0.2
    return {"sample_rate": 48000, "outputs": {"mix": noise}}
"""


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_web_aac_reports_the_length_a_browser_plays(tmp_path):
    # ffmpeg's decoder emits the last AAC packet whole; the MP4 declares the real length
    # (Chrome's decodeAudioData returns exactly it).
    entry = tmp_path / "work" / "song.py"
    entry.parent.mkdir()
    entry.write_text(NOISE)
    run(entry, out=tmp_path / "run")
    record = export(tmp_path / "run", tmp_path / "aac", "web", codec="aac", bitrate="224k")
    decoded = json.loads((tmp_path / "aac" / "bundle.json").read_text())["outputs"]["mix"]["decoded"]
    assert decoded["frames"] == 100_003
    assert decoded["offset_frames"] == 0
    assert decoded["padding_frames"] > 0
    assert decoded["decoder"] == "ffmpeg, trimmed to the MP4's declared length"
    assert record["result"]["decoded_mismatch"] == []
