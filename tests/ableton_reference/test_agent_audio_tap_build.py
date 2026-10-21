"""Adopted from bschoepke/ableton-live-mcp (MIT), revision 89f3b4e.

Copyright (c) 2026 Ableton Live MCP contributors. See LICENSE in this directory.
Local adaptations: src/tactus/bridges/ableton_support/UPSTREAM.md.
"""

from __future__ import annotations

import json
import importlib.util
from pathlib import Path


def load_builder():
    from tactus.bridges.ableton_support._vendor import build_audio_tap
    return build_audio_tap


def test_agent_audio_tap_sources_are_valid_json():
    patch = json.loads(Path(__file__).resolve().parents[2].joinpath("src/tactus/bridges/ableton_support/m4l/AgentAudioTap.maxpat").read_text(encoding="utf-8"))
    boxes = patch["patcher"]["boxes"]
    texts = {box["box"].get("text") for box in boxes}
    assert "sfrecord~ 2" in texts
    assert "js agent_audio_tap.js" in texts
    assert "notein" in texts


def test_agent_audio_tap_builds_amxd_container(tmp_path):
    builder = load_builder()
    output = tmp_path / "AgentAudioTap.amxd"
    command_file = tmp_path / "agent_audio_tap_command.json"
    builder.build_amxd(Path(__file__).resolve().parents[2].joinpath("src/tactus/bridges/ableton_support/m4l/AgentAudioTap.maxpat"), output, command_file)
    data = output.read_bytes()
    assert data.startswith(b"ampf\x04\x00\x00\x00aaaameta")
    assert b"Agent Audio Tap" in data
    assert b"sfrecord~ 2" in data
    assert builder.max_arg(command_file).encode("utf-8") in data


def test_agent_audio_tap_js_has_cross_platform_command_file_default():
    source = Path(__file__).resolve().parents[2].joinpath("src/tactus/bridges/ableton_support/m4l/agent_audio_tap.js").read_text(encoding="utf-8")
    assert "jsarguments" in source
    assert "scheduleStartRecording" in source
    assert "startTask.schedule(500)" in source
    assert "/tmp/agent_audio_tap_command.json" not in source
