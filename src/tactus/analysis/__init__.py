"""tactus.analysis: measurements on Tactus audio, grouped into categories.

A category is one aspect of sound and one module here (`level`, `spectral`, ...); names
inside a category carry no prefix. `CATEGORIES` maps category name to module, and each
module's `ANALYSES` tuple lists its public analysis functions. Every analysis takes `audio` in
Tactus's `(frames,)`/`(frames, channels)` float layout and `sample_rate` (matching `render`'s
own `sample_rate`), plus keyword parameters with type hints and defaults, and returns a
JSON-ready dict; none returns a pass/fail verdict — Tactus reports, not blocks (see
`docs/design.md`'s "驗證與觀察"). `tactus analyze` (see `tactus.cli`) generates its three-level
`--help` and its subcommands from `CATEGORIES`/`ANALYSES`; the library mirrors the same
structure:

    from tactus.analysis import spectral
    spectral.centroid(mix, rate, threshold_hz=2000.0)   # -> dict
    help(spectral)                                       # -> category summary + analyses

See `level.py` and `spectral.py` for the categories currently shipped, and each analysis's own
docstring for its parameters, result fields, units and definitions.

Reads: level · spectral
"""

from __future__ import annotations

from . import level, spectral

CATEGORIES = {"level": level, "spectral": spectral}

__all__ = ["CATEGORIES", "level", "spectral"]
