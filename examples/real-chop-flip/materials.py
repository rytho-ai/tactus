"""Source-owned identities for the local Music Agent OS sample and beat grid."""

import hashlib
import os
from itertools import pairwise
from pathlib import Path

import numpy as np
import soundfile as sf

ASSETS = (
    Path(__file__).resolve().parents[2]
    / "dogfood"
    / "2026-09-16-real-chop-flip"
    / "project"
    / "assets"
)
SOURCE_SHA256 = "845406ed5823a0af0dc4eec0985a58398bda9b74310c7c9e76863e1b17db1497"
GRID_SHA256 = "72aacde1e3184be72ef668f9f5ed67a606e7bf40b17bf05af7c9f02fd8de0b93"


def checked_path(variable: str, filename: str, expected: str) -> Path:
    path = Path(os.environ.get(variable, ASSETS / filename)).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Set {variable} to the locally owned {filename}")
    with path.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    if digest != expected:
        raise ValueError(f"{variable} identity mismatch: expected {expected}, got {digest}")
    return path


def source_bars() -> tuple[list[np.ndarray], int, np.ndarray]:
    """Select four actual source bars; preserve beat-grid identity as authored input."""
    audio_path = checked_path("TACTUS_CHOP_SOURCE", "CErZvbcaOeE_inst.wav", SOURCE_SHA256)
    grid_path = checked_path("TACTUS_CHOP_GRID", "CErZvbcaOeE.npy", GRID_SHA256)
    grid = np.load(grid_path, allow_pickle=False)
    downbeats = grid[grid[:, 1] == 1, 0]
    first = int(np.argmin(np.abs(downbeats - 54.1)))
    boundaries = downbeats[first : first + 5]
    if len(boundaries) != 5:
        raise ValueError("selected source phrase needs five downbeat boundaries")
    bars = []
    with sf.SoundFile(audio_path) as file:
        rate = file.samplerate
        if rate != 44100 or file.channels != 2:
            raise ValueError("this production is authored for the pinned 44.1 kHz stereo source")
        for start, end in pairwise(boundaries):
            left, right = round(float(start) * rate), round(float(end) * rate)
            file.seek(left)
            bars.append(file.read(right - left, dtype="float32", always_2d=True))
    return bars, rate, boundaries
