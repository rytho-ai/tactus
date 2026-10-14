"""tactus.timing: musical time <-> seconds <-> frames for a Tactus work (optional).

Nothing here decides feel: tempo, meter, swing, groove and quantize-strength amounts are
yours. Beats are 0-based quarter notes counted from the start of a bar (a musician's "beat 2"
is `beat=1.0`). Every conversion is computed absolutely from the start of the piece (never by
accumulating bar lengths), and rounded once: `frame = floor(seconds * sample_rate + 0.5)` —
that rule has one owner, the module-level `frame_of`. Nothing in `run`/`render` requires this
module; a work may keep its own time maths, or mix it with this one.

    from tactus.timing import Clock, swing, Groove, quantize, note_seconds, add_at, markers
    from tactus.timing import euclid, cycle

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
    euclid(4, 7)                          # Bjorklund hit steps: (0, 2, 4, 6)
    euclid(2, 5, rotate=1)                # Tidal-style left rotation: (1, 4)
    cycle("x..x.", 16)                    # a 5-step figure run continuously over 16 steps

Fitting adopted beat times (any tracker, or taps) to a constant grid, outside `render`; the
work picks the candidate and the downbeat and freezes `(bpm, bar-1 seconds)` as constants:

    from tactus.timing import fit_tempo, segment, warp_markers, fold
    fits = fit_tempo(beats_s, bpm_range=(60, 100))  # candidates, best first: TempoFit
    fits[0].bpm, fits[0].origin_s, fits[0].coverage  # 85.0, a beat near 0 s, ~1.0
    source = Clock(sample_rate=sr, tempo=85, start_seconds=0.734)   # frozen bar 1
    seg = segment(audio, source.frame(1) - lead, source.frame(9) + lead)   # zero-padded
    pairs = warp_markers(source, Clock(sample_rate=sr, tempo=88), 1, 9,
                         lead_frames=lead, tail_frames=lead)  # for pytimestretch.time_warp
    fold(onsets_s, period_s=4 * 60 / 85, origin_s=0.734, steps=16)  # onsets per 16th of a bar

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
from itertools import pairwise
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
    """Round an absolute time to a frame: floor(seconds * sample_rate + 0.5).

    Half-sample ties go to the later frame, including negative times. Used by
    musical placement and excerpt boundaries; DSP/analysis window lengths have
    their own documented discretization contracts."""
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


def _bjorklund(k: int, n: int) -> list[int]:
    """The classic recursive Bjorklund construction: n 0/1 ints with k evenly-spread 1s (NOT
    the "floor(i*k/n) != floor((i-1)*k/n)" shortcut formula, which differs from Tidal/Strudel
    for some (k, n)). Caller guarantees 0 < k < n."""
    pattern: list[int] = []
    counts: list[int] = []
    remainders = [k]
    divisor = n - k
    level = 0
    while remainders[level] > 1:
        counts.append(divisor // remainders[level])
        remainders.append(divisor % remainders[level])
        divisor = remainders[level]
        level += 1
    counts.append(divisor)

    def build(lvl: int) -> None:
        if lvl == -1:
            pattern.append(0)
        elif lvl == -2:
            pattern.append(1)
        else:
            for _ in range(counts[lvl]):
                build(lvl - 1)
            if remainders[lvl] != 0:
                build(lvl - 2)

    build(level)
    i = pattern.index(1)
    return pattern[i:] + pattern[:i]


def euclid(k: int, n: int, rotate: int = 0) -> tuple[int, ...]:
    """The hit step indices (0-based, ascending) of a Euclidean rhythm of k hits over n steps
    (Bjorklund's algorithm), as TidalCycles/Strudel produce them. `rotate` follows Tidal's
    `(k, n, r)`: it rotates the pattern LEFT, so a hit originally at step s ends up at
    `(s - rotate) % n`; a negative `rotate` moves hits later instead. E.g. `euclid(4, 7)` ->
    `(0, 2, 4, 6)`; `euclid(2, 5, rotate=1)` -> `(1, 4)`."""
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if not 0 <= k <= n:
        raise ValueError(f"k must be within 0..{n}, got {k}")
    if k == 0:
        base_hits: tuple[int, ...] = ()
    elif k == n:
        base_hits = tuple(range(n))
    else:
        base_hits = tuple(i for i, v in enumerate(_bjorklund(k, n)) if v)
    r = rotate % n
    if r == 0 or not base_hits:
        return base_hits
    return tuple(sorted((s - r) % n for s in base_hits))


def cycle(figure: str | Sequence[bool], count: int, start: int = 0) -> tuple[int, ...]:
    """The steps in `[start, start + count)` where `figure` hits, as it repeats continuously
    from step 0 (it never restarts at bar lines; callers map steps to bars and beats
    themselves). `figure` is a string of `x`/`X` for hits and `.`/`~` for rests (whitespace
    ignored), or a sequence of bools. E.g. `cycle("x..x.", 16)` ->
    `(0, 3, 5, 8, 10, 13, 15)`."""
    if isinstance(figure, str):
        chars = [c for c in figure if not c.isspace()]
        hits: list[bool] = []
        for c in chars:
            if c in ("x", "X"):
                hits.append(True)
            elif c in (".", "~"):
                hits.append(False)
            else:
                raise ValueError(f"unknown figure character {c!r} in {figure!r}; use x, X, . or ~")
    else:
        hits = [bool(v) for v in figure]
    m = len(hits)
    if m == 0:
        raise ValueError("figure must not be empty")
    if count < 0:
        raise ValueError(f"count must not be negative, got {count}")
    return tuple(s for s in range(start, start + count) if hits[s % m])


# -- fitting adopted beat times to a constant grid ------------------------------------------


class TempoFit(NamedTuple):
    """One constant-tempo grid candidate for a list of beat times (see `fit_tempo`)."""

    bpm: float  # candidate tempo: a whole multiple of `step`
    origin_s: float  # grid point nearest 0 s, in [-period/2, period/2): a beat, not a downbeat
    inliers: float  # fraction of input beats within tolerance_s of a grid point
    coverage: float  # fraction of grid points from the first to the last beat with an inlier
    offset_ms: float  # signed median inlier residual (beat - grid) after the origin refinement
    p95_ms: float  # 95th percentile of |inlier residual|
    drift_ms_per_min: float  # inlier residual slope against time; non-zero: not this exact tempo
    free_bpm: float  # least-squares tempo of the inliers (88.002 for an 88 master)


_CLUSTER_GAP = 4  # more missing grid points than this splits inliers into separate runs


def _beat_times(beats_s) -> np.ndarray:
    t = np.asarray(beats_s, dtype=float)
    if t.ndim != 1:
        raise ValueError("beats_s must be a one-dimensional sequence of seconds")
    if len(t) < 8:
        raise ValueError(f"fit_tempo needs at least 8 beats, got {len(t)}")
    if not np.all(np.isfinite(t)):
        raise ValueError("beats_s must be finite")
    if np.any(np.diff(t) <= 0):
        raise ValueError("beats_s must be strictly increasing")
    return t


def _wrap(x: np.ndarray, period: float) -> np.ndarray:
    """x folded into [-period/2, period/2)."""
    return np.mod(x + period / 2, period) - period / 2


def _fit_one(t: np.ndarray, bpm: float, tolerance_s: float) -> TempoFit:
    period = 60.0 / bpm
    # Phase: the densest window of width 2 * tolerance_s among the beats' phases. A circular
    # mean would cancel out when a tracker counts double (half the beats sit half a period
    # away), hiding the slower grid exactly where it matters.
    ph = np.sort(np.mod(t, period))
    ext = np.concatenate([ph, ph + period])
    counts = np.searchsorted(ext, ph + 2 * tolerance_s, side="right") - np.arange(len(ph))
    i = int(np.argmax(counts))
    origin = float(_wrap(np.array(np.median(ext[i : i + min(counts[i], len(ph))])), period))
    inl = np.abs(_wrap(t - origin, period)) <= tolerance_s
    if inl.any():  # one refinement: centre the grid on the inliers
        origin = float(_wrap(np.array(origin + np.median(_wrap(t[inl] - origin, period))), period))
    r = _wrap(t - origin, period)
    inl = np.abs(r) <= tolerance_s
    nan = float("nan")
    if not inl.any():
        return TempoFit(bpm, origin, 0.0, 0.0, nan, nan, nan, nan)
    ti, ri = t[inl], r[inl]
    k = np.floor((ti - origin) / period + 0.5).astype(np.int64)
    first = math.floor((t[0] - origin) / period + 0.5)
    last = math.floor((t[-1] - origin) / period + 0.5)
    coverage = len(np.unique(k)) / (last - first + 1)
    # Residual slope within runs of nearby grid points, pooled: an inexact tempo makes the
    # residuals a sawtooth (each run drifts through the tolerance, the next starts over),
    # so one line through all inliers would mix runs; per-run slopes measure the drift.
    run = np.concatenate([[0], np.cumsum(np.diff(k) > _CLUSTER_GAP + 1)])
    dt = ti.copy()
    dr = ri.copy()
    for j in range(run[-1] + 1):
        m = run == j
        dt[m] -= dt[m].mean()
        dr[m] -= dr[m].mean()
    denom = float(np.sum(dt * dt))
    slope = float(np.sum(dt * dr)) / denom if denom > 0 else nan
    return TempoFit(
        bpm=bpm,
        origin_s=origin,
        inliers=float(inl.mean()),
        coverage=float(coverage),
        offset_ms=float(np.median(ri)) * 1000.0,
        p95_ms=float(np.percentile(np.abs(ri), 95)) * 1000.0,
        drift_ms_per_min=slope * 60_000.0,
        free_bpm=bpm * (1.0 - slope),
    )


def fit_tempo(
    beats_s,
    *,
    bpm_range: tuple[float, float],
    step: float = 1.0,
    tolerance_s: float = 0.03,
    top: int = 5,
) -> list[TempoFit]:
    """Constant-tempo grid candidates for adopted beat times, best first.

    `beats_s` are beat times in seconds from any source (`rhythm.beats`'s `beats_s`, another
    tracker's report, hand taps): finite and strictly increasing, negatives allowed, at least
    8. This fits given numbers; it does not listen to audio. Every tempo that is a whole
    multiple of `step` within `bpm_range` (inclusive, required: the range is a choice) is
    tried: its phase is the densest `2 * tolerance_s` window of the beats' phases, refined
    once by the median inlier residual; a beat is an inlier within `tolerance_s` of a grid point. Candidates are sorted
    by `inliers`, then `coverage`. `step=1.0` encodes the whole-number BPM assumption;
    `step=0.5` or `0.01` relax it.

    The result never chooses a felt tempo or a downbeat. A grid at twice a tempo contains
    every beat of the slower one, so it never scores fewer inliers; `coverage` (grid points
    that have a beat) is how "tracker at 85" (85: coverage ~1) differs from "170 with every
    other point empty" (170: coverage ~0.5). A tracker counting double gives coverage ~1 at
    both, so the work decides from the music. `origin_s` is a beat; a bar line is
    `origin_s + k * 60 / bpm` for a `k` the work picks, and
    `Clock(sample_rate=sr, tempo=fit.bpm, meter=4, start_seconds=that)` is the grid. The
    origin inherits the tracker's placement bias. `drift_ms_per_min` well away from 0 (and
    `free_bpm` away from `bpm`) means the beats follow a nearby, not this exact, tempo.
    """
    t = _beat_times(beats_s)
    lo, hi = (float(v) for v in bpm_range)
    if not (step > 0 and tolerance_s > 0):
        raise ValueError("step and tolerance_s must be positive")
    if not (math.isfinite(lo) and math.isfinite(hi) and 0 < lo <= hi):
        raise ValueError(f"bpm_range must be (low, high) with 0 < low <= high, got {bpm_range}")
    if top < 1:
        raise ValueError(f"top must be at least 1, got {top}")
    ks = range(math.ceil(lo / step - 1e-9), math.floor(hi / step + 1e-9) + 1)
    if len(ks) == 0:
        raise ValueError(f"no multiple of step {step} lies within bpm_range {bpm_range}")
    fits = [_fit_one(t, round(k * step, 9), tolerance_s) for k in ks]
    fits.sort(key=lambda f: (-f.inliers, -f.coverage))
    return fits[:top]


# -- bar-aligned cutting and stretch markers ------------------------------------------------


def segment(audio: np.ndarray, start_frame: int, end_frame: int) -> np.ndarray:
    """Exactly `end_frame - start_frame` frames of `audio`, zero-filled where the range runs
    before frame 0 or past the end. Always a new array; dtype and channels kept. The
    read-side counterpart of `add_at`: `segment(audio, *clock.span(9, 17))`."""
    start, end = int(start_frame), int(end_frame)
    if start != start_frame or end != end_frame:
        raise ValueError("segment needs whole frames; round with frame_of")
    if end <= start:
        raise ValueError(f"end_frame must be after start_frame, got {start}..{end}")
    out = np.zeros((end - start, *audio.shape[1:]), dtype=audio.dtype)
    lo, hi = max(start, 0), min(end, len(audio))
    if hi > lo:
        out[lo - start : hi - start] = audio[lo:hi]
    return out


def warp_markers(
    source: Clock,
    target: Clock,
    first_bar: int,
    end_bar: int,
    *,
    target_bar: int = 1,
    lead_frames: int = 0,
    tail_frames: int = 0,
) -> list[tuple[int, int]]:
    """`(source_frame, output_frame)` pairs for `pytimestretch.time_warp` that put source bar
    lines `first_bar..end_bar` on target bar lines `target_bar..` exactly.

    The audio to warp is `segment(audio, source.frame(first_bar) - lead_frames,
    source.frame(end_bar) + tail_frames)`; frames are relative to that segment's start. The
    pairs start at `(0, 0)` and end at `(len(segment), output length)`, both columns strictly
    increasing Python ints, as `time_warp` requires. The lead and tail (context for the
    engine, such as a pre-roll) map by the tempo ratio of the bar next to them, rounded with
    `frame_of`; output bar line i is `target.frame(target_bar + i) - target.frame(target_bar)`
    plus the mapped lead. Both clocks need the same sample rate. The engine call, pitch and
    backend stay in the work:
    `pytimestretch.time_warp(seg, sr, markers=warp_markers(...), semitones=...)`.
    """
    sr = source.sample_rate
    if target.sample_rate != sr:
        raise ValueError("source and target clocks need the same sample rate")
    if end_bar <= first_bar:
        raise ValueError(f"end_bar must be after first_bar, got {first_bar}..{end_bar}")
    if lead_frames < 0 or tail_frames < 0:
        raise ValueError("lead_frames and tail_frames must not be negative")
    bars = end_bar - first_bar
    start = source.frame(first_bar) - lead_frames
    t0 = target.frame(target_bar)

    def ratio(src_bar: int, tgt_bar: int) -> float:
        src = source.seconds(src_bar + 1) - source.seconds(src_bar)
        return (target.seconds(tgt_bar + 1) - target.seconds(tgt_bar)) / src

    # A frame count scaled by a ratio is rounded by frame_of at a rate of 1 (frames in, frames
    # out), which keeps exact half-frame ties exact instead of passing through seconds.
    lead_out = frame_of(lead_frames * ratio(first_bar, target_bar), 1)
    pairs = [(0, 0)] if lead_frames else []
    for i in range(bars + 1):
        pairs.append(
            (source.frame(first_bar + i) - start, target.frame(target_bar + i) - t0 + lead_out)
        )
    if tail_frames:
        tail_out = frame_of(tail_frames * ratio(end_bar - 1, target_bar + bars - 1), 1)
        src_end, out_end = pairs[-1]
        pairs.append((src_end + tail_frames, out_end + tail_out))
    pairs = [(int(s), int(o)) for s, o in pairs]
    for (s0, o0), (s1, o1) in pairwise(pairs):
        if s1 <= s0 or o1 <= o0:
            raise ValueError(
                f"markers would not strictly increase at ({s0}, {o0}) -> ({s1}, {o1}); "
                "a lead or tail too short to map, or a bar shorter than one frame"
            )
    return pairs


def fold(times_s, *, period_s: float, origin_s: float, steps: int, weights=None) -> np.ndarray:
    """Events folded onto a repeating period: an onset list (or an envelope's frame times
    with `weights`) folded onto the beat or the bar, `steps` bins long.

    Step k covers `[k - 0.5, k + 0.5)` steps after `origin_s` (times before the origin fold
    the same way). Without `weights`, each bin holds its event count; with `weights`, the
    mean weight of its events, 0.0 for an empty bin. Scoring the result (which step is the
    downbeat) belongs to the work."""
    t = np.asarray(times_s, dtype=float).ravel()
    if not (period_s > 0 and math.isfinite(period_s)):
        raise ValueError(f"period_s must be positive, got {period_s}")
    if int(steps) != steps or steps < 1:
        raise ValueError(f"steps must be a positive whole number, got {steps}")
    steps = int(steps)
    if not np.all(np.isfinite(t)):
        raise ValueError("times_s must be finite")
    # floor(x + 0.5): the same tie rule as frame_of (half a step goes to the later bin).
    bins = np.floor((t - origin_s) / period_s * steps + 0.5).astype(np.int64) % steps
    counts = np.bincount(bins, minlength=steps).astype(float)
    if weights is None:
        return counts
    w = np.asarray(weights, dtype=float).ravel()
    if len(w) != len(t):
        raise ValueError("weights must have one value per time")
    sums = np.bincount(bins, weights=w, minlength=steps)
    return np.divide(sums, counts, out=np.zeros(steps), where=counts > 0)


__all__ = [
    "Bar",
    "Clock",
    "Groove",
    "TempoFit",
    "add_at",
    "cycle",
    "envelope_beats",
    "envelope_seconds",
    "euclid",
    "fit_tempo",
    "fold",
    "frame_of",
    "markers",
    "note_seconds",
    "quantize",
    "segment",
    "swing",
    "warp_markers",
]
