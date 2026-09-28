"""Brahms beat-alignment comparison as ordinary Tactus production functions.

Reads: pinned source audio and provisional beat analysis, pytimestretch, NumPy.
Owns: phrase choice, target grid, identical percussion, explicit gains and short edge fades.
No estimator runs during render. The selected beat indices are not downbeat labels.
"""

from __future__ import annotations

import json

import numpy as np
import pytimestretch as pts
import soundfile as sf

from tactus import material
from tactus.timing import add_at, frame_of

SOURCE = "sha256:c61c2ae027c7dfa5d2f0a507fb5c02d39125b1077ab27653a71fbba1d0cbb8ab"
BEAT_REPORT = "sha256:9f557ace48f448e5ed1428d8a29d70265e3b83c10667669cda3d6a6176648d00"
FIRST_BEAT = 11
LAST_BEAT = 83
BACKEND = "rubberband"
SEED = 928


def load_phrase():
    audio, rate = sf.read(material(SOURCE), dtype="float32", always_2d=True)
    report = json.loads(material(BEAT_REPORT).read_text())
    assert report["sample_rate"] == rate
    times = report["result"]["beats_s"][FIRST_BEAT : LAST_BEAT + 1]
    frames = np.array([frame_of(t, rate) for t in times], dtype=np.int64)
    phrase = audio[frames[0] : frames[-1]].copy()
    return phrase, rate, frames - frames[0]


def align_phrase(phrase, rate, source_frames, *, mode, target_bpm):
    if target_bpm <= 0:
        raise ValueError("target_bpm must be positive")
    target_frames = np.array(
        [frame_of(i * 60 / target_bpm, rate) for i in range(len(source_frames))],
        dtype=np.int64,
    )
    if mode == "source":
        return phrase.copy(), source_frames.copy()
    if mode == "fixed":
        output = pts.time_stretch(
            phrase,
            rate,
            duration_ratio=int(target_frames[-1]) / len(phrase),
            backend=BACKEND,
            quality="high",
        )
    elif mode == "warp":
        output = pts.time_warp(
            phrase,
            rate,
            markers=np.column_stack([source_frames, target_frames]),
            backend=BACKEND,
            quality="high",
        )
    else:
        raise ValueError("mode must be source, fixed or warp")
    assert len(output) == target_frames[-1]
    return output, target_frames


def edge_fade(audio, rate):
    result = audio.copy()
    n = min(frame_of(0.015, rate), len(result) // 2)
    envelope = np.linspace(0, 1, n, dtype=np.float32)
    result[:n] *= envelope[:, None]
    result[-n:] *= envelope[::-1, None]
    return result


def make_clicks(length, rate, beats):
    result = np.zeros((length, 2), dtype=np.float32)
    t = np.arange(frame_of(0.025, rate)) / rate
    hit = (0.2 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 160)).astype(np.float32)
    for frame in beats[:-1]:
        add_at(result, np.column_stack([hit, hit]), int(frame))
    return result


def percussion(length, rate, target_bpm):
    """An authored half-time groove; its grouping does not assert source bar positions."""
    rng = np.random.default_rng(SEED)
    result = np.zeros((length, 2), dtype=np.float32)
    t = np.arange(frame_of(0.28, rate)) / rate
    kick = np.sin(2 * np.pi * (48 * t + 65 * 0.018 * (1 - np.exp(-t / 0.018))))
    kick *= np.exp(-t * 18)
    t = np.arange(frame_of(0.15, rate)) / rate
    noise = rng.standard_normal(len(t))
    snare = (0.5 * noise + 0.3 * np.sin(2 * np.pi * 180 * t)) * np.exp(-t * 32)
    t = np.arange(frame_of(0.04, rate)) / rate
    noise = rng.standard_normal(len(t))
    hat = np.diff(noise, prepend=0) * np.exp(-t * 95) * 0.12
    for beat in range(LAST_BEAT - FIRST_BEAT):
        frame = frame_of(beat * 60 / target_bpm, rate)
        if beat % 4 == 0 or beat % 8 == 7:
            add_at(result, np.column_stack([kick, kick]), frame)
        if beat % 4 == 2:
            add_at(result, np.column_stack([snare, snare]), frame, gain=0.6)
        add_at(result, np.column_stack([hat * 0.8, hat]), frame, gain=0.8)
        offbeat = frame_of((beat + 0.5) * 60 / target_bpm, rate)
        add_at(result, np.column_stack([hat, hat * 0.8]), offbeat, gain=0.55)
    return result


def render(*, mode="fixed", target_bpm=160.0, music_gain_db=-6.0, percussion_gain_db=-13.0):
    phrase, rate, source_frames = load_phrase()
    aligned, grid = align_phrase(phrase, rate, source_frames, mode=mode, target_bpm=target_bpm)
    music = edge_fade(aligned, rate) * (10 ** (music_gain_db / 20))
    clicks = make_clicks(len(music), rate, grid)
    drums = (
        percussion(len(music), rate, target_bpm) * (10 ** (percussion_gain_db / 20))
        if mode != "source"
        else np.zeros_like(music)
    )
    return {
        "sample_rate": rate,
        "outputs": {
            "mix": music + drums,
            "music": music,
            "drums": drums,
            "with-clicks": music + clicks,
        },
    }
