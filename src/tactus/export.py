"""Export verified completed renders through built-in or project Python functions.

Exports own their new directory and completion record. Failure removes that directory,
never the source render. Built-ins and custom exporters receive the same named arrays,
rate and keyword-only out directory. Generated files are inventoried after execution.
wav, flac and stems share one names selection; wav and flac default to every output.
store.encode_pcm24 owns quantization; FLAC transcodes its integer samples losslessly.
Float WAVs are written without libsndfile's timestamped PEAK chunk, so bytes repeat.
An exporter that declares keyword-only `time_map` and/or `run_identity` receives the run's
verified map and identity; they never become CLI flags (flag_view). web, srt and curves
(_delivery) use them; exporters without them load and run unchanged.
"""

from __future__ import annotations

import functools
import inspect
import io
import json
import os
import shutil
import sys
import zipfile
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import soundfile as sf

from . import render_store
from ._contracts import RunError, write_json
from ._delivery import curves, srt, web
from .commands import Command, identity
from .inputs.pool import hash_file
from .store import OutputStore, encode_pcm24


def _selected(outputs, names) -> dict:
    """Every output, or the named ones in the given order."""
    if names is None:
        return outputs
    if not isinstance(names, list) or not names or any(n not in outputs for n in names):
        raise ValueError("names must be a nonempty list of existing output names")
    if len(set(names)) != len(names):
        raise ValueError("names must be unique")
    return {name: outputs[name] for name in names}


def wav(
    outputs, sample_rate, *, out: Path, subtype: str = "PCM_24", names: list[str] | None = None
) -> dict:
    """Write WAV files: PCM_24 for delivery, FLOAT or DOUBLE for original headroom.

    FLOAT casts to float32; DOUBLE casts to float64; both are written without a
    timestamp, so the same audio gives the same bytes. PCM_24 uses the same clipping,
    float32 conversion and hashed names as run's default delivery. No resampling.
    Pass --names as a JSON list to write only those outputs; the default writes all.
    """
    if subtype not in ("PCM_24", "FLOAT", "DOUBLE"):
        raise ValueError("subtype must be PCM_24, FLOAT or DOUBLE")
    levels = {}
    for name, audio in _selected(outputs, names).items():
        if subtype == "PCM_24":
            _, levels[name] = OutputStore(out, sample_rate).add(name, audio)
        else:
            samples = np.asarray(audio, dtype=np.float32 if subtype == "FLOAT" else np.float64)
            if not np.isfinite(samples).all():
                raise ValueError(f"output {name!r} overflows {subtype}")
            # libsndfile stamps a timestamped PEAK chunk into float WAVs, so identical audio
            # would give different bytes on each export; SciPy writes a plain float file.
            from scipy.io import wavfile

            wavfile.write(out / f"{name}.wav", sample_rate, samples)
    return {"subtype": subtype, "levels": levels}


def flac(outputs, sample_rate, *, out: Path, names: list[str] | None = None) -> dict:
    """Write PCM24 FLACs, clipping to full scale with the default WAV conversion policy.

    Pass --names as a JSON list to write only those outputs; the default writes all.
    """
    clipped = {}
    for name, audio in _selected(outputs, names).items():
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
    selected = list(_selected(outputs, [n for n in outputs if n != "mix"] if names is None else names))
    levels = {}
    with zipfile.ZipFile(out / "stems.zip", "w", compression=zipfile.ZIP_STORED) as archive:
        for name in selected:
            payload, measured = encode_pcm24(outputs[name], sample_rate)
            levels[name] = measured["clipped_samples"]
            archive.writestr(zipfile.ZipInfo(f"{name}.wav"), payload)
    return {"names": selected, "clipped_samples": levels}


BUILTINS = {"wav": wav, "flac": flac, "stems": stems, "web": web, "srt": srt, "curves": curves}
RUNTIME_KEYWORDS = ("time_map", "run_identity")


def flag_view(fn):
    """`fn` as the CLI sees it: the same parameters without the runtime keywords."""
    signature = inspect.signature(fn)
    if not any(name in signature.parameters for name in RUNTIME_KEYWORDS):
        return fn

    @functools.wraps(fn)
    def view(*args, **kwargs):
        return fn(*args, **kwargs)

    view.__annotations__ = {
        key: value for key, value in fn.__annotations__.items() if key not in RUNTIME_KEYWORDS
    }
    view.__signature__ = signature.replace(
        parameters=[p for p in signature.parameters.values() if p.name not in RUNTIME_KEYWORDS]
    )
    return view


def _sha256(path: Path) -> str | None:
    return hash_file(path) if path.is_file() else None


def deliver(
    source: Path, *, out: Path, command: Command, params: dict, replace: bool = False
) -> dict:
    """Run an exporter into the new directory `out`; with `replace`, rewrite an earlier export.

    `replace` accepts only a directory that `tactus export` wrote (its `export.json`). The new
    export is written beside it and swapped in only after it succeeds, so a failure leaves the
    earlier export untouched.
    """
    out = Path(out).resolve()
    if not out.exists():
        return _deliver(source, out=out, command=command, params=params)
    if not replace:
        raise RunError(
            "output_exists", "request",
            f"output already exists: {out} (--replace rewrites an earlier export)",
        )  # fmt: skip
    try:
        earlier = json.loads((out / "export.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        earlier = None
    if not out.is_dir() or not isinstance(earlier, dict) or earlier.get("kind") != "tactus.export":
        raise RunError(
            "invalid_request", "request",
            f"--replace only rewrites a directory written by tactus export: {out}",
        )  # fmt: skip
    if Path(source).resolve().is_relative_to(out):
        raise RunError("invalid_request", "request", "export directory must be outside the source run")
    staging = out.parent / f".{out.name}.replacing-{os.getpid()}"
    retired = out.parent / f".{out.name}.replaced-{os.getpid()}"
    for leftover in (staging, retired):
        if leftover.exists():
            shutil.rmtree(leftover)
    result = _deliver(source, out=staging, command=command, params=params)
    out.rename(retired)
    staging.rename(out)
    shutil.rmtree(retired)

    def moved(value: str) -> str:
        return str(out / Path(value).relative_to(staging))

    return {
        **result,
        "directory": str(out),
        "manifest": moved(result["manifest"]),
        "files": {name: moved(path) for name, path in result["files"].items()},
        "replaced": True,
    }


def _deliver(source: Path, *, out: Path, command: Command, params: dict) -> dict:
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
        time_map = render_store.read_map(source, origin)
        map_sha256 = None if time_map is None else hash_file(source / "map.json")
        for audio in arrays.values():
            audio.flags.writeable = False
        declared = inspect.signature(fn).parameters
        runtime = {
            "time_map": time_map,
            "run_identity": {
                "run": str(source),
                "manifest_sha256": _sha256(source / "manifest.json"),
                "receipt_sha256": _sha256(source / "receipt.json"),
                "map_sha256": map_sha256,
                "origin": dict(origin),
            },
        }
        keywords = {**params, **{k: v for k, v in runtime.items() if k in declared}}
        out.mkdir(parents=True, exist_ok=False)
        created = True
        with redirect_stdout(sys.stderr):
            result = fn(arrays, rate, out=out, **keywords)
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
            "source": {**origin, "map": None if map_sha256 is None else {"sha256": map_sha256}},
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
            "result": result,
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
