"""Reusable offline DSP: independent transfer properties and observed probe regressions."""

import json

import numpy as np
import pytest
from scipy.signal import butter, lfilter

from tactus import dsp
from tactus.cli import main


def rms(x):
    return np.sqrt(np.mean(np.asarray(x) ** 2))


def history_delay(x, sr, seconds, feedback, tail):
    """Slow independent absolute-time oracle, with no circular buffer."""
    n = len(x) + round(tail * sr)
    delays = np.broadcast_to(seconds, (len(x),))
    stored = np.zeros((n,) + x.shape[1:])
    output = np.zeros_like(stored)
    for i in range(n):
        position = i - delays[min(i, len(x) - 1)] * sr
        left = int(np.floor(position))
        fraction = position - left
        if 0 <= left < i:
            output[i] += (1 - fraction) * stored[left]
        if 0 <= left + 1 < i:
            output[i] += fraction * stored[left + 1]
        stored[i] = (x[i] if i < len(x) else 0) + feedback * output[i]
    return output


@pytest.mark.parametrize("rate", [32000, 44100, 48000, 96000])
def test_duck_static_curve_silence_ratio_one_and_headroom(rate):
    x = np.ones((rate // 10, 2)) * [2, -4]
    detector = np.full(len(x), 0.5)
    y, g = dsp.duck(x, detector, rate, attack_ms=0, release_ms=0, return_gain=True)
    expected = 10 ** (-(20 * np.log10(0.5) + 18) * 0.75 / 20)
    np.testing.assert_allclose(g, expected, atol=1e-14)
    np.testing.assert_allclose(y, x * expected, atol=1e-14)
    np.testing.assert_array_equal(dsp.duck(x, detector * 0, rate), x)
    np.testing.assert_array_equal(dsp.duck(x, detector, rate, ratio=1), x)
    np.testing.assert_array_equal(dsp.duck(x, detector * 0, rate, threshold_db=-1000), x)


def test_duck_time_constants_against_analytic_step_and_release():
    sr = 1000
    detector = np.r_[np.ones(100), np.zeros(100)]
    attack, release = 0.01, 0.02
    rise = 1 - np.exp(-np.arange(1, 101) / (sr * attack))
    fall = rise[-1] * np.exp(-np.arange(1, 101) / (sr * release))
    envelope = np.r_[rise, fall]
    expected = 10 ** (-np.maximum(20 * np.log10(envelope) + 40, 0) * 0.5 / 20)
    y = dsp.duck(np.ones(200), detector, sr, threshold_db=-40, ratio=2, attack_ms=10, release_ms=20)
    np.testing.assert_allclose(y, expected, atol=1e-14)


def test_duck_stereo_detector_and_gain_reuse_on_another_program():
    d = np.random.default_rng(15).normal(size=(1103, 3))
    x = np.full((len(d), 2), [0.2, -0.7])
    original = d.copy()
    y, g = dsp.duck(x, d, 44100, return_gain=True)
    _, linked = dsp.duck(np.ones(len(d)), np.max(abs(d), axis=1), 44100, return_gain=True)
    np.testing.assert_array_equal(g, linked)
    np.testing.assert_allclose(y, x * g[:, None])
    different = np.linspace(-2, 2, len(d))
    yy, gg = dsp.duck(different, d, 44100, return_gain=True)
    np.testing.assert_array_equal(g, gg)
    np.testing.assert_array_equal(yy, different * g)
    np.testing.assert_array_equal(d, original)


@pytest.mark.parametrize("samples", [1, 1.25, 1.5, 37.25])
def test_delay_first_fractional_tap_is_wet_only(samples):
    x = np.r_[1.0, np.zeros(80)]
    y = dsp.delay(x, 1000, delay_seconds=samples / 1000, feedback=0)
    expected = np.zeros_like(x)
    left = int(np.floor(samples))
    expected[left] = 1 - samples % 1
    expected[left + 1] = samples % 1
    np.testing.assert_allclose(y, expected, atol=1e-14)
    assert y[0] == 0  # Never return the write-side history containing the dry input.


@pytest.mark.parametrize("feedback", [-0.8, 0, 0.5])
def test_delay_integer_impulse_feedback_and_tail(feedback):
    y = dsp.delay(np.array([2.0]), 1000, delay_seconds=0.001, feedback=feedback, tail_seconds=0.01)
    np.testing.assert_allclose(y, np.r_[0, 2 * feedback ** np.arange(10)], atol=1e-14)


@pytest.mark.parametrize("channels", [1, 2, 5])
@pytest.mark.parametrize("rate", [32000, 44100, 96000])
def test_modulated_delay_ring_matches_absolute_history(channels, rate):
    x = np.random.default_rng(99).normal(0, 0.2, (1013, channels))
    if channels == 1:
        x = x[:, 0]
    # Large excursions exercise wraparound and history retention, not only a ramp.
    samples = 1 + 73 * (1 + np.sin(np.arange(len(x)) * 0.11))
    samples[30:35] = 1
    samples[901:] = 37.25
    control = samples / rate
    y = dsp.delay(x, rate, delay_seconds=control, feedback=-0.6, tail_seconds=0.02)
    reference = history_delay(x, rate, control, -0.6, 0.02)
    np.testing.assert_allclose(y, reference, atol=1e-12)
    assert len(y) == len(x) + round(rate * 0.02)


def test_delay_long_delay_does_not_allocate_unreachable_history():
    # Allocating one million seconds of history would be infeasible for a two-frame clip.
    y = dsp.delay(np.ones((2, 3)), 48000, delay_seconds=1e6)
    np.testing.assert_array_equal(y, np.zeros((2, 3)))


@pytest.mark.parametrize("rate", [32000, 44100, 48000, 96000])
def test_lowpass_scalar_and_constant_control_match_independent_filter(rate):
    x = np.random.default_rng(4).normal(size=(4001, 2))
    b, a = butter(2, 1300, fs=rate)
    expected = lfilter(b, a, x, axis=0)
    scalar = dsp.lowpass(x, rate, cutoff_hz=1300)
    curve = dsp.lowpass(x, rate, cutoff_hz=np.full(len(x), 1300))
    np.testing.assert_allclose(scalar, expected, atol=1e-13)
    np.testing.assert_allclose(curve, expected, atol=1e-13)


@pytest.mark.parametrize("rate", [44100, 48000])
def test_lowpass_sweep_tracks_cutoff_without_channel_leakage(rate):
    t = np.arange(rate) / rate
    tone = np.sin(2 * np.pi * 4000 * t)
    x = np.column_stack([tone, np.zeros(rate)])
    y = dsp.lowpass(x, rate, cutoff_hz=np.geomspace(250, 10000, rate))
    assert 20 * np.log10(rms(y[rate // 20 : rate // 5, 0]) / rms(tone)) < -25
    assert 20 * np.log10(rms(y[-rate // 5 :, 0]) / rms(tone)) > -7
    assert np.max(abs(y)) < 2
    np.testing.assert_array_equal(y[:, 1], 0)


@pytest.mark.parametrize("q", [0.3, 1, 4])
def test_lowpass_q_center_gain(q):
    sr = 48000
    t = np.arange(sr // 4) / sr
    x = np.sin(2 * np.pi * 1000 * t)
    y = dsp.lowpass(x, sr, cutoff_hz=np.full(len(x), 1000), q=q)
    assert rms(y[6000:]) / rms(x[6000:]) == pytest.approx(q, abs=1e-10)


@pytest.mark.parametrize("rate,freq", [(48000, 7000), (44100, 6311)])
def test_saturate_retains_nonlinearity_and_suppresses_aliasing(rate, freq):
    t = np.arange(3 * rate) / rate
    x = 0.8 * np.sin(2 * np.pi * freq * t)
    y = dsp.saturate(x, rate, drive_db=18, mix=1)
    z = np.fft.rfft(y[rate : 2 * rate])
    valid = np.zeros(len(z), dtype=bool)
    valid[np.arange(freq, rate // 2, 2 * freq)] = True
    energy = abs(z) ** 2
    energy[1:-1] *= 2
    db = 10 * np.log10(energy[~valid].sum() / energy[valid].sum())
    assert db < -35
    assert 0.9 < 2 * abs(z[freq]) / rate < 1.4
    assert 2 * abs(z[3 * freq]) / rate > 0.15
    naive = dsp.saturate(x, rate, drive_db=18, mix=1, oversample=1)
    zz = abs(np.fft.rfft(naive[rate : 2 * rate])) ** 2
    assert 10 * np.log10(zz[~valid].sum() / zz[valid].sum()) > -35


def test_saturate_curves_transfer_and_fold_reflection():
    x = np.linspace(-3.0, 3.0, 13)
    np.testing.assert_allclose(
        dsp.saturate(x, 48000, drive_db=0, mix=1, oversample=1, curve="clip"), np.clip(x, -1, 1)
    )
    folded = dsp.saturate(x, 48000, drive_db=0, mix=1, oversample=1, curve="fold")
    expected = [1.0, 0.5, 0.0, -0.5, -1.0, -0.5, 0.0, 0.5, 1.0, 0.5, 0.0, -0.5, -1.0]
    np.testing.assert_allclose(folded, expected, atol=1e-15)
    np.testing.assert_array_equal(
        dsp.saturate(x, 48000, mix=1, oversample=1),
        dsp.saturate(x, 48000, mix=1, oversample=1, curve="tanh"),
    )
    with pytest.raises(ValueError, match="curve"):
        dsp.saturate(x, 48000, curve="sine")


@pytest.mark.parametrize("curve", ["clip", "fold"])
def test_saturate_oversampling_reduces_clip_and_fold_aliasing(curve):
    rate, freq = 48000, 2345
    x = 0.8 * np.sin(2 * np.pi * freq * np.arange(3 * rate) / rate)

    def alias_db(y):
        energy = abs(np.fft.rfft(y[rate : 2 * rate])) ** 2
        valid = np.zeros(len(energy), dtype=bool)
        valid[np.arange(freq, rate // 2, 2 * freq)] = True
        return 10 * np.log10(energy[~valid].sum() / energy[valid].sum())

    naive = dsp.saturate(x, rate, drive_db=12, mix=1, oversample=1, curve=curve)
    smooth = dsp.saturate(x, rate, drive_db=12, mix=1, oversample=8, curve=curve)
    assert alias_db(smooth) < alias_db(naive) - 15


@pytest.mark.parametrize("oversample", [1, 2, 4, 8, 16])
def test_saturate_transfer_alignment_and_exact_bypass(oversample):
    n = 4097
    x = np.full((n, 2), [0.001, 0.2])
    y = dsp.saturate(x, 48000, drive_db=12, mix=1, oversample=oversample)
    np.testing.assert_allclose(
        y[100:-100], np.broadcast_to(np.tanh(x[0] * 10**0.6), y[100:-100].shape), atol=2e-5
    )
    impulse = np.zeros(n)
    impulse[n // 2] = 1e-4
    response = dsp.saturate(impulse, 48000, drive_db=0, mix=1, oversample=oversample)
    assert np.argmax(abs(response)) == n // 2
    np.testing.assert_allclose(response, response[::-1], atol=1e-14)
    headroom = np.array([2.0, -3.0, 0.1])
    np.testing.assert_array_equal(
        dsp.saturate(headroom, 48000, mix=0, oversample=oversample), headroom
    )


def test_saturate_per_frame_gain_and_mix():
    n = 3003
    x = np.random.default_rng(7).normal(0, 0.2, (n, 3))
    drive = np.linspace(6, 18, n)
    blend = np.linspace(0, 1, n)
    wet = dsp.saturate(x, 44100, drive_db=drive, mix=1)
    y = dsp.saturate(x, 44100, drive_db=drive, mix=blend)
    np.testing.assert_array_equal(y, (1 - blend[:, None]) * x + blend[:, None] * wet)
    raw = dsp.saturate(x, 44100, drive_db=drive, mix=1, oversample=1)
    np.testing.assert_array_equal(raw, np.tanh(x * 10 ** (drive[:, None] / 20)))
    # All-zero automation is exactly the same as scalar bypass.
    np.testing.assert_array_equal(dsp.saturate(x, 44100, mix=np.zeros(n)), x)


@pytest.mark.parametrize("shape", [(0,), (0, 1), (0, 3), (1,), (1, 2), (17, 3)])
def test_effect_shapes_float64_reset_and_nonmutation(shape):
    x = np.ones(shape, dtype=np.float32)
    original = x.copy()
    detector = np.ones(shape[0])
    controls = np.full(shape[0], 1000.0)
    for fn in [
        lambda: dsp.duck(x, detector, 48000),
        lambda: dsp.delay(x, 48000, delay_seconds=np.full(shape[0], 0.02)),
        lambda: dsp.lowpass(x, 48000, cutoff_hz=controls),
        lambda: dsp.saturate(x, 48000, drive_db=np.full(shape[0], 12.0)),
    ]:
        y = fn()
        assert y.shape == x.shape and y.dtype == np.float64
        assert np.isfinite(y).all() and not np.shares_memory(x, y)
        np.testing.assert_array_equal(fn(), y)
        np.testing.assert_array_equal(x, original)
    tail = dsp.delay(x[:0], 48000, delay_seconds=np.empty(0), tail_seconds=0.001)
    assert tail.shape == (48,) + x.shape[1:]
    assert not tail.any()


@pytest.mark.parametrize("control", [np.nan, 1j, [1.0, 2.0], True])
def test_effects_reject_bad_scalar_or_array_controls(control):
    x = np.ones(10)
    for fn in [
        lambda: dsp.duck(x, x, 48000, ratio=control),
        lambda: dsp.delay(x, 48000, delay_seconds=control),
        lambda: dsp.lowpass(x, 48000, cutoff_hz=control),
        lambda: dsp.saturate(x, 48000, mix=control),
    ]:
        with pytest.raises(ValueError):
            fn()


@pytest.mark.parametrize("rate", [0, -1, 48000.0, True])
def test_effects_reject_invalid_rate(rate):
    x = np.ones(10)
    for fn in [dsp.delay, dsp.lowpass, dsp.saturate]:
        with pytest.raises(ValueError):
            fn(x, rate)
    with pytest.raises(ValueError):
        dsp.duck(x, x, rate)


@pytest.mark.parametrize(
    "x", [np.array([np.inf]), np.array([1j]), np.ones((3, 0)), np.ones((2, 2, 2)), np.array([True])]
)
def test_effects_reject_invalid_audio(x):
    for fn in [dsp.delay, dsp.lowpass, dsp.saturate]:
        with pytest.raises(ValueError):
            fn(x, 48000)
    with pytest.raises(ValueError):
        dsp.duck(x, np.zeros(len(x)), 48000)


def test_effect_parameter_boundaries():
    x = np.ones(10)
    calls = [
        lambda: dsp.duck(x, x[:-1], 48000),
        lambda: dsp.duck(x, x * np.nan, 48000),
        lambda: dsp.duck(x, x, 48000, ratio=0.5),
        lambda: dsp.duck(x, x, 48000, attack_ms=-1),
        lambda: dsp.duck(x, x, 48000, release_ms=-1),
        lambda: dsp.delay(x, 48000, delay_seconds=0),
        lambda: dsp.delay(x, 48000, delay_seconds=0.5 / 48000),
        lambda: dsp.delay(x, 48000, feedback=1),
        lambda: dsp.delay(x, 48000, feedback=-1),
        lambda: dsp.delay(x, 48000, tail_seconds=-1),
        lambda: dsp.lowpass(x, 48000, q=0),
        lambda: dsp.lowpass(x, 48000, cutoff_hz=24000),
        lambda: dsp.lowpass(x, 48000, cutoff_hz=0),
        lambda: dsp.saturate(x, 48000, mix=-0.1),
        lambda: dsp.saturate(x, 48000, mix=1.1),
        lambda: dsp.saturate(x, 48000, oversample=3),
        lambda: dsp.saturate(x, 48000, oversample=True),
        lambda: dsp.saturate(x, 48000, oversample=8.0),
        lambda: dsp.saturate(x, 48000, drive_db=10000),
    ]
    for fn in calls:
        with pytest.raises(ValueError):
            fn()
    with pytest.raises(TypeError):
        dsp.duck(x, x, 48000, return_gain=1)


def test_reusable_effects_in_runtime(tmp_path, capsys):
    source = tmp_path / "song.py"
    source.write_text("""import numpy as np
from tactus import dsp
def render():
    sr = 16000
    t = np.arange(1600) / sr
    x = dsp.pan(.2 * np.sin(2*np.pi*220*t))
    x, g = dsp.duck(x, .8*np.exp(-t/.01), sr, return_gain=True)
    x = dsp.lowpass(x, sr, cutoff_hz=np.linspace(500, 3000, len(x)))
    x = dsp.saturate(x, sr, drive_db=np.linspace(3, 12, len(x)), mix=.3)
    wet = dsp.delay(x, sr, delay_seconds=.0123, tail_seconds=.1)
    return {"sample_rate": sr, "outputs": {"dry": x, "wet": wet}}
""")
    out = tmp_path / "run"
    assert main(["run", str(source), "--out", str(out)]) == 0
    assert "wet" in capsys.readouterr().out
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["sample_rate"] == 16000


def reference_ladder(audio, sample_rate, cutoff, resonance, drive_db=0.0):
    x = np.asarray(audio, dtype=np.float64)
    thermal = 10 ** (drive_db / 20)
    cutoff = np.broadcast_to(cutoff, (len(x),))
    resonance = np.broadcast_to(resonance, (len(x),))
    out = np.empty(len(x))
    d = [0.0] * 6
    t = [0.0] * 3
    for i in range(len(x)):
        fc = cutoff[i] / sample_rate
        fcr = 1.8730 * fc**3 + 0.4955 * fc**2 - 0.6490 * fc + 0.9988
        acr = -3.9364 * fc**2 + 1.8409 * fc + 0.9968
        g = (1 - np.exp(-np.pi * fc * fcr)) / thermal
        k = 4 * resonance[i] * acr
        for _ in range(2):
            d[0] = d[0] + g * (np.tanh((x[i] - k * d[5]) * thermal) - t[0])
            t[0] = np.tanh(d[0] * thermal)
            d[1] = d[1] + g * (t[0] - t[1])
            t[1] = np.tanh(d[1] * thermal)
            d[2] = d[2] + g * (t[1] - t[2])
            t[2] = np.tanh(d[2] * thermal)
            s3 = d[3] + g * (t[2] - np.tanh(d[3] * thermal))
            d[3] = s3
            d[5] = (s3 + d[4]) * 0.5
            d[4] = s3
        out[i] = d[5]
    return out


def test_ladder_kernel_matches_python_recurrence():
    rng = np.random.default_rng(12)
    audio = rng.normal(0, 0.5, 3000)
    cutoff = np.geomspace(100, 12000, 3000)
    resonance = np.linspace(0, 1, 3000)
    np.testing.assert_allclose(
        dsp.ladder(audio, 48000, cutoff_hz=cutoff, resonance=resonance, drive_db=6),
        reference_ladder(audio, 48000, cutoff, resonance, drive_db=6),
        rtol=0,
        atol=1e-12,
    )


def test_ladder_slope_passband_loss_self_oscillation_and_drive():
    sr = 48000
    t = np.arange(sr) / sr

    def gain_db(freq, **kwargs):
        x = 0.001 * np.sin(2 * np.pi * freq * t)
        y = dsp.ladder(x, sr, **kwargs)
        return 20 * np.log10(rms(y[sr // 2 :]) / rms(x[sr // 2 :]))

    assert gain_db(50, cutoff_hz=1000) == pytest.approx(0, abs=0.1)
    assert gain_db(1000, cutoff_hz=1000) == pytest.approx(-12, abs=0.6)
    assert gain_db(8000, cutoff_hz=1000) - gain_db(4000, cutoff_hz=1000) < -20  # ~24 dB/oct
    assert gain_db(50, cutoff_hz=1000, resonance=0.8) < -3  # passband loss, no makeup gain
    impulse = np.zeros(2 * sr)
    impulse[0] = 0.1
    ringing = dsp.ladder(impulse, sr, cutoff_hz=880, resonance=1.0)
    tail = ringing[-sr // 2 :]
    assert rms(tail) > 1e-3
    spectrum = np.abs(np.fft.rfft(tail * np.hanning(len(tail))))
    assert abs(np.argmax(spectrum) * 2 - 880) < 40
    loud = 0.9 * np.sin(2 * np.pi * 110 * t)
    clean = dsp.ladder(loud, sr, cutoff_hz=5000, drive_db=-20)
    driven = dsp.ladder(loud, sr, cutoff_hz=5000, drive_db=12)

    def third_harmonic(y):
        s = np.abs(np.fft.rfft(y[sr // 2 :]))
        return s[165] / s[55]

    assert third_harmonic(driven) > 10 * third_harmonic(clean)


def test_ladder_layouts_controls_and_validation():
    rng = np.random.default_rng(4)
    stereo = rng.normal(0, 0.2, (2000, 2))
    out = dsp.ladder(stereo, 48000, cutoff_hz=np.geomspace(200, 9000, 2000), resonance=0.5)
    assert out.shape == (2000, 2) and np.isfinite(out).all()
    np.testing.assert_allclose(
        out[:, 0], dsp.ladder(stereo[:, 0], 48000, cutoff_hz=np.geomspace(200, 9000, 2000), resonance=0.5)
    )
    assert dsp.ladder(stereo[:0], 48000, cutoff_hz=1000).shape == (0, 2)
    with pytest.raises(ValueError, match="resonance"):
        dsp.ladder(stereo, 48000, cutoff_hz=1000, resonance=1.2)
    with pytest.raises(ValueError, match="0.45"):
        dsp.ladder(stereo, 48000, cutoff_hz=22000)


def test_fit_loudness_plain_gain_reaches_target_and_keeps_shape():
    from tactus.analysis.level import loudness

    rng = np.random.default_rng(0)
    x = (rng.standard_normal((48000 * 3, 2)) * 0.02).astype(np.float32)
    y = dsp.fit_loudness(x, 48000, -16.0)
    assert y.shape == x.shape and y.dtype == np.float32
    assert abs(loudness(y, 48000)["integrated_lufs"] + 16.0) <= 0.01
    np.testing.assert_allclose(y / y[0, 0], x / x[0, 0], rtol=1e-4)  # one gain, nothing else


def test_fit_loudness_limits_when_the_ceiling_is_in_the_way():
    from tactus.analysis.level import loudness

    rng = np.random.default_rng(1)
    x = (rng.standard_normal(48000 * 3) * 0.05).astype(np.float32)
    x[::4800] = 0.9  # sparse tall peaks: a plain gain to the target would exceed the ceiling
    with pytest.raises(ValueError, match=r"plain gain reaches at most -?\d+\.\d LUFS"):
        dsp.fit_loudness(x, 48000, -14.0, ceiling_dbfs=-1.0)
    y = dsp.fit_loudness(x, 48000, -14.0, ceiling_dbfs=-1.0, limit=True)
    assert float(np.max(np.abs(y))) <= 10 ** (-1.0 / 20) + 1e-6
    assert abs(loudness(y, 48000)["integrated_lufs"] + 14.0) <= 0.1


def test_fit_loudness_silence_short_and_unreachable_inputs():
    silence = np.zeros(48000, dtype=np.float32)
    np.testing.assert_array_equal(dsp.fit_loudness(silence, 48000, -16.0), silence)
    with pytest.raises(ValueError, match="long and loud enough"):
        dsp.fit_loudness(np.full(1000, 0.1, dtype=np.float32), 48000, -16.0)
    tone = (0.5 * np.sin(2 * np.pi * 1000 * np.arange(48000 * 2) / 48000)).astype(np.float32)
    with pytest.raises(ValueError, match="fit_loudness could not reach"):
        dsp.fit_loudness(tone, 48000, 0.0, ceiling_dbfs=-12.0, limit=True)
