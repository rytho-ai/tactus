"""Export verified completed renders through built-in or project Python functions.

Exports own their new directory and completion record. Failure removes that directory,
never the source render. Built-ins and custom exporters receive the same named arrays,
rate and keyword-only out directory. Generated files are inventoried after execution.
store.encode_pcm24 owns quantization; FLAC transcodes its integer samples losslessly.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import soundfile as sf

from . import render_store
from ._contracts import RunError, write_json
from .commands import Command, identity
from .inputs.pool import hash_file
from .store import OutputStore, encode_pcm24


def wav(outputs, sample_rate, *, out: Path, subtype: str = "PCM_24") -> dict:
    """Write WAV files: PCM_24 for delivery, FLOAT or DOUBLE for original headroom.

    FLOAT casts to float32; DOUBLE casts to float64. PCM_24 uses the same clipping,
    float32 conversion and hashed names as run's default delivery. No resampling.
    """
    if subtype not in ("PCM_24", "FLOAT", "DOUBLE"):
        raise ValueError("subtype must be PCM_24, FLOAT or DOUBLE")
    levels = {}
    for name, audio in outputs.items():
        if subtype == "PCM_24":
            _, levels[name] = OutputStore(out, sample_rate).add(name, audio)
        else:
            samples = np.asarray(audio, dtype=np.float32 if subtype == "FLOAT" else np.float64)
            if not np.isfinite(samples).all():
                raise ValueError(f"output {name!r} overflows {subtype}")
            sf.write(out / f"{name}.wav", samples, sample_rate, subtype=subtype)
    return {"subtype": subtype, "levels": levels}


def flac(outputs, sample_rate, *, out: Path) -> dict:
    """Write PCM24 FLACs, clipping to full scale with the default WAV conversion policy."""
    clipped = {}
    for name, audio in outputs.items():
        payload, levels = encode_pcm24(audio, sample_rate)
        clipped[name] = levels["clipped_samples"]
        # Float-to-FLAC conversion can round differently from float-to-WAV by one LSB.
        # Feed the WAV's already-quantized integers to the lossless FLAC encoder.
        samples, _ = sf.read(io.BytesIO(payload), dtype="int32")
        sf.write(out / f"{name}.flac", samples, sample_rate, subtype="PCM_24")
    return {"subtype": "PCM_24", "clipped_samples": clipped}


def stems(outputs, sample_rate, *, out: Path, names: list[str] | None = None) -> dict:
    """Bundle named PCM24 WAVs into stems.zip. Default includes every output except mix.

    Pass --names as a JSON list to select explicitly. Lengths are preserved; this does
    not align, mix, normalize or infer stems, and stem sums need not match a master.
    """
    selected = [n for n in outputs if n != "mix"] if names is None else names
    if not isinstance(selected, list) or not selected or any(n not in outputs for n in selected):
        raise ValueError("names must be a nonempty list of existing output names")
    if len(set(selected)) != len(selected):
        raise ValueError("names must be unique")
    levels = {}
    with zipfile.ZipFile(out / "stems.zip", "w", compression=zipfile.ZIP_STORED) as archive:
        for name in selected:
            payload, measured = encode_pcm24(outputs[name], sample_rate)
            levels[name] = measured["clipped_samples"]
            archive.writestr(zipfile.ZipInfo(f"{name}.wav"), payload)
    return {"names": selected, "clipped_samples": levels}


BUILTINS = {"wav": wav, "flac": flac, "stems": stems}


def deliver(source: Path, *, out: Path, command: Command, params: dict) -> dict:
    from .provenance import begin, finish

    source, out = source.resolve(), out.resolve()
    if out.exists():
        raise RunError("output_exists", "request", f"output already exists: {out}")
    if source == out or source.is_relative_to(out) or out.is_relative_to(source):
        raise RunError(
            "invalid_request", "request", "export directory must be outside the source run"
        )
    created = False
    try:
        fn = command.load()
        provenance = begin(command, out)
        rendered = render_store.read(source)
        rate, arrays, origin = rendered.sample_rate, rendered.outputs, rendered.origin
        for audio in arrays.values():
            audio.flags.writeable = False
        out.mkdir(parents=True, exist_ok=False)
        created = True
        with redirect_stdout(sys.stderr):
            result = fn(arrays, rate, out=out, **params)
        if not isinstance(result, dict):
            raise TypeError("exporter must return a JSON object")
        json.dumps(result, allow_nan=False)
        files = {}
        for path in sorted(out.rglob("*")):
            if path.is_symlink():
                raise ValueError("exported artifacts must not be symlinks")
            if path.is_file():
                relative = path.relative_to(out).as_posix()
                if relative == "export.json":
                    raise ValueError("export.json is reserved for the runtime")
                files[relative] = {"sha256": hash_file(path), "bytes": path.stat().st_size}
            elif not path.is_dir():
                raise ValueError("exported artifacts must be regular files")
        if not files:
            raise ValueError("exporter did not write any files")
        # Verify that the source still identifies the same completed render.
        marker = source / (
            "render.json" if origin["kind"] == "original-render" else "manifest.json"
        )
        if hash_file(marker) != origin["sha256"]:
            raise ValueError("source render changed during export")
        record = {
            "kind": "tactus.export",
            "format_version": 1,
            "source": origin,
            "exporter": identity(command),
            "params": params,
            "sample_rate": rate,
            "files": files,
            "result": result,
            "provenance": finish(command, out, provenance),
        }
        write_json(out / "export.json", record)
        return {
            "status": "ok",
            "directory": str(out),
            "manifest": str(out / "export.json"),
            "files": {name: str(out / name) for name in files},
        }
    except RunError:
        if created:
            shutil.rmtree(out)
        raise
    except BaseException as exc:
        if created:
            shutil.rmtree(out)
        if isinstance(exc, KeyboardInterrupt):
            raise RunError("cancelled", "execute", "export cancelled") from exc
        raise RunError("export_failed", "execute", f"{type(exc).__name__}: {exc}") from exc
