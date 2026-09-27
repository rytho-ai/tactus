"""tactus.timing: musical time <-> seconds <-> frames for a Tactus work (optional).

Nothing here decides feel: tempo, meter, swing, groove and quantize-strength amounts are
yours. Beats are 0-based quarter notes counted from the start of a bar (a musician's "beat 2"
is `beat=1.0`). Every conversion is computed absolutely from the start of the piece (never by
accumulating bar lengths), and rounded once: `frame = floor(seconds * sample_rate + 0.5)` —
that rule has one owner, the module-level `frame_of`. Nothing in `run`/`render` requires this
module; a work may keep its own time maths, or mix it with this one.

    from tactus.timing import Clock, swing, Groove, quantize, note_seconds, add_at, markers

    clock = Clock(sample_rate=48000,
                  tempo=[(1, 92),                      # 92 BPM from bar 1
                         (13, 92), (17, 100, "ramp"),   # gradual 92 -> 100 over bars 13-16
                         (21, 120),                     # a sudden change at bar 21
                         (25, 120), (29, 70, "smooth")],  # an eased slow-down
                  meter=[(1, 4), (9, 3.5), (10, 4)],    # quarter beats per bar (7/8 = 3.5)
                  start_seconds=6.0)                    # after a free-time intro
    clock.frame(9, 1.5)                   # bar 9, beat 1.5 (beats: 0-based quarter notes)
    clock.frame(9, 1.5, ms=-7.0)          # 7 ms early: pushes, flams, humanization
    clock.frame(9, swing(1.75, 0.58))     # swung sixteenth (see swing)
    groove.frame(clock, 9, 1.75)          # a groove template applied (see Groove)
    clock.frame_at(37.25, ms=3.0)         # absolute beat from bar 1, ignoring bar lines
    clock.beat_of(20.0), clock.bpm_at(40.0)
    for bar in clock.bars(1, 12): ...     # .number .start_beat .beats .start_frame .end_frame
    clock.span(17, 25)                    # frame range of bars 17..24
    frame_of(3.3, 48000)                  # free time: plain seconds, no clock needed
    quantize(1.61, grid=0.25, strength=0.75)         # a performed beat moved toward its 16th
    note_seconds(clock, 0.0, 0.75)                   # a dotted eighth's seconds at that tempo
    add_at(buffer, clip, clock.frame(9, 1.5))        # in-place mix; head/tail cut, never wraps
    markers([clock.frame(b) for b in range(1, 9)], length)  # one impulse per in-range frame

Tempo points: `(bar, bpm)` is a step (the tempo becomes `bpm` at that bar). `(bar, bpm, shape)`
is a gradual change that starts at the previous point and arrives at `bpm` at this bar; shape
is `"ramp"` (linear in beats, as most DAWs draw it), `"ramp-time"` (linear in time) or
`"smooth"` (a cosine-eased S-curve). Bars may be fractional (bar 9.5 = halfway through bar
9's beats).

Reads: numpy · math · bisect
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence
from typing import NamedTuple, Union

import numpy as np

_SHAPES = ("ramp", "ramp-time", "smooth")

TempoPoint = Union[tuple, "Sequence"]


class Bar(NamedTuple):
    number: int
    start_beat: float
    beats: float
    start_frame: int
    end_frame: int


class Clock:
    """Resolves musical position (bar, beat) to seconds and frames under a tempo map.

    `tempo` is a constant BPM, or a list of tempo points (see module docstring). `meter` is a
    constant quarter-beats-per-bar, or a list of `(bar, quarter_beats)` pairs, the first of
    which must start at bar 1 (7/8 is `3.5`). `start_seconds` offsets every result, for a
    free-time intro before the clock starts.
    """

    def __init__(
        self,
        *,
        sample_rate: int,
        tempo: float | Sequence[TempoPoint],
        meter: float | Sequence[tuple] = 4.0,
        start_seconds: float = 0.0,
    ) -> None:
        self.sample_rate = sample_rate
        self.start_seconds = float(start_seconds)
        meters = [(1, float(meter))] if isinstance(meter, (int, float)) else sorted(meter)
        if meters[0][0] != 1:
            raise ValueError("the first meter must start at bar 1")
        self._meter_bars = [b for b, _ in meters]
        self._meter_beats = [float(q) for _, q in meters]
        self._meter_start_beat = [0.0]
        for i in range(1, len(meters)):
            span = self._meter_bars[i] - self._meter_bars[i - 1]
            self._meter_start_beat.append(
                self._meter_start_beat[-1] + span * self._meter_beats[i - 1]
            )
        points = [(1, float(tempo))] if isinstance(tempo, (int, float)) else list(tempo)
        # segments: (beat_start, beat_end, bpm_start, bpm_end, shape); constant between points
        self._segments: list[tuple[float, float, float, float, str]] = []
        prev_beat, prev_bpm = 0.0, float(points[0][1])
        for p in points:
            bar, bpm = p[0], float(p[1])
            if bpm <= 0:
                raise ValueError(f"bpm must be positive, got {bpm} at bar {bar}")
            shape = p[2] if len(p) > 2 else "step"
            if shape not in (*_SHAPES, "step"):
                raise ValueError(f"unknown tempo shape {shape!r}; use one of {_SHAPES} or omit it")
            beat = self._bar_to_beats(bar)
            if beat < prev_beat:
                raise ValueError("tempo points must be in bar order")
            if shape == "step":
                if beat > prev_beat:
                    self._segments.append((prev_beat, beat, prev_bpm, prev_bpm, "const"))
                prev_beat, prev_bpm = beat, bpm
            else:
                if beat == prev_beat:
                    raise ValueError(f"a {shape} needs a previous tempo point before bar {bar}")
                self._segments.append((prev_beat, beat, prev_bpm, bpm, shape))
                prev_beat, prev_bpm = beat, bpm
        self._tail = (prev_beat, prev_bpm)
        # cumulative seconds at each segment start
        self._seg_t0: list[float] = []
        t = 0.0
        for seg in self._segments:
            self._seg_t0.append(t)
            t += self._seg_seconds(seg, seg[1])
        self._tail_t0 = t
        self._inverse: tuple[np.ndarray, np.ndarray] | None = None

    # -- musical position -> beats ------------------------------------------------------
    def _bar_to_beats(self, bar: float) -> float:
        i = max(0, bisect_right(self._meter_bars, math.floor(bar)) - 1)
        return self._meter_start_beat[i] + (bar - self._meter_bars[i]) * self._meter_beats[i]

    def beats(self, bar: float, beat: float = 0.0) -> float:
        """Quarter-note beats from the start of bar 1 to (bar, beat)."""
        return self._bar_to_beats(bar) + beat

    def beats_per_bar(self, bar: int) -> float:
        i = max(0, bisect_right(self._meter_bars, bar) - 1)
        return self._meter_beats[i]

    # -- beats -> seconds ----------------------------------------------------------------
    @staticmethod
    def _seg_seconds(seg: tuple, beat: float) -> float:
        """Seconds from the segment's start to `beat` (within the segment)."""
        b0, b1, q0, q1, shape = seg
        x = beat - b0
        if shape == "const" or q0 == q1:
            return 60.0 * x / q0
        if shape == "ramp":  # bpm linear in beats: integral of 60 / bpm(b) db
            k = (q1 - q0) / (b1 - b0)
            return 60.0 / k * math.log((q0 + k * x) / q0)
        if shape == "ramp-time":  # bpm linear in time over the segment's total duration T
            total = 120.0 * (b1 - b0) / (q0 + q1)
            k = (q1 - q0) / total  # bpm per second
            # beats(t) = (q0 t + k t^2 / 2) / 60 = x  ->  solve for t
            return (-q0 + math.sqrt(q0 * q0 + 2 * k * 60.0 * x)) / k
        # smooth: bpm(u) = q0 + (q1 - q0) * (1 - cos(pi u)) / 2, u = x / (b1 - b0); Simpson.
        # n=512 keeps error under 1e-6 s over a 64-bar span (tested against scipy.quad).
        n = 512
        h = x / n
        if h == 0:
            return 0.0
        f = lambda b: 60.0 / (q0 + (q1 - q0) * (1 - math.cos(math.pi * b / (b1 - b0))) / 2)
        s = f(0) + f(x) + sum((4 if i % 2 else 2) * f(i * h) for i in range(1, n))
        return s * h / 3

    def at(self, beat: float, *, ms: float = 0.0) -> float:
        """Seconds at an absolute beat (0 = start of bar 1), plus an optional ms offset."""
        if beat >= self._tail[0]:
            t = self._tail_t0 + 60.0 * (beat - self._tail[0]) / self._tail[1]
        elif beat < 0:
            first = self._segments[0] if self._segments else (0, 0, self._tail[1], 0, "const")
            t = 60.0 * beat / first[2]
        else:
            i = max(0, bisect_right([s[0] for s in self._segments], beat) - 1)
            t = self._seg_t0[i] + self._seg_seconds(self._segments[i], beat)
        return self.start_seconds + t + ms / 1000.0

    def frame_at(self, beat: float, *, ms: float = 0.0) -> int:
        return frame_of(self.at(beat, ms=ms), self.sample_rate)

    def seconds(self, bar: float, beat: float = 0.0, *, ms: float = 0.0) -> float:
        """Absolute seconds of (bar, beat), plus an optional offset in milliseconds."""
        return self.at(self.beats(bar, beat), ms=ms)

    def frame(self, bar: float, beat: float = 0.0, *, ms: float = 0.0) -> int:
        return frame_of(self.seconds(bar, beat, ms=ms), self.sample_rate)

    def bpm_at(self, beat: float) -> float:
        """The tempo sounding at `beat` (ramp-time is recomputed from `at`, since its shape is
        linear in time, not in beats)."""
        if beat >= self._tail[0]:
            return self._tail[1]
        for b0, b1, q0, q1, shape in self._segments:
            if b0 <= beat < b1:
                u = (beat - b0) / (b1 - b0)
                if shape == "const":
                    return q0
                if shape == "ramp":
                    return q0 + (q1 - q0) * u
                if shape == "smooth":
                    return q0 + (q1 - q0) * (1 - math.cos(math.pi * u)) / 2
                t = self.at(beat) - self.at(b0)
                total = self.at(b1) - self.at(b0)
                return q0 + (q1 - q0) * t / total
        return self._segments[0][2] if self._segments else self._tail[1]

    def _inverse_grid(self) -> tuple[np.ndarray, np.ndarray]:
        """Sample points for `beat_of`'s seed interpolation, covering beat 0..tail exactly at
        each segment's boundaries plus interior points. Sized by segment count, not by beat
        range, so it stays cheap over a long piece; the Newton polish in `beat_of` recovers
        full precision from this coarse seed."""
        if self._inverse is None:
            beats = [0.0]
            for b0, b1, *_ in self._segments:
                steps = 32
                beats.extend(b0 + (b1 - b0) * i / steps for i in range(1, steps + 1))
            grid = np.array(beats, dtype=float)
            times = np.array([self.at(b) for b in grid], dtype=float)
            self._inverse = (times, grid)
        return self._inverse

    def beat_of(self, seconds):
        """The absolute beat sounding at `seconds` (inverse of `at`); accepts arrays.

        Before the piece starts and beyond the last tempo point, the tempo is constant, so
        those regions use the exact closed form; only the region covered by tempo segments
        needs numeric inversion (an interpolated seed, polished by two Newton steps on
        d(seconds)/d(beat) = 60 / bpm)."""
        t = np.asarray(seconds, dtype=float)
        scalar = t.ndim == 0
        t = np.atleast_1d(t).astype(float)

        tail_beat, tail_bpm = self._tail
        seconds_tail = self.start_seconds + self._tail_t0
        seconds_zero = self.start_seconds
        first_bpm = self._segments[0][2] if self._segments else tail_bpm

        out = np.empty_like(t)
        before = t < seconds_zero
        after = t >= seconds_tail
        within = ~before & ~after

        out[before] = (t[before] - seconds_zero) * first_bpm / 60.0
        out[after] = tail_beat + (t[after] - seconds_tail) * tail_bpm / 60.0

        if within.any():
            times, grid = self._inverse_grid()
            tw = t[within]
            b = np.interp(tw, times, grid)
            for _ in range(2):  # Newton polish on d(seconds)/d(beat) = 60 / bpm
                err = np.vectorize(self.at)(b) - tw
                b = b - err * np.vectorize(self.bpm_at)(b) / 60.0
            out[within] = b

        return float(out[0]) if scalar else out

    def bars(self, first: int = 1, last: int | None = None):
        """Bar records for bars first..last inclusive."""
        last = first if last is None else last
        for n in range(first, last + 1):
            yield Bar(
                n, self._bar_to_beats(n), self.beats_per_bar(n), self.frame(n), self.frame(n + 1)
            )

    def span(self, first_bar: int, end_bar: int) -> tuple[int, int]:
        """(first frame of first_bar, first frame of end_bar)."""
        return self.frame(first_bar), self.frame(end_bar)


def frame_of(seconds: float, sample_rate: int) -> int:
    """The single rounding rule: floor(seconds * sample_rate + 0.5)."""
    return math.floor(seconds * sample_rate + 0.5)


def quantize(beat: float, grid: float = 0.25, strength: float = 1.0) -> float:
    """Move `beat` toward the nearest multiple of `grid` by `strength` (0 = no move, 1 = snap
    exactly onto the grid). An exact tie (`beat` exactly halfway between two grid points)
    resolves to the LATER grid point, guarded against float noise near the tie."""
    steps = math.floor(beat / grid + 0.5 + 1e-9)
    nearest = steps * grid
    return beat + strength * (nearest - beat)


def note_seconds(clock: Clock, beat: float, value: float) -> float:
    """Seconds equivalent of a note `value` in beats (e.g. 0.75 dotted eighth, 2/3 quarter
    triplet) at the tempo sounding at `beat` (`clock.bpm_at(beat)`)."""
    return value * 60.0 / clock.bpm_at(beat)


def swing(beat: float, amount: float, unit: float = 0.5) -> float:
    """Swing a beat position: within each `unit` (0.5 = an eighth note, so sixteenths swing),
    the midpoint moves to `amount` of the unit (0.5 = straight, 0.58 = 58%, 2/3 = triplet).
    Positions between are stretched linearly, so any event (fills, grace notes) swings
    consistently. Use the beat position within the bar (odd meters stay aligned)."""
    k, r = divmod(beat, unit)
    x = r / unit
    y = x * (amount / 0.5) if x <= 0.5 else amount + (x - 0.5) * ((1 - amount) / 0.5)
    return k * unit + y * unit


class Groove:
    """A repeating micro-timing and velocity template over a grid.

    offsets_ms: one timing offset per grid slot (e.g. 16 values for sixteenths in a bar);
    velocities: optional per-slot gain multipliers; grid: slot length in beats (0.25 =
    sixteenth). Positions between slots take the nearer slot's values. You write the values;
    nothing here chooses a feel.
    """

    def __init__(
        self,
        offsets_ms: Sequence[float],
        velocities: Sequence[float] | None = None,
        grid: float = 0.25,
    ) -> None:
        self.offsets_ms = list(offsets_ms)
        self.velocities = (
            list(velocities) if velocities is not None else [1.0] * len(self.offsets_ms)
        )
        if len(self.velocities) != len(self.offsets_ms):
            raise ValueError("velocities and offsets_ms must have the same length")
        self.grid = grid

    def _slot(self, beat: float) -> int:
        return math.floor(beat / self.grid + 0.5) % len(self.offsets_ms)

    def ms(self, beat: float) -> float:
        return self.offsets_ms[self._slot(beat)]

    def velocity(self, beat: float) -> float:
        return self.velocities[self._slot(beat)]

    def frame(self, clock: Clock, bar: float, beat: float, *, ms: float = 0.0) -> int:
        """clock.frame with this groove's offset for the in-bar `beat` added."""
        return clock.frame(bar, beat, ms=ms + self.ms(beat))


def add_at(buffer: np.ndarray, clip: np.ndarray, frame: int, gain: float = 1.0) -> np.ndarray:
    """Add `clip * gain` into `buffer` starting at `frame`, in place. Returns `buffer`.

    A clip starting before frame 0 has its head (the part before 0) dropped; a clip running
    past the end of `buffer` has its tail dropped. Never wraps around either end.
    """
    n = len(buffer)
    dst_start = frame
    src_start = 0
    if dst_start < 0:
        src_start = -dst_start
        dst_start = 0
    if dst_start >= n or src_start >= len(clip):
        return buffer
    src_end = min(src_start + (n - dst_start), len(clip))
    length = src_end - src_start
    if length <= 0:
        return buffer
    part = clip[src_start:src_end]
    if buffer.ndim == 2 and part.ndim == 1:
        part = part[:, None]
    buffer[dst_start : dst_start + length] += part * gain
    return buffer


def markers(
    frames: Sequence[float], length: int, value: float = 0.5, channels: int = 1
) -> np.ndarray:
    """A mono (or multi-channel) impulse track: one impulse of `value` per distinct in-range
    frame in `frames`. Frames outside [0, length) are dropped; coincident frames collapse to a
    single impulse (not summed). Frames must be whole numbers (round with `frame_of`)."""
    shape = (length,) if channels == 1 else (length, channels)
    out = np.zeros(shape, dtype=np.float32)
    seen: set[int] = set()
    for f in frames:
        fi = int(f)
        if fi != f:
            raise ValueError(f"markers needs whole frames, got {f!r}; round with frame_of")
        if 0 <= fi < length and fi not in seen:
            seen.add(fi)
            out[fi] = value
    return out


def envelope_beats(clock: Clock, points: Sequence[tuple], length: int) -> np.ndarray:
    """Per-frame curve, linear in musical position between ((bar, beat), value) points."""
    xs = [
        clock.beats(*pos) if not isinstance(pos, (int, float)) else clock.beat_of(pos)
        for pos, _ in points
    ]
    vs = [float(v) for _, v in points]
    t = np.arange(length) / clock.sample_rate
    return np.interp(clock.beat_of(t), xs, vs).astype(np.float32)


def envelope_seconds(clock: Clock, points: Sequence[tuple], length: int) -> np.ndarray:
    """Per-frame curve, linear in time between ((bar, beat) or seconds, value) points."""
    xs = [pos if isinstance(pos, (int, float)) else clock.seconds(*pos) for pos, _ in points]
    vs = [float(v) for _, v in points]
    t = np.arange(length) / clock.sample_rate
    return np.interp(t, xs, vs).astype(np.float32)


__all__ = [
    "Bar",
    "Clock",
    "Groove",
    "add_at",
    "envelope_beats",
    "envelope_seconds",
    "frame_of",
    "markers",
    "note_seconds",
    "quantize",
    "swing",
]
