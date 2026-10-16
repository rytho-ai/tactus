"""Offline original-engine fixtures and public physical-synthesis behavior."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from tactus import synth

FIXTURES = Path(__file__).parent / "fixtures/instruments"
CASES = json.loads((FIXTURES / "reference.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_against_original_dawg_fixtures(case):
    recipe = case["recipe"]
    rate = case["rate"]
    before = copy.deepcopy(recipe)
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


@pytest.mark.parametrize("frames", [0, 1, 17])
def test_short_outputs(frames):
    assert synth.piano([], np.int64(44100), frames=frames, seed="empty").shape == (frames, 2)


@pytest.mark.parametrize(
    "argument,value",
    [("frames", True), ("frames", -1), ("sample_rate", True), ("sample_rate", 7999)],
)
def test_invalid_common_inputs(argument, value):
    p = {"sample_rate": 44100, "frames": 100, "seed": "test"}
    p[argument] = value
    with pytest.raises((ValueError, TypeError)):
        synth.piano([], **p)


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
