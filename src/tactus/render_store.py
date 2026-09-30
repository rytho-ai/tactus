"""Verified completed audio: original render arrays and published PCM outputs.

render.json marks a complete original render. Original-array reads verify arrays and
receipt bytes; export never falls back to PCM if an existing checkpoint is corrupt.
read_published owns legacy run/excerpt manifests and their PCM verification.
read prefers original arrays, falling back to published PCM only for legacy runs.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NamedTuple, TypedDict

import numpy as np

from ._contracts import RunError, validate_audio_mapping, write_json
from .inputs.pool import hash_file
from .store import AudioRef, OutputStore, validate_name


@dataclass(frozen=True)
class PublishedAudio:
    """Verified PCM with the exact manifest bytes and output identities that were read."""

    manifest_bytes: bytes
    sample_rate: int
    outputs: dict[str, np.ndarray]
    references: dict[str, AudioRef]


class RenderOrigin(TypedDict):
    path: str
    kind: Literal["published-pcm", "original-render"]
    sha256: str


class RenderedAudio(NamedTuple):
    """Named internal result; tuple unpacking remains compatible with previous readers."""

    sample_rate: int
    outputs: dict[str, np.ndarray]
    origin: RenderOrigin


def read_published(
    run_dir: Path,
) -> PublishedAudio:
    """Read a run or excerpt directory's manifest and every published output, each re-verified
    against its recorded sha256 and metadata, with named arrays and references.
    A malformed manifest or a failed verification raises `RunError`
    (`source_corrupt`)."""
    manifest_path = run_dir / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        if manifest.get("format_version") not in (1, 2, 3):
            raise ValueError(
                f"unsupported manifest format_version: {manifest.get('format_version')!r}"
            )
        rate = manifest["sample_rate"]
        refs = manifest["outputs"]
        if type(rate) is not int or rate <= 0 or not isinstance(refs, dict) or not refs:
            raise ValueError("manifest sample_rate/outputs are malformed")
        for name in refs:
            validate_name(name)
    except (KeyError, ValueError, TypeError, AttributeError, OSError) as exc:
        raise RunError("source_corrupt", "validate", f"malformed manifest: {exc}") from exc

    source_store = OutputStore(run_dir, rate)
    full_outputs: dict[str, np.ndarray] = {}
    references: dict[str, AudioRef] = {}
    for name, ref_dict in refs.items():
        try:
            ref = AudioRef(
                ref_dict["sha256"], ref_dict["frames"], ref_dict["channels"], ref_dict["file"]
            )
            full_outputs[name] = source_store.read(ref)
            references[name] = ref
        except (KeyError, ValueError, TypeError, OSError) as exc:
            raise RunError(
                "source_corrupt", "validate", f"output {name!r} failed verification: {exc}"
            ) from exc
    return PublishedAudio(manifest_bytes, rate, full_outputs, references)


def publish(root: Path, rate: int, outputs: dict, takes: dict | None = None) -> Path:
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
    write_json(root / "render.json", manifest)
    return root / "render.json"


def read(root: Path) -> RenderedAudio:
    try:
        path = root / "render.json"
        if not path.exists():
            published = read_published(root)
            return RenderedAudio(
                published.sample_rate,
                published.outputs,
                {
                    "path": str(root),
                    "kind": "published-pcm",
                    "sha256": hashlib.sha256(published.manifest_bytes).hexdigest(),
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
        validate_audio_mapping(arrays)
        return RenderedAudio(
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
