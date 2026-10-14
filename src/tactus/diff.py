"""Where two runs of a work differ, output by output and over time.

The comparison is measured, not reported by whoever made the change: the second run minus
the level-aligned first. One gain aligns the pair (the median of each shared output's
least-squares gain), so a master-level change alone is not a difference. Each output's
residual is read in short windows; a window differs when the residual is above
`RESIDUAL_FLOOR_DBFS` and within `RELATIVE_FLOOR_DB` of the louder side, and is `major`
when within `MAJOR_DB`. On one work these thresholds separated three causes cleanly:
identical outputs sit near -146 dBFS (PCM24 rounding), an edit and what it drives sit above
-20 dB relative, and a different library version left -26 to -39 dB relative differences
across the whole piece. The result names such causes when the receipts show them
(an uncommitted patch, different Tactus commits) and leaves the judgement to the reader.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from . import render_store

RESIDUAL_FLOOR_DBFS = -70.0
RELATIVE_FLOOR_DB = -40.0
MAJOR_DB = -20.0
WINDOW_S = 0.25  # without a tempo; with one, half a beat


def _db(value: float) -> float:
    return 20.0 * math.log10(value) if value > 0 else -math.inf


def _stereo(audio: np.ndarray) -> np.ndarray:
    return audio[:, None] if audio.ndim == 1 else audio


def _window_rms(audio: np.ndarray, window: int) -> np.ndarray:
    count = math.ceil(len(audio) / window)
    padded = np.zeros((count * window, audio.shape[1]))
    padded[: len(audio)] = audio
    return np.sqrt((padded**2).mean(axis=1).reshape(count, window).mean(axis=1))


def _ranges(res: np.ndarray, level: np.ndarray, window_s: float, end_s: float) -> list[dict]:
    with np.errstate(divide="ignore", invalid="ignore"):  # silence against silence is NaN: not hot
        res_db = 20.0 * np.log10(res)
        rel_db = res_db - 20.0 * np.log10(level)
    hot = (res_db > RESIDUAL_FLOOR_DBFS) & (rel_db > RELATIVE_FLOOR_DB)
    out, index, count = [], 0, len(hot)
    while index < count:
        if not hot[index]:
            index += 1
            continue
        last = index
        # A single quiet window between two differing ones does not split a range.
        while last + 1 < count and (hot[last + 1] or (last + 2 < count and hot[last + 2])):
            last += 1
        rel = float(rel_db[index : last + 1][hot[index : last + 1]].max())
        out.append(
            {
                "start_s": round(index * window_s, 4),
                "end_s": round(min((last + 1) * window_s, end_s), 4),
                "res_db": round(float(res_db[index : last + 1].max()), 1),
                "rel_db": round(rel, 1),
                "major": rel > MAJOR_DB,
            }
        )
        index = last + 1
    return out


def _side(run_dir: Path) -> dict:
    receipt = json.loads((run_dir / "receipt.json").read_text())
    git = receipt.get("git") or {}
    tactus = ((receipt.get("package_sources") or {}).get("tactus") or {}).get("git") or {}
    patch = run_dir / "source.patch"
    return {
        "run": str(run_dir),
        "git_commit": git.get("commit"),
        "dirty": git.get("dirty"),
        "patch": str(patch) if git.get("dirty") and patch.is_file() else None,
        "parameters": receipt.get("parameters") or {},
        "tactus": tactus.get("commit"),
    }


def compare(run_a: str | Path, run_b: str | Path, *, bpm: float | None = None) -> dict:
    """Compare two completed runs. Times are seconds from the start of the outputs.

    Returns `gain_db` (applied to `a` before subtracting), `window_s`, the thresholds, `a` and
    `b` (run, commit, dirty, patch, parameters, Tactus commit), `causes` (hints read from the
    receipts) and `outputs`: for each name `kind` (`same`, `changed`, `new` in `b`, `missing`
    from `b`) and `ranges` of `start_s`, `end_s`, `res_db` (largest residual window, dBFS),
    `rel_db` (largest residual relative to the louder side) and `major`.
    `bpm` sets the window to half a beat. Outputs are read as published (PCM24).
    """
    a_dir, b_dir = Path(run_a).resolve(), Path(run_b).resolve()
    a, b = render_store.read_published(a_dir), render_store.read_published(b_dir)
    if a.sample_rate != b.sample_rate:
        raise ValueError(f"sample rates differ: {a.sample_rate} and {b.sample_rate}")
    if bpm is not None and not bpm > 0:
        raise ValueError("bpm must be positive")
    rate = a.sample_rate
    window_s = 30.0 / bpm if bpm else WINDOW_S
    window = max(1, round(window_s * rate))
    window_s = window / rate
    shared = [name for name in b.outputs if name in a.outputs]

    gains = []
    for name in shared:
        x, y = _stereo(a.outputs[name]), _stereo(b.outputs[name])
        if x.shape[1] != y.shape[1]:
            continue
        frames = min(len(x), len(y))
        energy = float((x[:frames] ** 2).sum())
        if energy > 0:
            gain = float((x[:frames] * y[:frames]).sum()) / energy
            if gain > 0:
                gains.append(gain)
    gain = float(np.median(gains)) if gains else 1.0

    outputs: dict[str, dict] = {}
    for name in dict.fromkeys([*a.outputs, *b.outputs]):
        if name not in a.outputs or name not in b.outputs:
            only = _stereo((b if name in b.outputs else a).outputs[name])
            rms = _window_rms(only, window)
            ranges = _ranges(rms, rms, window_s, len(only) / rate)
            outputs[name] = {"kind": "new" if name in b.outputs else "missing", "ranges": ranges}
            continue
        x, y = _stereo(a.outputs[name]) * gain, _stereo(b.outputs[name])
        note = None
        if x.shape[1] != y.shape[1]:
            x, y = x.mean(axis=1, keepdims=True), y.mean(axis=1, keepdims=True)
            note = "channel counts differ; compared as mono"
        frames = max(len(x), len(y))
        padded = [np.zeros((frames, side.shape[1])) for side in (x, y)]
        padded[0][: len(x)], padded[1][: len(y)] = x, y
        level = np.maximum(_window_rms(padded[0], window), _window_rms(padded[1], window))
        ranges = _ranges(_window_rms(padded[1] - padded[0], window), level, window_s, frames / rate)
        entry: dict = {"kind": "changed" if ranges else "same", "ranges": ranges}
        if len(x) != len(y):
            note = f"lengths differ: {len(x) / rate:.3f} s and {len(y) / rate:.3f} s"
        if note:
            entry["note"] = note
        outputs[name] = entry

    sides = {"a": _side(a_dir), "b": _side(b_dir)}
    causes = []
    for key, side in sides.items():
        if side["patch"]:
            causes.append(f"{key} was rendered with uncommitted source changes ({side['patch']})")
    if sides["a"]["git_commit"] != sides["b"]["git_commit"]:
        causes.append("the work's commits differ")
    if sides["a"]["parameters"] != sides["b"]["parameters"]:
        causes.append("the render parameters differ")
    if sides["a"]["tactus"] != sides["b"]["tactus"]:
        causes.append(
            f"Tactus differs between the runs ({sides['a']['tactus']} and {sides['b']['tactus']}): "
            "small differences across the whole piece can come from the library, not the work"
        )
    return {
        **sides,
        "sample_rate": rate,
        "gain_db": round(_db(gain), 4),
        "window_s": round(window_s, 6),
        "thresholds": {
            "residual_floor_dbfs": RESIDUAL_FLOOR_DBFS,
            "relative_floor_db": RELATIVE_FLOOR_DB,
            "major_db": MAJOR_DB,
        },
        "causes": causes,
        "outputs": outputs,
    }
