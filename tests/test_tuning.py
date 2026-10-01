"""spectral.tuning: known offsets, degenerate inputs, CLI and an optional librosa comparison."""

from __future__ import annotations

import json

import numpy as np
import pytest
import soundfile as sf

from tactus.analysis import spectral
from tactus.cli import main

SR = 48000


def chords(offset_cents, *, sample_rate=SR, harmonics=6, seconds=4.0, seed=0):
    """Four chords of harmonic tones, every fundamental `offset_cents` from A440 tuning."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    out = np.zeros_like(t)
    progression = [(48, 60, 64, 67), (53, 60, 65, 69), (55, 59, 62, 67), (45, 57, 60, 64)]
    for bar, notes in enumerate(progression):
        seg = (t >= bar * seconds / 4) & (t < (bar + 1) * seconds / 4)
        for note in notes:
            f0 = 440.0 * 2 ** ((note - 69 + offset_cents / 100) / 12)
            for h in range(1, harmonics + 1):
                out[seg] += np.sin(2 * np.pi * f0 * h * t[seg] + rng.uniform(0, 6.28)) / h
    return 0.5 * out / np.abs(out).max()


def wrapped(error):
    return (error + 50) % 100 - 50


@pytest.mark.parametrize("true", [-45, -30, -12, 0, 7, 20, 37, 48])
@pytest.mark.parametrize("rate", [44100, 48000])
def test_tuning_recovers_a_known_offset_within_four_cents(true, rate):
    result = spectral.tuning(chords(true, sample_rate=rate), rate)
    assert abs(wrapped(result["offset_cents"] - true)) <= 4.0
    assert result["offset_semitones"] == pytest.approx(result["offset_cents"] / 100)
    assert result["concentration"] > 0.6 and result["peaks"] > 100


def test_tuning_of_pure_tones_is_exact_and_feeds_chroma():
    result = spectral.tuning(chords(37, harmonics=1), SR)
    assert abs(result["offset_cents"] - 37) <= 0.5 and result["concentration"] > 0.95
    audio = chords(37)
    measured = spectral.tuning(audio, SR)["offset_semitones"]
    sharp = spectral.chroma(audio[: SR // 2], SR, tuning=measured)["chroma"][:, 4:-4].mean(axis=1)
    naive = spectral.chroma(audio[: SR // 2], SR)["chroma"][:, 4:-4].mean(axis=1)
    c_major = [0, 4, 7]
    assert sharp[c_major].sum() / sharp.sum() > naive[c_major].sum() / naive.sum()


def test_tuning_silence_noise_stereo_and_gain():
    empty = spectral.tuning(np.zeros(SR), SR)
    assert empty == {"offset_cents": None, "offset_semitones": None, "concentration": 0.0, "peaks": 0}
    noise = spectral.tuning(0.3 * np.random.default_rng(1).standard_normal(SR * 3), SR)
    assert noise["concentration"] < 0.05
    mono = chords(20)
    before = mono.copy()
    base = spectral.tuning(mono, SR)
    np.testing.assert_array_equal(mono, before)
    stereo = spectral.tuning(np.column_stack([mono, mono]), SR)
    quiet = spectral.tuning(mono * 0.01, SR)
    assert stereo["offset_cents"] == pytest.approx(base["offset_cents"], abs=1e-6)
    assert quiet["offset_cents"] == pytest.approx(base["offset_cents"], abs=1e-6)


def test_tuning_rejects_invalid_requests():
    audio = chords(0, seconds=1.0)
    with pytest.raises(ValueError, match="threshold_db"):
        spectral.tuning(audio, SR, threshold_db=3.0)
    with pytest.raises(ValueError, match="fmin < fmax"):
        spectral.tuning(audio, SR, fmin=5000.0)
    with pytest.raises(ValueError):
        spectral.tuning(np.array([]), SR)
    with pytest.raises(ValueError):
        spectral.tuning(np.full(SR, np.nan), SR)


def test_tuning_cli_reports_the_offset(tmp_path, capsys):
    wav = tmp_path / "sharp.wav"
    sf.write(wav, chords(37), SR, subtype="PCM_24")
    assert main(["analyze", "spectral", "tuning", str(wav), "--brief"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["analysis"] == "spectral.tuning"
    assert abs(report["result"]["offset_cents"] - 37) <= 4.0


@pytest.mark.reference
@pytest.mark.parametrize("true", [-30, 0, 20, 37])
def test_tuning_agrees_with_librosa_estimate(true, librosa):
    audio = chords(true, sample_rate=22050)
    ours = spectral.tuning(audio, 22050)["offset_cents"]
    theirs = 100.0 * librosa.estimate_tuning(y=audio, sr=22050)
    assert abs(wrapped(ours - theirs)) <= 6.0


@pytest.mark.parametrize("shift", [-30, -10, 10, 25, 40])
def test_tuning_follows_a_known_repitch_within_a_cent(shift):
    rng = np.random.default_rng(3)
    audio = chords(12, seconds=6.0) + 0.02 * rng.standard_normal(SR * 6)
    rate = 2 ** (shift / 1200)
    repitched = np.interp(np.arange(0, len(audio) - 1, rate), np.arange(len(audio)), audio)
    change = spectral.tuning(repitched, SR)["offset_cents"] - spectral.tuning(audio, SR)["offset_cents"]
    assert abs(wrapped(change - shift)) <= 1.0
