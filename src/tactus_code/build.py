"""Execute Git-owned Python and emit a derived arrangement plus build receipt."""

from __future__ import annotations

import hashlib
import json
import runpy
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any

from .project import Project


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_inventory(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _hash(path)
        for path in sorted(root.rglob("*.py"))
        if ".tactus-code" not in path.parts and ".venv" not in path.parts
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def build(entry: Path, output: Path) -> dict[str, Path]:
    entry = entry.resolve()
    root = entry.parent
    if not entry.is_file():
        raise FileNotFoundError(entry)
    output = output.resolve()
    if output == root or root.is_relative_to(output):
        raise ValueError("build output may not be the source project directory or its parent")
    original_path = list(sys.path)
    try:
        sys.path.insert(0, str(root))
        namespace = runpy.run_path(str(entry))
        factory = namespace.get("build")
        if not callable(factory):
            raise TypeError(f"{entry.name} must define build(project)")
        transport = namespace.get("TRANSPORT")
        if not isinstance(transport, dict) or set(transport) != {"bpm", "bars", "sample_rate"}:
            raise ValueError("song.py must define TRANSPORT with bpm, bars, and sample_rate")
        project = Project(root=root, materials=output / "materials", **transport)
        factory(project)
    finally:
        sys.path[:] = original_path
    graph = project.arrangement()
    source_files = _source_inventory(root)
    lock = root / "uv.lock"
    receipt = {
        "source_files": source_files,
        "dependency_lock_sha256": _hash(lock) if lock.is_file() else None,
        "runtime": {
            "python": sys.version.split()[0],
            "tactus_code": version("tactus-code"),
            "numpy": version("numpy"),
            "soundfile": version("soundfile"),
        },
        "reproducibility": "compiled replay only; source rebuild not guaranteed",
        "materialized_computations": len(project.computations),
    }
    graph_path = output / "arrangement.json"
    receipt_path = output / "receipt.json"
    _write_json(graph_path, graph)
    _write_json(receipt_path, receipt)
    return {"graph": graph_path, "receipt": receipt_path, "materials": output / "materials"}
