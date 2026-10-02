"""Verified completed audio: original render arrays and published PCM outputs.

render.json marks a complete original render. Original-array reads verify arrays and
receipt bytes; export never falls back to PCM if an existing checkpoint is corrupt.
read_published owns legacy run/excerpt manifests and their PCM verification.
read prefers original arrays, falling back to published PCM only for legacy runs.
prune removes a run's original arrays after verifying its published PCM, marker first.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, NamedTuple, TypedDict

import numpy as np

from ._contracts import RunError, validate_audio_mapping, write_json
from .inputs import MaterialError, _material_tree_files, tree
from .inputs.pool import DIGEST_RE, hash_file
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


@dataclass(frozen=True)
class LoadedRender:
    """Original saved arrays, their sample rate and fixed material/checkpoint identity."""

    sample_rate: int
    outputs: Mapping[str, np.ndarray]
    origin: Mapping[str, str]


class _OutputSelectionError(ValueError):
    """An invalid caller selection, distinct from malformed checkpoint content."""


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


def prune(root: Path) -> dict:
    """Remove a completed run's original arrays, keeping its published audio and records.

    The published PCM is verified first, so the run stays readable as `published-pcm`.
    `render.json` goes before `render/`: a marker without its arrays reads as a corrupt
    checkpoint, a missing marker as a run that never had one. Takes, the receipt and the
    manifest are untouched. Returns the bytes freed (0 when there was no checkpoint).
    """
    root = Path(root)
    if not (root / "manifest.json").is_file():
        raise RunError("invalid_request", "request", f"not a completed run or excerpt: {root}")
    read_published(root)
    marker, arrays = root / "render.json", root / "render"
    if arrays.is_symlink() or marker.is_symlink():
        raise RunError("invalid_request", "request", f"render files must not be symlinks: {root}")
    files = sorted(arrays.glob("*.npy")) if arrays.is_dir() else []
    freed = sum(f.stat().st_size for f in files) + (marker.stat().st_size if marker.is_file() else 0)
    marker.unlink(missing_ok=True)
    for file in files:
        file.unlink()
    if arrays.is_dir() and not any(arrays.iterdir()):
        arrays.rmdir()
    return {"freed_bytes": freed, "kind": "published-pcm"}


def _checkpoint(
    file: Callable[[str, str | None], Path],
    outputs: list[str] | tuple[str, ...] | None = None,
) -> tuple[int, dict[str, np.ndarray], str]:
    """Shared original-array validation for local export and selected material reads."""

    def unique_pairs(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate checkpoint field: {key}")
            result[key] = value
        return result

    payload = file("render.json", None).read_bytes()
    manifest = json.loads(payload, object_pairs_hook=unique_pairs)
    if (
        manifest["kind"] != "tactus.render"
        or type(manifest["format_version"]) is not int
        or manifest["format_version"] != 1
    ):
        raise ValueError("unsupported render checkpoint")
    rate = manifest["sample_rate"]
    if type(rate) is not int or rate <= 0:
        raise ValueError("invalid render sample rate")
    receipt_digest = manifest["receipt_sha256"]
    if not isinstance(receipt_digest, str) or not DIGEST_RE.fullmatch(receipt_digest):
        raise ValueError("invalid render receipt digest")
    file("receipt.json", receipt_digest)
    items = manifest["outputs"]
    if not isinstance(items, dict) or not items:
        raise ValueError("render outputs must be a nonempty mapping")
    for name, item in items.items():
        validate_name(name)
        if item["file"] != f"render/{name}.npy":
            raise ValueError("invalid render array path")
        digest, shape, dtype = item["sha256"], item["shape"], item["dtype"]
        if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
            raise ValueError(f"invalid render array digest: {name}")
        if (
            not isinstance(shape, list)
            or len(shape) not in (1, 2)
            or any(type(size) is not int or size <= 0 for size in shape)
            or (len(shape) == 2 and shape[1] not in (1, 2))
            or not isinstance(dtype, str)
            or np.dtype(dtype).kind not in "iuf"
        ):
            raise ValueError(f"invalid render array metadata: {name}")
    names = list(items) if outputs is None else outputs
    if (
        not isinstance(names, (list, tuple))
        or not names
        or any(not isinstance(name, str) for name in names)
        or len(set(names)) != len(names)
    ):
        raise ValueError("outputs must be a nonempty list or tuple of unique names")
    unknown = set(names) - items.keys()
    if unknown:
        raise _OutputSelectionError(f"unknown render outputs: {sorted(unknown)}")
    arrays = {}
    for name in names:
        item = items[name]
        audio = np.load(file(item["file"], item["sha256"]), allow_pickle=False)
        if not isinstance(audio, np.ndarray):
            if hasattr(audio, "close"):
                audio.close()
            raise TypeError(f"render output must be an array: {name}")
        if list(audio.shape) != item["shape"] or audio.dtype.str != item["dtype"]:
            raise ValueError(f"render array metadata mismatch: {name}")
        arrays[name] = audio
    validate_audio_mapping(arrays)
    return rate, arrays, hashlib.sha256(payload).hexdigest()


def load_render(ref: str, *, outputs: list[str] | tuple[str, ...] | None = None) -> LoadedRender:
    """Load selected original outputs from a pinned render folder material.

    Import a completed run with `tactus material add RUN_DIR`, then pin its tree ref
    in source. Returns readonly arrays at their original rate, dtype and shape.
    `outputs=None` selects all; a list/tuple selects named outputs in that order.
    Copy an array before editing it. No regeneration, resampling or PCM fallback.

    Verifies the tree index, render checkpoint, receipt and selected arrays each call.
    Unrequested audio is neither loaded nor verified; this is not a whole-tree health
    check. The tree ref is captured as an input by run receipts and stage captures.
    Missing/corrupt materials raise MaterialError; invalid selections raise ValueError.
    """
    if outputs is not None and (
        not isinstance(outputs, (list, tuple))
        or not outputs
        or any(not isinstance(name, str) for name in outputs)
        or len(set(outputs)) != len(outputs)
    ):
        raise ValueError("outputs must be a nonempty list or tuple of unique names")
    files = _material_tree_files(ref)
    try:
        rate, arrays, digest = _checkpoint(files.file, outputs)
    except _OutputSelectionError:
        raise
    except tree.TreeError as exc:
        raise MaterialError(exc.reason, ref, str(exc)) from exc
    except (ValueError, TypeError, KeyError, OSError, EOFError, AttributeError) as exc:
        raise MaterialError("corrupt", ref, f"invalid render checkpoint: {exc}") from exc
    for audio in arrays.values():
        audio.setflags(write=False)
    return LoadedRender(
        rate,
        MappingProxyType(arrays),
        MappingProxyType({"ref": ref, "kind": "original-render", "sha256": digest}),
    )


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

        def local_file(relative: str, expected: str | None) -> Path:
            file_path = root / relative
            if file_path.is_symlink() or file_path.parent.is_symlink():
                raise ValueError(f"render file must not be a symlink: {relative}")
            if expected is not None and hash_file(file_path) != expected:
                raise ValueError(f"render file hash mismatch: {relative}")
            return file_path

        rate, arrays, digest = _checkpoint(local_file)
        return RenderedAudio(
            rate,
            arrays,
            {
                "path": str(root),
                "kind": "original-render",
                "sha256": digest,
            },
        )
    except RunError:
        raise
    except (ValueError, TypeError, KeyError, OSError, EOFError, AttributeError) as exc:
        raise RunError("source_corrupt", "validate", f"invalid render checkpoint: {exc}") from exc
