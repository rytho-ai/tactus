"""Exercise fx.set_param (fake VST-style params + built-ins) and fx.process_automated."""

from __future__ import annotations

from pathlib import Path

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


def test_set_param_continuous_out_of_range_message_includes_units():
    plugin = FakePlugin({"level": FakeParam(min_value=0.0, max_value=100.0, units="%")})
    with pytest.raises(ValueError, match=r"\[0.0, 100.0\].*%"):
        fx.set_param(plugin, "level", 500.0)


def test_set_param_unknown_discrete_label_message_has_samples_and_units():
    plugin = FakePlugin(
        {
            "osc_2_pitch": FakeParam(
                valid_values=["-12 semitones", "0 semitones", "7 semitones"],
                units="semitones",
            )
        }
    )
    with pytest.raises(ValueError) as excinfo:
        fx.set_param(plugin, "osc_2_pitch", 7, unit="furlongs")
    message = str(excinfo.value)
    assert "semitones" in message
    assert "-12 semitones" in message or "0 semitones" in message


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
# describe / format_table
# ---------------------------------------------------------------------------


def _describe_fake_plugin():
    return FakePlugin(
        {
            "cutoff": FakeParam(min_value=20.0, max_value=20000.0, units="Hz"),
            "amp_env_sustain": FakeParam(min_value=0.0, max_value=100.0, units="%"),
            "mode": FakeParam(valid_values=["Off", "Sync", "Free"]),
            "high_quality_mode": FakeParam(valid_values=[False, True]),
            "transpose": FakeParam(
                valid_values=[f"{i} semitones" for i in range(-24, 25)], units="semitones"
            ),
        }
    )


def test_describe_covers_range_labels_boolean_and_units():
    plugin = _describe_fake_plugin()
    plugin.cutoff = 1000.0
    plugin.amp_env_sustain = 1.0
    plugin.mode = "Sync"
    plugin.high_quality_mode = True

    rows = {row["name"]: row for row in fx.describe(plugin)}

    assert rows["cutoff"]["kind"] == "range"
    assert rows["cutoff"]["units"] == "Hz"
    assert rows["cutoff"]["min"] == 20.0
    assert rows["cutoff"]["max"] == 20000.0
    assert rows["cutoff"]["value"] == 1000.0

    assert rows["amp_env_sustain"]["kind"] == "range"
    assert rows["amp_env_sustain"]["units"] == "%"
    assert rows["amp_env_sustain"]["max"] == 100.0
    assert rows["amp_env_sustain"]["value"] == 1.0

    assert rows["mode"]["kind"] == "labels"
    assert rows["mode"]["valid_values"] == ["Off", "Sync", "Free"]
    assert rows["mode"]["value"] == "Sync"

    assert rows["high_quality_mode"]["kind"] == "boolean"
    assert rows["high_quality_mode"]["value"] is True

    # sorted by name
    assert list(rows.keys()) == sorted(rows.keys())


def test_describe_contains_filter_is_case_insensitive():
    plugin = _describe_fake_plugin()
    rows = fx.describe(plugin, contains="SUSTAIN")
    assert [row["name"] for row in rows] == ["amp_env_sustain"]


def test_describe_truncates_long_valid_values_and_reports_count():
    plugin = _describe_fake_plugin()
    rows = {row["name"]: row for row in fx.describe(plugin)}
    transpose = rows["transpose"]
    assert transpose["valid_values_count"] == 49
    assert len(transpose["valid_values"]) == 12


def test_describe_builtin_plugin_lists_settable_attributes_with_values():
    rev = pedalboard.Reverb(room_size=0.6, wet_level=0.25)
    rows = {row["name"]: row for row in fx.describe(rev)}

    for name in ("room_size", "wet_level", "damping", "width", "dry_level"):
        assert name in rows, f"missing {name}"

    assert rows["room_size"]["value"] == pytest.approx(0.6)
    assert rows["wet_level"]["value"] == pytest.approx(0.25)
    assert rows["room_size"]["kind"] == "range"
    # read-only helper properties should not appear
    assert "is_effect" not in rows
    assert "is_instrument" not in rows


def test_format_table_contains_every_row_name():
    plugin = _describe_fake_plugin()
    rows = fx.describe(plugin)
    table = fx.format_table(rows)
    for row in rows:
        assert row["name"] in table


def test_format_table_truncated_valid_values_show_more_count():
    plugin = _describe_fake_plugin()
    rows = fx.describe(plugin, contains="transpose")
    table = fx.format_table(rows)
    assert "more" in table


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
# internal helpers: latency reports and block framing
# ---------------------------------------------------------------------------


class _StubPluginWithLatency:
    def __init__(self, latency):
        self.reported_latency_samples = latency


class _StubChain(list):
    """A list-like stand-in for pedalboard.Pedalboard, iterable over stub plugins."""


def test_latency_reports_collect_external_plugins():
    chain = _StubChain([_StubPluginWithLatency(128), _StubPluginWithLatency(64), pedalboard.Gain()])
    assert fx._latencies(chain) == (128, 64)


def test_latency_reports_omit_native_plugins():
    assert fx._latencies(pedalboard.Gain()) == ()


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

    def __call__(
        self, messages, *, duration, sample_rate, num_channels, buffer_size=8192, reset=True
    ):
        self.calls.append(
            {
                "messages": list(messages),
                "duration": duration,
                "sample_rate": sample_rate,
                "num_channels": num_channels,
                "buffer_size": buffer_size,
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


def test_render_instrument_renders_in_small_blocks_by_default():
    # Pedalboard's 8192-frame default applies pitch bend and CC at the start of the block
    # containing them; the small default keeps them near their stated time.
    plugin = _FakeInstrumentPlugin()
    fx.render_instrument(plugin, [], duration=1.0, sample_rate=1000, warmup_seconds=0.2)
    assert [call["buffer_size"] for call in plugin.calls] == [64, 64]

    plugin = _FakeInstrumentPlugin()
    fx.render_instrument(
        plugin, [], duration=1.0, sample_rate=1000, warmup_seconds=0.0, buffer_size=256
    )
    assert plugin.calls[0]["buffer_size"] == 256


def test_render_instrument_rejects_non_positive_buffer_size():
    with pytest.raises(ValueError, match="buffer_size"):
        fx.render_instrument(
            _FakeInstrumentPlugin(), [], duration=1.0, sample_rate=1000, buffer_size=0
        )


_DEXED = Path.home() / ".vst3" / "Dexed.vst3"


@pytest.mark.skipif(not _DEXED.exists(), reason="needs the Dexed VST3 instrument")
def test_render_instrument_pitch_bend_lands_on_time_with_a_real_plugin():
    import mido
    import pedalboard

    rate, bend_at = 48000, 1.02

    def render(with_bend):
        plugin = pedalboard.load_plugin(str(_DEXED))
        msgs = [mido.Message("note_on", note=43, velocity=100, time=0.1)]
        if with_bend:
            msgs.append(mido.Message("pitchwheel", pitch=8191, time=bend_at))
        msgs.append(mido.Message("note_off", note=43, time=1.8))
        return fx.render_instrument(plugin, msgs, duration=2.0, sample_rate=rate)

    diff = np.abs(render(True) - render(False)).max(axis=1)
    first = int(np.flatnonzero(diff > 1e-6)[0])
    assert abs(first - bend_at * rate) <= 0.002 * rate  # within 2 ms, not a block early


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


# ---------------------------------------------------------------------------
# fit_rms


def _rms_dbfs(x: np.ndarray) -> float:
    ms = float(np.mean(np.square(x.astype(np.float64))))
    return 20 * np.log10(np.sqrt(ms)) if ms > 0 else -np.inf


def _peaky_drum_hits(rng, n_frames: int, sample_rate: int = 48000, hits_per_sec: float = 6.0):
    """Synthetic drum-sum-like material without needing a fixture file: a continuous low-level
    bed (like combined hats/room, always present) plus frequent near-unity decaying bursts
    (like kick/snare transients) -- high crest factor, like a real drum sum. Stereo, so the
    ceiling/RMS-across-channels behavior is exercised too."""
    out = (rng.standard_normal((n_frames, 2)) * 0.12).astype(np.float64)
    burst_len = int(sample_rate * 0.025)
    decay = np.exp(-np.arange(burst_len) / (sample_rate * 0.008))
    n_hits = int(n_frames / sample_rate * hits_per_sec)
    positions = np.linspace(0, n_frames - burst_len - 1, n_hits).astype(int)
    for i, pos in enumerate(positions):
        peak = 0.85 + 0.15 * (i % 3 == 0)  # every third hit near-full-scale (kick-like)
        noise = rng.standard_normal(burst_len)
        burst = peak * decay * noise / np.max(np.abs(noise))
        out[pos : pos + burst_len, 0] += burst
        out[pos : pos + burst_len, 1] += burst * 0.9
    return out.astype(np.float32)


def test_fit_rms_hits_target_and_ceiling():
    rng = np.random.default_rng(0)
    x = rng.standard_normal(48000 * 2).astype(np.float32) * 0.01
    y = fx.fit_rms(x, 48000, target_dbfs=-14.0, ceiling_dbfs=-1.0)
    assert abs(_rms_dbfs(y) - (-14.0)) <= 0.05
    assert float(np.max(np.abs(y))) <= 10 ** (-1.0 / 20) + 1e-6


def test_fit_rms_loud_input_gets_limited_not_just_scaled():
    rng = np.random.default_rng(1)
    x = rng.standard_normal(48000).astype(np.float32) * 0.9  # already very loud/peaky
    y = fx.fit_rms(x, 48000, target_dbfs=-12.0, ceiling_dbfs=-1.0)
    assert abs(_rms_dbfs(y) - (-12.0)) <= 0.05
    assert float(np.max(np.abs(y))) <= 10 ** (-1.0 / 20) + 1e-6


def test_fit_rms_silence_passthrough():
    x = np.zeros(1000, dtype=np.float32)
    y = fx.fit_rms(x, 48000, target_dbfs=-14.0)
    assert np.allclose(y, 0)


def test_fit_rms_stereo_measures_all_channels_together():
    rng = np.random.default_rng(2)
    x = rng.standard_normal((48000, 2)).astype(np.float32) * 0.05
    y = fx.fit_rms(x, 48000, target_dbfs=-14.0, ceiling_dbfs=-1.0)
    assert abs(_rms_dbfs(y) - (-14.0)) <= 0.05
    assert float(np.max(np.abs(y))) <= 10 ** (-1.0 / 20) + 1e-6


def test_fit_rms_unreachable_target_raises():
    rng = np.random.default_rng(3)
    x = rng.standard_normal(4800).astype(np.float32) * 0.1
    # RMS can never exceed peak, and peak can never exceed the ceiling -- asking for a target
    # louder than the ceiling itself is unreachable at any pre-gain.
    with pytest.raises(ValueError, match="could not reach"):
        fx.fit_rms(x, 48000, target_dbfs=-2.0, ceiling_dbfs=-6.0)


def test_fit_rms_no_flat_top_on_peaky_drum_material():
    """The plan's no-flat-top criterion: unlike pedalboard.Limiter (which left 675-2641
    samples flat at the ceiling on peaky material in the probe), fewer than 0.01% of samples
    should land within 0.01 dB of the ceiling."""
    rng = np.random.default_rng(4)
    x = _peaky_drum_hits(rng, n_frames=48000 * 8)
    ceiling_dbfs = -1.0
    y = fx.fit_rms(x, 48000, target_dbfs=-14.0, ceiling_dbfs=ceiling_dbfs)

    ceiling_lin = 10 ** (ceiling_dbfs / 20.0)
    near_ceiling_lin = 10 ** ((ceiling_dbfs - 0.01) / 20.0)
    flat_top = int(np.sum(np.abs(y) >= near_ceiling_lin))
    assert flat_top / y.size < 0.0001, f"{flat_top} of {y.size} samples within 0.01 dB of ceiling"
    assert float(np.max(np.abs(y))) <= ceiling_lin + 1e-6
    assert abs(_rms_dbfs(y) - (-14.0)) <= 0.05


def test_owned_dsp_aliases_preserve_existing_fx_imports():
    from tactus import dsp

    assert fx.varispeed is dsp.varispeed
    assert fx.fit_rms is dsp.fit_rms


def test_process_keeps_tactus_layout_tail_and_determinism():
    rng = np.random.default_rng(4)
    stereo = rng.normal(0, 0.1, (4800, 2))
    quiet = fx.process(pedalboard.Gain(gain_db=-6.0), stereo, 48000)
    assert quiet.shape == (4800, 2) and quiet.dtype == np.float32
    np.testing.assert_allclose(quiet, stereo * 10 ** (-6 / 20), atol=1e-6)
    mono = fx.process(pedalboard.Gain(gain_db=0.0), stereo[:, 0], 48000)
    assert mono.shape == (4800,)
    wet = fx.process(pedalboard.Reverb(room_size=0.8), stereo, 48000, tail_seconds=0.5)
    assert wet.shape == (4800 + 24000, 2) and np.max(np.abs(wet[4800:])) > 0
    np.testing.assert_array_equal(
        wet, fx.process(pedalboard.Reverb(room_size=0.8), stereo, 48000, tail_seconds=0.5)
    )
    chain = pedalboard.Pedalboard([pedalboard.Gain(gain_db=-6.0), pedalboard.Gain(gain_db=6.0)])
    np.testing.assert_allclose(fx.process(chain, stereo, 48000), stereo, atol=1e-6)
    assert fx.process(pedalboard.Gain(), stereo[:0], 48000).shape == (0, 2)
    with pytest.raises(ValueError, match="ambiguous"):
        fx.process(pedalboard.Gain(), np.zeros((2, 2)), 48000)
    with pytest.raises(ValueError, match="tail_seconds"):
        fx.process(pedalboard.Gain(), stereo, 48000, tail_seconds=-1)
