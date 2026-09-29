"""Preserve explicitly selected performances as verified folder materials.

The runner publishes candidate bundles inside its transaction. Selection imports one
bundle into the ordinary input pool; playback records that material without resolving
its historical tools. Source refs, rather than a mutable registry, choose the take.
Source snapshots are ZIP bytes, so archived Python does not join later source inventories.

Reads: inputs.material/pool/tree · store.validate_name · numpy (pickle disabled)
"""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import numpy as np

from .inputs import MaterialError, material, pool, tree
from .store import validate_name


def snapshot_source(source: Path, inventory: dict) -> bytes:
    """Snapshot the inventoried source before execution, verifying the recorded hashes."""
    files = {
        f"source/{name}": (source.parent / name, digest)
        for name, digest in inventory["source_files"].items()
    }
    lock = inventory["dependency_lock"]
    if lock:
        files["uv.lock"] = (Path(lock["path"]), lock["sha256"])
    project = source.parent / "pyproject.toml"
    if project.is_file():
        files["pyproject.toml"] = (project, pool.hash_file(project))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, (path, digest) in sorted(files.items()):
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"source changed while snapshotting: {path}")
            archive.writestr(zipfile.ZipInfo(name), data)
    return buffer.getvalue()


def publish_candidates(
    out: Path,
    takes: dict[str, np.ndarray],
    rate: int,
    snapshot: bytes,
) -> dict[str, str]:
    """Write exact arrays and provenance; return candidate tree identities, not pool imports."""
    refs = {}
    for name, audio in takes.items():
        root = out / "takes" / name
        root.mkdir(parents=True)
        np.save(root / "audio.npy", audio, allow_pickle=False)
        (root / "source.zip").write_bytes(snapshot)
        shutil.copyfile(out / "receipt.json", root / "receipt.json")
        if (out / "source.patch").is_file():
            shutil.copyfile(out / "source.patch", root / "source.patch")
        metadata = {
            "kind": "tactus.take",
            "format_version": 1,
            "name": name,
            "sample_rate": rate,
            "shape": list(audio.shape),
            "dtype": audio.dtype.str,
            "audio_sha256": pool.hash_file(root / "audio.npy"),
            "receipt_sha256": pool.hash_file(root / "receipt.json"),
            "source_sha256": pool.hash_file(root / "source.zip"),
        }
        (root / "take.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        refs[name] = tree.PREFIX + tree.digest_of_tree(root)[0]
    return refs


def _read(root: Path, sample_rate: int | None = None) -> tuple[np.ndarray, dict]:
    metadata = json.loads((root / "take.json").read_text())
    if metadata["kind"] != "tactus.take" or metadata["format_version"] != 1:
        raise ValueError("unsupported take format")
    validate_name(metadata["name"])
    rate = metadata["sample_rate"]
    if type(rate) is not int or rate <= 0:
        raise ValueError("take sample_rate must be a positive integer")
    if sample_rate is not None and rate != sample_rate:
        raise ValueError(
            f"take sample rate is {rate}, requested {sample_rate}; resample explicitly"
        )
    for filename, key in [
        ("audio.npy", "audio_sha256"),
        ("receipt.json", "receipt_sha256"),
        ("source.zip", "source_sha256"),
    ]:
        if pool.hash_file(root / filename) != metadata[key]:
            raise ValueError(f"take {filename} hash mismatch")
    audio = np.load(root / "audio.npy", allow_pickle=False)
    if not isinstance(audio, np.ndarray) or audio.dtype.kind not in "iuf":
        raise ValueError("take audio must be a real numeric array")
    if (
        audio.ndim not in (1, 2)
        or not len(audio)
        or (audio.ndim == 2 and audio.shape[1] not in (1, 2))
        or not np.isfinite(audio).all()
    ):
        raise ValueError("take audio must contain finite, nonempty mono or stereo frames")
    if list(audio.shape) != metadata["shape"] or audio.dtype.str != metadata["dtype"]:
        raise ValueError("take audio metadata mismatch")
    return audio, metadata


def load_take(ref: str, *, sample_rate: int) -> np.ndarray:
    """Load an immutable take at its original rate, dtype and shape; never regenerate it.

    Resolve a saved tree ref through material(), so the run receipt and stage cache
    record it as an input. Historical generator tools are provenance, not dependencies
    of playback. Gain/effects/placement remain ordinary Python after this call.
    """
    if type(sample_rate) is not int or sample_rate <= 0:
        raise ValueError("sample_rate must be a positive integer")
    try:
        tree.digest_from_ref(ref)
    except ValueError as exc:
        raise MaterialError("invalid_ref", ref, str(exc)) from exc
    root = material(ref)
    try:
        return _read(root, sample_rate)[0]
    except (ValueError, TypeError, KeyError, OSError, EOFError, AttributeError) as exc:
        raise MaterialError("corrupt", ref, f"invalid take: {exc}") from exc


def save_take(run_dir: str | Path, name: str) -> dict[str, Any]:
    """Verify a completed run's candidate and persist it independently of that run/cache."""
    from .run import RunError

    try:
        validate_name(name)
        run_dir = Path(run_dir).resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text())
        if manifest["kind"] != "tactus.functional-run" or manifest["format_version"] != 3:
            raise ValueError("run has no take candidates; return a takes mapping from render()")
        expected = manifest["takes"][name]
        tree.digest_from_ref(expected)
        candidate = run_dir / "takes" / name
        # Validate and import the same private copy, including its provenance.
        with tempfile.TemporaryDirectory(prefix="tactus-take-") as temporary:
            bundle = Path(temporary) / "bundle"
            shutil.copytree(candidate, bundle, symlinks=True)
            actual = tree.PREFIX + tree.digest_of_tree(bundle)[0]
            if actual != expected:
                raise ValueError("take candidate does not match the completed run")
            _, metadata = _read(bundle)
            if metadata["name"] != name or metadata["sample_rate"] != manifest["sample_rate"]:
                raise ValueError("take candidate metadata does not match the completed run")
            ref = tree.add(bundle)
            # Recheck stored content, including pre-existing pool entries.
            material(ref)
        return {"status": "ok", "name": name, "ref": ref}
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        EOFError,
        AttributeError,
        MaterialError,
    ) as exc:
        raise RunError("invalid_request", "validate", f"cannot save take: {exc}") from exc


def export_take(ref: str, *, out: str | Path) -> dict[str, Any]:
    """Copy a take bundle for `tactus material add DIR` on another machine."""
    from .run import RunError

    created = False
    destination = Path(out).resolve()
    try:
        tree.digest_from_ref(ref)
        root = material(ref)
        _read(root)
        destination.mkdir(parents=True, exist_ok=False)
        created = True
        shutil.copytree(root, destination, dirs_exist_ok=True)
        if tree.PREFIX + tree.digest_of_tree(destination)[0] != ref:
            raise ValueError("exported take hash mismatch")
        return {"status": "ok", "ref": ref, "directory": str(destination)}
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        EOFError,
        AttributeError,
        MaterialError,
    ) as exc:
        if created:
            shutil.rmtree(destination)
        raise RunError("invalid_request", "request", f"cannot export take: {exc}") from exc
