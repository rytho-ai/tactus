"""Tactus: produce music with code. Built for agents.

`tactus.analysis` and `tactus.devices` load on first access, so importing Tactus does not
import SciPy's signal package until an analysis (or DSP/synthesis) needs it.
"""

import importlib

from . import fx, timemap, timing
from .excerpt import excerpt
from .inputs import MaterialError, ToolError, load_audio, material, tool
from .render_store import LoadedRender, load_render
from .run import RunError, run
from .stage import stage
from .store import AudioRef
from .takes import load_take

__all__ = [
    "AudioRef",
    "LoadedRender",
    "MaterialError",
    "RunError",
    "ToolError",
    "analysis",
    "excerpt",
    "fx",
    "load_audio",
    "load_render",
    "load_take",
    "material",
    "run",
    "stage",
    "timemap",
    "timing",
    "tool",
]


_LAZY = ("analysis", "devices", "dsp", "synth")


def __dir__():
    return sorted(set(globals()) | set(_LAZY))


def __getattr__(name):
    if name in _LAZY:
        return importlib.import_module("." + name, __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
