"""Steps: a step sequencer that turns a grid into timed events (in the manner of a TR drum machine).

Self-contained: copy this file into a work and change it freely. It makes events only;
`pads.play` or `sampler.play` (or your own code) turns them into sound.

Reads: tactus.timing.swing
"""

from __future__ import annotations

from tactus.timing import swing as _swing

__all__ = ["events", "from_indices", "hits", "notes"]

_REST = ".-_0"


def _velocities(pattern, level, accent):
    if isinstance(pattern, str):
        cells = [c for c in pattern if not c.isspace() and c != "|"]
        unknown = sorted({c for c in cells if c not in _REST + "xX"})
        if unknown:
            raise ValueError(f"unknown step characters {unknown}; use x, X and . (spaces and | are ignored)")
        return [accent if c == "X" else level if c == "x" else 0.0 for c in cells]
    values = [float(v) for v in pattern]
    if any(v < 0 for v in values):
        raise ValueError("step velocities must be nonnegative")
    return values


def events(pattern, *, bpm, steps_per_beat=4, start_s=0.0, repeats=1, swing=0.5, level=0.7, accent=1.0):
    """Timed hits from a step pattern: returns `(start_s, velocity)` for every active step.

    `pattern` is a string such as `"x... x... X.x. x..."` (`x` plays at `level`, `X` at
    `accent`, `.` rests; spaces and `|` are only for reading) or a sequence of velocities
    where 0 is a rest. Each step lasts 1/`steps_per_beat` beat at `bpm`; the pattern
    plays `repeats` times from `start_s`. `swing` is the position of every second step
    inside its pair as in `timing.swing`: 0.5 straight, 0.58 light, 2/3 triplet.
    """
    velocities = _velocities(pattern, level, accent)
    if not velocities:
        raise ValueError("pattern has no steps")
    if bpm <= 0 or steps_per_beat <= 0 or repeats < 1:
        raise ValueError("bpm and steps_per_beat must be positive and repeats at least 1")
    beat_s = 60.0 / bpm
    unit = 2.0 / steps_per_beat
    out = []
    for step in range(len(velocities) * repeats):
        velocity = velocities[step % len(velocities)]
        if velocity > 0:
            beat = _swing(step / steps_per_beat, swing, unit)
            out.append((start_s + beat * beat_s, velocity))
    return out


def hits(pattern, pad, *, bpm, steps_per_beat=4, start_s=0.0, repeats=1, swing=0.5, level=0.7, accent=1.0):
    """`events` with a pad name attached: `(start_s, pad, velocity)` for `pads.play`."""
    timed = events(pattern, bpm=bpm, steps_per_beat=steps_per_beat, start_s=start_s,
                   repeats=repeats, swing=swing, level=level, accent=accent)
    return [(at, pad, velocity) for at, velocity in timed]


def notes(pattern, pitches, *, bpm, gate=0.5, steps_per_beat=4, start_s=0.0, repeats=1, swing=0.5,
          level=0.7, accent=1.0):
    """`events` as notes `(start_s, pitch, duration_s, velocity)` for `sampler.play`.

    `pitches` is one MIDI number or a sequence cycled over the active steps. Each note
    lasts `gate` of one straight step.
    """
    cycle = [pitches] if isinstance(pitches, (int, float)) else list(pitches)
    step_s = 60.0 / bpm / steps_per_beat
    timed = events(pattern, bpm=bpm, steps_per_beat=steps_per_beat, start_s=start_s,
                   repeats=repeats, swing=swing, level=level, accent=accent)
    return [(at, cycle[i % len(cycle)], gate * step_s, velocity) for i, (at, velocity) in enumerate(timed)]


def from_indices(indices, length, *, velocity=0.7):
    """A velocity pattern of `length` steps with hits at `indices`, e.g. from `timing.euclid`."""
    wanted = set(indices)
    if any(i < 0 or i >= length for i in wanted):
        raise ValueError("indices must lie inside the pattern length")
    return [velocity if i in wanted else 0.0 for i in range(length)]
