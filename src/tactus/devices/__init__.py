"""Music devices: familiar ways of making music as plain functions (not audio hardware).

`sampler` plays a recording as a pitched instrument, `pads` plays slices and one-shots
from named pads, and `steps` turns a step grid into events. Use them directly
(`from tactus.devices import sampler`) or copy a file into your work and change it:
each module is self-contained, needs only NumPy and public Tactus modules, and takes
and returns ordinary arrays, tuples and dicts. Nothing here chooses a sound; the
material and settings you pass do.

Events use absolute seconds: a note is `(start_s, pitch, duration_s, velocity)` with a
MIDI pitch number (fractions allowed) and velocity 0..1; a pad hit is
`(start_s, pad, velocity)`.

Reads: pads · sampler · steps
"""

from . import pads, sampler, steps

__all__ = ["pads", "sampler", "steps"]
