"""Source-owned identities for the local Music Agent OS sample and beat grid.

The source recording and its beat grid are the work's creative identity: pinned as
`sha256:<hex>` constants and resolved through `tactus.material`, so moving this example
or the pool never changes what it renders. Import them once with
`tactus material add <file>` before running.
"""

from itertools import pairwise

import numpy as np
import soundfile as sf

from tactus import material

SOURCE = "sha256:845406ed5823a0af0dc4eec0985a58398bda9b74310c7c9e76863e1b17db1497"
GRID = "sha256:72aacde1e3184be72ef668f9f5ed67a606e7bf40b17bf05af7c9f02fd8de0b93"


def source_bars() -> tuple[list[np.ndarray], int, np.ndarray]:
    """Select four actual source bars; preserve beat-grid identity as authored input."""
    audio_path = material(SOURCE)
    grid_path = material(GRID)
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
