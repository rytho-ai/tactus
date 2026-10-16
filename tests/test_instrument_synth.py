"""Offline original-engine fixtures and public physical-synthesis behavior."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from tactus import synth
from tactus._instruments.bow import make_voice

FIXTURES = Path(__file__).parent / "fixtures/instruments"
CASES = json.loads((FIXTURES / "reference.json").read_text())["cases"]


def bow_arguments(recipe):
    events = []
    for event in recipe.get("events", []):
        item = {"kind": event["kind"], "time_s": event["time"]}
        if event["kind"] == "slur":
            item.update(
                freq_hz=event["hz"], hold_s=event["hold"], pitch_curve=event.get("cents", [])
            )
        events.append(item)
    return {
        "hold_s": recipe["hold"],
        "seed": recipe["seed"],
        "velocity": recipe["velocity"],
        "parameters": recipe.get("spec"),
        "body_size": recipe.get("body_size"),
        "controls": recipe.get("controls", ()),
        "pitch_curve": recipe.get("cents", ()),
        "vibrato_hz": recipe.get("vibrato_hz", 0),
        "vibrato_cents": recipe.get("vibrato_cents", 0),
        "events": events,
    }


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_against_original_dawg_fixtures(case):
    recipe = case["recipe"]
    rate = case["rate"]
    before = copy.deepcopy(recipe)
    if case["kind"] == "piano":
        n = recipe["notes"][0]
        # For this one onset-zero note, the explicit prefix reproduces the oracle's
        # v:n0:0 strike seed. The public API does not introduce an upstream tick grid.
        audio = synth.piano(
            [(n["start"], n["pitch"], n["duration"], n["velocity"])],
            rate,
            frames=case["frames"],
            seed="v:n0",
            family=recipe.get("family", "grand"),
            pedal=[(e["time"], e["state"]) for e in recipe.get("pedal", [])],
            soft_pedal=[(e["time"], e["state"]) for e in recipe.get("softPedal", [])],
        )
        tolerance = 1e-10
    else:
        audio = synth.bowed_string(
            recipe["hz"], rate, frames=case["frames"], **bow_arguments(recipe)
        )[:, None]
        tolerance = 1e-9
    actual = np.stack([audio[i : i + case["window_frames"]] for i in case["starts"]])
    with np.load(FIXTURES / "reference.npz", allow_pickle=False) as oracle:
        np.testing.assert_allclose(actual, oracle[case["name"]], rtol=0, atol=tolerance)
    assert abs(np.max(abs(audio)) - case["peak"]) < tolerance
    assert abs(np.sqrt(np.mean(audio**2)) - case["rms"]) < tolerance
    assert recipe == before


def test_piano_pedals_dynamics_and_silence():
    def play(velocity=0.7, pedal=()):
        return synth.piano(
            [(0, 60, 0.5, velocity)],
            44100,
            frames=110250,
            seed="behavior",
            parameters={"knock": 0, "noise": 0},
            pedal=pedal,
        )

    dry = play()
    half = play(pedal=[(0, "half")])
    held = play(pedal=[(0, "down"), (2, "up")])
    rms = [np.sqrt(np.mean(a[44100:66150] ** 2)) for a in (dry, half, held)]
    assert rms[0] < rms[1] < rms[2]
    assert np.sqrt(np.mean(play(0.9) ** 2)) > np.sqrt(np.mean(play(0.2) ** 2))
    assert not np.any(play(0))
    np.testing.assert_array_equal(dry, play())


def test_piano_placement_polyphony_fractional_pitch_and_inputs_unchanged():
    notes = [(0, 60.5, 0.2, 0.7), (0.5, 67, 0.2, 0.5)]
    before = copy.deepcopy(notes)
    audio = synth.piano(notes, 24000, frames=24000, seed="part")
    assert audio.shape == (24000, 2) and audio.dtype == np.float64 and np.isfinite(audio).all()
    assert notes == before
    delayed = synth.piano([(0.5, 60, 0.2, 0.7)], 24000, frames=24000, seed="part")
    assert not np.any(delayed[:12000]) and np.any(delayed[12000:])
    # No arbitrary prototype voice-count ceiling or automatic voice stealing.
    many = synth.piano([(0, 60, 0.1, 0.3)] * 65, 8000, frames=32, seed="many")
    assert np.isfinite(many).all() and many.shape == (32, 2)


def test_bow_stream_state_and_readable_reference():
    recipe = {
        "hz": 3000.0,
        "velocity": 0.7,
        "hold": 1.0,
        "seconds": 2.0,
        "seed": 17,
        "spec": {"tremhz": 7.0},
        "vibrato_hz": 5.0,
        "vibrato_cents": 10.0,
    }
    a, b = make_voice(recipe, 44100), make_voice(recipe, 44100)
    whole = a.process(4096)
    split = np.concatenate([b.process(n) for n in (1, 7, 32, 64, 129, 3863)])
    np.testing.assert_array_equal(whole, split)
    for name in ("nb", "bb", "history"):
        np.testing.assert_array_equal(getattr(a, name), getattr(b, name))
    readable = make_voice(recipe, 44100, compiled=False).process(4096)
    np.testing.assert_allclose(whole, readable, rtol=0, atol=1e-10)


def test_bow_silence_slur_and_tail_controls():
    assert not np.any(synth.bowed_string(440, 44100, frames=4410, hold_s=0.1, seed=1, velocity=0))
    audio = synth.bowed_string(
        440,
        44100,
        frames=110250,
        hold_s=1.0,
        seed=1,
        events=[{"kind": "slur", "time_s": 0.5, "freq_hz": 660, "hold_s": 0.7}],
    )
    assert np.isfinite(audio).all() and np.max(abs(audio[-22050:])) < 1e-4
    with pytest.raises(ValueError, match="boundary"):
        synth.bowed_string(
            440,
            44100,
            frames=44100,
            hold_s=1.0,
            seed=1,
            events=[{"kind": "slur", "time_s": 0.5, "freq_hz": 3000, "hold_s": 1}],
        )


@pytest.mark.parametrize("frames", [0, 1, 17])
def test_short_outputs(frames):
    assert synth.piano([], np.int64(44100), frames=frames, seed="empty").shape == (frames, 2)
    assert synth.bowed_string(440, 44100, frames=frames, hold_s=2, seed=np.uint32(1)).shape == (
        frames,
    )


@pytest.mark.parametrize(
    "argument,value",
    [("frames", True), ("frames", -1), ("sample_rate", True), ("sample_rate", 7999)],
)
def test_invalid_common_inputs(argument, value):
    p = {"sample_rate": 44100, "frames": 100, "seed": "test"}
    p[argument] = value
    b = {"sample_rate": 44100, "frames": 100, "hold_s": 0.1, "seed": 1}
    b[argument] = value
    with pytest.raises((ValueError, TypeError)):
        synth.piano([], **p)
    with pytest.raises((ValueError, TypeError)):
        synth.bowed_string(440, **b)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"seed": True},
        {"seed": -1},
        {"hold_s": -1},
        {"parameters": {"pressure": 2}},
        {"parameters": {"nonsense": 1}},
        {"body_size": 0},
        {"body_size": float("nan")},
        {"controls": [[0, "x", 0, 0, 1]]},
        {"pitch_curve": [[1, 0], [0, 2]]},
        {"pitch_curve": [[0, 101]]},
        {"events": [{"kind": "slur", "time_s": 0.1}]},
        {"velocity": float("nan")},
    ],
)
def test_invalid_bow_inputs(kwargs):
    options = {"frames": 4410, "hold_s": 0.1, "seed": 1, **kwargs}
    with pytest.raises((ValueError, TypeError)):
        synth.bowed_string(440, 44100, **options)


@pytest.mark.parametrize(
    "notes,kwargs",
    [
        ([(0, float("inf"), 1, 0.7)], {}),
        ([(0, 60, 0, 0.7)], {}),
        ([(0, 60, 1, 1.1)], {}),
        ([], {"parameters": {"prep": 1}}),
        ([], {"parameters": {"noise": True}}),
        ([], {"seed": 1}),
        ([], {"family": "upright"}),
        ([], {"pedal": [(1, "down"), (0, "up")]}),
        ([], {"tail_s": 0}),
    ],
)
def test_invalid_piano_inputs(notes, kwargs):
    with pytest.raises((ValueError, TypeError)):
        synth.piano(notes, 44100, frames=4410, **{"seed": "test", **kwargs})
