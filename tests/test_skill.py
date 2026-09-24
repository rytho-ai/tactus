"""Keep the tactus-authoring skill in step with the run contract it documents."""

from __future__ import annotations

import json
from pathlib import Path

from tactus import RunError, run

SKILL = Path(__file__).parents[1] / "skills" / "tactus-authoring" / "SKILL.md"

SOURCE = """\
import numpy as np

def render(*, gain: float = 0.5):
    return {"sample_rate": 8000, "outputs": {"tone": np.full(8, gain)}}
"""


def test_skill_names_every_manifest_and_receipt_field(tmp_path, monkeypatch):
    monkeypatch.setenv("TACTUS_POOL", str(tmp_path / "pool"))
    entry = tmp_path / "work" / "song.py"
    entry.parent.mkdir()
    entry.write_text(SOURCE, encoding="utf-8")
    result = run(entry, out=tmp_path / "out")
    text = SKILL.read_text(encoding="utf-8")
    manifest = json.loads(Path(result["manifest"]).read_text())
    receipt = json.loads(Path(result["receipt"]).read_text())
    missing = [
        key
        for document in (manifest, receipt, result)
        for key in document
        if f"`{key}`" not in text and f'"{key}"' not in text
    ]
    assert not missing, f"SKILL.md does not document: {missing}"
    assert f"`format_version` {manifest['format_version']}" in text
    assert f"`format_version` {receipt['format_version']}" in text


def test_skill_names_every_error_phase():
    text = SKILL.read_text(encoding="utf-8")
    phases = {"request", "load", "bind", "execute", "validate", "publish"}
    assert all(f"`{phase}`" in text for phase in phases)
    assert RunError("x", "request", "").exit_code == 2
    assert RunError("x", "execute", "").exit_code == 1
    assert RunError("cancelled", "execute", "").exit_code == 130
