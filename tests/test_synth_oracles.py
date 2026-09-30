"""Behavioral comparisons of tactus.synth against Csound, used as an external oracle.

Skipped when the `csound` binary is absent. Agreement is judged on shape (correlation,
harmonic levels), not sample identity: the implementations are independent and the
oracle's own conventions (normalization, start phase) differ.
"""

import math
import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from tactus import synth

pytestmark = [
    pytest.mark.oracle,
    pytest.mark.skipif(shutil.which("csound") is None, reason="csound binary not installed"),
]

SR = 48000


def render_csound(tmp_path, instrument, seconds):
    csd = tmp_path / "oracle.csd"
    out = tmp_path / "oracle.wav"
    csd.write_text(
        f"""<CsoundSynthesizer>
<CsOptions>
-o {out} -W -f --nodisplays -d
</CsOptions>
<CsInstruments>
sr = {SR}
ksmps = 1
nchnls = 1
0dbfs = 1
instr 1
{instrument}
endin
</CsInstruments>
<CsScore>
i1 0 {seconds}
</CsScore>
</CsoundSynthesizer>
"""
    )
    subprocess.run(["csound", str(csd)], check=True, capture_output=True, timeout=60)
    audio, rate = sf.read(out, dtype="float64")
    assert rate == SR
    return audio


def test_resonator_matches_csound_mode_shape(tmp_path):
    freq, decay = 440.0, 0.5
    q = math.pi * freq * decay / math.log(1000)
    oracle = render_csound(
        tmp_path,
        f"""aimp mpulse 1, 0
 aout mode aimp, {freq}, {q}
 out aout""",
        decay,
    )
    impulse = np.zeros(len(oracle))
    impulse[0] = 1.0
    ours = synth.resonators(impulse, SR, freqs_hz=[freq], decays_s=[decay])
    envelope_ours = np.abs(ours[: SR // 4]).max()
    envelope_oracle = np.abs(oracle[: SR // 4]).max()
    a = ours[: SR // 4] / envelope_ours
    b = oracle[: SR // 4] / envelope_oracle
    lag = int(np.argmax(np.correlate(a[:2000], b[:2000], mode="full"))) - 1999
    b = np.roll(b, lag)
    assert abs(np.corrcoef(a[100:], b[100:])[0, 1]) > 0.99
    later = slice(int(0.2 * SR), int(0.25 * SR))
    ratio_ours = np.abs(ours[later]).max() / envelope_ours
    ratio_oracle = np.abs(oracle[later]).max() / envelope_oracle
    assert 20 * math.log10(ratio_ours / ratio_oracle) == pytest.approx(0.0, abs=1.5)


def harmonic_levels_db(signal, freq, count):
    n = len(signal)
    power = np.abs(np.fft.rfft(signal * np.hanning(n)))
    freqs = np.fft.rfftfreq(n, 1 / SR)
    levels = [power[np.abs(freqs - k * freq) < 5].max() for k in range(1, count + 1)]
    return 20 * np.log10(np.array(levels) / levels[0])


def test_saw_harmonic_profile_matches_csound_vco2(tmp_path):
    freq = 1000.0
    oracle = render_csound(tmp_path, f"aout vco2 0.5, {freq}\n out aout", 1.0)
    ours = synth.saw(freq, SR, frames=len(oracle))
    diff = harmonic_levels_db(ours, freq, 12) - harmonic_levels_db(oracle, freq, 12)
    # Harmonics agree through 6 kHz; PolyBLEP then rolls off slightly faster than vco2's
    # near-ideal band limiting (documented in synth.saw): monotonic, under 2.5 dB at 12 kHz.
    assert np.max(np.abs(diff[:6])) < 0.5
    assert np.all(np.diff(diff) <= 0.01) and diff[-1] > -2.5


@pytest.mark.parametrize("resonance", [0.0, 0.5, 0.9])
def test_ladder_small_signal_response_matches_csound_moogladder(tmp_path, resonance):
    from tactus import dsp

    cutoff = 1200.0
    for i, freq in enumerate((150.0, 600.0, 1200.0, 2400.0, 6000.0)):
        oracle = render_csound(
            tmp_path,
            f"ain poscil 0.001, {freq}\n aout moogladder ain, {cutoff}, {resonance}\n out aout",
            1.0,
        )
        tone = 0.001 * synth.sine(freq, SR, frames=len(oracle))
        ours = dsp.ladder(tone, SR, cutoff_hz=cutoff, resonance=resonance)
        steady = slice(SR // 2, len(oracle))
        gain_ours = 20 * math.log10(np.std(ours[steady]) / np.std(tone[steady]))
        gain_oracle = 20 * math.log10(np.std(oracle[steady]) / np.std(tone[steady]))
        assert gain_ours == pytest.approx(gain_oracle, abs=0.3), (freq, gain_ours, gain_oracle)
