"""Behavior of tactus.synth generators and the dsp.svf / dsp.spectral additions."""

import math

import numpy as np
import pytest

from tactus import dsp, synth
from tactus._synth_kernels import karplus_strong

SR = 48000


def peak_hz(signal, sample_rate=SR):
    n = len(signal)
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(n), 8 * n))
    k = int(np.argmax(spectrum))
    a, b, c = np.log(spectrum[k - 1 : k + 2] + 1e-300)
    offset = 0.5 * (a - c) / (a - 2 * b + c)
    return (k + offset) * sample_rate / (8 * n)


def alias_ratio_db(signal, fundamental, sample_rate=SR):
    n = len(signal)
    signal = signal - signal.mean()
    power = np.abs(np.fft.rfft(signal * np.hanning(n))) ** 2
    freqs = np.fft.rfftfreq(n, 1 / sample_rate)
    harmonic = np.zeros(len(freqs), bool)
    for k in range(1, int(sample_rate / 2 / fundamental) + 1):
        harmonic |= np.abs(freqs - k * fundamental) < 30
    return 10 * np.log10(power[~harmonic].sum() / power[harmonic].sum())


def band_db(signal, lo, hi, sample_rate=SR):
    power = np.abs(np.fft.rfft(signal)) ** 2
    freqs = np.fft.rfftfreq(len(signal), 1 / sample_rate)
    return 10 * np.log10(power[(freqs >= lo) & (freqs < hi)].mean())


def test_phase_scalar_per_frame_and_start():
    got = synth.phase(480.0, SR, frames=100, start=0.25)
    np.testing.assert_allclose(got, 0.25 + np.arange(100) * 0.01, rtol=0, atol=1e-15)
    per_frame = synth.phase(np.full(100, 480.0), SR, frames=100, start=0.25)
    np.testing.assert_allclose(per_frame, got, rtol=0, atol=1e-12)
    glide = synth.phase(np.linspace(100, 200, 1000), SR, frames=1000)
    assert glide[0] == 0 and np.all(np.diff(glide) > 0)
    assert synth.phase(100, SR, frames=0).shape == (0,)
    with pytest.raises(ValueError, match="Nyquist"):
        synth.phase(24000, SR, frames=10)
    with pytest.raises(ValueError, match="frames"):
        synth.phase(100, SR, frames=-1)


def test_sine_frequency_and_phase_modulation_sidebands():
    tone = synth.sine(1234.5, SR, frames=SR)
    assert abs(peak_hz(tone) - 1234.5) < 0.05
    assert np.max(np.abs(tone)) <= 1
    modulator = 0.5 * synth.sine(200.0, SR, frames=SR)
    fm = synth.sine(1000.0, SR, frames=SR, phase_mod=modulator)
    power = np.abs(np.fft.rfft(fm * np.hanning(SR))) ** 2
    freqs = np.fft.rfftfreq(SR, 1 / SR)
    top = sorted(freqs[np.argsort(power)[-40:]].round(-1))
    assert {800.0, 1000.0, 1200.0} <= set(top)


@pytest.mark.parametrize("freq", [440.0, 4321.0, 9876.0])
def test_band_limited_oscillators_alias_far_below_naive(freq):
    t = (np.arange(SR) * freq / SR) % 1
    naive = {
        "saw": 2 * t - 1,
        "pulse": np.where(t < 0.3, 1.0, -1.0),
        "triangle": 4 * np.abs(t - 0.5) - 1,
    }
    made = {
        "saw": synth.saw(freq, SR, frames=SR),
        "pulse": synth.pulse(freq, SR, frames=SR, width=0.3),
        "triangle": synth.triangle(freq, SR, frames=SR),
    }
    for name, signal in made.items():
        assert alias_ratio_db(signal, freq) < alias_ratio_db(naive[name], freq) - 8, name
        assert abs(peak_hz(signal) - freq) < 0.1, name


def test_waveform_shapes_and_pulse_width_average():
    saw = synth.saw(100.0, SR, frames=SR)
    assert saw.min() > -1.01 and saw.max() < 1.01
    square = synth.pulse(100.0, SR, frames=SR, width=0.5)
    assert abs(square.mean()) < 1e-3
    narrow = synth.pulse(100.0, SR, frames=SR, width=0.2)
    assert abs(narrow.mean() - (2 * 0.2 - 1)) < 1e-3
    varying = synth.pulse(100.0, SR, frames=SR, width=np.linspace(0.1, 0.9, SR))
    assert np.isfinite(varying).all()
    tri = synth.triangle(100.0, SR, frames=SR)
    assert abs(tri[0] - 1) < 0.02 and abs(tri[240] + 1) < 0.02
    with pytest.raises(ValueError, match="width"):
        synth.pulse(100.0, SR, frames=10, width=1.0)
    with pytest.raises(ValueError, match=r"reaches \d+ Hz at frame \d+.*2\*pi\*D\*f"):
        synth.saw(12000.0, SR, frames=100, phase_mod=synth.sine(5000, SR, frames=100) * 3)


def test_sine_accepts_any_fm_depth_and_matches_radian_index():
    deep = synth.sine(8000.0, SR, frames=SR, phase_mod=3.0 * synth.sine(2000.0, SR, frames=SR))
    assert np.isfinite(deep).all() and np.max(np.abs(deep)) <= 1
    beta = 2.0
    ours = synth.sine(1000.0, SR, frames=SR, phase_mod=beta / (2 * np.pi) * synth.sine(100.0, SR, frames=SR))
    t = np.arange(SR) / SR
    classic = np.sin(2 * np.pi * 1000.0 * t + beta * np.sin(2 * np.pi * 100.0 * t))
    np.testing.assert_allclose(ours, classic, atol=1e-9)
    with pytest.raises(ValueError, match="Nyquist"):
        synth.sine(24000.0, SR, frames=10)


def test_glides_and_negative_frequency_stay_band_limited():
    glide = synth.saw(np.geomspace(200, 8000, SR), SR, frames=SR)
    assert np.isfinite(glide).all() and np.max(np.abs(glide)) < 1.05
    backwards = synth.saw(-440.0, SR, frames=SR)
    forwards = synth.saw(440.0, SR, frames=SR)
    assert alias_ratio_db(backwards, 440.0) == pytest.approx(alias_ratio_db(forwards, 440.0), abs=1)


def test_noise_is_seeded_bounded_and_pink_slopes():
    a = synth.noise(SR, seed=7)
    np.testing.assert_array_equal(a, synth.noise(SR, seed=7))
    assert not np.array_equal(a, synth.noise(SR, seed=8))
    assert a.min() >= -1 and a.max() < 1
    pink = synth.noise(8 * SR, seed=7, color="pink")
    np.testing.assert_array_equal(pink, synth.noise(8 * SR, seed=7, color="pink"))
    slope = (band_db(pink, 1600, 3200) - band_db(pink, 100, 200)) / 4
    assert -3.6 < slope < -2.4
    with pytest.raises(ValueError, match="seed"):
        synth.noise(10, seed=-1)
    with pytest.raises(ValueError, match="color"):
        synth.noise(10, seed=1, color="brown")


def test_envelope_boundaries_curves_and_length():
    env = synth.envelope(0.0, [(0.001, 1.0, 0), (0.002, 0.0, -4)], SR)
    assert len(env) == 145 and env[0] == 0 and env[48] == 1 and env[-1] == 0
    np.testing.assert_allclose(env[:49], np.arange(49) / 48)
    assert np.all(np.diff(env[48:]) < 0)
    fast = env[48:][:48]
    assert fast[24] < 0.5
    through_zero = synth.envelope(-1.0, [(0.01, 1.0, 3.0)], SR)
    assert np.isfinite(through_zero).all() and through_zero[-1] == 1
    jump = synth.envelope(0.5, [(0.0, 1.0, 0), (0.001, 0.0, 0)], SR)
    assert jump[0] == 1 and jump[-1] == 0
    held = synth.envelope(0.0, [(0.001, 1.0, 0)], SR, frames=100)
    assert len(held) == 100 and np.all(held[48:] == 1)
    assert len(synth.envelope(0.0, [(0.01, 1.0, 0)], SR, frames=10)) == 10
    with pytest.raises(ValueError, match="segment"):
        synth.envelope(0.0, [(0.01, 1.0)], SR)
    with pytest.raises(ValueError, match="nonnegative"):
        synth.envelope(0.0, [(-0.01, 1.0, 0)], SR)


def test_resonator_impulse_response_frequency_and_decay():
    impulse = np.zeros(SR)
    impulse[0] = 1
    out = synth.resonators(impulse, SR, freqs_hz=[440.0], decays_s=[0.5], gains=[0.7])
    n = np.arange(SR)
    r = math.exp(-math.log(1000) / (0.5 * SR))
    expected = 0.7 * r**n * np.sin(2 * np.pi * 440 * (n + 1) / SR)
    np.testing.assert_allclose(out, expected, rtol=0, atol=1e-9)
    stereo = synth.resonators(np.column_stack((impulse, impulse)), SR, freqs_hz=[440, 880], decays_s=[1, 1])
    assert stereo.shape == (SR, 2)
    with pytest.raises(ValueError, match="equal-length"):
        synth.resonators(impulse, SR, freqs_hz=[440, 880], decays_s=[1])
    with pytest.raises(ValueError, match="Nyquist"):
        synth.resonators(impulse, SR, freqs_hz=[30000], decays_s=[1])


def reference_karplus(drive, delay, s, c, g):
    out = np.zeros(len(drive))
    prev_avg = prev_ap = 0.0
    for n in range(len(drive)):
        newer = out[n - delay] if n >= delay else 0.0
        older = out[n - delay - 1] if n >= delay + 1 else 0.0
        avg = (1 - s) * newer + s * older
        ap = c * avg + prev_avg - c * prev_ap
        prev_avg, prev_ap = avg, ap
        out[n] = drive[n] + g * ap
    return out


def test_pluck_kernel_matches_reference_recurrence():
    drive = synth.noise(3000, seed=3)
    np.testing.assert_allclose(
        karplus_strong(drive, 97, 0.3, 0.2, 0.99),
        reference_karplus(drive, 97, 0.3, 0.2, 0.99),
        rtol=0,
        atol=1e-12,
    )


def component_level(signal, freq, start_s, seconds=0.1):
    """Amplitude of the frequency component near `freq` in a Hann window."""
    begin, n = int(start_s * SR), int(seconds * SR)
    window = np.hanning(n)
    segment = signal[begin : begin + n] * window
    spectrum = np.abs(np.fft.rfft(segment, 16 * n))
    freqs = np.fft.rfftfreq(16 * n, 1 / SR)
    near = np.abs(freqs - freq) < freq * 0.03
    k = np.flatnonzero(near)[np.argmax(spectrum[near])]
    return freqs[k], 2 * spectrum[k] / window.sum()


@pytest.mark.parametrize("freq", [82.41, 220.0, 1000.0])
def test_pluck_tuning_and_decay(freq):
    burst = synth.noise(int(SR / freq), seed=11)
    burst -= burst.mean()
    string = synth.pluck(freq, SR, excitation=burst, frames=2 * SR, decay_s=1.0, brightness=0.6)
    found, _ = component_level(string, freq, 0.1, seconds=0.5)
    assert abs(1200 * math.log2(found / freq)) < 3
    _, first = component_level(string, freq, 0.2)
    _, later = component_level(string, freq, 0.7)
    assert 20 * math.log10(first / later) == pytest.approx(30.0, abs=3.0)
    with pytest.raises(ValueError, match="decay"):
        synth.pluck(freq, SR, excitation=burst, frames=100, decay_s=1e6, brightness=0.0)


def test_grains_placement_window_pan_and_reverse():
    source = np.ones(SR)
    one = synth.grains(source, SR, onsets_s=[0.01], positions_s=[0.1], durations_s=0.01, frames=2000)
    begin, length = 480, 480
    x = (np.arange(length) + 0.5) / length
    np.testing.assert_allclose(one[begin : begin + length], np.sin(np.pi * x) ** 2)
    assert np.all(one[:begin] == 0) and np.all(one[begin + length :] == 0)
    stereo = synth.grains(
        source, SR, onsets_s=[0.0, 0.0], positions_s=0.1, durations_s=0.01, frames=480, pan=[-1, 1]
    )
    assert stereo.shape == (480, 2)
    np.testing.assert_allclose(stereo[:, 0], stereo[:, 1], atol=1e-12)
    ramp = np.arange(SR, dtype=float)
    backwards = synth.grains(
        ramp, SR, onsets_s=[0.0], positions_s=[0.5], durations_s=0.01, rate=-1.0,
        frames=480, window="triangle",
    )
    assert np.all(np.diff(backwards[240:470] / (1 - np.abs(2 * (np.arange(240, 470) + 0.5) / 480 - 1))) < 0)
    outside = synth.grains(source, SR, onsets_s=[0.0], positions_s=[2.0], durations_s=0.01, frames=480)
    assert np.all(outside == 0)
    with pytest.raises(ValueError, match="window"):
        synth.grains(source, SR, onsets_s=[0], positions_s=[0], durations_s=0.1, frames=10, window="gauss")


def test_generators_do_not_mutate_inputs():
    freq = np.linspace(100, 200, 1000)
    freq.setflags(write=False)
    synth.saw(freq, SR, frames=1000)
    burst = synth.noise(200, seed=1)
    before = burst.copy()
    synth.pluck(220.0, SR, excitation=burst, frames=1000, decay_s=0.5)
    synth.resonators(burst, SR, freqs_hz=[500], decays_s=[0.1])
    np.testing.assert_array_equal(burst, before)


def svf_gain_db(mode, freq, cutoff=1000.0, q=2**-0.5):
    tone = synth.sine(freq, SR, frames=SR)
    out = dsp.svf(tone, SR, mode=mode, cutoff_hz=cutoff, q=q)
    steady = slice(SR // 2, SR)
    return 20 * np.log10(np.std(out[steady]) / np.std(tone[steady]))


def test_svf_modes_magnitude_responses():
    assert svf_gain_db("lowpass", 1000.0) == pytest.approx(-3.01, abs=0.05)
    assert svf_gain_db("lowpass", 100.0) == pytest.approx(0.0, abs=0.05)
    assert svf_gain_db("highpass", 1000.0) == pytest.approx(-3.01, abs=0.05)
    assert svf_gain_db("highpass", 10000.0) == pytest.approx(0.0, abs=0.2)
    assert svf_gain_db("bandpass", 1000.0, q=5) == pytest.approx(0.0, abs=0.05)
    assert svf_gain_db("bandpass", 2000.0, q=5) < -10
    assert svf_gain_db("notch", 1000.0, q=2) < -40
    assert svf_gain_db("lowpass", 1000.0, q=4) == pytest.approx(20 * math.log10(4), abs=0.1)


def test_svf_lowpass_equals_lowpass_and_accepts_per_frame_q():
    rng = np.random.default_rng(5)
    audio = rng.normal(0, 0.2, (4000, 2))
    cutoff = np.geomspace(200, 12000, 4000)
    np.testing.assert_array_equal(
        dsp.svf(audio, SR, mode="lowpass", cutoff_hz=cutoff, q=1.5),
        dsp.lowpass(audio, SR, cutoff_hz=cutoff, q=1.5),
    )
    moving_q = dsp.svf(audio[:, 0], SR, mode="bandpass", cutoff_hz=800, q=np.linspace(0.5, 10, 4000))
    assert moving_q.shape == (4000,) and np.isfinite(moving_q).all()
    with pytest.raises(ValueError, match="mode"):
        dsp.svf(audio, SR, mode="peak", cutoff_hz=1000)
    with pytest.raises(ValueError, match="q"):
        dsp.svf(audio, SR, mode="lowpass", cutoff_hz=1000, q=0)


def test_spectral_identity_and_transform_contract():
    rng = np.random.default_rng(9)
    audio = rng.normal(0, 0.3, (SR // 2, 2))
    same = dsp.spectral(audio, SR, lambda m, f, i: (m, f))
    assert 20 * np.log10(np.max(np.abs(same - audio))) < -150
    mono = dsp.spectral(audio[:, 0], SR, lambda m, f, i: (m, f), n_fft=512, hop=128)
    assert mono.shape == (SR // 2,) and np.max(np.abs(mono - audio[:, 0])) < 1e-9

    seen = []

    def check(magnitude, frequency, index):
        seen.append((magnitude.shape, index))
        return magnitude, frequency

    dsp.spectral(audio[:4096], SR, check, n_fft=1024, hop=256)
    assert seen[0] == ((513, 2), 0) and seen[-1][1] == len(seen) - 1
    with pytest.raises(ValueError, match="return"):
        dsp.spectral(audio[:4096], SR, lambda m, f, i: m)
    with pytest.raises(ValueError, match="nonnegative"):
        dsp.spectral(audio[:4096], SR, lambda m, f, i: (-m, f))
    with pytest.raises(ValueError, match="hop"):
        dsp.spectral(audio[:4096], SR, lambda m, f, i: (m, f), n_fft=1024, hop=600)


def test_spectral_frequency_follows_a_steady_tone():
    tone = synth.sine(1000.0, SR, frames=SR)
    estimates = []

    def record(magnitude, frequency, index):
        if index > 4:
            estimates.append(frequency[np.argmax(magnitude)])
        return magnitude, frequency

    dsp.spectral(tone, SR, record)
    assert np.allclose(estimates[:50], 1000.0, atol=0.5)


def reference_svf(audio, sample_rate, mode, cutoff, q):
    x = np.asarray(audio, dtype=np.float64)[:, None]
    cutoff = np.broadcast_to(cutoff, (len(x),))
    k = np.broadcast_to(1 / np.asarray(q, dtype=np.float64), (len(x),))
    out = np.empty(len(x))
    s1 = s2 = 0.0
    for i in range(len(x)):
        g = math.tan(math.pi * cutoff[i] / sample_rate)
        a1 = 1 / (1 + g * (g + k[i]))
        a2 = g * a1
        a3 = g * a2
        v0 = x[i, 0]
        v3 = v0 - s2
        v1 = a1 * s1 + a2 * v3
        v2 = s2 + a2 * s1 + a3 * v3
        s1, s2 = 2 * v1 - s1, 2 * v2 - s2
        out[i] = {
            "lowpass": v2,
            "highpass": v0 - k[i] * v1 - v2,
            "bandpass": k[i] * v1,
            "notch": v0 - k[i] * v1,
        }[mode]
    return out


@pytest.mark.parametrize("mode", ["lowpass", "highpass", "bandpass", "notch"])
def test_svf_kernel_matches_python_recurrence(mode):
    rng = np.random.default_rng(31)
    audio = rng.normal(0, 0.2, 3000)
    cutoff = np.geomspace(150, 15000, 3000)
    q = np.linspace(0.5, 8, 3000)
    np.testing.assert_allclose(
        dsp.svf(audio, SR, mode=mode, cutoff_hz=cutoff, q=q),
        reference_svf(audio, SR, mode, cutoff, q),
        rtol=0,
        atol=1e-12,
    )
