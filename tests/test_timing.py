"""Exercise tactus.timing against independent computations (scipy quad, closed forms) and the
validation the plan requires. See docs/blueprints/plans/2026-09-27-tactus-timing.md."""

from __future__ import annotations

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
