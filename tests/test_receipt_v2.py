"""Exercise receipt v2: resolved materials/tools, package attribution and lock discovery."""

from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import sys
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pytest

from tactus import RunError, run
from tactus.inputs import pool

# `tactus/__init__.py` rebinds the package's `run` attribute to this function, shadowing
# the `tactus.run` submodule; `import_module` reaches the submodule regardless.
run_module = import_module("tactus.run")


def source(tmp_path: Path, text: str, *, subdir: str = "authoring") -> Path:
    root = tmp_path / subdir
    root.mkdir(parents=True, exist_ok=True)
    path = root / "song.py"
    path.write_text(text, encoding="utf-8")
    return path


def read(path: str) -> dict:
    return json.loads(Path(path).read_text())


@pytest.fixture(autouse=True)
def scratch_pool(tmp_path, monkeypatch):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))


def test_receipt_lists_materials_and_tools_in_resolution_order(tmp_path):
    first = tmp_path / "b-material.bin"
    first.write_bytes(b"second logically, first resolved")
    second = tmp_path / "a-material.bin"
    second.write_bytes(b"first logically, second resolved")
    first_digest = pool.put(first)
    second_digest = pool.put(second)

    tool_script = tmp_path / "declared-tool.sh"
    tool_script.write_text("#!/bin/sh\necho hi\n")
    tool_script.chmod(tool_script.stat().st_mode | stat.S_IEXEC)

    entry = source(
        tmp_path,
        f"""import numpy as np
from tactus.inputs import material, tool

def render():
    material("sha256:{first_digest}")
    material("sha256:{second_digest}")
    material("sha256:{first_digest}")  # repeat resolution must not duplicate the record
    tool({str(tool_script)!r})
    return {{"sample_rate": 8000, "outputs": {{"a": np.zeros(8)}}}}
""",
    )
    result = run(entry, out=tmp_path / "out")
    receipt = read(result["receipt"])
    assert receipt["format_version"] == 4
    assert receipt["materials"] == [
        {"ref": f"sha256:{first_digest}"},
        {"ref": f"sha256:{second_digest}"},
    ]
    assert receipt["tools"] == [
        {
            "name": str(tool_script),
            "path": str(tool_script.resolve()),
            "sha256": pool.put(tool_script),  # same bytes, same digest
            "kind": "file",
        }
    ]


def test_python_packages_includes_numpy_and_excludes_stdlib(tmp_path):
    entry = source(
        tmp_path,
        """import json  # stdlib; must not appear in python_packages
import numpy as np
def render():
    return {"sample_rate": 8000, "outputs": {"a": np.zeros(8)}}
""",
    )
    result = run(entry, out=tmp_path / "out")
    receipt = read(result["receipt"])
    assert receipt["python_packages"]["numpy"] == version("numpy")
    assert "json" not in receipt["python_packages"]


def test_nearest_lock_is_found_upward_from_a_nested_entry(tmp_path):
    root = tmp_path / "proj"
    root.mkdir(parents=True)
    lock = root / "uv.lock"
    lock.write_text("# fake lock\n")
    entry = source(
        tmp_path,
        "import numpy as np\ndef render():\n"
        "    return {'sample_rate': 8000, 'outputs': {'a': np.zeros(8)}}\n",
        subdir="proj/nested/entry",
    )
    result = run(entry, out=tmp_path / "out")
    receipt = read(result["receipt"])
    assert receipt["dependency_lock"]["path"] == str(lock)
    import hashlib

    assert receipt["dependency_lock"]["sha256"] == hashlib.sha256(lock.read_bytes()).hexdigest()


def test_render_resolving_a_missing_material_fails_with_material_unavailable(tmp_path):
    missing_ref = f"sha256:{'1' * 64}"
    entry = source(
        tmp_path,
        f"""import numpy as np
from tactus.inputs import material
def render():
    material({missing_ref!r})
    return {{"sample_rate": 8000, "outputs": {{"a": np.zeros(8)}}}}
""",
    )
    out = tmp_path / "out"
    with pytest.raises(RunError) as failure:
        run(entry, out=out)
    assert (failure.value.code, failure.value.phase) == ("material_unavailable", "execute")
    assert not out.exists()


def test_import_time_missing_material_fails_at_load_phase(tmp_path):
    missing_ref = f"sha256:{'2' * 64}"
    entry = source(
        tmp_path,
        f"""from tactus.inputs import material
material({missing_ref!r})
import numpy as np
def render():
    return {{"sample_rate": 8000, "outputs": {{"a": np.zeros(8)}}}}
""",
    )
    out = tmp_path / "out"
    with pytest.raises(RunError) as failure:
        run(entry, out=out)
    assert (failure.value.code, failure.value.phase) == ("material_unavailable", "load")
    assert not out.exists()


def test_missing_tool_fails_with_tool_unavailable(tmp_path):
    entry = source(
        tmp_path,
        """import numpy as np
from tactus.inputs import tool
def render():
    tool("definitely-not-a-real-executable-name")
    return {"sample_rate": 8000, "outputs": {"a": np.zeros(8)}}
""",
    )
    out = tmp_path / "out"
    with pytest.raises(RunError) as failure:
        run(entry, out=out)
    assert (failure.value.code, failure.value.phase) == ("tool_unavailable", "execute")
    assert not out.exists()


def test_environment_lock_resolves_for_the_running_venv(tmp_path):
    entry = source(
        tmp_path,
        """import numpy as np
def render():
    return {"sample_rate": 8000, "outputs": {"a": np.zeros(8)}}
""",
    )
    result = run(entry, out=tmp_path / "out")
    receipt = read(result["receipt"])
    environment = receipt["environment"]
    assert environment["prefix"] == sys.prefix
    project_lock = Path(sys.prefix).parent / "uv.lock"
    if project_lock.is_file():
        assert environment["lock"] == {
            "path": str(project_lock),
            "sha256": hashlib.sha256(project_lock.read_bytes()).hexdigest(),
        }
    else:
        assert environment["lock"] is None


def test_environment_lock_is_null_when_the_prefixs_parent_has_no_lock(tmp_path, monkeypatch):
    prefix = tmp_path / "somewhere" / ".venv"
    prefix.mkdir(parents=True)
    monkeypatch.setattr(sys, "prefix", str(prefix))
    assert run_module._environment() == {"prefix": str(prefix), "lock": None}


def test_environment_lock_resolves_when_the_prefixs_parent_has_one(tmp_path, monkeypatch):
    project = tmp_path / "project"
    prefix = project / ".venv"
    prefix.mkdir(parents=True)
    lock = project / "uv.lock"
    lock.write_text("# fake lock\n")
    monkeypatch.setattr(sys, "prefix", str(prefix))
    assert run_module._environment() == {
        "prefix": str(prefix),
        "lock": {"path": str(lock), "sha256": hashlib.sha256(lock.read_bytes()).hexdigest()},
    }


class _FakeDistribution:
    def __init__(self, text: str | None) -> None:
        self._text = text

    def read_text(self, filename: str) -> str | None:
        assert filename == "direct_url.json"
        return self._text


def test_package_sources_records_a_vcs_installed_distributions_commit(monkeypatch):
    payload = json.dumps(
        {
            "url": "https://github.com/openmirlab/pytimestretch",
            "vcs_info": {
                "vcs": "git",
                "commit_id": "e43cc6d" * 5 + "e",
                "requested_revision": "main",
            },
        }
    )
    monkeypatch.setattr(
        run_module,
        "distribution",
        lambda name: _FakeDistribution(payload if name == "pytimestretch" else None),
    )
    result = run_module._package_sources(["pytimestretch"])
    assert result == {
        "pytimestretch": {
            "url": "https://github.com/openmirlab/pytimestretch",
            "vcs": "git",
            "commit": "e43cc6d" * 5 + "e",
        }
    }


def test_package_sources_records_an_editable_local_git_checkouts_commit_and_dirty(
    tmp_path, monkeypatch
):
    directory = tmp_path / "tactus-checkout"
    directory.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=directory, check=True)
    subprocess.run(["git", "config", "user.email", "a@example.com"], cwd=directory, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=directory, check=True)
    (directory / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=directory, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=directory, check=True)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=directory, capture_output=True, text=True, check=True
    ).stdout.strip()
    (directory / "a.py").write_text("x = 2\n", encoding="utf-8")  # dirty after the commit

    payload = json.dumps({"url": directory.as_uri(), "dir_info": {"editable": True}})
    monkeypatch.setattr(
        run_module,
        "distribution",
        lambda name: _FakeDistribution(payload if name == "tactus" else None),
    )
    result = run_module._package_sources(["tactus"])
    assert result == {
        "tactus": {
            "url": directory.as_uri(),
            "editable": True,
            "git": {"commit": commit, "dirty": True},
        }
    }


def test_package_sources_omits_index_installed_distributions(monkeypatch):
    monkeypatch.setattr(run_module, "distribution", lambda name: _FakeDistribution(None))
    assert run_module._package_sources(["numpy", "soundfile"]) == {}


def test_package_sources_skips_a_distribution_missing_its_metadata(monkeypatch):
    def fake(name: str) -> _FakeDistribution:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(run_module, "distribution", fake)
    assert run_module._package_sources(["ghost"]) == {}
