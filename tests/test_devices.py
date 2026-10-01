"""Behaviour of tactus.devices: sampler, pads and steps."""

import importlib.util
import shutil
from pathlib import Path

import numpy as np
import pytest

import tactus
from tactus import synth, timing
from tactus.devices import pads, sampler, steps

SR = 48000
C4_HZ = 440.0 * 2 ** (-9 / 12)
DEVICES = Path(tactus.__file__).parent / "devices"


def peak_hz(signal):
    n = len(signal)
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(n), 8 * n))
    return np.argmax(spectrum) * SR / (8 * n)


def test_sampler_note_transposes_from_root_and_scales_velocity():
    source = synth.sine(C4_HZ, SR, frames=2 * SR)
    for pitch, expected in ((60, C4_HZ), (67, C4_HZ * 2 ** (7 / 12)), (48.5, C4_HZ * 2 ** (-11.5 / 12))):
        note = sampler.note(source, SR, pitch, 0.5, root=60)
        assert abs(peak_hz(note[2000:20000]) - expected) < 0.5
    flat_root = sampler.note(source, SR, 60, 0.5, root=60.31)
    assert abs(1200 * np.log2(peak_hz(flat_root[2000:20000]) / C4_HZ) + 31) < 2
    loud = sampler.note(source, SR, 60, 0.5)
    np.testing.assert_allclose(sampler.note(source, SR, 60, 0.5, 0.25), loud * 0.25)
    assert len(loud) == round((0.5 + 0.08) * SR)
    assert loud[0] == 0 and abs(loud[-1]) < 0.01


def test_sampler_start_offset_envelope_and_source_end():
    ramp = np.arange(SR, dtype=float)
    skipped = sampler.note(ramp, SR, 60, 0.1, start_s=0.25, attack_s=0.0, release_s=0.0)
    np.testing.assert_allclose(skipped, 12000 + np.arange(4800))
    short = np.ones(1000)
    ended = sampler.note(short, SR, 60, 0.1, attack_s=0.0, release_s=0.0)
    assert np.all(ended[:1000] == 1) and np.all(ended[1000:] == 0)
    shaped = sampler.note(np.ones(SR), SR, 60, 0.1, attack_s=0.01, release_s=0.02)
    assert shaped[240] == pytest.approx(0.5) and shaped[2000] == 1
    assert shaped[4800 + 480] == pytest.approx(0.5)
    with pytest.raises(ValueError, match="duration_s"):
        sampler.note(short, SR, 60, 0.0)


def test_sampler_loop_sustains_past_the_source_without_a_click():
    source = synth.sine(C4_HZ, SR, frames=SR // 2)
    period = 1 / C4_HZ
    looped = sampler.note(source, SR, 64, 3.0, loop=(0.1, 0.1 + 40 * period), xfade_s=0.01)
    assert len(looped) == round(3.08 * SR)
    body = looped[1000 : 3 * SR]
    assert np.min(np.abs(body).reshape(-1, 500).max(axis=1)) > 0.9  # still sounding to the end
    step = 2 * np.pi * C4_HZ * 2 ** (4 / 12) / SR
    assert np.max(np.abs(np.diff(body))) < 1.2 * step  # no jump at any wrap, the first included
    unlooped = sampler.note(source, SR, 64, 3.0)
    assert np.all(unlooped[SR:] == 0)
    with pytest.raises(ValueError, match="loop"):
        sampler.note(source, SR, 60, 1.0, loop=(0.4, 0.9))


def test_sampler_stereo_and_play_places_notes_and_keeps_inputs():
    stereo = np.column_stack((np.ones(SR), -np.ones(SR)))
    before = stereo.copy()
    part = sampler.play(
        stereo, SR, [(0.0, 60, 0.1, 1.0), (0.5, 60, 0.1, 0.5), (5.0, 60, 0.1, 1.0)],
        frames=SR, attack_s=0.0, release_s=0.0,
    )
    assert part.shape == (SR, 2)
    assert np.all(part[:4800, 0] == 1) and np.all(part[:4800, 1] == -1)
    assert np.all(part[4800:24000] == 0) and np.all(part[24000:28800, 0] == 0.5)
    np.testing.assert_array_equal(stereo, before)
    overlapping = sampler.play(np.ones(SR), SR, [(0.0, 60, 0.2, 1.0), (0.1, 60, 0.2, 1.0)],
                               frames=SR, attack_s=0.0, release_s=0.0)
    assert overlapping[6000] == 2 and overlapping.shape == (SR,)


def test_pads_slices_by_count_and_times():
    sample = np.arange(1000, dtype=float)
    parts = pads.slices(sample, SR, count=4)
    assert [len(p) for p in parts] == [250, 250, 250, 250]
    np.testing.assert_array_equal(np.concatenate(parts), sample)
    cut = pads.slices(np.arange(SR, dtype=float), SR, at_s=[0.25, 0.5])
    assert [len(p) for p in cut] == [12000, 12000, 24000] and cut[1][0] == 12000
    parts[0][:] = -1
    assert sample[0] == 0
    with pytest.raises(ValueError, match="exactly one"):
        pads.slices(sample, SR)
    with pytest.raises(ValueError, match="inside"):
        pads.slices(sample, SR, at_s=[0.5, 0.25])


def test_pads_play_placement_stems_tuning_and_unknown_pad():
    kit = {"kick": np.ones(100), "hat": np.column_stack((np.ones(50), np.zeros(50)))}
    hits = [(0.0, "kick", 1.0), (0.01, "hat", 0.5), (0.5, "kick", 0.25)]
    mix = pads.play(hits, kit, SR, frames=SR)
    assert mix.shape == (SR, 2)
    assert mix[0, 0] == 1 and mix[0, 1] == 1 and mix[480, 0] == 0.5 and mix[480, 1] == 0
    assert mix[24000, 0] == 0.25 and mix[24100, 0] == 0
    stems = pads.play(hits, kit, SR, frames=SR, per_pad=True)
    np.testing.assert_array_equal(stems["kick"] + stems["hat"], mix)
    mono = pads.play([(0.0, "a", 1.0)], {"a": np.ones(100)}, SR, frames=200)
    assert mono.shape == (200,)
    tone = synth.sine(1000.0, SR, frames=SR)
    up = pads.play([(0.0, "t", 1.0)], {"t": tone}, SR, frames=SR, tune={"t": 12})
    assert abs(peak_hz(up[1000:20000]) - 2000) < 2 and np.all(up[SR // 2 + 10 :] == 0)
    with pytest.raises(ValueError, match="unknown pad"):
        pads.play([(0.0, "snare", 1.0)], kit, SR, frames=SR)


def test_pads_choke_cuts_the_ringing_hit_of_its_group_only():
    kit = {"open": np.ones(SR // 2), "closed": np.ones(100), "kick": np.ones(SR // 2)}
    hits = [(0.0, "open", 1.0), (0.0, "kick", 1.0), (0.1, "closed", 1.0)]
    stems = pads.play(hits, kit, SR, frames=SR, choke={"open": "hat", "closed": "hat"}, fade_s=0.005, per_pad=True)
    assert stems["open"][4799] == 1 and stems["open"][4800 + 240] == 0
    assert 0 < stems["open"][4800 + 120] < 1
    assert np.all(stems["kick"][: SR // 2] == 1)
    free = pads.play(hits, kit, SR, frames=SR, per_pad=True)
    assert np.all(free["open"][: SR // 2] == 1)


def test_steps_grid_swing_accents_and_repeats():
    got = steps.events("x... X.x.", bpm=120, steps_per_beat=4)
    assert [round(t, 6) for t, _ in got] == [0.0, 0.5, 0.75]
    assert [v for _, v in got] == [0.7, 1.0, 0.7]
    swung = steps.events("xxxx", bpm=120, swing=0.58)
    expected = [timing.swing(i / 4, 0.58, 0.5) * 0.5 for i in range(4)]
    np.testing.assert_allclose([t for t, _ in swung], expected)
    assert swung[1][0] > 0.125 and swung[2][0] == pytest.approx(0.25)
    twice = steps.events([1.0, 0, 0.3], bpm=60, steps_per_beat=1, repeats=2, start_s=10.0)
    assert twice == [(10.0, 1.0), (12.0, 0.3), (13.0, 1.0), (15.0, 0.3)]
    with pytest.raises(ValueError, match="unknown step"):
        steps.events("x.o.", bpm=120)
    with pytest.raises(ValueError, match="no steps"):
        steps.events("", bpm=120)


def test_steps_hits_notes_and_euclid_bridge():
    assert steps.hits("x.x.", "kick", bpm=120) == [(0.0, "kick", 0.7), (0.25, "kick", 0.7)]
    notes = steps.notes("xxx.", [60, 64], bpm=120, gate=0.5)
    assert [n[1] for n in notes] == [60, 64, 60]
    assert notes[0][2] == pytest.approx(0.0625)
    assert steps.notes("x", 72, bpm=120)[0][1] == 72
    pattern = steps.from_indices(timing.euclid(3, 8), 8, velocity=0.9)
    assert pattern == [0.9, 0, 0, 0.9, 0, 0, 0.9, 0]
    assert len(steps.events(pattern, bpm=120)) == 3
    with pytest.raises(ValueError, match="inside"):
        steps.from_indices([8], 8)


def test_devices_work_together():
    source = synth.sine(C4_HZ, SR, frames=SR)
    melody = sampler.play(source, SR, steps.notes("x.x.x.x.", [60, 67, 72, 67], bpm=120), frames=SR)
    drums = pads.play(steps.hits("x...x...", "k", bpm=120), {"k": np.ones(200)}, SR, frames=SR)
    assert melody.shape == drums.shape == (SR,) and np.isfinite(melody).all()
    assert np.count_nonzero(drums) == 400


@pytest.mark.parametrize("name", ["sampler", "pads", "steps"])
def test_each_device_file_runs_when_copied_alone(tmp_path, name):
    """The import-or-copy contract: one file, copied anywhere, is a working module."""
    copied = tmp_path / f"my_{name}.py"
    shutil.copy(DEVICES / f"{name}.py", copied)
    spec = importlib.util.spec_from_file_location(f"my_{name}", copied)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = copied.read_text()
    assert "from ." not in source and "import tactus._" not in source and "tactus._" not in source
    if name == "sampler":
        assert module.play(np.ones(100), SR, [(0.0, 60, 0.001, 1.0)], frames=100).shape == (100,)
    elif name == "pads":
        assert len(module.slices(np.ones(100), SR, count=4)) == 4
    else:
        assert module.events("x.", bpm=120) == [(0.0, 0.7)]


def test_devices_load_lazily_from_the_package():
    assert tactus.devices.sampler is sampler
    assert set(tactus.devices.__all__) == {"pads", "sampler", "steps"}


def test_steps_wrappers_expose_timing_arguments_and_package_lists_modules():
    import inspect

    for fn in (steps.hits, steps.notes):
        assert {"bpm", "steps_per_beat", "start_s", "repeats", "swing"} <= set(inspect.signature(fn).parameters)
    assert steps.notes("x.", 60, bpm=120, steps_per_beat=2, start_s=1.0) == [(1.0, 60, 0.125, 0.7)]
    assert {"analysis", "devices", "dsp", "synth"} <= set(dir(tactus))
    assert tactus.dsp.svf and tactus.synth.saw


def test_pads_slices_tail_and_whole_kit_tune_and_choke():
    sample = np.arange(SR, dtype=float)
    parts = pads.slices(sample, SR, count=4, tail_s=0.1)
    assert [len(p) for p in parts] == [SR // 4 + SR // 10] * 3 + [SR // 4]
    assert parts[1][0] == SR // 4
    with pytest.raises(ValueError, match="tail_s"):
        pads.slices(sample, SR, count=4, tail_s=-0.1)

    kit = {"a": np.ones(SR), "b": np.ones(SR)}
    hits = [(0.0, "a", 1.0), (0.25, "b", 1.0)]
    whole = pads.play(hits, kit, SR, frames=SR, choke=1, tune=-12.0)
    named = pads.play(hits, kit, SR, frames=SR, choke={"a": 1, "b": 1}, tune={"a": -12.0, "b": -12.0})
    np.testing.assert_array_equal(whole, named)
    assert whole[SR // 2] == 1.0  # pad a was cut by pad b: one voice, not two
