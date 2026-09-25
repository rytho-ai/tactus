"""Slice an existing run's published outputs into a new run directory, without re-rendering.

`run` renders once; this module is the single owner of selecting and slicing what a run
already published. A slice is a plain array slice of the verified, already-published full
outputs — no padding, fade, re-normalization or re-render — so it is sample-identical to the
same frames of the source run even when the work's render is nondeterministic (e.g. a VST3
instrument whose oscillator phases differ every render). Provenance is the source run itself:
an excerpt keeps no receipt, only a `source` pointer (run path + manifest hash). Accepts a
source manifest of `format_version` 1 or 2. Excerpt outputs are already-clipped published
audio, so each carries `peak_dbfs`/`clipped_samples` for the published slice (`clipped_samples`
is always 0 there); its own manifest is `format_version` 2, following the run manifest.

Reads: run._write_json (shared JSON writer) · run.RunError · store.OutputStore/AudioRef
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from .run import RunError, _write_json
from .store import AudioRef, OutputStore, validate_name


def parse_range(raw: str) -> list[float | None]:
    """Parse CLI ``--range START:END``; END may be empty to mean "to each output's end"."""
    if raw.count(":") != 1:
        raise RunError("invalid_request", "request", f"--range must be START:END: {raw!r}")
    start_text, end_text = raw.split(":")
    if not start_text:
        raise RunError("invalid_request", "request", f"--range start is required: {raw!r}")
    try:
        start: float | None = float(start_text)
        end = float(end_text) if end_text else None
    except ValueError as exc:
        raise RunError("invalid_request", "request", f"--range must be numeric: {raw!r}") from exc
    return [start, end]


def parse_outputs(raw: str) -> list[str]:
    """Parse CLI ``--outputs a,b`` into a nonempty list of output names."""
    names = raw.split(",")
    if not raw or any(not name for name in names):
        raise RunError(
            "invalid_request",
            "request",
            f"--outputs must be a comma-separated list of names: {raw!r}",
        )
    return names


def _resolve_range(range_: Any) -> list[float | None]:
    """Request-phase shape/value validation for ``range``; the single owner of this rule."""
    if not isinstance(range_, (list, tuple)) or len(range_) != 2:
        raise ValueError("range must be [start_seconds, end_seconds]")
    start, end = range_
    for value, label in ((start, "start"), (end, "end")):
        if value is None:
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"range {label} must be a finite number or null")
    if start is None:
        raise ValueError("range start must be a number")
    if start < 0:
        raise ValueError("range start must be >= 0")
    if end is not None and end <= start:
        raise ValueError("range end must be greater than start")
    return [float(start), float(end) if end is not None else None]


def _resolve_outputs(outputs_: Any) -> list[str]:
    """Request-phase shape validation for ``outputs``; names are checked after selection."""
    if not isinstance(outputs_, list) or not outputs_:
        raise ValueError("outputs must be a nonempty list of output names")
    names = []
    for name in outputs_:
        if not isinstance(name, str) or not name:
            raise ValueError("outputs must be a list of nonempty strings")
        names.append(name)
    return names


def _select_and_slice(
    outputs: dict[str, np.ndarray],
    rate: int,
    range_spec: list[Any],
    requested: list[str] | None,
) -> tuple[dict[str, np.ndarray], dict[str, Any], dict[str, int]]:
    """Select requested outputs and slice them to a validated range, after verified read.

    The single owner of range/outputs selection. A slice is a plain array slice of the
    already-verified source arrays — no padding, fade or re-normalization — so it is
    sample-identical to the same frames of the source run.
    """
    if requested is not None:
        unknown = [name for name in requested if name not in outputs]
        if unknown:
            raise RunError(
                "invalid_request", "validate", f"unknown output name(s): {', '.join(unknown)}"
            )
        selected = {name: outputs[name] for name in requested}
    else:
        selected = dict(outputs)

    start_seconds, end_seconds = range_spec
    start_frame = round(start_seconds * rate)
    end_frame = round(end_seconds * rate) if end_seconds is not None else None
    sliced: dict[str, np.ndarray] = {}
    source_frames: dict[str, int] = {}
    omitted: list[str] = []
    for name, audio in selected.items():
        length = len(audio)
        output_start = min(start_frame, length)
        output_end = length if end_frame is None else min(end_frame, length)
        if output_start >= output_end:
            omitted.append(name)
            continue
        sliced[name] = audio[output_start:output_end]
        source_frames[name] = length
    if not sliced:
        raise RunError(
            "invalid_request", "validate", "range excludes every requested output's frames"
        )
    record = {
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "omitted": omitted,
    }
    return sliced, record, source_frames


def excerpt(
    run_dir: str | Path,
    *,
    out: str | Path,
    range: list[float | None],
    outputs: list[str] | None = None,
) -> dict[str, Any]:
    """Slice an existing run's published, hash-verified outputs into a new run directory.

    `range` is `[start_seconds, end_seconds]` (end may be `None`, meaning to each output's
    end); `outputs` is a list of output names to publish (default: every published output).
    Every selected output is re-verified against its recorded sha256 and metadata before
    slicing, so a tampered or corrupted source run fails loudly instead of publishing a
    silently wrong excerpt.
    """
    try:
        run_dir = Path(run_dir).resolve()
        out = Path(out).resolve()
        if not run_dir.is_dir():
            raise ValueError(f"run directory does not exist: {run_dir}")
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError(f"run directory has no manifest.json: {run_dir}")
        if out.exists():
            raise ValueError(f"output already exists: {out}")
        range = _resolve_range(range)
        outputs = _resolve_outputs(outputs) if outputs is not None else None
    except (ValueError, TypeError, OSError, RecursionError) as exc:
        raise RunError("invalid_request", "request", str(exc)) from exc

    completed = False
    try:
        manifest_bytes = manifest_path.read_bytes()
        try:
            manifest = json.loads(manifest_bytes)
            if manifest.get("format_version") not in (1, 2):
                raise ValueError(
                    f"unsupported manifest format_version: {manifest.get('format_version')!r}"
                )
            rate = manifest["sample_rate"]
            refs = manifest["outputs"]
            if type(rate) is not int or rate <= 0 or not isinstance(refs, dict) or not refs:
                raise ValueError("manifest sample_rate/outputs are malformed")
            for name in refs:
                validate_name(name)
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise RunError("source_corrupt", "validate", f"malformed manifest: {exc}") from exc

        source_store = OutputStore(run_dir, rate)
        full_outputs: dict[str, np.ndarray] = {}
        for name, ref_dict in refs.items():
            try:
                ref = AudioRef(
                    ref_dict["sha256"], ref_dict["frames"], ref_dict["channels"], ref_dict["file"]
                )
                full_outputs[name] = source_store.read(ref)
            except (KeyError, ValueError, TypeError, OSError) as exc:
                raise RunError(
                    "source_corrupt", "validate", f"output {name!r} failed verification: {exc}"
                ) from exc

        selected, range_record, source_frames = _select_and_slice(
            full_outputs, rate, range, outputs
        )

        try:
            out.mkdir(parents=True, exist_ok=False)
            publish_store = OutputStore(out, rate)
            references = {}
            for name, audio in selected.items():
                ref, output_levels = publish_store.add(name, audio)
                reference = {**ref.to_dict(), **output_levels}
                reference["source_frames"] = source_frames[name]
                references[name] = reference

            manifest_out = {
                "kind": "tactus.excerpt",
                "format_version": 2,
                "sample_rate": rate,
                "outputs": references,
                "range": range_record,
                "source": {
                    "run": str(run_dir),
                    "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                },
            }
            _write_json(out / "manifest.json", manifest_out)
        except (ValueError, TypeError, OSError) as exc:
            raise RunError("invalid_request", "publish", str(exc)) from exc
        completed = True
        return {
            "status": "ok",
            "outputs": {name: str(out / ref["file"]) for name, ref in references.items()},
            "manifest": str(out / "manifest.json"),
        }
    finally:
        if not completed:
            shutil.rmtree(out, ignore_errors=True)
