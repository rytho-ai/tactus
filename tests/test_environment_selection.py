"""Project/interpreter precedence without redirecting an explicitly chosen uv work."""

import json
import sys

import pytest

from tactus import launcher
from tactus.cli import main
from tactus.project import selected_project


@pytest.fixture
def projects(tmp_path, monkeypatch):
    monkeypatch.delenv("TACTUS_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("UV_RUN_RECURSION_DEPTH", raising=False)
    roots = [tmp_path / name for name in ["cwd", "uv", "explicit"]]
    for root in roots:
        root.mkdir()
        (root / "pyproject.toml").write_text('[project]\nname="work"\ndependencies=["tactus"]\n')
        (root / "uv.lock").write_text("version = 1\n")
    monkeypatch.chdir(roots[0])
    monkeypatch.setattr(sys, "prefix", str(roots[1] / ".venv"))
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    return roots


def test_uv_selection_and_explicit_precedence(projects, monkeypatch):
    cwd, uv, explicit = projects
    assert selected_project().root == cwd  # Activation alone cannot override cwd.
    monkeypatch.setenv("UV_RUN_RECURSION_DEPTH", "1")
    assert selected_project().root == uv
    assert selected_project(explicit).root == explicit
    assert selected_project(recognize_uv=False).root == cwd
    monkeypatch.setenv("TACTUS_PROJECT_ROOT", str(cwd))
    assert selected_project().root == cwd
    assert selected_project(explicit).root == explicit


@pytest.mark.parametrize("marker", ["", "0", "invalid"])
def test_invalid_uv_context_uses_cwd(projects, monkeypatch, marker):
    monkeypatch.setenv("UV_RUN_RECURSION_DEPTH", marker)
    assert selected_project().root == projects[0]


def test_unrelated_activation_and_unrelated_project_boundary(projects, monkeypatch):
    cwd, uv, _ = projects
    monkeypatch.setenv("UV_RUN_RECURSION_DEPTH", "1")
    monkeypatch.setenv("VIRTUAL_ENV", "/another/environment")
    assert selected_project().root == cwd
    monkeypatch.setenv("VIRTUAL_ENV", sys.prefix)
    (uv / "pyproject.toml").write_text('[project]\nname="unrelated"\n')
    assert selected_project().root == cwd


@pytest.mark.parametrize("invalid", ["missing", "unrelated"])
def test_invalid_delegated_work_never_falls_back(projects, monkeypatch, invalid):
    root = projects[2]
    if invalid == "missing":
        root = root / "missing"
    else:
        (root / "pyproject.toml").write_text('[project]\nname="unrelated"\n')
    monkeypatch.setenv("TACTUS_PROJECT_ROOT", str(root))
    with pytest.raises(ValueError, match="selected"):
        selected_project()


def test_launcher_dispatch_honors_uv_owner_and_keeps_caller_paths(projects, monkeypatch):
    monkeypatch.setenv("UV_RUN_RECURSION_DEPTH", "1")
    monkeypatch.setattr(sys, "argv", ["tactus", "run", "song.py", "--out", "runs/a"])
    calls = []

    def execute(command, **kwargs):
        calls.append((command, kwargs))
        return type("Completed", (), {"returncode": 0})()

    monkeypatch.setattr(launcher.subprocess, "run", execute)
    assert launcher.main() == 0
    command, options = calls[0]
    assert command[3] == str(projects[1])
    assert command[-5:] == ["tactus.cli", "run", "song.py", "--out", "runs/a"]
    assert "cwd" not in options
    assert options["env"]["TACTUS_PROJECT_ROOT"] == str(projects[1])
    assert "VIRTUAL_ENV" not in options["env"]


def test_uv_work_missing_lock_does_not_dispatch_elsewhere(projects, monkeypatch, capsys):
    (projects[1] / "uv.lock").unlink()
    monkeypatch.setenv("UV_RUN_RECURSION_DEPTH", "1")
    monkeypatch.setattr(sys, "argv", ["tactus", "doctor"])
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: pytest.fail("fallback"))
    assert launcher.main() == 2
    assert str(projects[1]) in json.loads(capsys.readouterr().out)["error"]["message"]


def test_doctor_explains_interpreter_lock_and_environment_mismatch(projects, capsys):
    assert main(["doctor"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["project"] == str(projects[0])
    assert report["interpreter"] == sys.executable
    assert report["lock"]["path"] == str(projects[1] / "uv.lock")
    assert len(report["lock"]["sha256"]) == 64
    assert report["environment_matches_project"] is False
    assert "package_source" in report
