"""tactus.analysis: measurements on Tactus audio, grouped into categories.

A category is one aspect of sound and one module here (`level`, `spectral`, ...); names
inside a category carry no prefix. `CATEGORIES` maps category name to module, and each
module's `ANALYSES` tuple lists its public analysis functions. Every analysis takes `audio` in
Tactus's `(frames,)`/`(frames, channels)` float layout and `sample_rate` (matching `render`'s
own `sample_rate`), plus keyword parameters with type hints and defaults, and returns a
dict of values and optionally NumPy feature arrays (CLI arrays require --out attachments);
none returns a pass/fail verdict — Tactus reports, not blocks (see
`docs/design.md`'s "驗證與觀察"). `tactus analyze` (see `tactus.cli`) generates its three-level
`--help` and its subcommands from `CATEGORIES`/`ANALYSES`; the library mirrors the same
structure:

    from tactus.analysis import spectral
    spectral.centroid(mix, rate, threshold_hz=2000.0)   # -> dict
    help(spectral)                                       # -> category summary + analyses

See `level.py`, `spectral.py` and `rhythm.py` for the shipped categories, and each analysis's own
docstring for its parameters, result fields, units and definitions.

image(result, ...) optionally renders supported matrices as a labeled SVG without
changing their arrays; CLI --image publishes it alongside the numerical attachments.

Reads: level · spectral · rhythm · _image
"""

from __future__ import annotations

from . import level, rhythm, spectral
from ._image import image

CATEGORIES = {"level": level, "spectral": spectral, "rhythm": rhythm}

__all__ = ["CATEGORIES", "image", "level", "rhythm", "spectral"]
