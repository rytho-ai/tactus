"""Reusable DSP components: LR4 crossover and fixed-head crossfade delay."""

import math

import numpy as np
import pytest
from scipy.signal import butter, lfilter

from tactus import dsp


def reference_crossfade_delay(
    audio,
    sample_rate,
    *,
    delay_seconds,
    feedback=0.35,
    tail_seconds=0.0,
    crossfade_seconds=0.05,
):
    x = np.asarray(audio, dtype=np.float64)
    mono = x.ndim == 1
    frames = x[:, None] if mono else x
    total = len(x) + round(tail_seconds * sample_rate)
    result = np.zeros((total, frames.shape[1]))
    stored = np.zeros_like(result)
    if not len(x):
        return result[:, 0] if mono else result
    delays = np.asarray(delay_seconds, dtype=np.float64) * sample_rate
    delays = np.broadcast_to(delays, (len(x),))
    fade_samples = max(1, round(crossfade_seconds * sample_rate))
    current = delays[0]
    old = current
    new = current
    fade_index = 0
    fading = False

    def read(i, distance):
        wet = np.zeros(frames.shape[1])
        position = i - distance
        left = math.floor(position)
        fraction = position - left
        if 0 <= left < i:
            wet += (1 - fraction) * stored[left]
        if 0 <= left + 1 < i:
            wet += fraction * stored[left + 1]
        return wet

    for i in range(total):
        requested = delays[min(i, len(x) - 1)]
        if not fading and requested != current:
            old = current
            new = requested
            fade_index = 0
            fading = True

        if fading:
            fade_index += 1
            weight = fade_index / fade_samples
            result[i] = (1 - weight) * read(i, old) + weight * read(i, new)
            if fade_index == fade_samples:
                current = new
                fading = False
        else:
            result[i] = read(i, current)

        stored[i] = (frames[i] if i < len(x) else 0) + feedback * result[i]
        if not fading:
            current = new
    return result[:, 0] if mono else result


def reference_lr4_response(sample_rate, cutoff_hz, frequencies):
    r = np.tan(np.pi * frequencies / sample_rate) / np.tan(np.pi * cutoff_hz / sample_rate)
    denominator = 1 - r * r + 1j * np.sqrt(2) * r
    low = (1 / denominator) ** 2
    high = ((-r * r) / denominator) ** 2
    return low, high


@pytest.mark.parametrize("rate,cutoff", [(32000, 600), (44100, 1000), (96000, 5000)])
def test_crossover_lr4_response_flat_sum_cutoff_and_phase(rate, cutoff):
    impulse = np.r_[1.0, np.zeros(32767)]
    low, high = dsp.crossover(impulse, rate, cutoff_hz=cutoff)
    spectrum = np.fft.rfft(low + high)
    freqs = np.fft.rfftfreq(len(impulse), 1 / rate)
    valid = (freqs > 20) & (freqs < rate / 2 * 0.95)
    db = 20 * np.log10(np.maximum(abs(spectrum[valid]), 1e-300))
    assert db.max() - db.min() < 0.01

    bin_at_cutoff = np.argmin(abs(freqs - cutoff))
    low_db = 20 * np.log10(abs(np.fft.rfft(low)[bin_at_cutoff]))
    high_db = 20 * np.log10(abs(np.fft.rfft(high)[bin_at_cutoff]))
    assert low_db == pytest.approx(-6.02, abs=0.04)
    assert high_db == pytest.approx(-6.02, abs=0.04)
    assert not np.allclose(low + high, impulse, atol=1e-6)

    ref_low, ref_high = reference_lr4_response(rate, cutoff, freqs[valid])
    np.testing.assert_allclose(np.fft.rfft(low)[valid], ref_low, atol=2e-8)
    np.testing.assert_allclose(np.fft.rfft(high)[valid], ref_high, atol=2e-8)


def test_crossover_layout_channel_isolation_empty_and_nonmutation():
    x = np.zeros((128, 2), dtype=np.float32)
    x[0, 0] = 1
    original = x.copy()
    low, high = dsp.crossover(x, 48000, cutoff_hz=1200)
    assert low.shape == x.shape and high.shape == x.shape
    assert low.dtype == np.float64 and high.dtype == np.float64
    np.testing.assert_array_equal(low[:, 1], 0)
    np.testing.assert_array_equal(high[:, 1], 0)
    np.testing.assert_array_equal(x, original)
    empty_low, empty_high = dsp.crossover(x[:0], 48000, cutoff_hz=1200)
    assert empty_low.shape == (0, 2)
    assert empty_high.shape == (0, 2)


def test_crossover_matches_independent_cascaded_butterworth():
    x = np.random.default_rng(248).normal(0, 0.2, (4096, 3))
    low, high = dsp.crossover(x, 44100, cutoff_hz=1700)
    low_b, low_a = butter(2, 1700, fs=44100, btype="lowpass")
    high_b, high_a = butter(2, 1700, fs=44100, btype="highpass")
    np.testing.assert_allclose(low, lfilter(low_b, low_a, lfilter(low_b, low_a, x, axis=0), axis=0))
    np.testing.assert_allclose(
        high, lfilter(high_b, high_a, lfilter(high_b, high_a, x, axis=0), axis=0)
    )


def test_crossfade_delay_scalar_matches_existing_delay():
    x = np.random.default_rng(75).normal(0, 0.2, (300, 2))
    got = dsp.crossfade_delay(
        x, 48000, delay_seconds=3.25 / 48000, feedback=-0.4, tail_seconds=0.002
    )
    expected = dsp.delay(x, 48000, delay_seconds=3.25 / 48000, feedback=-0.4, tail_seconds=0.002)
    np.testing.assert_allclose(got, expected, atol=1e-14)


def test_crossfade_delay_modulation_matches_full_history_oracle_and_layouts():
    rng = np.random.default_rng(102)
    x = rng.normal(0, 0.2, (80, 5))[::2, ::2]
    control = np.full(len(x), 3.25) / 48000
    control[5:] = 8.5 / 48000
    control[9:] = 2.0 / 48000
    control[10:] = 12.25 / 48000
    control[20:] = 4.75 / 48000
    control.setflags(write=False)
    got = dsp.crossfade_delay(
        x,
        48000,
        delay_seconds=control,
        feedback=0.35,
        tail_seconds=0.001,
        crossfade_seconds=4 / 48000,
    )
    expected = reference_crossfade_delay(
        x,
        48000,
        delay_seconds=control,
        feedback=0.35,
        tail_seconds=0.001,
        crossfade_seconds=4 / 48000,
    )
    np.testing.assert_allclose(got, expected, atol=1e-14)
    mono = x[:, 0]
    np.testing.assert_allclose(
        dsp.crossfade_delay(mono, 48000, delay_seconds=control, crossfade_seconds=4 / 48000),
        reference_crossfade_delay(mono, 48000, delay_seconds=control, crossfade_seconds=4 / 48000),
        atol=1e-14,
    )


def test_crossfade_delay_first_fractional_tap_and_signed_feedback_tail():
    x = np.r_[2.0, np.zeros(12)]
    got = dsp.crossfade_delay(x, 1000, delay_seconds=1.25 / 1000, feedback=-0.5, tail_seconds=0.01)
    expected = reference_crossfade_delay(
        x, 1000, delay_seconds=1.25 / 1000, feedback=-0.5, tail_seconds=0.01
    )
    np.testing.assert_allclose(got, expected, atol=1e-14)
    assert got[0] == 0
    np.testing.assert_allclose(got[1], 1.5)
    assert np.any(got[13:] < 0)


def test_crossfade_delay_known_step_endpoints_and_latest_request_policy():
    x = np.arange(20.0)
    control = np.full(len(x), 1.0)
    control[5:] = 5.0
    control[6:] = 7.0
    control[7:] = 3.0
    control[8:] = 3.0
    got = dsp.crossfade_delay(
        x, 1000, delay_seconds=control / 1000, feedback=0, crossfade_seconds=0.003
    )
    expected = reference_crossfade_delay(
        x, 1000, delay_seconds=control / 1000, feedback=0, crossfade_seconds=0.003
    )
    np.testing.assert_allclose(got, expected, atol=1e-14)
    np.testing.assert_allclose(got[5:8], [8 / 3, 7 / 3, 2])
    assert got[8] == pytest.approx(11 / 3)


def test_crossfade_delay_uses_fresh_request_only_after_fade_completion():
    x = np.arange(12.0)
    control = np.full(len(x), 1.0)
    control[3:] = 5.0
    control[4:6] = 2.0
    got = dsp.crossfade_delay(
        x, 1000, delay_seconds=control / 1000, feedback=0, crossfade_seconds=0.003
    )
    expected = reference_crossfade_delay(
        x, 1000, delay_seconds=control / 1000, feedback=0, crossfade_seconds=0.003
    )
    np.testing.assert_allclose(got, expected, atol=1e-14)
    assert got[6] == pytest.approx(1)


def test_crossfade_delay_regression_does_not_reuse_stale_midfade_request():
    x = np.arange(20.0)
    control = np.full(20, 2.0)
    control[4:8] = 4.0
    control[6:8] = 3.0
    control[8:] = 5.0
    y = dsp.crossfade_delay(x, 10, delay_seconds=control / 10, feedback=0, crossfade_seconds=0.4)
    assert y[8] == pytest.approx(3.75)


def test_crossfade_delay_huge_unreachable_delay_empty_one_frame_and_reset():
    huge = dsp.crossfade_delay(np.ones((2, 3)), 48000, delay_seconds=1e300)
    np.testing.assert_array_equal(huge, np.zeros((2, 3)))
    tail = dsp.crossfade_delay(
        np.ones((0, 2)), 48000, delay_seconds=np.empty(0), tail_seconds=0.001
    )
    assert tail.shape == (48, 2)
    assert not tail.any()
    one = dsp.crossfade_delay(np.array([1.0]), 1000, delay_seconds=0.001, tail_seconds=0.002)
    assert one.shape == (3,)
    np.testing.assert_array_equal(
        dsp.crossfade_delay(np.ones(8), 1000, delay_seconds=np.linspace(1, 4, 8) / 1000),
        dsp.crossfade_delay(np.ones(8), 1000, delay_seconds=np.linspace(1, 4, 8) / 1000),
    )


def test_crossfade_delay_transition_has_fixed_carriers_but_can_cancel():
    sr = 48000
    frequency = 997
    fade = round(0.05 * sr)
    step = 20000
    t = np.arange(40000) / sr
    x = np.sin(2 * np.pi * frequency * t)
    control = np.full(len(x), 0.125)
    control[step:] = 0.25
    y = dsp.crossfade_delay(x, sr, delay_seconds=control, feedback=0, crossfade_seconds=0.05)
    transition = y[step : step + fade]
    phase = 2 * np.pi * frequency * np.arange(step, step + fade) / sr
    ramp = np.arange(1, fade + 1) / fade
    basis = np.column_stack(
        [np.sin(phase), np.cos(phase), ramp * np.sin(phase), ramp * np.cos(phase)]
    )
    fit, *_ = np.linalg.lstsq(basis, transition, rcond=None)
    residual = transition - basis @ fit
    assert np.sqrt(np.mean(residual**2)) < 1e-8

    t = np.arange(sr // 4) / sr
    dry = np.sin(2 * np.pi * 1000 * t)
    control = np.full(len(dry), 24 / sr)
    control[2000:] = 48 / sr
    cancel = dsp.crossfade_delay(
        dry,
        sr,
        delay_seconds=control,
        feedback=0,
        crossfade_seconds=0.05,
    )
    center = 2000 + round(0.025 * sr)
    window = cancel[center - 48 : center + 48]
    assert (
        np.sqrt(np.mean(window**2)) / np.sqrt(np.mean(dry[center - 48 : center + 48] ** 2)) < 0.05
    )


@pytest.mark.parametrize(
    "call",
    [
        lambda: dsp.crossover(np.ones(8), 48000, cutoff_hz=0),
        lambda: dsp.crossover(np.ones(8), 48000, cutoff_hz=24000),
        lambda: dsp.crossover(np.ones(8), 48000, cutoff_hz=np.nan),
        lambda: dsp.crossover(np.ones(8), 48000, cutoff_hz=[1000, 1200]),
        lambda: dsp.crossfade_delay(np.ones(8), 48000, delay_seconds=0),
        lambda: dsp.crossfade_delay(np.ones(8), 48000, delay_seconds=0.5 / 48000),
        lambda: dsp.crossfade_delay(np.ones(8), 48000, feedback=1),
        lambda: dsp.crossfade_delay(np.ones(8), 48000, feedback=-1),
        lambda: dsp.crossfade_delay(np.ones(8), 48000, tail_seconds=-1),
        lambda: dsp.crossfade_delay(np.ones(8), 48000, crossfade_seconds=0),
        lambda: dsp.crossfade_delay(np.ones(8), 48000, crossfade_seconds=0.4 / 48000),
        lambda: dsp.crossfade_delay(np.ones(8), 48000, crossfade_seconds=np.inf),
    ],
)
def test_components_reject_invalid_parameters(call):
    with pytest.raises(ValueError):
        call()
