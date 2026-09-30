"""Execute functional productions in fresh processes and coordinate publication.

Owns request/process lifetime, render binding, receipts and failed-run cleanup.
Original arrays are committed before PCM delivery; completed renders survive a
delivery failure. Stage reuse, saved takes and output formats have dedicated owners.
Shared errors/JSON/audio contracts live in _contracts; source and environment
identities live in _source. RunError and parse_params remain available here.

Reads: _contracts · _source · inputs · stage · takes/render_store · store/revision
"""

from __future__ import annotations

import inspect
import json
import os
import runpy
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np

from . import _source as source_info
from . import render_store, revision, stage, takes
from ._contracts import RunError, json_copy, parse_params, validate_audio_mapping, write_json
from .inputs import MaterialError, ToolError, _record_snapshot, _reset_record
from .store import OutputStore

__all__ = ["RunError", "parse_params", "run"]


def _stop(process: subprocess.Popen[str]) -> None:
    """Reap the worker on cancellation; include its process group on POSIX."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    finally:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def run(
    source: str | Path,
    *,
    out: str | Path,
    params: dict[str, Any] | None = None,
    reuse: bool = False,
) -> dict[str, Any]:
    """Execute source's render(**params), returning paths to a completed new run.

    Relative assets/imports resolve from the source directory. Overrides leave
    source unchanged. Child diagnostics go to stderr; this function prints no
    result. Arbitrary author code is trusted, not sandboxed.

    `reuse=True` lets `@stage`-marked functions reuse an unchanged prior call's result
    (see `stage.py`); without it, `@stage` is a transparent call.
    """
    try:
        source = Path(source).resolve()
        out = Path(out).resolve()
        params = json_copy({} if params is None else params)
        if not isinstance(params, dict):
            raise TypeError("params must be a dictionary")
        if not source.is_file() or source.suffix != ".py":
            raise ValueError(f"source must be an existing Python file: {source}")
        if source.parent == out or source.parent.is_relative_to(out):
            raise ValueError("output cannot be the source directory or an ancestor")
    except (ValueError, TypeError, OSError, RecursionError) as exc:
        raise RunError("invalid_request", "request", str(exc)) from exc

    try:
        out.mkdir(parents=True, exist_ok=False)
    except FileExistsError as exc:
        raise RunError("output_exists", "request", f"output already exists: {out}") from exc
    except OSError as exc:
        raise RunError("publication_failed", "publish", str(exc)) from exc

    process = None
    completed = False
    try:
        with tempfile.TemporaryDirectory(prefix="tactus-run-") as temporary:
            request = Path(temporary) / "request.json"
            response = Path(temporary) / "response.json"
            write_json(
                request,
                {
                    "source": str(source),
                    "out": str(out),
                    "params": params,
                    "reuse": bool(reuse),
                },
            )
            # Load this installed Tactus before adding the author's import directory.
            bootstrap = (
                f"import sys; sys.path.insert(0, {str(Path(__file__).parent.parent)!r}); "
                "from tactus._worker import main; raise SystemExit(main())"
            )
            process = subprocess.Popen(
                # Ignore existing timestamp-based .pyc files: a rapid same-size source
                # revision must execute the bytes that the receipt inventories.
                [
                    sys.executable,
                    "-B",
                    "-X",
                    f"pycache_prefix={temporary}/pycache",
                    "-c",
                    bootstrap,
                    str(request),
                    str(response),
                ],
                cwd=source.parent,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                start_new_session=os.name == "posix",
            )
            assert process.stdout is not None
            with process.stdout:
                for diagnostic in process.stdout:
                    sys.stderr.write(diagnostic)
            process.wait()
            if not response.is_file():
                raise RunError(
                    "worker_failed",
                    "execute",
                    f"worker exited with status {process.returncode} without a result",
                )
            result = json.loads(response.read_text(encoding="utf-8"))
            if result.get("status") == "error":
                raise RunError(**result["error"])
            if process.returncode != 0 or result.get("status") != "ok":
                raise RunError(
                    "worker_failed",
                    "execute",
                    f"worker did not complete successfully: {process.returncode}",
                )
            if not (out / "manifest.json").is_file():
                raise RunError("worker_failed", "publish", "worker omitted the completion manifest")
        completed = True
        return result
    except KeyboardInterrupt as exc:
        raise RunError("cancelled", "execute", "run cancelled") from exc
    except RunError:
        raise
    except Exception as exc:
        raise RunError("worker_failed", "execute", str(exc)) from exc
    finally:
        if not completed:
            if process is not None:
                _stop(process)
            if (out / "render.json").is_file():
                # Keep the complete original arrays/receipt/takes, remove partial default WAVs.
                for path in out.glob("*.wav"):
                    path.unlink(missing_ok=True)
                (out / "manifest.json").unlink(missing_ok=True)
            else:
                shutil.rmtree(out, ignore_errors=True)


def _bind(factory: Any, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not inspect.isfunction(factory) or inspect.iscoroutinefunction(factory):
        raise ValueError("source must define a synchronous render function")
    if inspect.isgeneratorfunction(factory) or inspect.isasyncgenfunction(factory):
        raise ValueError("render must return audio, not yield it")
    signature = inspect.signature(factory)
    for parameter in signature.parameters.values():
        if parameter.kind != inspect.Parameter.KEYWORD_ONLY:
            raise ValueError("render accepts only explicitly named keyword-only parameters")
        if parameter.default is not inspect.Parameter.empty:
            json_copy(parameter.default)
    bound = signature.bind(**params)
    bound.apply_defaults()
    effective = json_copy(dict(bound.arguments))
    # Author mutation must not change the receipt's record of the input values.
    return json_copy(effective), effective


def _validate(result: Any) -> tuple[int, dict[str, np.ndarray]]:
    if not isinstance(result, dict) or set(result) not in (
        {"sample_rate", "outputs"},
        {"sample_rate", "outputs", "takes"},
    ):
        raise ValueError("render must return {sample_rate, outputs} with optional takes")
    rate = result["sample_rate"]
    if type(rate) is not int or rate <= 0:
        raise ValueError("sample_rate must be a positive integer")
    outputs = result["outputs"]
    if not isinstance(outputs, dict) or not outputs:
        raise ValueError("outputs must be a nonempty dictionary")
    validate_audio_mapping(outputs)
    if "takes" in result:
        validate_audio_mapping(result["takes"])
    return rate, outputs


def _execute(request: dict[str, Any]) -> dict[str, Any]:
    """Worker-only execution; phase labels keep diagnostics useful to callers."""
    source, out = Path(request["source"]), Path(request["out"])
    phase = "load"
    try:
        before = source_info.inventory(source.parent, out)
        snapshot = takes.snapshot_source(source, before)
        git = revision.record(source.parent, out)
        _reset_record()
        reuse = bool(request.get("reuse", False))
        stage._begin_run(
            reuse=reuse,
            source_files=before["source_files"],
            dependency_lock=before["dependency_lock"],
            python_version=sys.version.split()[0],
            tactus_version=version("tactus"),
        )
        sys.path.insert(0, str(source.parent))
        namespace = runpy.run_path(str(source), run_name="__tactus__")
        phase = "bind"
        factory = namespace.get("render")
        arguments, effective = _bind(factory, request["params"])
        phase = "execute"
        started = time.perf_counter()
        result = factory(**arguments)
        elapsed_seconds = round(time.perf_counter() - started, 3)
        stages = stage._end_run()
        inputs_used = _record_snapshot()
        python_packages = source_info.python_packages()
        environment = source_info.environment()
        # Tactus itself is always attributed even though `packages_distributions()`
        # does not map its own editable install back to `tactus.*` modules.
        package_sources = source_info.package_sources(sorted({*python_packages, "tactus"}))
        phase = "validate"
        rate, outputs = _validate(result)
        phase = "publish"
        if source_info.inventory(source.parent, out) != before:
            raise RunError(
                "source_changed", phase, "source or nearest uv.lock changed during execution"
            )
        identity = {"kind": "tactus.functional-run"}
        receipt = {
            **identity,
            "format_version": 4,
            "entry": {"path": str(source), "function": "render"},
            "parameters": effective,
            **before,
            "git": git,
            "materials": inputs_used["materials"],
            "tools": inputs_used["tools"],
            "python_packages": python_packages,
            "environment": environment,
            "package_sources": package_sources,
            "elapsed_seconds": elapsed_seconds,
            "stages": stages,
            "reuse": reuse,
            "runtime": {
                "python": sys.version.split()[0],
                **{name: version(name) for name in ("tactus", "numpy", "soundfile")},
            },
            "reproducibility": "saved outputs only; source rebuild not guaranteed",
            "attribution_scope": "Traced: entry-directory Python files, the nearest uv.lock, "
            "resolved materials, declared tools and imported third-party distributions. "
            "Not traced: undeclared files or executables, network access and randomness.",
        }
        write_json(out / "receipt.json", receipt)
        take_refs = (
            takes.publish_candidates(out, result["takes"], rate, snapshot)
            if "takes" in result
            else {}
        )
        render_store.publish(out, rate, outputs, take_refs)
        # A completed render is durable before the optional default delivery can fail.
        store = OutputStore(out, rate)
        references = {}
        levels = {}
        for name, audio in outputs.items():
            ref, output_levels = store.add(name, audio)
            references[name] = {**ref.to_dict(), **output_levels}
            levels[name] = output_levels
        manifest = {
            **identity,
            "format_version": 2,
            "sample_rate": rate,
            "outputs": references,
        }
        if "takes" in result:
            manifest["takes"] = take_refs
            manifest["format_version"] = 3
        write_json(out / "manifest.json", manifest)
        return {
            **({"takes": manifest["takes"]} if "takes" in manifest else {}),
            "status": "ok",
            "outputs": {name: str(out / ref["file"]) for name, ref in references.items()},
            "manifest": str(out / "manifest.json"),
            "receipt": str(out / "receipt.json"),
            "render": str(out / "render.json"),
            "levels": levels,
        }
    except (MaterialError, ToolError) as exc:
        code = "material_unavailable" if isinstance(exc, MaterialError) else "tool_unavailable"
        raise RunError(code, phase, str(exc)) from exc
    except RunError:
        raise
    except BaseException as exc:
        codes = {
            "load": "load_failed",
            "bind": "invalid_parameters",
            "execute": "execution_failed",
            "validate": "invalid_output",
            "publish": "publication_failed",
        }
        message = f"{type(exc).__name__}: {exc}"
        if (out / "render.json").is_file():
            message += (
                f"; completed render retained at {out}; retry delivery with "
                f"tactus export wav {out} --out NEW_DIR"
            )
        raise RunError(codes[phase], phase, message) from exc
