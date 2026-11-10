"""Bounded, isolated DSP checks for dependencies whose wheel tags can hide bad binaries.

Doctor owns when these run; normal rendering and imports pay no probe cost.
Each engine runs in the selected interpreter, outside the parent process, so a
loader failure, native crash or hang still produces a diagnostic JSON response.
"""

from __future__ import annotations

import subprocess
import sys

_TIMEOUT = 30
_AUDIO = """
import numpy as np
rate = 44100
audio = (0.1 * np.sin(2 * np.pi * 440 * np.arange(88200) / rate)).astype(np.float32)
"""
_FINITE = """
assert result.size > 0, 'native engine returned no samples'
assert np.isfinite(result).all(), 'native engine returned non-finite samples'
"""
_PROBES = {
    "pyqmdsp": _AUDIO + """
import pyqmdsp
result = pyqmdsp.beats(audio, rate)
assert np.isfinite(result['beats_s']).all(), 'non-finite beat positions'
""",
    **{
        f"pytimestretch.{backend}": _AUDIO + f"""
import pytimestretch
result = pytimestretch.time_stretch(audio, rate, duration_ratio=1.1, backend={backend!r})
assert result.shape == (97020,), 'unexpected stretched frame count'
""" + _FINITE
        for backend in ("rubberband", "signalsmith")
    },
    "pytimestretch.paulstretch": _AUDIO + """
import pytimestretch
result = pytimestretch.extreme_stretch(audio, rate, duration_ratio=1.1)
""" + _FINITE,
}


def _probe(script: str) -> dict[str, str]:
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", script],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": f"native probe timed out after {_TIMEOUT}s"}
    except OSError as exc:
        return {"status": "error", "error": str(exc)}
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-4000:]
        return {
            "status": "error",
            "error": f"native probe exited with code {result.returncode}: {detail}",
        }
    return {"status": "ok"}


def check_native_dependencies() -> dict[str, dict[str, str]]:
    """Exercise QM-DSP and every bundled stretch engine, not just lazy facades."""
    return {name: _probe(script) for name, script in _PROBES.items()}
