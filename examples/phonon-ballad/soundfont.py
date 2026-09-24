"""Small, dependency-free FluidSynth bridge for a sample-based comparison palette.

FluidR3 is provided by the host's ``fluid-soundfont-gm`` package (MIT license).
Only rendered audio is exported; the soundfont itself is not redistributed here.
libfluidsynth is declared with ``tactus.tool`` using the path of the shared object
Linux actually mapped into this process (scanned from ``/proc/self/maps``), so the
receipt names the binary that was used, not just the ``ctypes.CDLL`` search name.
This resolution is Linux-only; a different platform needs its own equivalent.
"""

from __future__ import annotations

import ctypes as ct
from pathlib import Path
from typing import Self

import numpy as np

from tactus import tool


def _loaded_library_path(soname_fragment: str) -> str:
    """The absolute path Linux mapped for a loaded shared object, from /proc/self/maps."""
    with open("/proc/self/maps", encoding="utf-8") as maps:
        for line in maps:
            if soname_fragment in line:
                return line.rsplit(" ", 1)[-1].strip()
    raise RuntimeError(f"{soname_fragment} is not mapped in this process")


class SoundFont:
    def __init__(self, path: Path, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self.cache: dict[tuple[int, int, int, int], np.ndarray] = {}
        self.lib = ct.CDLL("libfluidsynth.so.3")
        tool(_loaded_library_path("libfluidsynth.so"))
        lib = self.lib
        lib.new_fluid_settings.restype = ct.c_void_p
        lib.fluid_settings_setnum.argtypes = (ct.c_void_p, ct.c_char_p, ct.c_double)
        lib.fluid_settings_setint.argtypes = (ct.c_void_p, ct.c_char_p, ct.c_int)
        lib.new_fluid_synth.argtypes = (ct.c_void_p,)
        lib.new_fluid_synth.restype = ct.c_void_p
        lib.fluid_synth_sfload.argtypes = (ct.c_void_p, ct.c_char_p, ct.c_int)
        lib.fluid_synth_sfload.restype = ct.c_int
        lib.fluid_synth_program_change.argtypes = (ct.c_void_p, ct.c_int, ct.c_int)
        lib.fluid_synth_noteon.argtypes = (ct.c_void_p, ct.c_int, ct.c_int, ct.c_int)
        lib.fluid_synth_noteoff.argtypes = (ct.c_void_p, ct.c_int, ct.c_int)
        lib.fluid_synth_all_sounds_off.argtypes = (ct.c_void_p, ct.c_int)
        lib.fluid_synth_write_float.argtypes = (
            ct.c_void_p,
            ct.c_int,
            ct.c_void_p,
            ct.c_int,
            ct.c_int,
            ct.c_void_p,
            ct.c_int,
            ct.c_int,
        )
        lib.delete_fluid_synth.argtypes = (ct.c_void_p,)
        lib.delete_fluid_settings.argtypes = (ct.c_void_p,)
        self.settings = lib.new_fluid_settings()
        if not self.settings:
            raise RuntimeError("FluidSynth settings could not be created")
        lib.fluid_settings_setnum(self.settings, b"synth.sample-rate", sample_rate)
        lib.fluid_settings_setnum(self.settings, b"synth.gain", 0.3)
        lib.fluid_settings_setint(self.settings, b"synth.reverb.active", 0)
        lib.fluid_settings_setint(self.settings, b"synth.chorus.active", 0)
        self.synth = lib.new_fluid_synth(self.settings)
        if not self.synth:
            lib.delete_fluid_settings(self.settings)
            raise RuntimeError("FluidSynth could not be created")
        if lib.fluid_synth_sfload(self.synth, str(path).encode(), 1) < 0:
            self.close()
            raise FileNotFoundError(f"Could not load soundfont: {path}")

    def _render(self, frames: int) -> np.ndarray:
        left = np.zeros(frames, dtype=np.float32)
        right = np.zeros(frames, dtype=np.float32)
        self.lib.fluid_synth_write_float(
            self.synth,
            frames,
            left.ctypes.data,
            0,
            1,
            right.ctypes.data,
            0,
            1,
        )
        return (left + right) * 0.5

    def note(self, program: int, pitch: int, seconds: float, tail: float = 0.3) -> np.ndarray:
        on_frames = max(1, int(seconds * self.sample_rate))
        tail_frames = max(1, int(tail * self.sample_rate))
        key = (program, pitch, on_frames, tail_frames)
        if key not in self.cache:
            lib = self.lib
            lib.fluid_synth_all_sounds_off(self.synth, 0)
            lib.fluid_synth_program_change(self.synth, 0, program)
            lib.fluid_synth_noteon(self.synth, 0, pitch, 88)
            head = self._render(on_frames)
            lib.fluid_synth_noteoff(self.synth, 0, pitch)
            self.cache[key] = np.concatenate((head, self._render(tail_frames)))
        return self.cache[key]

    def close(self) -> None:
        if getattr(self, "synth", None):
            self.lib.delete_fluid_synth(self.synth)
            self.synth = None
        if getattr(self, "settings", None):
            self.lib.delete_fluid_settings(self.settings)
            self.settings = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
