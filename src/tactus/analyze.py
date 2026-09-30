"""Common built-in/project analysis execution, JSON results and NumPy attachments.

CLI discovery and flags belong to commands.py. Here audio decoding, verified run
selection, input/source attribution and result publication have one implementation.
Analysis of a run measures its published audition WAVs, retaining existing semantics.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import soundfile as sf

from ._contracts import RunError, write_json
from .commands import Command
from .inputs.pool import hash_file
from .provenance import begin, finish
from .render_store import read_published


def json_safe(value):
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("analysis result object keys must be strings")
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def _attachments(value, directory: Path | None, arrays: dict):
    if isinstance(value, np.ndarray):
        if directory is None:
            raise ValueError("analysis returned arrays; pass --out DIR to save attachments")
        if value.dtype.hasobject:
            raise ValueError("analysis attachments cannot contain Python objects")
        key = f"array_{len(arrays)}"
        arrays[key] = value
        return {
            "file": str(directory / "arrays.npz"),
            "key": key,
            "shape": list(value.shape),
            "dtype": value.dtype.str,
        }
    if isinstance(value, dict):
        return {key: _attachments(item, directory, arrays) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_attachments(item, directory, arrays) for item in value]
    return value


def _measure(path, output, audio, rate, command, params, out, input_hash, visualization=None):
    directory = None
    created = False
    try:
        fn = command.load()
        before = begin(command, out.resolve() if out else None)
        kwargs = dict(params)
        if out is not None:
            identity = [str(path.resolve()), input_hash, params, before["callable"]]
            if visualization is not None:
                identity.append({"visualization": visualization})
            token = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            directory = out / f"{path.stem}.{command.name}.{token}"
            directory.mkdir(parents=True, exist_ok=False)
            created = True
        if "out" in inspect.signature(fn).parameters:
            kwargs["out"] = str(directory / "data.npz") if directory else None
        with redirect_stdout(sys.stderr):
            result = fn(audio, rate, **kwargs)
        if not isinstance(result, dict):
            raise TypeError("analysis must return a dict")
        if visualization is not None:
            from .analysis import image

            if directory is None:
                raise ValueError("image output requires --out DIR")
            svg = image(result, title=command.name, **visualization)
            (directory / "image.svg").write_text(svg, encoding="utf-8")
        arrays = {}
        result = json_safe(_attachments(result, directory, arrays))
        json.dumps(result, allow_nan=False)
        if arrays:
            np.savez_compressed(directory / "arrays.npz", **arrays)
        if hash_file(path) != input_hash:
            raise ValueError("analysis input changed during execution")
        report = {
            "path": str(path),
            "sample_rate": rate,
            "analysis": command.name,
            "revision": getattr(fn, "revision", None),
            "params": params,
            "result": result,
            "input_sha256": input_hash,
            "provenance": finish(command, out.resolve() if out else None, before),
        }
        if visualization is not None:
            report["visualization"] = {**visualization, "file": str(directory / "image.svg")}
        if output is not None:
            report["output"] = output
        if directory:
            artifacts = {}
            for artifact in sorted(directory.rglob("*")):
                if artifact.is_symlink() or not (artifact.is_dir() or artifact.is_file()):
                    raise ValueError("analysis artifacts must be regular files")
                if artifact.is_file():
                    relative = artifact.relative_to(directory).as_posix()
                    if relative == "result.json":
                        raise ValueError("result.json is reserved for the analysis record")
                    artifacts[relative] = {"sha256": hash_file(artifact)}
            report["artifacts"] = artifacts
            write_json(directory / "result.json", report)
        return report
    except FileExistsError as exc:
        if created:
            shutil.rmtree(directory)
            raise RunError("analysis_failed", "execute", str(exc)) from exc
        raise RunError("output_exists", "request", str(exc)) from exc
    except BaseException as exc:
        if created and directory is not None and directory.exists():
            shutil.rmtree(directory)
        if isinstance(exc, RunError):
            raise
        if isinstance(exc, KeyboardInterrupt):
            raise RunError("cancelled", "execute", "analysis cancelled") from exc
        raise RunError("analysis_failed", "execute", f"{type(exc).__name__}: {exc}") from exc


def measure(
    paths: list[Path],
    command: Command,
    params: dict,
    out: Path | None,
    *,
    visualization: dict | None = None,
) -> list[dict]:
    results = []
    for path in paths:
        if path.is_dir():
            if not (path / "manifest.json").is_file():
                raise RunError("invalid_request", "request", f"no manifest.json in {path}")
            published = read_published(path)
            for name in sorted(published.outputs):
                results.append(
                    _measure(
                        path / published.references[name].file,
                        name,
                        published.outputs[name],
                        published.sample_rate,
                        command,
                        params,
                        out,
                        published.references[name].sha256,
                        visualization,
                    )
                )
        elif path.is_file():
            try:
                input_hash = hash_file(path)
                audio, rate = sf.read(path, dtype="float64")
            except Exception as exc:
                raise RunError(
                    "invalid_request", "request", f"could not read {path}: {exc}"
                ) from exc
            results.append(
                _measure(path, None, audio, rate, command, params, out, input_hash, visualization)
            )
        else:
            raise RunError("invalid_request", "request", f"path does not exist: {path}")
    return results
