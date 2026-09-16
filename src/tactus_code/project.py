"""Small authoring boundary; music-making functions remain ordinary Python."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .material import AudioRef, MaterialStore


def _finite(value: float, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


@dataclass
class Track:
    project: Project
    name: str
    gain_db: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)

    def place(
        self,
        id: str,
        audio: AudioRef,
        *,
        at_beats: float,
        duration_beats: float | None = None,
        gain_db: float = 0.0,
    ) -> Track:
        if not id or any(event["id"] == id for event in self.project.all_events()):
            raise ValueError(f"empty or duplicate event id: {id!r}")
        at = _finite(at_beats, "at_beats")
        duration = (
            audio.frames / self.project.sample_rate * self.project.bpm / 60
            if duration_beats is None
            else _finite(duration_beats, "duration_beats")
        )
        if at < 0 or duration <= 0 or at + duration > self.project.total_beats + 1e-9:
            raise ValueError(f"event {id!r} is outside the project body")
        self.events.append(
            {
                "id": id,
                "at_beats": at,
                "duration_beats": duration,
                "gain_db": _finite(gain_db, "gain_db"),
                "audio": audio.to_dict(),
            }
        )
        return self


class Project:
    def __init__(
        self, *, root: Path, materials: Path, bpm: float, bars: int, sample_rate: int = 48000
    ) -> None:
        if bars <= 0 or sample_rate <= 0 or _finite(bpm, "bpm") <= 0:
            raise ValueError("bars, bpm, and sample_rate must be positive")
        self.root = root.resolve()
        self.bpm = float(bpm)
        self.bars = bars
        self.sample_rate = sample_rate
        self.total_beats = 4 * bars  # 4/4 is the first-slice transport contract.
        self.store = MaterialStore(materials, sample_rate)
        self.tracks: list[Track] = []
        self.computations: list[dict[str, Any]] = []
        self.inputs: list[dict[str, str]] = []

    def asset(self, path: str | Path) -> AudioRef:
        source = (self.root / path).resolve()
        if not source.is_relative_to(self.root) or not source.is_file():
            raise ValueError(f"asset must be a file inside the project: {path}")
        ref = self.store.import_file(source)
        self.inputs.append(
            {
                "path": source.relative_to(self.root).as_posix(),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "material_sha256": ref.sha256,
            }
        )
        return ref

    def compute(
        self,
        id: str,
        run: Callable[..., np.ndarray],
        *,
        inputs: Mapping[str, AudioRef] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> AudioRef:
        if not id or any(node["id"] == id for node in self.computations):
            raise ValueError(f"empty or duplicate computation id: {id!r}")
        refs = dict(inputs or {})
        values = dict(params or {})
        json.dumps(values, allow_nan=False, sort_keys=True)
        if set(refs) & set(values) or "sample_rate" in refs or "sample_rate" in values:
            raise ValueError("compute input names, parameter names, and sample_rate must be distinct")
        arguments = {name: self.store.read(ref) for name, ref in refs.items()}
        result = run(**arguments, sample_rate=self.sample_rate, **values)
        output = self.store.add(result)
        source_path = inspect.getsourcefile(run)
        code_sha = (
            hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
            if source_path and Path(source_path).is_file()
            else None
        )
        self.computations.append(
            {
                "id": id,
                "callable": f"{run.__module__}.{run.__qualname__}",
                "code_sha256": code_sha,
                "inputs": {name: ref.sha256 for name, ref in refs.items()},
                "params": values,
                "output": output.to_dict(),
                "reproducibility": "materialized; source recomputation not guaranteed",
            }
        )
        return output

    def track(self, name: str, *, gain_db: float = 0.0) -> Track:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or any(
            track.name == name for track in self.tracks
        ):
            raise ValueError(f"empty or duplicate track name: {name!r}")
        track = Track(self, name, _finite(gain_db, "gain_db"))
        self.tracks.append(track)
        return track

    def all_events(self) -> list[dict[str, Any]]:
        return [event for track in self.tracks for event in track.events]

    def arrangement(self) -> dict[str, Any]:
        if not self.tracks:
            raise ValueError("a project needs at least one track")
        return {
            "format_version": 1,
            "transport": {
                "bpm": self.bpm,
                "bars": self.bars,
                "meter": [4, 4],
                "sample_rate": self.sample_rate,
            },
            "tracks": [
                {"name": track.name, "gain_db": track.gain_db, "events": track.events}
                for track in self.tracks
            ],
            "computations": self.computations,
            "inputs": self.inputs,
            "outputs": ["mix", *[f"stem:{track.name}" for track in self.tracks]],
        }
