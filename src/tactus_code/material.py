"""Content-addressed PCM material at the production boundary."""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf


@dataclass(frozen=True)
class AudioRef:
    sha256: str
    frames: int
    channels: int

    def to_dict(self) -> dict[str, int | str]:
        return {"sha256": self.sha256, "frames": self.frames, "channels": self.channels}


class MaterialStore:
    def __init__(self, root: Path, sample_rate: int) -> None:
        self.root = root
        self.sample_rate = sample_rate

    def _path(self, digest: str) -> Path:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid audio material digest")
        return self.root / "audio" / f"{digest}.wav"

    def add(self, audio: np.ndarray) -> AudioRef:
        samples = np.asarray(audio, dtype=np.float32)
        if samples.ndim == 1:
            samples = samples[:, None]
        if samples.ndim != 2 or samples.shape[1] not in (1, 2) or not len(samples):
            raise ValueError("audio must have nonempty mono or stereo frames")
        if not np.isfinite(samples).all():
            raise ValueError("audio contains NaN or infinity")
        if np.max(np.abs(samples)) > 1.0:
            raise ValueError("audio exceeds full scale; set gain explicitly before materialization")
        buffer = io.BytesIO()
        sf.write(buffer, samples, self.sample_rate, format="WAV", subtype="PCM_24")
        payload = buffer.getvalue()
        digest = hashlib.sha256(payload).hexdigest()
        path = self._path(digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(payload)
        return AudioRef(digest, len(samples), samples.shape[1])

    def import_file(
        self,
        path: Path,
        *,
        start_seconds: float | None = None,
        duration_seconds: float | None = None,
    ) -> AudioRef:
        if start_seconds is not None and (not math.isfinite(start_seconds) or start_seconds < 0):
            raise ValueError("start_seconds must be finite and nonnegative")
        if duration_seconds is not None and (
            not math.isfinite(duration_seconds) or duration_seconds <= 0
        ):
            raise ValueError("duration_seconds must be finite and positive")
        with sf.SoundFile(path) as source:
            rate = source.samplerate
            if rate != self.sample_rate:
                raise ValueError(f"source sample rate {rate} differs from project {self.sample_rate}")
            start = round((start_seconds or 0.0) * rate)
            if start >= len(source):
                raise ValueError("audio region starts outside source")
            requested = (
                len(source) - start
                if duration_seconds is None
                else round(duration_seconds * rate)
            )
            if requested <= 0 or start + requested > len(source):
                raise ValueError("audio region exceeds source or is empty")
            source.seek(start)
            samples = source.read(requested, always_2d=True, dtype="float32")
        return self.add(samples)

    def read(self, ref: AudioRef) -> np.ndarray:
        path = self._path(ref.sha256)
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != ref.sha256:
            raise ValueError(f"audio material hash mismatch: {ref.sha256}")
        audio, rate = sf.read(io.BytesIO(payload), always_2d=True, dtype="float32")
        if rate != self.sample_rate or audio.shape != (ref.frames, ref.channels):
            raise ValueError(f"audio material metadata mismatch: {ref.sha256}")
        return audio
