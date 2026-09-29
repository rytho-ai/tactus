"""Named, hash-verified PCM output at the production boundary.

`encode_pcm24` owns clipping, measurement and WAV quantization for run delivery and
export formats. `OutputStore.add` names and stores those bytes with an `AudioRef`.
FLAC exporters consume the quantized integers so encoder rounding cannot change samples.

Reads: numpy · soundfile
"""

from __future__ import annotations

import hashlib
import io
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

# Owns the output-name shape: run.py's early validation and this module's own
# defensive check both defer to this single pattern so the rule never drifts.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validate_name(name: str) -> None:
    if not NAME_PATTERN.match(name):
        raise ValueError(
            f"output {name!r} must match [A-Za-z0-9][A-Za-z0-9._-]* to be a safe filename"
        )


@dataclass(frozen=True)
class AudioRef:
    sha256: str
    frames: int
    channels: int
    file: str

    def to_dict(self) -> dict[str, int | str]:
        return {
            "sha256": self.sha256,
            "frames": self.frames,
            "channels": self.channels,
            "file": self.file,
        }


def encode_pcm24(audio: np.ndarray, sample_rate: int) -> tuple[bytes, dict]:
    """Return default delivery WAV bytes and pre-clip levels, with one PCM24 policy."""
    samples = np.asarray(audio, dtype=np.float32)
    if samples.ndim == 1:
        samples = samples[:, None]
    if samples.ndim != 2 or samples.shape[1] not in (1, 2) or not len(samples):
        raise ValueError("audio must have nonempty mono or stereo frames")
    if not np.isfinite(samples).all():
        raise ValueError("audio contains NaN or infinity")
    peak = float(np.max(np.abs(samples)))
    levels: dict[str, float | int | None] = {
        "peak_dbfs": round(20 * math.log10(peak), 2) if peak > 0 else None,
        "clipped_samples": int(np.count_nonzero(np.abs(samples) > 1.0)),
    }
    clipped = np.clip(samples, -1.0, 1.0)
    buffer = io.BytesIO()
    sf.write(buffer, clipped, sample_rate, format="WAV", subtype="PCM_24")
    payload = buffer.getvalue()
    return payload, levels


class OutputStore:
    def __init__(self, root: Path, sample_rate: int) -> None:
        self.root = root
        self.sample_rate = sample_rate

    def add(self, name: str, audio: np.ndarray) -> tuple[AudioRef, dict[str, float | int | None]]:
        """Clip to full scale, write PCM24, and return the ref plus the pre-clip levels.

        `peak_dbfs` is the peak of `audio` as given (before clipping), `null` for digital
        silence; `clipped_samples` counts sample values (all channels) outside ±1. Nothing
        about level is refused here or anywhere upstream — over-full-scale audio publishes
        clipped.
        """
        validate_name(name)
        samples = np.asarray(audio)
        payload, levels = encode_pcm24(samples, self.sample_rate)
        digest = hashlib.sha256(payload).hexdigest()
        filename = f"{name}-{digest[:8]}.wav"
        path = self.root / filename
        self.root.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(payload)
        channels = 1 if samples.ndim == 1 else samples.shape[1]
        return AudioRef(digest, len(samples), channels, filename), levels

    def read(self, ref: AudioRef) -> np.ndarray:
        stem, _, suffix = ref.file.rpartition("-")
        if suffix != f"{ref.sha256[:8]}.wav" or not NAME_PATTERN.match(stem):
            raise ValueError(f"audio output file does not match its reference: {ref.file!r}")
        path = self.root / ref.file
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != ref.sha256:
            raise ValueError(f"audio output hash mismatch: {ref.sha256}")
        audio, rate = sf.read(io.BytesIO(payload), always_2d=True, dtype="float32")
        if rate != self.sample_rate or audio.shape != (ref.frames, ref.channels):
            raise ValueError(f"audio output metadata mismatch: {ref.sha256}")
        return audio
