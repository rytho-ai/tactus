"""Render only from the compiled arrangement and its material store."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .graph import read_graph
from .material import AudioRef, MaterialStore


def _render_track(track: dict[str, Any], graph: dict[str, Any], store: MaterialStore) -> np.ndarray:
    transport = graph["transport"]
    rate = transport["sample_rate"]
    bpm = transport["bpm"]
    frames = round(transport["bars"] * 4 * 60 / bpm * rate)
    output = np.zeros((frames, 2), dtype=np.float64)
    for event in track["events"]:
        audio = store.read(AudioRef(**event["audio"]))
        if audio.shape[1] == 1:
            audio = np.repeat(audio, 2, axis=1)
        start = round(event["at_beats"] * 60 / bpm * rate)
        length = round(event["duration_beats"] * 60 / bpm * rate)
        available = min(length, len(audio), frames - start)
        if available > 0:
            output[start : start + available] += audio[:available] * 10 ** (
                event["gain_db"] / 20
            )
    return output * 10 ** (track["gain_db"] / 20)


def _wav_bytes(audio: np.ndarray, rate: int) -> bytes:
    if np.max(np.abs(audio)) > 1.0:
        raise ValueError("mix exceeds full scale; lower project or track gains")
    buffer = io.BytesIO()
    sf.write(buffer, audio, rate, format="WAV", subtype="PCM_24")
    return buffer.getvalue()


def render(
    graph_path: Path,
    output: Path,
    *,
    mute: frozenset[str] = frozenset(),
    solo: frozenset[str] = frozenset(),
) -> dict[str, Path]:
    graph_path = graph_path.resolve()
    graph = read_graph(graph_path)
    names = {track["name"] for track in graph["tracks"]}
    if (mute | solo) - names:
        raise ValueError(f"unknown track: {sorted((mute | solo) - names)}")
    rate = graph["transport"]["sample_rate"]
    store = MaterialStore(graph_path.parent / "materials", rate)
    rendered = {track["name"]: _render_track(track, graph, store) for track in graph["tracks"]}
    body = next(iter(rendered.values()))
    included = solo if solo else names - mute
    mix = np.zeros_like(body)
    for name in sorted(included):
        mix += rendered[name]
    files: dict[str, Path] = {}
    output.mkdir(parents=True, exist_ok=True)
    mix_path = output / "mix.wav"
    mix_path.write_bytes(_wav_bytes(mix, rate))
    files["mix"] = mix_path
    for name, audio in rendered.items():
        stem_path = output / f"stem-{name}.wav"
        stem_path.write_bytes(_wav_bytes(audio, rate))
        files[f"stem:{name}"] = stem_path
    return files
