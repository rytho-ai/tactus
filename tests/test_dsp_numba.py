"""Equivalence coverage for cached DSP kernels behind the public functions."""

import math

import numpy as np

from tactus import dsp

BUTTERWORTH_Q = 2**-0.5


def reference_duck(audio, detector, sample_rate, *, threshold_db=-18.0, ratio=4.0):
    peaks = np.abs(detector)
    if peaks.ndim == 2:
        peaks = np.max(peaks, axis=1)
    attack_weight = -math.expm1(-1000.0 / sample_rate / 5.0)
    release_weight = -math.expm1(-1000.0 / sample_rate / 100.0)
    envelope = np.empty(len(audio))
    level = 0.0
    for i, peak in enumerate(peaks):
        weight = attack_weight if peak > level else release_weight
        level += weight * (peak - level)
        envelope[i] = level
    levels_db = np.full(len(audio), -np.inf)
    np.log10(envelope, out=levels_db, where=envelope > 0)
    excess = np.maximum(20 * levels_db - threshold_db, 0)
    gains = 10 ** (-excess * (1 - 1 / ratio) / 20)
    return audio * (gains[:, None] if np.asarray(audio).ndim == 2 else gains), gains


def reference_delay(audio, sample_rate, *, delay_seconds, feedback=0.35, tail_seconds=0.0):
    x = np.asarray(audio, dtype=np.float64)
    mono = x.ndim == 1
    frames = x[:, None] if mono else x
    delays = np.asarray(delay_seconds, dtype=np.float64) * sample_rate
    total = len(x) + round(tail_seconds * sample_rate)
    result = np.zeros((total, frames.shape[1]))
    if len(x):
        capacity = math.ceil(min(float(np.max(delays)), total)) + 1
        history = np.zeros((capacity, frames.shape[1]))
        for i in range(total):
            distance = float(delays if delays.ndim == 0 else delays[min(i, len(x) - 1)])
            integer = math.floor(distance)
            fraction = distance - integer
            newer = i - integer
            if newer >= 0:
                result[i] += (1 - fraction) * history[newer % capacity]
            if newer >= 1:
                result[i] += fraction * history[(newer - 1) % capacity]
            history[i % capacity] = feedback * result[i]
            if i < len(x):
                history[i % capacity] += frames[i]
    return result[:, 0] if mono else result


def reference_lowpass(audio, sample_rate, *, cutoff_hz, q=BUTTERWORTH_Q):
    x = np.asarray(audio, dtype=np.float64)
    mono = x.ndim == 1
    frames = x[:, None] if mono else x
    cutoff = np.asarray(cutoff_hz, dtype=np.float64)
    result = np.empty_like(frames)
    g = np.tan(np.pi * cutoff / sample_rate)
    k = 1 / q
    a1 = 1 / (1 + g * (g + k))
    a2 = g * a1
    a3 = g * a2
    state1 = np.zeros(frames.shape[1])
    state2 = np.zeros(frames.shape[1])
    for i, frame in enumerate(frames):
        v3 = frame - state2
        v1 = a1[i] * state1 + a2[i] * v3
        v2 = state2 + a2[i] * state1 + a3[i] * v3
        state1 = 2 * v1 - state1
        state2 = 2 * v2 - state2
        result[i] = v2
    return result[:, 0] if mono else result


def test_numba_duck_matches_python_recurrence_for_layouts_and_empty():
    rng = np.random.default_rng(519)
    program = rng.normal(0, 0.2, (96, 4))[::2, ::2]
    detector = rng.normal(0, 0.4, (96, 6))[::2, ::2]
    detector.setflags(write=False)
    got, gain = dsp.duck(program, detector, 48000, return_gain=True)
    expected, expected_gain = reference_duck(program, detector, 48000)
    np.testing.assert_allclose(gain, expected_gain, rtol=0, atol=1e-15)
    np.testing.assert_allclose(got, expected, rtol=0, atol=1e-15)

    mono = program[:, 0]
    mono_detector = detector[:, 0]
    got_mono = dsp.duck(mono, mono_detector, 48000)
    expected_mono, _ = reference_duck(mono, mono_detector, 48000)
    np.testing.assert_allclose(got_mono, expected_mono, rtol=0, atol=1e-15)
    assert dsp.duck(mono[:0], mono_detector[:0], 48000).shape == (0,)


def test_numba_delay_matches_python_recurrence_for_controls_and_layouts():
    rng = np.random.default_rng(238)
    program = rng.normal(0, 0.2, (128, 4))[::2, ::2]
    source_control = (3.25 + np.sin(np.arange(len(program) * 2) * 0.37) * 1.5) / 48000
    control = source_control[::2]
    control.setflags(write=False)
    got = dsp.delay(program, 48000, delay_seconds=control, feedback=-0.45, tail_seconds=0.002)
    expected = reference_delay(
        program, 48000, delay_seconds=control, feedback=-0.45, tail_seconds=0.002
    )
    np.testing.assert_allclose(got, expected, rtol=0, atol=1e-14)

    mono = program[:, 0]
    got_mono = dsp.delay(mono, 48000, delay_seconds=3.5 / 48000, feedback=0.25)
    expected_mono = reference_delay(mono, 48000, delay_seconds=3.5 / 48000, feedback=0.25)
    np.testing.assert_allclose(got_mono, expected_mono, rtol=0, atol=1e-14)
    returns_from_prehistory = dsp.delay(
        np.array([1.0, 0.0, 0.0]),
        48000,
        delay_seconds=np.array([1e300, 1 / 48000, 1 / 48000]),
        feedback=0,
    )
    np.testing.assert_array_equal(returns_from_prehistory, np.array([0.0, 1.0, 0.0]))
    np.testing.assert_array_equal(
        dsp.delay(mono[:0], 48000, delay_seconds=np.empty(0), tail_seconds=0.001),
        np.zeros(48),
    )


def test_numba_lowpass_matches_python_svf_for_controls_and_layouts():
    rng = np.random.default_rng(724)
    program = rng.normal(0, 0.2, (160, 4))[::2, ::2]
    cutoff = np.geomspace(200, 8000, len(program) * 2)[::2]
    cutoff.setflags(write=False)
    got = dsp.lowpass(program, 48000, cutoff_hz=cutoff, q=0.9)
    expected = reference_lowpass(program, 48000, cutoff_hz=cutoff, q=0.9)
    np.testing.assert_allclose(got, expected, rtol=0, atol=1e-14)

    mono = program[:, 0]
    mono_cutoff = cutoff[::-1].copy()
    got_mono = dsp.lowpass(mono, 48000, cutoff_hz=mono_cutoff, q=1.7)
    expected_mono = reference_lowpass(mono, 48000, cutoff_hz=mono_cutoff, q=1.7)
    np.testing.assert_allclose(got_mono, expected_mono, rtol=0, atol=1e-14)
    assert dsp.lowpass(mono[:0], 48000, cutoff_hz=np.empty(0)).shape == (0,)
