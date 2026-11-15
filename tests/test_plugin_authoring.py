"""Opt-in native behavior checks for the copied transparent and editor examples."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).parents[1]


def _build_plugin(tmp_path_factory, *, editor=False):
    source = os.environ.get("TACTUS_JUCE_SOURCE")
    if not source:
        pytest.skip("Set TACTUS_JUCE_SOURCE to a pinned JUCE checkout for a native build")
    if not shutil.which("cmake"):
        pytest.skip("The native plugin starter requires CMake and a C++ toolchain")
    from pedalboard import load_plugin

    work = tmp_path_factory.mktemp("plugin authoring")
    project = work / "copied starter"
    shutil.copytree(ROOT / "skills/plugin/assets", project)
    if editor:
        for filename in ("Processor.cpp", "ParameterControl.h"):
            shutil.copy2(project / "editor-example" / filename, project / filename)
    build = work / "native build"
    commands = [
        ["cmake", "-S", str(project), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
         f"-DJUCE_SOURCE_DIR={Path(source).resolve()}"],
        ["cmake", "--build", str(build), "--config", "Release",
         "--target", "AudioPlugin_VST3", "--parallel", "2"],
    ]
    if sys.platform == "darwin":
        commands[0].append(f"-DCMAKE_OSX_ARCHITECTURES={platform.machine()}")
    for index, command in enumerate(commands):
        result = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
        log = result.stdout + result.stderr
        (work / f"build-{index}.log").write_text(log)
        assert result.returncode == 0, log[-6000:]
    bundle = build / "AudioPlugin_artefacts/Release/VST3/Audio Study.vst3"
    plugin = load_plugin(str(bundle))
    assert plugin.is_effect
    return plugin


@pytest.fixture(scope="module")
def starter_plugin(tmp_path_factory):
    return _build_plugin(tmp_path_factory)


@pytest.fixture(scope="module")
def editor_plugin(tmp_path_factory):
    return _build_plugin(tmp_path_factory, editor=True)


@pytest.mark.parametrize("rate", [44100, 48000])
@pytest.mark.parametrize("channels", [1, 2])
def test_copied_starter_preserves_audio(starter_plugin, rate, channels):
    """Compilation success alone does not establish an audio-transparent starter."""
    signal = np.random.default_rng(91).uniform(-0.6, 0.6, (511, channels)).astype(np.float32)
    before = signal.copy()
    actual = starter_plugin.process(signal, rate, buffer_size=31, reset=True)
    np.testing.assert_array_equal(actual, before)
    np.testing.assert_array_equal(signal, before)


@pytest.mark.parametrize("rate", [44100, 48000])
@pytest.mark.parametrize("channels", [1, 2])
def test_copied_editor_example_gain(editor_plugin, rate, channels):
    """The editor example's real parameter affects native sound in physical units."""
    from tactus import fx

    signal = np.random.default_rng(44).uniform(-0.5, 0.5, (511, channels)).astype(np.float32)
    fx.set_param(editor_plugin, "level_db", -12, unit="dB")
    result = editor_plugin.process(signal, rate, buffer_size=31, reset=True)
    np.testing.assert_allclose(result, signal * 10 ** (-12 / 20), rtol=1e-5, atol=1e-7)


def test_copied_editor_example_native_state(editor_plugin):
    """Saved processor state restores sound independently of editor lifetime."""
    from tactus import fx

    signal = np.full((256, 2), 0.2, dtype=np.float32)
    fx.set_param(editor_plugin, "level_db", -9.5, unit="dB")
    state = editor_plugin.raw_state
    expected = editor_plugin.process(signal, 48000, reset=True)
    fx.set_param(editor_plugin, "level_db", 3, unit="dB")
    editor_plugin.raw_state = state
    np.testing.assert_array_equal(editor_plugin.process(signal, 48000, reset=True), expected)
