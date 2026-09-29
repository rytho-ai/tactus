# Project analysis and export commands

Install the CLI once with uv. Inside a work, `tactus` runs with that work's locked Tactus
version and dependencies. Register the work's Python functions by name; use the same CLI
for built-in and custom operations.

## Install and select a work

For a fixed installation, replace `FULL_COMMIT` with the chosen published commit SHA:

```bash
uv tool install --python 3.12 "tactus @ git+https://github.com/rytho-ai/tactus.git@FULL_COMMIT"
tactus init my-work
cd my-work
```

The tool is installed from Git, so editing or switching a development checkout cannot
change it. `init` pins the same commit in the work. Use `--force` when replacing an existing
tool installation. This fixes the Tactus source revision; the work's `uv.lock` fixes its
full dependency environment.

For a development checkout:

```bash
uv tool install --python 3.12 --editable /path/to/tactus
tactus init my-work --tactus-path /path/to/tactus
cd my-work
uv add PACKAGE  # only when the work needs another dependency
```

For a portable work, `tactus init DIR --tactus URL@REV` pins a published revision instead.
An editable path follows local source changes; it does not freeze the checkout.

From then on, use `tactus ...` directly. The launcher discovers the nearest `pyproject.toml`
from the current directory, including parent directories. An unrelated nearest Python
project ends discovery. In a Tactus work it runs `uv run --project DIR --locked -- python -m
tactus.cli ...`. This installs/syncs the locked environment as needed. Missing or outdated
locks fail with no fallback to the global installation; use `uv lock` when intentionally
changing dependencies. `tactus doctor` reports the selected project, interpreter and version.
`init` uses the launcher installation; outside a work commands use the global environment.

Use `tactus --project /path/to/work ...` to select a work from elsewhere. Put `--project`
before the subcommand. File arguments remain relative to your invoking directory. A work
pinned to an older Tactus exposes that version's commands; update its dependency deliberately
to adopt new commands. `uv run tactus ...` remains usable but is unnecessary for daily use.

## Register local functions

```toml
[tool.tactus.analysis]
"stereo.width" = "measurements:width"

[tool.tactus.export]
"my-delivery" = "delivery:bundle"
```

Modules are imported from the work root or installed dependencies. Use distinctive module
names that do not shadow Python or dependency packages. Only the selected custom function is
imported; listing commands does not import all plugins. Built-in name conflicts are errors.
Functions must be synchronous, with the first two arguments as shown below and additional
parameters keyword-only. They remain directly callable from Python.

Parameters become flags: `window_ms: float = 100` becomes `--window-ms 100`. Parameters
without defaults are required. `bool` becomes `--flag` / `--no-flag`; `str`, `int`, `float`
use those types; lists/dicts and other annotations parse JSON. An unannotated flag takes a
string. Use annotations and JSON-valued defaults. `out`, help and dispatch fields are
reserved. Type parsing does not replace validation inside your function.

## Analyze

```python
import numpy as np


def width(audio, sample_rate, *, window_ms: float = 100.0):
    """Measure the first window's stereo side/mid RMS ratio (linear)."""
    if audio.ndim != 2 or audio.shape[1] != 2:
        raise ValueError("stereo required")
    frames = round(window_ms * sample_rate / 1000)
    if frames < 1:
        raise ValueError("window too short")
    audio = audio[:frames]
    mid = (audio[:, 0] + audio[:, 1]) / 2
    side = (audio[:, 0] - audio[:, 1]) / 2
    denominator = np.sqrt(np.mean(mid ** 2))
    return {"ratio": float(np.sqrt(np.mean(side ** 2)) / denominator) if denominator else None}
```

The runnable [example](../examples/project-commands/README.md) implements windowed values
and an optional array curve.

```bash
tactus analyze --help
tactus analyze stereo width --help
tactus analyze stereo width mix.wav --window-ms 100 --out measurements
```

The function receives decoded float64 audio (mono `(frames,)` or interleaved channels) and
its sample rate. It returns a dict. Each input produces one JSON line with `path`, `analysis`,
`revision` (optional function attribute, otherwise null), effective `params`, `sample_rate`,
`result`, `input_sha256` and `provenance`. A run directory measures its published audition
WAVs and adds each output name. It does not substitute original arrays for the heard audio.
Non-finite scalar measurements become null.

`--out DIR` saves each result under its own input/command identity directory, along with
`result.json`. Nested NumPy arrays become attachments in `arrays.npz`; their JSON references
include `file`, `key`, `shape` and `dtype`. Arrays require `--out`; object arrays are rejected.
Existing result directories are preserved and rejected on repeat; choose a new destination
for a fresh execution. A callable may reserve keyword-only `out` to receive a runtime-owned
NPZ file path (or None), as the built-in STFT does; returning arrays is simpler for new code.
Logs go to stderr. Freeze accepted analysis results as materials or constants before using
them for creative decisions in `render`.

## Export a completed render

```bash
tactus export wav runs/a --out delivery/pcm
tactus export wav runs/a --subtype DOUBLE --out delivery/original
tactus export flac runs/a --out delivery/flac
tactus export stems runs/a --names '["drums", "bass"]' --out delivery/stems
tactus export my-delivery runs/a --out delivery/label --title "Chosen candidate"
```

`run` saves original returned arrays plus their receipt in `render/` and `render.json` before
writing the default PCM24 audition WAVs. It still renders and delivers in one command. If
that delivery fails after the checkpoint, the original arrays and candidate takes survive;
retry with `tactus export`, without rerunning instruments. Failures before completion remove
the new run directory. Keep `render.json`, `render/` and `receipt.json` together.

This adds storage: float32 arrays use about 4 bytes per sample value, float64 about 8, in
addition to 3 bytes for PCM24 audition audio (plus headers and provenance). There is no
automatic cleanup. Saved takes separately preserve selected intermediate performances as
reusable materials; `take export` transfers one of those bundles.

Export verifies the checkpoint's array and receipt hashes. `wav` defaults to the identical
PCM24 conversion and filenames used by `run`; FLOAT casts to float32 and DOUBLE to float64,
preserving headroom. `flac` and `stems` encode PCM24 with clipping counts. `stems` defaults to
every named output except literal `mix`; explicit `--names` selects a JSON list. No exporter
resamples, aligns, normalizes or assumes stems sum to the master. Older runs/excerpts without
`render.json` use verified saved WAVs; the record labels this `published-pcm`, whose lost
precision/headroom cannot be recovered. A corrupt checkpoint fails instead of using PCM.

A custom exporter receives verified, read-only named arrays and the sample rate:

```python
import soundfile as sf


def bundle(outputs, sample_rate, *, out, title: str = "Demo"):
    """Deliver the chosen mix as FLOAT WAV."""
    sf.write(out / "mix.wav", outputs["mix"], sample_rate, subtype="FLOAT")
    return {"title": title, "mix": "mix.wav"}
```

`out` is a newly created `pathlib.Path` directory, outside the source run. Write artifacts
there and return a finite JSON dict, using relative paths for your files. The runtime hashes
all files and writes `export.json` last, with source identity, callable, effective parameters,
result and provenance. This filename is reserved; symlinks and special files are rejected.
On failure only the newly created delivery directory is removed. Existing output locations
are rejected before calling your exporter. Exporting never invokes the original render code.

## Attribution boundary

Records include input hashes, callable source identity, local Python source inventory,
pyproject hash, dependency lock, actual environment/packages, and declared materials/tools.
Changes to observed input or project source during analysis/export fail the operation.
The source inventory covers local `.py` files, not every external file Python might read.
These are trusted Python functions: external I/O, network, randomness and side effects are
not sandboxed or exhaustively traced. Commit custom code, registration and the work's lock
with the work; pin any additional inputs with `material()` / `tool()`.
