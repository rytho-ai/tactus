"""Exercise fx.set_param (fake VST-style params + built-ins) and fx.process_automated."""

from __future__ import annotations

import numpy as np
import pedalboard
import pytest

from tactus import fx


class FakeParam:
    def __init__(self, valid_values=None, min_value=None, max_value=None, units=None):
        self.valid_values = valid_values or []
        self.min_value = min_value
        self.max_value = max_value
        self.units = units


class FakePlugin:
    """Stands in for a VST3Plugin: a `.parameters` dict plus plain attribute storage."""

    def __init__(self, parameters):
        self.parameters = parameters
        for name in parameters:
            setattr(self, name, None)


# ---------------------------------------------------------------------------
# set_param: discrete VST3-style parameters
# ---------------------------------------------------------------------------


def test_set_param_nearest_ms_label_the_bug_case():
    plugin = FakePlugin(
        {
            "attack": FakeParam(
                valid_values=["8.21 ms", "10.16 ms", "250 ms", "1.00 s", "9.97 s"],
                units="ms",
            )
        }
    )
    chosen = fx.set_param(plugin, "attack", 10, unit="ms")
    assert chosen == "10.16 ms"
    assert plugin.attack == "10.16 ms"


def test_set_param_nearest_label_crosses_units():
    plugin = FakePlugin(
        {
            "attack": FakeParam(
                valid_values=["8.21 ms", "10.16 ms", "250 ms", "1.00 s", "9.97 s"],
                units="ms",
            )
        }
    )
    assert fx.set_param(plugin, "attack", 1, unit="s") == "1.00 s"


def test_set_param_frequency_labels_hz_and_khz():
    plugin = FakePlugin(
        {"cutoff": FakeParam(valid_values=["120 Hz", "500 Hz", "1.20 kHz", "5.00 kHz"], units="Hz")}
    )
    assert fx.set_param(plugin, "cutoff", 1100, unit="Hz") == "1.20 kHz"
    assert fx.set_param(plugin, "cutoff", 5, unit="kHz") == "5.00 kHz"


def test_set_param_cents_labels():
    plugin = FakePlugin(
        {"tune": FakeParam(valid_values=["-100.0 cents", "0.0 cents", "50.0 cents"], units="cents")}
    )
    assert fx.set_param(plugin, "tune", 40, unit="cents") == "50.0 cents"


def test_set_param_exact_string_match():
    plugin = FakePlugin({"mode": FakeParam(valid_values=["Off", "Sync", "Free"])})
    assert fx.set_param(plugin, "mode", "Sync") == "Sync"


def test_set_param_exact_string_match_failure_lists_valid_values():
    plugin = FakePlugin({"mode": FakeParam(valid_values=["Off", "Sync", "Free"])})
    with pytest.raises(ValueError, match="Off"):
        fx.set_param(plugin, "mode", "Nope")


def test_set_param_unit_family_mismatch():
    plugin = FakePlugin(
        {"attack": FakeParam(valid_values=["8.21 ms", "10.16 ms", "250 ms"], units="ms")}
    )
    with pytest.raises(ValueError):
        fx.set_param(plugin, "attack", 100, unit="Hz")


def test_set_param_semitones_labels_unknown_unit_family():
    plugin = FakePlugin(
        {
            "osc_2_pitch": FakeParam(
                valid_values=["-12 semitones", "0 semitones", "7 semitones"],
                units="semitones",
            )
        }
    )
    assert fx.set_param(plugin, "osc_2_pitch", 7, unit="semitones") == "7 semitones"
    assert fx.set_param(plugin, "osc_2_pitch", -10, unit="semitones") == "-12 semitones"


def test_set_param_semitones_singular_request_unit():
    plugin = FakePlugin(
        {
            "osc_2_pitch": FakeParam(
                valid_values=["-12 semitones", "0 semitones", "7 semitones"],
                units="semitones",
            )
        }
    )
    assert fx.set_param(plugin, "osc_2_pitch", 7, unit="semitone") == "7 semitones"


def test_set_param_voices_labels():
    plugin = FakePlugin(
        {"voice_count": FakeParam(valid_values=["1 voice", "2 voices", "4 voices"], units="voices")}
    )
    assert fx.set_param(plugin, "voice_count", 3.4, unit="voices") == "4 voices"
    assert fx.set_param(plugin, "voice_count", 1, unit="voice") == "1 voice"


def test_set_param_unknown_unit_matches_no_label_raises():
    plugin = FakePlugin(
        {
            "osc_2_pitch": FakeParam(
                valid_values=["-12 semitones", "0 semitones", "7 semitones"],
                units="semitones",
            )
        }
    )
    with pytest.raises(ValueError, match="semitones"):
        fx.set_param(plugin, "osc_2_pitch", 7, unit="furlongs")


def test_set_param_unknown_name_lists_close_matches():
    plugin = FakePlugin({"attack_ms": FakeParam(valid_values=["1 ms", "2 ms"])})
    with pytest.raises(KeyError) as excinfo:
        fx.set_param(plugin, "atack_ms", 1, unit="ms")
    message = str(excinfo.value)
    assert "attack_ms" in message


def test_set_param_continuous_out_of_range():
    plugin = FakePlugin({"level": FakeParam(min_value=0.0, max_value=1.0)})
    with pytest.raises(ValueError, match=r"\[0.0, 1.0\]"):
        fx.set_param(plugin, "level", 5.0)


def test_set_param_continuous_in_range():
    plugin = FakePlugin({"level": FakeParam(min_value=0.0, max_value=1.0)})
    assert fx.set_param(plugin, "level", 0.5) == 0.5
    assert plugin.level == 0.5


def test_set_param_builtin_plugin():
    rev = pedalboard.Reverb()
    assert fx.set_param(rev, "wet_level", 0.4) == 0.4
    assert rev.wet_level == pytest.approx(0.4)


def test_set_param_builtin_plugin_rejects_unit():
    rev = pedalboard.Reverb()
    with pytest.raises(ValueError):
        fx.set_param(rev, "wet_level", 0.4, unit="ms")


def test_set_param_builtin_unknown_attribute():
    rev = pedalboard.Reverb()
    with pytest.raises(KeyError):
        fx.set_param(rev, "not_a_real_param", 1.0)


# ---------------------------------------------------------------------------
# process_automated
# ---------------------------------------------------------------------------


def _tone(seconds=1.0, rate=44100, freq=220.0):
    t = np.arange(int(seconds * rate)) / rate
    return (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _stereo(mono):
    return np.stack([mono, mono], axis=1)


def test_process_automated_matches_single_shot_call_with_noop_update():
    rate = 44100
    audio = _stereo(_tone(0.5, rate))

    chain_blocked = pedalboard.Pedalboard(
        [pedalboard.Gain(gain_db=-3.0), pedalboard.LowpassFilter(cutoff_frequency_hz=2000.0)]
    )
    chain_single = pedalboard.Pedalboard(
        [pedalboard.Gain(gain_db=-3.0), pedalboard.LowpassFilter(cutoff_frequency_hz=2000.0)]
    )

    out_blocked = fx.process_automated(chain_blocked, audio, rate, update=lambda t: None)
    out_single = chain_single(audio, rate, reset=True)

    assert out_blocked.shape == out_single.shape
    np.testing.assert_allclose(out_blocked, out_single, atol=1e-6)


def test_process_automated_tail_extends_and_is_non_silent():
    rate = 44100
    audio = _tone(0.2, rate)
    chain = pedalboard.Pedalboard([pedalboard.Reverb(room_size=0.9, wet_level=0.8)])

    out = fx.process_automated(chain, audio, rate, update=lambda t: None, tail_seconds=0.5)

    assert out.shape[0] == audio.shape[0] + round(0.5 * rate)
    tail = out[audio.shape[0] :]
    assert np.max(np.abs(tail)) > 1e-5


def test_process_automated_calls_update_with_block_start_times_and_automates_gain():
    rate = 44100
    audio = _tone(1.0, rate, freq=440.0)
    gain = pedalboard.Gain(gain_db=0.0)
    chain = pedalboard.Pedalboard([gain])

    seen_times = []

    def update(t):
        seen_times.append(t)
        gain.gain_db = 0.0 if t < 0.5 else -60.0

    out = fx.process_automated(chain, audio, rate, update, block_seconds=0.02)

    assert seen_times == sorted(seen_times)
    assert seen_times[0] == 0.0

    block_frames = round(0.02 * rate)
    before = out[: round(0.4 * rate)]
    after = out[round(0.6 * rate) : round(0.9 * rate)]
    assert np.max(np.abs(before)) > 0.05
    assert (
        np.max(np.abs(after)) < 0.05 / (10 ** (60 / 20)) * 10
    )  # much quieter, well below -60dB-ish
    assert block_frames > 0


def test_process_automated_mono_roundtrip_shape():
    rate = 44100
    audio = _tone(0.3, rate)
    chain = pedalboard.Pedalboard([pedalboard.Gain(gain_db=-6.0)])

    out = fx.process_automated(chain, audio, rate, update=lambda t: None)

    assert out.ndim == 1
    assert out.shape[0] == audio.shape[0]


def test_process_automated_tiny_remainder_merged_exact_length():
    rate = 1000
    # block_seconds=0.02 -> 20-frame blocks; make total frames leave a 2-frame remainder.
    n = 20 * 5 + 2
    audio = np.zeros((n,), dtype=np.float32)
    chain = pedalboard.Pedalboard([pedalboard.Gain(gain_db=0.0)])

    out = fx.process_automated(chain, audio, rate, update=lambda t: None, block_seconds=0.02)

    assert out.shape[0] == n


# ---------------------------------------------------------------------------
# internal helpers: latency sum/shift, testable without a real VST
# ---------------------------------------------------------------------------


class _StubPluginWithLatency:
    def __init__(self, latency):
        self.reported_latency_samples = latency


class _StubChain(list):
    """A list-like stand-in for pedalboard.Pedalboard, iterable over stub plugins."""


def test_total_latency_sums_over_chain():
    chain = _StubChain([_StubPluginWithLatency(128), _StubPluginWithLatency(64), pedalboard.Gain()])
    assert fx._total_latency(chain) == 192


def test_total_latency_single_plugin_no_attribute_is_zero():
    assert fx._total_latency(pedalboard.Gain()) == 0


def test_block_bounds_merges_tiny_remainder():
    bounds = fx._block_bounds(102, 20)
    assert bounds[-1] == (80, 102)
    assert all(end - start >= 3 for start, end in bounds)


def test_block_bounds_empty():
    assert fx._block_bounds(0, 20) == []


# ---------------------------------------------------------------------------
# render_instrument
# ---------------------------------------------------------------------------


class _FakeInstrumentPlugin:
    """Stands in for a VST3Plugin instrument: records each call and simulates a start
    transient on the first render only (as if the transient is baked into the plugin's
    internal state from prior set_param calls, and warm-up absorbs it)."""

    def __init__(self):
        self.calls = []

    def __call__(self, messages, *, duration, sample_rate, num_channels, reset=True):
        self.calls.append(
            {
                "messages": list(messages),
                "duration": duration,
                "sample_rate": sample_rate,
                "num_channels": num_channels,
                "reset": reset,
            }
        )
        frames = round(duration * sample_rate)
        audio = np.zeros((num_channels, frames), dtype=np.float32)
        if len(self.calls) == 1 and frames > 0:
            audio[:, 0] = 0.09  # simulated start transient, first call only
        return audio


def test_render_instrument_runs_silent_warmup_first():
    plugin = _FakeInstrumentPlugin()
    fx.render_instrument(plugin, [], duration=1.0, sample_rate=1000, warmup_seconds=0.5)

    assert len(plugin.calls) == 2
    assert plugin.calls[0]["messages"] == []
    assert plugin.calls[0]["duration"] == 0.5
    assert plugin.calls[0]["reset"] is True  # default plugin reset for the warm-up call


def test_render_instrument_performance_render_uses_reset_false():
    plugin = _FakeInstrumentPlugin()
    fx.render_instrument(plugin, [], duration=1.0, sample_rate=1000, warmup_seconds=0.5)

    assert plugin.calls[1]["reset"] is False


def test_render_instrument_absorbs_transient_via_warmup():
    plugin = _FakeInstrumentPlugin()
    out = fx.render_instrument(plugin, [], duration=1.0, sample_rate=1000, warmup_seconds=0.5)

    assert np.max(np.abs(out)) == 0.0  # transient landed on the discarded warm-up call


def test_render_instrument_skips_warmup_when_zero():
    plugin = _FakeInstrumentPlugin()
    out = fx.render_instrument(plugin, [], duration=1.0, sample_rate=1000, warmup_seconds=0.0)

    assert len(plugin.calls) == 1
    assert np.max(np.abs(out)) > 0.0  # no warm-up to absorb the transient


def test_render_instrument_transposes_to_tactus_layout_and_exact_length():
    plugin = _FakeInstrumentPlugin()
    out = fx.render_instrument(
        plugin, [], duration=1.5, sample_rate=1000, num_channels=2, warmup_seconds=0.2
    )

    assert out.shape == (1500, 2)
    assert out.dtype == np.float32


def test_render_instrument_passes_messages_through_to_performance_call():
    plugin = _FakeInstrumentPlugin()
    messages = [(b"\x90\x3c\x64", 0.1), (b"\x80\x3c\x00", 0.5)]
    fx.render_instrument(plugin, messages, duration=1.0, sample_rate=1000, warmup_seconds=0.2)

    assert plugin.calls[1]["messages"] == messages


def test_render_instrument_validates_args():
    plugin = _FakeInstrumentPlugin()
    with pytest.raises(ValueError):
        fx.render_instrument(plugin, [], duration=0, sample_rate=1000)
    with pytest.raises(ValueError):
        fx.render_instrument(plugin, [], duration=1.0, sample_rate=0)
    with pytest.raises(ValueError):
        fx.render_instrument(plugin, [], duration=1.0, sample_rate=1000, warmup_seconds=-1)
    with pytest.raises(ValueError):
        fx.render_instrument(plugin, [], duration=1.0, sample_rate=1000, num_channels=3)


# ---------------------------------------------------------------------------
# varispeed


def test_varispeed_unit_speed_is_identity():
    audio = np.random.default_rng(1).standard_normal((1000, 2)).astype(np.float32)
    out = fx.varispeed(audio, 44100, np.ones(1000))
    np.testing.assert_allclose(out, audio, atol=1e-7)


def test_varispeed_half_speed_lowers_pitch_an_octave():
    rate = 8000
    t = np.arange(rate) / rate
    tone = np.sin(2 * np.pi * 440 * t).astype(np.float32)
    out = fx.varispeed(tone, rate, np.full(rate, 0.5))
    spectrum = np.abs(np.fft.rfft(out))
    peak_hz = np.argmax(spectrum) * rate / len(out)
    assert abs(peak_hz - 220) < 2


def test_varispeed_tape_stop_holds_then_silence_past_the_end():
    audio = np.linspace(-1, 1, 100, dtype=np.float32)
    out = fx.varispeed(audio, 1000, np.concatenate([np.ones(50), np.zeros(50)]))
    assert out.shape == (100,)
    assert np.all(out[50:] == out[50])  # speed 0 holds the read position

    fast = fx.varispeed(audio, 1000, np.full(100, 2.0))
    assert np.all(fast[50:] == 0.0)  # read past the end becomes silence


def test_varispeed_rejects_bad_speed():
    audio = np.zeros(10, dtype=np.float32)
    for bad in (np.array([]), np.array([1.0, -0.1]), np.array([np.nan]), np.ones((2, 2))):
        with pytest.raises(ValueError):
            fx.varispeed(audio, 44100, bad)
