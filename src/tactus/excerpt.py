"""Slice an existing run's published outputs into a new run directory, without re-rendering.

`run` renders once; this module is the single owner of selecting and slicing what a run
already published. A slice is a plain array slice of the verified, already-published full
outputs — no padding, fade, re-normalization or re-render — so it is sample-identical to the
same frames of the source run even when the work's render is nondeterministic (e.g. a VST3
instrument whose oscillator phases differ every render). Provenance is the source run itself:
an excerpt keeps no receipt, only a `source` pointer (run path + manifest hash). Accepts a
source manifest of `format_version` 1, 2 or 3. Excerpt outputs are already-clipped published
audio, so each carries `peak_dbfs`/`clipped_samples` for the published slice (`clipped_samples`
is always 0 there); its own manifest is `format_version` 2, following the run manifest.

Reads: _contracts · render_store · store.OutputStore · timing.frame_of
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from . import render_store
from ._contracts import RunError, write_json
from .store import OutputStore
from .timing import frame_of


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


def parse_beats(raw: str) -> list[int]:
    """Parse two explicit 1-based beat-point indices, with the end exclusive."""
    try:
        parts = raw.split(":")
        if len(parts) != 2 or any(not part.isascii() or not part.isdecimal() for part in parts):
            raise ValueError
        return [int(part) for part in parts]
    except ValueError as exc:
        raise RunError(
            "invalid_request", "request", "--beats must be START:END integer indices"
        ) from exc


def _beat_range(grid: Any, beats: Any) -> tuple[list[float], dict[str, Any]]:
    """Resolve an explicitly adopted seconds grid and retain its selection identity."""
    source = None
    if isinstance(grid, (str, Path)):
        path = Path(grid).resolve()
        data = path.read_bytes()
        grid = json.loads(data)
        source = {"file": str(path), "sha256": hashlib.sha256(data).hexdigest()}
    if isinstance(grid, dict):
        grid = grid.get("result", grid)
        if not isinstance(grid, dict):
            raise TypeError("beat grid result must contain beats_s")
        grid = grid.get("beats_s")
    if isinstance(grid, np.ndarray):
        grid = grid.tolist()
    if not isinstance(grid, (list, tuple)) or len(grid) < 2:
        raise ValueError("beat grid must contain at least two beat times in seconds")
    times = []
    for time in grid:
        if (
            isinstance(time, bool)
            or not isinstance(time, (int, float))
            or not math.isfinite(time)
            or time < 0
        ):
            raise ValueError("beat times must be finite nonnegative numbers")
        if times and time <= times[-1]:
            raise ValueError("beat times must be strictly increasing")
        times.append(float(time))
    if not isinstance(beats, (list, tuple)) or len(beats) != 2:
        raise ValueError("beats must be [start_index, end_index]")
    start, end = beats
    if any(isinstance(value, bool) or not isinstance(value, int) for value in beats):
        raise ValueError("beat indices must be integers")
    if not 1 <= start < end <= len(times):
        raise ValueError(f"beat indices must satisfy 1 <= start < end <= {len(times)}")
    record = {
        "start_index": start,
        "end_index": end,
        "index_base": 1,
        "beats_s": times,
        "source": source,
    }
    return [times[start - 1], times[end - 1]], record


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
    start_frame = frame_of(start_seconds, rate)
    end_frame = frame_of(end_seconds, rate) if end_seconds is not None else None
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


def read_published(
    run_dir: Path,
) -> tuple[bytes, int, dict[str, np.ndarray], dict[str, str]]:
    """Compatibility adapter; published-audio reading belongs to render_store."""
    published = render_store.read_published(run_dir)
    return (
        published.manifest_bytes,
        published.sample_rate,
        published.outputs,
        {name: ref.file for name, ref in published.references.items()},
    )


def excerpt(
    run_dir: str | Path,
    *,
    out: str | Path,
    range: list[float | None] | None = None,
    beat_grid: str | Path | list[float] | np.ndarray | None = None,
    beats: list[int] | None = None,
    outputs: list[str] | None = None,
) -> dict[str, Any]:
    """Slice an existing run's published, hash-verified outputs into a new run directory.

    `range` is `[start_seconds, end_seconds]` (end may be `None`, meaning to each output's
    end); `outputs` is a list of output names to publish (default: every published output).
    Every selected output is re-verified against its recorded sha256 and metadata before
    slicing, so a tampered or corrupted source run fails loudly instead of publishing a
    silently wrong excerpt.

    Alternatively supply `beat_grid` (seconds array or JSON path) and `beats=[start, end]`.
    Indices are 1-based beat points; 9:17 spans eight intervals, end exclusive. JSON
    accepts a raw list, a beats_s object or an analysis record with result.beats_s.
    Times are relative to the source run, not inferred from BPM or meter. No reanalysis.

    Absolute boundaries use timing.frame_of: floor(seconds * sample_rate + 0.5),
    with half-sample ties going to the later frame. End frames are exclusive.
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
        beat_record = None
        if beats is not None or beat_grid is not None:
            if range is not None or beats is None or beat_grid is None:
                raise ValueError("supply either range or both beat_grid and beats")
            range, beat_record = _beat_range(beat_grid, beats)
        range = _resolve_range(range)
        outputs = _resolve_outputs(outputs) if outputs is not None else None
    except (ValueError, TypeError, OSError, RecursionError) as exc:
        raise RunError("invalid_request", "request", str(exc)) from exc

    completed = False
    created = False
    try:
        published = render_store.read_published(run_dir)
        rate = published.sample_rate

        selected, range_record, source_frames = _select_and_slice(
            published.outputs, rate, range, outputs
        )

        try:
            out.mkdir(parents=True, exist_ok=False)
            created = True
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
                    "manifest_sha256": hashlib.sha256(published.manifest_bytes).hexdigest(),
                },
            }
            if beat_record is not None:
                manifest_out["beat_selection"] = beat_record
            write_json(out / "manifest.json", manifest_out)
        except (ValueError, TypeError, OSError) as exc:
            raise RunError("invalid_request", "publish", str(exc)) from exc
        completed = True
        return {
            "status": "ok",
            "outputs": {name: str(out / ref["file"]) for name, ref in references.items()},
            "manifest": str(out / "manifest.json"),
        }
    finally:
        if created and not completed:
            shutil.rmtree(out, ignore_errors=True)
