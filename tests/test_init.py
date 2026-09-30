"""Exercise `tactus init`: scaffolding content, source resolution, and refusals."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tactus import init as init_module
from tactus.cli import main
from tactus.init import init
from tactus.run import RunError

TACTUS_ROOT = Path(__file__).resolve().parents[1]


def git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def init_repo(root: Path) -> None:
    git(["init", "-q"], root)
    git(["config", "user.email", "a@example.com"], root)
    git(["config", "user.name", "Test"], root)


def commit_all(root: Path, message: str) -> str:
    git(["add", "-A"], root)
    git(["commit", "-q", "-m", message], root)
    return git(["rev-parse", "HEAD"], root).stdout.strip()


@pytest.fixture(autouse=True)
def _fake_uv(monkeypatch):
    """Unit tests never shell out to a real `uv`; they only assert it would be invoked."""
    calls: list[tuple[list[str], Path]] = []
    real_which = shutil.which

    def fake_which(name: str) -> str | None:
        return "/usr/bin/uv" if name == "uv" else real_which(name)

    real_run = subprocess.run

    def fake_run(args, cwd=None, **kwargs):
        # `subprocess` is one shared module object: patching it here would also swallow
        # revision.py's real `git` calls used by the editable-checkout tests, so only the
        # `uv` invocation this module makes is faked; everything else runs for real.
        if args[:1] == ["/usr/bin/uv"]:
            calls.append((list(args), Path(cwd)))
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        return real_run(args, cwd=cwd, **kwargs)

    monkeypatch.setattr(init_module.shutil, "which", fake_which)
    monkeypatch.setattr(init_module.subprocess, "run", fake_run)
    return calls


def test_init_writes_pyproject_and_gitignore_and_locks(tmp_path, _fake_uv):
    work = tmp_path / "work"
    result = init(work, tactus="https://example.com/tactus@abc123")
    assert result["status"] == "ok"
    assert result["work"] == str(work)
    assert result["tactus"] == {"git": "https://example.com/tactus", "rev": "abc123"}

    pyproject = (work / "pyproject.toml").read_text()
    assert 'name = "work"' in pyproject
    assert 'dependencies = ["tactus"]' in pyproject
    assert 'requires-python = "' in pyproject
    assert result["python"] in pyproject
    assert "[tool.uv.sources]" in pyproject
    assert 'git = "https://example.com/tactus"' in pyproject
    assert 'rev = "abc123"' in pyproject

    assert (work / ".gitignore").read_text() == "runs/\nanalyses/\nexports/\n.tactus/\n.venv/\n__pycache__/\n"

    assert _fake_uv == [(["/usr/bin/uv", "lock"], work)]


def test_init_refuses_a_nonempty_directory(tmp_path, _fake_uv):
    work = tmp_path / "work"
    work.mkdir()
    (work / "existing.txt").write_text("x")
    with pytest.raises(RunError) as excinfo:
        init(work, tactus="https://example.com/tactus@abc123")
    assert excinfo.value.code == "invalid_request"
    assert not _fake_uv


def test_init_allows_an_existing_empty_directory(tmp_path, _fake_uv):
    work = tmp_path / "work"
    work.mkdir()
    result = init(work, tactus="https://example.com/tactus@abc123")
    assert result["status"] == "ok"


def test_init_requires_uv_on_path(tmp_path, monkeypatch):
    monkeypatch.setattr(init_module.shutil, "which", lambda name: None)
    with pytest.raises(RunError) as excinfo:
        init(tmp_path / "work", tactus="https://example.com/tactus@abc123")
    assert excinfo.value.code == "init_failed"


def test_tactus_path_and_tactus_are_mutually_exclusive(tmp_path, _fake_uv):
    with pytest.raises(RunError) as excinfo:
        init(tmp_path / "work", tactus_path=tmp_path, tactus="https://example.com/tactus@abc")
    assert excinfo.value.code == "invalid_request"


def test_explicit_tactus_source_must_be_url_at_rev(tmp_path, _fake_uv):
    with pytest.raises(RunError) as excinfo:
        init(tmp_path / "work", tactus="not-a-url-rev-pair")
    assert excinfo.value.code == "invalid_request"


def test_tactus_path_pins_an_editable_local_checkout(tmp_path, _fake_uv):
    checkout = tmp_path / "tactus-checkout"
    checkout.mkdir()
    result = init(tmp_path / "work", tactus_path=checkout)
    assert result["tactus"] == {"path": str(checkout.resolve()), "editable": True}


def test_tactus_path_must_be_a_directory(tmp_path, _fake_uv):
    not_a_dir = tmp_path / "missing"
    with pytest.raises(RunError) as excinfo:
        init(tmp_path / "work", tactus_path=not_a_dir)
    assert excinfo.value.code == "invalid_request"


def test_running_tactus_source_pins_a_git_install(tmp_path, monkeypatch, _fake_uv):
    monkeypatch.setattr(
        init_module,
        "_direct_url",
        lambda name: {
            "url": "https://github.com/rytho-ai/tactus",
            "vcs_info": {"vcs": "git", "commit_id": "deadbeef"},
        },
    )
    result = init(tmp_path / "work")
    assert result["tactus"] == {"git": "https://github.com/rytho-ai/tactus", "rev": "deadbeef"}


def test_running_tactus_source_pins_a_clean_pushed_editable_checkout(
    tmp_path, monkeypatch, _fake_uv
):
    remote = tmp_path / "remote.git"
    git(["init", "-q", "--bare", str(remote)], tmp_path)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    init_repo(checkout)
    (checkout / "a.py").write_text("x = 1\n")
    commit = commit_all(checkout, "initial")
    git(["remote", "add", "origin", str(remote)], checkout)
    git(["push", "-q", "origin", "HEAD:refs/heads/main"], checkout)
    git(["fetch", "-q", "origin"], checkout)  # populate local remote-tracking refs

    monkeypatch.setattr(
        init_module,
        "_direct_url",
        lambda name: {
            "url": f"file://{checkout}",
            "dir_info": {"editable": True},
        },
    )
    result = init(tmp_path / "work")
    assert result["tactus"] == {"git": str(remote), "rev": commit}


def test_running_tactus_source_refuses_a_dirty_editable_checkout(tmp_path, monkeypatch, _fake_uv):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    init_repo(checkout)
    (checkout / "a.py").write_text("x = 1\n")
    commit_all(checkout, "initial")
    (checkout / "a.py").write_text("x = 2\n")  # dirty

    monkeypatch.setattr(
        init_module,
        "_direct_url",
        lambda name: {"url": f"file://{checkout}", "dir_info": {"editable": True}},
    )
    with pytest.raises(RunError) as excinfo:
        init(tmp_path / "work")
    assert excinfo.value.code == "init_failed"
    assert "uncommitted" in str(excinfo.value)


def test_running_tactus_source_refuses_an_unpushed_editable_checkout(
    tmp_path, monkeypatch, _fake_uv
):
    remote = tmp_path / "remote.git"
    git(["init", "-q", "--bare", str(remote)], tmp_path)
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    init_repo(checkout)
    (checkout / "a.py").write_text("x = 1\n")
    commit_all(checkout, "initial")
    git(["remote", "add", "origin", str(remote)], checkout)
    # No push: HEAD is not reachable from any remote-tracking branch.

    monkeypatch.setattr(
        init_module,
        "_direct_url",
        lambda name: {"url": f"file://{checkout}", "dir_info": {"editable": True}},
    )
    with pytest.raises(RunError) as excinfo:
        init(tmp_path / "work")
    assert excinfo.value.code == "init_failed"
    assert "not pushed" in str(excinfo.value)


def test_running_tactus_source_refuses_an_editable_checkout_without_origin(
    tmp_path, monkeypatch, _fake_uv
):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    init_repo(checkout)
    (checkout / "a.py").write_text("x = 1\n")
    commit_all(checkout, "initial")
    # No remote at all.

    monkeypatch.setattr(
        init_module,
        "_direct_url",
        lambda name: {"url": f"file://{checkout}", "dir_info": {"editable": True}},
    )
    with pytest.raises(RunError) as excinfo:
        init(tmp_path / "work")
    assert excinfo.value.code == "init_failed"
    assert "origin" in str(excinfo.value)


def test_running_tactus_source_refuses_an_unsupported_install(tmp_path, monkeypatch, _fake_uv):
    monkeypatch.setattr(init_module, "_direct_url", lambda name: None)
    with pytest.raises(RunError) as excinfo:
        init(tmp_path / "work")
    assert excinfo.value.code == "init_failed"


def test_cli_init_prints_a_json_result(tmp_path, capsys, _fake_uv):
    work = tmp_path / "work"
    assert main(["init", str(work), "--tactus", "https://example.com/tactus@abc123"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ok"
    assert report["work"] == str(work)


def test_cli_init_reports_a_request_error_as_json_with_exit_code_2(tmp_path, capsys, _fake_uv):
    work = tmp_path / "work"
    work.mkdir()
    (work / "existing.txt").write_text("x")
    assert main(["init", str(work), "--tactus", "https://example.com/tactus@abc123"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["error"]["code"] == "invalid_request"


def test_cli_init_rejects_tactus_path_and_tactus_together(tmp_path, capsys, _fake_uv):
    assert (
        main(
            [
                "init",
                str(tmp_path / "work"),
                "--tactus-path",
                str(tmp_path),
                "--tactus",
                "https://example.com/tactus@abc123",
            ]
        )
        == 2
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "error"


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("TACTUS_SLOW") != "1",
    reason="slow: real uv sync + install + run; set TACTUS_SLOW=1 to run it",
)
def test_init_then_uv_sync_then_run_uses_the_works_own_lock(tmp_path):
    if shutil.which("uv") is None:
        pytest.skip("uv not installed")
    work = tmp_path / "work"
    assert main(["init", str(work), "--tactus-path", str(TACTUS_ROOT)]) == 0
    subprocess.run(["uv", "sync"], cwd=work, check=True)

    (work / "song.py").write_text(
        "import numpy as np\n\n\n"
        "def render(*, gain=0.1):\n"
        "    return {'sample_rate': 8000, "
        "'outputs': {'a': np.full(8, gain, dtype=np.float32)}}\n"
    )
    subprocess.run(
        ["uv", "run", "tactus", "run", "song.py", "--out", "runs/a"],
        cwd=work,
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads((work / "runs" / "a" / "receipt.json").read_text())
    assert receipt["dependency_lock"]["path"] == str(work / "uv.lock")
    assert receipt["environment"]["lock"]["path"] == str(work / "uv.lock")


def test_init_creates_a_git_repository_for_a_fresh_work(tmp_path, _fake_uv):
    result = init(tmp_path / "work", tactus_path=TACTUS_ROOT)
    assert result["git_init"] is True
    assert (tmp_path / "work" / ".git").is_dir()


def test_init_gives_a_nested_work_its_own_repository(tmp_path, _fake_uv):
    init_repo(tmp_path)
    result = init(tmp_path / "work", tactus_path=TACTUS_ROOT)
    assert result["git_init"] is True
    assert (tmp_path / "work" / ".git").is_dir()
    assert git(["rev-parse", "--show-toplevel"], tmp_path / "work").stdout.strip() == str(tmp_path / "work")


def test_init_requires_git_before_creating_files(tmp_path, monkeypatch):
    monkeypatch.setattr(init_module.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    with pytest.raises(RunError, match="install Git") as failure:
        init(tmp_path / "work", tactus_path=TACTUS_ROOT)
    assert (failure.value.code, failure.value.phase) == ("init_failed", "request")
    assert not (tmp_path / "work").exists()


def test_init_reports_git_initialization_failure(tmp_path, monkeypatch, _fake_uv):
    real_git = init_module.revision._git

    def fail(args, directory):
        if args[:1] == ["init"]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="permission denied")
        return real_git(args, directory)

    monkeypatch.setattr(init_module.revision, "_git", fail)
    with pytest.raises(RunError, match="permission denied") as failure:
        init(tmp_path / "work", tactus_path=TACTUS_ROOT)
    assert (failure.value.code, failure.value.phase) == ("init_failed", "git")
