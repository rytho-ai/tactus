"""Spectral note labels are candidates, including louder harmonics, not chosen roots."""

import numpy as np
import pytest

from tactus.analysis import schema, spectral


def tone(midi, seconds=1.0, rate=22050):
    t = np.arange(round(seconds * rate)) / rate
    return 0.2 * np.sin(2 * np.pi * 440 * 2 ** ((midi - 69) / 12) * t)


@pytest.mark.parametrize("midi, note, cents", [(55.22, "G3", 22), (60., "C4", 0), (69.31, "A4", 31)])
def test_labels_frequency_in_note_octave_and_fractional_midi(midi, note, cents):
    result = spectral.note_candidates(tone(midi), 22050, n=1)
    [candidate] = result["candidates"]
    assert candidate["note"] == note
    assert candidate["midi"] == pytest.approx(midi, abs=.015)
    assert candidate["offset_cents"] == pytest.approx(cents, abs=1.5)
    schema.validate(result)


def test_louder_harmonic_is_not_mislabeled_as_an_automatic_root():
    x = tone(55.22) * .3 + tone(67.22)
    result = spectral.note_candidates(x, 22050, n=2)
    assert [c["note"] for c in result["candidates"]] == ["G4", "G3"]
    assert "root" not in result
    assert result["candidates"][1]["midi"] == pytest.approx(55.22, abs=.015)


def test_selected_region_excludes_attack_and_keeps_input_unchanged():
    x = np.concatenate([tone(43, .5), tone(55.22, .5)])
    before = x.copy()
    result = spectral.note_candidates(x, 22050, start_s=.5, end_s=1, n=1)
    assert result["start_s"] == .5 and result["end_s"] == 1
    assert result["candidates"][0]["note"] == "G3"
    np.testing.assert_array_equal(x, before)
    assert result["schema"]["input"]["frames"] == len(x)


def test_silence_and_cancelled_stereo_have_no_candidates():
    x = tone(55)
    for audio in (np.zeros(1000), np.column_stack([x, -x])):
        assert spectral.note_candidates(audio, 22050)["candidates"] == []


@pytest.mark.parametrize("kwargs", [
    {"start_s": -1}, {"end_s": 2}, {"start_s": .5, "end_s": .5},
    {"end_s": 1e-5}, {"n": 0}, {"n": True}, {"min_hz": 0},
    {"min_hz": 12000}, {"resolution_hz": 0}, {"start_s": float("nan")},
])
def test_invalid_region_and_settings_are_rejected(kwargs):
    with pytest.raises(ValueError):
        spectral.note_candidates(tone(55), 22050, **kwargs)


def test_nonfinite_input_is_rejected():
    with pytest.raises(ValueError):
        spectral.note_candidates(np.array([np.nan] * 100), 22050)
