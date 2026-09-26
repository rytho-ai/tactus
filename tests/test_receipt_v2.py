"""Exercise receipt v2: resolved materials/tools, package attribution and lock discovery."""

from __future__ import annotations

import json
import stat
from importlib.metadata import version
from pathlib import Path

import pytest

from tactus import RunError, run
from tactus.inputs import pool


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
    assert receipt["format_version"] == 3
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
