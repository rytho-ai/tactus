"""Exercise the receipt's Git revision record: commit, dirty, untracked, and the source patch."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from tactus import run

SOURCE = """\
import numpy as np

def render(*, gain=0.2):
    return {"sample_rate": 8000, "outputs": {"a": np.full(8, gain, dtype=np.float32)}}
"""


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
def scratch_pool(tmp_path, monkeypatch):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))


def entry_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    entry_dir = repo / "song"
    entry_dir.mkdir(parents=True)
    (entry_dir / "entry.py").write_text(SOURCE, encoding="utf-8")
    init_repo(repo)
    commit_all(repo, "initial")
    return repo, entry_dir / "entry.py"


def test_clean_tree_gives_commit_and_dirty_false(tmp_path):
    repo, entry = entry_repo(tmp_path)
    result = run(entry, out=tmp_path / "out")
    receipt = json.loads(Path(result["receipt"]).read_text())
    head = git(["rev-parse", "HEAD"], repo).stdout.strip()
    assert receipt["git"] == {"commit": head, "dirty": False, "untracked": []}
    assert not (tmp_path / "out" / "source.patch").exists()


def test_edited_tracked_file_gives_dirty_true_and_patch_reproduces_source(tmp_path):
    repo, entry = entry_repo(tmp_path)
    head = git(["rev-parse", "HEAD"], repo).stdout.strip()
    entry.write_text(SOURCE + "\n# a candidate edit\n", encoding="utf-8")
    result = run(entry, out=tmp_path / "out")
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert receipt["git"]["commit"] == head
    assert receipt["git"]["dirty"] is True
    assert receipt["git"]["patch"] == "source.patch"
    patch = tmp_path / "out" / "source.patch"
    assert patch.is_file()

    worktree = tmp_path / "worktree"
    git(["worktree", "add", "-q", "--detach", str(worktree), head], repo)
    apply = subprocess.run(
        ["git", "apply", "--binary", str(patch)],
        cwd=worktree,
        capture_output=True,
        text=True,
        check=False,
    )
    assert apply.returncode == 0, apply.stderr
    rebuilt = (worktree / "song" / "entry.py").read_bytes()
    expected_hash = receipt["source_files"]["entry.py"]
    assert hashlib.sha256(rebuilt).hexdigest() == expected_hash


def test_untracked_py_file_is_listed(tmp_path):
    _repo, entry = entry_repo(tmp_path)
    (entry.parent / "scratch.py").write_text("# untracked\n", encoding="utf-8")
    result = run(entry, out=tmp_path / "out")
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert receipt["git"]["untracked"] == ["scratch.py"]
    assert receipt["git"]["dirty"] is False


def test_non_repository_gives_null_git(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    entry = root / "entry.py"
    entry.write_text(SOURCE, encoding="utf-8")
    result = run(entry, out=tmp_path / "out")
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert receipt["git"] is None


def test_missing_git_binary_gives_null_git(tmp_path, monkeypatch):
    _repo, entry = entry_repo(tmp_path)
    empty_path = tmp_path / "empty-path"
    empty_path.mkdir()
    monkeypatch.setenv("PATH", str(empty_path))
    result = run(entry, out=tmp_path / "out")
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert receipt["git"] is None


def test_repository_with_no_commits_gives_null_git(tmp_path):
    root = tmp_path / "empty-repo"
    entry_dir = root / "song"
    entry_dir.mkdir(parents=True)
    (entry_dir / "entry.py").write_text(SOURCE, encoding="utf-8")
    init_repo(root)
    result = run(entry_dir / "entry.py", out=tmp_path / "out")
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert receipt["git"] is None


def test_run_inside_a_worktree_records_the_worktrees_head(tmp_path):
    repo, _entry = entry_repo(tmp_path)
    branch_head = git(["rev-parse", "HEAD"], repo).stdout.strip()
    git(["branch", "-q", "feature"], repo)
    worktree = tmp_path / "feature-worktree"
    git(["worktree", "add", "-q", str(worktree), "feature"], repo)
    (worktree / "song" / "entry.py").write_text(
        SOURCE.replace("gain=0.2", "gain=0.3"), encoding="utf-8"
    )
    worktree_head = commit_all(worktree, "feature change")
    assert worktree_head != branch_head

    result = run(worktree / "song" / "entry.py", out=tmp_path / "out")
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert receipt["git"]["commit"] == worktree_head
    assert receipt["git"]["dirty"] is False
