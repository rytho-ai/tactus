"""Bundled DAW installation must be repeatable and preserve prior user files."""

import json
import time
from pathlib import Path

from tactus import connect as setup
from tactus._mcp_args import LIVE_SCRIPT_NAME
from tactus.bridges import ableton, reaper
from tactus.cli import main


def test_live_control_surface_name_is_valid_python_import():
    # Live constructs an `import NAME` statement when activating a Remote Script.
    compile(f"import {LIVE_SCRIPT_NAME}", "<live-remote-script>", "exec")


def test_setup_installs_bundled_files_and_check_is_read_only(tmp_path, capsys):
    resource = tmp_path / "REAPER"
    library = tmp_path / "User Library"
    resource.mkdir()
    library.mkdir()
    assert main(["connect", "--check", "--reaper-path", str(resource),
                 "--live-library", str(library)]) == 0
    pending = json.loads(capsys.readouterr().out)
    assert pending["reaper"]["state"] == "not_installed"
    assert pending["live"]["state"] == "not_installed"
    assert not (resource / "Scripts").exists()
    assert not (library / "Remote Scripts").exists()

    assert main(["connect", "--reaper-path", str(resource),
                 "--live-library", str(library)]) == 0
    installed = json.loads(capsys.readouterr().out)
    assert installed["reaper"]["state"] == "installed"
    assert installed["live"]["state"] == "installed"
    assert (resource / "Scripts" / "TactusMCP.lua").read_bytes() == reaper.script().read_bytes()
    for source in ableton.script().glob("*.py"):
        assert (library / "Remote Scripts" / "TactusMCP" / source.name).read_bytes() == source.read_bytes()
    assert setup.connect(reaper_path=resource, live_library=library)["reaper"]["state"] == "installed"
    assert not (resource / ".tactus-backups").exists()


def test_update_backs_up_differing_installed_file(tmp_path):
    resource = tmp_path / "REAPER"
    library = tmp_path / "User Library"
    old_reaper = resource / "Scripts" / "TactusMCP.lua"
    old_live = library / "Remote Scripts" / "TactusMCP" / "bridge.py"
    old_reaper.parent.mkdir(parents=True)
    old_live.parent.mkdir(parents=True)
    old_reaper.write_text("old reaper")
    old_live.write_text("old live")
    check = setup.connect(reaper_path=resource, live_library=library, check=True)
    assert check["reaper"]["state"] == "update_available"
    assert check["live"]["state"] == "update_available"
    assert old_reaper.read_text() == "old reaper"

    result = setup.connect(reaper_path=resource, live_library=library)
    assert (Path(result["reaper"]["backup"]) / "TactusMCP.lua").read_text() == "old reaper"
    assert (Path(result["live"]["backup"]) / "bridge.py").read_text() == "old live"
    assert old_reaper.read_bytes() == reaper.script().read_bytes()
    assert old_live.read_bytes() == (ableton.script() / "bridge.py").read_bytes()


def test_live_setup_keeps_previous_remote_script_during_switch(tmp_path):
    library = tmp_path / "User Library"
    previous = library / "Remote Scripts" / "TactusBridge"
    previous.mkdir(parents=True)
    (previous / "__init__.py").write_text("previous setup")
    report = setup.connect(live_library=library)
    assert report["live"]["previous_name"] == str(previous)
    assert (previous / "__init__.py").read_text() == "previous setup"
    assert (library / "Remote Scripts" / "TactusMCP" / "__init__.py").is_file()


def test_live_setup_reports_which_control_surface_is_active(tmp_path):
    library = tmp_path / "User Library"
    old = library / "Remote Scripts" / "TactusBridge"
    old.mkdir(parents=True)
    setup.connect(live_library=library)
    heartbeat = old / "tactus-bridge" / "instances" / "old" / "heartbeat.json"
    heartbeat.parent.mkdir(parents=True)
    heartbeat.write_text(json.dumps({"protocol": 1, "time": time.time(), "instance": "old"}))
    report = setup.connect(live_library=library, check=True)
    assert report["live"]["active_scripts"] == ["TactusBridge"]
    assert "select TactusMCP" in report["live"]["next_step"]

    heartbeat.unlink()
    new = library / "Remote Scripts" / "TactusMCP"
    heartbeat = new / "tactus-bridge" / "instances" / "new" / "heartbeat.json"
    heartbeat.parent.mkdir(parents=True)
    heartbeat.write_text(json.dumps({"protocol": 1, "time": time.time(), "instance": "new"}))
    report = setup.connect(live_library=library, check=True)
    assert report["live"]["active_scripts"] == ["TactusMCP"]
    assert "active" in report["live"]["next_step"]


def test_setup_preserves_previous_reaper_filename_until_action_is_stopped(tmp_path):
    resource = tmp_path / "REAPER"
    scripts = resource / "Scripts"
    scripts.mkdir(parents=True)
    old = scripts / "Tactus MCP.lua"
    old.write_bytes(reaper.script().read_bytes())
    checked = setup.connect(reaper_path=resource, check=True)
    assert checked["reaper"]["previous_names"] == [str(old)]
    assert old.exists()

    installed = setup.connect(reaper_path=resource)
    assert installed["reaper"]["previous_names"] == [str(old)]
    assert old.exists()
    assert (scripts / "TactusMCP.lua").read_bytes() == reaper.script().read_bytes()

    old.write_text("user edited")
    setup.connect(reaper_path=resource)
    assert old.read_text() == "user edited"


def test_codex_conflict_is_preserved(tmp_path, monkeypatch):
    class Result:
        returncode = 0
        stdout = "tactus-mcp\n  command: /other/python\n  args: -m tactus.mcp\n"

    calls = []
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/bin/codex")
    monkeypatch.setattr(setup.subprocess, "run", lambda args, **kwargs: (calls.append(args), Result())[1])
    report = setup.connect(host="codex", reaper_path=tmp_path, live_library=tmp_path, check=True)
    assert report["host"]["state"] == "conflict"
    assert len(calls) == 1


def test_codex_registration_keeps_virtualenv_entrypoint(tmp_path, monkeypatch):
    venv_python = tmp_path / "venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.symlink_to(Path("/usr/bin/python3"))
    monkeypatch.setattr(setup.sys, "executable", str(venv_python))
    monkeypatch.setattr(setup.shutil, "which", lambda name: "/bin/codex")
    calls = []

    class Result:
        returncode = 1
        stdout = ""
        stderr = "No MCP server named tactus-mcp"

    class Added:
        returncode = 0
        stdout = "added"
        stderr = ""

    def run(args, **kwargs):
        calls.append(args)
        return Result() if args[2] == "get" else Added()

    monkeypatch.setattr(setup.subprocess, "run", run)
    assert setup._codex_entry(check=False)["state"] == "configured"
    assert calls[1][-3:] == [str(venv_python), "-m", "tactus.mcp"]


def test_missing_mcp_extra_does_not_register_host(monkeypatch):
    monkeypatch.setattr(setup, "find_spec", lambda name: None)
    assert setup._codex_entry(check=False)["state"] == "unavailable"
