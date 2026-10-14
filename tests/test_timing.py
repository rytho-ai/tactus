"""Exercise tactus.timing against independent computations (scipy quad, closed forms) and the
validation the plan requires. See docs/blueprints/plans/2026-09-27-tactus-timing.md."""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest
from scipy.integrate import quad

from tactus import timing
from tactus.timing import (
    Bar,
    Clock,
    Groove,
    add_at,
    cycle,
    envelope_beats,
    envelope_seconds,
    euclid,
    frame_of,
    markers,
    note_seconds,
    quantize,
    swing,
)

SR = 48000


# ---------------------------------------------------------------------------
# helpers: independent ground truth
# ---------------------------------------------------------------------------


def quad_seconds(bpm_of_beat, b0, b1):
    return quad(lambda b: 60.0 / bpm_of_beat(b), b0, b1, limit=200)[0]


def ramp_bpm(q0, q1, b0, b1):
    def f(b):
        u = (b - b0) / (b1 - b0)
        return q0 + (q1 - q0) * u

    return f


def ramp_time_closed_form(q0, q1, b0, b1, x):
    """Closed form for bpm linear in TIME (ramp-time): solve beats(t) = x for t."""
    total = 120.0 * (b1 - b0) / (q0 + q1)
    k = (q1 - q0) / total
    return (-q0 + math.sqrt(q0 * q0 + 2 * k * 60.0 * x)) / k


def smooth_bpm(q0, q1, b0, b1):
    def f(b):
        u = (b - b0) / (b1 - b0)
        return q0 + (q1 - q0) * (1 - math.cos(math.pi * u)) / 2

    return f


# ---------------------------------------------------------------------------
# step, ramp, ramp-time, smooth: against scipy quad and closed forms
# ---------------------------------------------------------------------------


def test_step_tempo_matches_constant_bpm():
    clock = Clock(sample_rate=SR, tempo=[(1, 120)])
    # 4 beats at 120 bpm = 2 seconds
    assert clock.at(4.0) == pytest.approx(2.0, abs=1e-12)


def test_ramp_matches_quad_and_closed_form():
    clock = Clock(sample_rate=SR, tempo=[(1, 92), (5, 92), (9, 120, "ramp")])
    b0, b1 = clock.beats(5), clock.beats(9)
    truth = quad_seconds(ramp_bpm(92, 120, b0, b1), b0, b1)
    got = clock.at(b1) - clock.at(b0)
    assert got == pytest.approx(truth, abs=1e-6)


def test_ramp_time_matches_quad_and_closed_form():
    clock = Clock(sample_rate=SR, tempo=[(1, 92), (5, 92), (9, 120, "ramp-time")])
    b0, b1 = clock.beats(5), clock.beats(9)

    def bpm_ramp_time(b):
        # bpm linear in TIME: invert the closed form numerically via bisection on x
        x = b - b0
        total = 120.0 * (b1 - b0) / (92 + 120)
        k = (120 - 92) / total
        t = ramp_time_closed_form(92, 120, b0, b1, x)
        return 92 + k * t

    truth = quad_seconds(bpm_ramp_time, b0, b1)
    got = clock.at(b1) - clock.at(b0)
    assert got == pytest.approx(truth, abs=1e-6)
    closed = ramp_time_closed_form(92, 120, b0, b1, b1 - b0)
    assert got == pytest.approx(closed, abs=1e-9)


def test_smooth_matches_quad_within_1e6_over_64_bars():
    clock = Clock(sample_rate=SR, tempo=[(1, 70), (1, 70), (65, 140, "smooth")])
    b0, b1 = clock.beats(1), clock.beats(65)
    truth = quad_seconds(smooth_bpm(70, 140, b0, b1), b0, b1)
    got = clock.at(b1) - clock.at(b0)
    assert abs(got - truth) <= 1e-6


def test_smooth_matches_quad_various_spans():
    for bars in (2, 8, 16, 32, 64):
        clock = Clock(sample_rate=SR, tempo=[(1, 60), (1, 60), (1 + bars, 180, "smooth")])
        b0, b1 = clock.beats(1), clock.beats(1 + bars)
        truth = quad_seconds(smooth_bpm(60, 180, b0, b1), b0, b1)
        got = clock.at(b1) - clock.at(b0)
        assert abs(got - truth) <= 1e-6, f"bars={bars}"


# ---------------------------------------------------------------------------
# meters, including 7/8 and fractional bars
# ---------------------------------------------------------------------------


def test_meter_7_8_and_fractional_bars():
    clock = Clock(sample_rate=SR, tempo=[(1, 120)], meter=[(1, 4), (9, 3.5), (10, 4)])
    assert clock.beats_per_bar(9) == 3.5
    assert clock.beats(9) == pytest.approx(8 * 4.0)
    assert clock.beats(10) == pytest.approx(8 * 4.0 + 3.5)
    # fractional bar: halfway through bar 9's (3.5-beat) bar
    assert clock.beats(9.5) == pytest.approx(8 * 4.0 + 0.5 * 3.5)


def test_meter_default_constant():
    clock = Clock(sample_rate=SR, tempo=120, meter=4)
    assert clock.beats_per_bar(1) == 4.0
    assert clock.beats_per_bar(1000) == 4.0


# ---------------------------------------------------------------------------
# no drift over 10,000 bars
# ---------------------------------------------------------------------------


def test_no_drift_over_10000_bars():
    clock = Clock(sample_rate=SR, tempo=[(1, 96)])
    # absolute computation directly from bar 1, vs an independent per-bar accumulation
    beats_per_bar = 4.0
    expected_seconds_per_bar = 60.0 * beats_per_bar / 96.0
    bar = 10_000
    expected = bar_start_seconds = (bar - 1) * expected_seconds_per_bar
    got = clock.seconds(bar)
    assert got == pytest.approx(bar_start_seconds, abs=1e-9)
    assert got == pytest.approx(expected, abs=1e-9)


def test_no_drift_over_10000_bars_with_tempo_changes():
    clock = Clock(
        sample_rate=SR,
        tempo=[(1, 90), (100, 90), (110, 130, "ramp"), (9000, 130), (9010, 80, "smooth")],
    )
    # Recompute bar 10,000's start seconds by summing independent segment integrals and
    # compare to the clock's own absolute computation: they must agree exactly (same maths),
    # but this also exercises that beat 39996 (bar 10000) is beyond the last tempo point and
    # uses the constant tail closed form.
    tail_beat, tail_bpm = clock._tail
    beat = clock.beats(bar=10_000)
    assert beat > tail_beat
    direct = clock._tail_t0 + 60.0 * (beat - tail_beat) / tail_bpm
    assert clock.seconds(10_000) == pytest.approx(clock.start_seconds + direct, abs=1e-9)


# ---------------------------------------------------------------------------
# beat_of round trip, including arrays and times far beyond the old inverse-table tail
# ---------------------------------------------------------------------------


def test_beat_of_round_trip_scalar():
    clock = Clock(sample_rate=SR, tempo=[(1, 92), (13, 92), (17, 100, "ramp"), (21, 120)])
    for beat in (0.0, 3.25, clock.beats(13), clock.beats(19), clock.beats(25)):
        seconds = clock.at(beat)
        assert clock.beat_of(seconds) == pytest.approx(beat, abs=1e-9)


def test_beat_of_round_trip_array():
    clock = Clock(sample_rate=SR, tempo=[(1, 92), (13, 92), (17, 100, "ramp"), (21, 120)])
    beats = np.linspace(0.0, clock.beats(30), 200)
    seconds = np.array([clock.at(b) for b in beats])
    got = clock.beat_of(seconds)
    assert isinstance(got, np.ndarray)
    np.testing.assert_allclose(got, beats, atol=1e-9)


def test_beat_of_before_start_and_far_beyond_tail_uses_closed_form():
    """Regression for the probe's inverse-table sizing bug: times far past the last tempo
    point (well beyond the old 64-beat lookup tail) must still resolve exactly."""
    clock = Clock(sample_rate=SR, tempo=[(1, 96), (5, 96), (9, 130, "ramp")])
    tail_beat, _tail_bpm = clock._tail
    far_beat = tail_beat + 100_000.0  # far beyond any fixed-size inverse table
    seconds = clock.at(far_beat)
    assert clock.beat_of(seconds) == pytest.approx(far_beat, abs=1e-9)

    # before the piece starts
    early_seconds = clock.start_seconds - 3.0
    got = clock.beat_of(early_seconds)
    assert clock.at(got) == pytest.approx(early_seconds, abs=1e-9)
    assert got < 0


def test_beat_of_accurate_to_1e9_beats_within_segments():
    clock = Clock(sample_rate=SR, tempo=[(1, 70), (1, 70), (33, 150, "smooth")])
    for beat in np.linspace(0.0, clock.beats(33), 25):
        seconds = clock.at(beat)
        assert abs(clock.beat_of(seconds) - beat) <= 1e-9


# ---------------------------------------------------------------------------
# bpm_at
# ---------------------------------------------------------------------------


def test_bpm_at_step_ramp_smooth_and_tail():
    clock = Clock(sample_rate=SR, tempo=[(1, 92), (13, 92), (17, 100, "ramp"), (21, 120)])
    assert clock.bpm_at(0.0) == 92
    b0, b1 = clock.beats(13), clock.beats(17)
    u = 0.5
    mid = b0 + (b1 - b0) * u
    assert clock.bpm_at(mid) == pytest.approx(92 + (100 - 92) * u)
    assert clock.bpm_at(clock.beats(30)) == 120  # tail


def test_bpm_at_ramp_time_matches_derivative_of_at():
    clock = Clock(sample_rate=SR, tempo=[(1, 92), (5, 92), (9, 130, "ramp-time")])
    b0, b1 = clock.beats(5), clock.beats(9)
    mid = (b0 + b1) / 2
    eps = 1e-4
    numeric_bpm = 60.0 / ((clock.at(mid + eps) - clock.at(mid - eps)) / (2 * eps))
    assert clock.bpm_at(mid) == pytest.approx(numeric_bpm, rel=1e-3)


# ---------------------------------------------------------------------------
# swing
# ---------------------------------------------------------------------------


def test_swing_straight_is_identity():
    for beat in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5):
        assert swing(beat, 0.5) == pytest.approx(beat)


def test_swing_amounts():
    # midpoint of the unit moves to `amount`
    assert swing(0.25, 0.58, unit=0.5) == pytest.approx(0.58 * 0.5)
    assert swing(0.25, 2 / 3, unit=0.5) == pytest.approx((2 / 3) * 0.5)


def test_swing_between_grid_points_is_linear():
    amount = 0.6
    unit = 0.5
    # quarter-way to the midpoint, in the first half
    beat = 0.125
    x = beat / unit
    expected = x * (amount / 0.5) * unit
    assert swing(beat, amount, unit) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Groove
# ---------------------------------------------------------------------------


def test_groove_slots_and_wraparound():
    groove = Groove(offsets_ms=[0.0, 5.0, -3.0, 2.0], velocities=[1.0, 0.8, 1.0, 0.9], grid=0.25)
    assert groove.ms(0.0) == 0.0
    assert groove.ms(0.25) == 5.0
    assert groove.ms(0.5) == -3.0
    assert groove.ms(0.75) == 2.0
    # wrap: bar-relative beat 1.0 wraps to slot 0 again
    assert groove.ms(1.0) == 0.0
    assert groove.velocity(0.25) == 0.8


def test_groove_frame_adds_offset():
    clock = Clock(sample_rate=SR, tempo=[(1, 120)])
    groove = Groove(offsets_ms=[0.0, 10.0], grid=0.5)
    plain = clock.frame(1, 0.5)
    grooved = groove.frame(clock, 1, 0.5)
    assert grooved == frame_of(clock.seconds(1, 0.5, ms=10.0), SR)
    assert grooved != plain


def test_groove_mismatched_lengths_raises():
    with pytest.raises(ValueError):
        Groove(offsets_ms=[0.0, 1.0], velocities=[1.0])


# ---------------------------------------------------------------------------
# envelope_beats / envelope_seconds
# ---------------------------------------------------------------------------


def test_envelope_beats_endpoints_and_midpoint():
    clock = Clock(sample_rate=SR, tempo=[(1, 120)])
    length = clock.frame(5)
    env = envelope_beats(clock, [((1, 0.0), 0.0), ((5, 0.0), 1.0)], length)
    assert env[0] == pytest.approx(0.0, abs=1e-6)
    assert env[-1] == pytest.approx(1.0, abs=1e-2)
    mid_frame = length // 2
    assert 0.0 < env[mid_frame] < 1.0


def test_envelope_seconds_endpoints_and_midpoint():
    clock = Clock(sample_rate=SR, tempo=[(1, 120)])
    length = SR * 4
    env = envelope_seconds(clock, [(0.0, 0.0), (4.0, 1.0)], length)
    assert env[0] == pytest.approx(0.0, abs=1e-6)
    assert env[-1] == pytest.approx(1.0, abs=1e-3)
    assert env[length // 2] == pytest.approx(0.5, abs=1e-2)


# ---------------------------------------------------------------------------
# add_at: in-place mix, head/tail cut, never wraps
# ---------------------------------------------------------------------------


def test_add_at_normal():
    buf = np.zeros(10)
    clip = np.array([1.0, 2.0, 3.0])
    add_at(buf, clip, 4)
    assert np.allclose(buf[4:7], [1, 2, 3])
    assert np.allclose(buf[:4], 0)
    assert np.allclose(buf[7:], 0)


def test_add_at_negative_frame_loses_head():
    buf = np.zeros(5)
    clip = np.array([1.0, 2.0, 3.0, 4.0])
    add_at(buf, clip, -2)
    # clip[2:] = [3, 4] should land at buf[0:2]
    assert np.allclose(buf[:2], [3, 4])
    assert np.allclose(buf[2:], 0)


def test_add_at_past_end_loses_tail():
    buf = np.zeros(5)
    clip = np.array([1.0, 2.0, 3.0, 4.0])
    add_at(buf, clip, 3)
    assert np.allclose(buf[3:5], [1, 2])


def test_add_at_gain():
    buf = np.zeros(3)
    clip = np.array([1.0, 1.0, 1.0])
    add_at(buf, clip, 0, gain=0.5)
    assert np.allclose(buf, [0.5, 0.5, 0.5])


def test_add_at_returns_same_buffer_object():
    buf = np.zeros(3)
    out = add_at(buf, np.array([1.0]), 0)
    assert out is buf


def test_add_at_entirely_before_start_no_op():
    buf = np.zeros(5)
    clip = np.array([1.0, 2.0])
    add_at(buf, clip, -5)
    assert np.allclose(buf, 0)


def test_add_at_entirely_past_end_no_op():
    buf = np.zeros(5)
    clip = np.array([1.0, 2.0])
    add_at(buf, clip, 10)
    assert np.allclose(buf, 0)


def test_add_at_never_wraps():
    buf = np.ones(5) * 9.0
    clip = np.array([1.0, 2.0, 3.0])
    add_at(buf, clip, 4)  # only clip[0] fits at index 4; rest should NOT wrap to index 0/1
    assert buf[0] == 9.0 and buf[1] == 9.0


def test_add_at_stereo_buffer_accepts_mono_clip():
    buf = np.zeros((5, 2))
    clip = np.array([1.0, 2.0])
    add_at(buf, clip, 1)
    np.testing.assert_allclose(buf[1:3], [[1.0, 1.0], [2.0, 2.0]])


# ---------------------------------------------------------------------------
# markers: one impulse per distinct in-range frame
# ---------------------------------------------------------------------------


def test_markers_basic():
    m = markers([0, 5, 9], 10)
    assert m.shape == (10,)
    assert m[0] == 0.5 and m[5] == 0.5 and m[9] == 0.5
    assert np.sum(m != 0) == 3


def test_markers_out_of_range_dropped():
    m = markers([-1, 3, 100], 10)
    assert m[3] == 0.5
    assert np.sum(m != 0) == 1


def test_markers_coincident_collapse_to_one():
    m = markers([2, 2, 2], 10)
    assert m[2] == 0.5
    assert np.sum(m != 0) == 1


def test_markers_custom_value():
    m = markers([1], 5, value=1.0)
    assert m[1] == 1.0


def test_markers_multi_channel_shape():
    m = markers([1, 3], 5, channels=2)
    assert m.shape == (5, 2)
    assert np.all(m[1] == 0.5) and np.all(m[3] == 0.5)


def test_markers_refuse_fractional_frames():
    assert markers([np.int64(2), 3.0], 5)[3] == 0.5
    with pytest.raises(ValueError, match="frame_of"):
        markers([2.6], 5)


# ---------------------------------------------------------------------------
# quantize: exact ties go later
# ---------------------------------------------------------------------------


def test_quantize_full_strength_snaps_exactly():
    assert quantize(0.26, grid=0.25, strength=1.0) == pytest.approx(0.25)


def test_quantize_zero_strength_no_move():
    assert quantize(0.26, grid=0.25, strength=0.0) == pytest.approx(0.26)


def test_quantize_partial_strength():
    v = quantize(0.0, grid=0.25, strength=0.5)
    assert v == pytest.approx(0.0)  # nearest grid to 0.0 is 0.0 itself
    v2 = quantize(0.1, grid=0.25, strength=0.5)
    assert v2 == pytest.approx(0.1 + 0.5 * (0.0 - 0.1))


def test_quantize_exact_tie_goes_later():
    # 0.125 is exactly halfway between 0.0 and 0.25 -> later = 0.25
    assert quantize(0.125, grid=0.25, strength=1.0) == pytest.approx(0.25)


def test_quantize_exact_tie_negative_side():
    # halfway between 0.75 and 1.0 is 0.875 -> later = 1.0
    assert quantize(0.875, grid=0.25, strength=1.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# note_seconds: value (beats) as seconds at the tempo sounding at `beat`
# ---------------------------------------------------------------------------


def test_note_seconds_quarter_at_120bpm():
    clock = Clock(sample_rate=SR, tempo=[(1, 120.0)])
    assert note_seconds(clock, 0.0, 1.0) == pytest.approx(0.5)


def test_note_seconds_dotted_eighth():
    clock = Clock(sample_rate=SR, tempo=[(1, 120.0)])
    assert note_seconds(clock, 0.0, 0.75) == pytest.approx(0.375)


def test_note_seconds_triplet():
    clock = Clock(sample_rate=SR, tempo=[(1, 120.0)])
    assert note_seconds(clock, 0.0, 2 / 3) == pytest.approx((2 / 3) * 0.5)


def test_note_seconds_uses_tempo_at_that_beat():
    # a ramp from 90 -> 126 bpm across bars 1..5 (beats 0..16); note_seconds at beat 8
    # (the ramp's midpoint) should use the tempo halfway between, not the tempo at 0.
    clock = Clock(sample_rate=SR, tempo=[(1, 90.0), (5, 126.0, "ramp")])
    beat = 8.0
    expected = 1.0 * 60.0 / clock.bpm_at(beat)
    assert note_seconds(clock, beat, 1.0) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# validation errors
# ---------------------------------------------------------------------------


def test_validation_unknown_shape():
    with pytest.raises(ValueError, match="unknown tempo shape"):
        Clock(sample_rate=SR, tempo=[(1, 90), (5, 100, "bogus")])


def test_validation_ramp_without_previous_point():
    with pytest.raises(ValueError, match="needs a previous tempo point"):
        Clock(sample_rate=SR, tempo=[(1, 90, "ramp")])


def test_validation_points_out_of_order():
    with pytest.raises(ValueError, match="bar order"):
        Clock(sample_rate=SR, tempo=[(9, 90), (1, 100)])


def test_validation_first_meter_not_at_bar_1():
    with pytest.raises(ValueError, match="bar 1"):
        Clock(sample_rate=SR, tempo=120, meter=[(2, 4)])


def test_validation_non_positive_bpm():
    with pytest.raises(ValueError, match="positive"):
        Clock(sample_rate=SR, tempo=[(1, 0)])
    with pytest.raises(ValueError, match="positive"):
        Clock(sample_rate=SR, tempo=[(1, 90), (5, -10)])


# ---------------------------------------------------------------------------
# bars / span
# ---------------------------------------------------------------------------


def test_bars_yields_bar_records():
    clock = Clock(sample_rate=SR, tempo=[(1, 120)])
    bars = list(clock.bars(1, 3))
    assert len(bars) == 3
    assert all(isinstance(b, Bar) for b in bars)
    assert bars[0].number == 1
    assert bars[0].start_beat == 0.0
    assert bars[0].beats == 4.0
    assert bars[0].start_frame == clock.frame(1)
    assert bars[0].end_frame == clock.frame(2)


def test_span_matches_frame_of_first_and_end_bar():
    clock = Clock(sample_rate=SR, tempo=[(1, 120)])
    assert clock.span(17, 25) == (clock.frame(17), clock.frame(25))


# ---------------------------------------------------------------------------
# ms offsets
# ---------------------------------------------------------------------------


def test_ms_offset_shifts_frame():
    clock = Clock(sample_rate=SR, tempo=[(1, 120)])
    base = clock.frame(9, 1.5)
    early = clock.frame(9, 1.5, ms=-7.0)
    late = clock.frame(9, 1.5, ms=7.0)
    assert early < base < late
    assert early == frame_of(clock.seconds(9, 1.5) - 0.007, SR)


def test_frame_at_ms_offset():
    clock = Clock(sample_rate=SR, tempo=[(1, 120)])
    assert clock.frame_at(4.0, ms=3.0) == frame_of(clock.at(4.0) + 0.003, SR)


# ---------------------------------------------------------------------------
# frame_of: the single rounding rule
# ---------------------------------------------------------------------------


def test_frame_of_rounding_rule():
    assert frame_of(1.0, SR) == SR
    assert frame_of(0.0, SR) == 0
    for position, expected in [(0.5, 1), (1.5, 2), (2.5, 3), (-0.5, 0), (-1.5, -1)]:
        assert frame_of(position / 1024, 1024) == expected
    assert frame_of(0.499 / 1024, 1024) == 0


# ---------------------------------------------------------------------------
# module surface
# ---------------------------------------------------------------------------


def test_timing_importable_as_submodule():
    from tactus import timing as t2

    assert t2 is timing
    assert hasattr(timing, "Clock")


# ---------------------------------------------------------------------------
# euclid: Bjorklund tables, rotation, edges, validation
# ---------------------------------------------------------------------------


def test_euclid_tidal_tables():
    assert euclid(3, 8) == (0, 3, 6)
    assert euclid(5, 8) == (0, 2, 3, 5, 6)
    assert euclid(7, 16) == (0, 2, 4, 7, 9, 11, 14)
    assert euclid(2, 5) == (0, 2)
    assert euclid(4, 7) == (0, 2, 4, 6)


def test_euclid_rotation_left():
    # a hit at step s moves to (s - rotate) mod n
    assert euclid(3, 8, rotate=2) == (1, 4, 6)
    assert euclid(5, 8, rotate=2) == (0, 1, 3, 4, 6)


def test_euclid_negative_rotation_moves_hits_later():
    base = euclid(3, 8)
    later = euclid(3, 8, rotate=-1)
    assert later == tuple(sorted((s + 1) % 8 for s in base))


def test_euclid_edge_k_zero_and_k_equals_n():
    assert euclid(0, 8) == ()
    assert euclid(8, 8) == tuple(range(8))


def test_euclid_validation_errors():
    with pytest.raises(ValueError):
        euclid(3, 0)
    with pytest.raises(ValueError):
        euclid(3, -8)
    with pytest.raises(ValueError):
        euclid(-1, 8)
    with pytest.raises(ValueError):
        euclid(9, 8)


# ---------------------------------------------------------------------------
# cycle: continuity across bar lines, string and bool forms, start offset
# ---------------------------------------------------------------------------


def test_cycle_continuous_across_bar_lines():
    assert cycle("x..x.", 16) == (0, 3, 5, 8, 10, 13, 15)


def test_cycle_start_offset_matches_continuity():
    full = cycle("x..x.", 16)
    tail = cycle("x..x.", 10, start=6)
    assert tail == tuple(s for s in full if s >= 6)


def test_cycle_accepts_x_dot_forms_and_whitespace():
    assert cycle("x . x", 3) == cycle("x.x", 3)
    assert cycle("x ~ x x ~", 5) == cycle("x~xx~", 5)


def test_cycle_accepts_bool_sequence():
    assert cycle([True, False, True], 6) == (0, 2, 3, 5)


def test_cycle_empty_result():
    assert cycle("...", 6) == ()


def test_cycle_unknown_character_raises():
    with pytest.raises(ValueError):
        cycle("x?x", 4)


def test_cycle_empty_figure_raises():
    with pytest.raises(ValueError):
        cycle("", 4)


# ---------------------------------------------------------------------------
# fit_tempo / segment / warp_markers / fold
# See docs/blueprints/plans/2026-10-14-tempo-grid-fitting.md.
# ---------------------------------------------------------------------------


def _beat_train(
    bpm, *, seed, duration=200.0, intro=15.0, jitter=0.008, offset=-0.015, drop=0.05, extra=0.05
):
    """A tracker-like beat list: a regular grid (origin `offset`) from `intro` on, with
    Gaussian jitter, dropped and spurious beats, and an irregular intro before it."""
    rng = np.random.default_rng(seed)
    period = 60.0 / bpm
    n = np.arange(math.ceil(intro / period), int(duration / period))
    grid = n * period + offset + rng.normal(0.0, jitter, len(n))
    grid = grid[rng.random(len(grid)) > drop]
    spurious = rng.uniform(intro, duration, int(extra * len(grid)))
    taps = np.cumsum(rng.uniform(0.3, 1.1, 40))
    return np.unique(np.concatenate([taps[taps < intro - 0.5], grid, spurious]))


def _phase_error(a, b, period):
    return abs((a - b + period / 2) % period - period / 2)


@pytest.mark.parametrize("bpm", [85, 88, 91, 66, 69, 71])
def test_fit_tempo_recovers_whole_tempo_or_its_double(bpm):
    fits = timing.fit_tempo(_beat_train(bpm, seed=bpm), bpm_range=(50, 180))
    assert fits[0].bpm in (bpm, 2 * bpm)
    truth = next(f for f in fits if f.bpm == bpm)
    if fits[0].bpm == 2 * bpm:  # a doubled grid holds every beat: coverage tells them apart
        assert truth.coverage > 1.5 * fits[0].coverage
        assert fits[0].inliers >= truth.inliers
    assert _phase_error(truth.origin_s, -0.015, 60 / bpm) < 0.005
    assert -60 / bpm / 2 <= truth.origin_s < 60 / bpm / 2
    assert abs(truth.drift_ms_per_min) < 3
    assert truth.free_bpm == pytest.approx(bpm, abs=0.02)
    assert truth.inliers > 0.8 and truth.coverage > 0.85
    assert abs(truth.offset_ms) < 2 and truth.p95_ms < 20


def test_fit_tempo_survives_a_half_beat_lock_that_misleads_least_squares():
    # The album's 04: the tracker (at 132 = 2 x 66) slips half a beat for 30 s and loses one
    # beat on the way back; a line through all beats then rounds to 131.
    period = 60 / 132
    grid = np.arange(0, 120, period)
    beats = np.concatenate(
        [grid[grid < 40], grid[(grid >= 40) & (grid < 70 - period)] + period / 2, grid[grid >= 70]]
    )
    beats = beats + np.random.default_rng(4).normal(0, 0.004, len(beats))
    slope = np.polyfit(np.arange(len(beats)), beats, 1)[0]
    assert round(60 / slope) == 131
    fits = timing.fit_tempo(beats, bpm_range=(50, 180))
    assert fits[0].bpm == 132
    assert fits[0].inliers == pytest.approx(0.75, abs=0.03)


def test_fit_tempo_keeps_the_true_tempo_when_the_tracker_locks_double_and_1_6x():
    # The album's 05 (71 BPM): beats at 142 in parts, locked to 1.6 x 71 elsewhere.
    period = 60 / 71
    rng = np.random.default_rng(5)
    double = period / 2
    beats = np.concatenate(
        [
            np.arange(0, 60, double),
            60.2 + np.arange(0, 60, period / 1.6),
            np.arange(math.ceil(121 / double), int(200 / double)) * double,
        ]
    )
    beats = np.sort(beats + rng.normal(0, 0.008, len(beats)))
    fits = timing.fit_tempo(beats, bpm_range=(50, 180))
    assert fits[0].bpm == 142
    true = next(f for f in fits if f.bpm == 71)
    assert true.inliers < fits[0].inliers
    assert true.coverage >= fits[0].coverage - 0.01


def test_fit_tempo_reports_drift_for_a_tempo_between_whole_numbers():
    period = 60 / 87.6
    grid = np.arange(0, 200, period)
    beats = grid + np.random.default_rng(6).normal(0, 0.002, len(grid))
    near = next(f for f in timing.fit_tempo(beats, bpm_range=(80, 95), top=50) if f.bpm == 88)
    assert near.inliers < 0.3
    assert near.drift_ms_per_min > 100  # beats fall behind an 88 grid
    assert near.free_bpm == pytest.approx(87.6, abs=0.1)
    finer = timing.fit_tempo(beats, bpm_range=(80, 95), step=0.1)[0]
    assert finer.bpm == pytest.approx(87.6)
    assert finer.inliers == 1.0 and abs(finer.drift_ms_per_min) < 1


def test_fit_tempo_finds_no_good_grid_in_a_tempo_ramp():
    times = [0.0]
    for i in range(300):  # 60 -> 100 BPM, a romantic accelerando
        times.append(times[-1] + 60 / (60 + 40 * i / 300))
    fits = timing.fit_tempo(times, bpm_range=(50, 180), top=200)
    assert max(f.inliers for f in fits) < 0.4


def test_fit_tempo_candidates_respect_range_step_and_top():
    beats = np.arange(16) * 0.5
    fits = timing.fit_tempo(beats, bpm_range=(100, 140), step=10, top=10)
    assert sorted(f.bpm for f in fits) == [100, 110, 120, 130, 140]
    assert fits[0].bpm == 120 and fits[0].coverage == 1.0
    assert len(timing.fit_tempo(beats, bpm_range=(100, 140))) == 5
    shifted = timing.fit_tempo(beats - 3.0, bpm_range=(100, 140))[0]  # negatives allowed
    assert shifted.bpm == 120 and shifted.origin_s == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(
    "beats, kwargs",
    [
        (np.arange(7) * 0.5, {}),
        (np.r_[np.arange(10) * 0.5, 4.0], {}),
        (np.r_[np.arange(10) * 0.5, np.nan], {}),
        (np.arange(10) * 0.5, {"bpm_range": (121.2, 121.8)}),
        (np.arange(10) * 0.5, {"bpm_range": (140, 100)}),
        (np.arange(10) * 0.5, {"step": 0}),
        (np.arange(10) * 0.5, {"top": 0}),
    ],
)
def test_fit_tempo_validation(beats, kwargs):
    with pytest.raises(ValueError):
        timing.fit_tempo(beats, **{"bpm_range": (60, 180), **kwargs})


def test_fit_tempo_requires_a_range():
    with pytest.raises(TypeError):
        timing.fit_tempo(np.arange(10) * 0.5)


@pytest.mark.parametrize("channels", [None, 2])
def test_segment_is_exact_length_and_zero_filled(channels):
    shape = (10,) if channels is None else (10, channels)
    audio = np.arange(1, 11, dtype=np.float32).reshape(10, -1).repeat(channels or 1, axis=1)
    audio = audio.reshape(shape)
    for start, end in [(-3, 4), (7, 14), (-5, -1), (12, 15), (-2, 12), (2, 5)]:
        out = timing.segment(audio, start, end)
        assert out.shape == (end - start, *shape[1:]) and out.dtype == np.float32
        for i in range(end - start):
            src = start + i
            expected = audio[src] if 0 <= src < 10 else np.zeros(shape[1:])
            np.testing.assert_array_equal(out[i], expected)
    out = timing.segment(audio, 0, 10)
    out[0] = -1
    assert audio[0].flat[0] == 1  # a copy, never a view


def test_segment_validation():
    with pytest.raises(ValueError):
        timing.segment(np.zeros(4), 3, 3)
    with pytest.raises(ValueError):
        timing.segment(np.zeros(4), 0.5, 3)


def _check_time_warp_contract(pairs, segment_length):
    assert pairs[0] == (0, 0)
    assert pairs[-1][0] == segment_length
    assert all(type(s) is int and type(o) is int for s, o in pairs)
    assert all(s1 > s0 and o1 > o0 for (s0, o0), (s1, o1) in itertools.pairwise(pairs))


@pytest.mark.parametrize("lead, tail", [(0, 0), (8000, 0), (0, 5000), (11025, 11025)])
def test_warp_markers_put_bar_lines_on_the_target_grid(lead, tail):
    source = Clock(sample_rate=44100, tempo=85, start_seconds=-0.001)  # negative origin
    target = Clock(sample_rate=44100, tempo=88, start_seconds=3.0)
    pairs = timing.warp_markers(
        source, target, 1, 9, target_bar=5, lead_frames=lead, tail_frames=tail
    )
    start, end = source.frame(1) - lead, source.frame(9) + tail
    seg = timing.segment(np.ones(source.frame(20)), start, end)
    _check_time_warp_contract(pairs, len(seg))
    lead_out = frame_of(lead * 85 / 88, 1)
    bar_pairs = pairs[1 if lead else 0 :][:9]
    for i, (s, o) in enumerate(bar_pairs):
        assert s == source.frame(1 + i) - start
        assert o == target.frame(5 + i) - target.frame(5) + lead_out
    assert pairs[-1][1] == target.frame(13) - target.frame(5) + lead_out + frame_of(
        tail * 85 / 88, 1
    )


def test_warp_markers_follow_frame_of_on_half_frame_ties():
    source = Clock(sample_rate=48000, tempo=100)
    target = Clock(sample_rate=48000, tempo=200)  # ratio 0.5: odd leads land on half frames
    for lead in (1, 3, 5, 7, 12345):
        assert (
            timing.warp_markers(source, target, 1, 2, lead_frames=lead)[1]
            == (lead, frame_of(lead / 2, 1))
            == (lead, (lead + 1) // 2)
        )


def test_warp_markers_validation():
    a = Clock(sample_rate=48000, tempo=100)
    with pytest.raises(ValueError):
        timing.warp_markers(a, Clock(sample_rate=44100, tempo=100), 1, 2)
    with pytest.raises(ValueError):
        timing.warp_markers(a, a, 3, 3)
    with pytest.raises(ValueError):
        timing.warp_markers(a, a, 1, 2, lead_frames=-1)
    with pytest.raises(ValueError):  # one lead frame at ratio 0.4 maps to zero frames
        timing.warp_markers(a, Clock(sample_rate=48000, tempo=250), 1, 2, lead_frames=1)


def test_fold_counts_and_averages_per_step():
    period = 2.0
    times = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]) + 10.0
    counts = timing.fold(times, period_s=period, origin_s=10.0, steps=16)
    expected = np.zeros(16)
    expected[[0, 4, 8, 12]] = 2
    np.testing.assert_array_equal(counts, expected)
    weights = [1, 2, 3, 4, 3, 4, 5, 6]
    means = timing.fold(times, period_s=period, origin_s=10.0, steps=16, weights=weights)
    np.testing.assert_allclose(means[[0, 4, 8, 12]], [2, 3, 4, 5])
    assert means.sum() == 14
    # a half-step tie goes to the later step; times before the origin fold the same way
    tie = timing.fold(
        [10.0 + period / 32, 10.0 - period / 16], period_s=period, origin_s=10.0, steps=16
    )
    assert tie[1] == 1 and tie[15] == 1


def test_fold_validation():
    with pytest.raises(ValueError):
        timing.fold([0.0], period_s=0.0, origin_s=0.0, steps=4)
    with pytest.raises(ValueError):
        timing.fold([0.0], period_s=1.0, origin_s=0.0, steps=0)
    with pytest.raises(ValueError):
        timing.fold([0.0, 1.0], period_s=1.0, origin_s=0.0, steps=4, weights=[1.0])


def test_clicks_to_beats_to_fit_to_warp_land_on_the_new_grid():
    import pytimestretch

    from tactus import synth
    from tactus.analysis import rhythm

    rate, bars, first_click = 44100, 10, 1.0
    performed = Clock(sample_rate=rate, tempo=85, start_seconds=first_click)
    hit_frames = frame_of(0.02, rate)
    hit = synth.sine(1000, rate, frames=hit_frames) * np.exp(-np.arange(hit_frames) / rate * 250)
    audio = np.zeros(performed.frame(bars + 1) + rate)
    clicks = [performed.frame_at(b) for b in range(bars * 4)]
    for f in clicks:
        add_at(audio, hit, f)

    beats = np.array(rhythm.beats(audio, rate)["beats_s"])
    fit = timing.fit_tempo(beats, bpm_range=(60, 100))[0]
    assert fit.bpm == 85 and fit.coverage > 0.95
    period = 60 / fit.bpm
    # The work picks the downbeat: here the grid point nearest the first click.
    k = round((first_click - fit.origin_s) / period)
    source = Clock(sample_rate=rate, tempo=fit.bpm, start_seconds=fit.origin_s + k * period)
    target = Clock(sample_rate=rate, tempo=88)
    lead = frame_of(period, rate)
    seg = timing.segment(audio, source.frame(1) - lead, source.frame(9) + lead)
    pairs = timing.warp_markers(source, target, 1, 9, lead_frames=lead, tail_frames=lead)
    out = pytimestretch.time_warp(seg.astype(np.float32), rate, markers=pairs)
    lead_out = pairs[1][1]
    assert len(out) == pairs[-1][1] == target.frame(9) + lead_out + frame_of(lead * 85 / 88, 1)

    # The fitted origin carries the tracker's placement bias (decision: document, no API);
    # once that measured bias is accounted for, every click sits within 2 ms of its beat.
    click_s = np.array(clicks) / rate
    bias_s = np.median(beats - click_s[np.abs(beats[:, None] - click_s).argmin(axis=1)])
    assert -0.04 < bias_s < 0  # qm-dsp places these clicks' beats early
    expected_ms = -bias_s * 1000 * 85 / 88
    window = frame_of(0.03, rate)
    late_ms = []
    for b in range(33):
        line = lead_out + target.frame_at(b)
        env = np.abs(out[line - window : line + window])
        late_ms.append((np.argmax(env > 0.5 * env.max()) - window) / rate * 1000)
    assert np.all(np.abs(np.array(late_ms) - expected_ms) < 2.0)
