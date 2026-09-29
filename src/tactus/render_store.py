"""Durable original render arrays, completed before delivery encoding.

render.json is this boundary's completion marker. Every read verifies arrays and
receipt bytes; export never falls back to PCM if an existing checkpoint is corrupt.
Legacy runs without this marker remain readable through excerpt.read_published.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from .inputs.pool import hash_file
from .store import validate_name


def publish(root: Path, rate: int, outputs: dict, takes: dict | None = None) -> Path:
    from .run import _write_json

    directory = root / "render"
    directory.mkdir()
    entries = {}
    for name, audio in outputs.items():
        validate_name(name)
        path = directory / f"{name}.npy"
        np.save(path, audio, allow_pickle=False)
        entries[name] = {
            "file": f"render/{name}.npy",
            "sha256": hash_file(path),
            "shape": list(audio.shape),
            "dtype": audio.dtype.str,
        }
    manifest = {
        "kind": "tactus.render",
        "format_version": 1,
        "sample_rate": rate,
        "outputs": entries,
        "receipt_sha256": hash_file(root / "receipt.json"),
    }
    if takes:
        manifest["takes"] = takes
    _write_json(root / "render.json", manifest)
    return root / "render.json"


def read(root: Path) -> tuple[int, dict, dict]:
    from .run import RunError

    try:
        path = root / "render.json"
        if not path.exists():
            from .excerpt import read_published

            payload, rate, arrays, _ = read_published(root)
            return (
                rate,
                arrays,
                {
                    "path": str(root),
                    "kind": "published-pcm",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                },
            )
        payload = path.read_bytes()
        manifest = json.loads(payload)
        if manifest["kind"] != "tactus.render" or manifest["format_version"] != 1:
            raise ValueError("unsupported render checkpoint")
        rate = manifest["sample_rate"]
        if type(rate) is not int or rate <= 0:
            raise ValueError("invalid render sample rate")
        if hash_file(root / "receipt.json") != manifest["receipt_sha256"]:
            raise ValueError("render receipt hash mismatch")
        arrays = {}
        for name, item in manifest["outputs"].items():
            validate_name(name)
            if item["file"] != f"render/{name}.npy":
                raise ValueError("invalid render array path")
            array_path = root / item["file"]
            if array_path.is_symlink() or hash_file(array_path) != item["sha256"]:
                raise ValueError(f"render array hash mismatch: {name}")
            audio = np.load(array_path, allow_pickle=False)
            if list(audio.shape) != item["shape"] or audio.dtype.str != item["dtype"]:
                raise ValueError(f"render array metadata mismatch: {name}")
            arrays[name] = audio
        from .run import _validate_audio_mapping

        _validate_audio_mapping(arrays)
        return (
            rate,
            arrays,
            {
                "path": str(root),
                "kind": "original-render",
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        )
    except RunError:
        raise
    except (ValueError, TypeError, KeyError, OSError, EOFError, AttributeError) as exc:
        raise RunError("source_corrupt", "validate", f"invalid render checkpoint: {exc}") from exc
