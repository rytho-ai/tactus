"""A render's time map: structural validation, binding in the run and verified reading."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tactus import RunError, excerpt, inputs, load_render, render_store, run, timemap
from tactus.inputs import tree
from tactus.takes import save_take
from tactus.timing import Clock

OUTPUTS = {"tape": 1000, "loop": 400}


def good_map() -> dict:
    return {
        "outputs": {
            "tape": {
                "grid": {"bars": [0, 250, 500, 750], "end": 1000, "beats_per_bar": [4, 4, 3, 4]},
                "lanes": {
                    "sections": {
                        "kind": "spans",
                        "items": [{"start": 0, "end": 500, "label": "a"}, {"start": 500, "end": 1000}],
                    },
                    "kick": {"kind": "points", "items": [{"at": 0}, {"at": 250, "velocity": 0.8}]},
                },
            },
            "loop": {"grid": {"bars": [0, 200], "end": 400}},
        },
        "segments": {
            "loop": {
                "output": "loop",
                "start": 0,
                "end": 400,
                "loop": True,
                "tags": ["block"],
                "joins": [{"at": "bars", "to": {"tags": ["block"]}, "keep_phase": True}],
            },
            "intro": {"output": "tape", "start": 0, "end": 500, "tail_end": 600,
                      "joins": [{"at": [250], "to": ["loop"], "label": "scratch"}]},
        },
        "clock_hint": {"tempo": [[1, 110], [4, 140]], "meter": 4},
    }


def test_valid_map_is_kept_with_defaults_filled():
    checked = timemap.validate(good_map(), OUTPUTS)
    assert checked["outputs"]["tape"]["grid"]["first_bar"] == 1
    assert checked["outputs"]["tape"]["lanes"]["kick"]["items"][1] == {"at": 250, "velocity": 0.8}
    loop = checked["segments"]["loop"]
    assert loop["tail_end"] == 400 and loop["joins"][0]["keep_phase"] is True
    intro = checked["segments"]["intro"]
    assert intro["loop"] is False and intro["tags"] == []
    assert intro["joins"][0] == {"at": [250], "to": ["loop"], "keep_phase": False, "label": "scratch"}
    # A join's successors are optional: only the exit points are required.
    plain = {"segments": {"x": {"output": "loop", "start": 0, "end": 400, "joins": [{"at": [0]}]}}}
    assert timemap.validate(plain, OUTPUTS)["segments"]["x"]["joins"][0]["to"] is None
    assert checked["clock_hint"] == good_map()["clock_hint"]
    assert timemap.validate({}, OUTPUTS) == {}


def test_numpy_scalars_and_arrays_lengths_are_accepted():
    value = {"outputs": {"loop": {"grid": {"bars": [np.int64(0), np.int64(200)]}}}}
    checked = timemap.validate(value, {"loop": np.zeros((400, 2))})
    assert checked["outputs"]["loop"]["grid"]["bars"] == [0, 200]
    assert type(checked["outputs"]["loop"]["grid"]["bars"][1]) is int


def edit(change):
    value = good_map()
    change(value)
    return value


def setter(path, item):
    def change(value):
        *parents, last = path
        for key in parents:
            value = value[key]
        value[last] = item

    return change


@pytest.mark.parametrize(
    "change,message",
    [
        (setter(["outputs", "drums"], {}), "map.outputs.drums: names no returned output"),
        (setter(["outputs", "tape", "grid", "bars", 3], 1001),
         "map.outputs.tape.grid.bars[3]: frame 1001 lies outside [0, 1000]"),
        (setter(["outputs", "tape", "grid", "bars", 1], 250.0),
         "map.outputs.tape.grid.bars[1]: must be an integer frame"),
        (setter(["outputs", "tape", "grid", "bars", 1], True),
         "map.outputs.tape.grid.bars[1]: must be an integer frame"),
        (setter(["outputs", "tape", "grid", "bars", 3], 400),
         "map.outputs.tape.grid.bars[3]: frames must not decrease (400 after 500)"),
        (setter(["outputs", "tape", "grid", "beats_per_bar"], [4, 4]),
         "map.outputs.tape.grid.beats_per_bar: has 2 entries for 4 bars"),
        (setter(["outputs", "tape", "grid", "beats_per_bar"], 0),
         "map.outputs.tape.grid.beats_per_bar: must be a positive number"),
        (setter(["outputs", "tape", "grid", "end"], 700),
         "map.outputs.tape.grid.end: frame 700 lies outside [750]"),
        (setter(["outputs", "tape", "grid", "tempo"], 120),
         "map.outputs.tape.grid: unexpected fields: 'tempo'"),
        (setter(["outputs", "tape", "lanes", "kick", "items", 1, "at"], -1),
         "map.outputs.tape.lanes.kick.items[1].at: frame -1 lies outside [0, 1000]"),
        (setter(["outputs", "tape", "lanes", "sections", "items"],
                [{"start": 500, "end": 1000}, {"start": 0, "end": 500}]),
         "map.outputs.tape.lanes.sections.items[1]: items must be sorted"),
        (setter(["outputs", "tape", "lanes", "sections", "items", 0, "end"], 1200),
         "map.outputs.tape.lanes.sections.items[0].end: frame 1200 lies outside [0, 1000]"),
        (setter(["outputs", "tape", "lanes", "kick", "kind"], "hits"),
         "map.outputs.tape.lanes.kick.kind: must be 'spans' or 'points'"),
        (setter(["segments", "intro", "tail_end"], 450),
         "map.segments.intro.tail_end: frame 450 lies outside [500, 1000]"),
        (setter(["segments", "intro", "end"], 1100),
         "map.segments.intro.end: frame 1100 lies outside [0, 1000]"),
        (setter(["segments", "intro", "output"], "mix"),
         "map.segments.intro.output: names no returned output"),
        (setter(["segments", "intro", "joins", 0, "to"], ["outro"]),
         "map.segments.intro.joins[0].to[0]: names no segment: 'outro'"),
        (setter(["segments", "loop", "joins", 0, "to"], {"tags": ["trap"]}),
         "map.segments.loop.joins[0].to.tags[0]: no segment carries tag 'trap'"),
        (setter(["segments", "intro", "joins", 0, "at"], [600]),
         "map.segments.intro.joins[0].at[0]: frame 600 lies outside [0, 500]"),
        (setter(["segments", "intro", "joins", 0, "at"], "bars"),
         "map.segments.intro.joins[0].at: 'bars' needs a grid"),
        (setter(["segments", "intro", "joins", 0, "when"], "hour 3"),
         "map.segments.intro.joins[0]: unexpected fields: 'when'"),
        (setter(["markers"], []), "map: unexpected fields: 'markers'"),
        (setter(["clock_hint"], (1, 2)), "map.clock_hint: must be JSON"),
        (setter(["clock_hint"], float("nan")), "map.clock_hint: numbers must be finite"),
    ],
)
def test_invalid_maps_name_the_field(change, message):
    if "'bars' needs a grid" in message:
        value = edit(change)
        value["outputs"]["tape"].pop("grid")
    else:
        value = edit(change)
    with pytest.raises(ValueError) as failure:
        timemap.validate(value, OUTPUTS)
    assert message in str(failure.value)


def test_to_seconds_converts_positions_only():
    seconds = timemap.to_seconds(timemap.validate(good_map(), OUTPUTS), 100)
    tape = seconds["outputs"]["tape"]
    assert tape["grid"]["bars"] == [0.0, 2.5, 5.0, 7.5] and tape["grid"]["end"] == 10.0
    assert tape["grid"]["first_bar"] == 1 and tape["grid"]["beats_per_bar"] == [4, 4, 3, 4]
    assert tape["lanes"]["kick"]["items"][1] == {"at": 2.5, "velocity": 0.8}
    assert seconds["segments"]["intro"]["tail_end"] == 6.0
    assert seconds["segments"]["intro"]["joins"][0]["at"] == [2.5]
    assert seconds["segments"]["loop"]["joins"][0]["at"] == "bars"


def test_from_seconds_inverts_to_seconds():
    checked = timemap.validate(good_map(), OUTPUTS)
    for rate in (100, 44100, 48000):
        assert timemap.from_seconds(timemap.to_seconds(checked, rate), rate) == checked


def test_from_seconds_rounds_like_frame_of_and_copies_other_fields():
    items = [
        {"start": 0.005, "end": 0.015, "text": "one", "status": "draft"},
        {"start": 0.0149, "end": 0.02},
    ]
    seconds = {"outputs": {"tape": {"lanes": {"words": {"kind": "spans", "items": items}}}},
               "clock_hint": {"tempo": 0.5}}
    frames = timemap.from_seconds(seconds, 100)
    got = frames["outputs"]["tape"]["lanes"]["words"]["items"]
    assert got[0] == {"start": 1, "end": 2, "text": "one", "status": "draft"}  # half a sample -> later
    assert got[1] == {"start": 1, "end": 2}
    assert frames["clock_hint"] == {"tempo": 0.5} and items[0]["start"] == 0.005
    timemap.validate(frames, OUTPUTS)


def test_from_seconds_does_not_sort_or_clamp():
    items = [{"at": 0.5}, {"at": 0.25}]
    frames = timemap.from_seconds(
        {"outputs": {"tape": {"lanes": {"cues": {"kind": "points", "items": items}}}}}, 100)
    assert [i["at"] for i in frames["outputs"]["tape"]["lanes"]["cues"]["items"]] == [50, 25]
    with pytest.raises(ValueError, match="map.outputs.tape.lanes.cues"):
        timemap.validate(frames, OUTPUTS)


@pytest.mark.parametrize(
    "tempo,meter,start",
    [
        (110, 4, 0.0),
        ([(1, 92), (3, 100, "ramp"), (5, 120)], 4, 0.0),
        ([(1, 80), (4, 60, "smooth")], [(1, 4), (3, 3.5), (4, 3)], 1.3),
    ],
)
def test_clock_grid_is_clock_frames(tempo, meter, start):
    clock = Clock(sample_rate=32000, tempo=tempo, meter=meter, start_seconds=start)
    grid = clock.grid(2, 6)
    assert grid["first_bar"] == 2
    assert grid["bars"] == [clock.frame(b) for b in range(2, 7)]
    assert grid["end"] == clock.frame(7)
    meters = [clock.beats_per_bar(b) for b in range(2, 7)]
    assert grid["beats_per_bar"] == (meters[0] if len(set(meters)) == 1 else meters)
    shifted = clock.grid(2, 6, offset=57600)
    assert shifted["bars"] == [f + 57600 for f in grid["bars"]]
    assert timemap.validate({"outputs": {"x": {"grid": grid}}}, {"x": grid["bars"][-1] + 1})


def test_clock_grid_uses_frame_of_rounding():
    # 8 bars at 110 BPM, 48 kHz: 837818.18... frames, rounded once by frame_of.
    assert Clock(sample_rate=48000, tempo=110).grid(1, 8)["end"] == 837818
    assert Clock(sample_rate=48000, tempo=110).grid(1, 1)["beats_per_bar"] == 4
    with pytest.raises(ValueError):
        Clock(sample_rate=48000, tempo=110).grid(3, 2)


MAPPED = """import numpy as np
from tactus.timing import Clock

def render(*, takes=False):
    clock = Clock(sample_rate=8000, tempo=120)
    mix = np.zeros((clock.frame(3), 2), dtype=np.float32)
    result = {"sample_rate": 8000, "outputs": {"mix": mix},
              "map": {"outputs": {"mix": {"grid": clock.grid(1, 2),
                      "lanes": {"kick": {"kind": "points", "items": [{"at": 0}, {"at": 8000}]}}}},
                      "clock_hint": {"tempo": 120}}}
    if takes:
        result["takes"] = {"raw": mix}
    return result
"""


def write(tmp_path: Path, text: str) -> Path:
    entry = tmp_path / "work" / "song.py"
    entry.parent.mkdir(exist_ok=True)
    entry.write_text(text)
    return entry


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def test_run_publishes_and_binds_the_map(tmp_path):
    result = run(write(tmp_path, MAPPED), out=tmp_path / "run")
    out = tmp_path / "run"
    assert result["map"] == str(out / "map.json")
    saved = load(out / "map.json")
    assert saved["outputs"]["mix"]["grid"] == {
        "first_bar": 1, "bars": [0, 16000], "end": 32000, "beats_per_bar": 4
    }
    entry = {"file": "map.json", "sha256": inputs.pool.hash_file(out / "map.json")}
    manifest, receipt, checkpoint = (load(out / f) for f in ("manifest.json", "receipt.json",
                                                             "render.json"))
    assert manifest["format_version"] == 4 and manifest["map"] == entry
    assert receipt["map"] == entry and checkpoint["map"] == entry
    published = render_store.read_published(out)
    assert published.time_map == saved
    rendered = render_store.read(out)
    assert render_store.read_map(out, rendered.origin) == saved


def test_run_without_map_is_written_as_before(tmp_path):
    entry = write(tmp_path, "import numpy as np\ndef render():\n"
                  "    return {'sample_rate': 8000, 'outputs': {'mix': np.zeros(8)}}\n")
    result = run(entry, out=tmp_path / "run")
    assert "map" not in result and not (tmp_path / "run" / "map.json").exists()
    manifest = load(tmp_path / "run" / "manifest.json")
    assert manifest["format_version"] == 2 and "map" not in manifest
    assert "map" not in load(tmp_path / "run" / "receipt.json")
    assert "map" not in load(tmp_path / "run" / "render.json")
    assert render_store.read_published(tmp_path / "run").time_map is None


def test_invalid_map_fails_validation_and_removes_the_run(tmp_path):
    entry = write(tmp_path, MAPPED.replace("[{\"at\": 0}, {\"at\": 8000}]",
                                           "[{\"at\": 0}, {\"at\": 99999}]"))
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "run")
    assert (failure.value.code, failure.value.phase) == ("invalid_output", "validate")
    assert "map.outputs.mix.lanes.kick.items[1].at" in str(failure.value)
    assert not (tmp_path / "run").exists()


def test_unexpected_result_field_lists_map_as_optional(tmp_path):
    entry = write(tmp_path, "import numpy as np\ndef render():\n    return {'sample_rate': 8000, "
                  "'outputs': {'mix': np.zeros(8)}, 'notes': 1}\n")
    with pytest.raises(RunError) as failure:
        run(entry, out=tmp_path / "run")
    assert 'optional: "takes", "map"' in str(failure.value)


def test_map_without_checkpoint_binds_through_the_manifest(tmp_path):
    run(write(tmp_path, MAPPED), out=tmp_path / "run", checkpoint=False)
    out = tmp_path / "run"
    assert not (out / "render.json").exists()
    rendered = render_store.read(out)
    assert rendered.origin["kind"] == "published-pcm"
    assert render_store.read_map(out, rendered.origin)["clock_hint"] == {"tempo": 120}


@pytest.mark.parametrize("checkpoint", [True, False])
def test_tampered_map_fails_verification(tmp_path, checkpoint):
    run(write(tmp_path, MAPPED), out=tmp_path / "run", checkpoint=checkpoint)
    out = tmp_path / "run"
    (out / "map.json").write_text('{"outputs": {}}\n')
    with pytest.raises(RunError) as failure:
        render_store.read_map(out, render_store.read(out).origin)
    assert failure.value.code == "source_corrupt" and "map.json hash mismatch" in str(failure.value)
    with pytest.raises(RunError):
        render_store.read_published(out)


def test_prune_keeps_the_map(tmp_path):
    run(write(tmp_path, MAPPED), out=tmp_path / "run")
    out = tmp_path / "run"
    render_store.prune(out)
    assert (out / "map.json").is_file() and not (out / "render.json").exists()
    assert render_store.read_published(out).time_map["outputs"]["mix"]["grid"]["end"] == 32000


def test_takes_save_and_load_render_with_a_map(tmp_path, monkeypatch):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    inputs._reset_record()
    run(write(tmp_path, MAPPED), out=tmp_path / "run", params={"takes": True})
    out = tmp_path / "run"
    assert load(out / "manifest.json")["format_version"] == 4
    assert save_take(out, "raw")["ref"].startswith("tree:sha256:")
    ref = tree.add(out)
    loaded = load_render(ref)
    assert loaded.map == load(out / "map.json")
    without = tmp_path / "plain"
    run(write(tmp_path, "import numpy as np\ndef render():\n"
              "    return {'sample_rate': 8000, 'outputs': {'mix': np.zeros(8)}}\n"), out=without)
    assert load_render(tree.add(without)).map is None


def test_excerpt_reads_a_mapped_run(tmp_path):
    run(write(tmp_path, MAPPED), out=tmp_path / "run")
    result = excerpt(tmp_path / "run", out=tmp_path / "part", range=(0.0, 1.0))
    assert load(Path(result["manifest"]))["outputs"]["mix"]["frames"] == 8000
