"""Exercise `@stage`/`--reuse`: hits, misses, and what a call not reusable does instead."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from tactus import run
from tactus.inputs import pool

COUNTER_SOURCE = """\
import numpy as np
from pathlib import Path
from tactus import stage

COUNTS = Path({counts!r})

@stage
def bed(*, gain: float = 1.0):
    with COUNTS.open("a", encoding="utf-8") as handle:
        handle.write("x")
    return np.full(8, gain, dtype=np.float32)

def render(*, gain: float = 1.0):
    return {{"sample_rate": 8000, "outputs": {{"bed": bed(gain=gain)}}}}
"""

TWO_STAGE_SOURCE = """\
import numpy as np
from pathlib import Path
from tactus import stage

COUNTS_A = Path({counts_a!r})
COUNTS_B = Path({counts_b!r})

@stage
def bed_a(*, gain: float = 1.0):
    with COUNTS_A.open("a", encoding="utf-8") as handle:
        handle.write("x")
    return np.full(8, gain, dtype=np.float32)

@stage
def bed_b(*, pad: float = 1.0):
    with COUNTS_B.open("a", encoding="utf-8") as handle:
        handle.write("x")
    return np.full(8, pad, dtype=np.float32)

def render(*, gain: float = 1.0, pad: float = 1.0):
    a = bed_a(gain=gain)
    b = bed_b(pad=pad)
    return {{"sample_rate": 8000, "outputs": {{"a": a, "b": b}}}}
"""

TOOL_SOURCE = """\
import numpy as np
from pathlib import Path
from tactus import stage, tool

TOOL_PATH = {tool_path!r}
COUNTS = Path({counts!r})

@stage
def bed(*, gain: float = 1.0):
    tool(TOOL_PATH)
    with COUNTS.open("a", encoding="utf-8") as handle:
        handle.write("x")
    return np.full(8, gain, dtype=np.float32)

def render(*, gain: float = 1.0):
    return {{"sample_rate": 8000, "outputs": {{"bed": bed(gain=gain)}}}}
"""

UNSUPPORTED_SOURCE = """\
import numpy as np
from pathlib import Path
from tactus import stage

COUNTS = Path({counts!r})

@stage
def bed(*, rng):
    with COUNTS.open("a", encoding="utf-8") as handle:
        handle.write("x")
    return np.full(8, rng.random(), dtype=np.float32)

def render():
    rng = np.random.default_rng(0)
    return {{"sample_rate": 8000, "outputs": {{"bed": bed(rng=rng)}}}}
"""

MATERIAL_SOURCE = """\
import numpy as np
from tactus import material, stage

REF = {ref!r}

@stage
def bed(*, gain: float = 1.0):
    material(REF)
    return np.full(8, gain, dtype=np.float32)

def render(*, gain: float = 1.0):
    return {{"sample_rate": 8000, "outputs": {{"bed": bed(gain=gain)}}}}
"""

DETERMINISTIC_SOURCE = """\
import numpy as np
from tactus import stage

@stage
def bed(*, gain: float = 1.0):
    return np.full(8, gain, dtype=np.float32)

def render(*, gain: float = 1.0):
    return {"sample_rate": 8000, "outputs": {"bed": bed(gain=gain)}}
"""


@pytest.fixture(autouse=True)
def scratch_pool(tmp_path, monkeypatch):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))


def write_source(tmp_path: Path, text: str, *, subdir: str = "work") -> Path:
    root = tmp_path / subdir
    root.mkdir(parents=True, exist_ok=True)
    path = root / "song.py"
    path.write_text(text, encoding="utf-8")
    return path


def read(path: str) -> dict:
    return json.loads(Path(path).read_text())


def test_hit_returns_identical_arrays_and_skips_the_body(tmp_path):
    counts = tmp_path / "counts.txt"
    entry = write_source(tmp_path, COUNTER_SOURCE.format(counts=str(counts)))

    first = run(entry, out=tmp_path / "first", reuse=True)
    second = run(entry, out=tmp_path / "second", reuse=True)

    assert counts.read_text() == "x"  # the body ran exactly once
    first_manifest = read(first["manifest"])
    second_manifest = read(second["manifest"])
    assert first_manifest["outputs"]["bed"] == second_manifest["outputs"]["bed"]

    first_receipt = read(first["receipt"])
    second_receipt = read(second["receipt"])
    assert first_receipt["reuse"] is True
    [first_stage] = first_receipt["stages"]
    [second_stage] = second_receipt["stages"]
    assert first_stage["reused"] is False
    assert first_stage["reason"] is None
    assert second_stage["reused"] is True
    assert second_stage["key"] == first_stage["key"]
    assert second_stage["reason"] is None


def test_changed_parameter_misses_only_the_stages_that_received_it(tmp_path):
    counts_a = tmp_path / "counts_a.txt"
    counts_b = tmp_path / "counts_b.txt"
    entry = write_source(
        tmp_path,
        TWO_STAGE_SOURCE.format(counts_a=str(counts_a), counts_b=str(counts_b)),
    )

    run(entry, out=tmp_path / "first", reuse=True)
    result = run(entry, out=tmp_path / "second", params={"pad": 0.25}, reuse=True)

    assert counts_a.read_text() == "x"  # bed_a's argument did not change: reused
    assert counts_b.read_text() == "xx"  # bed_b's argument changed: recomputed

    receipt = read(result["receipt"])
    by_name = {entry["name"]: entry for entry in receipt["stages"]}
    assert by_name["bed_a"]["reused"] is True
    assert by_name["bed_b"]["reused"] is False


def test_source_edit_misses_everything(tmp_path):
    counts = tmp_path / "counts.txt"
    entry = write_source(tmp_path, COUNTER_SOURCE.format(counts=str(counts)))

    run(entry, out=tmp_path / "first", reuse=True)
    entry.write_text(entry.read_text() + "\n# a harmless edit\n", encoding="utf-8")
    result = run(entry, out=tmp_path / "second", reuse=True)

    assert counts.read_text() == "xx"  # the body ran again
    [stage_entry] = read(result["receipt"])["stages"]
    assert stage_entry["reused"] is False


def test_changed_tool_file_misses(tmp_path):
    counts = tmp_path / "counts.txt"
    tool_path = tmp_path / "declared-tool.sh"
    tool_path.write_text("#!/bin/sh\necho v1\n")
    tool_path.chmod(tool_path.stat().st_mode | stat.S_IEXEC)
    entry = write_source(tmp_path, TOOL_SOURCE.format(tool_path=str(tool_path), counts=str(counts)))

    run(entry, out=tmp_path / "first", reuse=True)
    tool_path.write_text("#!/bin/sh\necho v2\n")
    tool_path.chmod(tool_path.stat().st_mode | stat.S_IEXEC)
    result = run(entry, out=tmp_path / "second", reuse=True)

    assert counts.read_text() == "xx"  # the tool changed underneath the same key: recomputed
    [stage_entry] = read(result["receipt"])["stages"]
    assert stage_entry["reused"] is False


def test_unsupported_argument_runs_uncached_with_a_reason(tmp_path):
    counts = tmp_path / "counts.txt"
    entry = write_source(tmp_path, UNSUPPORTED_SOURCE.format(counts=str(counts)))

    first = run(entry, out=tmp_path / "first", reuse=True)
    second = run(entry, out=tmp_path / "second", reuse=True)

    assert counts.read_text() == "xx"  # never cacheable, so the body always runs
    for result in (first, second):
        [stage_entry] = read(result["receipt"])["stages"]
        assert stage_entry["reused"] is False
        assert stage_entry["key"] is None
        assert stage_entry["reason"]


def test_receipt_materials_and_tools_match_a_full_render(tmp_path):
    material_path = tmp_path / "material.bin"
    material_path.write_bytes(b"stage material bytes")
    digest = pool.put(material_path)
    ref = f"sha256:{digest}"
    entry = write_source(tmp_path, MATERIAL_SOURCE.format(ref=ref))

    full = run(entry, out=tmp_path / "full")
    reused_first = run(entry, out=tmp_path / "reused-first", reuse=True)
    reused_second = run(entry, out=tmp_path / "reused-second", reuse=True)

    full_materials = read(full["receipt"])["materials"]
    first_materials = read(reused_first["receipt"])["materials"]
    second_materials = read(reused_second["receipt"])["materials"]
    assert full_materials == first_materials == second_materials == [{"ref": ref}]
    assert read(reused_second["receipt"])["stages"][0]["reused"] is True


def test_reuse_outputs_equal_outputs_without_it_for_a_deterministic_work(tmp_path):
    entry = write_source(tmp_path, DETERMINISTIC_SOURCE)

    without = run(entry, out=tmp_path / "without", params={"gain": 0.4})
    with_reuse = run(entry, out=tmp_path / "with-reuse", params={"gain": 0.4}, reuse=True)

    assert (
        read(without["manifest"])["outputs"]["bed"]
        == read(with_reuse["manifest"])["outputs"]["bed"]
    )


def test_without_reuse_nothing_is_cached(tmp_path):
    entry = write_source(tmp_path, DETERMINISTIC_SOURCE)

    result = run(entry, out=tmp_path / "out")

    receipt = read(result["receipt"])
    assert receipt["reuse"] is False
    assert receipt["stages"] == []
    assert not (pool.default_pool_dir() / "stages").exists()
