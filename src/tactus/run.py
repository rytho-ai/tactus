"""Run functional Python productions in fresh processes and publish named PCM outputs.

Optional render `takes` preserves exact intermediate arrays with source and receipt in
run-local candidate bundles (manifest version 3). `takes.py` owns their format and
explicit promotion to materials; ordinary runs keep manifest version 2.

The public runner owns request validation, process lifetime and failed-run cleanup.
The private worker calls _execute for source binding, attribution and OutputStore
publication. Manifests identify saved audio, plus each output's `peak_dbfs` and
`clipped_samples` from `OutputStore.add` (manifest `format_version` 2); the run result's
`levels` mirrors the same numbers so the Agent sees them without opening the manifest.
Nothing about level is refused — over-full-scale audio publishes clipped. Receipts
attribute the bounded execution, including resolved input materials, declared tools and
imported package versions (`tactus.inputs`) (receipt `format_version` 4, adding `stages`,
`reuse`, `environment` and `package_sources` — the interpreter's project lock and each
non-index distribution's PEP 610 origin, so a work can be rebuilt in another directory).
To hear part of a run, or only some of its outputs, slice an already
completed run with `tactus.excerpt` instead of re-rendering — a work whose render is
nondeterministic (e.g. a VST3 instrument) would otherwise produce a different
performance.

With `reuse=True` (CLI `--reuse`), `_execute` computes this run's stage key parts once
from data it already gathers (`source_files`, `dependency_lock`, the Python and Tactus
versions) and hands them to `stage.py` before calling `render`, so `@stage`-marked
functions can reuse an unchanged prior call's result; see `stage.py` for the key and
storage. Without `--reuse`, `@stage` is a transparent call and this costs nothing.

`_direct_url` is the single PEP 610 reader (`_package_sources` uses it for attribution;
`init.py` reuses it to resolve the running Tactus's own origin when scaffolding a work).

Reads: inputs.MaterialError/ToolError/_record_snapshot/_reset_record · store.OutputStore
· stage._begin_run/_end_run
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import os
import runpy
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from importlib.metadata import PackageNotFoundError, distribution, packages_distributions, version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import url2pathname

import numpy as np

from . import revision, stage, takes
from .inputs import MaterialError, ToolError, _record_snapshot, _reset_record
from .store import OutputStore, validate_name


class RunError(Exception):
    """A failed run with a stable code and the phase in which it failed."""

    def __init__(self, code: str, phase: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.phase = phase

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "error",
            "error": {
                "code": self.code,
                "phase": self.phase,
                "message": str(self),
            },
        }

    @property
    def exit_code(self) -> int:
        if self.code == "cancelled":
            return 130
        return 2 if self.phase in {"request", "load", "bind"} else 1


def _json_copy(value: Any) -> Any:
    """Validate JSON values without silently coercing tuples or nonstring keys."""
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_json_copy(item) for item in value]
    if type(value) is dict and all(isinstance(key, str) for key in value):
        return {key: _json_copy(item) for key, item in value.items()}
    raise ValueError("parameters must contain finite JSON values and string object keys")


def parse_params(raw: str) -> dict[str, Any]:
    """Parse CLI overrides, rejecting duplicate keys and nonstandard JSON numbers."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate parameter key: {key}")
            result[key] = value
        return result

    try:
        params = _json_copy(json.loads(raw, object_pairs_hook=pairs))
        if not isinstance(params, dict):
            raise TypeError("--params must be a JSON object")
        return params
    except (ValueError, TypeError, RecursionError) as exc:
        raise RunError("invalid_request", "request", str(exc)) from exc


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


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
        params = _json_copy({} if params is None else params)
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
            _write_json(
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
            shutil.rmtree(out, ignore_errors=True)


def _find_lock(start: Path) -> Path | None:
    """Walk upward from `start` for the nearest `uv.lock`, stopping at the filesystem root."""
    current = start
    while True:
        candidate = current / "uv.lock"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _inventory(root: Path, output: Path) -> dict[str, Any]:
    excluded = {".tactus", ".tactus-code", ".venv", "__pycache__", ".git"}
    files = {}
    for directory, children, names in os.walk(root):
        children[:] = [
            name
            for name in children
            if name not in excluded and (Path(directory) / name).resolve() != output
        ]
        for name in sorted(names):
            if name.endswith(".py"):
                path = Path(directory) / name
                files[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    lock = _find_lock(root)
    return {
        "source_files": files,
        "dependency_lock": {
            "path": str(lock),
            "sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        }
        if lock is not None
        else None,
    }


def _python_packages() -> dict[str, str]:
    """Map imported top-level modules to installed distribution versions, minus stdlib."""
    mapping = packages_distributions()
    stdlib = sys.stdlib_module_names
    result: dict[str, str] = {}
    for name in list(sys.modules):
        top = name.split(".", 1)[0]
        if top in stdlib:
            continue
        for dist_name in mapping.get(top, ()):
            if dist_name in result:
                continue
            try:
                result[dist_name] = version(dist_name)
            except PackageNotFoundError:  # pragma: no cover - defensive; metadata inconsistent
                pass
    return dict(sorted(result.items()))


def _environment() -> dict[str, Any]:
    """The running interpreter's prefix and, when it owns a project, that project's lock."""
    prefix = Path(sys.prefix)
    candidate = prefix.parent / "uv.lock"
    lock = (
        {"path": str(candidate), "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest()}
        if candidate.is_file()
        else None
    )
    return {"prefix": str(prefix), "lock": lock}


def _direct_url(name: str) -> dict[str, Any] | None:
    """Parsed PEP 610 `direct_url.json` for an installed distribution, or None without one.

    Shared by `_package_sources` (receipt attribution) and `init.py` (resolving the
    running Tactus's own origin to pin a new work) so the parsing lives in one place.
    """
    try:
        raw = distribution(name).read_text("direct_url.json")
    except PackageNotFoundError:  # pragma: no cover - defensive; metadata inconsistent
        return None
    if raw is None:
        return None
    return json.loads(raw)


def _package_sources(names: list[str]) -> dict[str, Any]:
    """PEP 610 origin of each named distribution not installed from an index.

    Reads each distribution's `direct_url.json`; a distribution with none (an index
    install) is omitted, since the lock already pins it.
    """
    result: dict[str, Any] = {}
    for name in names:
        data = _direct_url(name)
        if data is None:
            continue
        url = data.get("url", "")
        vcs_info = data.get("vcs_info")
        dir_info = data.get("dir_info")
        archive_info = data.get("archive_info")
        if vcs_info:
            result[name] = {
                "url": url,
                "vcs": vcs_info.get("vcs"),
                "commit": vcs_info.get("commit_id"),
            }
        elif dir_info:
            entry: dict[str, Any] = {"url": url, "editable": bool(dir_info.get("editable", False))}
            parsed = urlparse(url)
            if parsed.scheme == "file":
                git = revision.describe(Path(url2pathname(parsed.path)))
                if git is not None:
                    entry["git"] = git
            result[name] = entry
        elif archive_info and archive_info.get("hash"):
            result[name] = {"url": url, "hash": archive_info["hash"]}
    return dict(sorted(result.items()))


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
            _json_copy(parameter.default)
    bound = signature.bind(**params)
    bound.apply_defaults()
    effective = _json_copy(dict(bound.arguments))
    # Author mutation must not change the receipt's record of the input values.
    return _json_copy(effective), effective


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
    _validate_audio_mapping(outputs)
    if "takes" in result:
        _validate_audio_mapping(result["takes"])
    return rate, outputs


def _validate_audio_mapping(outputs: Any) -> None:
    if not isinstance(outputs, dict) or not outputs:
        raise ValueError("audio mapping must be a nonempty dictionary")
    for name, audio in outputs.items():
        if not isinstance(name, str) or not name:
            raise ValueError("output labels must be nonempty strings")
        validate_name(name)
        if not isinstance(audio, np.ndarray) or audio.dtype.kind not in "iuf":
            raise ValueError(f"output {name!r} must be a real numeric NumPy array")
        if (
            audio.ndim not in (1, 2)
            or not len(audio)
            or (audio.ndim == 2 and audio.shape[1] not in (1, 2))
        ):
            raise ValueError(f"output {name!r} must contain nonempty mono or stereo frames")
        if not np.isfinite(audio).all():
            raise ValueError(f"output {name!r} contains NaN or infinity")


def _execute(request: dict[str, Any]) -> dict[str, Any]:
    """Worker-only execution; phase labels keep diagnostics useful to callers."""
    source, out = Path(request["source"]), Path(request["out"])
    phase = "load"
    try:
        before = _inventory(source.parent, out)
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
        python_packages = _python_packages()
        environment = _environment()
        # Tactus itself is always attributed even though `packages_distributions()`
        # does not map its own editable install back to `tactus.*` modules.
        package_sources = _package_sources(sorted({*python_packages, "tactus"}))
        phase = "validate"
        rate, outputs = _validate(result)
        phase = "publish"
        store = OutputStore(out, rate)
        references = {}
        levels = {}
        for name, audio in outputs.items():
            ref, output_levels = store.add(name, audio)
            references[name] = {**ref.to_dict(), **output_levels}
            levels[name] = output_levels
        if _inventory(source.parent, out) != before:
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
        _write_json(out / "receipt.json", receipt)
        manifest = {
            **identity,
            "format_version": 2,
            "sample_rate": rate,
            "outputs": references,
        }
        if "takes" in result:
            manifest["takes"] = takes.publish_candidates(out, result["takes"], rate, snapshot)
            manifest["format_version"] = 3
        _write_json(out / "manifest.json", manifest)
        return {
            **({"takes": manifest["takes"]} if "takes" in manifest else {}),
            "status": "ok",
            "outputs": {name: str(out / ref["file"]) for name, ref in references.items()},
            "manifest": str(out / "manifest.json"),
            "receipt": str(out / "receipt.json"),
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
        raise RunError(codes[phase], phase, f"{type(exc).__name__}: {exc}") from exc
