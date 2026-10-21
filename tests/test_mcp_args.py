"""The default MCP setup exposes both DAWs without breaking targeted launchers."""

from pathlib import Path

import pytest

from tactus import _mcp_args
from tactus.cli import main as tactus_main


def resolve(daw=None, path=None, resource_path=None, ableton_path=None,
            reaper_path=None, live_path=None):
    return _mcp_args.connection_kwargs(daw=daw, path=path,
                                       resource_path=resource_path,
                                       ableton_path=ableton_path,
                                       reaper_path=reaper_path, live_path=live_path)


def test_short_names_discover_installed_directories(tmp_path, monkeypatch):
    reaper = tmp_path / "REAPER"
    live = tmp_path / "TactusBridge"
    reaper.mkdir()
    live.mkdir()
    monkeypatch.setattr(_mcp_args, "_candidates", lambda daw: [
        tmp_path / "missing", reaper if daw == "reaper" else live])

    assert resolve("reaper") == {"resource_path": reaper}
    assert resolve("live") == {"ableton_path": live}
    assert resolve() == {"resource_path": reaper, "ableton_path": live,
                         "allow_missing": True}


def test_explicit_path_and_legacy_flags(tmp_path):
    assert resolve("reaper", tmp_path) == {"resource_path": tmp_path}
    assert resolve("live", tmp_path) == {"ableton_path": tmp_path}
    assert resolve(resource_path=tmp_path) == {"resource_path": tmp_path}
    assert resolve(ableton_path=tmp_path) == {"ableton_path": tmp_path}
    assert resolve(reaper_path=tmp_path / "one", live_path=tmp_path / "two") == {
        "resource_path": tmp_path / "one", "ableton_path": tmp_path / "two",
        "allow_missing": True}


def test_missing_or_mixed_target_explains_override(tmp_path, monkeypatch):
    missing = tmp_path / "missing"
    monkeypatch.setattr(_mcp_args, "_candidates", lambda daw: [missing])
    with pytest.raises(ValueError, match="Use --path DIR"):
        resolve("live")
    assert resolve() == {"resource_path": missing, "ableton_path": missing,
                         "allow_missing": True}
    with pytest.raises(ValueError, match="--reaper-path or --live-path"):
        resolve(path=missing)
    with pytest.raises(ValueError, match="do not combine"):
        resolve("reaper", resource_path=Path("legacy"))


def test_main_cli_accepts_short_target_before_server_start(tmp_path, capsys):
    assert tactus_main(["mcp", "live", "--path", str(tmp_path / "missing")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ableton connection directory does not exist" in captured.err
