"""Tactus: produce music with code. Built for agents."""

from . import analysis, fx, timing
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
    "timing",
    "tool",
]
